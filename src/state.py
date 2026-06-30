import json
import os
from pathlib import Path

class State:
    def __init__(self, state_file_path):
        self.filepath = Path(state_file_path)
        self.data = {
            "processed_videos": {},
            "saved_skills": {}
        }
        self.load()

    def load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"Error loading state file: {e}. Starting fresh.")
                self.data = {
                    "processed_videos": {},
                    "saved_skills": {}
                }
        else:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self.save()

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def is_video_processed(self, video_id):
        return video_id in self.data.get("processed_videos", {})

    def mark_video_processed(self, video_id, metadata):
        if "processed_videos" not in self.data:
            self.data["processed_videos"] = {}
        self.data["processed_videos"][video_id] = metadata
        self.save()

    def get_video_metadata(self, video_id):
        return self.data.get("processed_videos", {}).get(video_id)

    def record_synthesized_skill(self, skill_name, video_ids, metadata=None):
        if "saved_skills" not in self.data:
            self.data["saved_skills"] = {}
        self.data["saved_skills"][skill_name] = {
            "video_ids": video_ids,
            "metadata": metadata or {}
        }
        # Update each video's status to synthesized
        for vid in video_ids:
            if vid in self.data["processed_videos"]:
                self.data["processed_videos"][vid]["status"] = "synthesized"
                self.data["processed_videos"][vid]["synthesized_skill_name"] = skill_name
        self.save()
