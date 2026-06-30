import os
import requests
import yaml
from pathlib import Path

def search_skills_sh(query):
    """
    Queries skills.sh API to search for existing skills on a topic.
    Returns list of matching skills from the directory.
    """
    if not query:
        return []
    
    url = f"https://www.skills.sh/api/search?q={requests.utils.quote(query)}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return data.get("skills", [])
            return data
    except Exception as e:
        print(f"[Dedup] Error searching skills.sh for '{query}': {e}")
    return []

def get_existing_local_skills(repo_dir):
    """
    Scans the local ai-skills repository to build a dictionary of existing skills.
    Returns a dict mapping skill-slug -> metadata dict.
    """
    local_skills = {}
    skills_path = Path(repo_dir) / "skills"
    
    if not skills_path.exists():
        return local_skills
        
    for item in skills_path.iterdir():
        if item.is_dir():
            meta_file = item / "metadata.yaml"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = yaml.safe_load(f) or {}
                        name = meta.get("name", item.name)
                        local_skills[name] = {
                            "path": item,
                            "metadata": meta
                        }
                except Exception as e:
                    print(f"[Dedup] Error reading metadata for existing skill {item.name}: {e}")
                    
    return local_skills

def check_deduplication(topic_name, keywords, repo_dir):
    """
    Checks if a skill with the given topic_name or keywords already exists in:
    1. The local ai-skills repo
    2. The public skills.sh directory
    
    Returns a dict:
    {
       "exists": bool,
       "source": "local" | "skills_sh" | None,
       "details": dict | None,
       "action": "skip" | "update" | "create"
    }
    """
    # 1. Check local repo
    local_skills = get_existing_local_skills(repo_dir)
    
    # Exact match check
    if topic_name in local_skills:
        print(f"[Dedup] Exact match found locally for skill '{topic_name}'")
        return {
            "exists": True,
            "source": "local",
            "details": local_skills[topic_name],
            "action": "update"  # We should update it with new sources
        }
        
    # Keyword-based check on local skills
    for name, skill in local_skills.items():
        existing_keywords = set(skill["metadata"].get("keywords", []))
        overlap = existing_keywords.intersection(set(keywords))
        if len(overlap) >= 2: # Significant keyword overlap
            print(f"[Dedup] High keyword overlap found locally with skill '{name}' (overlapping: {overlap})")
            return {
                "exists": True,
                "source": "local",
                "details": skill,
                "action": "update"
            }

    # 2. Check skills.sh directory
    print(f"[Dedup] Querying skills.sh for '{topic_name}'...")
    matches = search_skills_sh(topic_name)
    
    # Try searching for the first couple of keywords if no matches
    if not matches and keywords:
        search_query = " ".join(keywords[:2])
        print(f"[Dedup] Querying skills.sh with keywords: '{search_query}'...")
        matches = search_skills_sh(search_query)
        
    if matches:
        # Check if any match is an exact or highly relevant name match
        for match in matches:
            match_name = match.get("name", "").lower()
            if topic_name.lower() in match_name or match_name in topic_name.lower():
                print(f"[Dedup] Found matching ecosystem skill on skills.sh: {match['id']} ({match['installs']} installs)")
                return {
                    "exists": True,
                    "source": "skills_sh",
                    "details": match,
                    "action": "skip" # Skip to avoid recreating a popular public skill
                }

    return {
        "exists": False,
        "source": None,
        "details": None,
        "action": "create"
    }
