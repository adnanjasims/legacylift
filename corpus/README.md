# Corpus

Small legacy projects used by `make migrate-samples` and `make eval`.

Python 2.7 samples in M1:

- `py2_textkit`: `iteritems`, `has_key`, `except E, e`, `print`
- `py2_pricing`: `xrange`, `print`, float division
- `py2_counts`: integer `/` plus `xrange` (2to3 default fixers leave `/`)

Java 8 Maven samples in M6 (`make java-deps` seeds `reports/m2` for offline `mvn`):

- `java8_box`: `new Integer(` (OpenRewrite `UpgradeToJava21`)
- `java8_urlkit`: `new URL(` (OpenRewrite `UpgradeToJava21`)

See `LICENSES.md` for origin and license of every tree.
