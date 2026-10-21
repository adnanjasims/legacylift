from legacylift_worker.chunk import CHUNK_LINES, chunk_source


def test_short_file_is_one_chunk() -> None:
    chunks = chunk_source("mod.py", "def f():\n    return 1\n")
    assert len(chunks) == 1
    assert chunks[0].path == "mod.py"
    assert "def f()" in chunks[0].text


def test_long_file_overlaps_windows() -> None:
    lines = [f"x = {i}\n" for i in range(CHUNK_LINES + 10)]
    chunks = chunk_source("long.py", "".join(lines))
    assert len(chunks) >= 2
    assert chunks[0].index == 0
    assert chunks[1].index == 1
    assert chunks[0].text.splitlines()[-1] in chunks[1].text
