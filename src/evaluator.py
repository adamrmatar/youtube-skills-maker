import json
import os
import time
import urllib.request
import urllib.error

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class EvaluationResult(BaseModel):
    is_teachable_skill: bool = Field(
        description=(
            "True if the transcript contains a concrete technique, system structure, "
            "prompt design, or workflow that can be turned into an instruction/rules file "
            "for an AI agent to perform. False if it's purely opinion, high-level overview, "
            "industry news, or product demonstration without actionable instructions."
        )
    )
    technique_description: str = Field(
        description=(
            "If is_teachable_skill is True, summarize the specific technique or workflow. "
            "Explain what an AI agent would need to do to execute it."
        )
    )
    skill_potential: int = Field(
        description="Integer from 1 (unactionable/pure talk) to 5 (highly actionable, detailed rules, clear code/prompt patterns)."
    )
    category: str = Field(
        description="Standard category label, e.g., prompt-engineering, rag, agents, automation, local-ai, ai-coding, or design."
    )
    reasoning: str = Field(description="Internal reasoning for this classification.")
    keywords: list[str] = Field(default_factory=list, description="3-8 keyword tags for this skill topic.")


# ---------------------------------------------------------------------------
# OpenRouter backend (OpenAI-compatible)
# ---------------------------------------------------------------------------

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"

EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_teachable_skill": {"type": "boolean"},
        "technique_description": {"type": "string"},
        "skill_potential": {"type": "integer", "minimum": 1, "maximum": 5},
        "category": {"type": "string"},
        "reasoning": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["is_teachable_skill", "technique_description", "skill_potential", "category", "reasoning", "keywords"],
}


def _call_openrouter(system: str, user: str, api_key: str, model: str) -> dict | None:
    """Call OpenRouter with the given model. Returns parsed JSON dict or None."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "EvaluationResult",
                "strict": True,
                "schema": EVAL_SCHEMA,
            },
        },
        "temperature": 0.1,
        "max_tokens": 1024,
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

    delay = 15
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.load(resp)

            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            # Normalise types defensively
            return {
                "is_teachable_skill": bool(parsed.get("is_teachable_skill", False)),
                "technique_description": str(parsed.get("technique_description", "")),
                "skill_potential": int(parsed.get("skill_potential", 2)),
                "category": str(parsed.get("category", "general")),
                "reasoning": str(parsed.get("reasoning", "")),
                "keywords": list(parsed.get("keywords", [])),
            }

        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            if e.code == 429:
                print(f"[OpenRouter] Rate limit (429). Waiting {delay}s (attempt {attempt + 1}/6)...")
                time.sleep(delay)
                delay = min(delay * 2, 120)
            elif e.code in (502, 503, 504):
                print(f"[OpenRouter] Server error ({e.code}). Waiting {delay}s...")
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                print(f"[OpenRouter] HTTP {e.code}: {body_text[:300]}")
                return None
        except json.JSONDecodeError as e:
            print(f"[OpenRouter] JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"[OpenRouter] Unexpected error: {e}")
            return None

    print("[OpenRouter] Exhausted retries.")
    return None


# ---------------------------------------------------------------------------
# Local Ollama fallback
# ---------------------------------------------------------------------------

def _call_local_model(prompt: str, model_name: str) -> dict | None:
    """Call a local Ollama model and parse a best-effort EvaluationResult."""
    json_prompt = (
        prompt
        + "\n\nRespond ONLY with valid JSON matching this schema:\n"
        + json.dumps({
            "is_teachable_skill": "bool",
            "technique_description": "string",
            "skill_potential": "int 1-5",
            "category": "string",
            "reasoning": "string",
            "keywords": ["string"],
        })
    )
    try:
        payload = {"model": model_name, "prompt": json_prompt, "stream": False}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.load(resp)

        raw = result.get("response", "").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        return {
            "is_teachable_skill": bool(parsed.get("is_teachable_skill", False)),
            "technique_description": str(parsed.get("technique_description", "")),
            "skill_potential": int(parsed.get("skill_potential", 2)),
            "category": str(parsed.get("category", "general")),
            "reasoning": str(parsed.get("reasoning", "")),
            "keywords": list(parsed.get("keywords", [])),
        }
    except Exception as e:
        print(f"[LocalModel] Error calling {model_name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_evaluation_counter = 0


def evaluate_transcript(video_id: str, title: str, transcript_text: str, api_key: str) -> dict | None:
    """
    Evaluate a video transcript to determine if it contains a teachable AI skill.

    Priority order:
      1. OpenRouter (DeepSeek-V3 by default) — if OPENROUTER_API_KEY is set
      2. Gemini — if GEMINI_API_KEY is set and openrouter unavailable
      3. Local Ollama — if LOCAL_MODEL is set to a model name (not 'none')
    """
    global _evaluation_counter
    _evaluation_counter += 1

    if not transcript_text:
        print(f"[Evaluator] [{video_id}] Empty transcript. Skipping.")
        return None

    system = "You are an expert AI agent curriculum engineer. Evaluate transcripts to extract structured AI agent skills. Always respond with valid JSON."

    user_prompt = f"""Analyze the following video transcript. Determine if it contains an actionable technique, method, prompt framework, code pattern, or workflow that can be turned into a "Skill" file for an AI agent to execute.

Title: {title}
Video ID: {video_id}

Transcript:
{transcript_text[:80000]}
"""

    # --- OpenRouter first (primary) ---
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        model = os.getenv("EVAL_MODEL", "deepseek/deepseek-chat")
        fallback = os.getenv("FALLBACK_MODEL", "deepseek/deepseek-chat-v3-0324")
        print(f"[Evaluator] [{video_id}] → OpenRouter ({model})")
        result = _call_openrouter(system, user_prompt, openrouter_key, model)
        if result is None and fallback != model:
            print(f"[Evaluator] [{video_id}] Primary failed, trying fallback ({fallback})...")
            result = _call_openrouter(system, user_prompt, openrouter_key, fallback)
        if result is not None:
            print(
                f"[Evaluator] [{video_id}] ✓ Teachable={result['is_teachable_skill']} "
                f"Potential={result['skill_potential']} Category={result['category']}"
            )
            return result

    # --- Gemini fallback ---
    if api_key:
        try:
            from google import genai
            from google.genai import types
            from google.genai.errors import ClientError

            client = genai.Client(api_key=api_key)
            gemini_model = "gemini-1.5-flash"
            print(f"[Evaluator] [{video_id}] → Gemini fallback ({gemini_model})")

            full_prompt = f"{system}\n\n{user_prompt}"
            delay = 30
            for attempt in range(4):
                try:
                    from pydantic import BaseModel as PydanticBase
                    response = client.models.generate_content(
                        model=gemini_model,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=EvaluationResult,
                            temperature=0.1,
                        ),
                    )
                    result = json.loads(response.text)
                    print(f"[Evaluator] [{video_id}] ✓ Gemini fallback succeeded")
                    return result
                except ClientError as e:
                    if e.code == 429:
                        print(f"[Evaluator] Gemini 429, waiting {delay}s...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        break
                except Exception:
                    break
        except Exception as e:
            print(f"[Evaluator] Gemini fallback error: {e}")

    # --- Local model last resort ---
    local_model = os.getenv("LOCAL_MODEL", "none").strip()
    if local_model and local_model != "none":
        print(f"[Evaluator] [{video_id}] → Local model ({local_model})")
        result = _call_local_model(user_prompt, local_model)
        if result is not None:
            print(f"[Evaluator] [{video_id}] ✓ Local model succeeded")
            return result

    print(f"[Evaluator] [{video_id}] ✗ All backends failed.")
    return None
