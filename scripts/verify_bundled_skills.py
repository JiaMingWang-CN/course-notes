"""Offline integrity check for the course-notes bundled video skills."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "references" / "hyperframes-skills"
SKILLS = (
    "hyperframes", "hyperframes-animation", "hyperframes-audio",
    "hyperframes-cli", "hyperframes-core", "hyperframes-creative",
    "hyperframes-keyframes", "hyperframes-registry", "hyperframes-studio",
    "media-use", "faceless-explainer", "general-video",
)


def main() -> int:
    missing = [str(BUNDLE / name / "SKILL.md") for name in SKILLS
               if not (BUNDLE / name / "SKILL.md").is_file()]
    missing += [str(BUNDLE / name) for name in ("LICENSE", "PROVENANCE.md")
                if not (BUNDLE / name).is_file()]

    for doc in BUNDLE.rglob("*.md"):
        text = doc.read_text(encoding="utf-8")
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
            path = target.split("#", 1)[0]
            if (path and not path.startswith(("http:", "https:", "mailto:", "/"))
                    and "<" not in path and " " not in path
                    and not (doc.parent / path).exists()):
                missing.append(f"{doc}: {path}")

    for source in BUNDLE.rglob("*.mjs"):
        text = source.read_text(encoding="utf-8", errors="replace")
        for target in re.findall(
            r"(?:from\s*|import\s*\(|require\s*\()\s*['\"](\.{1,2}/[^'\"]+)['\"]", text
        ):
            path = source.parent / target
            if not any(candidate.exists() for candidate in
                       (path, path.with_suffix(".mjs"), path.with_suffix(".js"))):
                missing.append(f"{source}: {target}")

    for item in missing:
        print(f"MISSING {item}")
    if missing:
        return 1
    print(f"Bundled skills OK: {len(SKILLS)} entry files, local links and imports resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
