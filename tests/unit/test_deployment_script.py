from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = PROJECT_ROOT / "scripts" / "deploy.sh"
DEPLOY_COMMANDS = [
    ["compose", "build", "bot", "worker"],
    ["compose", "up", "-d", "--wait", "--wait-timeout", "120", "postgres", "redis"],
    ["compose", "run", "--rm", "--no-deps", "bot", "alembic", "upgrade", "head"],
    ["compose", "up", "-d", "bot", "worker"],
    ["compose", "ps"],
]


@pytest.mark.parametrize("fail_at", [None, 1, 2, 3])
def test_deployment_stops_on_failure_before_starting_application(
    tmp_path: Path, fail_at: int | None
) -> None:
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "log = Path(os.environ['DEPLOY_TEST_LOG'])\n"
        "record = {'args': sys.argv[1:], 'cwd': os.getcwd()}\n"
        "with log.open('a') as handle:\n"
        "    handle.write(json.dumps(record) + '\\n')\n"
        "attempt = len(log.read_text().splitlines())\n"
        "sys.exit(42 if attempt == int(os.environ['DEPLOY_TEST_FAIL_AT']) else 0)\n"
    )
    docker.chmod(0o755)
    make = tmp_path / "make"
    make.write_text("#!/bin/sh\nexit 99\n")
    make.chmod(0o755)
    log = tmp_path / "docker-calls.jsonl"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.defpath,
        "DEPLOY_TEST_LOG": str(log),
        "DEPLOY_TEST_FAIL_AT": str(fail_at or 0),
    }
    # Invoking from elsewhere must work even when make is unavailable.
    result = subprocess.run(
        ["/bin/sh", str(DEPLOY_SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (42 if fail_at else 0), result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    expected = DEPLOY_COMMANDS[:fail_at] if fail_at else DEPLOY_COMMANDS
    assert [call["args"] for call in calls] == expected
    assert all(call["cwd"] == str(PROJECT_ROOT) for call in calls)
