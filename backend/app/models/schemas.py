from pydantic import BaseModel, field_validator


def _validate_url(value: str) -> str:
    value = value.strip()
    # Cheap sanity check, not a full URL parser -- just enough to reject
    # obviously-wrong input (e.g. someone accidentally pasting a whole file's
    # contents instead of a link) with a clear 400 instead of it silently
    # becoming a reel_checks row that fails later with that pasted content
    # leaking into a yt-dlp error message.
    if len(value) > 2000 or not value.startswith(("http://", "https://")):
        raise ValueError("must be a valid http(s) URL")
    return value


class CreateSessionRequest(BaseModel):
    url: str

    _validate = field_validator("url")(_validate_url)


class SessionResponse(BaseModel):
    id: str
    url: str
    source_type: str
    status: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None


class ClipResponse(BaseModel):
    id: str
    session_id: str
    title: str
    summary: str
    start_seconds: float
    end_seconds: float
    status: str
    created_at: str


class RenameClipRequest(BaseModel):
    title: str | None = None
    summary: str | None = None


class RetrimClipRequest(BaseModel):
    start_seconds: float
    end_seconds: float


class ClipReelResponse(BaseModel):
    id: str
    clip_id: str
    status: str
    hook_text: str | None = None
    audio_style: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class NewspaperResponse(BaseModel):
    session_id: str
    content: str
    created_at: str


class FullArticleResponse(BaseModel):
    clip_id: str
    article: str


class CreateReelCheckRequest(BaseModel):
    url: str

    _validate = field_validator("url")(_validate_url)


class ClaimVerificationResponse(BaseModel):
    quote: str
    timestamp: str
    claim: str
    verdict: str
    analysis: str
    sources: list[str]
    grounded: bool
    official_sources: list[str] = []
    official_verdict: str = "no source found"
    official_analysis: str = ""
    start_seconds: float = 0.0
    end_seconds: float = 0.0


class ReelCheckResponse(BaseModel):
    id: str
    url: str
    status: str
    progress: str
    manuscript: str | None = None
    claims: list[ClaimVerificationResponse]
    conclusion: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class CreateBatchRequest(BaseModel):
    urls: list[str]

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, values: list[str]) -> list[str]:
        return [_validate_url(v) for v in values]


class BatchResponse(BaseModel):
    id: str
    status: str
    created_at: str
    completed_at: str | None = None
    checks: list[ReelCheckResponse]


class TimelineItem(BaseModel):
    type: str  # "claim" | "upload"
    claim_index: int | None = None
    upload_id: str | None = None


class TimelineResponse(BaseModel):
    check_id: str
    items: list[TimelineItem]


class EditorUploadResponse(BaseModel):
    id: str
    check_id: str
    filename: str
    duration_seconds: float


class EditorExportResponse(BaseModel):
    id: str
    check_id: str
    status: str
    output_path: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class InstagramKitResponse(BaseModel):
    id: str
    export_id: str
    check_id: str
    status: str
    caption: str | None = None
    best_time: str | None = None
    audio_style: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class DebunkBeat(BaseModel):
    claim_index: int
    claim_quote: str
    verdict: str
    reaction_narration: str
    humor_cue: str | None = None
    question_cue: str | None = None


class DebunkScriptResponse(BaseModel):
    id: str
    check_id: str
    status: str
    title: str | None = None
    intro_hook: str | None = None
    beats: list[DebunkBeat] = []
    outro_cta: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None
