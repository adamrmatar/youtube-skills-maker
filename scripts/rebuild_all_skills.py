#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.synthesize import synthesize_skill
from src.skill_builder import build_universal_skill
from src.publisher import publish_skills_to_github, publish_to_ikf

load_dotenv()

LOCAL_REPO_PATH = "data/ai-skills"
SKILLS_DIR = Path(LOCAL_REPO_PATH) / "skills"
TRANSCRIPTS_DIR = Path("data/transcripts")

def extract_video_id(url: str) -> str:
    # Match patterns like:
    # https://www.youtube.com/watch?v=VIDEO_ID
    # https://youtu.be/VIDEO_ID
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

    if not SKILLS_DIR.exists():
        print(f"Error: Skills directory '{SKILLS_DIR}' does not exist.")
        sys.exit(1)

    skill_folders = sorted([d for d in SKILLS_DIR.iterdir() if d.is_dir()])
    print(f"Found {len(skill_folders)} skills to rebuild.")

    enabled_adapters = ["antigravity", "cursor", "claude", "copilot", "windsurf"]

    for idx, folder in enumerate(skill_folders, 1):
        slug = folder.name
        print(f"\n[{idx}/{len(skill_folders)}] Rebuilding skill '{slug}'...")

        meta_path = folder / "metadata.yaml"
        if not meta_path.exists():
            print(f"  ⚠️ Skipping {slug}: metadata.yaml not found.")
            continue

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

        sources = meta.get("sources", [])
        if not sources:
            print(f"  ⚠️ Skipping {slug}: No sources found in metadata.")
            continue

        videos_in_cluster = []
        for src in sources:
            url = src.get("link", "")
            video_id = extract_video_id(url)
            if not video_id:
                # Try fallback: match from Title if url isn't parsing
                print(f"  Could not extract video ID from url: {url}")
                continue

            # Reconstruct the video info structure expected by build_universal_skill and synthesize_skill
            videos_in_cluster.append({
                "videoId": video_id,
                "title": src.get("title", "Unknown Title"),
                "channelName": src.get("channel", "Unknown Channel"),
                "link": url
            })

        if not videos_in_cluster:
            print(f"  ⚠️ Skipping {slug}: No valid video IDs could be mapped.")
            continue

        print(f"  Sources mapped: {[v['videoId'] for v in videos_in_cluster]}")

        # 1. Re-synthesize using the new OpenRouter prompt/flow
        synthesized_data = synthesize_skill(
            slug,
            videos_in_cluster,
            api_key=api_key,
            model_name=os.getenv("SYNTH_MODEL", "deepseek/deepseek-chat")
        )

        if not synthesized_data:
            print(f"  ❌ Re-synthesis failed for '{slug}'. skipping.")
            continue

        # 2. Package skill and output to the target output directory
        build_universal_skill(
            synthesized_data,
            videos_in_cluster,
            output_dir=str(SKILLS_DIR),
            enabled_adapters=enabled_adapters
        )
        print(f"  ✅ Rebuilt and packaged '{slug}' successfully.")

    # 3. Publish updates to both GitHub repos
    print("\n[Publisher] Publishing updated skills to GitHub (ai-skills)...")
    publish_skills_to_github(repo_slug="adamrmatar/ai-skills", local_repo_path=LOCAL_REPO_PATH)

    print("\n[Publisher] Publishing updated skills to TDH-Labs/i-know-kung-fu...")
    publish_to_ikf(
        src_skills_path=str(SKILLS_DIR),
        ikf_repo_slug="TDH-Labs/i-know-kung-fu",
        ikf_local_path="data/i-know-kung-fu"
    )

    print("\nAll skills rebuilt and pushed successfully!")

if __name__ == "__main__":
    main()
