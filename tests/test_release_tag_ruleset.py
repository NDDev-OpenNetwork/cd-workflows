"""The tag selector uses GitHub fnmatch patterns, not regular expressions."""
import fnmatch
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def matches(pattern, ref):
    # GitHub uses FNM_PATHNAME: a wildcard cannot consume a slash. These
    # patterns use only ordinary character classes and stars, with no extglob.
    patterns, parts = pattern.split("/"), ref.split("/")
    return len(patterns) == len(parts) and all(fnmatch.fnmatchcase(part, glob) for glob, part in zip(patterns, parts))


class ReleaseTagProtectionTests(unittest.TestCase):
    def test_actual_release_refs_receive_immutable_tag_protection(self):
        ruleset = json.loads((ROOT / ".github/rulesets/tag-semver.json").read_text())
        patterns = ruleset["conditions"]["ref_name"]["include"]
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(ruleset["enforcement"], "active")
        self.assertEqual(ruleset["bypass_actors"], [])
        self.assertEqual({rule["type"] for rule in ruleset["rules"]}, {"deletion", "non_fast_forward", "update", "required_signatures"})
        for ref in ("refs/tags/0.1.2", "refs/tags/12.34.567", "refs/tags/1.2.3-rc.1"):
            with self.subTest(ref=ref):
                self.assertTrue(any(matches(pattern, ref) for pattern in patterns))
        for ref in ("refs/heads/0.1.2", "refs/tags/main", "refs/tags/preview/0.1.2", "refs/tags/v1"):
            with self.subTest(ref=ref):
                self.assertFalse(any(matches(pattern, ref) for pattern in patterns))

class ReleaseChangelogMatchTests(unittest.TestCase):
    def test_resolve_matches_any_dated_heading_for_the_tag_version(self):
        """A frozen 0.1.2 date in the grep made every later tag fail resolve."""
        source = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn(r'grep -q "^## \[$version\]" CHANGELOG.md', source)
        self.assertNotIn("2026-08-26", source.split("Validate exact release identity", 1)[1].split("git fetch", 1)[0])

