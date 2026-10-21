from pathlib import Path

from legacylift_worker.characterize import _valid_rows, _write_tests


def test_write_tests_emits_assert_equal(tmp_path: Path) -> None:
    rows = _valid_rows(
        [
            {
                "module": "pricing",
                "function": "add_tax",
                "args": [10, 8],
                "status": "ok",
                "result": 10.8,
            }
        ]
    )
    _write_tests(tmp_path, rows)
    text = (tmp_path / "test_char_pricing.py").read_text(encoding="utf-8")
    assert "import pricing" in text
    assert "json.loads" in text
    assert "add_tax" in text
    assert "eval(" not in text
