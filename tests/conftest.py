from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.fixture
def upstream(tmp_path):
    def run(code: str, *arguments: object) -> str:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        process = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code), *(str(arg) for arg in arguments)],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode:
            raise AssertionError(
                f"upstream python-docx failed:\n{process.stdout}\n{process.stderr}"
            )
        return process.stdout.strip()

    return run
