from pathlib import Path

from legacylift_worker.analyze import analyze_tree


def test_analyze_ranks_py2_markers(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "def f(xs):\n    print xs\n    for i in xrange(3):\n        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "clean.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    analysis = analyze_tree(tmp_path)
    assert analysis.language == "python"
    assert analysis.version_guess == "2.7"
    ranked = analysis.ranked_files()
    assert ranked[0].path == "mod.py"
    kinds = {item.kind for item in ranked[0].findings}
    assert "print_statement" in kinds
    assert "xrange" in kinds
    assert ranked[0].risk_score > ranked[1].risk_score
