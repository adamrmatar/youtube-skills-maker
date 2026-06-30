import shutil
from pathlib import Path
from src.adapters.base import BaseAdapter

class AntigravityAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "antigravity"
        
    def adapt(self, skill_dir: Path, output_platform_dir: Path, metadata: dict) -> Path:
        platform_dir = output_platform_dir / self.platform_name
        platform_dir.mkdir(parents=True, exist_ok=True)
        
        # Write SKILL.md with YAML frontmatter
        skill_md_path = platform_dir / "SKILL.md"
        
        name = metadata.get("name", skill_dir.name)
        description = metadata.get("description", "")
        
        # Format multi-line description safely for YAML
        desc_formatted = description.replace("\n", " ").strip()
        
        # Core skill contents
        with open(skill_dir / "skill.md", "r", encoding="utf-8") as f:
            skill_body = f.read()
            
        frontmatter = f"""---
name: {name}
description: >-
  {desc_formatted}
---

{skill_body}
"""
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            
        # Copy references/ directory
        src_refs = skill_dir / "references"
        if src_refs.exists():
            dest_refs = platform_dir / "references"
            if dest_refs.exists():
                shutil.rmtree(dest_refs)
            shutil.copytree(src_refs, dest_refs)
            
        return platform_dir
        
    def install_instructions(self, skill_name: str) -> str:
        return f"Copy the contents of `platforms/antigravity/` to `~/.gemini/config/skills/{skill_name}/`."
