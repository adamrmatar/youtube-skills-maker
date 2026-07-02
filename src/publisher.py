import os
import re
import shutil
import subprocess
import sys
import yaml
from pathlib import Path
from git import Repo

# ---------------------------------------------------------------------------
# Vercel-skills conversion helpers (mirrors scripts/convert_to_vercel_skills.py)
# ---------------------------------------------------------------------------

def _build_skill_md(meta: dict, body: str, platforms: list) -> str:
    """Build a SKILL.md with YAML frontmatter compatible with npx skills."""
    name = meta.get("name", "Unknown Skill")
    description = meta.get("description", "")
    keywords = meta.get("keywords", [])

    frontmatter = {"name": name, "description": description}
    if keywords:
        frontmatter["tags"] = keywords

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()

    body_clean = re.sub(r"^# .+\n\n?", "", body, count=1).strip()
    sections = [f"# {name}", "", f"> {description}", "", body_clean]

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
                line = f"- {title}" + (f" — {channel}" if channel else "")
            sections.append(line)

    difficulty = meta.get("difficulty", "")
    if difficulty:
        sections.append(f"\n**Difficulty**: {difficulty.capitalize()}")

    prereqs = meta.get("prerequisites", [])
    if prereqs:
        sections.append("\n## Prerequisites\n")
        for p in prereqs:
            sections.append(f"- {p}")

    full_body = "\n".join(sections).strip()
    return f"---\n{fm_str}\n---\n\n{full_body}\n"


def _convert_skill_to_vercel(skill_dir: Path, dst_root: Path) -> None:
    """Convert one pipeline skill folder → vercel-compatible SKILL.md."""
    meta_path = skill_dir / "metadata.yaml"
    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = yaml.safe_load(f) or {}

    body = ""
    body_path = skill_dir / "skill.md"
    if body_path.exists():
        with open(body_path) as f:
            body = f.read()

    platforms_dir = skill_dir / "platforms"
    platforms = [p.name for p in platforms_dir.iterdir() if p.is_file()] if platforms_dir.exists() else []

    skill_md = _build_skill_md(meta, body, platforms)

    out_dir = dst_root / skill_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    refs_src = skill_dir / "references"
    refs_dst = out_dir / "references"
    if refs_src.exists():
        if refs_dst.exists():
            shutil.rmtree(refs_dst)
        shutil.copytree(refs_src, refs_dst)

def init_or_clone_repo(repo_slug, local_path):
    """
    Clones the repository if it exists, or creates it on GitHub using `gh` CLI if it doesn't,
    then initializes a local Git workspace.
    """
    local_path = Path(local_path)
    
    # 1. If it already exists locally and has a .git directory, just pull
    if (local_path / ".git").exists():
        try:
            repo = Repo(local_path)
            print(f"[Publisher] Local repo found at {local_path}. Pulling latest changes...")
            repo.remotes.origin.pull()
            return repo
        except Exception as e:
            print(f"[Publisher] Local repository pull failed: {e}. Re-cloning.")
            shutil.rmtree(local_path)

    # 1.5 If local path exists but has no .git directory, clean it up so we can clone into it cleanly
    if local_path.exists() and not (local_path / ".git").exists():
        print(f"[Publisher] Local path {local_path} exists but is not a Git repo. Cleaning up...")
        if local_path.is_dir():
            shutil.rmtree(local_path)
        else:
            local_path.unlink()

    # 2. Check if repo exists on GitHub. If not, create it.
    print(f"[Publisher] Checking if GitHub repo 'github.com/{repo_slug}' exists...")
    check_cmd = ["gh", "repo", "view", repo_slug]
    result = subprocess.run(check_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[Publisher] Repository '{repo_slug}' not found on GitHub. Creating it...")
        # Create public repo (required for skills.sh registry discovery)
        create_cmd = ["gh", "repo", "create", repo_slug, "--public", "--confirm"]
        create_res = subprocess.run(create_cmd, capture_output=True, text=True)
        if create_res.returncode != 0:
            print(f"[Publisher] Error creating GitHub repo: {create_res.stderr}")
            # Try fallback: just initialize locally
            local_path.mkdir(parents=True, exist_ok=True)
            repo = Repo.init(local_path)
            return repo
            
    # 3. Clone the repo locally
    print(f"[Publisher] Cloning 'github.com/{repo_slug}' to {local_path}...")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    
    clone_cmd = ["gh", "repo", "clone", repo_slug, str(local_path)]
    clone_res = subprocess.run(clone_cmd, capture_output=True, text=True)
    if clone_res.returncode != 0:
        print(f"[Publisher] Error cloning repo: {clone_res.stderr}")
        # Fallback to direct Git clone
        try:
            return Repo.clone_from(f"https://github.com/{repo_slug}.git", local_path)
        except Exception as e:
            print(f"[Publisher] Git clone fallback failed: {e}")
            local_path.mkdir(parents=True, exist_ok=True)
            return Repo.init(local_path)
            
    return Repo(local_path)

def publish_skills_to_github(repo_slug="adamrmatar/ai-skills", local_repo_path="data/ai-skills"):
    """
    Stages, commits, and pushes generated skills in the local_repo_path.
    """
    try:
        repo = init_or_clone_repo(repo_slug, local_repo_path)
    except Exception as e:
        print(f"[Publisher] Failed to initialize Git repository: {e}")
        return False

    dest_skills_path = Path(local_repo_path) / "skills"
    
    # Identify skills present
    skills_present = []
    if dest_skills_path.exists():
        skills_present = [item.name for item in dest_skills_path.iterdir() if item.is_dir()]

    # Generate root README.md index in target repo
    readme_path = Path(local_repo_path) / "README.md"
    readme_lines = [
        "# My AI Agent Skills\n",
        "A collection of custom AI agent skills generated automatically from curated videos on [25experts.com](https://25experts.com).\n",
        "These skills are compiled for multiple developer agents: Antigravity, Cursor, Claude Code, GitHub Copilot, and Windsurf.\n",
        "## 🛠️ Available Skills\n"
    ]
    
    if skills_present:
        for skill_name in sorted(skills_present):
            desc = ""
            meta_file = dest_skills_path / skill_name / "metadata.yaml"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = yaml.safe_load(f) or {}
                        desc = meta.get("description", "")
                except:
                    pass
            readme_lines.append(f"- **[{skill_name}](./skills/{skill_name}/README.md)**" + (f": {desc}" if desc else ""))
    else:
        readme_lines.append("No skills generated yet.")
        
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("\n".join(readme_lines))
    except Exception as e:
        print(f"[Publisher] Warning: Failed to write root README: {e}")

    # Stage all changes
    repo.git.add(A=True)
    
    if not repo.is_dirty(untracked_files=True):
        print("[Publisher] No changes detected in the repository. Skipping commit/push.")
        return True

    # Commit and Push
    commit_msg = f"feat(skills): Update AI skills ({', '.join(skills_present) if skills_present else 'general update'})"
    print(f"[Publisher] Committing changes: {commit_msg}")
    repo.index.commit(commit_msg)
    
    print("[Publisher] Pushing changes to GitHub...")
    try:
        origin = repo.remote(name="origin")
        origin.push()
        print("[Publisher] Successfully published skills to GitHub.")
        return True
    except Exception as e:
        print(f"[Publisher] Failed to push to GitHub: {e}")
        # Try pushing with subprocess git CLI
        try:
            print("[Publisher] Retrying push using Git CLI...")
            subprocess.run(["git", "push", "origin", "main"], cwd=str(local_repo_path), check=True)
            print("[Publisher] Successfully pushed using Git CLI.")
            return True
        except Exception as ex:
            print(f"[Publisher] Git CLI push retry failed: {ex}")
            return False


# ---------------------------------------------------------------------------
# Publish to TDH-Labs/i-know-kung-fu (vercel-skills compatible format)
# ---------------------------------------------------------------------------

def publish_to_ikf(
    src_skills_path: str = "data/ai-skills/skills",
    ikf_repo_slug: str = "TDH-Labs/i-know-kung-fu",
    ikf_local_path: str = "data/i-know-kung-fu",
) -> bool:
    """
    Convert all skills from the pipeline format to vercel-skills format
    and push them to TDH-Labs/i-know-kung-fu.
    """
    src_path = Path(src_skills_path)
    if not src_path.exists():
        print(f"[IKF Publisher] Source skills path not found: {src_path}")
        return False

    # Ensure the i-know-kung-fu repo is cloned locally
    try:
        repo = init_or_clone_repo(ikf_repo_slug, ikf_local_path)
    except Exception as e:
        print(f"[IKF Publisher] Failed to initialise repo: {e}")
        return False

    dst_skills = Path(ikf_local_path) / "skills"
    dst_skills.mkdir(parents=True, exist_ok=True)

    # Convert every skill
    skill_dirs = [d for d in src_path.iterdir() if d.is_dir()]
    converted = []
    for skill_dir in sorted(skill_dirs):
        try:
            _convert_skill_to_vercel(skill_dir, dst_skills)
            converted.append(skill_dir.name)
            print(f"[IKF Publisher]   ✅ Converted: {skill_dir.name}")
        except Exception as e:
            print(f"[IKF Publisher]   ⚠️  Failed to convert {skill_dir.name}: {e}")

    if not converted:
        print("[IKF Publisher] No skills converted — skipping push.")
        return True

    # Regenerate README in the ikf repo
    _write_ikf_readme(Path(ikf_local_path), dst_skills)

    # Stage, commit, push
    repo.git.add(A=True)
    if not repo.is_dirty(untracked_files=True):
        print("[IKF Publisher] No changes — skipping commit/push.")
        return True

    commit_msg = f"feat(skills): add/update {', '.join(converted)}"
    print(f"[IKF Publisher] Committing: {commit_msg}")
    repo.index.commit(commit_msg)

    try:
        repo.remote(name="origin").push()
        print("[IKF Publisher] ✅ Pushed to TDH-Labs/i-know-kung-fu")
        return True
    except Exception as e:
        print(f"[IKF Publisher] Push failed: {e}")
        try:
            subprocess.run(["git", "push", "origin", "main"], cwd=ikf_local_path, check=True)
            print("[IKF Publisher] ✅ Pushed via git CLI")
            return True
        except Exception as ex:
            print(f"[IKF Publisher] git CLI push failed: {ex}")
            return False


def _write_ikf_readme(repo_root: Path, skills_dir: Path) -> None:
    """Write a clean README.md for the i-know-kung-fu repo."""
    skills = sorted([d.name for d in skills_dir.iterdir() if d.is_dir()]) if skills_dir.exists() else []

    table_rows = []
    for slug in skills:
        skill_md_path = skills_dir / slug / "SKILL.md"
        desc = ""
        if skill_md_path.exists():
            content = skill_md_path.read_text()
            # Extract description from frontmatter
            m = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
            if m:
                desc = m.group(1).strip()
        table_rows.append(f"| [{slug}](./skills/{slug}/SKILL.md) | {desc} |")

    table = "\n".join(["| Skill | Description |", "|-------|-------------|" ] + table_rows)

    readme = f"""# I Know Kung Fu 🥋

> *"I know kung fu." — Neo, The Matrix*

AI skills distilled from expert video content, installable in any AI coding agent via the [skills CLI](https://skills.sh).

## Install a skill

```bash
# Install a specific skill
npx skills add TDH-Labs/i-know-kung-fu@<skill-name>

# Browse all available skills  
npx skills find --owner TDH-Labs
```

## Available Skills ({len(skills)} total)

{table}

## Supported Agents

Works with Antigravity, Claude Code, Cursor, Windsurf, Copilot, Gemini CLI, and [many more](https://skills.sh).

## License

MIT
"""
    (repo_root / "README.md").write_text(readme, encoding="utf-8")
