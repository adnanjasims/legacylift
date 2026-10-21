import io
import stat
import zipfile
from pathlib import Path

import pytest

from legacylift_worker.errors import PipelineError
from legacylift_worker.ingest import ingest


def test_copy_directory(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("x = 1\n", encoding="utf-8")
    dest = tmp_path / "dest"
    ingest(str(src), dest)
    assert (dest / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.py", "print 1\n")
    dest = tmp_path / "dest"
    with pytest.raises(PipelineError, match="not allowed"):
        ingest(str(archive), dest)
    assert not (tmp_path / "escape.py").exists()


def test_zip_symlink_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "link.zip"
    info = zipfile.ZipInfo("link.py")
    info.external_attr = (stat.S_IFLNK | 0o644) << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "/tmp/target")
    dest = tmp_path / "dest"
    with pytest.raises(PipelineError, match="symlink"):
        ingest(str(archive), dest)


def test_valid_zip_extracts(tmp_path: Path) -> None:
    archive = tmp_path / "ok.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("pkg/mod.py", "print 1\n")
    archive.write_bytes(buf.getvalue())
    dest = tmp_path / "dest"
    ingest(str(archive), dest)
    assert (dest / "pkg" / "mod.py").read_text(encoding="utf-8") == "print 1\n"
