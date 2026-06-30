import time
import numpy as np
from google import genai
from google.genai.errors import ClientError

def get_embedding(text, api_key, model="gemini-embedding-2"):
    """Generates text embedding using Gemini API."""
    if not api_key:
        return None
        
    client = genai.Client(api_key=api_key)
    
    response = None
    delay = 6
    for attempt in range(4):
        try:
            response = client.models.embed_content(
                model=model,
                contents=text
            )
            break
        except ClientError as e:
            if e.code == 429:
                print(f"[Embedding] Rate limit (429) hit. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[Embedding] Gemini API error: {e}")
                return None
        except Exception as e:
            print(f"[Embedding] Unexpected error generating embedding: {e}")
            return None

    if response:
        return response.embeddings[0].values
    return None

def cosine_similarity(v1, v2):
    """Computes cosine similarity between two vectors."""
    if v1 is None or v2 is None:
        return 0.0
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return float(dot_product / (norm_v1 * norm_v2))

def cluster_videos(videos_with_metadata, api_key, similarity_threshold=0.75):
    """
    Groups new videos into topic clusters based on their Firestore topic tags
    and semantic similarity of their technique descriptions.
    
    videos_with_metadata: List of dicts, each having 'videoId', 'title', 'evaluation' (from evaluator)
    """
    if not videos_with_metadata:
        return {}

    # Step 1: Pre-group by category/topic identified by evaluator and Firestore topics
    clusters = {}
    
    # Pre-calculate embeddings for the technique descriptions
    for video in videos_with_metadata:
        eval_res = video.get("evaluation")
        if not eval_res:
            continue
            
        desc = eval_res.get("technique_description", "")
        category = eval_res.get("category", "general")
        
        video["embedding"] = get_embedding(desc, api_key)
        video["category"] = category

    # Group by category first
    category_groups = {}
    for video in videos_with_metadata:
        cat = video.get("category", "general")
        if cat not in category_groups:
            category_groups[cat] = []
        category_groups[cat].append(video)

    # Step 2: Within each category group, sub-cluster based on cosine similarity of embeddings
    cluster_counter = 0
    for cat, cat_videos in category_groups.items():
        if not cat_videos:
            continue
            
        sub_clusters = [] # list of lists of videos
        
        for video in cat_videos:
            emb = video.get("embedding")
            if emb is None:
                # Fallback: put in its own cluster if we couldn't get an embedding
                sub_clusters.append([video])
                continue
                
            # Find the best matching cluster in this category
            best_match_idx = -1
            best_sim = -1.0
            
            for idx, sc in enumerate(sub_clusters):
                # Compare to the first item of the cluster (or compute average cluster embedding)
                sc_emb = sc[0].get("embedding")
                if sc_emb is not None:
                    sim = cosine_similarity(emb, sc_emb)
                    if sim > best_sim:
                        best_sim = sim
                        best_match_idx = idx
                        
            if best_sim >= similarity_threshold and best_match_idx != -1:
                # Add to existing cluster
                sub_clusters[best_match_idx].append(video)
            else:
                # Create a new sub-cluster
                sub_clusters.append([video])
                
        # Register the clusters
        for sc in sub_clusters:
            # Topic name is based on category and first video ID or title
            topic_slug = cat.lower().replace(" ", "-")
            cluster_name = f"{topic_slug}-{sc[0]['videoId']}"
            clusters[cluster_name] = sc

    print(f"[Clustering] Grouped {len(videos_with_metadata)} videos into {len(clusters)} clusters.")
    for name, cluster in clusters.items():
        v_titles = [v["title"] for v in cluster]
        print(f"  Cluster '{name}': {v_titles}")
        
    return clusters
