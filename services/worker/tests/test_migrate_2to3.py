from pathlib import Path

from legacylift_worker.migrate_2to3 import migrate_with_2to3


def test_2to3_rewrites_print_and_xrange(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    (original / "mod.py").write_text(
        "def f(n):\n    print n\n    return list(xrange(n))\n",
        encoding="utf-8",
    )
    migrated = tmp_path / "migrated"
    migrate_with_2to3(original, migrated)
    text = (migrated / "mod.py").read_text(encoding="utf-8")
    assert "print(" in text
    assert "xrange" not in text
    assert "range(" in text
    compile(text, str(migrated / "mod.py"), "exec")
