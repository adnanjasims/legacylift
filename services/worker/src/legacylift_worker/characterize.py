"""Generate characterization tests from sandbox probes of original code."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legacylift_sandbox import (
    PY2_IMAGE,
    DockerBackend,
    SandboxLimits,
    SandboxRequest,
)
from legacylift_worker.errors import PipelineError
from legacylift_worker.platformutil import py2_docker_platform
from legacylift_worker.scripts import PROBE_PY, RUN_TESTS_PY

SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BUILTIN_EXC = {
    "Exception",
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "ZeroDivisionError",
    "OverflowError",
    "RuntimeError",
    "AttributeError",
}


@dataclass(frozen=True)
class SuiteRun:
    records: list[dict[str, Any]]
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def generate_and_keep_tests(
    original: Path,
    backend: DockerBackend,
    limits: SandboxLimits,
) -> SuiteRun:
    """Probe original modules, write unittest files, keep tests that pass 3 times."""
    (original / "_probe.py").write_text(PROBE_PY, encoding="utf-8")
    (original / "run_tests.py").write_text(RUN_TESTS_PY, encoding="utf-8")
    probe = _run(
        original,
        backend,
        limits,
        ["python", "_probe.py"],
        PY2_IMAGE,
    )
    if probe.timed_out or probe.exit_code != 0:
        raise PipelineError(
            "characterization probe failed in the sandbox: "
            f"exit={probe.exit_code} timeout={probe.timed_out}\n{probe.stderr}"
        )
    try:
        payload = json.loads(probe.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise PipelineError(f"probe did not print JSON: {probe.stdout!r}") from exc
    observations = payload.get("observations", [])
    if not isinstance(observations, list):
        raise PipelineError("probe JSON observations must be a list")
    rows = _valid_rows(observations)
    _write_tests(original, rows)
    kept_ids = _keep_stable_tests(original, backend, limits)
    kept_rows = [
        row for row in rows if any(item.endswith(row["method"]) for item in kept_ids)
    ]
    _write_tests(original, kept_rows)
    return run_unittest(original, backend, limits, PY2_IMAGE)


def _run(
    workspace: Path,
    backend: DockerBackend,
    limits: SandboxLimits,
    argv: list[str],
    image: str,
) -> SuiteRun:
    result = backend.run(
        SandboxRequest(
            image=image,
            workspace=workspace,
            argv=argv,
            limits=limits,
            platform=py2_docker_platform() if image == PY2_IMAGE else None,
        )
    )
    records: list[dict[str, Any]] = []
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout.strip().splitlines()[-1])
            if isinstance(parsed, dict) and isinstance(parsed.get("records"), list):
                records = parsed["records"]
        except json.JSONDecodeError:
            records = []
    return SuiteRun(
        records=records,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
    )


def run_unittest(
    workspace: Path,
    backend: DockerBackend,
    limits: SandboxLimits,
    image: str,
) -> SuiteRun:
    """Run generated characterization tests in the sandbox."""
    return _run(workspace, backend, limits, ["python", "run_tests.py"], image)


def _keep_stable_tests(
    original: Path,
    backend: DockerBackend,
    limits: SandboxLimits,
) -> set[str]:
    runs = [run_unittest(original, backend, limits, PY2_IMAGE) for _ in range(3)]
    if any(run.timed_out for run in runs):
        raise PipelineError("characterization tests timed out on the original code")
    passed: list[set[str]] = []
    for run in runs:
        passed.append(
            {str(item["id"]) for item in run.records if item.get("status") == "pass"}
        )
    if not passed:
        return set()
    stable = passed[0]
    for extra in passed[1:]:
        stable &= extra
    return stable


def _valid_rows(observations: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index_by_module: dict[str, int] = {}
    for item in observations:
        if not isinstance(item, dict):
            continue
        module = item.get("module")
        function = item.get("function")
        if not isinstance(module, str) or not isinstance(function, str):
            continue
        if not SAFE_IDENT.match(module) or not SAFE_IDENT.match(function):
            continue
        if item.get("status") not in {"ok", "raise"}:
            continue
        count = index_by_module.get(module, 0)
        index_by_module[module] = count + 1
        row = dict(item)
        row["method"] = f"test_{function}_{count}"
        rows.append(row)
    return rows


def _write_tests(original: Path, rows: list[dict[str, Any]]) -> None:
    for path in original.glob("test_char_*.py"):
        path.unlink()
    by_module: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_module.setdefault(str(row["module"]), []).append(row)
    for module, module_rows in by_module.items():
        body = _module_test_source(module, module_rows)
        (original / f"test_char_{module}.py").write_text(body, encoding="utf-8")


def _module_test_source(module: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        "from __future__ import print_function",
        "import json",
        "import unittest",
        f"import {module}",
        "",
        "def canon(value):",
        "    if isinstance(value, tuple):",
        "        return list(value)",
        "    return value",
        "",
        f"class Test{module.title().replace('_', '')}(unittest.TestCase):",
    ]
    added = 0
    for row in rows:
        method = str(row["method"])
        args_literal = json.dumps(row.get("args", []))
        status = row.get("status")
        if status == "ok":
            expected = json.dumps(row.get("result"))
            lines.extend(
                [
                    f"    def {method}(self):",
                    f"        args = json.loads({args_literal!r})",
                    f"        expected = json.loads({expected!r})",
                    f"        got = canon({module}.{row['function']}(*args))",
                    "        self.assertEqual(got, expected)",
                    "",
                ]
            )
            added += 1
        elif status == "raise":
            exc = row.get("exc_type")
            if not isinstance(exc, str) or exc not in BUILTIN_EXC:
                continue
            lines.extend(
                [
                    f"    def {method}(self):",
                    f"        args = json.loads({args_literal!r})",
                    f"        fn = {module}.{row['function']}",
                    f"        self.assertRaises({exc}, fn, *args)",
                    "",
                ]
            )
            added += 1
    if added == 0:
        lines.extend(
            [
                "    def test_module_imports(self):",
                f"        self.assertTrue(hasattr({module}, '__file__'))",
                "",
            ]
        )
    lines.extend(["if __name__ == '__main__':", "    unittest.main()", ""])
    return "\n".join(lines)
