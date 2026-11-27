#!/usr/bin/env python3
"""
PinhOS Host-Side App Contract & Policy Validator (scripts/check_app.py)
Validates one or more PinhOS app .py files on PC using the exact same APP_META
and static policy rules enforced on-device by core/sandbox.py.

Usage:
  python3 scripts/check_app.py apps/wifi_spectrum.py
  python3 scripts/check_app.py apps/ docs/templates/app_template.py
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.sandbox import inspect_app, SandboxError  # noqa: E402


def _collect_targets(args):
    if not args:
        args = [
            os.path.join(REPO_ROOT, "apps"),
            os.path.join(REPO_ROOT, "docs", "templates", "app_template.py"),
        ]
    files = []
    for a in args:
        p = a if os.path.isabs(a) else os.path.join(REPO_ROOT, a)
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.endswith(".py") and not fn.startswith("_"):
                    files.append(os.path.join(p, fn))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("[FAIL] Not found: {}".format(a))
            return None
    return files


def check_file(path):
    rel = os.path.relpath(path, REPO_ROOT)
    # 1. Python syntax check
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        compile(src, rel, "exec")
    except SyntaxError as e:
        print("[FAIL] {} -> SyntaxError L{}: {}".format(rel, e.lineno, e.msg))
        return False
    except Exception as e:
        print("[FAIL] {} -> Read error: {}".format(rel, e))
        return False

    # 2. Strict PinhOS APP_META + OS Safety Policy check (identical to on-device core/sandbox.py)
    try:
        meta = inspect_app(path, strict=True)
    except SandboxError as e:
        print("[FAIL] {} -> {}: {}".format(rel, type(e).__name__, e))
        return False

    print("[PASS] {} -> id={} v{} min_sram={}K blk={}K radio={}".format(
        rel,
        meta["id"],
        meta["version"],
        meta["min_sram"] // 1024,
        meta.get("min_block", 16384) // 1024,
        bool(meta.get("needs_radio", False)),
    ))
    return True


def main():
    files = _collect_targets(sys.argv[1:])
    if not files:
        sys.exit(1)
    ok_all = True
    for fp in files:
        if not check_file(fp):
            ok_all = False
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
