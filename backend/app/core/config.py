from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_api_key_4: str = ""
    groq_api_key_5: str = ""
    groq_api_key_6: str = ""
    groq_api_key_7: str = ""

    openai_api_key: str = ""

    # Qdrant Cloud cluster used by the claim-verification RAG pipeline (see
    # app/rag/claim_store.py) to retrieve context from earlier claims in the
    # same video when verifying a later, possibly-continuation claim. Left
    # unset, that retrieval step is skipped and verification behaves exactly
    # as before -- it never blocks the pipeline.
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "claim_chunks"

    # Separate Qdrant collection holding ingested Indian-government source
    # documents (see app/rag/gov_store.py, populated by
    # scripts/ingest_gov_sources.py) that claim verification retrieves from
    # for grounding -- distinct from qdrant_collection above, which only
    # holds per-video claim chunks for intra-video context.
    qdrant_gov_collection: str = "gov_sources"

    # Free-signup API key for data.gov.in / OGD Platform India
    # (https://data.gov.in/user/register, then https://data.gov.in/apis),
    # used by scripts/ingest_gov_sources.py to pull real government datasets
    # into qdrant_gov_collection. Left unset, data.gov.in ingestion is
    # skipped -- it never blocks the app.
    data_gov_in_api_key: str = ""

    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    # If set, structured data (sessions, fact-checks, timelines, etc.) is
    # stored in this Postgres database instead of the local SQLite file --
    # used in production so that data survives restarts/redeploys on hosts
    # with an ephemeral filesystem. Render injects this automatically when a
    # Postgres database is attached via render.yaml. Video/image/PDF files
    # still live on local disk either way (see data_dir) and are NOT covered
    # by this -- they still don't survive a restart without a mounted disk.
    database_url: str = ""

    chunk_seconds: int = 10
    batch_window_seconds: int = 600
    whisper_model: str = "whisper-large-v3-turbo"
    # llama-3.3-70b-versatile was retired from Groq's hosted lineup (404
    # model_not_found on this account as of 2026-08) -- gpt-oss-120b is
    # Groq's current flagship general-purpose hosted model and, like the
    # model it replaces, supports response_format={"type": "json_object"},
    # which every caller of this setting relies on.
    segmentation_model: str = "openai/gpt-oss-120b"
    verification_model: str = "gpt-4.1"

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    ytdlp_bin: str = "yt-dlp"

    # Path to a Netscape-format cookies.txt exported from a real logged-in
    # browser session. Some platforms (Instagram especially) serve a more
    # restricted format list -- sometimes video with no audio track at all
    # -- to requests that look unauthenticated/automated, particularly from
    # datacenter IPs; a logged-in session is generally treated less
    # suspiciously. Left unset, yt-dlp runs unauthenticated as before. On
    # Render, upload the file as a Secret File and point this at
    # /etc/secrets/<filename>.
    ytdlp_cookies_file: str = ""

    # Comma-separated list of allowed frontend origins for CORS, e.g.
    # "https://live-cutter.onrender.com,https://live-cutter.vercel.app".
    # Defaults to the Vite dev server so local development keeps working
    # with no .env changes.
    cors_origins: str = "http://localhost:5173"

    # Whether the session cookie requires HTTPS. Must be true in production
    # (Render/Vercel serve HTTPS) -- kept false by default so login works on
    # plain http://localhost during local development.
    cookie_secure: bool = False

    # If set, main.py serves the built frontend (index.html + assets) from
    # this directory and API/static share one origin -- used only in the
    # production Docker image, where the frontend is prebuilt into it. Unset
    # locally, where the Vite dev server runs separately on :5173.
    static_dir: Path | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_api_keys(self) -> list[str]:
        """All configured Groq keys, in order. Multiple keys let the app
        round-robin across them to spread load past any single key's rate
        limit during continuous transcription (see groq_pool.py)."""
        candidates = [
            self.groq_api_key, self.groq_api_key_2, self.groq_api_key_3,
            self.groq_api_key_4, self.groq_api_key_5, self.groq_api_key_6,
            self.groq_api_key_7,
        ]
        return [k for k in candidates if k and "placeholder" not in k]


settings = Settings()
