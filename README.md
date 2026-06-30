# YouTube Skills Maker

An automated AI knowledge ingestion pipeline that regularly pulls curated video references from [25experts.com](https://25experts.com), extracts transcriptions, determines if they teach actionable AI techniques, clusters transcripts by topic, synthesizes them into developer skills, and commits + pushes them to your `ai-skills` repository.

## Features

1. **Firestore Sync**: Queries your Firestore database directly to pull newly curated videos.
2. **Layered Transcript Extraction**: Uses `youtube-transcript-api` (free) first, then falls back to `yt-dlp` (auto-subs download), and finally Gemini multimodal audio transcription as a last resort.
3. **AI Evaluation ("Human Learn → AI Do")**: Uses Gemini 2.5 Flash to parse transcripts and determine if a video teaches an actionable technique that an AI agent can execute.
4. **Embedding Clustering**: Groups related video transcripts together using Gemini text embeddings (`text-embedding-004`).
5. **Ecosystem Deduplication**: Queries Vercel's [skills.sh](https://skills.sh) public registry and checks the local repo to avoid duplication.
6. **Universal Platform Packaging**: Synthesizes transcripts into a neutral core rule markdown file, then runs platform-specific adapters to generate ready-to-use rule formats:
   - **Antigravity**: `SKILL.md` + `references/` subdocs
   - **Cursor**: `.mdc` file containing all rules and references
   - **Claude Code**: Guidelines for project `CLAUDE.md`
   - **GitHub Copilot**: `.instructions.md` format
   - **Windsurf**: `.windsurfrules` file

---

## Setup

### Prerequisites

1. **Python 3.12+**
2. **gh CLI** (GitHub Command Line Tool) logged into your account:
   ```bash
   gh auth login
   ```
3. **yt-dlp** (for subtitle extraction fallback):
   ```bash
   brew install yt-dlp
   ```

### Installation

1. Clone this repository.
2. Set up virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your Gemini API key:
   ```bash
   cp .env.example .env
   # Add your key to .env:
   # GEMINI_API_KEY=your_gemini_api_key
   ```

---

## Usage

### Run locally (dry run)
Checks firestore, transcripts, and runs evaluation but makes no file changes or Git pushes:
```bash
python run.py --dry-run
```

### Run locally (process & generate, skip push)
Extracts transcripts, evaluates, and writes rule files to local `data/ai-skills/skills/` directory without pushing to GitHub:
```bash
python run.py --no-push
```

### Run locally (full run)
Downloads, synthesizes, packages, and pushes new skills directly to your `adamrmatar/ai-skills` repository on GitHub:
```bash
python run.py
```

### Options
- `--limit <num>`: Limit processing to a maximum of `<num>` new videos (defaults to 10) to control API token usage.
- `--reset-state`: Deletes local state history, causing the pipeline to re-process all videos in Firestore from scratch.

---

## GitHub Actions Cloud Scheduling

The pipeline is set up to run automatically in the cloud. Simply:
1. Push this generator code to your target GitHub repository.
2. Go to your repository settings on GitHub → **Secrets and variables** → **Actions**.
3. Create a **Repository Secret** named `GEMINI_API_KEY` and paste your key.
4. The daily workflow `.github/workflows/generate-skills.yml` will run automatically at 8:00 AM UTC (1:00 AM PT) every day, committing newly generated skills directly back to your repository.
