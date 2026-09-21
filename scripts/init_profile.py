#!/usr/bin/env python3
"""course-notes helper: Initialize candidate profile and target school exam intelligence.

Usage:
  # With explicit arguments:
  python init_profile.py --school "浙江大学" --exam "845 计算机专业基础" --major "0854 电子信息/软件工程" --lang "C/C++" --stage "强化刷题"

  # Standard 408 preset:
  python init_profile.py --exam 408

  # Skip profile setup (soft fallback to default 408):
  python init_profile.py --skip

Outputs:
  - <workspace_root>/user-profile/PROFILE.md
  - <workspace_root>/user-profile/EXAM_INTELLIGENCE.md
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# Force UTF-8 encoding on Windows
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def calculate_exam_target(year: int | None = None) -> tuple[datetime.date, int]:
    """Calculate the estimated graduate entrance exam date (late December) and countdown days."""
    today = datetime.date.today()
    target_year = year or today.year

    # If today is past December 25th of the target year, target next year
    if today > datetime.date(target_year, 12, 25):
        target_year += 1

    # Typical exam date is the Saturday of late December (Dec 19 - Dec 26)
    # Finding the second-to-last or last full weekend
    dec25 = datetime.date(target_year, 12, 25)
    # Saturday is weekday 5
    offset = (dec25.weekday() - 5) % 7
    exam_date = dec25 - datetime.timedelta(days=offset)
    if exam_date.day < 20:
        exam_date += datetime.timedelta(days=7)

    days_remaining = max(0, (exam_date - today).days)
    return exam_date, days_remaining


SCHOOL_INTELLIGENCE_BASE = {
    "浙江大学": {
        "code": "845 / 408",
        "default_exam": "845 计算机专业基础",
        "major": "0812 计科 / 0854 软工专硕",
        "textbook": "何钦铭《数据结构》、严蔚敏版教材",
        "traits": "注重算法设计与综合分析题，对代码书写规范要求极高，常结合工程实际场景出题。",
        "focus_chapters": "树与二叉树、图论最短路径/拓扑排序、散列表与高级排序算法",
        "trap_advice": "浙大自命题对算法时间复杂度推导和空间分配特别严苛，大题严禁使用伪代码偷懒，必须规范声明指针与边界。"
    },
    "清华大学": {
        "code": "912",
        "default_exam": "912 计算机专业基础综合",
        "major": "0812 计算机科学与技术 / 0854 电子信息",
        "textbook": "邓俊辉《数据结构(C++语言版)》",
        "traits": "考研界难度天花板，大纲涵盖数据结构、计组、操作系统、网络四门，数据结构深度融合算法推导与复杂度下界证明。",
        "focus_chapters": "平衡二叉搜索树(AVL/Splay/Red-Black)、B-树/B+树、KMP算法下界、并查集与高级图论",
        "trap_advice": "清华极其注重 C++ 面对对象实现细节与常数优化，证明题与分治复杂度分析分值极高。"
    },
    "北京大学": {
        "code": "839 / 408",
        "default_exam": "408 / 839 计算机专业综合",
        "major": "0812 计科 / 0854 软工",
        "textbook": "张铭《数据结构与算法》、严蔚敏版教材",
        "traits": "重视算法逻辑严谨性与离散数学基础，注重数据结构的抽象数据类型（ADT）与数学归纳推导。",
        "focus_chapters": "递归与分治策略、树与二叉树同构/遍历推导、动态规划与贪心",
        "trap_advice": "注意递归边界条件推演，选择题陷阱多集中在森林与二叉树转换及先根/后根顺序对比。"
    },
    "复旦大学": {
        "code": "408 / 960",
        "default_exam": "408 计算机学科专业基础",
        "major": "0812 计算机科学与技术 / 0854 软件工程",
        "textbook": "王道 408 系列、严蔚敏《数据结构》",
        "traits": "全面采用全国统考 408，考查面极为广阔，重视基础概念的扎实程度与大题手写代码的稳健性。",
        "focus_chapters": "线性表综合应用、KMP 模式匹配、二叉树与 Huffman 树、图的遍历与最小生成树",
        "trap_advice": "408 试卷题量巨大，要求答题速度极快；必须熟练掌握各种秒杀结论（如卡特兰数、完全二叉树编号公式）。"
    },
    "中国科学技术大学": {
        "code": "408 / 834",
        "default_exam": "408 计算机学科专业基础",
        "major": "0812 计算机 / 0854 电子信息",
        "textbook": "严蔚敏《数据结构》、王道 408",
        "traits": "回归 408 统考，强化数学推理底蕴，对算法分析的渐近边界和排序稳定性有高要求。",
        "focus_chapters": "内部排序对比与下界推导、散列冲突解决策略、图论算法手算过程",
        "trap_advice": "大题务必写清设计思想、核心代码及时间/空间复杂度分析，三者缺一不可。"
    },
    "北京航空航天大学": {
        "code": "961 / 408",
        "default_exam": "961 计算机基础综合",
        "major": "0812 计科 / 0854 电子信息",
        "textbook": "唐发根《数据结构》",
        "traits": "特色自命题包含计组、OS、数据结构，题目风格偏向硬核工科，注重结构体设计与底层内存交互。",
        "focus_chapters": "线性表链式存储、二叉树遍历非递归实现、哈夫曼编码与网络流应用",
        "trap_advice": "大题手写代码注重内存释放（free）与指针防野指针处理，注重工程防御性编程。"
    },
    "华中科技大学": {
        "code": "834 / 408",
        "default_exam": "834 计算机专业基础综合",
        "major": "0812 计算机 / 0854 软件工程",
        "textbook": "严蔚敏《数据结构》",
        "traits": "题目注重逻辑推演和综合运用，历年真题重复率较高，高频考点十分清晰。",
        "focus_chapters": "栈与队列应用（表达式求值/递归模拟）、二叉线索树、拓扑排序与关键路径",
        "trap_advice": "线索二叉树左右标志位（0/1 指向子节点还是前驱/后继）是华科极其容易失分的经典考点。"
    }
}


def get_school_intelligence(school_name: str, exam_category: str) -> dict:
    """Generate detailed exam intelligence tailored to the school and exam category."""
    matched_school = None
    for k, v in SCHOOL_INTELLIGENCE_BASE.items():
        if k in school_name or school_name in k:
            matched_school = v
            break

    is_408 = "408" in exam_category or "统考" in exam_category or (matched_school and matched_school["code"] == "408")

    if matched_school:
        return {
            "school": school_name,
            "exam_name": exam_category or matched_school["default_exam"],
            "textbook": matched_school["textbook"],
            "traits": matched_school["traits"],
            "focus_chapters": matched_school["focus_chapters"],
            "trap_advice": matched_school["trap_advice"],
            "is_408": is_408
        }

    # Generic or standard 408 / school self-test fallback
    return {
        "school": school_name or "全国统考院校",
        "exam_name": exam_category or ("408 计算机学科专业基础" if is_408 else "计算机专业基础综合自命题"),
        "textbook": "王道 408 数据结构单科、严蔚敏《数据结构》",
        "traits": "紧扣大纲基本考点，强调概念清晰、算法规范手写，选择题考查陷阱多、大题考查综合运用。",
        "focus_chapters": "栈与队列、串与KMP算法、二叉树与遍历性质、图论经典算法(Dijkstra/Prim)、内部排序",
        "trap_advice": "务必强化基础定义（如二叉树深度与高度区分、完全二叉树编号公式、0-based vs 1-based 数组边界），答大题时格式务必规范。",
        "is_408": is_408
    }


def find_workspace_root() -> Path:
    """Locate the workspace root directory (which contains .agents)."""
    cur = Path(__file__).resolve().parent
    while cur.parent != cur:
        if (cur / ".agents").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()


UI_STYLE_MAP = {
    "calm_textbook": {
        "key": "calm_textbook",
        "name": "温和教材 (Calm Textbook)",
        "desc": "暖白与浅灰绿背景、深墨绿标题和控制、少量琥珀易错提醒；柔和边界与清晰状态反馈"
    }
}


def init_profile(
    school: str = "",
    exam: str = "",
    major: str = "",
    lang: str = "C/C++",
    stage: str = "强化冲刺",
    ui_style: str = "calm_textbook",
    year: int | None = None,
    skip: bool = False
) -> int:
    """Initialize or skip the candidate profile and exam intelligence."""
    workspace_root = find_workspace_root()
    profile_dir = workspace_root / "user-profile"

    if skip:
        print("⏩ 已选择跳过考生画像定制。后续流水线将无缝遵循 408 通用标准流程（软降级模式）。")
        return 0

    exam_date, days_remaining = calculate_exam_target(year)
    clean_school = school.strip() or "全国统考"
    clean_exam = exam.strip() or "408 计算机学科专业基础"
    clean_major = major.strip() or "0812 计算机科学与技术 / 0854 电子信息"
    clean_lang = lang.strip() or "C/C++"
    clean_stage = stage.strip() or "二轮强化与真题冲刺"
    clean_ui_style = ui_style.strip().lower()
    if clean_ui_style not in UI_STYLE_MAP:
        clean_ui_style = "calm_textbook"
    style_info = UI_STYLE_MAP[clean_ui_style]

    intel = get_school_intelligence(clean_school, clean_exam)

    profile_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate PROFILE.md
    profile_content = f"""# 考生备考画像与个性化配置 (Candidate Profile)

> 📅 **建档时间**：{datetime.date.today().isoformat()}
> 🎯 **目标院校**：{clean_school}
> 📚 **考试科目**：{intel['exam_name']}
> 🎓 **报考专业/方向**：{clean_major}
> 💻 **代码偏好**：{clean_lang}
> ⏳ **备考阶段**：{clean_stage}
> 🎨 **微课UI美学风格**：{style_info['name']} (`{clean_ui_style}`)
> 🔥 **考研初试预估**：{exam_date.strftime('%Y年%m月%d日')}（剩余 **{days_remaining}** 天）

---

## 核心参数规范表

| 配置项 | 参数值 | 对下游产物的影响 |
|---|---|---|
| **target_school** | `{clean_school}` | 注入微课播放器 HUD 徽标、讲师开场白及院校专属避坑提示 |
| **exam_category** | `{intel['exam_name']}` | 确定考查重点倾向（408 统考广度 vs 院校自命题算法深度） |
| **major_direction** | `{clean_major}` | 侧重学术算法推导或工程实用实现 |
| **coding_language** | `{clean_lang}` | 规范笔记与沙盘代码语法规范（纯 C 指针 vs C++ 引用与 STL） |
| **review_stage** | `{clean_stage}` | 控制微课解说深度：基础概念夯实 vs 冲刺重点回顾 |
| **ui_style** | `{clean_ui_style}` | 微课固定采用温和教材风格，不提供其他主题或运行时换肤 |
| **days_remaining** | `{days_remaining}` | 渲染至微课右上角考研倒计时看板 |

---

## 备考执行方针
1. **时间优先**：距离预估考试日期剩余 {days_remaining} 天，减少冗余铺垫，聚焦核心概念与适用条件；
2. **代码风格统一**：采用 `{clean_lang}` 规范代码，并明确边界、输入输出与复杂度；
3. **闭环验证**：每小节结合例题或推演检查理解，记录仍需核实的内容；
4. **视觉与交互舒适度**：微课播放器固定渲染 `{style_info['name']}`，用颜色、文字状态和读数共同反馈学习进度。
"""

    profile_path = profile_dir / "PROFILE.md"
    profile_path.write_text(profile_content, encoding="utf-8")

    # 2. Generate EXAM_INTELLIGENCE.md
    intelligence_content = f"""# {clean_school} · {intel['exam_name']} 专项考情白皮书

> 📊 **情报归档级别**：重点推荐 / 核心情报
> 🎯 **对应院校**：{clean_school}
> 📝 **科目代号**：{intel['exam_name']}
> ⏱️ **倒计时状态**：距离初试尚余 **{days_remaining}** 天

---

## 一、科目参考信息（内置预设，须以院校当年官方信息核实）
* **参考教材**：{intel['textbook']}
* **命题风格参考**：{intel['traits']}
* **统考/自命题参考**：{'可能采用国家统一命题（408 统考卷）' if intel['is_408'] else '可能采用院校自主命题卷（自命题）'}

---

## 二、数据结构重点模块参考
* **核心章节清单**：{intel['focus_chapters']}
* **备考策略指导**：
  1. 重点章节须达到代码级盲写（如手写单链表逆置、二叉树先中后序及层序遍历、BFS/DFS最短路径、快速排序划分）；
  2. 针对非重点章节（如稀疏矩阵三元组压缩、KMP 算法深度数学下界），掌握核心结论与手算推导即可，避免浪费冲刺黄金时间。

---

## 三、院校专属易错避坑与命题陷阱预警
* **易错点参考**：
  > {intel['trap_advice']}
* **手写算法代码规范红线**：
  - 必须写清函数入口参数、返回值含义及边界异常退出条件；
  - 核心算法必须在末尾清晰写明：**时间复杂度 $O(\\cdot)$** 与 **空间复杂度 $O(\\cdot)$**（占分 2~3 分）；
  - 严禁擅自使用高级语言现成库函数（如 `std::sort()`、`std::stack`），除非题目明确允许。
"""

    intelligence_path = profile_dir / "EXAM_INTELLIGENCE.md"
    intelligence_path.write_text(intelligence_content, encoding="utf-8")

    print("=" * 65)
    print(f"🎉 考生画像与考情情报建档成功！")
    print(f"🏫 目标院校：{clean_school} | 📚 科目：{intel['exam_name']}")
    print(f"🎨 微课 UI 风格：{style_info['name']}")
    print(f"⏳ 考研初试预估：{exam_date} (倒计时: {days_remaining} 天)")
    print(f"📁 画像文件：{profile_path.relative_to(workspace_root)}")
    print(f"📁 考情白皮书：{intelligence_path.relative_to(workspace_root)}")
    print("=" * 65)
    print("💡 后续生成笔记或微课时可读取此画像；院校考情预设请以当年官方信息核实。")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Init candidate profile and exam intelligence for course-notes.")
    parser.add_argument("--school", default="", help="Target university name (e.g. 浙江大学, 清华大学)")
    parser.add_argument("--exam", default="", help="Exam subject name/code (e.g. 408, 845, 912)")
    parser.add_argument("--major", default="", help="Target major/direction (e.g. 0854 电子信息/软件工程)")
    parser.add_argument("--lang", default="C/C++", help="Preferred coding language (e.g. C/C++, C++ STL)")
    parser.add_argument("--stage", default="强化冲刺", help="Review stage (e.g. 基础夯实, 强化冲刺, 考前真题)")
    parser.add_argument("--ui-style", "--theme", dest="ui_style", choices=list(UI_STYLE_MAP.keys()), default="calm_textbook", help="Video player UI style (only calm_textbook is supported)")
    parser.add_argument("--year", type=int, default=None, help="Target exam year (e.g. 2026)")
    parser.add_argument("--skip", action="store_true", help="Skip candidate profile setup (soft fallback)")
    args = parser.parse_args()

    # If no flags provided at all, and running in non-skip mode:
    if not args.skip and not args.school and not args.exam:
        if sys.stdin.isatty():
            print("=== 🎓 course-notes 考研备考目标与用户画像快速建档 (按回车使用默认值) ===")
            school_in = input("1. 目标院校 [全国统考 408]: ").strip()
            exam_in = input("2. 考试科目 [408 计算机学科专业基础]: ").strip()
            major_in = input("3. 报考专业 [0854 电子信息/软件工程]: ").strip()
            lang_in = input("4. 代码语言偏好 [C/C++]: ").strip() or "C/C++"
            stage_in = input("5. 当前复习阶段 [强化冲刺]: ").strip() or "强化冲刺"
            print("6. 微课播放器视觉风格：温和教材 (calm_textbook，固定默认)")
            ui_style_in = "calm_textbook"
            return init_profile(school=school_in, exam=exam_in, major=major_in, lang=lang_in, stage=stage_in, ui_style=ui_style_in, year=args.year)
        else:
            print(
                "ERROR: profile details were not provided in a non-interactive session. "
                "Ask the user first, then pass explicit options, or use --skip.",
                file=sys.stderr,
            )
            return 2

    return init_profile(
        school=args.school,
        exam=args.exam,
        major=args.major,
        lang=args.lang,
        stage=args.stage,
        ui_style=args.ui_style,
        year=args.year,
        skip=args.skip
    )


if __name__ == "__main__":
    sys.exit(main())
