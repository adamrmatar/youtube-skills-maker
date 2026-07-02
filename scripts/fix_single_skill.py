#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
import yaml
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent.parent))

from src.synthesize import synthesize_skill
from src.skill_builder import build_universal_skill
from src.publisher import publish_skills_to_github, publish_to_ikf

load_dotenv()

LOCAL_REPO_PATH = "data/ai-skills"
SKILLS_DIR = Path(LOCAL_REPO_PATH) / "skills"
SLUG = "Automating Email Responses and Meeting Scheduling with OpenClaw"

def extract_video_id(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return ""

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        print("Error: OPENROUTER_API_KEY not found in .env")
        sys.exit(1)

    folder = SKILLS_DIR / SLUG
    if not folder.exists():
        print(f"Error: {folder} does not exist.")
        sys.exit(1)

    meta_path = folder / "metadata.yaml"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}

    sources = meta.get("sources", [])
    videos_in_cluster = []
    for src in sources:
        url = src.get("link", "")
        video_id = extract_video_id(url)
        if video_id:
            videos_in_cluster.append({
                "videoId": video_id,
                "title": src.get("title", "Unknown Title"),
                "channelName": src.get("channel", "Unknown Channel"),
                "link": url
            })

    print(f"Re-synthesizing '{SLUG}'...")
    
    # Retry up to 3 times to bypass temporary JSON parse or model generation errors
    synthesized_data = None
    for attempt in range(3):
        print(f"Attempt {attempt+1}/3...")
        synthesized_data = synthesize_skill(
            SLUG,
            videos_in_cluster,
            api_key=api_key,
            model_name="deepseek/deepseek-chat"
        )
        if synthesized_data:
            break
        print("Retrying...")

    if not synthesized_data:
        print("Failed to re-synthesize after 3 attempts.")
        sys.exit(1)

    enabled_adapters = ["antigravity", "cursor", "claude", "copilot", "windsurf"]
    build_universal_skill(
        synthesized_data,
        videos_in_cluster,
        output_dir=str(SKILLS_DIR),
        enabled_adapters=enabled_adapters
    )
    print("Build successful. Publishing changes...")

    publish_skills_to_github(repo_slug="adamrmatar/ai-skills", local_repo_path=LOCAL_REPO_PATH)
    publish_to_ikf(
        src_skills_path=str(SKILLS_DIR),
        ikf_repo_slug="TDH-Labs/i-know-kung-fu",
        ikf_local_path="data/i-know-kung-fu"
    )
    print("Publishing complete!")

if __name__ == "__main__":
    main()
