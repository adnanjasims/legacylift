"""Python 2.7-compatible helper scripts copied into the sandbox workspace."""

PROBE_PY = r"""from __future__ import print_function

import inspect
import json
import os
import sys
import traceback

ROOT = os.getcwd()
sys.path.insert(0, ROOT)

SKIP_NAMES = {"run_tests.py", "_probe.py"}


def jsonable(value):
    try:
        loaded = json.loads(json.dumps(value))
        return loaded == value
    except (TypeError, ValueError, OverflowError):
        return False


def candidates(n):
    scalars = [0, 1, 2, 10, "", "a"]
    if n == 0:
        return [()]
    if n == 1:
        return [(x,) for x in scalars] + [({"a": 1},), ("x:y",)]
    if n == 2:
        return [
            (0, 0),
            (1, 2),
            (10, 8),
            (10, 100),
            (2, 3),
            ({"a": 1}, "a"),
            ({"a": 1}, "z"),
        ]
    return []


def module_names():
    names = []
    for fname in os.listdir(ROOT):
        if not fname.endswith(".py"):
            continue
        if fname.startswith("test_") or fname in SKIP_NAMES:
            continue
        names.append(fname[:-3])
    return names


observations = []
for modname in module_names():
    try:
        mod = __import__(modname)
    except Exception:
        observations.append({
            "module": modname,
            "function": None,
            "error": traceback.format_exc(),
        })
        continue
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("_"):
            continue
        if getattr(obj, "__module__", None) != modname:
            continue
        try:
            spec = inspect.getargspec(obj)
            n = len(spec.args)
        except Exception:
            continue
        for args in candidates(n):
            rec = {
                "module": modname,
                "function": name,
                "args": list(args),
            }
            try:
                got = obj(*args)
                if isinstance(got, tuple):
                    got = list(got)
                if jsonable(got):
                    rec["status"] = "ok"
                    rec["result"] = got
                else:
                    rec["status"] = "skip"
            except Exception:
                rec["status"] = "raise"
                rec["exc_type"] = sys.exc_info()[0].__name__
            observations.append(rec)

print(json.dumps({"observations": observations}))
"""

RUN_TESTS_PY = r"""from __future__ import print_function

import json
import sys
import unittest


class JsonResult(unittest.TestResult):
    def __init__(self):
        unittest.TestResult.__init__(self)
        self.records = []

    def addSuccess(self, test):
        unittest.TestResult.addSuccess(self, test)
        self.records.append({"id": test.id(), "status": "pass"})

    def addFailure(self, test, err):
        unittest.TestResult.addFailure(self, test, err)
        self.records.append({
            "id": test.id(),
            "status": "fail",
            "detail": self._exc_info_to_string(err, test),
        })

    def addError(self, test, err):
        unittest.TestResult.addError(self, test, err)
        self.records.append({
            "id": test.id(),
            "status": "error",
            "detail": self._exc_info_to_string(err, test),
        })


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(".", pattern="test_char_*.py")
    result = JsonResult()
    suite.run(result)
    payload = {
        "records": result.records,
        "tests_run": result.testsRun,
        "failed": len(result.failures),
        "errors": len(result.errors),
    }
    print(json.dumps(payload))
    if result.failures or result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
"""
