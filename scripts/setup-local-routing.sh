#!/usr/bin/env bash
#
# setup-local-routing.sh — local (LAN) routing for a Nephos k3d cluster so App
# route URLs work as-is in the browser: http://<slug>.<domain> with no port.
#
# What it sets up:
#   1. a k3d cluster whose loadbalancer publishes host 80/443 (traefik ingress),
#      so canonicalUrl (http://<slug>.<domain>, port 80) is directly reachable;
#   2. a dnsmasq wildcard so every *.<domain> resolves to the bind IP;
#   3. a macOS /etc/resolver entry so the whole system (all browsers) uses it.
#
# After this, set the Nephos default platform domain to <domain> (see the end).
#
# macOS + Homebrew + Docker Desktop + k3d assumed. Some steps use sudo (prompts).
#
# Usage:
#   scripts/setup-local-routing.sh [DOMAIN] [BIND_IP]
#     DOMAIN   default: nephos.lcl
#     BIND_IP  default: 127.0.0.1   (use your LAN IP, e.g. 192.168.178.221,
#              to also reach apps from other devices; then point those devices'
#              DNS at this machine and give it a DHCP reservation)
set -euo pipefail

DOMAIN="${1:-nephos.lcl}"
BIND_IP="${2:-127.0.0.1}"
CLUSTER="${NEPHOS_K3D_CLUSTER:-nephos}"

echo "==> Nephos local routing: domain=${DOMAIN} bind=${BIND_IP} cluster=${CLUSTER}"

# --- prerequisites -----------------------------------------------------------
for bin in docker k3d brew; do
  command -v "$bin" >/dev/null || { echo "missing: $bin"; exit 1; }
done
# dnsmasq is configured + restarted below; make sure it is installed *before*
# we touch its config, so a fresh host doesn't fail half-way.
if ! brew list dnsmasq >/dev/null 2>&1; then
  echo "==> installing dnsmasq"
  brew install dnsmasq
fi

LB="k3d-${CLUSTER}-serverlb"

# Ports 80/443 must be free before we bind them. A conflict is another
# container (not this cluster's own loadbalancer) already publishing them
# (a common one is cloud-provider-kind's 'kindccm-*').
for port in 80 443; do
  if docker ps --format '{{.Names}} {{.Ports}}' | grep ":${port}->" | grep -qv "^${LB} "; then
    holder="$(docker ps --format '{{.Names}} {{.Ports}}' | grep ":${port}->" | grep -v "^${LB} " | head -1)"
    echo "port ${port} is already published by another container:"
    echo "  ${holder}"
    echo "free it first (e.g. 'docker stop <name>') then re-run."
    exit 1
  fi
done

# --- 1. k3d cluster with ingress on 80/443 -----------------------------------
if ! k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  echo "==> creating k3d cluster '${CLUSTER}' with ingress on 80/443"
  k3d cluster create "$CLUSTER" \
    --port "80:80@loadbalancer" \
    --port "443:443@loadbalancer" \
    --wait
else
  # Existing cluster: ensure the loadbalancer actually publishes 80/443, else
  # the portless URLs below would silently not work.
  echo "==> cluster '${CLUSTER}' exists; ensuring ingress on 80/443"
  lb_ports="$(docker ps --filter "name=${LB}" --format '{{.Ports}}' 2>/dev/null || true)"
  add_args=()
  echo "$lb_ports" | grep -q ':80->'  || add_args+=("--port-add" "80:80@loadbalancer")
  echo "$lb_ports" | grep -q ':443->' || add_args+=("--port-add" "443:443@loadbalancer")
  if [ "${#add_args[@]}" -gt 0 ]; then
    echo "    adding missing ports: ${add_args[*]}"
    k3d cluster edit "$CLUSTER" "${add_args[@]}"
  else
    echo "    already on 80/443."
  fi
fi

# --- 2. dnsmasq wildcard  *.<domain> -> BIND_IP ------------------------------
DNSMASQ_CONF="$(brew --prefix)/etc/dnsmasq.conf"
RULE="address=/${DOMAIN}/${BIND_IP}"
echo "==> dnsmasq: ${RULE}"
if ! grep -qxF "$RULE" "$DNSMASQ_CONF" 2>/dev/null; then
  echo "$RULE" | sudo tee -a "$DNSMASQ_CONF" >/dev/null
fi
# dnsmasq binds :53 -> run as root via brew services
sudo brew services restart dnsmasq

# --- 3. macOS resolver: send *.<domain> lookups to dnsmasq -------------------
echo "==> /etc/resolver/${DOMAIN} -> ${BIND_IP}"
sudo mkdir -p /etc/resolver
printf 'nameserver %s\n' "$BIND_IP" | sudo tee "/etc/resolver/${DOMAIN}" >/dev/null

# --- verify ------------------------------------------------------------------
echo "==> verify DNS"
dscacheutil -q host -a name "test-app.${DOMAIN}" | awk '/ip_address/{print "  test-app."ENVIRON["DOMAIN"]" -> "$2}' DOMAIN="$DOMAIN" || true

cat <<EOF

==> done. Next: point Nephos at this domain (API on :8099):

  curl -sS -X POST http://127.0.0.1:8099/platform/config/domains \\
    -H 'content-type: application/json' \\
    -d '{"name":"lcl","domain":"${DOMAIN}","default":true}'

  # then reconcile installed apps so their Ingress hosts pick up the new domain:
  #   POST /apps/<slug>/actions/reconcile

Apps are then reachable at:  http://<slug>.${DOMAIN}
EOF
