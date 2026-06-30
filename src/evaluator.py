import json
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
    delay = 6
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
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
