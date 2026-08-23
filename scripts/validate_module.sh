#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "${repo_root}"

python3 scripts/cd_contract.py validate-schema
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/cd_contract.py tests/test_cd_contract.py

python3 - <<'PY'
import json
from pathlib import Path

anchor = Path(".gds/repository.yaml").read_text(encoding="utf-8")
for line in (
    '  owner: "NDDev-OpenNetwork"',
    '  name: "cd-workflows"',
    '  visibility_contract: "public"',
    '  data_classification: "public"',
):
    if line not in anchor:
        raise SystemExit(f"public module anchor lacks {line!r}")
ruleset = json.loads(Path(".github/rulesets/branch-main.json").read_text())
checks = []
for rule in ruleset.get("rules", []):
    if rule.get("type") == "required_status_checks":
        checks = [row["context"] for row in rule["parameters"]["required_status_checks"]]
if checks != ["test"] or ruleset.get("bypass_actors") != []:
    raise SystemExit("public ruleset does not require the exact test context without bypass")
workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
if "runs-on: ubuntu-latest" not in workflow or "pull_request_target" in workflow or "secrets:" in workflow:
    raise SystemExit("public CI runner or trust boundary drifted")
plan_workflow = Path(".github/workflows/cd-plan.yml").read_text(encoding="utf-8")
for required in (
    "runs-on: ubuntu-latest",
    "runs-on: [self-hosted, cd-plan-out-of-band]",
    "inputs.execution_surface == 'hosted'",
    "inputs.execution_surface == 'out-of-band'",
    "repository: NDDev-OpenNetwork/cd-workflows",
    "ref: ${{ inputs.contract_sha }}",
    "retention-days: 30",
):
    if required not in plan_workflow:
        raise SystemExit(f"cd-plan workflow lacks {required!r}")
for forbidden in ("pull_request_target", "secrets:", "runs-on: ${{", "shell_command", "runner_label"):
    if forbidden in plan_workflow:
        raise SystemExit(f"cd-plan workflow exposes forbidden surface {forbidden!r}")
action = Path(".github/actions/contract/action.yml").read_text(encoding="utf-8")
for command in ("seal)", "validate-plan)", "transition)"):
    if command not in action:
        raise SystemExit(f"contract action lacks closed command {command!r}")
if "eval " in action or "bash -c" in action:
    raise SystemExit("contract action permits free-form command execution")
PY

python3 - <<'PY'
from pathlib import Path
import re

for path in Path(".").rglob("*"):
    if not path.is_file() or ".git" in path.parts:
        continue
    content = path.read_bytes()
    if b"-----BEGIN " + b"PRIVATE KEY-----" in content:
        raise SystemExit(f"raw private key marker in {path}")
    if re.search(b"gh" + b"[pousr]_[A-Za-z0-9]{30,}", content):
        raise SystemExit(f"raw GitHub token marker in {path}")
PY

git diff --check
