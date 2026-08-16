# SeaweedFS S3 identities live in the filer, not a static config file

- Status: accepted
- Deciders: Fer
- Date: 2026-08-16
- Tags: seaweedfs, object-storage, bindings, provisioning, catalog, secrets, phase-1

Amends:

- `20260630-alpha-backbone-binding-output-contracts.md`

Technical Story: the `seaweedfs` Service deploys but cannot be bound. Its
provisioner has never had a client, so every `object-storage/s3` binding blocks
with `binding_provisioner_unavailable`, and the catalog entry demands two
operator-supplied keys, so it can never be offered as a lazy dependency install.

## Context and Problem Statement

ADR 20260630 fixed the App-side Secret keys for a SeaweedFS S3 binding
(`endpointUrl`, `bucket`, `accessKeyId`, `secretAccessKey`, `region`) and closed
with a constraint: Nephos must not report a SeaweedFS Service as wired to
configured S3 credentials unless the pod actually consumes them. That constraint
was satisfied literally — the runtime mounts an `s3.json` Secret and passes
`-s3.config=/etc/seaweedfs/s3.json` — and the binding half was left unbuilt.

Two years of catalog work later the gap is load-bearing. `mythos-mail-ingress`
declares `object-storage/s3` as `raw-mail-storage` and cannot install.
`core-registry/docs/capability-bindings.md` names `seaweedfs` as the default
provider for `object-storage/s3`. The dependency-preflight path added in
`e96b172`/`91dbfea` offers to install a missing capability provider on App
install, but only when `entry_is_turnkey()` holds, and SeaweedFS declares
`s3-access-key` and `s3-secret-key` as `required` with no default and no
generation policy. So SeaweedFS is simultaneously the documented default for
object storage and uninstallable without operator input and unbindable after
install.

Fixing the binding half turns out to be constrained by the runtime shape rather
than by provisioner code. Behaviour pinned against `chrislusf/seaweedfs:3.85`:

- Started **without** `-s3.config`, the S3 API server loads identities from the
  filer at `/etc/iam/identity.json` and subscribes to `/etc/` for metadata
  changes, so identities written at runtime take effect with no restart.
- Started **with** `-s3.config`, it never subscribes to `/etc/`. Identities
  written at runtime are invisible; requests signed with them return
  `InvalidAccessKeyId`.

The two modes are mutually exclusive. A static config file is therefore not a
detail of how the admin credential is delivered — it is a decision to have no
app-scoped provisioning at all.

The remaining question is what the static file was buying. It was buying one
real thing: with no identities configured, SeaweedFS serves S3 **anonymously**
(verified: `GET /` returns `200` with no credentials). A static file guarantees
the admin identity exists from process start, so there is never an open window.
Filer-backed IAM has to earn that guarantee some other way.

## Decision Drivers

- `object-storage/s3` must be provisionable per binding, or the capability is
  decorative and `mythos-mail-ingress` stays uninstallable.
- Per-binding isolation must be real, not nominal. A shared admin key handed to
  every consumer is a credential that can never be rotated.
- SeaweedFS must never serve anonymous S3. This is the security floor.
- Install must require zero operator input, so the capability can be satisfied
  by lazy dependency install.
- No new Python runtime dependency on an S3 client in the control plane.
- Stay inside ADR 20260718: registry-declared engine, backend-executed, no
  registry-authored code in a cluster-admin process.

## Considered Options

- Filer-backed dynamic IAM, admin identity seeded by a service lifecycle
  provisioner.
- Filer-backed dynamic IAM, admin identity seeded by a sidecar in the workload.
- Keep the static config file; bindings hand every consumer the shared admin key
  plus a per-binding bucket.
- Keep the static config file; leave bindings blocked.

## Decision Outcome

Chosen option: **filer-backed dynamic IAM with a lifecycle-seeded admin
identity.**

The `seaweedfs` runtime drops the `-s3.config` argument and stops rendering the
Secret as an `s3.json` document mounted into the pod. Identities live in the
filer store, which sits on the Service's PVC and therefore survives pod restarts
(verified).

The Service Secret itself remains, holding the admin access key and secret key
as plain keys rather than as a config document. It is the coordinate the
lifecycle provisioner reads in order to seed, mirroring how the PostgreSQL
provisioner reads its admin password out of the Service's runtime Secret, and it
keeps the admin credential reachable by authenticated reveal (ADR 20260726) and
Service admin credentials (ADR 20260727).

**Admin identity.** A `ServiceLifecycleProvisioner` seeds the `nephos-admin`
identity immediately after deploy, the same shape `KubernetesOpenBaoLifecycle`
already uses for init/unseal. The deployer's lifecycle hook, currently a
hardcoded `context.provider_name == "openbao"` test, becomes a provider-keyed
mapping; SeaweedFS is the second consumer of a pattern that was written as if it
had one.

**Engine.** The `seaweedfs` manifest declares `provisioning.engine:
object-storage`, and the control plane registers an `object-storage` engine
backed by `SeaweedFSS3Provisioner` with a live client. The engine name follows
the capability name, matching the implemented convention (`sql`, `oidc`,
`opencypher`). ADR 20260718 listed the engine set illustratively as `sql`,
`oidc`, `s3`, `graph-db`; the implementation never used `graph-db`, and this ADR
records capability-name-as-engine-name as the actual convention rather than
leaving the two descriptions to drift.

**Provisioning mechanism.** The client executes `weed shell` inside the Service
pod, the same exec-into-pod approach `KubernetesPsqlRunner` uses for PostgreSQL,
behind a runner protocol so the provisioner is unit-testable without a cluster.
Per binding:

```text
weed shell -master=localhost:9333 -filer=localhost:8888
  s3.bucket.create -name <bucket>
  s3.configure -user <identity> -access_key <key> -secret_key <secret> \
               -buckets <bucket> -actions Read,Write,List,Tagging -apply
```

The filer address is passed explicitly rather than left to master discovery.
Discovery was observed failing on a freshly started instance with
`error: getOrCreateConnection : fail to dial`, which would make provisioning
intermittently fail against a cold pod.

Deprovision is `s3.configure -user <identity> -delete -apply` followed by
`s3.bucket.delete`. Every repeat path is a verified no-op: re-applying an
identical identity, re-creating an existing bucket, deleting a bucket that is
already gone, and deleting an identity that no longer exists all succeed
silently. Reconcile can therefore run repeatedly without special-casing.

`weed shell` exits `0` even when a subcommand fails, so the client detects
failure from the output text (`error:` / `panic:` prefixes) rather than the exit
code. Generated credentials are cached in an owned Kubernetes Secret in
the Service namespace, following the PostgreSQL provisioner's
read-existing-else-create discipline, so a reconcile never rotates a credential
an App is already using.

Choosing `weed shell` over the S3 API also keeps boto3 out of the control
plane's dependency set.

**Turnkey install.** `s3-access-key` and `s3-secret-key` stop being `required`
and gain a `generate` policy. Generation already works for `service_instance`
scope, so the manifest change alone makes `entry_is_turnkey()` hold and no
platform code is involved. Generated values draw from an alphanumeric alphabet,
which is valid for both S3 key positions.

**Output contract.** Unchanged. ADR 20260630's five keys remain the App-side
contract; this ADR changes only how they are produced. `endpointUrl` is the
in-cluster S3 address of the Service, and `region` is `us-east-1`: SeaweedFS
ignores the region, but S3 SDKs refuse to sign a request without one, so
omitting it would produce a Secret that no client can actually use.

**Entitlements.** The `object-storage` engine recognizes no entitlements
(default-deny under ADR 20260721). There is no `admin-credentials` grant for S3;
a consumer that needs cross-bucket access is a decision that should arrive with
its own justification.

**Migration.** None. No SeaweedFS instance is deployed, and the Service is
alpha. A pre-existing install must be destroyed and reinstalled.

### Positive Consequences

- `object-storage/s3` becomes a real capability: per-binding bucket, per-binding
  identity, verified 403 on cross-bucket read and write, and
  `ListAllMyBuckets` filtered to the caller's own bucket. **This holds at the S3
  protocol layer only** -- see the network-exposure consequence below, which
  bounds what that isolation is worth.
- SeaweedFS becomes installable with zero operator input, which makes it
  eligible for lazy dependency install — installing an App that requires
  `object-storage/s3` can offer to install SeaweedFS.
- Credential revocation is immediate and scoped: deleting one identity leaves
  every other identity working (verified).
- The service-lifecycle hook stops naming a single provider in control-plane
  code.

### Negative Consequences

- **The per-binding isolation is an S3-protocol boundary, not a network one, and
  the SeaweedFS deployment shape currently defeats it in-cluster.**
  `weed server` runs master, volume, filer and S3 in one process and binds every
  component to the pod IP; only S3 (8333) authenticates. There is no
  per-component bind flag -- `weed server` exposes a single global `-ip.bind` --
  so the filer cannot be confined to loopback while S3 stays reachable.

  Verified from an unprivileged pod in another namespace with no credentials
  (2026-08-17): `GET /etc/iam/identity.json` on the filer returns **every S3
  credential including `nephos-admin`'s**, and the filer permits `PUT` (201),
  `GET`, and `DELETE` (204) against any bucket. Master (9333) and volume (8080)
  answer unauthenticated too.

  So bucket scoping constrains S3 clients and constrains nothing else. This
  exposure predates this ADR -- the workload always ran `weed server` this way --
  but this ADR is what puts real App data and per-binding credentials behind it,
  which turns a latent shape into a live one.

  **Resolved in this ADR's implementation**: the workload now emits a
  NetworkPolicy restricting ingress to the S3 port, so the boundary is created
  and destroyed with the Service. Re-verified on k3d (2026-08-17) after a full
  destroy and one-click reinstall: the same unauthenticated probes that
  previously returned credentials and `201`/`204` now fail to connect, master
  and volume are unreachable, S3 still answers `403` unauthenticated, and a
  signed client using the binding's own credentials still reads and writes its
  own bucket while being denied another.

  Ingress-only is deliberate. The components reach each other over loopback
  inside the pod, and provisioning runs through the Kubernetes exec API, which
  no pod-network policy governs — both were confirmed still working with the
  policy in place. The readiness probe targets the same S3 port the policy
  admits, so kubelet probing is unaffected.

  This narrows the exposure to the pod; it does not encrypt it. S3 remains plain
  HTTP in-cluster, so credentials and object data still cross the pod network in
  the clear. TLS is not addressed here.

- **A window exists in which SeaweedFS serves anonymous S3**: between the pod
  becoming ready and the lifecycle provisioner seeding the admin identity. It
  is narrow, the S3 port is ClusterIP-only, and Nephos reconciles immediately
  after deploy — but it is real, and it re-opens if the PVC is lost while
  nephos-api is down. The named hardening path is a seeding sidecar in the
  StatefulSet, which closes the window to pod-start and self-heals without the
  control plane. Deferred deliberately, not overlooked.
- Provisioning depends on `weed shell` inside the pod, so the SeaweedFS image
  and its CLI surface become part of the contract. A future image that changes
  `s3.configure` flags breaks provisioning; the runner protocol keeps the blast
  radius to one class.
- The admin credential now lives in the filer store as well as in the secrets
  backend. Rotating it requires re-seeding, not just changing config.

## Pros and Cons of the Options

### Filer-backed dynamic IAM, lifecycle-seeded admin

- Good, because it is the only shape in which app-scoped provisioning works at
  all.
- Good, because it reuses `ServiceLifecycleProvisioner`, already proven by
  OpenBao.
- Good, because identity state persists on the PVC, so restarts are safe.
- Bad, because a short anonymous window exists on first boot.

### Filer-backed dynamic IAM, sidecar-seeded admin

- Good, because it closes the anonymous window to roughly pod-start.
- Good, because it self-heals with the control plane down.
- Bad, because credential plumbing is duplicated between the sidecar and the
  provisioner, and the two must agree on the identity they write.
- Bad, because it adds a container to the workload for a window that is
  in-cluster only.

### Static config, shared admin key per binding

- Good, because it needs no runtime change and very little code.
- Bad, because every consumer holds a credential that opens every bucket, so
  bucket-per-binding provides naming, not isolation.
- Bad, because the credential can never be rotated for one consumer without
  breaking all of them, and fixing it later means rewriting the provisioner.

### Static config, bindings stay blocked

- Good, because there is no anonymous window at any point.
- Bad, because `object-storage/s3` remains undeliverable and
  `mythos-mail-ingress` stays uninstallable.
- Bad, because the catalog keeps advertising a default provider for a capability
  nothing can consume.

## Links

- Amends [Alpha backbone binding output contracts](20260630-alpha-backbone-binding-output-contracts.md)
- Constrained by [Registry-declared binding provisioning engines](20260718-registry-declared-binding-provisioning-engines.md)
- Constrained by [Binding provisioning entitlements](20260721-binding-provisioning-entitlements.md)
- Related [OpenBao secret backend](20260712-openbao-secret-backend.md) for the service-lifecycle precedent
