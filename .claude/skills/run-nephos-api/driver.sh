#!/usr/bin/env bash
# Drive nephos-api: a FastAPI control plane that reconciles desired state into
# Kubernetes. Agent-facing harness for the run-nephos-api skill.
#
# Two modes:
#   local-*    runs the API on this host against a throwaway DB + catalog. Fast,
#              no cluster, no network. Reconciliation is inert (no runtime), so
#              installs stay `pending`. Right for API/catalog/schema work.
#   cluster-*  builds an image into k3d and drives the in-cluster deployment,
#              where reconciliation actually reaches Kubernetes.
#
# Usage: driver.sh <command> [args]
#   local-up            init a throwaway state dir + catalog, serve on :8099
#   local-smoke         end-to-end: catalog -> install -> admin -> token -> reveal
#   local-down          stop the server, remove the throwaway dir
#   api METHOD PATH [JSON]      curl the running API, pretty-printed
#   wait-status SLUG [LEVEL]    poll a service until status.level is terminal
#   mint-token [MINUTES]        insert a bearer token straight into the local DB
#   cluster-deploy      docker build -> k3d import -> rollout -> port-forward
#   cluster-smoke       drive the in-cluster API (expects cluster-deploy first)
#   cluster-mint-token [MINUTES]  same, against the DB on the PVC
#   cluster-revoke-tokens         delete every driver-minted token
#   test                the non-kubernetes test suite
set -uo pipefail

UNIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PORT="${NEPHOS_DRIVER_PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"
RUN_DIR="${NEPHOS_DRIVER_DIR:-/tmp/nephos-driver}"
DB="${RUN_DIR}/state/nephos.db"
CATALOG="${RUN_DIR}/catalog"
PIDFILE="${RUN_DIR}/serve.pid"
PFFILE="${RUN_DIR}/portforward.pid"
DOMAIN="${NEPHOS_API_INTERNAL_DOMAIN:-nephos.lcl}"
IMAGE="${NEPHOS_DRIVER_IMAGE:-nephos-api:driver}"
ADMIN_USER="driver-admin"
ADMIN_PASS="Driver-P@ss1"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- local catalog
# A self-contained fixture so `local-up` works with no registry access. The real
# registries are git clones from git.fcrozetta.app that the API syncs at startup;
# see the CATALOG_ROOTS gotcha in SKILL.md for why we replace rather than add.
write_catalog() {
  mkdir -p "${CATALOG}/services/demodb"
  cat >"${CATALOG}/services/demodb/service.yaml" <<'YAML'
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: demodb
  displayName: Demo DB
spec:
  provides:
  - capability: sql
    protocol: postgres
    as: sql
  config:
    options:
    - name: image
      type: string
      default: postgres:16-alpine
    - name: admin-password
      type: string
      required: true
      generate:
        kind: password
        length: 32
  credentials:
    username: postgres
    passwordOption: admin-password
  portals:
  - name: console
    displayName: Demo Console
    target:
      port: http
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: demodb
    values:
      mappings: []
YAML
}

# ------------------------------------------------------------------ local serve
cmd_local_up() {
  cd "$UNIT" || die "cannot cd $UNIT"
  say "syncing deps"
  uv sync --quiet || die "uv sync"

  cmd_local_down >/dev/null 2>&1
  mkdir -p "${RUN_DIR}/state"
  write_catalog

  # NEPHOS_API_INTERNAL_DOMAIN has no baked default; init fails fast without it.
  # NEPHOS_API_CATALOG_ROOTS replaces the managed git registries entirely, which
  # is what keeps this offline.
  say "init (domain ${DOMAIN})"
  env NEPHOS_API_DB_PATH="$DB" \
      NEPHOS_API_CATALOG_ROOTS="$CATALOG" \
      NEPHOS_API_INTERNAL_DOMAIN="$DOMAIN" \
    uv run nephos-api init --internal-domain "$DOMAIN" >"${RUN_DIR}/init.log" 2>&1 \
    || { cat "${RUN_DIR}/init.log"; die "init"; }

  say "serving on ${BASE}"
  env NEPHOS_API_DB_PATH="$DB" \
      NEPHOS_API_CATALOG_ROOTS="$CATALOG" \
      NEPHOS_API_INTERNAL_DOMAIN="$DOMAIN" \
    uv run nephos-api serve --host 127.0.0.1 --port "$PORT" \
      >"${RUN_DIR}/serve.log" 2>&1 &
  echo $! >"$PIDFILE"

  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null --max-time 2 "${BASE}/healthz" 2>/dev/null && {
      printf 'healthz: %s\n' "$(curl -fsS "${BASE}/healthz")"
      return 0
    }
    sleep 1
  done
  tail -30 "${RUN_DIR}/serve.log"
  die "server did not become healthy"
}

cmd_local_down() {
  for f in "$PFFILE" "$PIDFILE"; do
    [ -f "$f" ] && { kill "$(cat "$f")" 2>/dev/null; rm -f "$f"; }
  done
  pkill -f "nephos-api serve --host 127.0.0.1 --port ${PORT}" 2>/dev/null
  rm -rf "$RUN_DIR"
  echo "stopped"
}

# --------------------------------------------------------------------- API verbs
cmd_api() {
  local method="${1:?METHOD}" path="${2:?PATH}" body="${3:-}"
  local args=(-sS -X "$method" -H 'content-type: application/json')
  [ -n "$body" ] && args+=(--data "$body")
  [ -n "${NEPHOS_DRIVER_TOKEN:-}" ] &&
    args+=(-H "Authorization: Bearer ${NEPHOS_DRIVER_TOKEN}")
  curl "${args[@]}" "${BASE}${path}" |
    python3 -c 'import json,sys
raw=sys.stdin.read()
try: print(json.dumps(json.loads(raw), indent=2))
except Exception: print(raw)'
}

cmd_wait_status() {
  local slug="${1:?SLUG}" want="${2:-}"
  for i in $(seq 1 60); do
    local level
    level=$(curl -sS "${BASE}/services/${slug}" 2>/dev/null |
      python3 -c 'import json,sys
try: s=(json.load(sys.stdin).get("status") or {}); print(s.get("level") or "")
except Exception: print("")' )
    printf '[%02d] %s\n' "$i" "${level:-<none>}"
    [ -n "$want" ] && [ "$level" = "$want" ] && return 0
    case "$level" in healthy|blocked|degraded) [ -z "$want" ] && return 0 ;; esac
    sleep 3
  done
  die "status never settled for ${slug}"
}

# Bearer tokens gate the reveal endpoint. Minting one straight into the DB avoids
# needing the operator's password, which the driver must never hold.
cmd_mint_token() {
  local minutes="${1:-20}"
  python3 - "$DB" "$minutes" <<'PY'
import datetime, hashlib, secrets, sqlite3, sys
db, minutes = sys.argv[1], int(sys.argv[2])
tok = secrets.token_urlsafe(32)
exp = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes))
exp = exp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
c = sqlite3.connect(db)
c.execute("DELETE FROM admin_tokens WHERE subject='driver'")
c.execute(
    "INSERT INTO admin_tokens(id,token_hash,subject,expires_at,created_at)"
    " VALUES (?,?,?,?,?)",
    ("admtok_driver", hashlib.sha256(tok.encode()).hexdigest(), "driver", exp, exp),
)
c.commit()
print(tok)
PY
}

# In-cluster the desired-state DB lives on the PVC, so the local mint-token
# cannot reach it. Exec into the pod instead. Same trick, same reason: it avoids
# the driver ever holding the operator's password.
cmd_cluster_mint_token() {
  local minutes="${1:-20}"
  kubectl -n nephos-system exec deploy/nephos-api -c nephos-api -- python3 -c "
import datetime, hashlib, secrets, sqlite3
tok = secrets.token_urlsafe(32)
exp = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=${minutes}))
exp = exp.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
c = sqlite3.connect('/data/state/nephos.db')
c.execute(\"DELETE FROM admin_tokens WHERE subject='driver'\")
c.execute('INSERT INTO admin_tokens(id,token_hash,subject,expires_at,created_at)'
          ' VALUES (?,?,?,?,?)',
          ('admtok_driver', hashlib.sha256(tok.encode()).hexdigest(), 'driver', exp, exp))
c.commit()
print(tok)
"
}

cmd_cluster_revoke_tokens() {
  kubectl -n nephos-system exec deploy/nephos-api -c nephos-api -- python3 -c "
import sqlite3
c = sqlite3.connect('/data/state/nephos.db')
c.execute(\"DELETE FROM admin_tokens WHERE subject='driver'\")
c.commit()
print('driver tokens remaining:',
      c.execute(\"select count(*) from admin_tokens where subject='driver'\").fetchone()[0])
"
}

# ------------------------------------------------------------------- local smoke
cmd_local_smoke() {
  cmd_local_up || die "local-up"

  say "catalog sees the fixture Service"
  cmd_api GET /catalog/services |
    python3 -c 'import json,sys
d=json.load(sys.stdin)
names=[s["name"] for s in d["services"]]
assert "demodb" in names, names
print("  services:", names)
e=[s for s in d["services"] if s["name"]=="demodb"][0]
print("  portals:", [p["name"] for p in e["portals"]])
print("  credentials:", e["credentials"])' || die "catalog"

  say "install (config={} : admin-password is generated, needs no input)"
  cmd_api POST /services \
    '{"catalogRef":{"kind":"Service","name":"demodb"},"config":{}}' |
    python3 -c 'import json,sys
d=json.load(sys.stdin)
assert "resource" in d, d
print("  slug:", d["resource"]["slug"], "| lifecycle:", d["resource"]["lifecycle"])
print("  credentials:", d["resource"]["credentials"])' || die "install"

  say "portal reports unpublished (default-deny per root domain)"
  cmd_api GET /services/demodb |
    python3 -c 'import json,sys
p=json.load(sys.stdin)["portals"][0]
print("  published:", p["published"], "| reason:", p["unpublishedReason"])
assert p["published"] is False' || die "portal"

  say "opt the domain in to Service portals"
  local dom
  dom=$(curl -sS "${BASE}/platform/config/domains" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["domains"][0]["name"])')
  cmd_api POST "/platform/config/domains/${dom}/actions/set-service-portals" \
    '{"allowed":true}' >/dev/null
  cmd_api GET /services/demodb |
    python3 -c 'import json,sys
p=json.load(sys.stdin)["portals"][0]
print("  published:", p["published"], "| url:", p["canonicalUrl"])
assert p["published"] is True' || die "portal opt-in"

  say "reveal is gated"
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
    "${BASE}/services/demodb/config/admin-password/actions/reveal")
  [ "$code" = "401" ] || die "expected 401 unauthenticated, got ${code}"
  echo "  unauthenticated reveal: ${code}"

  say "mint a token and reveal"
  NEPHOS_DRIVER_TOKEN="$(cmd_mint_token 10)"
  export NEPHOS_DRIVER_TOKEN
  # No secrets provider is wired locally, so a generated secret has nowhere to
  # come from. 503 here is the correct fail-closed answer, not a driver bug.
  cmd_api POST /services/demodb/config/admin-password/actions/reveal |
    python3 -c 'import json,sys
d=json.load(sys.stdin)
if "value" in d:
    print("  revealed:", "<%d chars>" % len(d["value"]), "| source:", d["source"])
else:
    code=d["error"]["code"]
    print("  fail-closed:", code)
    assert code in ("secret_ref_provider_unavailable","secret_ref_unavailable"), d' \
    || die "reveal"

  say "PASS"
  cmd_local_down
}

# ----------------------------------------------------------------- cluster verbs
cmd_cluster_deploy() {
  cd "$UNIT" || die "cannot cd $UNIT"
  k3d cluster list 2>/dev/null | grep -q '^nephos' || die "no k3d cluster named nephos"
  # A stopped cluster shows 0/1 servers; start beats recreate.
  if k3d cluster list nephos | awk 'NR==2{print $2}' | grep -q '^0/'; then
    say "starting stopped cluster"
    k3d cluster start nephos || die "k3d cluster start"
  fi

  say "build ${IMAGE}"
  docker build -q -t "$IMAGE" . >/dev/null || die "docker build"
  say "import into k3d"
  # Every step below is guarded. `pipefail` alone does not stop the script, and an
  # unguarded failure here is the worst kind: an older cached image under the same
  # tag keeps the old deployment healthy, the final health check passes, and
  # cluster-deploy exits 0 having deployed nothing new.
  local import_log
  import_log=$(k3d image import "$IMAGE" -c nephos 2>&1) || die "k3d image import"
  printf '%s\n' "$import_log" | tail -1

  say "point the Deployment at it"
  kubectl -n nephos-system set image deploy/nephos-api \
    nephos-api="$IMAGE" init="$IMAGE" >/dev/null || die "kubectl set image"
  # The manifest defaults to :latest, so imagePullPolicy is Always and `set image`
  # does not change it: a locally-imported tag would ImagePullBackOff.
  kubectl -n nephos-system patch deploy/nephos-api --type=json -p '[
    {"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"IfNotPresent"},
    {"op":"replace","path":"/spec/template/spec/initContainers/0/imagePullPolicy","value":"IfNotPresent"}]' >/dev/null || die "kubectl patch imagePullPolicy"
  kubectl -n nephos-system rollout restart deploy/nephos-api >/dev/null || die "rollout restart"
  local rollout_log
  rollout_log=$(kubectl -n nephos-system rollout status deploy/nephos-api \
    --timeout=300s 2>&1) || die "rollout did not complete"
  printf '%s\n' "$rollout_log" | tail -1

  say "port-forward ${BASE}"
  mkdir -p "$RUN_DIR"
  [ -f "$PFFILE" ] && { kill "$(cat "$PFFILE")" 2>/dev/null; rm -f "$PFFILE"; }
  kubectl -n nephos-system port-forward svc/nephos-api "${PORT}:8099" \
    >"${RUN_DIR}/pf.log" 2>&1 &
  echo $! >"$PFFILE"
  # One request, not two. Probing and then re-fetching for the message let a
  # port-forward that died in between report success anyway.
  local health
  for _ in $(seq 1 40); do
    if health=$(curl -fsS --max-time 2 "${BASE}/healthz" 2>/dev/null); then
      printf 'healthz: %s\n' "$health"
      return 0
    fi
    sleep 1
  done
  die "in-cluster API not reachable"
}

cmd_cluster_smoke() {
  curl -fsS -o /dev/null --max-time 3 "${BASE}/healthz" ||
    die "no API on ${BASE}; run cluster-deploy first"
  say "installed services"
  # % formatting, not f-strings: this is a single-quoted shell string, so escaped
  # double quotes inside an f-string expression become literal backslashes.
  cmd_api GET /services | python3 -c 'import json,sys
rows=json.load(sys.stdin)["services"]
assert rows, "no services installed"
for s in rows:
    st=(s.get("status") or {}).get("level")
    print("  %-12s %-9s %s" % (s["slug"], s["lifecycle"], st))' || die "list services"

  say "generated ingress"
  # NAMESPACE NAME CLASS HOSTS ADDRESS PORTS AGE
  kubectl get ingress -A --no-headers 2>/dev/null |
    awk '{printf "  %-14s %-22s %s\n", $1, $2, $4}' || echo "  (none)"
  say "PASS"
}

cmd_test() { cd "$UNIT" && uv run ruff check && uv run pytest -q -m "not kubernetes"; }

case "${1:-}" in
  local-up)       cmd_local_up ;;
  local-smoke)    cmd_local_smoke ;;
  local-down)     cmd_local_down ;;
  api)            shift; cmd_api "$@" ;;
  wait-status)    shift; cmd_wait_status "$@" ;;
  mint-token)     shift; cmd_mint_token "$@" ;;
  cluster-deploy) cmd_cluster_deploy ;;
  cluster-smoke)  cmd_cluster_smoke ;;
  cluster-mint-token)   shift; cmd_cluster_mint_token "$@" ;;
  cluster-revoke-tokens) cmd_cluster_revoke_tokens ;;
  test)           cmd_test ;;
  *) sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
