from pathlib import Path

from legacylift_worker.analyze import analyze_tree
from legacylift_worker.maven import maven_argv, parse_surefire, rewrite_argv
from legacylift_worker.report import _module_from_test_id


def test_parse_surefire_counts_pass_and_fail() -> None:
    log = """
[INFO] Running com.example.box.BoxTest
[INFO] Tests run: 2, Failures: 0, Errors: 0, Skipped: 0 -- in com.example.box.BoxTest
[INFO] Running com.example.urlkit.UrlKitTest
[INFO] Tests run: 2, Failures: 1, Errors: 0 -- in com.example.urlkit.UrlKitTest
"""
    records = parse_surefire(log)
    passed = [item for item in records if item["status"] == "pass"]
    failed = [item for item in records if item["status"] == "fail"]
    assert len(passed) == 3
    assert len(failed) == 1
    assert passed[0]["id"] == "com.example.box.BoxTest"
    assert failed[0]["id"] == "com.example.urlkit.UrlKitTest"


def test_module_from_java_surefire_id() -> None:
    assert _module_from_test_id("com.example.box.BoxTest") == "Box"
    assert (
        _module_from_test_id("com.example.urlkit.UrlKitTest.hostFromHttp") == "UrlKit"
    )
    assert _module_from_test_id("test_char_pricing.TestPricing.test_add_tax_0") == (
        "pricing"
    )


def test_analyze_java_tree(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "com" / "example" / "box"
    src.mkdir(parents=True)
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (src / "Box.java").write_text(
        "package com.example.box;\n"
        "public class Box {\n"
        "    public static Integer boxed(int n) { return new Integer(n); }\n"
        "}\n",
        encoding="utf-8",
    )
    analysis = analyze_tree(tmp_path)
    assert analysis.language == "java"
    assert analysis.version_guess == "8"
    assert analysis.files[0].path.endswith("Box.java")
    kinds = {item.kind for item in analysis.files[0].findings}
    assert "boxed_constructor" in kinds


def test_rewrite_argv_uses_central_pins() -> None:
    argv = rewrite_argv()
    joined = " ".join(argv)
    assert "rewrite-maven-plugin:6.46.1" in joined
    assert "rewrite-migrate-java:3.42.1" in joined
    assert "UpgradeToJava21" in joined
    assert "-o" in argv
    assert "/output/" in joined


def test_maven_argv_copies_offline_cache() -> None:
    argv = maven_argv("test")
    assert argv[:3] == ["sh", "-c", 'cp -a /m2 /tmp/m2 && exec "$@"']
    assert "mvn" in argv
    assert "-o" in argv
