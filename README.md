# IT Market Analyzer App
AI-powered analytics platform for IT labor market demand, salary dynamics, skills intelligence, and actionable insights.

## What's new
- AI mascot assistant **Vyz** (chat, insights, markdown reports)
- Database-first architecture (SQLAlchemy, normalized schema)
- Multi-source ingestion pipeline:
  - Remotive public jobs API
  - Arbeitnow job board API
  - RemoteOK public API
  - Adzuna API (optional, with keys)
  - CSV fallback dataset
- Forecasting upgrade with model selection + backtesting (`prophet`, `linear_trend`, `seasonal_naive`)
- Modernized frontend with animated glassmorphism UI and KPI cards

## Tech stack
- Backend: FastAPI, SQLAlchemy, pandas, Prophet, scikit-learn
- Frontend: React, Vite, MUI, Framer Motion, Plotly
- AI runtime: Ollama-compatible endpoint (default model: `mistral:7b-instruct`)

## Backend setup
1. Create environment and install dependencies:
   - `conda create -n myenv python=3.11`
   - `conda activate myenv`
   - `conda install --file requirements.txt`
2. Copy config:
   - `copy env.example .env`
3. Run API:
   - `uvicorn app.main:app --reload`

API docs: `http://127.0.0.1:8000/docs`

## Frontend setup
1. Go to frontend folder
2. Install dependencies:
   - `npm install`
3. Run dev server:
   - `npm run dev`

Frontend app: `http://127.0.0.1:5173`

## One-time cloud demo deploy (GitHub + Render)
This repo includes `render.yaml` for deploying backend + frontend directly from GitHub.

1. Push this repo to GitHub.
2. In Render click **New +** → **Blueprint** and select this repository.
3. Wait until both services are ready:
   - `market-analyzer-api` (FastAPI backend)
   - `market-analyzer-frontend` (static frontend)
4. Open the frontend URL and use it for your presentation.

Demo profile details:
- Uses remote sources on startup for larger dataset sync (`ENABLE_REMOTE_SOURCES=true`, `REFRESH_ON_STARTUP=true`).
- First cloud boot may take several minutes while ingestion fills DB and analytics cache.
- CSV fallback is still applied automatically only if remote sources fail and DB is empty.
- LLM is enabled in cloud demo через OpenAI-compatible endpoint (`LLM_PROVIDER=openai_compatible`).
- Before first successful chat response, set secret `LLM_API_KEY` in Render backend service (Environment tab).
- Default model in `render.yaml`: `mistralai/mistral-7b-instruct:free` via OpenRouter.

## Key API routes
- `/api/demand/`
- `/api/salary/`
- `/api/skills/`
- `/api/assistant/chat`
- `/api/assistant/insights`
- `/api/assistant/report`
- `/api/system/data-status`
- `/api/system/refresh`

## Free data sources
- Remotive (public API, attribution required)
- Arbeitnow (public job board API)
- RemoteOK (public API, attribution required)

## Data source configuration
Set these in `.env` if you want to increase coverage:
- `REMOTIVE_LIMIT` (default 1000)
- `ARBEITNOW_MAX_PAGES` (default 10, 100 jobs/page)
- `ARBEITNOW_ENABLED=true`
- `REMOTEOK_ENABLED=true`

## Notes
- If Ollama is unavailable, assistant responses fall back to deterministic local insights.
- For natural dialog quality, pull an instruction model and set it in `.env`, for example:
  - `ollama pull qwen2.5:7b-instruct`
  - `OLLAMA_MODEL=qwen2.5:7b-instruct`
  - `ASSISTANT_LLM_ENABLED=true`
- On startup, the app initializes DB and refreshes market data into in-memory analytics cache.
- CSV fallback is used when remote sources are unavailable and DB is empty (or when forced refresh is triggered).
