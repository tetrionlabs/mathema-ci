# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""A changed function is one whose source on the head side, from its
first decorator to its last line, overlaps a line the diff adds or
changes, or sits at a deletion. A function the base did not define is
new, a renamed or moved one included, since its key is new; a deleted
function is not changed, there being nothing left to gate."""
from __future__ import annotations

import subprocess
import textwrap

from mathema_ci.diffmap import changed_functions, function_spans, module_of, parse_diff

BASE = textwrap.dedent('''\
    """Calc."""


    def double(x):
        """Return twice x."""
        return x * 2


    def half(x):
        """Return half of x."""
        return x / 2


    class Box:
        """A box."""

        def get(self, x):
            """Return x."""
            return x

        def put(self, x):
            """Store x."""
            self.x = x
    ''')


def _diff(tmp_path, before: dict, after: dict) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "config", "user.email", "t@example.invalid"], check=True)
    subprocess.run([*git, "config", "user.name", "t"], check=True)
    for path, text in before.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    for path in before:
        if path not in after:
            subprocess.run([*git, "rm", "-q", path], check=True)
    for path, text in after.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "head"], check=True)
    return subprocess.run([*git, "diff", "--unified=0", "--no-color", "-M", "HEAD^", "HEAD"],
                          check=True, capture_output=True, text=True).stdout


def _changed(tmp_path, before, after):
    changes = parse_diff(_diff(tmp_path, before, after))
    return changed_functions(changes, after, before)


def test_the_module_comes_from_the_path():
    assert module_of("calc.py") == "calc"
    assert module_of("src/pkg/calc.py") == "pkg.calc"
    assert module_of("src/pkg/__init__.py") == "pkg"
    assert module_of("tests/test_calc.py") is None
    assert module_of("README.md") is None


def test_spans_run_from_the_first_decorator_to_the_last_line():
    source = textwrap.dedent('''\
        import functools


        @functools.wraps(print)
        @staticmethod
        def f(x):
            return x


        class C:
            @property
            def p(self):
                return 1

            def m(self):
                def inner():
                    return 2
                return inner()

            class Nested:
                def deep(self):
                    return 3


        async def g(x):
            return x

        h = lambda x: x
        ''')
    spans = function_spans(source, "m")
    assert spans["m.f"] == (4, 7)
    assert spans["m.C.p"] == (11, 13)
    assert spans["m.C.m"] == (15, 18)
    assert spans["m.g"] == (25, 26)
    assert spans["m.h"] == (28, 28)
    assert "m.C.Nested.deep" not in spans and "m.inner" not in spans


def test_an_edited_body_marks_only_its_function(tmp_path):
    after = {"calc.py": BASE.replace("return x * 2", "return x * 3")}
    assert _changed(tmp_path, {"calc.py": BASE}, after) == {"calc.double": "edited"}


def test_a_method_edit_is_keyed_by_its_class(tmp_path):
    after = {"calc.py": BASE.replace("self.x = x", "self.x = x + 0")}
    assert _changed(tmp_path, {"calc.py": BASE}, after) == {"calc.Box.put": "edited"}


def test_a_new_function_is_new(tmp_path):
    after = {"calc.py": BASE + '\n\ndef triple(x):\n    """Return thrice x."""\n    return x * 3\n'}
    assert _changed(tmp_path, {"calc.py": BASE}, after) == {"calc.triple": "new"}


def test_a_deleted_line_inside_a_function_changes_it(tmp_path):
    after = {"calc.py": BASE.replace('        """Store x."""\n', "")}
    assert _changed(tmp_path, {"calc.py": BASE}, after) == {"calc.Box.put": "edited"}


def test_a_deleted_function_is_not_changed(tmp_path):
    start = BASE.index("\n\ndef half")
    end = BASE.index("\n\nclass Box")
    after = {"calc.py": BASE[:start] + BASE[end:]}
    changed = _changed(tmp_path, {"calc.py": BASE}, after)
    assert "calc.half" not in changed
    assert set(changed) <= {"calc.double", "calc.Box.get"}


def test_a_renamed_module_makes_its_functions_new(tmp_path):
    after = {"calc2.py": BASE.replace("return x * 2", "return x * 3")}
    changed = _changed(tmp_path, {"calc.py": BASE}, after)
    assert changed == {"calc2.double": "new"}


def test_tests_and_other_files_are_left_out(tmp_path):
    before = {"calc.py": BASE, "tests/test_calc.py": "def test_a():\n    assert 1\n",
              "README.md": "x\n"}
    after = {"calc.py": BASE, "tests/test_calc.py": "def test_a():\n    assert 2\n",
             "README.md": "y\n"}
    assert _changed(tmp_path, before, after) == {}


def test_a_decorator_line_changes_its_function():
    diff = textwrap.dedent('''\
        diff --git a/m.py b/m.py
        --- a/m.py
        +++ b/m.py
        @@ -1,0 +2 @@
        +@decorated
        ''')
    head = {"m.py": "\n@decorated\ndef f():\n    return 1\n"}
    base = {"m.py": "\ndef f():\n    return 1\n"}
    assert changed_functions(parse_diff(diff), head, base) == {"m.f": "edited"}
