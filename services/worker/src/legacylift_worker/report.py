"""Build the JSON and Markdown migration report."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from legacylift_worker.analyze import Analysis, FileAnalysis
from legacylift_worker.characterize import SuiteRun
from legacylift_worker.llm.base import UsageRecord

FileStatus = Literal["verified", "needs_human_review"]


class FileReport(BaseModel):
    path: str
    status: FileStatus
    risk_score: int
    findings: list[str]
    tests_before_passed: int
    tests_before_failed: int
    tests_after_passed: int
    tests_after_failed: int
    compile_ok: bool
    diff: str
    after_failures: list[str] = Field(default_factory=list)
    attempts: int = 1
    llm_used: bool = False


class UsageEntry(BaseModel):
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    estimated_cost: float | None
    attempt: int


class JobReport(BaseModel):
    job_id: str
    source: str
    language: str
    version_guess: str
    tool: str = "2to3 (CPython 3.12 lib2to3 default fixers)"
    files: list[FileReport]
    notes: list[str] = Field(default_factory=list)
    mode: str = "deterministic"
    provider: str | None = None
    model_id: str | None = None
    wall_clock_sec: float = 0.0
    usage: list[UsageEntry] = Field(default_factory=list)

    def verified_count(self) -> int:
        return sum(1 for item in self.files if item.status == "verified")

    def tokens_in(self) -> int:
        return sum(item.tokens_in for item in self.usage)

    def tokens_out(self) -> int:
        return sum(item.tokens_out for item in self.usage)

    def estimated_cost(self) -> float | None:
        if not self.usage:
            return 0.0
        total = 0.0
        for item in self.usage:
            if item.estimated_cost is None:
                return None
            total += item.estimated_cost
        return total


def count_pass_fail(run: SuiteRun) -> tuple[int, int]:
    """Return (passed, failed_or_error) from a unittest JSON run."""
    passed = sum(1 for item in run.records if item.get("status") == "pass")
    failed = sum(1 for item in run.records if item.get("status") in {"fail", "error"})
    return passed, failed


def file_diff(original: Path, migrated: Path, rel: str) -> str:
    """Unified diff for one relative path. Empty when the file is unchanged."""
    src = original / rel
    dst = migrated / rel
    if not src.exists() or not dst.exists():
        return ""
    left = src.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    right = dst.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(left, right, fromfile=f"a/{rel}", tofile=f"b/{rel}")
    )


def file_is_verified(
    item: FileAnalysis,
    before: SuiteRun,
    after: SuiteRun,
    compile_ok: bool,
) -> bool:
    """True when kept original tests still pass after migration and compile."""
    module = Path(item.path).stem
    b_pass, b_fail = _index_by_module(before).get(module, (0, 0))
    a_pass, a_fail = _index_by_module(after).get(module, (0, 0))
    return counts_verified(b_pass, b_fail, a_pass, a_fail, compile_ok)


def counts_verified(
    b_pass: int,
    b_fail: int,
    a_pass: int,
    a_fail: int,
    compile_ok: bool,
) -> bool:
    return (
        compile_ok and b_pass > 0 and b_fail == 0 and a_fail == 0 and a_pass >= b_pass
    )


def build_report(
    *,
    job_id: str,
    source: str,
    original: Path,
    migrated: Path,
    analysis: Analysis,
    before: SuiteRun,
    after: SuiteRun,
    compiled: SuiteRun,
    attempts: dict[str, int] | None = None,
    llm_used: set[str] | None = None,
    usage: list[UsageRecord] | None = None,
    mode: str = "deterministic",
    provider: str | None = None,
    model_id: str | None = None,
    wall_clock_sec: float = 0.0,
) -> JobReport:
    """Attach before/after test counts and diffs to each analyzed source file."""
    before_by_mod = _index_by_module(before)
    after_by_mod = _index_by_module(after)
    compile_ok = compiled.exit_code == 0 and not compiled.timed_out
    used = llm_used or set()
    per_attempts = attempts or {}
    files: list[FileReport] = []
    notes: list[str] = []
    if not compile_ok:
        notes.append("python -m compileall failed on the migrated tree.")
    for item in analysis.ranked_files():
        module = Path(item.path).stem
        b_pass, b_fail = before_by_mod.get(module, (0, 0))
        a_pass, a_fail = after_by_mod.get(module, (0, 0))
        failures = [
            f"{rec.get('id')}: {rec.get('detail', '')[:500]}"
            for rec in after.records
            if rec.get("status") in {"fail", "error"}
            and module in str(rec.get("id", ""))
        ]
        verified = counts_verified(b_pass, b_fail, a_pass, a_fail, compile_ok)
        files.append(
            FileReport(
                path=item.path,
                status="verified" if verified else "needs_human_review",
                risk_score=item.risk_score,
                findings=[finding.kind for finding in item.findings],
                tests_before_passed=b_pass,
                tests_before_failed=b_fail,
                tests_after_passed=a_pass,
                tests_after_failed=a_fail,
                compile_ok=compile_ok,
                diff=file_diff(original, migrated, item.path),
                after_failures=failures,
                attempts=per_attempts.get(item.path, 1),
                llm_used=item.path in used,
            )
        )
        if b_pass == 0:
            notes.append(f"{item.path}: no stable characterization tests were kept.")
    return JobReport(
        job_id=job_id,
        source=source,
        language=analysis.language,
        version_guess=analysis.version_guess,
        files=files,
        notes=notes,
        mode=mode,
        provider=provider,
        model_id=model_id,
        wall_clock_sec=wall_clock_sec,
        usage=[_usage_entry(item) for item in usage or []],
    )


def _usage_entry(item: UsageRecord) -> UsageEntry:
    return UsageEntry(
        provider=item.provider,
        model=item.model,
        tokens_in=item.tokens_in,
        tokens_out=item.tokens_out,
        latency_ms=item.latency_ms,
        estimated_cost=item.estimated_cost,
        attempt=item.attempt,
    )


def write_report(report: JobReport, out_dir: Path) -> None:
    """Write report.json and report.md under out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = report.model_dump()
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: JobReport) -> str:
    """Plain-language report plus the per-file table."""
    verified = report.verified_count()
    total = len(report.files)
    lines = [
        f"# LegacyLift report ({report.job_id})",
        "",
        "Plain English: characterization tests were generated from the original",
        "Python 2 code in Docker, then the same tests were run after a 2to3",
        "rewrite. A file is verified only when tests that passed on the original",
        "also pass on Python 3.12.",
        "",
        f"- Source: `{report.source}`",
        f"- Detected: {report.language} {report.version_guess}",
        f"- Tool: {report.tool}",
        f"- Mode: {report.mode}",
    ]
    if report.provider:
        lines.append(f"- LLM: {report.provider} `{report.model_id}`")
    lines.extend(
        [
            f"- Files verified: {verified} / {total}",
            f"- Wall-clock seconds: {report.wall_clock_sec:.1f}",
            f"- Tokens in/out: {report.tokens_in()}/{report.tokens_out()}",
            f"- Estimated cost USD: {_cost_label(report.estimated_cost())}",
            "",
            "| file | status | before | after | compile | risk | attempts | llm |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.files:
        lines.append(
            f"| `{item.path}` | {item.status} | "
            f"{item.tests_before_passed}/{item.tests_before_failed} | "
            f"{item.tests_after_passed}/{item.tests_after_failed} | "
            f"{'ok' if item.compile_ok else 'fail'} | {item.risk_score} | "
            f"{item.attempts} | {'yes' if item.llm_used else 'no'} |"
        )
    if report.notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in report.notes)
    for item in report.files:
        if item.diff:
            lines.extend(
                ["", f"## Diff `{item.path}`", "", "```diff", item.diff, "```"]
            )
        if item.after_failures:
            lines.extend(["", f"## Failures `{item.path}`"])
            lines.extend(f"```\n{detail}\n```" for detail in item.after_failures)
    lines.append("")
    return "\n".join(lines)


def _cost_label(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def _index_by_module(run: SuiteRun) -> dict[str, tuple[int, int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for rec in run.records:
        test_id = str(rec.get("id", ""))
        module = _module_from_test_id(test_id)
        grouped.setdefault(module, []).append(rec)
    out: dict[str, tuple[int, int]] = {}
    for module, recs in grouped.items():
        fake = SuiteRun(
            records=recs,
            stdout="",
            stderr="",
            exit_code=0,
            timed_out=False,
        )
        out[module] = count_pass_fail(fake)
    return out


def _module_from_test_id(test_id: str) -> str:
    """Map test_char_pricing.TestPricing.test_add_tax_0 to pricing."""
    head = test_id.split(".", 1)[0]
    if head.startswith("test_char_"):
        return head[len("test_char_") :]
    return head
