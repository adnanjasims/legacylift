from pathlib import Path

from legacylift_worker.chunk import CodeChunk
from legacylift_worker.llm.fake import FakeProvider
from legacylift_worker.retrieval import MemoryIndex


def test_memory_index_ranks_similar_chunk_first(tmp_path: Path) -> None:
    del tmp_path
    provider = FakeProvider()
    index = MemoryIndex("job1", provider)
    index.add(
        [
            CodeChunk(path="a.py", index=0, text="integer division half n / 2"),
            CodeChunk(path="b.py", index=0, text="print banner textkit"),
        ]
    )
    found, usage = index.query("division half integer", k=2)
    assert usage.provider == "fake"
    assert found[0].path == "a.py"
    assert found[0].score >= found[1].score
