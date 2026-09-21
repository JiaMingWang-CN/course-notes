#!/usr/bin/env python3
"""Interactively select an existing Fish Audio voice and write local .env settings.

Voice creation intentionally remains on https://fish.audio/zh-CN/app/my-voices/.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import webbrowser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CREATE_VOICE_URL = "https://fish.audio/zh-CN/app/my-voices/"
LANGUAGES = [
    ("zh-CN", "中文（普通话）"),
    ("zh-TW", "中文（繁体）"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
]


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value and value[0] in "\"'" and value[-1:] == value[0]:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pending = dict(updates)
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else ""
        if key in pending:
            output.append(f"{key}={pending.pop(key)}")
        else:
            output.append(line)
    if output and output[-1]:
        output.append("")
    output.extend(f"{key}={value}" for key, value in pending.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def field(obj: object, *names: str, default: str = "") -> str:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return str(obj[name])
        value = getattr(obj, name, None)
        if value is not None:
            if isinstance(value, (list, tuple)):
                return ", ".join(map(str, value))
            return str(value)
    return default


def choose_language(current: str) -> str:
    print("\n选择语种（用于筛选音色；合成时仍会自动识别文本语言）：")
    for index, (code, label) in enumerate(LANGUAGES, 1):
        marker = " *" if code == current else ""
        print(f"  {index}. {label} [{code}]{marker}")
    print("  0. 输入其他语言代码")
    raw = input(f"选择 [{current or 'zh-CN'}]: ").strip()
    if not raw:
        return current or "zh-CN"
    if raw == "0":
        return input("语言代码（例如 pt-BR）: ").strip() or current or "zh-CN"
    try:
        index = int(raw)
        if not 1 <= index <= len(LANGUAGES):
            raise ValueError
        return LANGUAGES[index - 1][0]
    except (ValueError, IndexError):
        raise ValueError("无效的语种选项")


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Fish Audio narration without creating voices through this project.")
    parser.add_argument("--env-file", default=".env", help="Local environment file to update (default: .env)")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    existing = read_env(env_path)
    language = choose_language(existing.get("FISH_AUDIO_LANGUAGE", "zh-CN"))

    print("\n音色来源：")
    print("  1. 我在 Fish Audio 创建/收藏的音色")
    print("  2. 搜索公开音色")
    print("  3. 前往 Fish Audio 创建新声音（本项目不负责创建）")
    source = input("选择 [1]: ").strip() or "1"
    if source == "3":
        print(f"请在网页完成创建：{CREATE_VOICE_URL}")
        try:
            webbrowser.open(CREATE_VOICE_URL)
        except Exception:
            pass
        print("创建完成后重新运行本脚本，即可选择新声音。")
        return 0
    if source not in {"1", "2"}:
        print("错误：无效的音色来源。", file=sys.stderr)
        return 2

    api_key = os.environ.get("FISH_API_KEY") or existing.get("FISH_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Fish Audio API Key（输入不会回显）: ").strip()
    if not api_key:
        print("错误：API Key 不能为空。", file=sys.stderr)
        return 2

    query: dict[str, object] = {
        "page_size": 50,
        "page_number": 1,
        "language": language,
        "self": "true" if source == "1" else "false",
    }
    if source == "2":
        title = input("按名称搜索（留空则显示热门音色）: ").strip()
        if title:
            query["title"] = title

    request = Request(
        "https://api.fish.audio/model?" + urlencode(query),
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            page = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"错误：读取 Fish Audio 音色失败（HTTP {exc.code}）：{detail}", file=sys.stderr)
        return 1
    except (URLError, ValueError) as exc:
        print(f"错误：读取 Fish Audio 音色失败：{exc}", file=sys.stderr)
        return 1

    voices = list(page.get("items", []) or [])
    if not voices:
        print("没有找到符合条件的音色。可更换语种/搜索词，或前往创建：")
        print(CREATE_VOICE_URL)
        return 1

    print("\n可用音色：")
    for index, voice in enumerate(voices, 1):
        voice_id = field(voice, "id", "_id")
        title = field(voice, "title", "name", default="未命名")
        voice_languages = field(voice, "languages", "language", default=language)
        print(f"  {index:>2}. {title} [{voice_languages}]  {voice_id}")

    raw_choice = input("选择音色编号: ").strip()
    try:
        selected_index = int(raw_choice)
        if not 1 <= selected_index <= len(voices):
            raise ValueError
        selected = voices[selected_index - 1]
    except (ValueError, IndexError):
        print("错误：无效的音色编号。", file=sys.stderr)
        return 2
    voice_id = field(selected, "id", "_id")
    if not voice_id:
        print("错误：所选音色缺少 ID。", file=sys.stderr)
        return 1

    update_env(env_path, {
        "TTS_PROVIDER": "fish_audio",
        "FISH_API_KEY": api_key,
        "FISH_AUDIO_LANGUAGE": language,
        "FISH_AUDIO_VOICE_ID": voice_id,
        "FISH_AUDIO_MODEL": existing.get("FISH_AUDIO_MODEL", "s2.1-pro-free"),
        "FISH_AUDIO_SPEED": existing.get("FISH_AUDIO_SPEED", "1.0"),
    })
    print(f"\n✅ 已保存到 {env_path}（请勿提交该文件）")
    print(f"已选择：{field(selected, 'title', 'name', default='未命名')} · {voice_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
