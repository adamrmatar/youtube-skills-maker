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
You translate human-facing tutorials into agent-facing execution rules and step‑by‑step instructions.
Instead of "Here is how you should construct your prompt", write "Construct your prompt by doing...".
Address the agent directly as "you" or "your".
Make the instructions concrete, showing best practices, pitfalls, and code/prompt templates.
When creating the skill markdown (skill_body), follow the style of the provided AGENTS.md example, including sections such as Project Overview, Commands table, Architecture diagram, and any relevant code snippets. Keep the format clean, headings hierarchical, and use markdown tables where appropriate.
"""

    prompt = f"""
We have the following sources discussing the topic '{topic_name}':
{sources_str}

Here are the transcripts from the videos:
{transcripts_str}

    Synthesize this knowledge into a single, comprehensive, high-quality agent skill SOP.
    Ensure the skill is written for an AI agent to execute, addressing the agent directly.
    Include:
    1. An overview and core concepts of the technique.
    2. Detailed, step‑by‑step workflow the agent should follow, with numbered actions.
    3. Concrete code snippets or prompt templates, fully functional and annotated.
    4. Best‑practice guidelines and common pitfalls to avoid.
    5. Validation and testing steps the agent can run to verify correctness.
    6. Reconcile any differences or disagreements among the source videos.
    7. A concise list of references, each to be emitted as a separate markdown file.

Output the result as a structured JSON object matching the requested schema.
"""

    print(f"[Synthesizer] Synthesizing skill '{topic_name}' from {len(videos)} sources using {model_name}...")
    
    response = None
    delay = 45
    for attempt in range(8):
        try:
            response = client.models.generate_content(
                model=os.getenv('SYNTH_MODEL', model_name),
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
