# cd-workflows

Public, generic contracts for agent-driven continuous delivery.

This repository owns immutable deployment plans, approval binding, state
transitions, verification evidence, retry/resume and exact rollback semantics.
It contains no environment topology or credentials. Private callers choose
their reviewed executor, environment, inventory and secret references.

The initial v1 contract deliberately performs no external mutation. It seals
and validates plans and proves state-machine behavior before mutation adapters
are introduced.

`cd-plan.yml` exposes two fixed execution surfaces: GitHub-hosted, or a generic
out-of-band runner carrying `cd-plan-out-of-band`. Callers cannot supply runner
labels or commands. A sealed plan artifact is transport evidence only; callers
must persist durable evidence outside Actions retention.

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
