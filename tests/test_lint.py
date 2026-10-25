import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

lint = helpers.sub("lint")
bundle = helpers.sub("bundle")
KNOWN = bundle.component_names()


def problems(src):
    return lint.check(src, KNOWN)


class GoodSources(unittest.TestCase):
    def test_every_shipped_example_is_clean(self):
        files = helpers.examples()
        self.assertGreaterEqual(len(files), 4)
        for f in files:
            with self.subTest(example=f.name):
                self.assertEqual(problems(f.read_text(encoding="utf-8")), [])

    def test_words_inside_strings_are_not_code(self):
        self.assertEqual(problems('root = Stack([a])\na = Text("use Dag( here, root = x, $var, @OpenUrl", "body")'), [])

    def test_object_literal_is_not_colon_syntax(self):
        self.assertEqual(problems('root = Stack([b])\nb = Button("Go", @ToAssistant("do it", {id: 4}))'), [])

    def test_a_statement_may_span_lines(self):
        self.assertEqual(problems('root = Stack([\n  a,\n  b\n])\na = Text("x")\nb = Text("y")'), [])

    def test_action_builtin_is_known(self):
        self.assertEqual(problems('root = Stack([b])\nb = Button("Go", Action([@ToAssistant("x")]))'), [])


class BadSources(unittest.TestCase):
    def one(self, src, needle):
        got = problems(src)
        self.assertTrue(any(needle in p for p in got), "expected %r in %r" % (needle, got))
        return got

    def test_empty(self):
        self.one("   \n", "empty")

    def test_missing_root(self):
        self.one('a = Text("x")', "No `root`")

    def test_truncated(self):
        self.one("root = Stack([a\n", "truncated")

    def test_unclosed_string(self):
        self.one('root = Stack([a])\na = Text("oops)', "truncated")

    def test_unknown_component_suggests_a_close_match(self):
        got = self.one('root = Stack([m])\nm = Metrik("a", "1")', "Unknown component `Metrik`")
        self.assertTrue(any("`Metric`" in p for p in got))

    def test_orphan_is_reported(self):
        self.one('root = Stack([a])\na = Text("x")\nlost = Text("y")', "`lost` is defined but not reachable")

    def test_undefined_reference(self):
        self.one('root = Stack([a, ghost])\na = Text("x")', "`ghost`, which is never defined")

    def test_colon_syntax(self):
        self.one('root = Stack([a], direction: "row")\na = Text("x")', "colon syntax")

    def test_dollar_variable(self):
        self.one('root = Stack([a])\na = Text($name)', "$variable")

    def test_open_url_is_refused(self):
        self.one('root = Stack([b])\nb = Button("Go", @OpenUrl("https://example.com"))', "@OpenUrl")

    def test_duplicate_definition(self):
        self.one('root = Stack([a])\na = Text("x")\na = Text("y")', "defined twice")

    def test_not_a_statement(self):
        self.one('root = Stack([a])\njust some words', "not a statement")


class Fences(unittest.TestCase):
    def test_fence_is_stripped(self):
        src = lint.strip_fences('```openui\nroot = Stack([a])\na = Text("x")\n```')
        self.assertEqual(problems(src), [])
        self.assertNotIn("```", src)

    def test_plain_source_is_untouched(self):
        self.assertEqual(lint.strip_fences('root = Stack([])').strip(), "root = Stack([])")


if __name__ == "__main__":
    unittest.main()
