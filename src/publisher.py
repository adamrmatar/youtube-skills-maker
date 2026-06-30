import os
import shutil
import subprocess
import yaml
from pathlib import Path
from git import Repo

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
