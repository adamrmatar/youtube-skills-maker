from pathlib import Path
from src.adapters.base import BaseAdapter

class ClaudeAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "claude"
        
    def adapt(self, skill_dir: Path, output_platform_dir: Path, metadata: dict) -> Path:
        platform_dir = output_platform_dir / self.platform_name
        platform_dir.mkdir(parents=True, exist_ok=True)
        
        name = metadata.get("name", skill_dir.name)
        description = metadata.get("description", "")
        
        claude_path = platform_dir / "CLAUDE.md"
        
        # Read the core skill body
        with open(skill_dir / "skill.md", "r", encoding="utf-8") as f:
            skill_body = f.read()
            
        # Combine skill body with reference sections
        combined_content = [
            f"# Claude Code Custom Instructions - {name.replace('-', ' ').title()}",
            f"> {description}\n",
            skill_body,
            "\n# Detailed Guidelines"
        ]
        
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.glob("*.md")):
                title = ref_file.stem.replace("_", " ").title()
                with open(ref_file, "r", encoding="utf-8") as rf:
                    content = rf.read()
                combined_content.append(f"\n## {title}\n\n{content}")
                
        full_content = "\n".join(combined_content)
        
        with open(claude_path, "w", encoding="utf-8") as f:
            f.write(full_content)
            
        return platform_dir
        
    def install_instructions(self, skill_name: str) -> str:
        return "Append the contents of `platforms/claude/CLAUDE.md` to the target project's `CLAUDE.md` file."
