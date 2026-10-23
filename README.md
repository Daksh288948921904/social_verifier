# Live Cutter

A newsroom tool for **capturing, fact-checking and finding video**. It watches a live stream and cuts it into story clips as they happen. It fact-checks social media reels claim by claim, and finds real YouTube footage for every segment of a script.

Backend: Python / FastAPI. Frontend: React / TypeScript / Vite. AI: Groq (Whisper transcription, `gpt-oss-120b`) and OpenAI (web-search fact-checking, images).

---

## Features

The app has four tabs.

### Sessions: live stream → story clips
Paste a **YouTube Live** link (or any direct stream URL) and Live Cutter will:
- record the stream in short segments with `ffmpeg`;
- transcribe the speech as it arrives (Groq Whisper, with silence skipped);
- use an LLM to spot where each story starts and ends, and cut every finished story into its own clip with a title, summary and thumbnail;
- show clips live on a dashboard (over a WebSocket), where you can rename, re-trim or delete them;
- turn any clip into a **vertical 9:16 Reel** with a hook title card and burned-in captions;
- write a **newspaper-style front page** of the session's stories, and expand any clip into a full article grounded in its transcript.

### Verifier: fact-check reels
Paste a reel/short link (Instagram, YouTube Shorts, X, TikTok, Facebook…), or a list of links as a **batch**. Each one is downloaded and transcribed, then:
- the claims made in it are extracted;
- each claim is checked using **OpenAI web search**, with context from earlier claims in the same video and from indexed **Indian government sources** (data.gov.in, PIB, RBI…) when Qdrant is configured;
- you get an overall conclusion, a **PDF claims report**, and a downloadable clip of the exact moment each claim is made.

From a fact-check you can also:
- **Editor**: arrange claim clips and your own uploaded videos on a timeline and compile them into one video;
- **Instagram kit**: generate a cover image, caption, best posting time and audio suggestion for the compiled video;
- **Debunk script**: generate a ready-to-record script (with PDF) responding to the reel.

### Search: one keyword, many sources
Search a keyword across **YouTube**, the **web/news** and **Instagram Reels** at once, and download any result's video.

### Footage: a script → footage for every segment
Drop in a script (PDF/TXT or pasted text) or a list of keywords:
- the script is split into segments, each with suggested YouTube search keywords;
- you pick keywords and fetch them in batches;
- for every video found, the app reads its captions and shows **which part of which video** fits each segment, down to the timestamp, with a fit score and an explanation;
- any suggested moment can be played in place or **downloaded as its own `.mp4` clip**, or all at once as a ZIP.

Full guide: **[docs/FOOTAGE_AND_SEARCH.md](docs/FOOTAGE_AND_SEARCH.md)**.

---

## Getting started (local)

### 1. Prerequisites

- **Python 3.13** and **Node.js 22**
- **ffmpeg**, **yt-dlp** and **Deno**. yt-dlp needs a JavaScript runtime to download from YouTube; without Deno, YouTube downloads fail with `HTTP Error 403`.

```bash
brew install ffmpeg yt-dlp deno
```

### 2. Backend

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`. At minimum:

```env
GROQ_API_KEY=your_groq_key
OPENAI_API_KEY=your_openai_key
```

See [Configuration](#configuration) for everything else. Then start the API with auto-reload:

```bash
uvicorn app.main:app --port 8787 --reload
```

On startup it checks that `ffmpeg`, `ffprobe` and `yt-dlp` are installed, creates the database (SQLite at `backend/data/live_cutter.db`), and logs a warning for any missing optional keys.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server forwards `/api` calls to the backend on port 8787.

### 4. Logging in

The app has a single account, defined in [`backend/app/core/auth.py`](backend/app/core/auth.py). In local development (`npm run dev`) you're logged in automatically; production builds always show the login page. Restarting the backend logs everyone out.

### 5. Optional: local Qdrant

Verification works without Qdrant, but it's needed for cross-claim context and government-source grounding.

```bash
docker compose up -d          # Qdrant on localhost:6333
```

Set `QDRANT_URL=http://localhost:6333` in `.env`. To load the government sources:

```bash
cd backend && python scripts/ingest_gov_sources.py
```

---

## Configuration

All settings are environment variables, read from `backend/.env` locally. Only the Groq key is required to start; each feature needs the keys listed next to it.

| Variable | Needed for | Notes |
|---|---|---|
| `GROQ_API_KEY` | Everything | Transcription and all LLM steps. |
| `GROQ_API_KEY_2` … `GROQ_API_KEY_7` | Optional | Extra keys, used in rotation to get past per-key rate limits. |
| `OPENAI_API_KEY` | Verifier, Instagram kit | Web-search fact-checking and cover images. Without it, verification falls back to a Groq model without web search. |
| `QDRANT_URL`, `QDRANT_API_KEY` | Verifier (optional) | Cross-claim context and government-source grounding. |
| `DATA_GOV_IN_API_KEY` | Optional | Used by `scripts/ingest_gov_sources.py`. |
| `YOUTUBE_API_KEY` | Search, Footage | YouTube Data API v3. Footage falls back to yt-dlp search without it. |
| `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` | Search | Web and Instagram results via Google Custom Search. |
| `YTDLP_COOKIES_FILE` | Optional | `cookies.txt` from a logged-in **Instagram** session; helps when Instagram restricts downloads. |
| `YTDLP_YOUTUBE_COOKIES_FILE` | Optional | `cookies.txt` from a logged-in **YouTube** session; helps when YouTube blocks the server's IP. |
| `DATABASE_URL` | Production | Postgres connection string. When unset, a local SQLite file is used. |
| `DATA_DIR` | Optional | Where videos, clips and the SQLite file are stored (default `backend/data`). |
| `CORS_ORIGINS` | Production (split hosting) | Comma-separated allowed frontend origins. |
| `COOKIE_SECURE` | Production | `true` when served over HTTPS. |
| `FOOTAGE_VIDEOS_PER_KEYWORD`, `FOOTAGE_KEYWORDS_PER_WAVE` | Footage | Default `5` and `3`. |
| `MAX_RESULTS_PER_SOURCE` | Search | Default `10`. |

Frontend: set `VITE_API_BASE` at build time only if the frontend is hosted separately from the backend (e.g. Vercel + Render).

---

## Deployment

The repo is set up for **Render** via [`render.yaml`](render.yaml):

- One **Docker** web service. The [`Dockerfile`](Dockerfile) builds the frontend, installs ffmpeg, Deno and the Python dependencies, and serves the frontend and API from the same address.
- A **Postgres** database attached through `DATABASE_URL`, so sessions, fact-checks and projects survive redeploys.

Set the API keys in the Render dashboard. Cookie files can be uploaded as **Secret Files** and referenced by their path, e.g. `YTDLP_YOUTUBE_COOKIES_FILE=/etc/secrets/youtube_cookies.txt`.

> **Video files are stored on local disk.** Clips, reels and downloads live under `DATA_DIR`. On a host without a persistent disk (such as Render's free plan) they are wiped on every redeploy, even though their database records remain. Attach a disk, or download what you need soon after creating it.

To run the production image locally:

```bash
docker build -t live-cutter .
docker run -p 8787:8787 --env-file backend/.env live-cutter
```

---

## Project structure

```
backend/
  app/
    main.py            FastAPI app: auth, routes, serves the built frontend in production
    api/               HTTP routes: sessions, clips, verify, editor, search, footage, auth, ws
    core/              config, database (SQLite/Postgres), auth, Groq/OpenAI/Qdrant clients
    ingest/            stream resolving and ffmpeg capture (Sessions)
    transcription/     speech detection, audio clean-up, Groq Whisper
    segmentation/      LLM story-boundary detection (Sessions)
    clipping/          clip cutting, thumbnails, 9:16 Reel export
    rag/               embeddings, Qdrant stores, newspaper/articles, government sources
    verifier/          reel download, claim extraction and verification, reports, debunk scripts
    editor/            timeline compile, uploads, Instagram kit
    search/            Search tab: YouTube, web, Instagram
    footage/           Footage tab: script parsing, captions, moment matching, clip downloads
  scripts/             one-off tools (government-source ingestion, pipeline tests)
  requirements.txt
frontend/
  src/
    pages/             one file per screen
    components/        shared UI; components/footage/ for the Footage tab
    api/               typed API client
docs/                  feature guides
Dockerfile, render.yaml, docker-compose.yml
```

Long-running work (capture, fact-checks, batches, downloads) runs as background tasks in the API process and writes its progress to a database row; the frontend polls that row (or, for live sessions, listens on a WebSocket). These tasks don't survive a server restart. Footage jobs that were cut off are marked as interrupted on startup so they can be re-run; other features don't do this yet.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `HTTP Error 403: Forbidden` from yt-dlp | Install Deno and update yt-dlp (`pip install -U "yt-dlp[default]"` or `brew upgrade yt-dlp`). |
| "Sign in to confirm you're not a bot" / `429 Too Many Requests` | Common from cloud servers. Set `YTDLP_YOUTUBE_COOKIES_FILE`. |
| Instagram reel downloads with no audio | Set `YTDLP_COOKIES_FILE` to a logged-in Instagram session. |
| Groq `429 rate_limit_exceeded` (tokens per day) | Add more Groq keys (`GROQ_API_KEY_2` …); the app rotates through them. |
| `Required binaries not found on PATH` at startup | Install `ffmpeg` and `yt-dlp`. |
| Logged out after restarting the backend | Expected: the session token is regenerated on every start. |
