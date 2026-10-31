"""Explicit, bounded Freesound searches and preview-format downloads."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from .sounds import SUPPORTED_EXTENSIONS
from .freesound_credentials import CredentialError, load_api_key

API_URL = "https://freesound.org/apiv2/search/"
MEDIA_HOSTS = ("cdn.freesound.org", "freesound.org")
CUE_LIMITS = {"reminder": 3.0, "countdown": 0.3}
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 12
OPERATION_TIMEOUT_SECONDS = 45
USER_AGENT = "SimplePomodoro/0.1 (https://github.com/RandallMan07/SimplePomodoro)"


class GalleryError(Exception):
    pass


class Cancelled(GalleryError):
    pass


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = _Text()
    parser.feed(str(value))
    return " ".join(" ".join(parser.parts).split())[:2000]


def valid_url(url, host):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == host
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def allowed_license(url):
    """Recognize explicit free licenses, rather than trusting a display label."""
    if not valid_url(url, "creativecommons.org"):
        return False
    path = urlsplit(url).path.rstrip("/")
    return bool(re.fullmatch(r"/(licenses/(by|by-sa)/(1\.0|2\.0|2\.5|3\.0|4\.0)|publicdomain/(zero/1\.0|mark/1\.0))", path))


@dataclass(frozen=True)
class GallerySound:
    title: str
    author: str
    source_url: str
    license_name: str
    license_url: str
    audio_url: str
    size_bytes: int | None
    duration_seconds: float | None
    mime: str
    sound_id: int = 0
    start_time_seconds: float | None = None

    @property
    def filename(self):
        return unquote(urlsplit(self.audio_url).path.rsplit("/", 1)[-1])


def search_filter(purpose="reminder"):
    maximum = CUE_LIMITS.get(purpose, CUE_LIMITS["reminder"])
    value = f'duration:[0.05 TO {maximum:g}] license:("Creative Commons 0" OR "Attribution")'
    if purpose == "countdown":
        value += " start_time:[0 TO 0.03]"
    return value


def browser_search_url(query, purpose="reminder"):
    return "https://freesound.org/search/?" + urlencode({"q": query.strip(), "f": search_filter(purpose)})


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not any(valid_url(newurl, host) for host in MEDIA_HOSTS):
            raise GalleryError("Freesound redirected to an unsupported address.")
        # Never forward an API credential onto a CDN or another origin.
        if request.has_header("Authorization") and not valid_url(newurl, "freesound.org"):
            raise GalleryError("Freesound redirected an authenticated request to another host.")
        return super().redirect_request(request, fp, code, message, headers, newurl)


class FreesoundGallery:
    def __init__(self, opener=None, api_key=None):
        self.opener = opener or build_opener(_Redirects())
        self.api_key = api_key
        self.notice = ""

    @staticmethod
    def _check(cancel, deadline):
        if cancel.is_set():
            raise Cancelled("Cancelled.")
        if time.monotonic() > deadline:
            raise GalleryError("The gallery request timed out. Try again with a shorter search.")

    def _open(self, url, host, cancel, deadline, api_key=None):
        self._check(cancel, deadline)
        if not valid_url(url, host):
            raise GalleryError("Freesound returned an unsupported address.")
        headers = {"User-Agent": USER_AGENT}
        if api_key:
            if host != "freesound.org":
                raise GalleryError("API credentials can only be sent to Freesound.")
            headers["Authorization"] = "Token " + api_key
        response = self.opener.open(Request(url, headers=headers), timeout=REQUEST_TIMEOUT_SECONDS)
        if not valid_url(response.geturl(), host):
            response.close()
            raise GalleryError("Freesound redirected to an unsupported address.")
        return response

    def search(self, query, cancel=None, purpose="reminder"):
        cancel = cancel or threading.Event()
        query = query.strip()
        self.notice = ""
        if not query or len(query) > 120:
            raise GalleryError("Enter a search between 1 and 120 characters.")
        try:
            api_key = self.api_key if self.api_key is not None else load_api_key()
        except CredentialError as error:
            raise GalleryError(str(error)) from None
        if not api_key:
            raise GalleryError("Set your Freesound API key in API key setup, or use Search in browser without a key.")
        if purpose not in CUE_LIMITS:
            raise GalleryError("Choose Reminder or Countdown pip before searching.")
        parameters = dict(query=query, filter=search_filter(purpose), page_size=15,
                          fields="id,name,url,username,license,duration,previews,start_time")
        deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
        try:
            with self._open(API_URL + "?" + urlencode(parameters), "freesound.org", cancel, deadline, api_key) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
            self._check(cancel, deadline)
            if len(raw) > MAX_JSON_BYTES:
                raise GalleryError("The response was too large. Try a more specific search.")
            payload = json.loads(raw)
            results = []
            missing_onset = False
            for item in payload.get("results", []):
                if item.get("start_time") is None:
                    missing_onset = True
                sound = self._parse(item, purpose)
                if sound:
                    results.append(sound)
            if missing_onset:
                self.notice = ("Some sounds have no onset analysis. They are excluded from Countdown searches; try Reminder and preview carefully.")
            elif purpose == "countdown" and not results:
                self.notice = "Countdown requires a 0.05–0.30 second sound with onset within 30 ms. Try beep or pip, or switch to Reminder."
            return results
        except HTTPError as error:
            if error.code in (401, 403):
                raise GalleryError("Freesound rejected the API key. Check your application key and save it again.") from None
            if error.code == 429:
                raise GalleryError("Freesound's request limit was reached. Wait before searching again.") from None
            raise GalleryError("Freesound could not complete this search. Try again later.") from None
        except (URLError, TimeoutError, OSError):
            raise GalleryError("Could not reach Freesound. Check your connection and try again.") from None
        except (ValueError, TypeError, AttributeError):
            raise GalleryError("Freesound returned an unreadable response. Try again later.") from None

    @staticmethod
    def _parse(item, purpose="reminder"):
        try:
            sound_id = item["id"]
            source = item["url"]
            license_url = item["license"].replace("http://creativecommons.org/", "https://creativecommons.org/")
            duration = item["duration"]
            onset = item.get("start_time")
            previews = item["previews"]
            audio_url = previews.get("preview-hq-ogg") or previews.get("preview-hq-mp3")
            if (type(sound_id) is not int or sound_id <= 0 or not valid_url(source, "freesound.org")
                    or not any(valid_url(audio_url, host) for host in MEDIA_HOSTS)
                    or not allowed_license(license_url)
                    or "/licenses/by-sa/" in license_url or "/publicdomain/mark/" in license_url
                    or type(duration) not in (int, float) or not math.isfinite(duration)
                    or not 0.05 <= duration <= CUE_LIMITS.get(purpose, 3.0)):
                return None
            if type(onset) not in (int, float) or not math.isfinite(onset) or onset < 0:
                onset = None
            if purpose == "countdown" and (onset is None or onset > 0.03):
                return None
            extension = Path(unquote(urlsplit(audio_url).path)).suffix.lower()
            if extension not in (".ogg", ".mp3"):
                return None
            license_name = "CC0" if "/publicdomain/zero/" in license_url else "CC BY"
            return GallerySound(plain_text(item["name"]), plain_text(item["username"]), source,
                                license_name, license_url, audio_url, None, duration,
                                "audio/ogg" if extension == ".ogg" else "audio/mpeg", sound_id, onset)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            return None

    def download(self, sound, directory, cancel=None):
        cancel = cancel or threading.Event()
        deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
        self._check(cancel, deadline)
        if (not any(valid_url(sound.audio_url, host) for host in MEDIA_HOSTS) or not allowed_license(sound.license_url)
                or not valid_url(sound.source_url, "freesound.org")
                or (sound.size_bytes is not None and not 0 < sound.size_bytes <= MAX_AUDIO_BYTES)
                or sound.duration_seconds is None or not 0.05 <= sound.duration_seconds <= 3):
            raise GalleryError("This result does not meet the gallery download limits.")
        directory = Path(directory)
        suffix = Path(sound.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise GalleryError("This audio format is unsupported.")
        title = Path(sound.title).stem or Path(sound.filename).stem
        stem = re.sub(r"[^\w-]+", "-", title, flags=re.ASCII).strip("-")[:60] or "sound"
        stem = f"freesound-{sound.sound_id}-{stem}"
        destination = directory / f"{stem}-{uuid.uuid4().hex[:12]}{suffix}"
        sidecar = destination.with_name(destination.name + ".json")
        audio_temp = destination.with_name("." + destination.name + ".part")
        metadata_temp = sidecar.with_name("." + sidecar.name + ".part")
        published_audio = False
        published_metadata = False
        completed = False
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with self._open(sound.audio_url, urlsplit(sound.audio_url).hostname, cancel, deadline) as response:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if not (content_type.startswith("audio/") or content_type in ("application/ogg", "application/octet-stream")):
                    raise GalleryError("The gallery did not return an audio file.")
                content_length = response.headers.get("Content-Length")
                expected_size = int(content_length) if content_length is not None else sound.size_bytes
                if expected_size is not None and not 0 < expected_size <= MAX_AUDIO_BYTES:
                    raise GalleryError("This preview exceeds the download size limit.")
                count = 0
                with audio_temp.open("xb") as output:
                    while True:
                        self._check(cancel, deadline)
                        chunk = response.read(64 * 1024)
                        self._check(cancel, deadline)
                        if not chunk:
                            break
                        if count == 0 and chunk.lstrip().lower().startswith((b"<!doctype html", b"<html", b"<?xml", b"{\"error\"")):
                            raise GalleryError("The gallery returned an error page instead of audio.")
                        count += len(chunk)
                        if count > MAX_AUDIO_BYTES or (expected_size is not None and count > expected_size):
                            raise GalleryError("The download exceeds the file size limit.")
                        output.write(chunk)
                if not count or (expected_size is not None and count != expected_size):
                    raise GalleryError("The audio download was incomplete. Try again.")
            provenance = asdict(sound)
            provenance.update(provider="Freesound", download_kind="preview", size_bytes=count, downloaded_at=datetime.now(timezone.utc).isoformat(),
                              local_filename=destination.name)
            with metadata_temp.open("x", encoding="utf-8") as output:
                json.dump(provenance, output, indent=2, ensure_ascii=False)
                output.write("\n")
            self._check(cancel, deadline)
            # Same-directory hard links publish complete files without overwriting.
            os.link(metadata_temp, sidecar)
            published_metadata = True
            self._check(cancel, deadline)
            os.link(audio_temp, destination)
            published_audio = True
            self._check(cancel, deadline)
            completed = True
            return destination
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            raise GalleryError("Could not download this preview. Check your connection and sound folder, then retry.") from None
        finally:
            for temporary in (audio_temp, metadata_temp):
                temporary.unlink(missing_ok=True)
            if cancel.is_set() or not completed:
                if published_audio:
                    destination.unlink(missing_ok=True)
                if published_metadata:
                    sidecar.unlink(missing_ok=True)
