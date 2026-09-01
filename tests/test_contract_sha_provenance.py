import pathlib
import subprocess
import tempfile
import unittest


class ContractSHAProvenanceTests(unittest.TestCase):
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
        if content.count("needs: authorize-contract") < content.count("ref: ${{ inputs.contract_sha }}"):
            raise AssertionError("a contract checkout skipped authorization")

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
