"""YouTube access settings and private, read-only cookie snapshots."""

from __future__ import annotations

import os
import re
import shutil
from copy import copy
from importlib.metadata import PackageNotFoundError, version
from io import StringIO
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.cookies import YoutubeDLCookieJar

MESSAGES = {
    "cookies": "Couldn't read YouTube cookies. Open YouTube access and export a fresh cookie file.",
    "sign_in": "YouTube needs sign-in. Open YouTube access to add cookies.",
    "rate_limit": "YouTube is limiting requests. Wait before checking again.",
    "javascript": "YouTube's player check failed. Check Node and yt-dlp updates in YouTube access.",
    "source_failed": "YouTube lookup failed. Try again later or check YouTube access.",
    "download_failed": "Couldn't download complete audio from YouTube.",
    "recording_changed": "The recording details changed. No suitable audio could be downloaded.",
    "analysis_failed": "Couldn't measure this recording's audio.",
}
NETSCAPE_FIELDS = 7
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


def youtube_cookie_text(jar: YoutubeDLCookieJar) -> str:
    """Keep only YouTube cookies in a separate in-memory Netscape export."""
    output = StringIO()
    filtered = YoutubeDLCookieJar(output)
    for cookie in jar:
        domain = cookie.domain.lstrip(".").lower()
        if not cookie.is_expired() and (domain == "youtube.com" or domain.endswith(".youtube.com")):
            filtered.set_cookie(copy(cookie))
    if not list(filtered):
        raise SourceAccessError("cookies")  # noqa: EM101 - fixed reason code.
    filtered.save(ignore_discard=True, ignore_expires=True)
    return output.getvalue()


def validate_cookie_text(text: str) -> str:
    """Validate uploaded/file cookies and discard cookies for unrelated sites."""
    try:
        # yt-dlp warns with raw malformed lines; validate before its parser can print credentials.
        lines = text.removeprefix("\ufeff").splitlines()
        if not lines or not re.fullmatch(r"# (?:Netscape )?HTTP Cookie File", lines[0]):
            raise SourceAccessError("cookies")  # noqa: EM101, TRY301 - fixed reason code.
        normalized = [lines[0]]
        for raw_line in lines[1:]:
            line = raw_line.removeprefix("#HttpOnly_")
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            if (
                len(fields) != NETSCAPE_FIELDS
                or not fields[0]
                or fields[1] not in {"TRUE", "FALSE"}
                or fields[3] not in {"TRUE", "FALSE"}
                or (fields[1] == "TRUE") != fields[0].startswith(".")
                or not re.fullmatch(r"\d{0,15}", fields[4])
            ):
                raise SourceAccessError("cookies")  # noqa: EM101, TRY301 - fixed reason code.
            if fields[4] == "0":
                fields[4] = ""  # Netscape zero denotes a session cookie, not an expired cookie.
            normalized.append("\t".join(fields))
        jar = YoutubeDLCookieJar(StringIO("\n".join(normalized) + "\n"))
        jar.load(ignore_discard=True, ignore_expires=False)
        return youtube_cookie_text(jar)
    except Exception as error:
        raise SourceAccessError("cookies") from error  # noqa: EM101 - fixed reason code.


def configured_cookies() -> str:
    """Snapshot operator-configured cookies once per job; file takes precedence over browser."""
    try:
        if path := os.environ.get("YOUTUBE_COOKIES_FILE"):
            return validate_cookie_text(Path(path).read_text(encoding="utf-8"))
        if browser := os.environ.get("YOUTUBE_BROWSER"):
            logger = YoutubeLogger()
            options = {
                "quiet": True,
                "logger": logger,
                "cookiesfrombrowser": (
                    browser.lower(),
                    os.environ.get("YOUTUBE_BROWSER_PROFILE") or None,
                    (os.environ.get("YOUTUBE_BROWSER_KEYRING") or "").upper() or None,
                    None,
                ),
            }
            with YoutubeDL(options) as browser_reader:
                cookies = youtube_cookie_text(browser_reader.cookiejar)
                if logger.reason:
                    raise SourceAccessError(logger.reason)  # noqa: TRY301
                return cookies
    except SourceAccessError:
        raise
    except Exception as error:
        raise SourceAccessError("cookies") from error  # noqa: EM101 - fixed reason code.
    return ""


def youtube_options(cookie_text: str = "") -> dict[str, Any]:
    """Bound retries for all source requests and enable packaged JavaScript support."""
    options: dict[str, Any] = {
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
    if cookie_text:
        options["cookiefile"] = StringIO(cookie_text)
    return options


def access_status(cookie_text: str | None) -> dict[str, Any]:
    """Expose setup status without reading a browser or returning secrets or local paths."""
    try:
        scripts = version("yt-dlp-ejs")
    except PackageNotFoundError:
        scripts = None
    browser = os.environ.get("YOUTUBE_BROWSER", "").lower()
    return {
        "mode": "server" if cookie_text is None else "upload" if cookie_text else "anonymous",
        "server_source": "file" if os.environ.get("YOUTUBE_COOKIES_FILE") else "browser" if browser else "anonymous",
        "browser": browser
        if browser in {"chrome", "chromium", "firefox", "brave", "edge", "opera", "vivaldi", "safari"}
        else None,
        "node_available": bool(shutil.which("node")),
        "scripts_available": bool(scripts),
        "yt_dlp_version": version("yt-dlp"),
    }
