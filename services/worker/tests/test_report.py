from pathlib import Path

from legacylift_worker.analyze import Analysis, FileAnalysis, Finding
from legacylift_worker.characterize import SuiteRun
from legacylift_worker.report import build_report, render_markdown


def test_report_marks_verified_only_when_after_tests_pass(tmp_path: Path) -> None:
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
    after_fail = SuiteRun(
        records=[
            {
                "id": "test_char_mod.TestMod.test_f_0",
                "status": "fail",
                "detail": "AssertionError",
            }
        ],
        stdout="",
        stderr="",
        exit_code=1,
        timed_out=False,
    )
    compiled = SuiteRun(records=[], stdout="", stderr="", exit_code=0, timed_out=False)
    failed = build_report(
        job_id="abc",
        source="corpus/mod",
        original=original,
        migrated=migrated,
        analysis=analysis,
        before=before,
        after=after_fail,
        compiled=compiled,
    )
    assert failed.files[0].status == "needs_human_review"
    after_ok = SuiteRun(
        records=[{"id": "test_char_mod.TestMod.test_f_0", "status": "pass"}],
        stdout="",
        stderr="",
        exit_code=0,
        timed_out=False,
    )
    ok = build_report(
        job_id="abc",
        source="corpus/mod",
        original=original,
        migrated=migrated,
        analysis=analysis,
        before=before,
        after=after_ok,
        compiled=compiled,
    )
    assert ok.files[0].status == "verified"
    markdown = render_markdown(ok)
    assert "verified" in markdown
    assert "Plain English" in markdown
