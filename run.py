import argparse
import sys
import os
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.state import State
from src.firestore_source import fetch_curated_videos
from src.transcribe import get_transcript
from src.evaluator import evaluate_transcript
from src.cluster import cluster_videos
from src.dedup import check_deduplication
from src.synthesize import synthesize_skill
from src.skill_builder import build_universal_skill
from src.publisher import publish_skills_to_github

def parse_args():
    parser = argparse.ArgumentParser(description="YouTube Skills Maker Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing files or calling APIs")
    parser.add_argument("--no-push", action="store_true", help="Run synthesis and packaging but skip pushing to GitHub")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of new videos to transcribe and evaluate in this run")
    parser.add_argument("--reset-state", action="store_true", help="Clear state history before running")
    parser.add_argument("--video-ids", type=str, default="", help="Comma-separated list of video IDs to force process")
    return parser.parse_args()

def load_config(config_path="config.yaml"):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        sys.exit(1)

def main():
    args = parse_args()
    config = load_config()
    
    # State setup
    state_file = "data/state.json"
    if args.reset_state and os.path.exists(state_file):
        os.remove(state_file)
        print("[Pipeline] State file reset.")
        
    state = State(state_file)
    
    # Get API keys
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("[Pipeline] Error: GEMINI_API_KEY environment variable is not set. Please set it in .env.")
        sys.exit(1)
        
    repo_slug = config.get("github", {}).get("repo", "adamrmatar/ai-skills")
    local_repo_path = config.get("github", {}).get("local_repo_path", "data/ai-skills")
    
    if args.dry_run:
        print("[Pipeline] DRY-RUN MODE: No API calls or disk changes will be made.")
    elif not args.no_push:
        print("[Pipeline] Initializing/Cloning target GitHub repository...")
        try:
            from src.publisher import init_or_clone_repo
            init_or_clone_repo(repo_slug, local_repo_path)
        except Exception as e:
            print(f"[Pipeline] Warning: Target repository initialization failed: {e}")
            
    # 1. Fetch curated videos from Firestore
    print("[Pipeline] Fetching videos from 25experts Firestore...")
    all_videos = fetch_curated_videos(
        project_id=config["firestore"]["project_id"],
        collection=config["firestore"]["collection"]
    )
    
    # Filter for target videos
    if args.video_ids:
        target_ids = [vid.strip() for vid in args.video_ids.split(",") if vid.strip()]
        new_videos = [v for v in all_videos if v["videoId"] in target_ids]
        print(f"[Pipeline] Forcing processing of specific video IDs: {target_ids}")
    else:
        new_videos = [v for v in all_videos if not state.is_video_processed(v["videoId"])]
        print(f"[Pipeline] Found {len(new_videos)} new unprocessed videos.")
    
    # Prioritize videos that match skill-focused topics
    priority_topics = {"prompt-engineering", "rag", "agents", "orchestration", "ai-coding", "automation"}
    def get_sort_key(video):
        video_topics = set(video.get("topics", []))
        has_priority = not video_topics.isdisjoint(priority_topics)
        # True (has priority) is 1, False is 0. Sort ascending means 0 (True) first.
        return (0 if has_priority else 1, video.get("publishedAt", ""))
        
    new_videos.sort(key=get_sort_key)
    print(f"[Pipeline] Prioritized {sum(1 for v in new_videos if not set(v.get('topics', [])).isdisjoint(priority_topics))} priority skill videos.")

    # Limit new videos to prevent rate limiting
    new_videos = new_videos[:args.limit]
    print(f"[Pipeline] Limiting to first {len(new_videos)} videos for this run.")

    # 2. Extract transcripts and evaluate each video
    teachable_videos = []
    
    for idx, video in enumerate(new_videos, 1):
        video_id = video["videoId"]
        title = video.get("title", "Unknown Title")
        print(f"\n[Pipeline] ({idx}/{len(new_videos)}) Processing video: {title} ({video_id})")
        
        if args.dry_run:
            continue
            
        # Get/Extract transcript
        transcript = get_transcript(video_id, data_dir="data", gemini_api_key=gemini_api_key)
        
        if not transcript:
            print(f"[Pipeline] Skip {video_id}: Transcript extraction failed.")
            state.mark_video_processed(video_id, {
                "title": title,
                "status": "failed_no_transcript"
            })
            continue

        # Evaluate if teachable skill
        evaluation = evaluate_transcript(video_id, title, transcript, gemini_api_key)
        
        if not evaluation:
            print(f"[Pipeline] Skip {video_id}: Evaluation failed.")
            continue
            
        # Save state with evaluation details
        is_teachable = evaluation.get("is_teachable_skill", False)
        potential = evaluation.get("skill_potential", 1)
        category = evaluation.get("category", "general")
        
        state.mark_video_processed(video_id, {
            "title": title,
            "status": "evaluated",
            "is_teachable": is_teachable,
            "skill_potential": potential,
            "category": category,
            "evaluation": evaluation
        })
        
        # Keep if it is a teachable skill and has minimum potential (3+)
        if is_teachable and potential >= 3:
            video["evaluation"] = evaluation
            teachable_videos.append(video)

    if args.dry_run:
        print("[Pipeline] Dry-run complete. Exiting.")
        return

    print(f"\n[Pipeline] Evaluated {len(new_videos)} videos. {len(teachable_videos)} contain actionable AI skills.")

    if not teachable_videos:
        print("[Pipeline] No new teachable skills found. Exiting.")
        return

    # 3. Cluster new teachable videos by topic
    similarity_threshold = config["pipeline"].get("clustering_threshold", 0.75)
    clusters = cluster_videos(teachable_videos, gemini_api_key, similarity_threshold)
    
    skills_created_or_updated = False

    # 4. Synthesize skills for each cluster
    for cluster_name, videos_in_cluster in clusters.items():
        print(f"\n[Pipeline] Processing cluster: {cluster_name}")
        
        # Check config limits
        min_vids = config["pipeline"].get("min_videos_in_cluster", 2)
        allow_solo = config["pipeline"].get("allow_solo_skills", True)
        
        if len(videos_in_cluster) < min_vids and not allow_solo:
            print(f"[Pipeline] Skipping cluster '{cluster_name}': Contains only {len(videos_in_cluster)} video(s), minimum configured is {min_vids}.")
            continue
            
        # Extract keywords and description from evaluation metadata
        # We merge all keywords across the cluster
        keywords = []
        categories = []
        for v in videos_in_cluster:
            keywords.extend(v["evaluation"].get("keywords", []))
            categories.append(v["evaluation"].get("category", "general"))
            
        keywords = list(set(keywords))
        main_category = max(set(categories), key=categories.count)
        
        # 5. Deduplication and check local repo or skills.sh
        # Prepare target slug name
        topic_slug = "-".join(cluster_name.split("-")[:-1]) # e.g. "ai-coding"
        
        if not topic_slug: # Fallback if split fails
            topic_slug = cluster_name
        
        dedup_res = check_deduplication(topic_slug, keywords, local_repo_path)
        action = dedup_res["action"]
        
        if action == "skip":
            print(f"[Pipeline] Deduplication matched: Skipping skill synthesis for '{topic_slug}'.")
            continue
            
        print(f"[Pipeline] Action for topic '{topic_slug}': {action.upper()}")
        
        # 6. Synthesis using Gemini
        synthesized_data = synthesize_skill(
            topic_slug, 
            videos_in_cluster, 
            gemini_api_key,
            model_name=config["pipeline"].get("gemini_model", "gemini-2.5-flash")
        )
        
        if not synthesized_data:
            print(f"[Pipeline] Failed to synthesize skill for '{topic_slug}'.")
            continue
            
        # 7. Package as Universal Skill & Platform formats
        build_universal_skill(
            synthesized_data,
            videos_in_cluster,
            output_dir=os.path.join(local_repo_path, "skills"),
            enabled_adapters=config.get("adapters", {}).get("enabled", [])
        )
        
        # Record synthesized skill in state
        video_ids = [v["videoId"] for v in videos_in_cluster]
        state.record_synthesized_skill(topic_slug, video_ids, {
            "category": main_category,
            "videos_count": len(videos_in_cluster)
        })
        skills_created_or_updated = True

    # 8. Push to GitHub if changes occurred
    if skills_created_or_updated and not args.no_push:
        print("\n[Pipeline] Publishing new skills to GitHub...")
        publish_skills_to_github(repo_slug, local_repo_path)
    elif not skills_created_or_updated:
        print("\n[Pipeline] No skills were created or updated in this run.")
    else:
        print("\n[Pipeline] Skipping GitHub push because --no-push was set.")

    print("\n[Pipeline] Pipeline execution complete.")

if __name__ == "__main__":
    main()
