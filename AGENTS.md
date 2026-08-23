# Agent contract

Implement generic, public continuous-delivery contracts. Never add private
organizations, repositories, hosts, networks, credentials, environment names,
deployment evidence, or runner labels.

CD is a separate trust boundary from PR-facing CI. Untrusted events may
validate schemas and plans but can never reach apply, resume, rollback,
deployment credentials, arbitrary commands, runner selection, or target
selection.

Plans use exact immutable identities, deterministic digests, bounded operations
and an explicit previous state. Every state transition is validated and
journal-ready. Keep adapters declarative and narrowly typed; do not accept
free-form shell fragments or implicit `secrets: inherit`.

Run `python3 -m unittest discover -s tests -v` and
`python3 scripts/cd_contract.py validate-schema` after changes.
