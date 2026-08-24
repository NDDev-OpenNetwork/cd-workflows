#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "${repo_root}"

python3 scripts/cd_contract.py validate-schema
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/cd_contract.py tests/test_cd_contract.py tests/test_contract_sha_provenance.py

python3 - <<'PY'
import json
from pathlib import Path
import re

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

lifecycle_action = Path(".github/actions/lifecycle/action.yml").read_text(encoding="utf-8")
for required in ("nddev-cd-adapter", "validate-approval", "validate-evidence", "command -v nddev-cd-adapter"):
    if required not in lifecycle_action:
        raise SystemExit(f"lifecycle action lacks {required!r}")
for forbidden in ("eval ", "bash -c", "ssh ", "sudo ", "curl "):
    if forbidden in lifecycle_action:
        raise SystemExit(f"lifecycle action exposes forbidden execution surface {forbidden!r}")

for name in ("apply", "verify", "resume", "rollback", "evidence"):
    content = Path(f".github/workflows/cd-{name}.yml").read_text(encoding="utf-8")
    if "pull_request_target" in content or "secrets:" in content or "runs-on: ${{" in content:
        raise SystemExit(f"cd-{name} workflow violates the fixed trust boundary")
    if name in {"apply", "resume", "rollback"}:
        for required in ("runs-on: [self-hosted, cd-apply-out-of-band]", "environment: cd-apply", "cancel-in-progress: false", "id-token: write"):
            if required not in content:
                raise SystemExit(f"cd-{name} workflow lacks {required!r}")
    if name == "apply":
        for required in (
            "authorize-contract:",
            "runs-on: ubuntu-latest",
            "permissions: {}",
            "fetch-depth: 0",
            'git -C authority fetch --no-tags --depth=1 origin "$CONTRACT_SHA"',
            'git -C authority merge-base --is-ancestor "$CONTRACT_SHA" refs/remotes/origin/main',
            "needs: authorize-contract",
            '[[ "$CONTRACT_SHA" == "$AUTHORIZED_CONTRACT_SHA" ]]',
        ):
            if required not in content:
                raise SystemExit(f"cd-apply workflow lacks provenance control {required!r}")
        if content.index("authorize-contract:") > content.index("  apply:"):
            raise SystemExit("cd-apply privileged job appears before contract authorization")
    if name == "verify" and "runs-on: [self-hosted, cd-verify-out-of-band]" not in content:
        raise SystemExit("cd-verify workflow is not independent of the managed fleet")

declared_labels = {
    line.removeprefix("    - ").strip()
    for line in Path(".github/actionlint.yaml").read_text(encoding="utf-8").splitlines()
    if line.startswith("    - ")
}
used_labels = set()
for path in Path(".github/workflows").glob("*.yml"):
    used_labels.update(re.findall(r"runs-on: \[self-hosted, ([a-z0-9-]+)\]", path.read_text(encoding="utf-8")))
if declared_labels != used_labels:
    raise SystemExit(f"actionlint labels differ from workflow contract: declared={sorted(declared_labels)} used={sorted(used_labels)}")
PY

python3 - <<'PYCHECK'
# Every pinned action must match catalog/actions.yml exactly: the SHA and the
# release its comment names. A comment nobody compares is a comment that
# drifts, and this one did -- fifteen checkout pins said v5.0.0 while the SHA
# was v7.0.1, two majors apart, on the module that deploys the fleet.
from pathlib import Path
import re

# Read strictly, by column. The first version of this stripped every line and
# looked for `- name:` anywhere, which ignores indentation entirely -- so a
# catalog that no YAML parser will load still "read fine" and the whole check
# below passed on it. That was found by mis-indenting an entry by two spaces:
# `yaml.safe_load` raised `expected <block end>`, and this script printed OK.
# The module ships no dependencies, so the answer is not PyYAML; it is refusing
# any shape other than the one shape this file is allowed to have.
registry = {}
current = {}
catalog = Path("catalog/actions.yml")
in_actions = False
for number, line in enumerate(catalog.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    if not in_actions:
        in_actions = line == "actions:"
        continue
    if line.startswith("  - name: "):
        if current:
            registry[current["name"]] = current
        current = {"name": line[len("  - name: "):].strip().strip('"')}
    elif line.startswith("    sha: ") and current:
        current["sha"] = line[len("    sha: "):].strip().strip('"')
    elif line.startswith("    version: ") and current:
        current["version"] = line[len("    version: "):].strip().strip('"')
    else:
        raise SystemExit(
            f"{catalog}:{number}: catalog entries are exactly "
            f'`  - name: X` / `    sha: \"…\"` / `    version: \"…\"`; got {line!r}'
        )
if current:
    registry[current["name"]] = current
if not registry:
    raise SystemExit(f"{catalog}: declares no actions; refusing to pass a check with nothing to check")
for name, entry in sorted(registry.items()):
    missing = [k for k in ("sha", "version") if k not in entry]
    if missing:
        raise SystemExit(f"{catalog}: {name} is missing {', '.join(missing)}")
    if len(entry["sha"]) != 40:
        raise SystemExit(f"{catalog}: {name} records a {len(entry['sha'])}-character SHA, expected 40")

pattern = re.compile(r"uses:\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@([0-9a-f]{40})\s*#\s*(\S+)")
seen = set()
for path in sorted(Path(".github").rglob("*.yml")):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "uses:" not in line or "@" not in line:
            continue
        if re.search(r"uses:\s+\./", line):
            continue
        match = pattern.search(line)
        if match is None:
            raise SystemExit(f"{path}:{number}: pinned action needs a 40-character SHA and a version comment")
        name, sha, version = match.groups()
        entry = registry.get(name)
        if entry is None:
            raise SystemExit(f"{path}:{number}: {name} is not declared in catalog/actions.yml")
        if sha != entry["sha"]:
            raise SystemExit(f"{path}:{number}: {name} pins {sha[:12]} but the catalog records {entry['sha'][:12]}")
        if version != entry["version"]:
            raise SystemExit(f"{path}:{number}: {name} comment says {version} but the catalog records {entry['version']} for this SHA")
        seen.add(name)

unused = sorted(set(registry) - seen)
if unused:
    raise SystemExit(f"catalog/actions.yml declares actions nothing uses: {unused}")
PYCHECK

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
