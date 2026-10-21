"""Split source files into overlapping line windows for embedding.

Granite embedding models on watsonx.ai accept 512 input tokens. Forty
lines of Python stays under that on the corpus trees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from legacylift_worker.analyze import python_modules

CHUNK_LINES = 40
OVERLAP_LINES = 8


@dataclass(frozen=True)
class CodeChunk:
    path: str
    index: int
    text: str


def chunk_tree(root: Path) -> list[CodeChunk]:
    """Chunk every non-test Python module under root."""
    chunks: list[CodeChunk] = []
    for path in python_modules(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks.extend(chunk_source(rel, text))
    return chunks


def chunk_source(path: str, text: str) -> list[CodeChunk]:
    """Split one file into overlapping windows. A short file is one chunk."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return [CodeChunk(path=path, index=0, text="")]
    if len(lines) <= CHUNK_LINES:
        return [CodeChunk(path=path, index=0, text="".join(lines))]
    step = CHUNK_LINES - OVERLAP_LINES
    chunks: list[CodeChunk] = []
    start = 0
    index = 0
    while start < len(lines):
        window = lines[start : start + CHUNK_LINES]
        chunks.append(CodeChunk(path=path, index=index, text="".join(window)))
        index += 1
        if start + CHUNK_LINES >= len(lines):
            break
        start += step
    return chunks
