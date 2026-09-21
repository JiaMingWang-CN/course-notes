#!/usr/bin/env python3
"""Export cookies from a logged-in playwright-cli browser session to a
Netscape-format cookies.txt usable by yt-dlp (--cookies).

Run only with the user's consent — the file contains their login credentials.

Usage:
  python export_cookies.py <output-file> [--domain bilibili.com]

The playwright-cli session must exist and be logged in to the target site.
Cookie values and the output path are never printed; only a count is shown.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Windows pipes default to a legacy codepage; force UTF-8 for consistent output.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PLAYWRIGHT_CLI = shutil.which("playwright-cli") or "playwright-cli"


def main() -> int:
    ap = argparse.ArgumentParser(prog="export_cookies")
    ap.add_argument("outfile", help="Path of the Netscape cookies file to write")
    ap.add_argument("--domain", type=str, default="bilibili.com", help="Cookie domain filter (default: bilibili.com)")
    args = ap.parse_args()

    proc = subprocess.run(
        [PLAYWRIGHT_CLI, "--raw", "cookie-list"] + (["--domain=" + args.domain] if args.domain else []),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"ERROR: playwright-cli failed: {proc.stderr.strip()}", file=sys.stderr)
        print("Hint: open a browser session first (playwright-cli open) and log in.", file=sys.stderr)
        return 2

    line_re = re.compile(r"^(.+?)=(.*) \(domain: ([^,]+), path: (.*)\)$")

    rows = []
    for line in proc.stdout.splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        name, value, domain, path = m.groups()
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        rows.append(f"{domain}\t{flag}\t{path}\tTRUE\t0\t{name}\t{value}")

    if not rows:
        print("ERROR: no cookies found in the playwright-cli session.", file=sys.stderr)
        return 2

    out = Path(args.outfile)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("# Netscape HTTP Cookie File\n" + "\n".join(rows) + "\n", encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    print(f"exported {len(rows)} cookies (output path not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
