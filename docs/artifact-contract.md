# The artifact contract: build once, promote by digest

cd-workflows seals *how* a change is planned, approved and applied. This
contract seals *what* moves: a deployable artifact is an OCI image in GitHub
Container Registry, named by content digest, built exactly once, and promoted
through environments without ever being rebuilt.

## Why ghcr

The platform already answers every operational question:

- **storage and bandwidth** for public and internal container images are
  currently free, with a month's notice contractually required before that
  changes;
- **access** is scoped by `GITHUB_TOKEN` per repository — a workflow can push
  only to its own namespace unless explicitly granted more;
- **provenance** attaches where the bytes live: build provenance and cosign
  signatures are ghcr artifacts beside the image.

## The rules

1. **Build once, on the fleet.** The image is built by
   ci-workflows' `docker-build.yml` (registry layer cache, digest output).
   The build's digest — `sha256:…` — is the artifact's identity from that
   moment on.
2. **Push by digest, tag as evidence.** Tags are pointers for humans;
   the digest is the contract. A tag may move only by re-pointing to an
   already-pushed digest, never by rebuilding.
3. **Promote the digest, not the source.** Moving an artifact from test to
   staging to production is re-tagging the same digest
   (`cd-promote.yml`), so every environment provably receives the same
   bytes. A rebuild "for production" is a different artifact and starts the
   pipeline over.
4. **Retention cleans what nothing names.** Untagged manifests — superseded
   build-cache entries and abandoned builds — are deleted by registry
   retention policy; promoted digests are always tagged and therefore kept.

## cd-promote.yml

The reusable promotion step: given `image`, `digest` and `to_tag`, it
verifies the digest exists in the registry, points the tag at it with
`docker buildx imagetools create`, and reads the tag back to prove it
resolves to exactly that digest. No checkout of the deployed source, no
build context, no way to introduce new bytes. `packages: write` on the
caller's token is the entire privilege surface.

```yaml
jobs:
  promote:
    uses: NDDev-OpenNetwork/cd-workflows/.github/workflows/cd-promote.yml@<pinned-sha>
    permissions:
      packages: write
    with:
      image: ghcr.io/nddev-opennetwork/example-service
      digest: sha256:0123…abcd
      to_tag: production
```

## First consumer

The almaty registry build-offload is the natural first consumer: its Stage 1
already builds on the fleet and pushes ghcr, so its images carry digests
from birth. Adopting the contract means its staging and production tags stop
being rebuild triggers and become `cd-promote.yml` calls on the digest
Stage 1 produced.
