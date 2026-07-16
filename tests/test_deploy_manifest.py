from pathlib import Path

import yaml

from nephos_api.deploy_manifest import render_manifest
from nephos_api.instance import resolve_instance

_MANIFEST = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: nephos-api-env
  namespace: nephos-system
data:
  NEPHOS_API_DB_PATH: /data/state/nephos.db
  KUBECONFIG: /etc/nephos/kube/config
  NEPHOS_API_ENV: lcl
  NEPHOS_API_INTERNAL_DOMAIN: nephos.lcl
  NEPHOS_API_INGRESS_CLASS: traefik
---
apiVersion: v1
kind: Secret
metadata:
  name: nephos-api-secrets
  namespace: nephos-system
stringData:
  PULUMI_CONFIG_PASSPHRASE: change-me
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nephos-api
  namespace: nephos-system
spec:
  template:
    spec:
      initContainers:
        - name: init
          image: ghcr.io/fcrozetta/nephos-api:latest
      containers:
        - name: nephos-api
          image: ghcr.io/fcrozetta/nephos-api:latest
"""


def _manifest_file(tmp_path: Path) -> Path:
    path = tmp_path / "nephos-incluster.yaml"
    path.write_text(_MANIFEST)
    return path


def _by_kind(docs: list[dict], kind: str, name: str) -> dict:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def test_render_injects_passphrase(tmp_path: Path) -> None:
    profile = resolve_instance("lcl")
    out = render_manifest(
        profile, passphrase="s3cret", manifest_path=_manifest_file(tmp_path)
    )
    docs = list(yaml.safe_load_all(out))
    secret = _by_kind(docs, "Secret", "nephos-api-secrets")
    assert secret["stringData"]["PULUMI_CONFIG_PASSPHRASE"] == "s3cret"


def test_render_sets_image_and_pull_policy_on_both_containers(tmp_path: Path) -> None:
    profile = resolve_instance("lcl")
    out = render_manifest(
        profile, passphrase="x", manifest_path=_manifest_file(tmp_path)
    )
    docs = list(yaml.safe_load_all(out))
    pod = _by_kind(docs, "Deployment", "nephos-api")["spec"]["template"]["spec"]
    containers = pod["initContainers"] + pod["containers"]
    assert len(containers) == 2
    for container in containers:
        assert container["image"] == "nephos-api:dev"
        assert container["imagePullPolicy"] == "IfNotPresent"


def test_render_preserves_unrelated_config_keys(tmp_path: Path) -> None:
    profile = resolve_instance("lcl")
    out = render_manifest(
        profile, passphrase="x", manifest_path=_manifest_file(tmp_path)
    )
    docs = list(yaml.safe_load_all(out))
    data = _by_kind(docs, "ConfigMap", "nephos-api-env")["data"]
    # KUBECONFIG (the Pulumi in-cluster kubeconfig) must survive the render.
    assert data["KUBECONFIG"] == "/etc/nephos/kube/config"
    assert data["NEPHOS_API_ENV"] == "lcl"
    assert data["NEPHOS_API_INGRESS_CLASS"] == "traefik"
