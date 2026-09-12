import pathlib
import os
import re
import subprocess
import tempfile
import textwrap
import unittest


class ContractSHAProvenanceTests(unittest.TestCase):
    def test_actual_authorization_scripts_accept_reviewed_commit_and_refuse_foreign_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            repository = root / "origin"
            repository.mkdir()
            self.git(repository, "init", "-b", "main")
            self.git(repository, "config", "user.name", "Example")
            self.git(repository, "config", "user.email", "example@example.invalid")
            reviewed = self.commit(repository, "reviewed")
            self.git(repository, "checkout", "-b", "unreviewed")
            foreign = self.commit(repository, "foreign")
            self.git(repository, "checkout", "main")
            self.git(root, "clone", str(repository), "authority")
            for path in pathlib.Path(".github/workflows").glob("cd-*.yml"):
                content = path.read_text()
                if "Authorize reviewed contract ancestry" not in content:
                    continue
                step = content.split("Authorize reviewed contract ancestry", 1)[1]
                # Read the full YAML block by its indentation, not just its first line.
                lines = step.split("        run: |\n", 1)[1].splitlines()
                block = []
                for line in lines:
                    if line.strip() and not line.startswith("          "):
                        break
                    block.append(line)
                script = textwrap.dedent("\n".join(block))
                scenarios = [(reviewed, True, {}), (foreign, False, {}), ("not-an-oid", False, {})]
                scenarios.extend((reviewed, False, overrides) for overrides in (
                    {"CALLER_PRIVATE": "false"}, {"CALLER_EVENT": "pull_request"},
                    {"CALLER_EVENT": "pull_request_target"}, {"CALLER_EVENT": "workflow_run"},
                    {"CALLER_REF": "refs/heads/unreviewed"}, {"CALLER_DEFAULT_BRANCH": ""},
                    {"CALLER_REF": "refs/tags/v1.0.0"},
                ))
                scenarios.extend((reviewed, True, {"CALLER_EVENT": event})
                                 for event in ("workflow_dispatch", "schedule"))
                scenarios.append((reviewed, True, {"REQUIRES_PRIVATE_RUNNER": "false",
                                                  "CALLER_PRIVATE": "false", "CALLER_EVENT": "pull_request"}))
                for sha, succeeds, overrides in scenarios:
                    with self.subTest(workflow=path.name, sha=sha):
                        output = root / "output"
                        output.write_text("")
                        env = {**os.environ, "CONTRACT_SHA": sha, "GITHUB_OUTPUT": str(output),
                               "CALLER_PRIVATE": "true", "CALLER_EVENT": "push",
                               "CALLER_REF": "refs/heads/main", "CALLER_DEFAULT_BRANCH": "main",
                               "REQUIRES_PRIVATE_RUNNER": "true"}
                        env.pop("AUTHORIZED_CONTRACT_SHA", None)
                        env.update(overrides)
                        result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                                cwd=root, env=env, capture_output=True, text=True)
                        self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                        self.assertEqual(f"contract_sha={sha}\n" in output.read_text(), succeeds)

    def test_only_reviewed_main_ancestry_is_authorized(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = pathlib.Path(directory)
            self.git(repository, "init", "-b", "main")
            self.git(repository, "config", "user.name", "Example")
            self.git(repository, "config", "user.email", "example@example.invalid")
            reviewed_parent = self.commit(repository, "reviewed-parent")
            reviewed_head = self.commit(repository, "reviewed-head")
            self.git(repository, "checkout", "-b", "fork-like", reviewed_parent)
            unreviewed = self.commit(repository, "unreviewed")

            self.assertTrue(self.is_ancestor(repository, reviewed_parent, reviewed_head))
            self.assertTrue(self.is_ancestor(repository, reviewed_head, reviewed_head))
            self.assertFalse(self.is_ancestor(repository, unreviewed, reviewed_head))

    @staticmethod
    def git(repository: pathlib.Path, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repository), *arguments], text=True, stderr=subprocess.DEVNULL
        ).strip()

    def commit(self, repository: pathlib.Path, content: str) -> str:
        (repository / "contract.txt").write_text(content, encoding="utf-8")
        self.git(repository, "add", "contract.txt")
        self.git(repository, "commit", "-m", content)
        return self.git(repository, "rev-parse", "HEAD")

    @staticmethod
    def is_ancestor(repository: pathlib.Path, candidate: str, reviewed_head: str) -> bool:
        return subprocess.run(
            ["git", "-C", str(repository), "merge-base", "--is-ancestor", candidate, reviewed_head],
            check=False,
        ).returncode == 0


if __name__ == "__main__":
    unittest.main()


class WorkflowProvenanceStructureTests(unittest.TestCase):
    """Every entrypoint that accepts a contract_sha must authorize it on a
    hosted job before any job checks that commit out, and the consuming job
    must re-compare the authorized value. cd-apply carried this alone once;
    the others executed a caller-supplied commit on privileged runners."""

    WORKFLOWS = {
        "cd-apply.yml": "  apply:",
        "cd-verify.yml": "  verify:",
        "cd-resume.yml": "  resume:",
        "cd-rollback.yml": "  rollback:",
        "cd-evidence.yml": "  validate:",
        "cd-plan.yml": "  hosted:",
    }

    @staticmethod
    def assert_provenance(content: str, first_job: str) -> None:
        for required in (
            "authorize-contract:",
            'git -C authority merge-base --is-ancestor "$CONTRACT_SHA" refs/remotes/origin/main',
            "needs: authorize-contract",
            '[[ "$CONTRACT_SHA" == "$AUTHORIZED_CONTRACT_SHA" ]]',
        ):
            if required not in content:
                raise AssertionError(f"missing provenance control {required!r}")
        if content.index("authorize-contract:") > content.index(first_job):
            raise AssertionError("privileged job appears before contract authorization")
        if content.count("needs: authorize-contract") < content.count("ref: ${{ needs.authorize-contract.outputs.contract_sha }}"):
            raise AssertionError("a contract checkout skipped authorization")
        if 'ref: ${{ inputs.contract_sha }}' in content or 'ref: "${{ inputs.contract_sha }}"' in content:
            raise AssertionError("contract checkout bypasses the authorized output")
        for job in re.split(r"\n  (?=[a-zA-Z0-9_-]+:\n)", content):
            if "runs-on: [self-hosted," in job:
                if "needs.authorize-contract.outputs.private_runner_allowed == 'true'" not in job:
                    raise AssertionError("private runner is not guarded by caller authorization")

    def test_every_entrypoint_authorizes_the_contract(self):
        for name, first_job in self.WORKFLOWS.items():
            content = pathlib.Path(".github/workflows", name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assert_provenance(content, first_job)

    def test_checker_rejects_a_job_that_skips_authorization(self):
        content = pathlib.Path(".github/workflows/cd-resume.yml").read_text(encoding="utf-8")
        stripped = content.replace("    needs: authorize-contract\n", "", 1)
        with self.assertRaises(AssertionError):
            self.assert_provenance(stripped, "  resume:")

    def test_checker_rejects_a_missing_comparison(self):
        content = pathlib.Path(".github/workflows/cd-rollback.yml").read_text(encoding="utf-8")
        stripped = content.replace('          [[ "$CONTRACT_SHA" == "$AUTHORIZED_CONTRACT_SHA" ]]\n', "", 1)
        with self.assertRaises(AssertionError):
            self.assert_provenance(stripped, "  rollback:")
