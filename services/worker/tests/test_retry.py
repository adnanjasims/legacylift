from pathlib import Path

import pytest

from legacylift_sandbox import DEFAULT_LIMITS, DockerBackend
from legacylift_worker.analyze import FileAnalysis
from legacylift_worker.characterize import SuiteRun
from legacylift_worker.chunk import CodeChunk
from legacylift_worker.llm.fake import FakeProvider
from legacylift_worker.retrieval import MemoryIndex
from legacylift_worker.retry import (
    MAX_LLM_ATTEMPTS,
    parse_python_fence,
    repair_until_verified,
)


def test_parse_python_fence_extracts_block() -> None:
    text = "notes\n```python\ndef f():\n    return 1\n```\n"
    assert parse_python_fence(text) == "def f():\n    return 1\n"


def test_parse_python_fence_none_for_prose() -> None:
    assert parse_python_fence("I cannot help with that.") is None


def test_repair_stops_after_max_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated = tmp_path / "migrated"
    migrated.mkdir()
    (migrated / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    before = SuiteRun(
        records=[{"id": "test_char_mod.TestMod.test_f_0", "status": "pass"}],
        stdout="",
        stderr="",
        exit_code=0,
        timed_out=False,
    )
    after = SuiteRun(
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
    llm = FakeProvider(replies=["```python\ndef f():\n    return 2\n```"] * 5)
    index = MemoryIndex("job", llm)
    index.add([CodeChunk(path="mod.py", index=0, text="def f():\n    return 1\n")])
    calls = {"n": 0}

    def fake_verify(
        path: Path, backend: DockerBackend, limits: object
    ) -> tuple[SuiteRun, SuiteRun]:
        del path, backend, limits
        calls["n"] += 1
        return compiled, after

    monkeypatch.setattr("legacylift_worker.retry.verify_migrated", fake_verify)
    _, _, attempts, used, usage = repair_until_verified(
        job_id="job",
        migrated=migrated,
        files=[FileAnalysis(path="mod.py")],
        before=before,
        after=after,
        compiled=compiled,
        backend=DockerBackend(),
        limits=DEFAULT_LIMITS,
        llm=llm,
        index=index,
    )
    assert llm.chat_calls == MAX_LLM_ATTEMPTS
    assert attempts["mod.py"] == 1 + MAX_LLM_ATTEMPTS
    assert "mod.py" in used
    assert calls["n"] == MAX_LLM_ATTEMPTS
    assert usage
