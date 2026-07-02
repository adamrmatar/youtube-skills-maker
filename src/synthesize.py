import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Dict, List


# ---------------------------------------------------------------------------
# Schema (kept as plain dicts for OpenRouter JSON schema mode)
# ---------------------------------------------------------------------------

SYNTH_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "difficulty": {"type": "string"},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "skill_body": {"type": "string"},
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    "required": ["name", "description", "keywords", "difficulty", "prerequisites", "skill_body", "references"],
}

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"


# ---------------------------------------------------------------------------
# OpenRouter call
# ---------------------------------------------------------------------------

def _call_openrouter_synth(system: str, user: str, api_key: str, model: str) -> dict | None:
    """Call OpenRouter for synthesis. Returns parsed JSON dict or None."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "SynthesizedSkill",
                "strict": True,
                "schema": SYNTH_SCHEMA,
            },
        },
        "temperature": 0.2,
        "max_tokens": 8192,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        OPENROUTER_BASE,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/TDH-Labs/i-know-kung-fu",
            "X-Title": "YouTube Skills Maker",
        },
    )

    delay = 20
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.load(resp)
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            if e.code == 429:
                print(f"[Synthesizer] OpenRouter rate limit (429). Waiting {delay}s (attempt {attempt+1}/6)...")
                time.sleep(delay)
                delay = min(delay * 2, 120)
            elif e.code in (502, 503, 504):
                print(f"[Synthesizer] Server error ({e.code}). Waiting {delay}s...")
                time.sleep(delay)
            else:
                print(f"[Synthesizer] HTTP {e.code}: {body_text[:300]}")
                return None
        except json.JSONDecodeError as e:
            print(f"[Synthesizer] JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"[Synthesizer] Unexpected error: {e}")
            return None

    print("[Synthesizer] Exhausted retries.")
    return None


# ---------------------------------------------------------------------------
# Gemini fallback
# ---------------------------------------------------------------------------

def _call_gemini_synth(prompt: str, system: str, api_key: str, model_name: str) -> dict | None:
    try:
        from pydantic import BaseModel, Field
        from google import genai
        from google.genai import types
        from google.genai.errors import ClientError

        class ReferenceDoc(BaseModel):
            filename: str
            content: str

        class SynthesizedSkill(BaseModel):
            name: str
            description: str
            keywords: List[str]
            difficulty: str
            prerequisites: List[str]
            skill_body: str
            references: List[ReferenceDoc]

        client = genai.Client(api_key=api_key)
        delay = 45
        for attempt in range(5):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SynthesizedSkill,
                        system_instruction=system,
                        temperature=0.2,
                    ),
                )
                return json.loads(response.text)
            except ClientError as e:
                if e.code == 429:
                    print(f"[Synthesizer] Gemini 429. Waiting {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                else:
                    print(f"[Synthesizer] Gemini error {e.code}: {e}")
                    return None
            except Exception as e:
                print(f"[Synthesizer] Gemini unexpected error: {e}")
                return None
    except Exception as e:
        print(f"[Synthesizer] Gemini import/setup error: {e}")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize_skill(topic_name: str, videos: list, api_key: str, model_name: str = "gemini-2.5-flash") -> dict | None:
    """
    Synthesizes multiple video transcripts into a single agent-agnostic skill structure.
    Uses OpenRouter (DeepSeek) as primary, Gemini as fallback.
    """
    # Build source/transcript blocks
    sources_summary = []
    transcripts_block = []

    for v in videos:
        vid = v["videoId"]
        title = v["title"]
        ch_name = v.get("channelName", "Unknown Channel")
        link = v.get("link", f"https://www.youtube.com/watch?v={vid}")

        transcript_text = ""
        cache_path = f"data/transcripts/{vid}.json"
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                transcript_text = cached.get("text", "")
        except Exception as e:
            print(f"[Synthesizer] Could not read cached transcript for {vid}: {e}")
            continue

        sources_summary.append(f"- '{title}' by {ch_name} (URL: {link})")
        transcripts_block.append(
            f"--- START TRANSCRIPT: {title} ({link}) ---\n{transcript_text[:50000]}\n--- END TRANSCRIPT ---"
        )

    if not transcripts_block:
        print("[Synthesizer] No transcript data available. Aborting.")
        return None

    sources_str = "\n".join(sources_summary)
    transcripts_str = "\n\n".join(transcripts_block)

    system_instruction = """You are an expert AI agent curriculum engineer.
Your job is to read video transcripts that teach a HUMAN how to do something with AI, and translate that knowledge into a direct, actionable "Skill" for an AI AGENT.
Address the agent directly as "you" or "your". Make instructions concrete with best practices, pitfalls, and code/prompt templates.

CRITICAL RULES FOR REFERENCES:
1. You will produce 2-4 reference documents in the `references` array.
2. Each reference MUST have a short, descriptive `filename` ending in `.md`, e.g. `core_concepts.md`, `practical_guide.md`, `code_examples.md`, `common_pitfalls.md`.
3. Each reference `content` field MUST be a FULL, SUBSTANTIVE markdown document — minimum 300 words. Do NOT write one-liners or stubs. Write real, detailed documentation an agent can read and act on, with explanations, examples, and specifics drawn from the transcript.
4. In the `skill_body`, when you link to a reference, use EXACTLY the filename you specified in the references array, prefixed with `references/`. For example, if you created `core_concepts.md`, link to it as `[Core Concepts](references/core_concepts.md)`. NEVER use placeholder text like `link_to_X.md` or `link_to_architecture_doc.md`.

When creating the skill_body markdown, include: overview, step-by-step workflow (numbered), code/prompt snippets, best practices, common pitfalls, and validation steps.
Always respond with valid JSON matching the requested schema."""

    user_prompt = f"""We have the following sources discussing the topic '{topic_name}':
{sources_str}

Here are the transcripts:
{transcripts_str}

Synthesize this knowledge into a single, comprehensive, high-quality agent skill SOP.
Include:
1. An overview and core concepts
2. Detailed step-by-step workflow with numbered actions
3. Concrete code snippets or prompt templates (copy-pasteable, fully annotated)
4. Best-practice guidelines and common pitfalls with specific examples from the transcripts
5. Validation and testing steps
6. Reconcile any differences among sources
7. 2-4 reference documents — each must be a FULL markdown doc (300+ words), not a stub.
   Use short descriptive filenames like core_concepts.md, practical_guide.md, code_examples.md.
   In skill_body, link to them using EXACTLY `references/<filename>` — the filename must match
   what you put in the references array. No placeholder text.

Output as JSON matching the SynthesizedSkill schema."""

    print(f"[Synthesizer] Synthesizing '{topic_name}' from {len(videos)} source(s)...")

    # --- OpenRouter primary ---
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    synth_model = os.getenv("SYNTH_MODEL", "deepseek/deepseek-chat")
    if openrouter_key:
        print(f"[Synthesizer] Using OpenRouter ({synth_model})...")
        result = _call_openrouter_synth(system_instruction, user_prompt, openrouter_key, synth_model)
        if result:
            result = _fix_reference_links(result)
            name = result.get("name", topic_name)
            refs = len(result.get("references", []))
            print(f"[Synthesizer] ✓ Synthesized '{name}' with {refs} reference(s).")
            return result
        print("[Synthesizer] OpenRouter synthesis failed, trying Gemini fallback...")

    # --- Gemini fallback ---
    if api_key:
        gemini_model = os.getenv("GEMINI_SYNTH_MODEL", "gemini-1.5-pro")
        print(f"[Synthesizer] Using Gemini fallback ({gemini_model})...")
        result = _call_gemini_synth(user_prompt, system_instruction, api_key, gemini_model)
        if result:
            result = _fix_reference_links(result)
            name = result.get("name", topic_name)
            refs = len(result.get("references", []))
            print(f"[Synthesizer] ✓ Gemini synthesized '{name}' with {refs} reference(s).")
            return result

    print(f"[Synthesizer] ✗ All backends failed for '{topic_name}'.")
    return None


# ---------------------------------------------------------------------------
# Post-processing: fix any broken reference links the model still produces
# ---------------------------------------------------------------------------

def _fix_reference_links(result: dict) -> dict:
    """
    After synthesis, scan skill_body for broken reference links and replace them
    with the actual filenames from the references array. Also warns about thin refs.
    """
    refs = result.get("references", [])
    skill_body = result.get("skill_body", "")

    # Build a map: normalised title → actual filename
    filename_map = {}
    for ref in refs:
        fname = ref.get("filename", "")
        # Warn if content is thin
        content = ref.get("content", "")
        word_count = len(content.split())
        if word_count < 150:
            print(f"[Synthesizer] ⚠️  Reference '{fname}' is thin ({word_count} words) — consider re-synthesis.")
        if fname:
            # normalise: strip path, lower, no extension
            key = os.path.splitext(os.path.basename(fname))[0].lower().replace(" ", "-").replace("_", "-")
            filename_map[key] = fname

    # Replace any markdown links whose href looks like a placeholder (no 'references/' prefix
    # or doesn't match an actual filename) with the closest actual filename.
    def replace_link(match):
        text = match.group(1)
        href = match.group(2)
        # Already correct
        if href.startswith("references/") and any(href == f"references/{r.get('filename','')}" for r in refs):
            return match.group(0)
        # Try to match by normalised text or href stem
        stem = os.path.splitext(os.path.basename(href))[0].lower().replace(" ", "-").replace("_", "-")
        if stem in filename_map:
            return f"[{text}](references/{filename_map[stem]})"
        # Try matching by link text
        text_key = text.lower().replace(" ", "-")
        if text_key in filename_map:
            return f"[{text}](references/{filename_map[text_key]})"
        # Fallback: use first reference filename if only one ref
        if len(refs) == 1:
            return f"[{text}](references/{refs[0]['filename']})"
        return match.group(0)  # leave unchanged if we can't resolve

    fixed_body = re.sub(r"\[([^\]]+)\]\(([^)]+\.md)\)", replace_link, skill_body)
    result["skill_body"] = fixed_body
    return result
