# SPDX-License-Identifier: GPL-3.0-or-later
"""Test setup.

Tests run with the ``bpy`` module from PyPI (Blender as a Python module), which
matches the targeted Blender version:

    python -m venv .venv && .venv/bin/pip install bpy==5.2.2 pytest
    .venv/bin/python -m pytest

Blender's user folders are redirected to a temporary directory so that
installing the extension never touches a real Blender configuration.
"""

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
_USER_DIR = tempfile.mkdtemp(prefix="gp2m_blender_user_")
os.environ["BLENDER_USER_RESOURCES"] = _USER_DIR

for folder in (ROOT, ROOT / "tests"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
