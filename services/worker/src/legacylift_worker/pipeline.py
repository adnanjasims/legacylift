"""Synchronous pipeline: ingest through report, optional LLM repair."""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from time import perf_counter

from legacylift_sandbox import DEFAULT_LIMITS, JAVA_LIMITS, DockerBackend, SandboxLimits
from legacylift_worker.analyze import analyze_tree
from legacylift_worker.characterize import generate_and_keep_tests
from legacylift_worker.errors import PipelineError
from legacylift_worker.ingest import ingest
from legacylift_worker.jsonlog import configure_logging
from legacylift_worker.llm.base import LLMProvider, UsageRecord
from legacylift_worker.maven import characterize_java
from legacylift_worker.migrate_2to3 import migrate_with_2to3
from legacylift_worker.migrate_rewrite import migrate_with_rewrite
from legacylift_worker.report import JobReport, build_report, write_report
from legacylift_worker.retrieval import index_tree, open_index
from legacylift_worker.retry import files_needing_repair, repair_until_verified
from legacylift_worker.verify import verify_migrated

logger = logging.getLogger("legacylift.worker")


def run_migration(
    source: str,
    out_dir: Path,
    *,
    backend: DockerBackend | None = None,
    limits: SandboxLimits = DEFAULT_LIMITS,
    llm: LLMProvider | None = None,
) -> JobReport:
    """Run ingest, analyze, characterize, migrate, optional LLM retry, verify.

    Args:
        source: Directory, zip path, or https git URL.
        out_dir: Destination for report.json, report.md, original/, migrated/.
        backend: Sandbox backend. Defaults to DockerBackend.
        limits: CPU, memory, pid, and timeout caps.
        llm: Optional provider used only after 2to3 verification fails.

    Returns:
        The job report that was written to out_dir.
    """
    configure_logging()
    started = perf_counter()
    runner = backend if backend is not None else DockerBackend()
    job_id = uuid.uuid4().hex[:12]
    work = Path(tempfile.mkdtemp(prefix=f"legacylift-{job_id}-"))
    original = work / "original"
    original.mkdir()
    logger.info("ingest start", extra={"job_id": job_id})
    try:
        ingest(source, original)
        analysis = analyze_tree(original)
        logger.info(
            "analyze done",
            extra={"job_id": job_id, "files": str(len(analysis.files))},
        )
        migrated = work / "migrated"
        tool = "2to3 (CPython 3.12 lib2to3 default fixers)"
        summary = ""
        if analysis.language == "java":
            before = characterize_java(original, runner, JAVA_LIMITS)
            logger.info("characterization done", extra={"job_id": job_id})
            rewrite_log = migrate_with_rewrite(original, migrated, runner, JAVA_LIMITS)
            logger.info("openrewrite done", extra={"job_id": job_id})
            compiled, after = verify_migrated(migrated, runner, JAVA_LIMITS)
            tool = (
                "OpenRewrite org.openrewrite.java.migrate.UpgradeToJava21 "
                "(rewrite-maven-plugin 6.46.1)"
            )
            summary = _rewrite_summary(rewrite_log)
        else:
            before = generate_and_keep_tests(original, runner, limits)
            logger.info("characterization done", extra={"job_id": job_id})
            two_to_three_log = migrate_with_2to3(original, migrated)
            logger.info("2to3 done", extra={"job_id": job_id})
            compiled, after = verify_migrated(migrated, runner, limits)
            summary = _two_to_three_summary(two_to_three_log)
        logger.info("verify done", extra={"job_id": job_id})
        usage: list[UsageRecord] = []
        attempts = {item.path: 1 for item in analysis.files}
        llm_used: set[str] = set()
        if llm is not None and analysis.language != "java":
            if files_needing_repair(list(analysis.files), before, after, compiled):
                index = open_index(job_id, llm)
                usage.extend(index_tree(migrated, index))
                (
                    compiled,
                    after,
                    attempts,
                    llm_used,
                    extra_usage,
                ) = repair_until_verified(
                    job_id=job_id,
                    migrated=migrated,
                    files=list(analysis.files),
                    before=before,
                    after=after,
                    compiled=compiled,
                    backend=runner,
                    limits=limits,
                    llm=llm,
                    index=index,
                )
                usage.extend(extra_usage)
                logger.info("llm repair done", extra={"job_id": job_id})
        wall_clock_sec = perf_counter() - started
        report = build_report(
            job_id=job_id,
            source=source,
            original=original,
            migrated=migrated,
            analysis=analysis,
            before=before,
            after=after,
            compiled=compiled,
            attempts=attempts,
            llm_used=llm_used,
            usage=usage,
            mode="deterministic+llm" if llm is not None else "deterministic",
            provider=llm.name if llm is not None else None,
            model_id=llm.model_id if llm is not None else None,
            wall_clock_sec=wall_clock_sec,
            tool=tool,
        )
        if summary:
            report.notes.append(summary)
        write_report(report, out_dir)
        _copy_tree(original, out_dir / "original")
        _copy_tree(migrated, out_dir / "migrated")
        return report
    except PipelineError:
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _rewrite_summary(log: str) -> str:
    hits = [
        line.strip()
        for line in log.splitlines()
        if "Changes have been made" in line or "Applying recipe" in line
    ]
    return "\n".join(hits[:20])


def _two_to_three_summary(log: str) -> str:
    """Keep fixer skip lines. Drop host paths from RefactoringTool output."""
    skips = [
        line.strip() for line in log.splitlines() if "Skipping optional fixer" in line
    ]
    return "\n".join(skips)


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
