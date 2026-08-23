# Changelog

All notable changes are documented here. The project follows Semantic
Versioning.

## [Unreleased]

### Fixed

- Every `actions/checkout` pin carried the comment `# v5.0.0` while its SHA was
  `v7.0.1` — two majors apart, in the module that deploys the fleet. Fifteen
  lines, wrong from the day they were written, because nothing compared the
  comment with the SHA.

### Added

- `catalog/actions.yml` records each pinned action's SHA and the release that
  SHA is, and `scripts/validate_module.sh` holds every `uses:` in `.github/` to
  it. A bump now changes one reviewed place instead of fifteen unreviewed
  comments, and five ways of getting it wrong fail the module gate: a comment
  that disagrees with the catalog, a SHA that does, a pin with no comment, an
  action the catalog does not declare, and a catalog entry nothing uses.
- `CONTRIBUTING.md`, matching the other public modules.

## [0.1.0] - 2026-08-23

### Added

- Immutable delivery contracts: typed plan, approval, deployment state and
  evidence schemas with digest binding.
- Closed reusable execution surfaces for plan, apply, verify, resume, rollback
  and evidence, on fixed runner labels with no arbitrary shell, runner or
  secret inputs.
- Runtime rejection of a plan that is stale or altered at execution time.
