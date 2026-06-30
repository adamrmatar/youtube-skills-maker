import requests
import urllib.parse

def parse_firestore_field(val):
    if not isinstance(val, dict):
        return val
    if "stringValue" in val:
        return val["stringValue"]
    if "integerValue" in val:
        return int(val["integerValue"])
    if "timestampValue" in val:
        return val["timestampValue"]
    if "booleanValue" in val:
        return val["booleanValue"]
    if "arrayValue" in val:
        values = val["arrayValue"].get("values", [])
        return [parse_firestore_field(v) for v in values]
    return val

def fetch_curated_videos(project_id="experts-d7c3d", collection="curatedVideos"):
    """
    Fetches all videos from the public Firestore curatedVideos collection using the REST API.
    Does not require service account credentials.
    """
    base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection}"
    videos = []
    next_page_token = None

    while True:
        url = base_url
        if next_page_token:
            url += f"?pageToken={urllib.parse.quote(next_page_token)}"
            
        print(f"Fetching Firestore batch: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"Error fetching curated videos from Firestore: {e}")
            break

        documents = data.get("documents", [])
        for doc in documents:
            fields = doc.get("fields", {})
            parsed_fields = {}
            for key, val in fields.items():
                parsed_fields[key] = parse_firestore_field(val)
            
            # Use the document name's last component as the ID if videoId is missing
            doc_id = doc.get("name", "").split("/")[-1]
            if "videoId" not in parsed_fields or not parsed_fields["videoId"]:
                parsed_fields["videoId"] = doc_id
            
            videos.append(parsed_fields)

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    print(f"Total videos fetched from Firestore: {len(videos)}")
    return videos
