# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""The plugin runs inside the measured project's test process, under
coverage. Importing mathema there would load sympy into that process
and put mathema's own lines into the report, so the plugin package must
import nothing from mathema, directly or through anything it imports."""
from __future__ import annotations

import subprocess
import sys


def test_importing_the_plugin_leaves_mathema_unloaded():
    code = (
        "import sys\n"
        "import mathema_pytest, mathema_pytest.plugin\n"
        "loaded = sorted(m for m in sys.modules "
        "if m == 'mathema' or m.startswith('mathema.') or m == 'sympy' "
        "or m.startswith('sympy.'))\n"
        "print(loaded)\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run([sys.executable, "-c", code],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
