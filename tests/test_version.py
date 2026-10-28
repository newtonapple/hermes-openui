"""The version is written in three places. These tests keep them in step so a release cannot ship with a stale one."""
import re
import unittest

from helpers import ROOT

SEMVER = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?"


def field(path, key):
    """Value of a top-level `key: value` line in a file with a simple YAML header (no PyYAML needed)."""
    m = re.search(r"^%s:\s*[\"']?([^\"'\n]+?)[\"']?\s*$" % re.escape(key), (ROOT / path).read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def changelog():
    return (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


class Version(unittest.TestCase):
    def test_plugin_version_is_semver(self):
        self.assertRegex(field("plugin.yaml", "version") or "", "^%s$" % SEMVER)

    def test_every_bundled_skill_has_the_same_version(self):
        skills = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(skills), 2, "update this test when a skill is added or removed")
        for path in skills:
            with self.subTest(skill=path):
                self.assertEqual(field(path, "version"), field("plugin.yaml", "version"))

    def test_changelog_has_an_unreleased_section(self):
        self.assertRegex(changelog(), r"(?m)^## \[Unreleased\]\s*$")

    def test_newest_changelog_release_is_the_plugin_version(self):
        releases = re.findall(r"(?m)^## \[(%s)\] - (\d{4}-\d{2}-\d{2})\s*$" % SEMVER, changelog())
        self.assertTrue(releases, "CHANGELOG.md has no `## [x.y.z] - YYYY-MM-DD` heading")
        self.assertEqual(releases[0][0], field("plugin.yaml", "version"), "bump plugin.yaml and the changelog together")

    def test_every_changelog_release_links_to_its_tag(self):
        text = changelog()
        for version in re.findall(r"(?m)^## \[(%s)\]" % SEMVER, text):
            self.assertRegex(text, r"(?m)^\[%s\]: \S+/v%s\s*$" % (re.escape(version), re.escape(version)))

    def test_requires_hermes_is_a_plain_floor(self):
        # Hermes reads this field when it loads the plugin; a typo can stop the plugin from loading at all.
        self.assertRegex(field("plugin.yaml", "requires_hermes") or "", r"^>=\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
