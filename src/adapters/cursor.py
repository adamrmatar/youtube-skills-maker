from pathlib import Path
from src.adapters.base import BaseAdapter

class CursorAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "cursor"
        
    def adapt(self, skill_dir: Path, output_platform_dir: Path, metadata: dict) -> Path:
        platform_dir = output_platform_dir / self.platform_name
        platform_dir.mkdir(parents=True, exist_ok=True)
        
        name = metadata.get("name", skill_dir.name)
        description = metadata.get("description", "").replace("\n", " ").strip()
        
        # Cursor rules (.mdc) must be placed in .cursor/rules/{name}.mdc
        mdc_path = platform_dir / f"{name}.mdc"
        
        # Read the core skill body
        with open(skill_dir / "skill.md", "r", encoding="utf-8") as f:
            skill_body = f.read()
            
        # Concatenate references because Cursor rules are single-file
        combined_content = [skill_body, "\n\n# Supporting Documentation"]
        
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.glob("*.md")):
                title = ref_file.stem.replace("_", " ").title()
                with open(ref_file, "r", encoding="utf-8") as rf:
                    content = rf.read()
                combined_content.append(f"\n## {title}\n\n{content}")
                
        full_body = "\n".join(combined_content)
        
        # Format the MDC file
        mdc_content = f"""---
description: {description}
globs: *
---

# {name.replace('-', ' ').title()}

{full_body}
"""
        with open(mdc_path, "w", encoding="utf-8") as f:
            f.write(mdc_content)
            
        return platform_dir
        
    def install_instructions(self, skill_name: str) -> str:
        return f"Copy `platforms/cursor/{skill_name}.mdc` to your project's `.cursor/rules/` directory."
