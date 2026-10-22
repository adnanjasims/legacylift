"""Static analysis of ingested Python 2 trees.

Detects language markers, local imports, and deprecated Python 2 APIs,
then risk-ranks files by finding count. Chunking and embeddings live in
chunk.py and retrieval.py.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

FINDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("print_statement", re.compile(r"(?m)^\s*print\s+[^(]")),
    ("xrange", re.compile(r"\bxrange\s*\(")),
    ("iteritems", re.compile(r"\.iteritems\s*\(")),
    ("iterkeys", re.compile(r"\.iterkeys\s*\(")),
    ("itervalues", re.compile(r"\.itervalues\s*\(")),
    ("except_comma", re.compile(r"except\s+[^:]+,\s*\w+\s*:")),
    ("has_key", re.compile(r"\.has_key\s*\(")),
    ("raw_input", re.compile(r"\braw_input\s*\(")),
    ("unicode_type", re.compile(r"\bunicode\s*\(")),
    ("basestring", re.compile(r"\bbasestring\b")),
    ("urllib2", re.compile(r"\burllib2\b")),
    ("ConfigParser", re.compile(r"\bConfigParser\b")),
    ("long_type", re.compile(r"\blong\s*\(")),
    ("not_equal_angle", re.compile(r"<>")),
    ("integer_div_hint", re.compile(r"/\s*(?!/)")),
)

IMPORT_RE = re.compile(r"(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int


@dataclass
class FileAnalysis:
    path: str
    findings: list[Finding] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    @property
    def risk_score(self) -> int:
        return len(self.findings)


@dataclass
class Analysis:
    language: str
    version_guess: str
    files: list[FileAnalysis]

    def ranked_files(self) -> list[FileAnalysis]:
        """Return files with the highest finding count first."""
        return sorted(self.files, key=lambda item: item.risk_score, reverse=True)


def analyze_tree(root: Path) -> Analysis:
    """Scan a Python 2 tree or a Maven Java tree."""
    if (root / "pom.xml").is_file():
        return _analyze_java(root)
    files: list[FileAnalysis] = []
    py2_hits = 0
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if _skip_name(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        file_analysis = FileAnalysis(
            path=rel,
            findings=_findings(text),
            imports=_local_imports(text, root),
        )
        files.append(file_analysis)
        py2_hits += sum(
            1
            for finding in file_analysis.findings
            if finding.kind in {"print_statement", "xrange", "except_comma", "has_key"}
        )
    version = "2.7" if py2_hits else _ast_version_guess(files, root)
    return Analysis(language="python", version_guess=version, files=files)


def _analyze_java(root: Path) -> Analysis:
    files: list[FileAnalysis] = []
    src = root / "src" / "main" / "java"
    if not src.is_dir():
        return Analysis(language="java", version_guess="8", files=files)
    for path in sorted(src.rglob("*.java")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        files.append(FileAnalysis(path=rel, findings=_java_findings(text)))
    return Analysis(language="java", version_guess="8", files=files)


def _java_findings(text: str) -> list[Finding]:
    found: list[Finding] = []
    markers = (
        ("boxed_constructor", "new Integer("),
        ("url_constructor", "new URL("),
        ("thread_stop", ".stop()"),
    )
    for kind, needle in markers:
        start = 0
        while True:
            idx = text.find(needle, start)
            if idx < 0:
                break
            line = text[:idx].count("\n") + 1
            found.append(Finding(kind=kind, line=line))
            start = idx + len(needle)
    return found


def python_modules(root: Path) -> list[Path]:
    """Return source modules that should be characterized (not tests)."""
    modules: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if _skip_name(rel):
            continue
        modules.append(path)
    return modules


def _skip_name(rel: str) -> bool:
    name = Path(rel).name
    return (
        name.startswith("test_")
        or name.startswith("_probe")
        or name in {"run_tests.py", "conftest.py"}
    )


def _findings(text: str) -> list[Finding]:
    found: list[Finding] = []
    for kind, pattern in FINDING_PATTERNS:
        if kind == "integer_div_hint":
            continue
        for match in pattern.finditer(text):
            line = text[: match.start()].count("\n") + 1
            found.append(Finding(kind=kind, line=line))
    for match in FINDING_PATTERNS[-1][1].finditer(text):
        line_text = text[: match.start()].rsplit("\n", 1)[-1]
        if "for " in line_text:
            continue
        if re.search(r"\d+\s*/\s*\d+", line_text) and "//" not in line_text:
            line = text[: match.start()].count("\n") + 1
            found.append(Finding(kind="integer_div_hint", line=line))
    return found


def _local_imports(text: str, root: Path) -> list[str]:
    names: list[str] = []
    for match in IMPORT_RE.finditer(text):
        name = match.group(1)
        if (root / f"{name}.py").exists() or (root / name / "__init__.py").exists():
            names.append(name)
    return names


def _ast_version_guess(files: list[FileAnalysis], root: Path) -> str:
    for item in files:
        try:
            ast.parse((root / item.path).read_text(encoding="utf-8"))
        except SyntaxError:
            return "2.7"
    return "3.x"
