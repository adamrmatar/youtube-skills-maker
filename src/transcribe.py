import json
import os
import re
import subprocess
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types

def clean_srt(srt_content):
    """Simple parser to clean SRT file content into plain text."""
    # Remove SRT index numbers
    content = re.sub(r'^\d+\r?\n', '', srt_content, flags=re.MULTILINE)
    # Remove SRT timestamps (e.g. 00:01:20,000 --> 00:01:23,000)
    content = re.sub(r'^\d{2}:\d{2}:\d{2}[,\.]\d{3} --> \d{2}:\d{2}:\d{2}[,\.]\d{3}\r?\n', '', content, flags=re.MULTILINE)
    # Clean blank lines and line breaks
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    
    # Deduplicate consecutive identical lines (auto-subs often duplicate text)
    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
            
    return " ".join(deduped)

def extract_via_ytdlp(video_id, data_dir):
    """Falls back to yt-dlp to download subtitles/auto-generated captions."""
    print(f"[{video_id}] Attempting transcript extraction via yt-dlp...")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    output_tmpl = os.path.join(data_dir, f"temp_{video_id}")
    
    # Flags: download auto-generated captions, english, skip video download, convert to srt
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--write-subs",
        "--sub-lang", "en",
        "--skip-download",
        "--convert-subs", "srt",
        "-o", output_tmpl,
        video_url
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Look for the generated srt file
        srt_path = Path(f"{output_tmpl}.en.srt")
        if srt_path.exists():
            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()
            # Clean up the file
            srt_path.unlink()
            text = clean_srt(srt_content)
            return text
    except Exception as e:
        print(f"[{video_id}] yt-dlp failed: {e}")
        
    # Clean up any residual temp files if yt-dlp failed or outputted another format
    for f in Path(data_dir).glob(f"temp_{video_id}*"):
        try:
            f.unlink()
        except:
            pass
            
    return None

def extract_via_gemini(video_id, api_key):
    """Last resort: Uses Gemini API's native YouTube video understanding to transcribe."""
    print(f"[{video_id}] Attempting native transcription via Gemini API...")
    if not api_key:
        print(f"[{video_id}] Gemini API key missing, skipping Gemini transcription.")
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # We prompt the model to transcribe the audio.
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                video_url,
                "Provide a word-for-word transcript of the audio in this video."
            ]
        )
        return response.text
    except Exception as e:
        print(f"[{video_id}] Gemini native transcription failed: {e}")
        return None

def get_transcript(video_id, data_dir="data", gemini_api_key=None):
    """
    Tries to retrieve the transcript for a video using:
    1. youtube_transcript_api
    2. yt-dlp download and parse
    3. Gemini API native YouTube transcription
    """
    cache_dir = Path(data_dir) / "transcripts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{video_id}.json"
    
    # Check cache first
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                print(f"[{video_id}] Loaded transcript from local cache.")
                return cached["text"]
        except Exception as e:
            print(f"[{video_id}] Cache read error: {e}")

    text = None
    method = None
    
    # 1. Primary: youtube_transcript_api
    try:
        print(f"[{video_id}] Fetching transcript from youtube_transcript_api...")
        transcript_list = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
        text = " ".join([t.text for t in transcript_list])
        method = "youtube_transcript_api"
    except Exception as e:
        print(f"[{video_id}] youtube_transcript_api failed: {e}")
        
    # 2. Fallback: yt-dlp
    if not text:
        text = extract_via_ytdlp(video_id, data_dir)
        if text:
            method = "yt-dlp"
            
    # 3. Last resort: Gemini API
    if not text and gemini_api_key:
        text = extract_via_gemini(video_id, gemini_api_key)
        if text:
            method = "gemini_api"
            
    if text:
        # Cache the result
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "video_id": video_id,
                    "text": text,
                    "method": method
                }, f, indent=2, ensure_ascii=False)
            print(f"[{video_id}] Successfully extracted and cached transcript via {method}.")
        except Exception as e:
            print(f"[{video_id}] Failed to cache transcript: {e}")
        return text
    else:
        print(f"[{video_id}] Failed to extract transcript using all available methods.")
        return None
