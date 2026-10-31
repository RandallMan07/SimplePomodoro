from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request
from unittest.mock import patch

from simplepomodoro.gallery import (API_URL, Cancelled, FreesoundGallery, GalleryError,
                                   MAX_AUDIO_BYTES, _Redirects, browser_search_url)
from simplepomodoro.freesound_credentials import (clear_api_key, credentials_path,
                                                 load_api_key, save_api_key)
from simplepomodoro.sounds import SoundLibrary


AUDIO_URL = "https://cdn.freesound.org/previews/1/123_456-hq.ogg"
SOURCE_URL = "https://freesound.org/people/Example/sounds/123/"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
AUDIO = b"OggS" + b"\x00" * 32
TOKEN = "testcredential123456"


def item(**overrides):
    result = dict(id=123, name="Test bell", url=SOURCE_URL, username="Example",
                  license=LICENSE_URL, duration=0.2, start_time=0.01,
                  previews={"preview-hq-ogg": AUDIO_URL})
    result.update(overrides)
    return result


def sound():
    return FreesoundGallery._parse(item())


class Response(io.BytesIO):
    def __init__(self, data, url=AUDIO_URL, headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers if headers is not None else {"Content-Type": "audio/ogg", "Content-Length": str(len(data))}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return self.response


class FreesoundTests(unittest.TestCase):
    def test_key_in_header_only_and_short_sound_filters(self):
        opener = Opener(Response(json.dumps({"results": [item()]}).encode(), API_URL))
        results = FreesoundGallery(opener, TOKEN).search("bell", purpose="countdown")
        self.assertEqual(results[0].sound_id, 123)
        self.assertIsNone(results[0].size_bytes)  # Original filesize is not preview size.
        request = opener.requests[0]
        self.assertEqual(request.get_header("Authorization"), "Token " + TOKEN)
        self.assertNotIn(TOKEN, request.full_url)
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertIn("duration:[0.05 TO 0.3]", query["filter"][0])
        self.assertIn("start_time:[0 TO 0.03]", query["filter"][0])
        self.assertIn("start_time", query["fields"][0])

    def test_no_key_and_auth_failures_are_actionable(self):
        with self.assertRaisesRegex(GalleryError, "Search in browser"):
            FreesoundGallery(api_key="").search("bell")
        class Unauthorized:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 401, "auth failure", {}, None)
        with self.assertRaisesRegex(GalleryError, "rejected the API key") as failure:
            FreesoundGallery(Unauthorized(), TOKEN).search("bell")
        self.assertNotIn(TOKEN, str(failure.exception))

    def test_long_late_onset_bad_license_and_missing_analysis(self):
        for invalid in (item(duration=442), item(start_time=0.1), item(start_time=None),
                        item(license="https://creativecommons.org/licenses/by-nc/4.0/"),
                        item(previews={"preview-hq-ogg": "https://evil.invalid/audio.ogg"})):
            self.assertIsNone(FreesoundGallery._parse(invalid, "countdown"))
        self.assertIsNotNone(FreesoundGallery._parse(item(start_time=None), "reminder"))
        opener = Opener(Response(json.dumps({"results": [item(start_time=None)]}).encode(), API_URL))
        gallery = FreesoundGallery(opener, TOKEN)
        self.assertEqual(gallery.search("pip", purpose="countdown"), [])
        self.assertIn("no onset analysis", gallery.notice)

    def test_browser_query_filters_encoded_without_key(self):
        url = browser_search_url("bell & chime", "countdown")
        values = parse_qs(urlsplit(url).query)
        self.assertEqual(values["q"], ["bell & chime"])
        self.assertIn("duration:[0.05 TO 0.3]", values["f"][0])
        self.assertNotIn("token", values)

    def test_redirect_never_forwards_token_to_cdn_or_external_host(self):
        request = Request(API_URL, headers={"Authorization": "Token " + TOKEN})
        for url in (AUDIO_URL, "https://evil.invalid/audio.ogg", "http://freesound.org/search/"):
            with self.assertRaises(GalleryError):
                _Redirects().redirect_request(request, None, 302, "redirect", {}, url)

    def test_preview_download_records_actual_size_source_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = Opener(Response(AUDIO))
            path = FreesoundGallery(opener, TOKEN).download(sound(), directory)
            self.assertIsNone(opener.requests[0].get_header("Authorization"))
            self.assertEqual(path.read_bytes(), AUDIO)
            metadata_text = path.with_name(path.name + ".json").read_text()
            metadata = json.loads(metadata_text)
            self.assertEqual(metadata["size_bytes"], len(AUDIO))
            self.assertEqual(metadata["sound_id"], 123)
            self.assertEqual(metadata["download_kind"], "preview")
            self.assertEqual(metadata["source_url"], SOURCE_URL)
            self.assertNotIn(TOKEN, metadata_text)
            self.assertEqual(SoundLibrary(directory).resolve("file:" + path.name).path, path)

    def test_cancel_incomplete_and_oversize_cleanup(self):
        cancel = threading.Event()
        class CancelResponse(Response):
            def read(self, *args):
                result = super().read(*args)
                cancel.set()
                return result
        cases = [(CancelResponse(AUDIO), cancel),
                 (Response(AUDIO, headers={"Content-Type": "audio/ogg", "Content-Length": "1000"}), None),
                 (Response(AUDIO, headers={"Content-Type": "audio/ogg", "Content-Length": str(MAX_AUDIO_BYTES + 1)}), None)]
        for response, cancellation in cases:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(GalleryError):
                    FreesoundGallery(Opener(response), TOKEN).download(sound(), directory, cancellation)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_private_key_save_clear_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": directory, "FREESOUND_API_KEY": ""}):
                save_api_key(TOKEN)
                self.assertEqual(credentials_path().stat().st_mode & 0o777, 0o600)
                self.assertEqual(load_api_key(), TOKEN)
                with patch.dict(os.environ, {"FREESOUND_API_KEY": "environmentexample123"}):
                    self.assertEqual(load_api_key(), "environmentexample123")
                    clear_api_key()
                    self.assertEqual(load_api_key(), "environmentexample123")
                self.assertEqual(load_api_key(), "")


if __name__ == "__main__":
    unittest.main()
