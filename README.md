# cd-workflows

Public, generic contracts for agent-driven continuous delivery.

This repository owns immutable deployment plans, approval binding, state
transitions, verification evidence, retry/resume and exact rollback semantics.
It contains no environment topology or credentials. Private callers choose
their reviewed executor, environment, inventory and secret references.

The v1 lifecycle exposes typed plan, apply, verify, evidence, resume and exact
rollback entrypoints. Mutation entrypoints invoke only the fixed
`nddev-cd-adapter` protocol on an independently managed executor. The adapter
receives the sealed plan and cannot receive a workflow-supplied command, host,
runner label, target selector or secret name.

`cd-plan.yml` exposes two fixed execution surfaces: GitHub-hosted, or a generic
out-of-band runner carrying `cd-plan-out-of-band`. Callers cannot supply runner
labels or commands. A sealed plan artifact is transport evidence only; callers
must persist durable evidence outside Actions retention.

`cd-apply.yml`, `cd-resume.yml` and `cd-rollback.yml` run only on
`cd-apply-out-of-band`, behind the fixed `cd-apply` GitHub environment and with
non-cancelling per-deployment serialization. `cd-verify.yml` uses the separate
`cd-verify-out-of-band` surface. Every adapter result must validate as an exact
plan-bound state transition and content-addressed evidence record before the
workflow can succeed. `cd-evidence.yml` provides a hosted, read-only verifier.

## Trust boundaries

- PR validation: schemas and fixtures only; no credentials or side effects.
- Plan: read-only exact source and inventory evidence.
- Apply/rollback: trusted ref, protected approval, serialized environment and a
  typed adapter. Arbitrary shell, target and runner inputs are forbidden.
- Evidence: content-addressed state and verification results; Actions artifacts
  are not the sole durable record.

## Commands

```bash
python3 scripts/cd_contract.py validate-schema
python3 scripts/cd_contract.py seal examples/plan.draft.json /tmp/plan.json
python3 scripts/cd_contract.py validate-plan /tmp/plan.json
python3 -m unittest discover -s tests -v
```
