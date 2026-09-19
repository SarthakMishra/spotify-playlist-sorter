"""Safe YouTube source access and bounded yt-dlp request options."""

from __future__ import annotations

from typing import Any

import yt_dlp

MESSAGES = {
    "cookies": "YouTube couldn't process this request. Try again later.",
    "sign_in": "YouTube is requiring sign-in for this recording. Try again later.",
    "rate_limit": "YouTube is limiting requests. Wait before trying again.",
    "javascript": "YouTube's player check failed. Update Node and yt-dlp.",
    "source_failed": "YouTube lookup failed. Try again later.",
    "download_failed": "Couldn't download complete audio from YouTube.",
    "recording_changed": "The recording details changed. No suitable audio could be downloaded.",
    "analysis_failed": "Couldn't measure this recording's audio.",
}
SHARED_FAILURES = {"cookies", "sign_in", "rate_limit", "javascript"}


class SourceAccessError(Exception):
    """A safe user-facing failure without URLs, paths or credential values."""

    def __init__(self, reason: str) -> None:
        """Retain only a known reason and its public explanation."""
        self.reason = reason
        super().__init__(MESSAGES[reason])

    def result(self) -> dict[str, Any]:
        """Return a terminal recording result."""
        return {"status": "error", "reason": self.reason, "message": str(self)}


def failure_reason(message: str) -> str | None:
    """Classify upstream text without publishing or persisting it."""
    text = message.casefold()
    if any(part in text for part in ("429", "too many requests", "rate limit", "try again later")):
        return "rate_limit"
    if any(part in text for part in ("sign in", "sign-in", "not a bot", "login required", "authentication")):
        return "sign_in"
    if any(
        part in text for part in ("decrypt", "cookie database", "keyring", "secretstorage", "failed to load cookies")
    ):
        return "cookies"
    if any(part in text for part in ("javascript", "js runtime", "challenge solving", "signature extraction", "nsig")):
        return "javascript"
    return None


class YoutubeLogger:
    """Keep actionable warning categories; never log yt-dlp's credential-bearing output."""

    def __init__(self) -> None:
        """Start with no known source failure."""
        self.reason: str | None = None

    def debug(self, _message: str) -> None:
        """Discard verbose extractor details."""

    def warning(self, message: str) -> None:
        """Retain a safe failure category when recognized."""
        self.reason = failure_reason(message) or self.reason

    def error(self, message: str) -> None:
        """Use the same safe categorization for terminal messages."""
        self.warning(message)


def youtube_options() -> dict[str, Any]:
    """Bound retries for all source requests and enable packaged JavaScript support."""
    return {
        "quiet": True,
        "noplaylist": True,
        "noprogress": True,
        "logger": YoutubeLogger(),
        "js_runtimes": {"node": {}},
        "socket_timeout": 15,
        "retries": 2,
        "extractor_retries": 1,
        "fragment_retries": 2,
        "retry_sleep_functions": {key: lambda n: min(2**n, 8) for key in ("http", "fragment", "extractor")},
        "skip_unavailable_fragments": False,
    }


def _safe_reason(error: Exception, logger: YoutubeLogger) -> str:
    """Classify one extractor failure without publishing its text."""
    return failure_reason(str(error)) or logger.reason or "source_failed"


class YoutubeSource:
    """The one yt-dlp adapter behind the source seam; every read failure becomes a safe reason."""

    def search(self, query: str) -> list[dict[str, Any]]:
        """Return flat search entries; any failure raises a safe SourceAccessError."""
        options: dict[str, Any] = {**youtube_options(), "extract_flat": "in_playlist", "format": "bestaudio"}
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(query, download=False) or {}
        except Exception as error:
            raise SourceAccessError(_safe_reason(error, options["logger"])) from error
        return [entry for entry in (info.get("entries") or [info]) if entry]

    def hydrate(self, video_id: str) -> dict[str, Any] | None:
        """Return one upload's full metadata when it matches the id; failures raise safely."""
        options: dict[str, Any] = {**youtube_options(), "extract_flat": "in_playlist", "format": "bestaudio"}
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                video = downloader.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        except Exception as error:
            raise SourceAccessError(_safe_reason(error, options["logger"])) from error
        return video if video and video.get("id") == video_id else None

    def fresh(self, url: str) -> dict[str, Any]:
        """Return current video details for a URL; any failure raises a safe SourceAccessError."""
        options = youtube_options()
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                video = downloader.extract_info(url, download=False)
        except Exception as error:
            raise SourceAccessError(_safe_reason(error, options["logger"])) from error
        return video or {}

    def download(self, video: dict[str, Any], options: dict[str, Any]) -> None:
        """Process one video for download; failures propagate raw so retry policy stays with the caller."""
        with yt_dlp.YoutubeDL({**youtube_options(), **options}) as downloader:
            downloader.process_ie_result(video, download=True)
