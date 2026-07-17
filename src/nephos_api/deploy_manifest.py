"""Render the in-cluster control-plane manifest for a specific instance.

Loads deploy/nephos-incluster.yaml and mutates only the per-instance fields
(env values, image + pull policy on both containers, the Pulumi passphrase),
then emits multi-doc YAML for `kubectl apply -f -`. Setting the pull policy at
render time (rather than a post-apply `set image` + JSON patch) removes the
documented ImagePullBackOff footgun.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nephos_api.instance import InstanceProfile


class ManifestNotFoundError(FileNotFoundError):
    pass


def default_manifest_path() -> Path:
    """Locate deploy/nephos-incluster.yaml.

    The host CLI runs from the repo working tree in v1, so prefer the CWD; fall
    back to the path relative to this package for out-of-tree invocations.
    """
    cwd_candidate = Path.cwd() / "deploy" / "nephos-incluster.yaml"
    if cwd_candidate.exists():
        return cwd_candidate
    pkg_candidate = (
        Path(__file__).resolve().parents[2] / "deploy" / "nephos-incluster.yaml"
    )
    if pkg_candidate.exists():
        return pkg_candidate
    raise ManifestNotFoundError(
        "could not locate deploy/nephos-incluster.yaml (run from the repo root)"
    )


def render_manifest(
    profile: InstanceProfile,
    *,
    passphrase: str,
    manifest_path: Path | None = None,
) -> str:
    path = manifest_path or default_manifest_path()
    docs: list[dict[str, Any]] = [
        doc for doc in yaml.safe_load_all(path.read_text()) if doc
    ]
    for doc in docs:
        kind = doc.get("kind")
        name = doc.get("metadata", {}).get("name")
        if kind == "ConfigMap" and name == "nephos-api-env":
            doc.setdefault("data", {}).update(profile.render_env())
        elif kind == "Secret" and name == "nephos-api-secrets":
            doc.setdefault("stringData", {})["PULUMI_CONFIG_PASSPHRASE"] = passphrase
        elif kind == "Deployment" and name == "nephos-api":
            _apply_image(doc, image=profile.image, policy=profile.image_pull_policy)
    return yaml.safe_dump_all(docs, sort_keys=False)


def _apply_image(deployment: dict[str, Any], *, image: str, policy: str) -> None:
    pod_spec = deployment["spec"]["template"]["spec"]
    for group in ("initContainers", "containers"):
        for container in pod_spec.get(group, []):
            container["image"] = image
            container["imagePullPolicy"] = policy
