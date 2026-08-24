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
