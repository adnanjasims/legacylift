"""Copy a directory, zip, or git URL into an isolated workspace.

Uploaded trees are treated as hostile. Zip members cannot escape dest,
symlinks are refused, and archive size is capped.
"""

from __future__ import annotations

import shutil
import stat
import subprocess  # nosec B404
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from legacylift_worker.errors import PipelineError

MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_FILES = 200
MAX_FILE_BYTES = 1 * 1024 * 1024


def classify_source(source: str) -> str:
    """Return 'dir', 'zip', or 'git' for a CLI source string."""
    path = Path(source)
    if source.startswith("https://"):
        return "git"
    if path.is_file() and path.suffix.lower() == ".zip":
        return "zip"
    if path.is_dir():
        return "dir"
    raise PipelineError(f"source is not a directory, zip, or https git URL: {source}")


def ingest(source: str, dest: Path) -> Path:
    """Materialize source into dest and return dest.

    Args:
        source: Existing directory, .zip path, or https:// git URL.
        dest: Empty directory that will hold the copy.

    Returns:
        dest after files have been copied.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise PipelineError(f"ingest destination is not empty: {dest}")
    kind = classify_source(source)
    if kind == "dir":
        _copy_tree(Path(source).resolve(), dest)
    elif kind == "zip":
        _extract_zip(Path(source).resolve(), dest)
    else:
        _clone_git(source, dest)
    _reject_escaping_symlinks(dest)
    return dest


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _copy_tree(src: Path, dest: Path) -> None:
    file_count = 0
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part.startswith(".git") for part in rel.parts):
            continue
        target = dest / rel
        if path.is_symlink():
            raise PipelineError(f"symlinks are not allowed in source trees: {rel}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            continue
        file_count += 1
        if file_count > MAX_FILES:
            raise PipelineError(f"source exceeds {MAX_FILES} files")
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise PipelineError(f"file exceeds {MAX_FILE_BYTES} bytes: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _extract_zip(archive: Path, dest: Path) -> None:
    size = archive.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise PipelineError(f"zip exceeds {MAX_ARCHIVE_BYTES} bytes")
    try:
        with zipfile.ZipFile(archive) as zf:
            _extract_open_zip(zf, dest)
    except zipfile.BadZipFile as exc:
        raise PipelineError("file is not a valid zip archive") from exc


def _extract_open_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise PipelineError(f"zip exceeds {MAX_FILES} members")
    uncompressed = 0
    dest_root = dest.resolve()
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.endswith("/"):
            continue
        uncompressed += info.file_size
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise PipelineError(
                f"zip uncompressed size exceeds {MAX_UNCOMPRESSED_BYTES} bytes"
            )
        if info.file_size > MAX_FILE_BYTES:
            raise PipelineError(f"zip member exceeds {MAX_FILE_BYTES} bytes: {name}")
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise PipelineError(f"symlink zip members are not allowed: {name}")
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts:
            raise PipelineError(f"zip member path is not allowed: {name}")
        target = (dest / name).resolve()
        if not _is_within(dest_root, target):
            raise PipelineError(f"zip member would extract outside workspace: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def _clone_git(url: str, dest: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.path:
        raise PipelineError("git sources must be https URLs")
    if parsed.username or parsed.password:
        raise PipelineError("git URLs must not contain credentials")
    git = shutil.which("git")
    if git is None:
        raise PipelineError("git is not installed")
    cmd = [
        git,
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--config",
        "core.symlinks=false",
        url,
        str(dest),
    ]
    completed = subprocess.run(  # nosec B603
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise PipelineError(f"git clone failed: {completed.stderr.strip()}")


def _reject_escaping_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        rel = path.relative_to(root)
        raise PipelineError(f"symlinks are not allowed after ingest: {rel}")
