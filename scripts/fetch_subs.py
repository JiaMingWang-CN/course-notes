#!/usr/bin/env python3
"""course-notes helper: fetch Bilibili ai-zh subtitles for selected episodes.

Usage:
  python fetch_subs.py <BV-id-or-URL> --list
  python fetch_subs.py <BV-id-or-URL> --ps 20-32 [--cookies FILE] [--out-dir DIR]

--list prints the full episode table (P number | title) using the public view
API, no login needed. --ps downloads the ai-zh AI subtitle for each episode
(using a login cookie when available) and converts each .srt/.vtt into a cleaned
P{p}.txt transcript with [MM:SS] stamps.

Cookie policy: if --cookies is omitted, the last saved path (from
~/.config/course-notes.json) is reused; on success the path is saved again.
--forget-cookies clears the saved path. Public subtitles are attempted when no
cookie is available; incomplete retrieval is reported without assuming that
authentication is the only possible cause.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

# Windows pipes default to a legacy codepage; force UTF-8 so Chinese titles survive.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

YTDLP = shutil.which("yt-dlp") or "yt-dlp"

VIEW_API = "https://api.bilibili.com/x/web-interface/view?bvid={}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
STATE_FILE = Path.home() / ".config" / "course-notes.json"
TS_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*\d{1,2}:\d{2}:\d{2}")
TAG_RE = re.compile(r"<[^>]+>")
BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass


def extract_bvid(source: str) -> str:
    m = BV_RE.search(source)
    if not m:
        raise SystemExit(f"ERROR: no BV id found in {source!r}")
    return m.group(0)


def list_episodes(bvid: str) -> list[dict]:
    req = Request(VIEW_API.format(bvid), headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise SystemExit(f"ERROR: view API returned code={data.get('code')} message={data.get('message')}")
    return [
        {"page": p["page"], "title": p["part"], "cid": p["cid"]}
        for p in data["data"]["pages"]
    ]


def parse_ps(spec: str, total: int) -> list[int]:
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(chunk))
    return sorted(p for p in out if 1 <= p <= total)


def run_ytdlp(
    bvid: str,
    p: int,
    cookies: str | None,
    out_dir: Path,
    download_video: bool = False,
    video_quality: str = "480",
) -> subprocess.CompletedProcess[str]:
    url = f"https://www.bilibili.com/video/{bvid}/?p={p}"
    cmd = [
        YTDLP,
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "ai-zh", "--no-playlist", "--quiet", "--no-warnings",
        "-o", str(out_dir / f"P{p}.%(ext)s"),
    ]
    if download_video:
        target_res = "1080" if video_quality == "best" else video_quality
        cmd.extend([
            "-f", f"b[height<={target_res}]/bv*[height<={target_res}]+ba/worst",
            "--merge-output-format", "mp4",
        ])
    else:
        cmd.append("--skip-download")

    if cookies:
        cmd[2:2] = ["--cookies", cookies]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def find_sub(out_dir: Path, p: int) -> Path | None:
    for pattern in (f"P{p}*.ai-zh.srt", f"P{p}*.ai-zh.vtt", f"P{p}*.srt", f"P{p}*.vtt"):
        hits = sorted(out_dir.glob(pattern))
        if hits:
            return hits[0]
    return None


def find_video(out_dir: Path, p: int) -> Path | None:
    for pattern in (f"P{p}.mp4", f"P{p}.mkv", f"P{p}.webm", f"P{p}*.mp4"):
        hits = sorted(out_dir.glob(pattern))
        if hits:
            return hits[0]
    return None


def sub_to_text(sub_path: Path, txt_path: Path) -> int:
    lines = sub_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    segments: list[tuple[float, str]] = []
    i = 0
    while i < len(lines):
        m = TS_RE.match(lines[i])
        if not m:
            i += 1
            continue
        h, mm, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        start = h * 3600 + mm * 60 + s
        i += 1
        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip() and not TS_RE.match(lines[i]):
            cleaned = TAG_RE.sub("", lines[i]).strip()
            if cleaned:
                text_lines.append(cleaned)
            i += 1
        text = " ".join(text_lines).strip()
        if text:
            segments.append((start, text))
    # drop consecutive duplicates (common in rolling auto-subs)
    deduped: list[tuple[float, str]] = []
    for start, text in segments:
        if deduped and text == deduped[-1][1]:
            continue
        deduped.append((start, text))
    stamp = lambda t: f"[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}]" if t >= 3600 else f"[{t // 60:02d}:{t % 60:02d}]"
    txt_path.write_text("\n".join(f"{stamp(t)} {text}" for t, text in deduped), encoding="utf-8")
    return len(deduped)


def main() -> int:
    ap = argparse.ArgumentParser(prog="fetch_subs", description="Fetch Bilibili ai-zh subtitles per episode")
    ap.add_argument("source", help="BV id or Bilibili video URL")
    ap.add_argument("--list", action="store_true", help="List episodes only (public API, no login)")
    ap.add_argument("--ps", type=str, default=None, help="Episodes, e.g. 20-32 or 20,21,25")
    ap.add_argument("--cookies", type=str, default=None, help="Netscape-format cookies.txt (default: reuse saved path)")
    ap.add_argument("--out-dir", type=str, default=None, help="Output directory (default: tmp/subs)")
    ap.add_argument("--download-video", action="store_true", help="Also download low-res video (e.g. 360p/480p) for multimodal understanding")
    ap.add_argument("--video-quality", type=str, default="480", choices=["360", "480", "720", "best"], help="Target video resolution (default: 480)")
    ap.add_argument("--forget-cookies", action="store_true", help="Forget the saved cookie path")
    args = ap.parse_args()

    if args.forget_cookies:
        state = load_state()
        state.pop("last_cookie_path", None)
        save_state(state)
        print("cookie path forgotten")
        return 0

    bvid = extract_bvid(args.source)

    if args.list:
        episodes = list_episodes(bvid)
        for ep in episodes:
            print(f"P{ep['page']}\t{ep['title']}")
        return 0

    if not args.ps:
        raise SystemExit("ERROR: --ps is required unless --list")
    if shutil.which("yt-dlp") is None:
        print("ERROR: yt-dlp is not available on PATH.", file=sys.stderr)
        return 1

    cookies = args.cookies or load_state().get("last_cookie_path")
    if cookies and not Path(cookies).exists():
        print("[warn] Cookie file not found; ignoring the unavailable path.", file=sys.stderr)
        cookies = None
    if not cookies:
        # Auto-discover in typical workspace & config locations
        candidates = [
            Path.cwd() / "tmp" / ".playwright-cli" / "bilibili_cookies.txt",
            Path.cwd() / "tmp" / "bilibili_cookies.txt",
            Path.cwd() / ".playwright-cli" / "bilibili_cookies.txt",
            Path.cwd() / "bilibili_cookies.txt",
            Path.cwd() / "cookies.txt",
            Path.home() / ".config" / "bilibili_cookies.txt",
        ]
        for cand in candidates:
            if cand.exists() and cand.stat().st_size > 50:
                cookies = str(cand.resolve())
                print("[info] Auto-discovered a local Cookie file (path not printed).")
                break

    if not cookies:
        print("[info] No cookie file found; trying publicly available subtitles.")

    out_dir = Path(args.out_dir or (Path.cwd() / "tmp" / "subs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    episodes = list_episodes(bvid)
    titles = {ep["page"]: ep["title"] for ep in episodes}
    try:
        targets = parse_ps(args.ps, len(episodes))
    except ValueError as exc:
        print(f"ERROR: invalid --ps value {args.ps!r}: {exc}", file=sys.stderr)
        return 2
    if not targets:
        print(f"ERROR: --ps selected no episodes in the valid range 1-{len(episodes)}.", file=sys.stderr)
        return 2

    ok, no_sub, failed = [], [], []
    for p in targets:
        proc = run_ytdlp(
            bvid, p, cookies, out_dir,
            download_video=args.download_video,
            video_quality=args.video_quality,
        )
        if proc.returncode != 0:
            failed.append(p)
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            summary = detail[-1] if detail else "yt-dlp failed without an error message"
            print(f"P{p}\tDOWNLOAD-FAIL\t{summary}\t{titles.get(p, '')}")
            continue
        sub = find_sub(out_dir, p)
        video_file = find_video(out_dir, p) if args.download_video else None
        video_tag = f"\tvideo: {video_file.name}" if video_file else ("\tvideo: MISSING" if args.download_video else "")
        if sub is None:
            no_sub.append(p)
            print(f"P{p}\tNO-SUB{video_tag}\t{titles.get(p, '')}")
            continue
        n = sub_to_text(sub, out_dir / f"P{p}.txt")
        if n == 0:
            no_sub.append(p)
            print(f"P{p}\tEMPTY-SUB{video_tag}\t{titles.get(p, '')}")
            continue
        ok.append(p)
        print(f"P{p}\tOK\t{n} lines{video_tag}\t{titles.get(p, '')}")

    if cookies:
        state = load_state()
        state["last_cookie_path"] = str(Path(cookies).resolve())
        save_state(state)

    if failed or no_sub:
        print(f"Subtitle retrieval incomplete. Download failures: {failed}; missing/empty subtitles: {no_sub}. "
              "Check network access, subtitle availability, and Cookie validity when authentication is required.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
