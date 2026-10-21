from pathlib import Path

from legacylift_eval.metrics import EvalOutcome, ModeMetrics, aggregate, render_results
from legacylift_eval.run import results_path
from legacylift_worker.analyze import Analysis, FileAnalysis, Finding
from legacylift_worker.characterize import SuiteRun
from legacylift_worker.report import build_report


def test_results_path_under_docs(tmp_path: Path) -> None:
    assert results_path(tmp_path) == tmp_path / "docs" / "RESULTS.md"


def test_render_results_is_na_without_docker() -> None:
    text = render_results(
        EvalOutcome(
            deterministic=None,
            llm=None,
            docker=False,
            recorded="2026-10-21 18:00 UTC",
            notes=["Docker daemon is not running. Metrics are n/a."],
        )
    )
    assert "n/a" in text
    assert "not running" in text
    assert "100%" not in text
    assert "deterministic-only" in text
    assert "deterministic+LLM" in text


def test_aggregate_and_render_use_real_counts(tmp_path: Path) -> None:
    original = tmp_path / "original"
    migrated = tmp_path / "migrated"
    original.mkdir()
    migrated.mkdir()
    (original / "mod.py").write_text("def f():\n    print 1\n", encoding="utf-8")
    (migrated / "mod.py").write_text("def f():\n    print(1)\n", encoding="utf-8")
    analysis = Analysis(
        language="python",
        version_guess="2.7",
        files=[
            FileAnalysis(
                path="mod.py", findings=[Finding(kind="print_statement", line=2)]
            )
        ],
    )
    before = SuiteRun(
        records=[{"id": "test_char_mod.TestMod.test_f_0", "status": "pass"}],
        stdout="",
        stderr="",
        exit_code=0,
        timed_out=False,
    )
    after = SuiteRun(
        records=[{"id": "test_char_mod.TestMod.test_f_0", "status": "fail"}],
        stdout="",
        stderr="",
        exit_code=1,
        timed_out=False,
    )
    compiled = SuiteRun(records=[], stdout="", stderr="", exit_code=0, timed_out=False)
    report = build_report(
        job_id="abc",
        source="corpus/mod",
        original=original,
        migrated=migrated,
        analysis=analysis,
        before=before,
        after=after,
        compiled=compiled,
        attempts={"mod.py": 1},
    )
    metrics = aggregate("deterministic", [report], wall_clock_sec=12.5)
    assert metrics.files_total == 1
    assert metrics.files_compile_ok == 1
    assert metrics.tests_before_pass == 1
    assert metrics.tests_after_pass == 0
    assert metrics.needs_review == 1
    text = render_results(
        EvalOutcome(
            deterministic=metrics,
            llm=None,
            docker=True,
            recorded="2026-10-21 18:00 UTC",
            notes=["LLM column is n/a."],
        )
    )
    assert "100.0% (1/1)" in text
    assert "0.0% (0/1)" in text
    assert "n/a" in text
    assert "12.5" in text
