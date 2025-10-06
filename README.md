# SY PDP Content LLM

Generates SEO + AEO–friendly long-form content for Square Yards project detail pages (PDP).

**What it does**
- Ingests **Datacenter JSON** per project
- Pulls **SERP evidence** for factual grounding
- Learns tone from **human examples**
- Outputs **structured JSON** + **styled HTML**

## Requirements
- Python 3.11
- OpenAI API key (model via `OPENAI_MODEL`)
- SERP API key

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

cp .env.example .env
# Fill .env with:
# OPENAI_API_KEY=...
# SERP_API_KEY=...
# (optional) OPENAI_BASE_URL=...
# (optional) OPENAI_MODEL=gpt-5
