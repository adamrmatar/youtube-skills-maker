import yaml
import shutil
from pathlib import Path
from src.adapters import get_adapters

def build_universal_skill(skill_data, videos, output_dir="output/skills", enabled_adapters=None):
    """
    Takes synthesized skill data from Gemini and writes it as an agent-agnostic skill directory structure.
    Also executes platform adapters.
    """
    name = skill_data.get("name", "untitled-skill")
    skill_path = Path(output_dir) / name
    
    # Clean output path
    if skill_path.exists():
        shutil.rmtree(skill_path)
    skill_path.mkdir(parents=True, exist_ok=True)
    
    # 1. Write metadata.yaml
    metadata = {
        "name": name,
        "description": skill_data.get("description", ""),
        "keywords": skill_data.get("keywords", []),
        "difficulty": skill_data.get("difficulty", "intermediate"),
        "prerequisites": skill_data.get("prerequisites", []),
        "sources": [
            {
                "title": v.get("title", ""),
                "channel": v.get("channelName", ""),
                "link": v.get("link", "")
            } for v in videos
        ]
    }
    
    with open(skill_path / "metadata.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(metadata, f, default_flow_style=False, sort_keys=False)
        
    # 2. Write core skill.md
    with open(skill_path / "skill.md", "w", encoding="utf-8") as f:
        f.write(skill_data.get("skill_body", ""))
        
    # 3. Create references/ directory and write each ref document
    refs_dir = skill_path / "references"
    refs_dir.mkdir(exist_ok=True)
    
    references = skill_data.get("references", [])
    if isinstance(references, dict):
        references_list = [{"filename": k, "content": v} for k, v in references.items()]
    else:
        references_list = references
        
    for ref_doc in references_list:
        if isinstance(ref_doc, dict):
            filename = ref_doc.get("filename", "")
            content = ref_doc.get("content", "")
        else:
            filename = getattr(ref_doc, "filename", "")
            content = getattr(ref_doc, "content", "")
            
        if not filename:
            continue
        # Sanitize filename
        if not filename.endswith(".md"):
            filename += ".md"
        with open(refs_dir / filename, "w", encoding="utf-8") as f:
            f.write(content)
            
    # 4. Generate sources.md inside references
    sources_content = ["# Video Sources\n", "The following curated videos were synthesized to create this skill:\n"]
    for idx, v in enumerate(videos, 1):
        title = v.get("title", "Unknown Title")
        channel = v.get("channelName", "Unknown Channel")
        link = v.get("link", "")
        sources_content.append(f"{idx}. **[{title}]({link})** by {channel}")
        
    with open(refs_dir / "sources.md", "w", encoding="utf-8") as f:
        f.write("\n".join(sources_content))
        
    # 5. Run Platform Adapters
    adapters = get_adapters(enabled_adapters)
    platform_base_dir = skill_path / "platforms"
    platform_base_dir.mkdir(exist_ok=True)
    
    install_instructions = {}
    for adapter in adapters:
        try:
            print(f"[Skill Builder] Executing platform adapter '{adapter.platform_name}' for '{name}'...")
            adapter.adapt(skill_path, platform_base_dir, metadata)
            install_instructions[adapter.platform_name] = adapter.install_instructions(name)
        except Exception as e:
            print(f"[Skill Builder] Adapter '{adapter.platform_name}' failed: {e}")
            
    # 6. Generate README.md with installation instructions
    readme_lines = [
        f"# {name.replace('-', ' ').title()}",
        f"\n{metadata['description']}\n",
        "## Setup & Installation\n",
        "This skill is agent-agnostic and packaged for multiple developer agents. Find your target platform below:\n"
    ]
    
    for platform, instructions in install_instructions.items():
        readme_lines.append(f"### 💻 {platform.title()}")
        readme_lines.append(f"_{instructions}_\n")
        
    with open(skill_path / "README.md", "w", encoding="utf-8") as f:
        f.write("\n".join(readme_lines))
        
    print(f"[Skill Builder] Completed packaging for '{name}'.")
    return skill_path
