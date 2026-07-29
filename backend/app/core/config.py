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

    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    chunk_seconds: int = 10
    batch_window_seconds: int = 600
    whisper_model: str = "whisper-large-v3-turbo"
    segmentation_model: str = "llama-3.3-70b-versatile"
    verification_model: str = "gpt-4.1"

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    ytdlp_bin: str = "yt-dlp"

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
