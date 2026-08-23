# Contributing

Thanks for considering a contribution. This repository is a delivery control
surface: it carries the typed contracts and the reusable workflows that apply,
verify, resume and roll back a deployment. Everything below follows from that.

Please report security problems privately per [SECURITY.md](SECURITY.md)
rather than in a pull request.

## The one rule that surprises people

**A workflow here may not take an arbitrary command, runner or secret.** The
trust boundary is fixed in the file, not chosen by the caller:

- runner labels are literal, never `runs-on: ${{ ... }}`;
- `pull_request_target` is refused outright;
- the apply, resume and rollback surfaces require the `cd-apply` environment
  and an out-of-band self-hosted label, so a deployment cannot be executed by
  the fleet it deploys;
- verify runs on its own label, independent of the managed fleet.

`scripts/validate_module.sh` enforces each of these. If a change needs one of
them relaxed, that is a design discussion before it is a pull request.

## Pinned actions

Third-party actions are pinned by full SHA with a comment naming the release,
and both must match `catalog/actions.yml`. Bump the catalog and the pins in one
change; the module gate refuses a comment that disagrees with the catalog, a
SHA that does, a pin with no comment, an undeclared action, and a catalog entry
nothing uses.

## Before you open a pull request

```
bash scripts/validate_module.sh
```

It runs the schema validation, the unit tests, the byte-compile, the ruleset
contract, the actionlint label contract, the action pin contract, the raw
secret sweep and `git diff --check`. The branch requires the `test` context, so
a green local run is the same gate.

## Commits

The only valid author is `rldyourmnd <danil@nddev.it.com>`. Conventional
Commits; the subject says what changed, the body says why it was wrong before.
