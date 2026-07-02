#!/usr/bin/env python3
"""
Convert our pipeline's skill format into vercel-labs/skills-compatible SKILL.md files.

Input format (data/ai-skills/skills/<slug>/):
  skill.md        – body content (markdown, NO frontmatter)
  metadata.yaml   – name, description, keywords, difficulty, sources, ...
  platforms/      – one file per supported platform (e.g., antigravity, cursor, claude)
  references/     – extra markdown reference files

Output format (data/ikf-skills/skills/<slug>/):
  SKILL.md        – YAML frontmatter + merged body content (vercel-skills compatible)
  references/     – copied as-is for agents to read when needed
"""

import os
import re
import shutil
import sys
from pathlib import Path

import yaml

SRC_ROOT = Path(__file__).parent.parent / "data" / "ai-skills" / "skills"
DST_ROOT = Path(__file__).parent.parent / "data" / "ikf-skills" / "skills"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower().strip()).strip("-")


def load_metadata(skill_dir: Path) -> dict:
    meta_path = skill_dir / "metadata.yaml"
    if meta_path.exists():
        with open(meta_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_skill_body(skill_dir: Path) -> str:
    body_path = skill_dir / "skill.md"
    if body_path.exists():
        with open(body_path) as f:
            content = f.read()
        # Strip leading h1 if metadata already provides a name
        content = re.sub(r"^# .+\n\n?", "", content, count=1)
        return content.strip()
    return ""


def build_skill_md(meta: dict, body: str, platforms: list[str]) -> str:
    """Build a SKILL.md with YAML frontmatter compatible with vercel-labs/skills."""
    name = meta.get("name", "Unknown Skill")
    description = meta.get("description", "")
    keywords = meta.get("keywords", [])

    # Build description trigger line: agents scan this to decide when to activate
    trigger_description = description
    if platforms:
        platform_str = ", ".join(sorted(platforms))
        trigger_description = f"{description} [Supported agents: {platform_str}]"

    frontmatter = {
        "name": name,
        "description": trigger_description,
    }
    if keywords:
        frontmatter["tags"] = keywords

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()

    # Build body: title + description blurb + original content
    sections = [f"# {name}", "", f"> {description}", "", body]

    # Add sources section if available
    sources = meta.get("sources", [])
    if sources:
        sections.append("\n## 📺 Source Videos\n")
        for src in sources:
            title = src.get("title", "")
            link = src.get("link", "")
            channel = src.get("channel", "")
            if link:
                line = f"- [{title}]({link})"
                if channel:
                    line += f" — {channel}"
            else:
                line = f"- {title}"
                if channel:
                    line += f" — {channel}"
            sections.append(line)

    # Difficulty badge
    difficulty = meta.get("difficulty", "")
    if difficulty:
        sections.append(f"\n**Difficulty**: {difficulty.capitalize()}")

    # Prerequisites
    prereqs = meta.get("prerequisites", [])
    if prereqs:
        sections.append("\n## Prerequisites\n")
        for p in prereqs:
            sections.append(f"- {p}")

    full_body = "\n".join(sections).strip()

    return f"---\n{fm_str}\n---\n\n{full_body}\n"


def convert_skill(skill_dir: Path, dst_root: Path) -> Path:
    slug = skill_dir.name
    meta = load_metadata(skill_dir)
    body = load_skill_body(skill_dir)

    # Collect platforms
    platforms_dir = skill_dir / "platforms"
    platforms = []
    if platforms_dir.exists():
        platforms = [p.name for p in platforms_dir.iterdir() if p.is_file()]

    skill_md = build_skill_md(meta, body, platforms)

    # Write output
    out_dir = dst_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # Copy references folder if it exists
    refs_src = skill_dir / "references"
    refs_dst = out_dir / "references"
    if refs_src.exists():
        if refs_dst.exists():
            shutil.rmtree(refs_dst)
        shutil.copytree(refs_src, refs_dst)

    print(f"  ✅ {slug}")
    return out_dir


def main():
    if not SRC_ROOT.exists():
        print(f"ERROR: Source skills directory not found: {SRC_ROOT}", file=sys.stderr)
        sys.exit(1)

    DST_ROOT.mkdir(parents=True, exist_ok=True)

    skill_dirs = [d for d in SRC_ROOT.iterdir() if d.is_dir()]
    if not skill_dirs:
        print("No skills found to convert.")
        return

    print(f"Converting {len(skill_dirs)} skill(s) → vercel-skills format...")
    for skill_dir in sorted(skill_dirs):
        convert_skill(skill_dir, DST_ROOT)

    print(f"\nDone! Output at: {DST_ROOT}")


if __name__ == "__main__":
    main()
