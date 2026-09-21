# -*- coding: utf-8 -*-
"""course-notes helper: Automate headless browser visual and console audit for HTML lecture players."""
from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

# Force UTF-8 on Windows
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_local_server(root_dir: Path) -> tuple[socketserver.TCPServer, int]:
    handler = lambda *args, **kwargs: SilentHandler(*args, directory=str(root_dir), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def audit_single_player(html_path: Path, server_root: Path, port: int, snap_dir: Path, session_name: str) -> dict:
    rel_path = html_path.relative_to(server_root).as_posix()
    url = f"http://127.0.0.1:{port}/{urllib.parse.quote(rel_path)}"
    stem = html_path.stem.replace("_讲解视频演示", "")
    session_arg = f"-s={session_name}"
    command_errors: list[str] = []

    # 1. Open player in an isolated playwright-cli session.
    open_res = subprocess.run(
        ["playwright-cli", session_arg, "open", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if open_res.returncode != 0:
        command_errors.append(f"playwright-cli open failed: {open_res.stderr.strip() or open_res.stdout.strip()}")
    else:
        time.sleep(1.2)

    # 2. Check console log for actual JavaScript errors.
    con_res = subprocess.run(
        ["playwright-cli", session_arg, "console"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    console_errors = list(command_errors)
    if con_res.returncode != 0:
        console_errors.append(f"playwright-cli console failed: {con_res.stderr.strip() or con_res.stdout.strip()}")

    # Check if a log file was referenced
    m_log = re.search(r'([^\s]+\.log)', con_res.stdout)
    if m_log:
        log_file = Path(m_log.group(1))
        if log_file.exists():
            log_text = log_file.read_text(encoding="utf-8", errors="ignore")
            for line in log_text.splitlines():
                line = line.strip()
                if "favicon.ico" in line:
                    continue
                if any(k in line.lower() for k in ["error", "syntaxerror", "referenceerror", "typeerror", "unexpected"]):
                    console_errors.append(line)

    # Also parse direct stdout
    for line in con_res.stdout.splitlines():
        line = line.strip()
        if "favicon.ico" in line or line.startswith("###") or "Total messages" in line:
            continue
        if any(k in line.lower() for k in ["error:", "syntaxerror:", "referenceerror:", "uncaught"]):
            if line not in console_errors:
                console_errors.append(line)

    # 3. Check layout and element bounds via eval
    eval_js = """
    (() => {
      const res = { overflows: false, stageOk: false, progressOk: false, details: [] };
      if (document.documentElement.scrollWidth > window.innerWidth + 2) {
        res.overflows = true;
        res.details.push("Horizontal overflow detected: " + document.documentElement.scrollWidth + " > " + window.innerWidth);
      }
      const stage = document.querySelector('.stage-arena');
      if (stage) {
        const r = stage.getBoundingClientRect();
        if (r.width > 200 && r.height > 120) res.stageOk = true;
        else res.details.push("Stage arena dimensions too small: " + r.width + "x" + r.height);
      } else {
        res.details.push("Missing .stage-arena");
      }
      const prog = document.querySelector('.progress-bar-bg');
      if (prog) {
        const r = prog.getBoundingClientRect();
        if (r.width > 100) res.progressOk = true;
        else res.details.push("Progress bar too small: " + r.width);
      } else {
        res.details.push("Missing .progress-bar-bg");
      }
      return JSON.stringify(res);
    })()
    """
    eval_proc = subprocess.run(
        ["playwright-cli", session_arg, "eval", eval_js.strip().replace(chr(10), " ")],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    layout_info = {
        "overflows": True,
        "stageOk": False,
        "progressOk": False,
        "details": ["Unable to read layout information"]
    }
    if eval_proc.returncode != 0:
        layout_info["details"] = [f"playwright-cli eval failed: {eval_proc.stderr.strip() or eval_proc.stdout.strip()}"]
    else:
        for line in eval_proc.stdout.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    layout_info = json.loads(line)
                    break
                except Exception:
                    pass

    # 4. Save visual snapshot.
    snap_path = snap_dir / f"{stem}.png"
    snap_res = subprocess.run(
        ["playwright-cli", session_arg, "screenshot", "--filename", str(snap_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if snap_res.returncode != 0:
        console_errors.append(f"playwright-cli screenshot failed: {snap_res.stderr.strip() or snap_res.stdout.strip()}")

    passed = len(console_errors) == 0 and not layout_info.get("overflows") and layout_info.get("stageOk") and layout_info.get("progressOk")

    return {
        "stem": stem,
        "html": html_path,
        "passed": passed,
        "console_errors": console_errors,
        "layout_details": layout_info.get("details", []),
        "snapshot": snap_path if snap_path.exists() else None
    }


def main():
    parser = argparse.ArgumentParser(description="Audit HTML lecture players for visual alignment and console errors.")
    parser.add_argument("--html", help="Path to a single HTML player file")
    parser.add_argument("--chapter-dir", help="Path to a chapter directory containing section HTML players")
    parser.add_argument("--snap-dir", default="tmp/audit_snapshots", help="Directory to save visual snapshots")
    args = parser.parse_args()

    targets = []
    if args.html:
        p = Path(args.html).resolve()
        if p.exists():
            targets.append(p)
        else:
            print(f"Error: File not found: {p}", file=sys.stderr)
            return 1
    elif args.chapter_dir:
        chap = Path(args.chapter_dir).resolve()
        if not chap.exists():
            print(f"Error: Chapter dir not found: {chap}", file=sys.stderr)
            return 1
        targets = sorted(chap.glob("*/*_讲解视频演示.html"))
        if not targets:
            targets = sorted(chap.glob("*_讲解视频演示.html"))
    else:
        for c in [Path.cwd() / "第三章_栈队列和数组", Path.cwd() / "第四章_串"]:
            if c.exists():
                targets.extend(sorted(c.glob("*/*_讲解视频演示.html")))

    if not targets:
        print("No HTML players found to audit.")
        return 0

    snap_dir = Path(args.snap_dir).resolve()
    snap_dir.mkdir(parents=True, exist_ok=True)

    playwright_cli = shutil.which("playwright-cli")
    if not playwright_cli:
        print("Error: playwright-cli is not available on PATH.", file=sys.stderr)
        return 1

    server_root = Path(os.path.commonpath([str(t.parent) for t in targets]))
    session_name = f"course-notes-audit-{os.getpid()}"
    print(f"🔍 Starting visual and alignment audit for {len(targets)} players...")
    server, port = start_local_server(server_root)

    results = []
    try:
        for idx, t in enumerate(targets, 1):
            res = audit_single_player(t, server_root, port, snap_dir, session_name)
            results.append(res)
            status_symbol = "✅ PASS" if res["passed"] else "❌ FAIL"
            print(f"  [{idx}/{len(targets)}] {status_symbol} {res['stem']}")
            if not res["passed"]:
                for err in res["console_errors"]:
                    print(f"       [Console Error] {err}")
                for d in res["layout_details"]:
                    print(f"       [Layout Issue] {d}")
    finally:
        subprocess.run(
            [playwright_cli, f"-s={session_name}", "close"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        server.shutdown()
        server.server_close()

    fails = [r for r in results if not r["passed"]]
    print("\n" + "=" * 50)
    print(f"Audit Summary: {len(results) - len(fails)}/{len(results)} passed.")
    if fails:
        print(f"⚠️ {len(fails)} player(s) flagged issues. Check snapshots in: {snap_dir}")
        return 2
    else:
        print(f"🎉 All {len(results)} players verified! Zero console errors, zero layout misalignments.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
