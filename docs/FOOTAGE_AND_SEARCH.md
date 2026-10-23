# Footage & Search

Two tabs in Live Cutter for finding existing video to use in a broadcast:

- **Footage**: give it a script (or a list of keywords). It splits the script into segments, suggests YouTube search keywords for each one, fetches videos in batches, and shows **which part of which video** fits each segment, down to the timestamp. Any suggested moment can be downloaded as its own `.mp4` clip.
- **Search**: a quick one-off keyword search across YouTube, the web and Instagram Reels, with a button to download any result.

---

## Footage

### Using it

1. Open the **Footage** tab and choose a mode:
   - **From a script**: drop in a PDF or TXT file, or paste the text. Segment markers such as `SEGMENT 2 —` are followed exactly; without them the script is split at natural topic changes.
   - **From keywords**: type keywords and press Enter, or paste a list (one per line or comma-separated).
2. For a script, each segment comes back with a title, a summary, a "footage wanted" note and 3–6 suggested search keywords. Each keyword has a short reason.
3. Click keyword chips to select them, or use **Select N not yet run** for a whole segment. You can add your own keyword to any segment or remove one.
4. Press **Fetch footage**. Keywords run in waves (3 at a time by default). The sticky bar shows overall progress and what each running keyword is doing.
5. Review the results for each segment:
   - **Best footage for this segment**: the 3 strongest moments, one per video.
   - **Keyword groups**: each keyword's videos in their own color, sorted by fit score. Every video shows a verdict, a timeline strip marking where the matching moments are, and the moments themselves: time range, what's shown or said, and which part of the script it covers.
   - Click any moment to play it in an embedded player starting at that time.
6. Download what you need: **⬇ Download clip** on any moment, **Download all best picks** for a segment, or **Download all as .zip** in the *Downloaded clips* panel.

Every project is saved and listed on the Footage start page.

#### Reading the results

| Signal | Meaning |
|---|---|
| **Strong fit** (70+) / **Partial** (40–69) / **Weak** (<40) | How useful the whole video is for the segment. |
| **no captions** tag | The video has no English captions, so it was judged from its title, description and chapters only. |
| **≈ Estimated time** | That moment's times are a guess, because there were no captions to confirm them. Check before using. |
| Dramatization noted in the verdict | Movies, reenactments, AI-generated or colourised edits are flagged and capped at 40, since they aren't real footage. |
| Sidebar dots | Green: the segment has a strong match. Amber: partial matches only. Grey: nothing fetched yet. |

### How it works

```
script ──► script_parse ──► segments + suggested keywords
                                   │  (user selects keywords)
                                   ▼
             runner: queue ──► waves of N keywords at a time
                                   │  per keyword
                                   ▼
          search (YouTube API, falls back to yt-dlp ytsearch)
                                   │  per video
                                   ▼
          transcript (yt-dlp metadata + one English caption track, cached)
                                   │
                                   ▼
          matcher (LLM picks timestamped moments + relevance score)
                                   │  on demand
                                   ▼
          clips (yt-dlp downloads only [start, end], frame-accurate .mp4)
```

- **Splitting the script** (`app/footage/script_parse.py`): the script is sent with numbered lines. The LLM returns only each segment's *first line number* plus its title, summary, footage note and keywords. The segment text is cut from the original script, so the wording is never paraphrased.
- **Captions** (`app/footage/transcript.py`): one `yt-dlp -J` call gets the duration, chapters and caption tracks. It picks one English track: manual captions first, then YouTube's auto-captions of English speech (`en-orig`, `en-US-orig`, …), and the machine translation only as a last resort, because YouTube rate-limits translation requests much harder. The track is downloaded in the small `srv1` format, merged into ~15 s lines, and cached in `footage_transcripts`, so a video is only fetched once.
- **Matching** (`app/footage/matcher.py`): long transcripts are trimmed to the lines that share the most words with the segment and keyword, kept in time order, so each LLM call stays small. The LLM returns a relevance score, a verdict and up to 4 moments, which are then checked against the video's length.
- **Batches** (`app/footage/runner.py`): one worker per project works through the queue in waves. Keywords queued while a batch is running join the same queue. One video failing doesn't fail the keyword. Jobs cut off by a server restart are marked as failed on startup.
- **Clip downloads** (`app/footage/clips.py`): `yt-dlp --download-sections "*start-end" --force-keyframes-at-cuts`, capped at 720p, with at most 2 downloads at a time. Files are named `S01_<moment-label>_<m>m<ss>s.mp4`.

### API (`/api/footage`)

| Method & path | Purpose |
|---|---|
| `POST /projects` | Create a project. Body: `{mode: "script", title?, script}` or `{mode: "keywords", title?, keywords: []}`. |
| `POST /projects/upload` | Create a script project from an uploaded PDF/TXT (multipart: `file`, optional `title`). |
| `GET /projects` | List projects with counts. |
| `GET /projects/{id}` | Full project: segments → keywords → videos → moments, plus batches and clips. |
| `DELETE /projects/{id}` | Delete a project, its results and its clip files (refused while anything is running). |
| `POST /projects/{id}/batches` | Run keywords. Body: `{keyword_ids: []}`. |
| `POST /projects/{id}/segments/{segment_id}/keywords` | Add a keyword. Body: `{text}`. |
| `DELETE /keywords/{id}` | Remove a keyword and its results. |
| `POST /projects/{id}/clips` | Queue clip downloads. Body: `{clips: [{video_id, video_title, segment_position, label, start, end}]}`. Moments already downloaded are skipped; failed ones are retried. |
| `GET /clips/{id}/file` | Download one clip. |
| `GET /projects/{id}/clips.zip` | Download every finished clip in a project as a ZIP. |
| `DELETE /clips/{id}` | Delete a clip and its file. |

### Database tables

| Table | Holds |
|---|---|
| `footage_projects` | Title, mode (`script`/`keywords`), script text, status (`analyzing`/`ready`/`error`). |
| `footage_segments` | Segment title, summary, footage note, script excerpt, order. |
| `footage_keywords` | Keyword text, reason, status (`idle`/`queued`/`searching`/`analyzing`/`done`/`error`), progress text, batch. |
| `footage_batches` | One row per **Fetch footage** press, for progress tracking. |
| `footage_videos` | Each video found for a keyword: metadata, relevance (`-1` while still being analysed), verdict, moments (JSON). |
| `footage_transcripts` | Cache of captions, duration and chapters per YouTube video id. |
| `footage_clips` | Downloaded clips: time range, filename, status, file path. |

Tables are created automatically on startup, in SQLite locally or Postgres when `DATABASE_URL` is set.

---

## Search

A single keyword searched across several sources at once.

1. Open the **Search** tab, type a keyword and press **Search**.
2. Results from **YouTube**, the **web** and **Instagram Reels** appear as cards. If one source fails (e.g. a missing API key), its error is shown and the other results still appear.
3. Press **Fetch Clip** on a result to download the whole video with yt-dlp, then play it in place.

Instagram has no public search API, so Reels are found through a Google Custom Search restricted to `site:instagram.com/reel`. That means the Custom Search engine must have **Search the entire web** turned on.

### API

| Method & path | Purpose |
|---|---|
| `POST /api/search` | Body: `{query, sources?: ["youtube", "web", "instagram"]}`. Returns results plus a per-source `errors` map. |
| `GET /api/search-results/{id}` | One result and its download status. |
| `POST /api/search-results/{id}/fetch` | Start downloading the result's video. |
| `GET /api/search-results/{id}/video` | Stream the downloaded video. |

Code lives in `backend/app/search/` and `backend/app/api/search*.py`. Results are stored in the `searches` and `search_results` tables.

---

## Configuration

Set these in `backend/.env` locally, or as environment variables on Render.

| Variable | Used by | Notes |
|---|---|---|
| `GROQ_API_KEY` … `GROQ_API_KEY_7` | Footage | Script splitting and moment matching. When a key hits its rate limit the next key is tried straight away, so more keys means larger batches per day. |
| `YOUTUBE_API_KEY` | Footage, Search | YouTube Data API v3. Optional for Footage (it falls back to yt-dlp search); required for Search's YouTube results. |
| `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` | Search | Web and Instagram results. |
| `MAX_RESULTS_PER_SOURCE` | Search | Default `10`. |
| `FOOTAGE_VIDEOS_PER_KEYWORD` | Footage | Default `5`. Each video costs one LLM call. |
| `FOOTAGE_KEYWORDS_PER_WAVE` | Footage | Default `3`. How many keywords run at the same time. |
| `YTDLP_YOUTUBE_COOKIES_FILE` | Footage, Search | Optional path to a Netscape `cookies.txt` from a logged-in YouTube session. Helps when YouTube blocks the server's IP. |
| `YTDLP_COOKIES_FILE` | Search | Same idea, for Instagram. |

System requirements: `ffmpeg`, `yt-dlp`, and a JavaScript runtime (**Deno**) for yt-dlp to solve YouTube's challenges. Without Deno, YouTube downloads fail with `HTTP Error 403`. The Docker image already includes all three. Locally:

```bash
brew install ffmpeg yt-dlp deno
```

Python dependencies (in `backend/requirements.txt`) include `yt-dlp[default]` and `pypdf` (for reading script PDFs).

---

## Limits & troubleshooting

- **Groq daily token limits**: each video analysed costs roughly 3–5k tokens, and every key shares its daily budget with the app's other features. If keywords fail with rate-limit errors, add more keys or lower `FOOTAGE_VIDEOS_PER_KEYWORD`.
- **YouTube API quota**: a search costs 100 of the default 10,000 daily units (about 100 keywords a day). After that, Footage falls back to yt-dlp search automatically; Search's YouTube results will fail until the quota resets.
- **YouTube blocking the server** (`HTTP Error 403`, `429 Too Many Requests`, "Sign in to confirm you're not a bot"): more common from cloud/datacenter IPs like Render's. Make sure yt-dlp is up to date and Deno is installed, and set `YTDLP_YOUTUBE_COOKIES_FILE`. Caption 429s are retried automatically, and failed caption fetches are not cached, so re-running the keyword tries again.
- **Videos with no captions** can still be matched from their title and chapters, but their times are marked as estimated.
- **Clip storage**: clips are saved under `backend/data/footage_clips/<project id>/`. On hosts without a persistent disk (e.g. Render's free plan) they are wiped on every redeploy. Download what you need soon after cutting it.
- **Scanned PDFs** have no text layer and can't be read. Paste the text instead.
- **Old results**: a keyword's results reflect the matching rules at the time it ran. Use **↻ Re-run** to re-score it.
