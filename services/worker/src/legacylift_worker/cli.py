"""CLI for the M1 synchronous migration pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from legacylift_sandbox import DEFAULT_LIMITS, SandboxLimits, docker_available
from legacylift_worker.errors import PipelineError
from legacylift_worker.llm.factory import provider_from_name
from legacylift_worker.pipeline import run_migration


def build_parser() -> argparse.ArgumentParser:
    """Return the migrate CLI parser."""
    parser = argparse.ArgumentParser(
        prog="legacylift",
        description="Migrate a Python 2 or Java 8 tree with sandbox-checked tests.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser("migrate", help="ingest, characterize, 2to3, verify")
    migrate.add_argument("source", help="directory, zip file, or https git URL")
    migrate.add_argument(
        "--out",
        type=Path,
        required=True,
        help="directory for report.json, report.md, original/, migrated/",
    )
    migrate.add_argument("--timeout", type=float, default=DEFAULT_LIMITS.timeout_sec)
    migrate.add_argument("--memory-mb", type=int, default=DEFAULT_LIMITS.memory_mb)
    migrate.add_argument(
        "--llm",
        default="none",
        help="none (default), watsonx, or local. fake is rejected.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m legacylift_worker.cli`."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "migrate":
        parser.error(f"unknown command {args.command}")
    if not docker_available():
        print(
            "docker CLI cannot reach a daemon (docker info failed); "
            "DockerBackend cannot execute code",
            file=sys.stderr,
        )
        return 2
    limits = SandboxLimits(timeout_sec=args.timeout, memory_mb=args.memory_mb)
    try:
        llm = provider_from_name(args.llm)
        report = run_migration(args.source, args.out, limits=limits, llm=llm)
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    verified = report.verified_count()
    total = len(report.files)
    print(f"wrote {args.out / 'report.md'} ({verified}/{total} files verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
