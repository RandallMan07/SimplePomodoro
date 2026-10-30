"""Explicit, bounded Wikimedia Commons sound search and downloads."""
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

API_URL = "https://commons.wikimedia.org/w/api.php"
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
class CommonsSound:
    title: str
    author: str
    source_url: str
    license_name: str
    license_url: str
    audio_url: str
    size_bytes: int
    duration_seconds: float | None
    mime: str

    @property
    def filename(self):
        return unquote(urlsplit(self.audio_url).path.rsplit("/", 1)[-1])


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not (valid_url(newurl, "commons.wikimedia.org") or valid_url(newurl, "upload.wikimedia.org")):
            raise GalleryError("The gallery redirected to an unsupported address.")
        return super().redirect_request(request, fp, code, message, headers, newurl)


class CommonsGallery:
    def __init__(self, opener=None):
        self.opener = opener or build_opener(_Redirects())

    @staticmethod
    def _check(cancel, deadline):
        if cancel.is_set():
            raise Cancelled("Cancelled.")
        if time.monotonic() > deadline:
            raise GalleryError("The gallery request timed out. Try again with a shorter search.")

    def _open(self, url, host, cancel, deadline):
        self._check(cancel, deadline)
        if not valid_url(url, host):
            raise GalleryError("The gallery returned an unsupported address.")
        response = self.opener.open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=REQUEST_TIMEOUT_SECONDS)
        if not valid_url(response.geturl(), host):
            response.close()
            raise GalleryError("The gallery redirected to an unsupported address.")
        return response

    def search(self, query, cancel=None):
        cancel = cancel or threading.Event()
        query = query.strip()
        if not query or len(query) > 120:
            raise GalleryError("Enter a search between 1 and 120 characters.")
        parameters = dict(action="query", format="json", generator="search",
                          gsrsearch=f"filetype:audio {query}", gsrnamespace=6, gsrlimit=10,
                          prop="imageinfo", iiprop="url|size|mime|extmetadata")
        deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
        try:
            with self._open(API_URL + "?" + urlencode(parameters), "commons.wikimedia.org", cancel, deadline) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
            self._check(cancel, deadline)
            if len(raw) > MAX_JSON_BYTES:
                raise GalleryError("The gallery response was too large. Try a more specific search.")
            payload = json.loads(raw)
            if "error" in payload:
                raise GalleryError("The gallery could not complete this search. Try again later.")
            pages = payload.get("query", {}).get("pages", {})
            results = []
            for page in sorted(pages.values(), key=lambda page: page.get("index", 0)):
                sound = self._parse(page)
                if sound:
                    results.append(sound)
            return results
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise GalleryError(f"Could not reach Wikimedia Commons: {error}. Check your connection and try again.") from error
        except (ValueError, TypeError, AttributeError) as error:
            raise GalleryError("The gallery returned an unreadable response. Try again later.") from error

    @staticmethod
    def _parse(page):
        try:
            info = page["imageinfo"][0]
            metadata = info.get("extmetadata", {})
            def value(key):
                return plain_text(metadata.get(key, {}).get("value", ""))
            audio_url = info["url"]
            mime = info["mime"]
            source = info["descriptionurl"]
            license_url = value("LicenseUrl")
            if license_url.startswith("//"):
                license_url = "https:" + license_url
            elif license_url.startswith("http://creativecommons.org/"):
                license_url = "https:" + license_url[5:]
            # Commons public-domain records sometimes omit LicenseUrl entirely.
            if not license_url and value("LicenseShortName").lower() in ("public domain", "cc0"):
                license_url = "https://creativecommons.org/publicdomain/mark/1.0/" if value("LicenseShortName").lower() == "public domain" else "https://creativecommons.org/publicdomain/zero/1.0/"
            size = info["size"]
            extension = Path(unquote(urlsplit(audio_url).path)).suffix.lower()
            if (not valid_url(audio_url, "upload.wikimedia.org") or not valid_url(source, "commons.wikimedia.org")
                    or not allowed_license(license_url) or extension not in SUPPORTED_EXTENSIONS
                    or not (mime.startswith("audio/") or mime == "application/ogg")
                    or type(size) is not int or not 0 < size <= MAX_AUDIO_BYTES
                    or value("Restrictions")):
                return None
            duration = info.get("duration")
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
                duration = None
            return CommonsSound(plain_text(page["title"].removeprefix("File:")), value("Artist") or "Unknown creator (see source)",
                                source, value("LicenseShortName") or "Creative Commons", license_url,
                                audio_url, size, duration, mime)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            return None

    def download(self, sound, directory, cancel=None):
        cancel = cancel or threading.Event()
        deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
        self._check(cancel, deadline)
        if (not valid_url(sound.audio_url, "upload.wikimedia.org") or not allowed_license(sound.license_url)
                or not valid_url(sound.source_url, "commons.wikimedia.org")
                or not 0 < sound.size_bytes <= MAX_AUDIO_BYTES):
            raise GalleryError("This result does not meet the gallery download limits.")
        directory = Path(directory)
        suffix = Path(sound.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise GalleryError("This audio format is unsupported.")
        stem = re.sub(r"[^\w-]+", "-", Path(sound.filename).stem, flags=re.ASCII).strip("-")[:70] or "sound"
        destination = directory / f"{stem}-{uuid.uuid4().hex[:12]}{suffix}"
        sidecar = destination.with_name(destination.name + ".json")
        audio_temp = destination.with_name("." + destination.name + ".part")
        metadata_temp = sidecar.with_name("." + sidecar.name + ".part")
        published_audio = False
        published_metadata = False
        completed = False
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with self._open(sound.audio_url, "upload.wikimedia.org", cancel, deadline) as response:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if not (content_type.startswith("audio/") or content_type in ("application/ogg", "application/octet-stream")):
                    raise GalleryError("The gallery did not return an audio file.")
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) != sound.size_bytes:
                    raise GalleryError("The gallery file changed size. Search again before downloading.")
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
                        if count > MAX_AUDIO_BYTES or count > sound.size_bytes:
                            raise GalleryError("The download exceeds the file size limit.")
                        output.write(chunk)
                if count != sound.size_bytes:
                    raise GalleryError("The audio download was incomplete. Try again.")
            provenance = asdict(sound)
            provenance.update(provider="Wikimedia Commons", downloaded_at=datetime.now(timezone.utc).isoformat(),
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
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise GalleryError(f"Could not download this sound: {error}. Check your connection and sound folder, then retry.") from error
        finally:
            for temporary in (audio_temp, metadata_temp):
                temporary.unlink(missing_ok=True)
            if cancel.is_set() or not completed:
                if published_audio:
                    destination.unlink(missing_ok=True)
                if published_metadata:
                    sidecar.unlink(missing_ok=True)
