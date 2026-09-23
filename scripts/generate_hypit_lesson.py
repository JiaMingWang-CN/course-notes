#!/usr/bin/env python3
"""course-notes helper: Generate Hypit video assets and interactive lecture player from lesson notes.

Usage:
  # Single note:
  python generate_hypit_lesson.py --note <path-to-note.md> [--out-dir <video-prod-dir>] [--html-dest <chapter-dir>]

  # Batch whole chapter:
  python generate_hypit_lesson.py --chapter-dir <path-to-chapter-folder>

This script bridges course-notes text notes and Hypit visual production:
1. Deeply parses 408 positioning, core concepts, formulas, code snippets, and traps.
2. Scaffolds Hypit production assets: BRIEF.md, TREATMENT.md, SCRIPT.md, STORYBOARD.md.
3. Automatically generates a standalone, responsive HTML5 lecture player:
   - Audio-driven progress, subtitles, and scene changes
   - Note-derived concept progression instead of unrelated preset animations
   - Fish Audio or Web Speech API narration
   - Independent lesson playback and hands-on review controls
"""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Force UTF-8 on Windows
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_user_profile(start_dir: Path | None = None) -> dict | None:
    """Load user profile from <workspace_root>/user-profile/PROFILE.md if present.

    Returns None if user-profile does not exist or cannot be parsed, enabling smooth soft fallback.
    """
    cur = (start_dir or Path.cwd()).resolve()
    while cur.parent != cur:
        prof_file = cur / "user-profile" / "PROFILE.md"
        if prof_file.is_file():
            try:
                text = prof_file.read_text(encoding="utf-8")
                profile = {
                    "school": "全国统考",
                    "exam": "408 计算机学科专业基础",
                    "major": "0812 计科 / 0854 软工",
                    "lang": "C/C++",
                    "stage": "强化冲刺",
                    "ui_style": "calm_textbook",
                    "days_remaining": 90,
                    "school_trap": ""
                }
                m_school = re.search(r"🎯\s*\*\*目标院校\*\*[：:]\s*(.+)", text)
                if m_school:
                    profile["school"] = m_school.group(1).strip()
                m_exam = re.search(r"📚\s*\*\*考试科目\*\*[：:]\s*(.+)", text)
                if m_exam:
                    profile["exam"] = m_exam.group(1).strip()
                m_major = re.search(r"🎓\s*\*\*报考专业/方向\*\*[：:]\s*(.+)", text)
                if m_major:
                    profile["major"] = m_major.group(1).strip()
                m_lang = re.search(r"💻\s*\*\*代码偏好\*\*[：:]\s*(.+)", text)
                if m_lang:
                    profile["lang"] = m_lang.group(1).strip()
                m_stage = re.search(r"⏳\s*\*\*备考阶段\*\*[：:]\s*(.+)", text)
                if m_stage:
                    profile["stage"] = m_stage.group(1).strip()
                m_style = re.search(r"🎨\s*\*\*微课UI美学风格\*\*[：:]\s*.*?`([a-z_]+)`", text)
                if m_style:
                    profile["ui_style"] = m_style.group(1).strip()
                else:
                    m_style2 = re.search(r"\|\s*\*\*ui_style\*\*\s*\|\s*`([a-z_]+)`", text)
                    if m_style2:
                        profile["ui_style"] = m_style2.group(1).strip()
                m_days = re.search(r"剩余\s*\*\*(\d+)\*\*\s*天", text)
                if m_days:
                    profile["days_remaining"] = int(m_days.group(1))

                intel_file = cur / "user-profile" / "EXAM_INTELLIGENCE.md"
                if intel_file.is_file():
                    intel_text = intel_file.read_text(encoding="utf-8")
                    m_trap = re.search(r"(?:易错点参考|命题人高频挖坑点)[：\s\*\n]+>\s*(.+)", intel_text)
                    if m_trap:
                        profile["school_trap"] = m_trap.group(1).strip()
                return profile
            except Exception:
                pass
        if (cur / ".agents").is_dir():
            break
        cur = cur.parent
    return None


def parse_note(note_text: str) -> dict:
    """Parse lesson note markdown to extract structural sections and semantic items."""
    data = {
        "title": "",
        "section_id": "",
        "clean_title": "",
        "exam_role": "",
        "core_points": [],
        "traps": [],
        "formulas": [],
        "code_blocks": [],
        "quick_tips": [],
        "topic_type": "generic",
        "raw": note_text
    }

    lines = note_text.splitlines()
    for line in lines:
        line_s = line.strip()
        if line_s.startswith("# ") and not data["title"]:
            full_title = line_s[2:].strip()
            data["title"] = full_title
            m = re.match(r"^([\d\.]+)\s*(.*)", full_title)
            if m:
                data["section_id"] = m.group(1).rstrip("._")
                data["clean_title"] = m.group(2).strip()
            else:
                data["clean_title"] = full_title
            break

    # Determine topic type for visual stage customization
    title_lower = (data["title"] + " " + data["clean_title"]).lower()
    if "栈" in title_lower or "stack" in title_lower:
        data["topic_type"] = "stack"
    elif "队" in title_lower or "queue" in title_lower:
        data["topic_type"] = "queue"
    elif any(k in title_lower for k in ("串", "kmp", "string", "next", "模式匹配")):
        data["topic_type"] = "string_kmp"
    elif any(k in title_lower for k in ("矩阵", "压缩", "matrix", "数组")):
        data["topic_type"] = "matrix"
    else:
        data["topic_type"] = "algorithm"

    # Extract 408 Positioning
    m_pos = re.search(r"##\s*一、本节在.*?中的定位\s*\n+([\s\S]*?)(?=\n##|\Z)", note_text)
    if m_pos:
        data["exam_role"] = m_pos.group(1).strip()

    # Extract Code Blocks
    code_matches = re.findall(r"```([a-zA-Z]*)\n([\s\S]*?)```", note_text)
    for lang, code in code_matches:
        if len(code.strip()) > 30:
            data["code_blocks"].append({"lang": lang or "c", "code": code.strip()})

    # Extract core points headings
    points = re.findall(r"###\s*(\d+[\.、].*?)\n+([\s\S]*?)(?=\n###|\n##|\Z)", note_text)
    for p_title, p_content in points:
        data["core_points"].append({
            "title": p_title.strip(),
            "content": p_content.strip()
        })

    # If no ### found, try ## 二、核心知识点 subsections
    if not data["core_points"]:
        m_core = re.search(r"##\s*(?:二、核心知识点|核心知识点)\s*\n+([\s\S]*?)(?=\n##|\Z)", note_text)
        if m_core:
            paras = [p.strip() for p in m_core.group(1).split("\n\n") if p.strip()]
            for idx, para in enumerate(paras[:4], 1):
                first_line = para.splitlines()[0].strip("-* \t#")
                data["core_points"].append({
                    "title": first_line[:30],
                    "content": para[:250]
                })

    # Extract traps
    m_traps = re.search(r"##\s*(?:四、易错点|三、易错点|易错点与辨析|易错点与高频陷阱)[\s\S]*?\n+([\s\S]*?)(?=\n##|\Z)", note_text)
    if m_traps:
        trap_lines = [l.strip("-* \t") for l in m_traps.group(1).splitlines() if l.strip().startswith(("-", "*", "1.", "2.", "3.", "4.", "5."))]
        data["traps"] = trap_lines[:5]

    # Extract formulas / math lines
    math_matches = re.findall(r"\$\$([\s\S]*?)\$\$|\$([^\$\n]+)\$", note_text)
    for m_block, m_inline in math_matches:
        formula = (m_block or m_inline).strip()
        if len(formula) > 3 and formula not in data["formulas"]:
            data["formulas"].append(formula)

    # Extract quick tips / 30s summary if present
    m_quick = re.search(r"##\s*(?:六、30秒速记|五、408典型考法|小结)[\s\S]*?\n+([\s\S]*?)(?=\n##|\Z)", note_text)
    if m_quick:
        q_lines = [l.strip("-* \t") for l in m_quick.group(1).splitlines() if l.strip()]
        data["quick_tips"] = q_lines[:4]

    return data


def generate_brief(info: dict, profile: dict | None = None) -> str:
    role_snippet = info.get("exam_role") or "以笔记中的学习目标与适用范围为准"
    if len(role_snippet) > 200:
        role_snippet = role_snippet[:200] + "..."

    school_name = profile["school"] if profile else "全国统考"
    exam_name = profile["exam"] if profile else "408 计算机学科专业基础"
    days_str = f"，距离初试仅剩 {profile['days_remaining']} 天" if profile else ""

    return f"""# Production Brief: {info['title']} ({school_name} · {exam_name} 专项精讲)

## 一、用户委托与创作目标
* **委托人目标**：针对【{school_name} - {exam_name}】定制冲刺备考{days_str}，复习时间极其紧迫。
* **核心诉求**：采用直观、重点突出的讲授方式，减少冗余铺垫，以 **3 ~ 5 分钟** 为目标讲清《{info['title']}》的核心内容；内容过密时应拆分而非省略必要条件。
* **交付物标准**：
  1. Hypit 制作简报与导演方案（Brief & Treatment）；
  2. 视听分镜脚本与专业口播稿（Script & Storyboard）；
  3. 可独立在浏览器运行的动态交互微课播放器（HTML5 Player）。

## 二、不可妥协的考点硬性事实
1. **考纲定位**：{role_snippet}
2. **核心概念与公式**：忠于输入笔记，保留公式的变量含义和适用条件。
3. **避坑要求**：对笔记中已有依据的易错点（如边界条件、指针回溯、操作区别）给出明确提醒。
"""


def generate_treatment(info: dict, profile: dict | None = None) -> str:
    school_name = profile["school"] if profile else "408 统考"
    exam_name = profile["exam"] if profile else "408 计算机学科专业基础"
    style_desc = "温和教材 (Calm Textbook) · 暖白浅灰绿、深墨绿重点与少量琥珀提醒"

    return f"""# Production Treatment: {info['title']} (导演方案)

> **视听与教学风格参考**：[STYLE_PROFILE.md](../references/STYLE_PROFILE.md)（若本章节未建立该文件，则采用播放器默认主题）

## 一、艺术指导与调性设计
* **风格定位**：{school_name} · {exam_name} 重点复习课，节奏紧凑、表达清晰；实际语速以最终口播为准。
* **微课 UI 视觉主题**：【{style_desc}】
  * 暖白、浅灰绿作为大面积背景，深墨绿承载标题、导航与播放控制；
  * 琥珀色仅用于易错提醒；卡片使用适度圆角、细边框和轻浅底色，不使用厚重阴影、玻璃效果或复杂渐变；
  * 中文标题清晰有分量，正文舒展；数值、下标、时间使用等宽字体；
  * 未访问、已访问、当前访问同时通过颜色、文字状态与读数区分。
* **听觉系统**：由真实音频播放进度驱动画面和字幕；一段结束后立即衔接下一段，不以固定秒数制造空白。使用 Fish Audio 时，字幕保持干净，另行生成带局部情绪、重音和停顿提示的教师式表演文本：导入温暖自信、概念解释平静清楚、易错提醒压低且严肃、总结温暖鼓励。

## 二、四大镜头子系统
1. **内容演示系统**：只展示从本节笔记提取的概念与步骤，不套用无关算法动画；
2. **公式与卡片系统**：核心结论卡片同时标注适用条件；
3. **易错提醒系统**：使用少量琥珀色和明确文字解释失败条件；
4. **独立动手演示**：课程播放与手动逐项查看互不抢占状态，按钮直接说明操作。
"""


def generate_script(info: dict, profile: dict | None = None) -> str:
    school_name = profile["school"] if profile else "全国"
    exam_name = profile["exam"] if profile else "408 统考"
    days_note = f"，距离考试仅剩 {profile['days_remaining']} 天" if profile else ""
    speaker = f"{school_name} 备考课程讲师" if profile and school_name != "全国统考" else "课程讲师"

    points_text = ""
    for i, p in enumerate(info["core_points"][:4], 1):
        clean_content = _clean_spoken_text(p['content'])[:140]
        points_text += f"""
### Segment {i+1}: {p['title']}
**【讲师口播】**：
重点来看【{p['title']}】。{clean_content}……这里需要结合定义和适用条件理解，避免只记结论！
`[画面：当前知识点进入“当前访问”状态，标题、正文和访问读数与本段口播同步]`
"""

    traps_list = list(info.get('traps', [])[:3])
    if profile and profile.get("school_trap"):
        traps_list.insert(0, f"【{school_name}专属考情】{profile['school_trap'][:80]}")
    traps_text = "\n".join([f"- 警示 {i+1}：{t[:80]}" for i, t in enumerate(traps_list[:3])])
    if not traps_text:
        traps_text = "- 警示 1：注意边界条件的判断与指针越界检查；\n- 警示 2：注意时间复杂度与空间复杂度的计算陷阱。"

    return f"""# Spoken Script: {info['title']}

> **主讲人**：{speaker}
> **目标时长**：约 3 分 30 秒
> **格式说明**：`[画面]` 为画面提示；正文是干净字幕。Fish Audio 启用时，生成器会另建不显示给学习者的表演文本，加入方括号情绪提示、局部 `[emphasis]` 与 `[pause]`。

---

### Segment 1: 开门见山，定位与核心概念（00:00 - 00:40）
**【讲师口播】**：
各位备考【{school_name} · {exam_name}】的同学大家好！{days_note}，今天我们进入【{info['title']}】的高能精讲。
很多同学在复习时容易在这里死记硬背，但其实一句话就能抓住本质！
`[画面：全景浮现章节标题，随后平滑过渡到动态数据结构演示舞台]`
在统考与自命题真题中，本节的命题核心是考查它的逻辑原理、实现细节与实际运算。
我们通过接下来的动态推演，带大家 3 分钟彻底攻克！

---
{points_text}

---

### Segment 末尾: 考前避坑与考点收敛（03:00 - 03:30）
**【讲师口播】**：
最后，我们快速盘点本小节的核心避坑清单：
{traps_text}
请结合适用条件回顾这些核心规律，并通过例题检查是否真正掌握。我们下一小节再见！
`[画面：全景总结卡片依次点亮打勾，定音符收尾]`
"""


def generate_storyboard(info: dict, profile: dict | None = None) -> str:
    school_name = profile["school"] if profile else "408"
    exam_name = profile["exam"] if profile else "408 统考"
    return f"""# Storyboard: {info['title']} (分镜脚本)

| 镜头号 | 时间区间 | 景别 / 布局 | 画面视觉元素与动效 | 口播内容概要 |
|:---:|:---:|---|---|---|
| **SC-01** | 随音频 | 全景 / 教材式工作台 | 暖白页面呈现《{info['title']}》与【{school_name} · {exam_name}】学习定位 | 章节引入与目标 |
| **SC-02** | 随音频 | 内容卡片 | 从笔记提取的第一个核心知识点进入“当前讲解”状态，读数同步更新 | 对应知识点口播 |
| **SC-03** | 随音频 | 连续步骤 | 后续知识点依次由“未访问”变为“当前访问”“已访问”，画面内容与当前口播一致 | 核心内容逐项讲解 |
| **SC-04** | 随音频 | 琥珀提醒卡 | 展示笔记中的易错点及判断条件，不播放无关算法仿真 | 易错点与适用条件 |
| **SC-05** | 随音频 | 回顾卡片 | 已讲知识点统一标为完成，并显示完成读数 | 全节回顾 |
"""


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a small dotenv file without adding a mandatory dependency."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] in "\"'" and value[-1:] == value[0]:
            value = value[1:-1]
        values[key] = value
    return values


def load_tts_config(start_dir: Path, env_file: Path | None = None) -> dict[str, object]:
    """Load TTS settings, with process environment variables taking precedence."""
    candidates: list[Path] = []
    if env_file:
        resolved_env_file = env_file.resolve()
        if not resolved_env_file.is_file():
            raise FileNotFoundError(f"Environment file not found: {resolved_env_file}")
        candidates.append(resolved_env_file)
    else:
        cur = start_dir.resolve()
        while True:
            candidates.append(cur / ".env")
            if cur.parent == cur:
                break
            cur = cur.parent
        candidates.extend((Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"))

    file_values: dict[str, str] = {}
    for candidate in candidates:
        if candidate.is_file():
            file_values = _read_env_file(candidate)
            break

    values = {**file_values, **os.environ}
    provider = values.get("TTS_PROVIDER", "browser").strip().lower()
    if provider not in {"browser", "fish_audio"}:
        raise ValueError("TTS_PROVIDER must be 'browser' or 'fish_audio'")

    config: dict[str, object] = {
        "provider": provider,
        "language": values.get("FISH_AUDIO_LANGUAGE", "zh-CN").strip() or "zh-CN",
    }
    if provider == "fish_audio":
        api_key = values.get("FISH_API_KEY", "").strip()
        voice_id = values.get("FISH_AUDIO_VOICE_ID", "").strip()
        if not api_key:
            raise ValueError("TTS_PROVIDER=fish_audio requires FISH_API_KEY in the environment or .env")
        if not voice_id:
            raise ValueError("TTS_PROVIDER=fish_audio requires FISH_AUDIO_VOICE_ID in the environment or .env")
        try:
            speed = float(values.get("FISH_AUDIO_SPEED", "1.0"))
        except ValueError as exc:
            raise ValueError("FISH_AUDIO_SPEED must be a number from 0.5 to 2.0") from exc
        if not 0.5 <= speed <= 2.0:
            raise ValueError("FISH_AUDIO_SPEED must be between 0.5 and 2.0")
        config.update({
            "api_key": api_key,
            "voice_id": voice_id,
            "model": values.get("FISH_AUDIO_MODEL", "s2.1-pro-free").strip() or "s2.1-pro-free",
            "speed": speed,
        })
    return config


FISH_TEACHER_CUES = {
    "intro": "[warm and confident]",
    "explain": "[calm explanatory tone]",
    "warning": "[lower voice, serious]",
    "summary": "[warm and encouraging]",
}


def _clean_spoken_text(text: str) -> str:
    """Remove Markdown noise while preserving the lesson's spoken meaning."""
    cleaned = re.sub(r"\[P\d+\s+\d{1,2}:\d{2}(?:[^\]]*)\]", "", text)
    cleaned = re.sub(r"[`*_#]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -—：:；;")


def _split_teacher_phrases(text: str, max_chars: int = 34) -> list[str]:
    """Create short, teachable phrases without changing their order or meaning."""
    sentences = [part.strip() for part in re.findall(r"[^。！？；]+[。！？；]?", text) if part.strip()]
    phrases: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            phrases.append(sentence)
            continue
        pieces = [part.strip() for part in re.findall(r"[^，、：]+[，、：]?", sentence) if part.strip()]
        phrases.extend(pieces or [sentence])
    return phrases


def build_fish_teacher_text(
    text: str,
    role: str = "explain",
    emphasis_terms: list[str] | None = None,
) -> str:
    """Convert clean captions into expressive Fish S2/S2.1 teacher delivery text.

    Fish receives this tagged text; the HTML subtitle keeps the original clean text.
    Cues follow Fish's square-bracket natural-language control syntax. Emphasis is
    a local standalone cue, not an unsupported paired tag.
    """
    clean_text = _clean_spoken_text(text)
    phrases = _split_teacher_phrases(clean_text)
    if not phrases:
        return clean_text

    remaining_terms = [term.strip() for term in (emphasis_terms or []) if term.strip()]
    rendered: list[str] = []
    for phrase in phrases:
        marked = phrase
        for term in list(remaining_terms):
            if term in marked:
                marked = marked.replace(term, f"[emphasis]{term}", 1)
                remaining_terms.remove(term)
        rendered.append(marked)

    cue = FISH_TEACHER_CUES.get(role, FISH_TEACHER_CUES["explain"])
    return f"{cue} " + " [pause] ".join(rendered)


def add_fish_audio(beats: list[dict], config: dict[str, object], cache_dir: Path) -> None:
    """Synthesize expressive teacher narration through Fish Audio and embed cached MP3 data."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for index, beat in enumerate(beats, 1):
        tts_text = build_fish_teacher_text(
            beat["text"],
            role=beat.get("deliveryRole", "explain"),
            emphasis_terms=beat.get("emphasisTerms", []),
        )
        cache_key = json.dumps({
            "text": tts_text,
            "voice_id": config["voice_id"],
            "model": config["model"],
            "speed": config["speed"],
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")
        audio_path = cache_dir / f"{hashlib.sha256(cache_key).hexdigest()}.mp3"
        if not audio_path.exists():
            payload = json.dumps({
                "text": tts_text,
                "reference_id": str(config["voice_id"]),
                "format": "mp3",
                "prosody": {"speed": float(config["speed"])},
            }, ensure_ascii=False).encode("utf-8")
            request = Request(
                "https://api.fish.audio/v1/tts",
                data=payload,
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                    "model": str(config["model"]),
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=300) as response:
                    audio = response.read()
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"Fish Audio synthesis failed for timeline segment {index} (HTTP {exc.code}): {detail}") from exc
            except URLError as exc:
                raise RuntimeError(f"Fish Audio synthesis failed for timeline segment {index}: {exc.reason}") from exc
            audio_path.write_bytes(audio)
        beat["audioData"] = "data:audio/mpeg;base64," + base64.b64encode(audio_path.read_bytes()).decode("ascii")
        beat["language"] = config["language"]
        beat.pop("deliveryRole", None)
        beat.pop("emphasisTerms", None)


def generate_html_player(
    info: dict,
    profile: dict | None = None,
    tts_config: dict[str, object] | None = None,
    tts_cache_dir: Path | None = None,
) -> str:
    """Generate a fully functioning interactive HTML lecture player tailored to the note."""
    title = info["title"]
    # The player uses a note-derived concept progression for every lesson. A
    # specialized simulation must never be selected from title keywords alone.
    topic = "lesson"
    points = info["core_points"][:4]
    traps = info["traps"][:3]
    formulas = info["formulas"][:2]
    formula_display = formulas[0] if formulas else r"\text{核心定理与性质}"
    safe_trap_json = json.dumps(traps[0] if traps else "注意边界检查与指针规范", ensure_ascii=False)

    school_name = profile["school"] if profile else "全国统考"
    exam_name = profile["exam"] if profile else "408 计算机学科专业基础"
    days_rem = profile.get("days_remaining", 90) if profile else None
    speaker = f"{school_name} 备考课程讲师" if profile and school_name != "全国统考" else "课程讲师"
    hud_alert_default = f"{school_name} 核心内容" if profile and school_name != "全国统考" else "408 重点复习区"

    if profile and school_name != "全国统考":
        header_badges = f"""<span class="badge">{school_name} · {exam_name}</span>
      <span class="badge" style="background: linear-gradient(135deg, #f59e0b, #ef4444); box-shadow: 0 0 10px rgba(239, 68, 68, 0.4);">🔥 考研倒计时 {days_rem} 天</span>"""
        status_text = f"{school_name} 考情引擎已就绪"
        intro_spoken = f"备考【{school_name} {exam_name}】的同学大家好！距离考试仅剩 {days_rem} 天，今天我们进入【{title}】的专项精讲。抓住核心，轻松拿分！"
    else:
        header_badges = """<span class="badge">408 考研微课</span>"""
        status_text = "Course Notes 微课已就绪"
        intro_spoken = f"各位同学大家好！今天我们进入【{title}】的精讲，一起理解它的核心内容与适用条件。"

    # Generate timeline beats for JS
    beats = [
        {
            "atSec": 0,
            "sceneTag": "🎬 SC-01 概念引入",
            "alertText": hud_alert_default,
            "speaker": speaker,
            "text": intro_spoken,
            "deliveryRole": "intro",
            "emphasisTerms": [title],
            "cardId": None,
            "actionCode": "initStage();"
        }
    ]

    sec_counter = 25
    for idx, p in enumerate(points):
        p_text = _clean_spoken_text(p["content"])[:90]
        beats.append({
            "atSec": sec_counter,
            "sceneTag": f"📌 SC-0{idx+2} {p['title'][:16]}",
            "alertText": "重点推演",
            "speaker": speaker,
            "text": f"重点来看：{p['title']}。{p_text}……请结合定义与适用条件理解这一关键逻辑！",
            "deliveryRole": "explain",
            "emphasisTerms": [p["title"], "适用条件"],
            "cardId": f"card-{idx}",
            "actionCode": f"stepAction({idx});"
        })
        sec_counter += 35

    beats.append({
        "atSec": min(180, sec_counter),
        "sceneTag": "⚠️ SC-05 易错陷阱防范",
        "alertText": "易错点提醒",
        "speaker": speaker,
        "text": f"最后检查易错点：{traps[0] if traps else '注意边界条件与指针约定'}。请结合反例确认理解！",
        "deliveryRole": "warning",
        "emphasisTerms": ["易错点", "注意"],
        "cardId": "card-trap",
        "actionCode": "showTrapWarning();"
    })

    beats.append({
        "atSec": min(205, sec_counter + 25),
        "sceneTag": "🎉 SC-06 总结与全景通关",
        "alertText": "本节回顾",
        "speaker": speaker,
        "text": f"以上是本节的核心内容，请通过例题继续检查掌握情况。我们下一小节再见！",
        "deliveryRole": "summary",
        "emphasisTerms": ["核心内容", "检查掌握情况"],
        "cardId": None,
        "actionCode": "finishStage();"
    })

    tts_config = tts_config or {"provider": "browser", "language": "zh-CN"}
    for beat in beats:
        beat["language"] = tts_config["language"]
    if tts_config["provider"] == "fish_audio":
        if tts_cache_dir is None:
            raise ValueError("Fish Audio TTS requires a cache directory")
        add_fish_audio(beats, tts_config, tts_cache_dir)
    else:
        for beat in beats:
            beat.pop("deliveryRole", None)
            beat.pop("emphasisTerms", None)

    beats_json = json.dumps(beats, ensure_ascii=False, indent=6)
    steps_data = []
    for idx, p in enumerate(points):
        clean_title = re.sub(r"^\d+[\.、\s]*", "", p["title"]).strip()
        bolds = re.findall(r"\*\*([^\*]+)\*\*", p["content"])
        diag_in = bolds[0].strip() if len(bolds) > 0 else "前置输入/定义"
        diag_out = bolds[1].strip() if len(bolds) > 1 else (bolds[0].strip() if len(bolds) > 0 else "性质收敛/考法")
        steps_data.append({
            "index": idx + 1,
            "title": clean_title,
            "input": diag_in[:16],
            "output": diag_out[:16],
            "stageTag": f"阶段 0{idx+1} · 核心推演",
        })
    lesson_steps_json = json.dumps(steps_data, ensure_ascii=False)

    # Topic-specific stage markup
    if topic == "stack":
        stage_markup = """
          <div class="index-axis">
            <div class="axis-slot"><div class="pointer-badge" id="ptrBadge-4">➡ top: 4</div><span>[4]</span></div>
            <div class="axis-slot"><div class="pointer-badge" id="ptrBadge-3">➡ top: 3</div><span>[3]</span></div>
            <div class="axis-slot"><div class="pointer-badge" id="ptrBadge-2">➡ top: 2</div><span>[2]</span></div>
            <div class="axis-slot"><div class="pointer-badge" id="ptrBadge-1">➡ top: 1</div><span>[1]</span></div>
            <div class="axis-slot"><div class="pointer-badge" id="ptrBadge-0">➡ top: 0</div><span>[0]</span></div>
            <div class="axis-slot empty-base"><div class="pointer-badge active" id="ptrBadge-empty">➡ top: -1</div><span>-1</span></div>
          </div>
          <div class="stack-box-wrapper">
            <div class="stage-label-top">▼ 栈顶 Top (出入端) ▼</div>
            <div class="stack-container" id="visualContainer"></div>
            <div class="stage-label-bot">▲ 栈底 Bottom (封闭端) ▲</div>
          </div>
          <div class="stage-output-col">
            <div class="output-flow-card">
              <div class="flow-title">📤 出栈序列 (Output):</div>
              <div class="flow-stream" id="flowStream"><span class="flow-empty">[ 暂无出栈 ]</span></div>
            </div>
            <div class="verdict-banner" id="verdictBanner" style="display:none;">
              <span style="font-size: 1.4rem;">🚫</span>
              <div><div class="v-title" id="verdictTitle">注意</div><div class="v-desc" id="verdictDesc"></div></div>
            </div>
          </div>
        """
        sandbox_controls = """
          <div class="btn-grid">
            <button class="tool-btn primary" onclick="manualOp1()">压栈 Push</button>
            <button class="tool-btn" onclick="manualOp2()">弹栈 Pop</button>
            <button class="tool-btn" onclick="manualOp3()">读顶 GetTop</button>
            <button class="tool-btn" onclick="manualReset()">清空重置</button>
          </div>
        """
    elif topic == "queue":
        stage_markup = """
          <div style="display:flex; flex-direction:column; align-items:center; gap:1.25rem; width:100%; max-width:480px;">
            <div style="font-size:0.85rem; color:var(--primary); font-weight:bold;">循环队列内存视图 (MaxSize = 6, 模运算实现)</div>
            <div class="queue-container" id="visualContainer" style="display:grid; grid-template-columns:repeat(6, 1fr); gap:6px; width:100%;">
              <!-- 6 queue slots -->
            </div>
            <div style="display:flex; justify-content:space-between; width:100%; font-family:monospace; font-size:0.85rem; background:#0f172a; padding:0.6rem 1rem; border-radius:0.5rem; border:1px solid var(--border);">
              <span id="qFrontLabel" style="color:var(--warning);">front: 0</span>
              <span id="qRearLabel" style="color:var(--success);">rear: 0</span>
              <span id="qCountLabel" style="color:var(--primary);">元素数: 0</span>
            </div>
          </div>
        """
        sandbox_controls = """
          <div class="btn-grid">
            <button class="tool-btn primary" onclick="manualOp1()">入队 EnQueue</button>
            <button class="tool-btn" onclick="manualOp2()">出队 DeQueue</button>
            <button class="tool-btn" onclick="manualOp3()">队列判空/满</button>
            <button class="tool-btn" onclick="manualReset()">清空重置</button>
          </div>
        """
    elif topic == "string_kmp":
        stage_markup = """
          <div style="display:flex; flex-direction:column; gap:1rem; width:100%; max-width:500px;">
            <div style="background:#0f172a; border:1px solid var(--border); border-radius:8px; padding:0.75rem;">
              <div style="font-size:0.75rem; color:var(--muted); margin-bottom:0.4rem;">主串 S (i 指针不回溯):</div>
              <div id="mainStrRow" style="display:flex; gap:4px; font-family:monospace; font-size:1.1rem; font-weight:bold;"></div>
            </div>
            <div style="background:#0f172a; border:1px solid var(--border); border-radius:8px; padding:0.75rem;">
              <div style="font-size:0.75rem; color:var(--muted); margin-bottom:0.4rem;">模式串 T (滑动对其，退至 next[j]):</div>
              <div id="patStrRow" style="display:flex; gap:4px; font-family:monospace; font-size:1.1rem; font-weight:bold;"></div>
            </div>
            <div id="kmpInfoBox" style="font-size:0.85rem; color:var(--warning); text-align:center; min-height:24px;"></div>
          </div>
        """
        sandbox_controls = """
          <div class="btn-grid">
            <button class="tool-btn primary" onclick="manualOp1()">单步匹配 Step</button>
            <button class="tool-btn" onclick="manualOp2()">快速匹配</button>
            <button class="tool-btn" onclick="manualOp3()">显示 next 数组</button>
            <button class="tool-btn" onclick="manualReset()">重置初始</button>
          </div>
        """
    else:
        stage_markup = """
          <div class="lesson-stage">
            <div class="stage-visual-header">
              <div class="visual-badge">🎬 知识图解与动态状态机</div>
              <div id="visualRunStatus" class="visual-status">● 待命中</div>
            </div>

            <!-- Central Dynamic Architecture Diagram -->
            <div class="diagram-canvas" id="diagramCanvas">
              <div class="diagram-node-block" id="nodeInputBlock">
                <span class="node-tag">IN 前置/输入</span>
                <strong id="nodeInputText">等待初始化</strong>
              </div>
              <div class="diagram-connector">
                <svg width="36" height="20" viewBox="0 0 36 20">
                  <path class="flow-arrow" d="M2,10 L28,10 M20,4 L28,10 L20,16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
                </svg>
              </div>
              <div class="diagram-node-block core" id="nodeCoreBlock">
                <span class="node-tag">CORE 核心推演</span>
                <strong id="nodeCoreText">知识状态机</strong>
              </div>
              <div class="diagram-connector">
                <svg width="36" height="20" viewBox="0 0 36 20">
                  <path class="flow-arrow" d="M2,10 L28,10 M20,4 L28,10 L20,16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
                </svg>
              </div>
              <div class="diagram-node-block" id="nodeOutputBlock">
                <span class="node-tag">OUT 收敛/性质</span>
                <strong id="nodeOutputText">待推导</strong>
              </div>
            </div>

            <!-- Active Concept Highlight Pill -->
            <div class="active-concept-pill" id="activeConceptPill">
              <span class="concept-icon">📌</span>
              <span id="activeConceptLabel">点击下方播放，开始动态推演</span>
            </div>

            <!-- State Step Navigation Slots -->
            <div id="stateSlots" class="lesson-step-list" aria-label="知识点访问状态"></div>

            <div class="lesson-stage-metrics">
              <span>已推演 <strong id="visitedCount">0</strong></span>
              <span>当前节点 <strong id="currentStepLabel">—</strong></span>
              <span>总节点 <strong id="totalStepCount">0</strong></span>
            </div>
          </div>
        """
        sandbox_controls = """
          <div class="btn-grid">
            <button class="tool-btn primary" onclick="manualOp1()">查看下一知识点</button>
            <button class="tool-btn" onclick="manualOp2()">查看上一知识点</button>
            <button class="tool-btn" onclick="manualOp3()">显示全部知识点</button>
            <button class="tool-btn" onclick="manualReset()">重置动手演示</button>
          </div>
          <div class="manual-demo" id="manualDemo" aria-live="polite">
            <span class="manual-demo-state" id="manualDemoState">未开始</span>
            <strong id="manualDemoTitle">请选择“查看下一知识点”</strong>
            <p id="manualDemoBody">这里的操作不会改变课程画面、旁白或播放进度。</p>
          </div>
          <p class="sandbox-note">动手演示与课程播放使用独立状态，不会互相覆盖。</p>
        """

    # Generate points cards markup
    cards_html = ""
    for idx, p in enumerate(points):
        cards_html += f"""
          <div class="point-item" id="card-{idx}">
            <span class="tag blue">考点 {idx+1}</span>
            <div class="point-title">{p['title']}</div>
            <div class="point-body">{p['content'][:110]}...</div>
          </div>
        """
    if traps:
        cards_html += f"""
          <div class="point-item" id="card-trap">
            <span class="tag red">易错陷阱</span>
            <div class="point-title">408 核心避坑点</div>
            <div class="point-body">{traps[0][:110]}</div>
          </div>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" href="data:,">
  <title>{title} —— 408考研动态讲解微课</title>
  <style>
    /* 温和教材：唯一内置视觉风格 */
    ::selection {{ background: var(--primary); color: #000; }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--muted); }}
    :focus-visible {{ outline: 2px solid var(--primary); outline-offset: 2px; }}
    .time-readout, .catalan-math, .index-axis, #qFrontLabel, #qRearLabel, #qCountLabel, #mainStrRow, #patStrRow, #kmpInfoBox {{
      font-variant-numeric: tabular-nums;
    }}

    :root {{
      --bg: #f5f5ef;
      --panel: #fffefa;
      --card: #e9f0e5;
      --border: #dfe3d9;
      --primary: #24634e;
      --accent: #315f50;
      --success: #4f755f;
      --danger: #93601e;
      --warning: #93601e;
      --text: #30413b;
      --muted: #717b73;
      --viewport-bg: #f8f8f3;
      --sandbox-bg: #f2f4ed;
      --badge-bg: #243c36;
      --badge-color: #fffefa;
      --container-bg: #f7f8f2;
      --card-shadow: 0 4px 12px rgba(36, 60, 54, 0.06);
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
      transition: background-color 0.25s ease, color 0.25s ease;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 0.85rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: 0 4px 12px rgba(0,0,0,0.25);
      z-index: 10;
    }}
    .brand {{ display: flex; align-items: center; gap: 0.75rem; }}
    .header-right {{ display: flex; align-items: center; gap: 1.25rem; }}
    .badge {{
      background: var(--badge-bg);
      color: var(--badge-color);
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
      letter-spacing: 0.05em;
    }}
    h1 {{ font-size: 1.15rem; font-weight: 600; color: var(--text); }}
    .status-badge {{ display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--primary); }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px var(--success); }}
    main {{
      flex: 1;
      display: grid;
      grid-template-columns: 1.25fr 1fr;
      gap: 1.5rem;
      padding: 1.5rem;
      max-width: 1560px;
      margin: 0 auto;
      width: 100%;
    }}
    @media (max-width: 1080px) {{ main {{ grid-template-columns: 1fr; }} }}
    .stage-card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 1rem;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      box-shadow: var(--card-shadow);
      transition: all 0.25s ease;
    }}
    .video-viewport {{
      flex: 1;
      min-height: 520px;
      background: var(--viewport-bg);
      position: relative;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 1.25rem;
      overflow: hidden;
      transition: background 0.25s ease;
    }}
    .viewport-hud {{ display: flex; justify-content: space-between; align-items: center; z-index: 5; }}
    .hud-tag {{
      background: var(--card);
      border: 1px solid var(--border);
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--primary);
    }}
    .hud-alert {{
      background: rgba(251, 191, 36, 0.15);
      border: 1px solid rgba(251, 191, 36, 0.4);
      color: #fef08a;
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
    }}
    .stage-arena {{
      flex: 1;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 2.5rem;
      position: relative;
      margin: 1rem 0;
    }}
    /* Stage Specific Styles */
    .index-axis {{ display: flex; flex-direction: column; height: 270px; justify-content: space-between; align-items: flex-end; width: 130px; margin-top: 1.3rem; }}
    .axis-slot {{ display: flex; align-items: center; gap: 0.5rem; height: 46px; color: var(--muted); font-family: monospace; font-size: 0.85rem; }}
    .axis-slot.empty-base {{ height: 20px; color: #64748b; }}
    .pointer-badge {{
      display: flex; align-items: center; gap: 4px;
      background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.5);
      color: var(--danger); font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 6px;
      font-size: 0.8rem; opacity: 0; transform: translateX(10px); transition: all 0.25s; white-space: nowrap;
    }}
    .pointer-badge.active {{ opacity: 1; transform: translateX(0); }}
    .stack-box-wrapper {{ display: flex; flex-direction: column; align-items: center; }}
    .stage-label-top {{ font-size: 0.75rem; color: var(--warning); font-weight: 600; margin-bottom: 0.4rem; }}
    .stage-label-bot {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.5rem; }}
    .stack-container {{
      width: 160px; height: 270px;
      border-left: 4px solid var(--primary); border-right: 4px solid var(--primary); border-bottom: 5px solid var(--primary);
      border-radius: 0 0 14px 14px; position: relative;
      background: rgba(56, 189, 248, 0.03); box-shadow: 0 0 25px rgba(56, 189, 248, 0.15);
      display: flex; flex-direction: column-reverse; padding: 6px; gap: 6px;
    }}
    .stack-elem {{
      height: 46px; background: linear-gradient(135deg, #0284c7, #2563eb);
      border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-size: 1.15rem; font-weight: 700; color: white;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
      animation: dropIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }}
    @keyframes dropIn {{ from {{ transform: translateY(-100px); opacity: 0; }} to {{ transform: translateY(0); opacity: 1; }} }}
    .stack-elem.pop-out {{ animation: popOut 0.35s ease forwards; }}
    @keyframes popOut {{ to {{ transform: translateY(-120px); opacity: 0; }} }}
    .stage-output-col {{ width: 170px; display: flex; flex-direction: column; gap: 1rem; }}
    .output-flow-card {{ background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border); border-radius: 0.75rem; padding: 0.85rem; }}
    .flow-title {{ font-size: 0.75rem; color: var(--muted); margin-bottom: 0.5rem; font-weight: 600; }}
    .flow-stream {{ display: flex; flex-wrap: wrap; gap: 0.4rem; min-height: 40px; align-items: center; }}
    .flow-pill {{ background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.4); color: var(--success); font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px; }}
    .flow-empty {{ font-size: 0.8rem; color: #64748b; font-style: italic; }}
    .verdict-banner {{ background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); border-radius: 0.75rem; padding: 0.85rem; display: flex; gap: 0.6rem; }}
    .v-title {{ font-size: 0.85rem; font-weight: 700; color: var(--danger); }}
    .v-desc {{ font-size: 0.75rem; color: #fca5a5; line-height: 1.3; }}

    /* Queue & String/KMP Styles */
    .queue-slot {{
      background: #1e293b; border: 2px solid var(--border); border-radius: 8px;
      height: 64px; display: flex; flex-direction: column; align-items: center; justify-content: space-around;
      position: relative; transition: all 0.25s; padding: 4px;
    }}
    .queue-slot.active-front {{ border-color: var(--warning); box-shadow: 0 0 10px rgba(251, 191, 36, 0.4); }}
    .queue-slot.active-rear {{ border-color: var(--success); box-shadow: 0 0 10px rgba(52, 211, 153, 0.4); }}
    .q-idx {{ font-size: 0.7rem; color: var(--muted); font-family: monospace; }}
    .q-val {{ font-size: 1.1rem; font-weight: bold; color: #fff; }}
    .q-ptr {{ font-size: 0.65rem; font-weight: 700; height: 14px; }}

    .char-cell {{
      width: 44px; height: 50px; background: #1e293b; border: 1.5px solid var(--border); border-radius: 6px;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      position: relative; transition: all 0.2s;
    }}
    .char-cell.match {{ background: rgba(52, 211, 153, 0.2); border-color: var(--success); color: var(--success); }}
    .char-cell.mismatch {{ background: rgba(248, 113, 113, 0.2); border-color: var(--danger); color: var(--danger); }}
    .char-cell.active-ptr {{ box-shadow: 0 0 10px var(--primary); border-color: var(--primary); }}
    .c-char {{ font-size: 1.15rem; font-weight: bold; }}
    .c-idx {{ font-size: 0.68rem; color: var(--muted); font-family: monospace; }}
    /* Subtitle */
    .subtitle-bar {{
      background: rgba(15, 23, 42, 0.9); border: 1px solid var(--border);
      backdrop-filter: blur(10px); border-radius: 0.75rem; padding: 0.85rem 1.25rem;
      min-height: 68px; display: flex; flex-direction: column; justify-content: center; gap: 0.25rem;
      box-shadow: 0 10px 20px rgba(0,0,0,0.4); z-index: 5;
    }}
    .speaker-tag {{ font-size: 0.75rem; color: var(--primary); font-weight: 700; }}
    .subtitle-text {{ font-size: 1rem; font-weight: 500; color: #fff; line-height: 1.4; }}
    /* Controls */
    .controls-bar {{ background: #0d1522; padding: 0.85rem 1.5rem; border-top: 1px solid var(--border); display: flex; align-items: center; gap: 1.25rem; }}
    .play-btn {{
      width: 44px; height: 44px; border-radius: 50%; background: var(--primary);
      border: none; color: #0b0f19; font-size: 1.25rem; display: flex; align-items: center; justify-content: center;
      cursor: pointer; transition: all 0.2s; flex-shrink: 0;
    }}
    .play-btn:hover {{ transform: scale(1.08); background: #7dd3fc; }}
    .progress-container {{ flex: 1; display: flex; flex-direction: column; gap: 0.4rem; }}
    .progress-hit-area {{ height: 18px; display: flex; align-items: center; cursor: pointer; position: relative; }}
    .progress-bar-bg {{ height: 6px; width: 100%; background: #334155; border-radius: 4px; overflow: hidden; }}
    .progress-fill {{ height: 100%; background: linear-gradient(90deg, var(--primary), var(--accent)); width: 0%; border-radius: 4px; transition: width 0.1s linear; }}
    .progress-hit-area:hover .progress-bar-bg {{ height: 8px; }}
    .time-readout {{ display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--muted); font-family: monospace; }}
    /* Sidebar */
    .sidebar-card {{ display: flex; flex-direction: column; gap: 1.25rem; }}
    .panel-box {{ background: var(--panel); border: 1px solid var(--border); border-radius: 1rem; padding: 1.25rem; }}
    .panel-header {{ font-size: 0.95rem; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255, 255, 255, 0.08); }}
    .btn-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin-bottom: 1rem; }}
    .tool-btn {{
      background: var(--card); border: 1px solid var(--border); color: var(--text);
      padding: 0.55rem 0.5rem; border-radius: 0.5rem; font-size: 0.8rem; font-weight: 600;
      cursor: pointer; transition: all 0.2s; text-align: center;
    }}
    .tool-btn:hover {{ background: #334155; border-color: var(--primary); }}
    .tool-btn.primary {{ background: #0284c7; border-color: #38bdf8; color: #fff; }}
    .catalan-display {{
      background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
      border: 1px solid rgba(251, 191, 36, 0.3); border-radius: 0.75rem; padding: 0.85rem 1rem; text-align: center; margin-bottom: 1rem;
    }}
    .catalan-math {{ font-size: 1.15rem; color: var(--warning); font-weight: bold; margin: 0.3rem 0; }}
    .points-container {{ display: flex; flex-direction: column; gap: 0.65rem; max-height: 250px; overflow-y: auto; }}
    .point-item {{ background: rgba(30, 41, 59, 0.4); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.7rem; transition: all 0.2s; }}
    .point-item.active {{ border-color: var(--accent); background: rgba(99, 102, 241, 0.12); }}
    .tag {{ display: inline-block; font-size: 0.68rem; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: bold; margin-bottom: 0.3rem; }}
    .tag.blue {{ background: rgba(56, 189, 248, 0.2); color: var(--primary); }}
    .tag.red {{ background: rgba(248, 113, 113, 0.2); color: var(--danger); }}
    .point-title {{ font-size: 0.85rem; font-weight: 600; color: var(--text); margin-bottom: 0.2rem; }}
    .point-body {{ font-size: 0.78rem; color: var(--muted); line-height: 1.55; }}
    .lesson-stage {{ width:100%; max-width:640px; background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:1.25rem; }}
    .stage-visual-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; }}
    .visual-badge {{ font-size:0.82rem; font-weight:700; color:var(--primary); }}
    .visual-status {{ font-size:0.75rem; font-weight:600; color:var(--muted); padding:0.15rem 0.55rem; border-radius:999px; background:var(--card); transition:all 0.2s; }}
    .visual-status.active {{ color:#047857; background:#d1fae5; box-shadow:0 0 8px rgba(4, 120, 87, 0.25); }}
    .visual-status.warn {{ color:#b45309; background:#fef3c7; }}
    .visual-status.done {{ color:#15803d; background:#dcfce7; }}
    .diagram-canvas {{
      display:flex; align-items:center; justify-content:space-between; gap:0.5rem;
      background:var(--viewport-bg); border:1.5px solid var(--border); border-radius:10px;
      padding:0.85rem 0.75rem; margin-bottom:0.75rem; transition:all 0.3s ease;
    }}
    .diagram-canvas.pulse {{ border-color:var(--primary); box-shadow:0 0 14px rgba(36, 99, 78, 0.2); transform:scale(1.01); }}
    .diagram-node-block {{
      flex:1; display:flex; flex-direction:column; align-items:center; text-align:center;
      background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:0.55rem 0.4rem;
      min-height:56px; justify-content:center; transition:all 0.2s;
    }}
    .diagram-node-block.core {{
      flex:1.4; border-color:var(--primary); background:var(--card); box-shadow:0 2px 8px rgba(36, 99, 78, 0.1);
    }}
    .node-tag {{ font-size:0.65rem; color:var(--muted); font-weight:700; text-transform:uppercase; margin-bottom:0.2rem; }}
    .diagram-node-block.core .node-tag {{ color:var(--primary); }}
    .diagram-node-block strong {{ font-size:0.8rem; color:var(--text); line-height:1.3; word-break:break-all; }}
    .diagram-connector {{ display:flex; align-items:center; color:var(--primary); flex-shrink:0; }}
    .flow-arrow {{ stroke-dasharray: 5 3; animation: flowDash 1.2s linear infinite; }}
    @keyframes flowDash {{ to {{ stroke-dashoffset: -16; }} }}
    .active-concept-pill {{
      display:flex; align-items:center; gap:0.5rem; background:var(--card);
      border:1px solid var(--border); border-radius:8px; padding:0.45rem 0.75rem;
      font-size:0.82rem; font-weight:600; color:var(--text); margin-bottom:0.75rem;
    }}
    .lesson-step-list {{ display:grid; gap:0.5rem; margin-top:0.75rem; }}
    .lesson-step {{ display:grid; grid-template-columns:2rem 1fr auto; gap:0.65rem; align-items:center; padding:0.65rem 0.75rem; border:1px solid var(--border); border-radius:10px; background:#fafaf6; color:var(--muted); }}
    .lesson-step.visited {{ background:var(--card); color:var(--text); }}
    .lesson-step.current {{ background:var(--primary); border-color:var(--primary); color:#fff; }}
    .lesson-step-index, .lesson-stage-metrics {{ font-family:Consolas, "SFMono-Regular", monospace; font-variant-numeric:tabular-nums; }}
    .lesson-step-state {{ font-size:0.72rem; }}
    .lesson-stage-metrics {{ display:flex; justify-content:space-between; gap:1rem; margin-top:0.75rem; padding-top:0.75rem; border-top:1px solid var(--border); color:var(--muted); font-size:0.78rem; }}
    .sandbox-note {{ color:var(--muted); font-size:0.75rem; line-height:1.6; margin-top:0.65rem; }}
    .manual-demo {{ border:1px solid var(--border); border-radius:10px; background:#fafaf6; padding:0.8rem; min-height:6.5rem; }}
    .manual-demo-state {{ display:inline-block; color:var(--primary); background:var(--card); border-radius:999px; padding:0.15rem 0.5rem; font:0.7rem Consolas, monospace; margin-bottom:0.45rem; }}
    .manual-demo strong {{ display:block; color:var(--text); font-size:0.85rem; margin-bottom:0.35rem; }}
    .manual-demo p {{ color:var(--muted); font-size:0.76rem; line-height:1.55; }}
    .subtitle-bar {{ background:#243c36; backdrop-filter:none; box-shadow:none; }}
    .controls-bar {{ background:#243c36; }}
    .play-btn {{ color:#243c36; background:#e2edda; }}
    .hud-alert {{ background:#faf0dd; border-color:#eddfc6; color:#7d541d; }}
    .panel-box, .stage-card {{ box-shadow:var(--card-shadow); }}
    @media (prefers-reduced-motion: reduce) {{ * {{ transition:none!important; animation:none!important; }} }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      {header_badges}
      <h1>{title} —— 动态讲解</h1>
    </div>
    <div class="header-right">
      <div class="status-badge"><div class="dot"></div><span>{status_text}</span></div>
    </div>
  </header>

  <main>
    <section class="stage-card">
      <div class="video-viewport">
        <div class="viewport-hud">
          <div class="hud-tag" id="hudSceneTag">🎬 SC-01 概念引入</div>
          <div class="hud-alert" id="hudAlert">{hud_alert_default}</div>
        </div>

        <div class="stage-arena">
          {stage_markup}
        </div>

        <div class="subtitle-bar">
          <div class="speaker-tag" id="speakerLabel">{speaker}</div>
          <div class="subtitle-text" id="subtitleContent">欢迎进入【{title}】！点击下方播放开始极速通关。</div>
        </div>
      </div>

      <div class="controls-bar">
        <button class="play-btn" id="playBtn" onclick="togglePlay()">▶</button>
        <div class="progress-container">
          <div class="progress-hit-area" onclick="handleSeek(event)">
            <div class="progress-bar-bg"><div class="progress-fill" id="progressFill"></div></div>
          </div>
          <div class="time-readout">
            <span id="currentTimeLabel">00:00</span>
            <span id="totalTimeLabel">--:--</span>
          </div>
        </div>
        <button class="tool-btn" onclick="restartVideo()" style="flex:0; padding:0.4rem 0.8rem;">↺ 重置</button>
      </div>
    </section>

    <section class="sidebar-card">
      <div class="panel-box">
        <div class="panel-header"><span>🛠️ 动手推演沙盘 (Sandbox)</span></div>
        {sandbox_controls}
      </div>

      <div class="panel-box" style="flex:1;">
        <div class="panel-header"><span>🎯 核心内容速查</span></div>
        <div class="catalan-display">
          <div style="font-size:0.75rem; color:var(--muted);">核心数学结论与公式：</div>
          <div class="catalan-math">{formula_display}</div>
        </div>
        <div class="points-container">
          {cards_html}
        </div>
      </div>
    </section>
  </main>

  <script>
    let totalDurationSec = 0;
    let currentSeconds = 0;
    let isPlaying = false;
    let playInterval = null;
    let activeAudio = null;
    let activeBeatIndex = 0;
    let activeBeatOffset = 0;
    let lastExecutedStep = -1;
    let timelineReady = false;
    let timelinePromise = null;
    let elements = [];
    let outputs = [];
    let counter = 1;
    let manualLessonStep = -1;

    const beats = {beats_json};
    const LESSON_STEPS = {lesson_steps_json};

    function formatTime(s) {{
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return `${{String(m).padStart(2, '0')}}:${{String(sec).padStart(2, '0')}}`;
    }}

    function estimateSpeechDuration(text) {{
      return Math.max(2.5, text.length / 4.6);
    }}

    function prepareTimeline() {{
      if (timelinePromise) return timelinePromise;
      timelinePromise = Promise.all(beats.map((beat) => new Promise((resolve) => {{
        if (!beat.audioData) {{ resolve(estimateSpeechDuration(beat.text)); return; }}
        const audio = new Audio(beat.audioData);
        audio.preload = 'metadata';
        const done = () => resolve(Number.isFinite(audio.duration) ? audio.duration : estimateSpeechDuration(beat.text));
        audio.addEventListener('loadedmetadata', done, {{once:true}});
        audio.addEventListener('error', () => resolve(estimateSpeechDuration(beat.text)), {{once:true}});
      }}))).then((durations) => {{
        let cursor = 0;
        beats.forEach((beat, index) => {{
          beat.startSec = cursor;
          beat.durationSec = durations[index];
          cursor += durations[index];
        }});
        totalDurationSec = cursor;
        timelineReady = true;
        updateProgressUI();
      }});
      return timelinePromise;
    }}

    async function togglePlay() {{
      await prepareTimeline();
      const btn = document.getElementById('playBtn');
      if (isPlaying) {{
        pausePlayback();
        btn.innerText = "▶";
      }} else {{
        isPlaying = true;
        btn.innerText = "⏸";
        playBeat(activeBeatIndex, activeBeatOffset);
      }}
    }}

    function startProgressTicker() {{
      if (playInterval) clearInterval(playInterval);
      playInterval = setInterval(() => {{
        if (activeAudio) currentSeconds = beats[activeBeatIndex].startSec + activeAudio.currentTime;
        updateProgressUI();
      }}, 100);
    }}

    function stopNarration() {{
      if (activeAudio) {{ activeAudio.pause(); activeAudio = null; }}
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    }}

    function pausePlayback() {{
      if (activeAudio) activeBeatOffset = activeAudio.currentTime;
      if (playInterval) clearInterval(playInterval);
      stopNarration();
      isPlaying = false;
    }}

    function finishPlayback() {{
      if (playInterval) clearInterval(playInterval);
      stopNarration();
      isPlaying = false;
      currentSeconds = totalDurationSec;
      activeBeatIndex = 0;
      activeBeatOffset = 0;
      document.getElementById('playBtn').innerText = "▶";
      updateProgressUI();
    }}

    function playBeat(index, offset = 0) {{
      if (!isPlaying) return;
      if (index >= beats.length) {{ finishPlayback(); return; }}
      stopNarration();
      activeBeatIndex = index;
      activeBeatOffset = Math.max(0, offset);
      currentSeconds = beats[index].startSec + activeBeatOffset;
      applyBeat(beats[index]);
      const beat = beats[index];
      if (beat.audioData) {{
        activeAudio = new Audio(beat.audioData);
        activeAudio.currentTime = Math.min(activeBeatOffset, Math.max(0, beat.durationSec - 0.05));
        activeAudio.onended = () => {{ activeBeatOffset = 0; playBeat(index + 1, 0); }};
        activeAudio.play().then(startProgressTicker).catch((err) => {{
          console.log('Fish Audio playback failed:', err);
          pausePlayback();
          document.getElementById('playBtn').innerText = "▶";
        }});
      }} else if ('speechSynthesis' in window) {{
        const utterance = new SpeechSynthesisUtterance(beat.text);
        utterance.lang = beat.language || 'zh-CN';
        utterance.rate = 1.0;
        utterance.onend = () => {{ activeBeatOffset = 0; playBeat(index + 1, 0); }};
        window.speechSynthesis.speak(utterance);
        const started = performance.now() - activeBeatOffset * 1000;
        if (playInterval) clearInterval(playInterval);
        playInterval = setInterval(() => {{
          currentSeconds = Math.min(beat.startSec + beat.durationSec, beat.startSec + (performance.now() - started) / 1000);
          updateProgressUI();
        }}, 100);
      }} else {{
        playBeat(index + 1, 0);
      }}
    }}

    async function restartVideo() {{
      pausePlayback();
      await prepareTimeline();
      document.getElementById('playBtn').innerText = "▶";
      currentSeconds = 0;
      activeBeatIndex = 0;
      activeBeatOffset = 0;
      lastExecutedStep = -1;
      updateProgressUI();
      initStage();
      applyBeat(beats[0]);
    }}

    async function handleSeek(e) {{
      await prepareTimeline();
      const wasPlaying = isPlaying;
      pausePlayback();
      const rect = e.currentTarget.getBoundingClientRect();
      currentSeconds = Math.max(0, Math.min(totalDurationSec, ((e.clientX - rect.left) / rect.width) * totalDurationSec));
      let index = beats.findIndex((beat) => currentSeconds < beat.startSec + beat.durationSec);
      if (index < 0) index = beats.length - 1;
      activeBeatIndex = index;
      activeBeatOffset = Math.max(0, currentSeconds - beats[index].startSec);
      applyBeat(beats[index]);
      updateProgressUI();
      if (wasPlaying) {{ isPlaying = true; document.getElementById('playBtn').innerText = "⏸"; playBeat(index, activeBeatOffset); }}
      else document.getElementById('playBtn').innerText = "▶";
    }}

    function updateProgressUI() {{
      const duration = totalDurationSec || 0;
      const pct = duration ? (currentSeconds / duration) * 100 : 0;
      document.getElementById('progressFill').style.width = `${{Math.min(100, pct)}}%`;
      document.getElementById('currentTimeLabel').innerText = formatTime(currentSeconds);
      document.getElementById('totalTimeLabel').innerText = timelineReady ? formatTime(duration) : "--:--";
    }}

    function applyBeat(b) {{
      document.getElementById('hudSceneTag').innerText = b.sceneTag;
      document.getElementById('hudAlert').innerText = b.alertText;
      document.getElementById('speakerLabel').innerText = b.speaker;
      document.getElementById('subtitleContent').innerText = b.text;

      document.querySelectorAll('.point-item').forEach(c => c.classList.remove('active'));
      if (b.cardId) {{
        const el = document.getElementById(b.cardId);
        if (el) el.classList.add('active');
      }}

      try {{ eval(b.actionCode); }} catch (err) {{ console.log(err); }}
    }}

    /* Stage Mechanics for {topic} */
    let qData = new Array(6).fill(null);
    let qFront = 0;
    let qRear = 0;
    let qCount = 0;

    const S_STR = "ABABCABAA";
    const T_STR = "ABAA";
    const NEXT_VALS = [0, 1, 1, 2];
    let kmpI = 0;
    let kmpJ = 0;

    let algoStep = 0;

    function initStage() {{
      if ("{topic}" === "stack") {{
        const box = document.getElementById('visualContainer');
        if (box) box.innerHTML = '';
        elements = [];
        outputs = [];
        counter = 1;
        syncPointerUI();
      }} else if ("{topic}" === "queue") {{
        initQueue();
      }} else if ("{topic}" === "string_kmp") {{
        initKmp();
      }} else {{
        initAlgo();
      }}
    }}

    /* Queue Implementation */
    function initQueue() {{
      const box = document.getElementById('visualContainer');
      if (!box) return;
      box.innerHTML = '';
      for (let i = 0; i < 6; i++) {{
        const slot = document.createElement('div');
        slot.className = 'queue-slot';
        slot.id = 'qSlot-' + i;
        slot.innerHTML = `<span class="q-idx">[${{i}}]</span><span class="q-val" id="qVal-${{i}}">-</span><div class="q-ptr" id="qPtr-${{i}}"></div>`;
        box.appendChild(slot);
      }}
      qData = new Array(6).fill(null);
      qFront = 0;
      qRear = 0;
      qCount = 0;
      syncQueueUI();
    }}

    function syncQueueUI() {{
      for (let i = 0; i < 6; i++) {{
        const slot = document.getElementById('qSlot-' + i);
        const valEl = document.getElementById('qVal-' + i);
        const ptrEl = document.getElementById('qPtr-' + i);
        if (!slot) continue;
        slot.classList.remove('active-front', 'active-rear');
        valEl.innerText = qData[i] !== null ? qData[i] : '-';
        let ptrs = [];
        if (i === qFront) {{ slot.classList.add('active-front'); ptrs.push('<span style="color:var(--warning)">▲front</span>'); }}
        if (i === qRear) {{ slot.classList.add('active-rear'); ptrs.push('<span style="color:var(--success)">▼rear</span>'); }}
        ptrEl.innerHTML = ptrs.join(' ');
      }}
      const fLabel = document.getElementById('qFrontLabel');
      const rLabel = document.getElementById('qRearLabel');
      const cLabel = document.getElementById('qCountLabel');
      if (fLabel) fLabel.innerText = 'front: ' + qFront;
      if (rLabel) rLabel.innerText = 'rear: ' + qRear;
      if (cLabel) cLabel.innerText = '元素数: ' + qCount + (qCount === 5 ? ' (队满牺牲一格)' : (qCount === 0 ? ' (队空)' : ''));
    }}

    function queueEnq(val) {{
      if ((qRear + 1) % 6 === qFront) {{
        alert("【队列已满】(rear+1)%MaxSize == front，无法再入队！");
        return false;
      }}
      qData[qRear] = val;
      qRear = (qRear + 1) % 6;
      qCount++;
      syncQueueUI();
      return true;
    }}

    function queueDeq() {{
      if (qFront === qRear) {{
        alert("【队列为空】front == rear，无法出队！");
        return null;
      }}
      const val = qData[qFront];
      qData[qFront] = null;
      qFront = (qFront + 1) % 6;
      qCount--;
      syncQueueUI();
      return val;
    }}

    /* String / KMP Implementation */
    function initKmp() {{
      const sRow = document.getElementById('mainStrRow');
      const tRow = document.getElementById('patStrRow');
      if (!sRow || !tRow) return;
      sRow.innerHTML = '';
      tRow.innerHTML = '';
      for (let i = 0; i < S_STR.length; i++) {{
        const c = document.createElement('div');
        c.className = 'char-cell';
        c.id = 'sCell-' + i;
        c.innerHTML = `<span class="c-char">${{S_STR[i]}}</span><span class="c-idx">${{i+1}}</span>`;
        sRow.appendChild(c);
      }}
      for (let j = 0; j < T_STR.length; j++) {{
        const c = document.createElement('div');
        c.className = 'char-cell';
        c.id = 'tCell-' + j;
        c.innerHTML = `<span class="c-char">${{T_STR[j]}}</span><span class="c-idx">${{j+1}}</span>`;
        tRow.appendChild(c);
      }}
      kmpI = 0;
      kmpJ = 0;
      syncKmpUI("就绪：主串与模式串对齐");
    }}

    function syncKmpUI(info) {{
      for (let i = 0; i < S_STR.length; i++) {{
        const c = document.getElementById('sCell-' + i);
        if (c) c.className = 'char-cell' + (i === kmpI ? ' active-ptr' : '');
      }}
      for (let j = 0; j < T_STR.length; j++) {{
        const c = document.getElementById('tCell-' + j);
        if (c) c.className = 'char-cell' + (j === kmpJ ? ' active-ptr' : '');
      }}
      const box = document.getElementById('kmpInfoBox');
      if (box) box.innerText = info || `当前比对：S[${{kmpI+1}}]='${{S_STR[kmpI]}}' vs T[${{kmpJ+1}}]='${{T_STR[kmpJ]}}'`;
    }}

    function kmpStep() {{
      if (kmpI >= S_STR.length || kmpJ >= T_STR.length) {{
        initKmp();
        return;
      }}
      const sChar = S_STR[kmpI];
      const tChar = T_STR[kmpJ];
      if (sChar === tChar) {{
        const sCell = document.getElementById('sCell-' + kmpI);
        const tCell = document.getElementById('tCell-' + kmpJ);
        if (sCell) sCell.classList.add('match');
        if (tCell) tCell.classList.add('match');
        kmpI++;
        kmpJ++;
        if (kmpJ === T_STR.length) {{
          syncKmpUI(`🎉 模式匹配成功！起始下标为: ${{kmpI - T_STR.length + 1}}`);
        }} else {{
          syncKmpUI(`字符匹配: '${{sChar}}' == '${{tChar}}'，双指针协同右移`);
        }}
      }} else {{
        const sCell = document.getElementById('sCell-' + kmpI);
        const tCell = document.getElementById('tCell-' + kmpJ);
        if (sCell) sCell.classList.add('mismatch');
        if (tCell) tCell.classList.add('mismatch');
        const nextJ = NEXT_VALS[kmpJ];
        syncKmpUI(`⚠️ 失配！'${{sChar}}' != '${{tChar}}'，主串 i=${{kmpI+1}} 不回溯，模式串退至 next[${{kmpJ+1}}]=${{nextJ}}`);
        if (nextJ === 0) {{
          kmpI++;
          kmpJ = 0;
        }} else {{
          kmpJ = nextJ - 1;
        }}
      }}
    }}

    /* Algorithm / Generic Implementation */
    function initAlgo() {{
      const slots = document.getElementById('stateSlots');
      if (!slots) return;
      slots.innerHTML = '';
      LESSON_STEPS.forEach((step, idx) => {{
        const item = document.createElement('div');
        item.className = 'lesson-step';
        item.id = 'algoSlot-' + idx;
        item.innerHTML = `<span class="lesson-step-index">${{String(idx + 1).padStart(2, '0')}}</span><span>${{step.title}}</span><span class="lesson-step-state">未访问</span>`;
        slots.appendChild(item);
      }});
      algoStep = 0;
      const total = document.getElementById('totalStepCount');
      if (total) total.innerText = LESSON_STEPS.length;
      updateLessonStage(-1, false);
    }}

    function updateLessonStage(index, manual = false) {{
      LESSON_STEPS.forEach((step, idx) => {{
        const el = document.getElementById('algoSlot-' + idx);
        if (!el) return;
        const state = el.querySelector('.lesson-step-state');
        el.className = 'lesson-step' + (idx < index ? ' visited' : (idx === index ? ' current' : ''));
        if (state) state.innerText = idx < index ? '已访问' : (idx === index ? '当前访问' : '未访问');
      }});

      const inText = document.getElementById('nodeInputText');
      const coreText = document.getElementById('nodeCoreText');
      const outText = document.getElementById('nodeOutputText');
      const pill = document.getElementById('activeConceptLabel');
      const runStatus = document.getElementById('visualRunStatus');
      const canvas = document.getElementById('diagramCanvas');

      if (index >= 0 && LESSON_STEPS[index]) {{
        const s = LESSON_STEPS[index];
        if (inText) inText.innerText = s.input || '输入就绪';
        if (coreText) coreText.innerText = s.title;
        if (outText) outText.innerText = s.output || '性质推导';
        if (pill) pill.innerText = `${{s.stageTag}}：${{s.title}}`;
        if (runStatus) {{
          runStatus.innerText = '● 正在推演';
          runStatus.className = 'visual-status active';
        }}
        if (canvas) {{
          canvas.classList.remove('pulse');
          void canvas.offsetWidth;
          canvas.classList.add('pulse');
        }}
      }} else {{
        if (inText) inText.innerText = '等待初始化';
        if (coreText) coreText.innerText = '知识状态机';
        if (outText) outText.innerText = '待推导';
        if (pill) pill.innerText = '点击下方播放，开始动态推演';
        if (runStatus) {{
          runStatus.innerText = '● 待命中';
          runStatus.className = 'visual-status';
        }}
      }}

      const visited = document.getElementById('visitedCount');
      const current = document.getElementById('currentStepLabel');
      if (visited) visited.innerText = Math.max(0, index);
      if (current) current.innerText = index >= 0 ? String(index + 1).padStart(2, '0') : '—';
    }}

    function stepAlgo(index = null, manual = false) {{
      if (!LESSON_STEPS.length) return;
      const target = index === null ? algoStep % LESSON_STEPS.length : Math.max(0, Math.min(index, LESSON_STEPS.length - 1));
      updateLessonStage(target, manual);
      algoStep = target + 1;
    }}

    function stepAction(stepIdx) {{
      if ("{topic}" === "stack") {{
        pushRaw("Node" + (stepIdx + 1));
      }} else if ("{topic}" === "queue") {{
        queueEnq("Q" + (stepIdx + 1));
      }} else if ("{topic}" === "string_kmp") {{
        kmpStep();
      }} else {{
        stepAlgo(stepIdx);
      }}
    }}

    function showTrapWarning() {{
      if ("{topic}" === "lesson") {{
        LESSON_STEPS.forEach((_, idx) => {{
          const el = document.getElementById('algoSlot-' + idx);
          if (!el) return;
          el.className = 'lesson-step visited';
          const state = el.querySelector('.lesson-step-state');
          if (state) state.innerText = '已访问';
        }});
        const pill = document.getElementById('activeConceptLabel');
        const runStatus = document.getElementById('visualRunStatus');
        const coreText = document.getElementById('nodeCoreText');
        const outText = document.getElementById('nodeOutputText');
        if (runStatus) {{
          runStatus.innerText = '⚠️ 易错警示';
          runStatus.className = 'visual-status warn';
        }}
        if (pill) pill.innerText = '易错陷阱排查：结合反例与边界条件检验';
        if (coreText) coreText.innerText = '易错边界拦截';
        if (outText) outText.innerText = '避坑准则生效';
        const visited = document.getElementById('visitedCount');
        const current = document.getElementById('currentStepLabel');
        if (visited) visited.innerText = LESSON_STEPS.length;
        if (current) current.innerText = '易错';
        return;
      }}
      const vb = document.getElementById('verdictBanner');
      if (vb) {{
        vb.style.display = "flex";
        const vt = document.getElementById('verdictTitle');
        const vd = document.getElementById('verdictDesc');
        if (vt) vt.innerText = "易错点警示";
        if (vd) vd.innerText = {safe_trap_json};
      }}
    }}

    function finishStage() {{
      if ("{topic}" === "lesson") {{
        LESSON_STEPS.forEach((_, idx) => {{
          const el = document.getElementById('algoSlot-' + idx);
          if (!el) return;
          el.className = 'lesson-step visited';
          const state = el.querySelector('.lesson-step-state');
          if (state) state.innerText = '已访问';
        }});
        const pill = document.getElementById('activeConceptLabel');
        const runStatus = document.getElementById('visualRunStatus');
        const coreText = document.getElementById('nodeCoreText');
        const outText = document.getElementById('nodeOutputText');
        if (runStatus) {{
          runStatus.innerText = '✓ 全景就绪';
          runStatus.className = 'visual-status done';
        }}
        if (pill) pill.innerText = '本节知识图解已全景收敛，可结合下方例题继续通关';
        if (coreText) coreText.innerText = '全章考点收敛';
        if (outText) outText.innerText = '知识体系构建';
        const visited = document.getElementById('visitedCount');
        const current = document.getElementById('currentStepLabel');
        if (visited) visited.innerText = LESSON_STEPS.length;
        if (current) current.innerText = '通关';
        return;
      }}
      const vb = document.getElementById('verdictBanner');
      if (vb) vb.style.display = "none";
    }}

    function pushRaw(val) {{
      const box = document.getElementById('visualContainer');
      if (!box || elements.length >= 5) return;
      const el = document.createElement('div');
      el.className = 'stack-elem';
      el.innerText = val;
      box.appendChild(el);
      elements.push(val);
      syncPointerUI();
    }}

    function popRaw() {{
      const box = document.getElementById('visualContainer');
      if (!box || elements.length === 0) return null;
      const val = elements.pop();
      outputs.push(val);
      const fs = document.getElementById('flowStream');
      if (fs) fs.innerHTML = outputs.map(x => `<div class="flow-pill">${{x}}</div>`).join('');
      const last = box.lastElementChild;
      if (last) {{
        last.classList.add('pop-out');
        setTimeout(() => {{ if (last.parentNode) last.remove(); }}, 320);
      }}
      syncPointerUI();
      return val;
    }}

    function syncPointerUI() {{
      for (let i = 0; i < 5; i++) {{
        const b = document.getElementById(`ptrBadge-${{i}}`);
        if (b) b.classList.remove('active');
      }}
      const emptyBadge = document.getElementById('ptrBadge-empty');
      if (emptyBadge) emptyBadge.classList.remove('active');
      if (elements.length === 0) {{
        if (emptyBadge) emptyBadge.classList.add('active');
      }} else {{
        const tb = document.getElementById(`ptrBadge-${{elements.length - 1}}`);
        if (tb) tb.classList.add('active');
      }}
    }}

    /* Sandbox Interactive Handlers */
    function manualOp1() {{
      if ("{topic}" === "stack") pushRaw(String(counter++));
      else if ("{topic}" === "queue") queueEnq("D" + (qCount + 1));
      else if ("{topic}" === "string_kmp") kmpStep();
      else {{ manualLessonStep = Math.min(LESSON_STEPS.length - 1, manualLessonStep + 1); renderManualLessonStep(); }}
    }}
    function manualOp2() {{
      if ("{topic}" === "stack") popRaw();
      else if ("{topic}" === "queue") queueDeq();
      else if ("{topic}" === "string_kmp") {{ for (let k = 0; k < 3; k++) kmpStep(); }}
      else {{ manualLessonStep = Math.max(0, manualLessonStep - 1); renderManualLessonStep(); }}
    }}
    function manualOp3() {{
      if ("{topic}" === "stack") {{
        if (elements.length === 0) alert("当前栈为空！");
        else alert("当前栈顶元素 GetTop: " + elements[elements.length - 1]);
      }} else if ("{topic}" === "queue") {{
        alert(qCount === 0 ? "当前队列为空 (front == rear)" : `当前队列非空，首元素: ${{qData[qFront]}}，元素数: ${{qCount}}`);
      }} else if ("{topic}" === "string_kmp") {{
        alert(`模式串 T="ABAA" 的 next 数组为:\nnext[1]=0, next[2]=1, next[3]=1, next[4]=2\nnextval 数组为:\nnextval[1]=0, nextval[2]=1, nextval[3]=0, nextval[4]=2`);
      }} else {{
        const state = document.getElementById('manualDemoState');
        const title = document.getElementById('manualDemoTitle');
        const body = document.getElementById('manualDemoBody');
        if (state) state.innerText = `全部 ${{LESSON_STEPS.length}} 项`;
        if (title) title.innerText = '全部知识点';
        if (body) body.innerText = LESSON_STEPS.map((step, idx) => `${{idx + 1}}. ${{step.title}}`).join('；');
      }}
    }}
    function renderManualLessonStep() {{
      const step = LESSON_STEPS[manualLessonStep];
      const state = document.getElementById('manualDemoState');
      const title = document.getElementById('manualDemoTitle');
      const body = document.getElementById('manualDemoBody');
      if (!step) {{ resetManualLessonDemo(); return; }}
      if (state) state.innerText = `${{String(manualLessonStep + 1).padStart(2, '0')}} / ${{String(LESSON_STEPS.length).padStart(2, '0')}}`;
      if (title) title.innerText = step.title;
      if (body) body.innerText = step.output ? `前置约束: ${{step.input}}  ➔  推演结论: ${{step.output}}` : step.title;
    }}
    function resetManualLessonDemo() {{
      manualLessonStep = -1;
      const state = document.getElementById('manualDemoState');
      const title = document.getElementById('manualDemoTitle');
      const body = document.getElementById('manualDemoBody');
      if (state) state.innerText = '未开始';
      if (title) title.innerText = '请选择“查看下一知识点”';
      if (body) body.innerText = '这里的操作不会改变课程画面、旁白或播放进度。';
    }}
    function manualReset() {{
      if ("{topic}" === "lesson") {{ resetManualLessonDemo(); return; }}
      initStage();
      const fs = document.getElementById('flowStream');
      if (fs) fs.innerHTML = '<span class="flow-empty">[ 暂无出栈 ]</span>';
      const vb = document.getElementById('verdictBanner');
      if (vb) vb.style.display = 'none';
    }}

    // Init
    updateProgressUI();
    initStage();
    resetManualLessonDemo();
  </script>
</body>
</html>
"""


def process_note_file(
    note_path: Path,
    prod_base_dir: Path | None = None,
    html_dest_dir: Path | None = None,
    profile: dict | None = None,
    tts_config: dict[str, object] | None = None,
) -> dict:
    """Process a single note file and generate all Hypit assets and HTML player inside the section directory."""
    if profile is None:
        profile = load_user_profile(note_path.parent)

    note_text = note_path.read_text(encoding="utf-8")
    info = parse_note(note_text)
    clean_stem = note_path.stem

    # If the note is not already in its section directory, copy it instead of
    # moving the caller's source file. Existing copies are left untouched.
    if note_path.parent.name == clean_stem:
        sec_dir = note_path.parent
    else:
        sec_dir = note_path.parent / clean_stem
        sec_dir.mkdir(parents=True, exist_ok=True)
        target_note = sec_dir / note_path.name
        if target_note.exists() and target_note.read_text(encoding="utf-8") != note_text:
            raise FileExistsError(f"Refusing to overwrite a different section note: {target_note}")
        if not target_note.exists():
            shutil.copy2(note_path, target_note)

    brief_content = generate_brief(info, profile)
    treatment_content = generate_treatment(info, profile)
    script_content = generate_script(info, profile)
    storyboard_content = generate_storyboard(info, profile)
    html_content = generate_html_player(info, profile, tts_config, sec_dir / ".course-notes-tts")

    # Write Hypit production assets directly into section folder
    (sec_dir / "BRIEF.md").write_text(brief_content, encoding="utf-8")
    (sec_dir / "TREATMENT.md").write_text(treatment_content, encoding="utf-8")
    (sec_dir / "SCRIPT.md").write_text(script_content, encoding="utf-8")
    (sec_dir / "STORYBOARD.md").write_text(storyboard_content, encoding="utf-8")

    # Write HTML player into section folder
    target_html_path = sec_dir / f"{clean_stem}_讲解视频演示.html"
    target_html_path.write_text(html_content, encoding="utf-8")

    # Optionally save an extra HTML copy in a caller-selected directory.
    if html_dest_dir:
        html_dest_dir.mkdir(parents=True, exist_ok=True)
        (html_dest_dir / target_html_path.name).write_text(html_content, encoding="utf-8")

    # If an external production base dir is specified, mirror assets there as well
    prod_dir = None
    if prod_base_dir:
        prod_dir = prod_base_dir / clean_stem
        prod_dir.mkdir(parents=True, exist_ok=True)
        (prod_dir / "BRIEF.md").write_text(brief_content, encoding="utf-8")
        (prod_dir / "TREATMENT.md").write_text(treatment_content, encoding="utf-8")
        (prod_dir / "SCRIPT.md").write_text(script_content, encoding="utf-8")
        (prod_dir / "STORYBOARD.md").write_text(storyboard_content, encoding="utf-8")
        (prod_dir / "index.html").write_text(html_content, encoding="utf-8")

    return {
        "title": info["title"],
        "sec_dir": sec_dir,
        "prod_dir": prod_dir or sec_dir,
        "html_path": target_html_path
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Hypit video production assets and interactive player from course notes.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--note", default=None, help="Path to a single markdown note file")
    source_group.add_argument("--chapter-dir", default=None, help="Process all markdown notes in a chapter directory")
    parser.add_argument("--out-dir", default=None, help="Optional external production directory (e.g. tmp/video_productions/productions)")
    parser.add_argument("--html-dest", default=None, help="Directory to save extra copy of interactive HTML players")
    parser.add_argument("--env-file", default=None, help="Optional path to a .env file containing local TTS settings")
    parser.add_argument("--audit", dest="audit", action="store_true", default=False, help="Run headless visual & alignment audit")
    parser.add_argument("--no-audit", dest="audit", action="store_false", help="Skip visual audit (default)")
    args = parser.parse_args()

    prod_base_dir = Path(args.out_dir).resolve() if args.out_dir else None

    EXCLUDED_MD_NAMES = {"brief.md", "treatment.md", "script.md", "storyboard.md", "style_profile.md", "readme.md"}

    if args.note:
        note_path = Path(args.note).resolve()
        if not note_path.exists():
            print(f"Error: Note file not found: {note_path}", file=sys.stderr)
            sys.exit(1)
        if note_path.name.lower() in EXCLUDED_MD_NAMES or note_path.name.startswith("00_"):
            print(f"Skipping non-lesson file: {note_path.name}")
            return 0

        profile = load_user_profile(note_path.parent)
        if profile:
            print(f"🎯 检测到考生画像：{profile['school']} · {profile['exam']} (初试倒计时 {profile['days_remaining']} 天)")
        else:
            print("ℹ️ 未检测到考生画像（或已跳过），自动按 408 通用标准流程执行（软降级模式）。")

        tts_config = load_tts_config(note_path.parent, Path(args.env_file) if args.env_file else None)
        print(f"🔊 Narration provider: {tts_config['provider']}")
        res = process_note_file(note_path, prod_base_dir, Path(args.html_dest).resolve() if args.html_dest else None, profile=profile, tts_config=tts_config)
        print(f"✅ Hypit assets & interactive player generated for [{res['title']}]:")
        print(f"   📁 Section folder: {res['sec_dir']}")
        print(f"   🌐 Interactive player: {res['html_path']}")

        if args.audit:
            audit_script = Path(__file__).parent / "audit_player.py"
            if audit_script.exists():
                print("\n🔍 Running automated visual & alignment audit...")
                audit_result = subprocess.run([sys.executable, str(audit_script), "--html", str(res["html_path"])])
                return audit_result.returncode
        return 0

    if args.chapter_dir:
        chap_dir = Path(args.chapter_dir).resolve()
        if not chap_dir.exists() or not chap_dir.is_dir():
            print(f"Error: Chapter directory not found: {chap_dir}", file=sys.stderr)
            sys.exit(1)

        def is_valid_note(p: Path) -> bool:
            if (
                p.suffix.lower() != ".md"
                or p.name.startswith("00_")
                or p.name.lower() in EXCLUDED_MD_NAMES
            ):
                return False
            # Nested lesson notes must live in a directory with the same stem.
            # This prevents references/*.md and other support documents from
            # being treated as lessons during chapter scans.
            return p.parent == chap_dir or p.parent.name == p.stem

        # Look for notes either in section subfolders (chap_dir/*/*.md) or flat (chap_dir/*.md)
        discovered = []
        for f in chap_dir.glob("*/*.md"):
            if is_valid_note(f):
                discovered.append(f)
        for f in chap_dir.glob("*.md"):
            if is_valid_note(f):
                if not any(d.stem == f.stem for d in discovered):
                    discovered.append(f)

        note_files = sorted(discovered, key=lambda p: p.stem)

        if not note_files:
            print(f"No section note markdown files found in: {chap_dir}", file=sys.stderr)
            return 1

        profile = load_user_profile(chap_dir)
        if profile:
            print(f"🎯 检测到考生画像：{profile['school']} · {profile['exam']} (初试倒计时 {profile['days_remaining']} 天)")
        else:
            print("ℹ️ 未检测到考生画像（或已跳过），自动按 408 通用标准流程执行（软降级模式）。")

        tts_config = load_tts_config(chap_dir, Path(args.env_file) if args.env_file else None)
        print(f"🚀 Batch generating Hypit video assets for {len(note_files)} lessons in [{chap_dir.name}]...")
        print(f"🔊 Narration provider: {tts_config['provider']}")

        for idx, note_path in enumerate(note_files, 1):
            res = process_note_file(note_path, prod_base_dir, Path(args.html_dest).resolve() if args.html_dest else None, profile=profile, tts_config=tts_config)
            print(f"  [{idx}/{len(note_files)}] {res['title']} ➔ {res['sec_dir'].name}")

        print(f"\n🎉 Batch production complete! All {len(note_files)} lessons now have Hypit assets & interactive players.")

        if args.audit:
            audit_script = Path(__file__).parent / "audit_player.py"
            if audit_script.exists():
                print("\n🔍 Running automated visual & alignment audit across chapter...")
                audit_result = subprocess.run([sys.executable, str(audit_script), "--chapter-dir", str(chap_dir)])
                return audit_result.returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
