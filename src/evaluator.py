import json
import os
import time
import urllib.request
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# Global counter to alternate between cloud and local models
_evaluation_counter = 0

class EvaluationResult(BaseModel):
    is_teachable_skill: bool = Field(description="True if the transcript contains a concrete technique, system structure, prompt design, or workflow that can be turned into an instruction/rules file for an AI agent to perform. False if it's purely opinion, high-level overview, industry news, or product demonstration without actionable instructions.")
    technique_description: str = Field(description="If is_teachable_skill is True, summarize the specific technique or workflow. Explain what an AI agent would need to do to execute it.")
    skill_potential: int = Field(description="Integer from 1 (unactionable / pure talk) to 5 (highly actionable, detailed rules, clear code/prompt patterns).")
    category: str = Field(description="Standard category label, e.g., prompt-engineering, rag, agents, automation, local-ai, ai-coding, or design.")
    reasoning: str = Field(description="Internal reasoning for this classification.")

def _call_gemini(prompt: str, api_key: str, model_name: str) -> dict | None:
    """Call Gemini with the given model name and return parsed JSON dict or None on failure."""
    client = genai.Client(api_key=api_key)
    delay = 45
    for attempt in range(8):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EvaluationResult,
                    system_instruction="You evaluate transcript text to extract structured AI agent skills.",
                    temperature=0.1,
                ),
            )
            # Throttle after a successful call to avoid rapid bursts
            time.sleep(5)
            return json.loads(response.text)
        except ClientError as e:
            if e.code == 429:
                print(f"[Gemini] Rate limit hit (429). Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
                continue
            else:
                print(f"[Gemini] API error ({e.code}): {e}")
                return None
        except Exception as e:
            print(f"[Gemini] Unexpected error: {e}")
            return None
    print("[Gemini] Exhausted retries.")
    return None

def _call_local_model(prompt: str, model_name: str) -> dict:
    """Call a local Ollama model via its REST API and wrap result in EvaluationResult format.
    Since local models may not produce the exact JSON schema, we fallback to a safe placeholder.
    """
    try:
        payload = {"model": model_name, "prompt": prompt, "stream": False}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            result = json.load(resp)
        # Very simple heuristic: if the model mentions "skill" assume teachable, else not.
        text = result.get("response", "").lower()
        is_teachable = "skill" in text or "tool" in text or "prompt" in text
        return {
            "is_teachable_skill": is_teachable,
            "technique_description": text[:200],
            "skill_potential": 3 if is_teachable else 1,
            "category": "local-ai",
            "reasoning": "Heuristic based on presence of keywords.",
        }
    except Exception as e:
        print(f"[LocalModel] Error calling {model_name}: {e}")
        return {
            "is_teachable_skill": False,
            "technique_description": "",
            "skill_potential": 1,
            "category": "local-ai",
            "reasoning": f"Failed to call local model: {e}",
        }

def evaluate_transcript(video_id, title, transcript_text, api_key):
    """Hybrid evaluation: alternate between Gemini (cloud) and a local Ollama model.
    Cloud calls are throttled to respect usage limits.
    """
    global _evaluation_counter
    _evaluation_counter += 1
    use_cloud = (_evaluation_counter % 2 == 1)  # odd calls → cloud, even → local

    if not api_key:
        print("[Evaluator] Gemini API key missing. Skipping evaluation.")
        return None
    if not transcript_text:
        print(f"[Evaluator] [{video_id}] Empty transcript. Skipping.")
        return None

    prompt = f"""
You are an expert AI agent curriculum engineer. Analyze the following video transcript.
Determine if the video contains an actionable technique, method, prompt framework, code pattern, or workflow that can be turned into a \"Skill\" file (like a system prompt, rule file, or custom tool instructions) that allows an AI agent to perform the task.

Title: {title}
Video ID: {video_id}

Transcript Content:
{transcript_text[:100000]}
"""

    if use_cloud:
        primary = os.getenv('EVAL_MODEL', 'gemini-1.5-flash')
        fallback = os.getenv('FALLBACK_MODEL', 'gemini-1.0-pro')
        result = _call_gemini(prompt, api_key, primary)
        if result is None:
            # try fallback model
            result = _call_gemini(prompt, api_key, fallback)
        return result
    else:
        # Choose a local model – pick the first available from the list (you can change this)
        local_model = os.getenv('LOCAL_MODEL', 'gemma4:12b-mlx')
        return _call_local_model(prompt, local_model)

import os
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class EvaluationResult(BaseModel):
    is_teachable_skill: bool = Field(description="True if the transcript contains a concrete technique, system structure, prompt design, or workflow that can be turned into an instruction/rules file for an AI agent to perform. False if it's purely opinion, high-level overview, industry news, or product demonstration without actionable instructions.")
    technique_description: str = Field(description="If is_teachable_skill is True, summarize the specific technique or workflow. Explain what an AI agent would need to do to execute it.")
    skill_potential: int = Field(description="Integer from 1 (unactionable / pure talk) to 5 (highly actionable, detailed rules, clear code/prompt patterns).")
    category: str = Field(description="Standard category label, e.g., prompt-engineering, rag, agents, automation, local-ai, ai-coding, or design.")
    reasoning: str = Field(description="Internal reasoning for this classification.")

import time
from google.genai.errors import ClientError

def evaluate_transcript(video_id, title, transcript_text, api_key):
    """
    Uses Gemini structured output to classify if a transcript teaches an actionable skill.
    """
    if not api_key:
        print("[Evaluator] Gemini API key missing. Skipping evaluation.")
        return None

    if not transcript_text:
        print(f"[Evaluator] [{video_id}] Empty transcript. Skipping.")
        return None

    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are an expert AI agent curriculum engineer. Analyze the following video transcript.
Determine if the video contains an actionable technique, method, prompt framework, code pattern, or workflow that can be turned into a "Skill" file (like a system prompt, rule file, or custom tool instructions) that allows an AI agent to perform the task.

Your goal is to identify videos that teach a human a technique and translate that into a skill so that the AI can do the work for the human.

Title: {title}
Video ID: {video_id}

Transcript Content:
{transcript_text[:100000]}  # Truncate to protect context limits if very long
"""

    response = None
    delay = 45
    primary_model = os.getenv('EVAL_MODEL', 'gemini-1.5-flash')
    fallback_model = os.getenv('FALLBACK_MODEL', 'gemini-1.0-pro')
    for attempt in range(8):
        try:
            response = client.models.generate_content(
                model=primary_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EvaluationResult,
                    system_instruction="You evaluate transcript text to extract structured AI agent skills.",
                    temperature=0.1
                )
            )
            break
        except ClientError as e:
            if e.code == 404:
                print(f"[{video_id}] Primary model {primary_model} not found. Trying fallback {fallback_model}.")
                try:
                    response = client.models.generate_content(
                        model=fallback_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=EvaluationResult,
                            system_instruction="You evaluate transcript text to extract structured AI agent skills.",
                            temperature=0.1
                        )
                    )
                    break
                except Exception as e2:
                    print(f"[{video_id}] Fallback model error: {e2}")
                    return None
            elif e.code == 429:
                print(f"[{video_id}] Gemini rate limit (429) hit. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
                continue
            else:
                print(f"[{video_id}] Gemini API error: {e}")
                return None
        except Exception as e:
            print(f"[{video_id}] Gemini API unexpected error: {e}")
            return None
    delay = 45
    for attempt in range(8):
        try:
            response = client.models.generate_content(
                model=os.getenv('EVAL_MODEL', 'gemini-1.5-pro'),
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EvaluationResult,
                    system_instruction="You evaluate transcript text to extract structured AI agent skills.",
                    temperature=0.1
                )
            )
            break
        except ClientError as e:
            if e.code == 429:
                print(f"[{video_id}] Gemini rate limit (429) hit. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[{video_id}] Gemini API error: {e}")
                return None
        except Exception as e:
            print(f"[{video_id}] Gemini API unexpected error: {e}")
            return None

    if not response:
        print(f"[{video_id}] Failed to get evaluation response from Gemini after retries.")
        return None

    try:
        result_dict = json.loads(response.text)
        print(f"[{video_id}] Evaluation: Teachable={result_dict['is_teachable_skill']}, Potential={result_dict['skill_potential']}, Category={result_dict['category']}")
        return result_dict
    except Exception as e:
        print(f"[{video_id}] Failed to parse Gemini response JSON: {e}")
        return None
