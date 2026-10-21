"""Turn job reports into the eval table. No invented percentages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from legacylift_worker.report import JobReport


@dataclass
class ModeMetrics:
    label: str
    files_total: int
    files_compile_ok: int
    tests_before_pass: int
    tests_before_total: int
    tests_after_pass: int
    tests_after_total: int
    attempts_sum: int
    tokens_in: int
    tokens_out: int
    estimated_cost: float | None
    wall_clock_sec: float
    needs_review: int
    provider: str | None = None
    model_id: str | None = None
    projects: list[str] = field(default_factory=list)


@dataclass
class EvalOutcome:
    deterministic: ModeMetrics | None
    llm: ModeMetrics | None
    docker: bool
    recorded: str
    notes: list[str]


def aggregate(
    label: str,
    reports: list[JobReport],
    wall_clock_sec: float,
    *,
    provider: str | None = None,
    model_id: str | None = None,
) -> ModeMetrics:
    """Sum file and test counts across corpus reports."""
    files_total = 0
    files_compile_ok = 0
    tests_before_pass = 0
    tests_before_total = 0
    tests_after_pass = 0
    tests_after_total = 0
    attempts_sum = 0
    tokens_in = 0
    tokens_out = 0
    needs_review = 0
    cost_total = 0.0
    cost_known = True
    projects: list[str] = []
    for report in reports:
        review = sum(1 for item in report.files if item.status == "needs_human_review")
        verified = report.verified_count()
        total = len(report.files)
        label = Path(report.source).name
        projects.append(f"{label}: {verified}/{total} verified, review {review}")
        tokens_in += report.tokens_in()
        tokens_out += report.tokens_out()
        report_cost = report.estimated_cost()
        if report.usage and report_cost is None:
            cost_known = False
        elif report_cost is not None:
            cost_total += report_cost
        for item in report.files:
            files_total += 1
            if item.compile_ok:
                files_compile_ok += 1
            tests_before_pass += item.tests_before_passed
            tests_before_total += item.tests_before_passed + item.tests_before_failed
            tests_after_pass += item.tests_after_passed
            tests_after_total += item.tests_after_passed + item.tests_after_failed
            attempts_sum += item.attempts
            if item.status == "needs_human_review":
                needs_review += 1
    return ModeMetrics(
        label=label,
        files_total=files_total,
        files_compile_ok=files_compile_ok,
        tests_before_pass=tests_before_pass,
        tests_before_total=tests_before_total,
        tests_after_pass=tests_after_pass,
        tests_after_total=tests_after_total,
        attempts_sum=attempts_sum,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        estimated_cost=cost_total if cost_known else None,
        wall_clock_sec=wall_clock_sec,
        needs_review=needs_review,
        provider=provider,
        model_id=model_id,
        projects=projects,
    )


def render_results(outcome: EvalOutcome) -> str:
    """Markdown table for docs/RESULTS.md."""
    det = _cells(outcome.deterministic)
    llm = _cells(outcome.llm)
    lines = [
        "# Evaluation results",
        "",
        f"Recorded {outcome.recorded}.",
        f"Docker: {'yes' if outcome.docker else 'no'}.",
        "",
        "Characterization tests ran in Docker against Python 2.7, then again",
        "against Python 3.12 after 2to3. A file is verified only when tests",
        "that passed on the original also pass after migration.",
        "",
        "| metric | deterministic-only | deterministic+LLM |",
        "| --- | --- | --- |",
        f"| files migrated and compiled | {det['compile']} | {llm['compile']} |",
        f"| characterization pass rate (before) | {det['before']} | {llm['before']} |",
        f"| characterization pass rate (after) | {det['after']} | {llm['after']} |",
        f"| attempts per file | {det['attempts']} | {llm['attempts']} |",
        f"| tokens (in/out) | {det['tokens']} | {llm['tokens']} |",
        f"| estimated cost USD | {det['cost']} | {llm['cost']} |",
        f"| wall-clock seconds | {det['wall']} | {llm['wall']} |",
        f"| files needing human review | {det['review']} | {llm['review']} |",
        "",
    ]
    if outcome.llm is not None and outcome.llm.provider:
        lines.extend(
            [
                f"LLM provider: {outcome.llm.provider} `{outcome.llm.model_id}`.",
                "",
            ]
        )
    if outcome.deterministic and outcome.deterministic.projects:
        lines.extend(["## Deterministic-only projects", ""])
        lines.extend(f"- {row}" for row in outcome.deterministic.projects)
        lines.append("")
    if outcome.llm and outcome.llm.projects:
        lines.extend(["## Deterministic plus LLM projects", ""])
        lines.extend(f"- {row}" for row in outcome.llm.projects)
        lines.append("")
    if outcome.notes:
        lines.extend(["## Notes", ""])
        lines.extend(f"- {note}" for note in outcome.notes)
        lines.append("")
    return "\n".join(lines)


def _cells(metrics: ModeMetrics | None) -> dict[str, str]:
    if metrics is None:
        na = "n/a"
        return {
            "compile": na,
            "before": na,
            "after": na,
            "attempts": na,
            "tokens": na,
            "cost": na,
            "wall": na,
            "review": na,
        }
    return {
        "compile": _ratio(metrics.files_compile_ok, metrics.files_total),
        "before": _ratio(metrics.tests_before_pass, metrics.tests_before_total),
        "after": _ratio(metrics.tests_after_pass, metrics.tests_after_total),
        "attempts": (
            f"{metrics.attempts_sum / metrics.files_total:.2f}"
            if metrics.files_total
            else "n/a"
        ),
        "tokens": f"{metrics.tokens_in}/{metrics.tokens_out}",
        "cost": (
            "n/a" if metrics.estimated_cost is None else f"{metrics.estimated_cost:.6f}"
        ),
        "wall": f"{metrics.wall_clock_sec:.1f}",
        "review": str(metrics.needs_review),
    }


def _ratio(passed: int, total: int) -> str:
    if total == 0:
        return "n/a"
    pct = 100.0 * passed / total
    return f"{pct:.1f}% ({passed}/{total})"
