"""Run the corpus through deterministic and optional LLM pipelines.

Writes docs/RESULTS.md with numbers from those runs. Missing Docker or a
missing LLM configuration is recorded as n/a to ensure no fabricated scores.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from legacylift_eval.metrics import (
    EvalOutcome,
    ModeMetrics,
    aggregate,
    render_results,
)
from legacylift_sandbox import DEFAULT_LIMITS, SandboxLimits, docker_available
from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.base import LLMProvider
from legacylift_worker.llm.factory import configured_provider
from legacylift_worker.maven import maven_repo
from legacylift_worker.pipeline import run_migration
from legacylift_worker.report import JobReport

CORPUS_PYTHON = ("py2_pricing", "py2_textkit", "py2_counts")
CORPUS_JAVA = ("java8_box", "java8_urlkit")
CORPUS = CORPUS_PYTHON + CORPUS_JAVA


def repo_root() -> Path:
    """Return the repository root (two levels above this package)."""
    return Path(__file__).resolve().parents[3]


def results_path(root: Path | None = None) -> Path:
    """Return the path of the generated results file."""
    base = root if root is not None else repo_root()
    return base / "docs" / "RESULTS.md"


def write_results(root: Path | None = None) -> Path:
    """Run eval when possible and write docs/RESULTS.md."""
    base = root if root is not None else repo_root()
    outcome = run_eval(base)
    path = results_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_results(outcome), encoding="utf-8")
    return path


def run_eval(root: Path) -> EvalOutcome:
    """Execute corpus migrations and collect metrics."""
    recorded = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    notes: list[str] = []
    if not docker_available():
        notes.append("Docker daemon is not running. Metrics are n/a.")
        return EvalOutcome(
            deterministic=None,
            llm=None,
            docker=False,
            recorded=recorded,
            notes=notes,
        )
    limits = SandboxLimits(
        timeout_sec=max(DEFAULT_LIMITS.timeout_sec, 120.0),
        memory_mb=DEFAULT_LIMITS.memory_mb,
    )
    names = list(CORPUS_PYTHON)
    try:
        maven_repo()
        names.extend(CORPUS_JAVA)
    except PipelineError:
        notes.append(
            "Java corpus skipped. Run make java-deps for the offline Maven cache."
        )
    det_reports, det_wall = _run_mode(
        root, limits, llm=None, stamp="eval-deterministic", names=names
    )
    deterministic = aggregate("deterministic", det_reports, det_wall)
    llm_provider = configured_provider()
    llm_metrics: ModeMetrics | None
    if llm_provider is None:
        notes.append(
            "LLM column is n/a. Set WATSONX_* or OLLAMA_MODEL and "
            "OLLAMA_EMBED_MODEL to run deterministic plus LLM."
        )
        llm_metrics = None
    else:
        llm_reports, llm_wall = _run_mode(
            root, limits, llm=llm_provider, stamp="eval-llm", names=names
        )
        llm_metrics = aggregate(
            "deterministic+llm",
            llm_reports,
            llm_wall,
            provider=llm_provider.name,
            model_id=llm_provider.model_id,
        )
    return EvalOutcome(
        deterministic=deterministic,
        llm=llm_metrics,
        docker=True,
        recorded=recorded,
        notes=notes,
    )


def _run_mode(
    root: Path,
    limits: SandboxLimits,
    *,
    llm: LLMProvider | None,
    stamp: str,
    names: list[str],
) -> tuple[list[JobReport], float]:
    reports: list[JobReport] = []
    started = perf_counter()
    for name in names:
        source = root / "corpus" / name
        out_dir = root / "reports" / stamp / name
        reports.append(run_migration(str(source), out_dir, limits=limits, llm=llm))
    return reports, perf_counter() - started


def main() -> None:
    """Entry point for `python -m legacylift_eval.run`."""
    path = write_results()
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
