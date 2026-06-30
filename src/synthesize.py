import json
import time
from pydantic import BaseModel, Field
from typing import Dict, List
from google import genai
from google.genai import types
from google.genai.errors import ClientError

class ReferenceDoc(BaseModel):
    filename: str = Field(description="Filename for the supporting document, e.g. core_concepts.md, practical_guide.md, code_examples.md")
    content: str = Field(description="The full markdown content for the file.")

class SynthesizedSkill(BaseModel):
    name: str = Field(description="Kebab-case name of the skill, e.g., prompt-chaining-workflows.")
    description: str = Field(description="A 1-2 sentence description explaining what the skill teaches and when the agent should activate it.")
    keywords: List[str] = Field(description="List of trigger keywords/phrases that trigger this skill.")
    difficulty: str = Field(description="Difficulty level of the skill (beginner, intermediate, advanced).")
    prerequisites: List[str] = Field(description="List of prerequisites or required tools/configurations.")
    
    skill_body: str = Field(description="The core platform-neutral skill.md body. Written in the second person addressing the AI agent (e.g., 'You should use this technique to... Here is your step-by-step workflow...'). Contains high-level concepts and workflow steps. Links to references should use relative paths like [Practical Guide](references/practical_guide.md).")
    
    references: List[ReferenceDoc] = Field(description="List of supporting reference markdown files.")

def synthesize_skill(topic_name, videos, api_key, model_name="gemini-2.5-flash"):
    """
    Synthesizes multiple video transcripts into a single agent-agnostic skill structure.
    """
    if not api_key:
        print("[Synthesizer] Gemini API key missing. Skipping synthesis.")
        return None

    client = genai.Client(api_key=api_key)
    
    # Prepare the input for Gemini
    sources_summary = []
    transcripts_block = []
    
    for v in videos:
        vid = v["videoId"]
        title = v["title"]
        ch_name = v.get("channelName", "Unknown Channel")
        link = v.get("link", f"https://www.youtube.com/watch?v={vid}")
        
        # Read the cached transcript text
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
        transcripts_block.append(f"--- START TRANSCRIPT: {title} ({link}) ---\n{transcript_text[:50000]}\n--- END TRANSCRIPT ---")

    sources_str = "\n".join(sources_summary)
    transcripts_str = "\n\n".join(transcripts_block)
    
    system_instruction = """
You are an expert AI agent curriculum engineer.
Your job is to read video transcripts that teach a HUMAN how to do something with AI, and translate that knowledge into a direct, actionable "Skill" for an AI AGENT.
You translate human-facing tutorials into agent-facing execution rules and step-by-step instructions.
Instead of "Here is how you should construct your prompt", write "Construct your prompt by doing...".
Address the agent directly as "you" or "your".
Make the instructions concrete, showing best practices, pitfalls, and code/prompt templates.
"""

    prompt = f"""
We have the following sources discussing the topic '{topic_name}':
{sources_str}

Here are the transcripts from the videos:
{transcripts_str}

Synthesize this knowledge into a single, comprehensive, high-quality agent skill.
Ensure the skill is written for an AI agent to execute.
Include:
1. Core concepts
2. Practical step-by-step workflow for the agent to follow
3. Concrete code or prompt examples
4. Reconcile any differences or disagreements in the sources.

Output the result as a structured JSON object matching the requested schema.
"""

    print(f"[Synthesizer] Synthesizing skill '{topic_name}' from {len(videos)} sources using {model_name}...")
    
    response = None
    delay = 6
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SynthesizedSkill,
                    system_instruction=system_instruction,
                    temperature=0.2
                )
            )
            break
        except ClientError as e:
            if e.code == 429:
                print(f"[Synthesizer] Gemini rate limit (429) hit. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"[Synthesizer] Gemini API error: {e}")
                return None
        except Exception as e:
            print(f"[Synthesizer] Gemini API unexpected error: {e}")
            return None

    if not response:
        print(f"[Synthesizer] Failed to get synthesis response from Gemini after retries.")
        return None

    try:
        result_dict = json.loads(response.text)
        print(f"[Synthesizer] Synthesis successful for '{result_dict['name']}' with {len(result_dict['references'])} references.")
        return result_dict
    except Exception as e:
        print(f"[Synthesizer] Failed to parse synthesized response JSON: {e}")
        return None
