from pathlib import Path
from src.adapters.base import BaseAdapter

class CopilotAdapter(BaseAdapter):
    @property
    def platform_name(self) -> str:
        return "copilot"
        
    def adapt(self, skill_dir: Path, output_platform_dir: Path, metadata: dict) -> Path:
        platform_dir = output_platform_dir / self.platform_name
        platform_dir.mkdir(parents=True, exist_ok=True)
        
        name = metadata.get("name", skill_dir.name)
        description = metadata.get("description", "")
        
        copilot_path = platform_dir / f"{name}.instructions.md"
        
        # Read the core skill body
        with open(skill_dir / "skill.md", "r", encoding="utf-8") as f:
            skill_body = f.read()
            
        combined_content = [
            f"# Copilot Instructions: {name.replace('-', ' ').title()}",
            f"Description: {description}\n",
            skill_body,
            "\n## Reference Guides"
        ]
        
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.glob("*.md")):
                title = ref_file.stem.replace("_", " ").title()
                with open(ref_file, "r", encoding="utf-8") as rf:
                    content = rf.read()
                combined_content.append(f"\n### {title}\n\n{content}")
                
        full_content = "\n".join(combined_content)
        
        with open(copilot_path, "w", encoding="utf-8") as f:
            f.write(full_content)
            
        return platform_dir
        
    def install_instructions(self, skill_name: str) -> str:
        return f"Copy `platforms/copilot/{skill_name}.instructions.md` to your project's `.github/instructions/` directory."
