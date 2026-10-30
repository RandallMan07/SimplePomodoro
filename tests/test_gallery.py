from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import URLError
from unittest.mock import patch

from simplepomodoro.gallery import (API_URL, Cancelled, CommonsGallery, CommonsSound,
                                   GalleryError, MAX_AUDIO_BYTES, MAX_JSON_BYTES, _Redirects,
                                   allowed_license)
from simplepomodoro.sounds import SoundLibrary


AUDIO_URL = "https://upload.wikimedia.org/wikipedia/commons/a/aa/Bell.ogg"
SOURCE_URL = "https://commons.wikimedia.org/wiki/File:Bell.ogg"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
AUDIO = b"OggS" + b"\x00" * 32


def page(**info_overrides):
    info = dict(url=AUDIO_URL, descriptionurl=SOURCE_URL, size=len(AUDIO), duration=2.5,
                mime="application/ogg", extmetadata=dict(
                    Artist={"value": '<a href="//commons.wikimedia.org/wiki/User:Example">Example &amp; artist</a>'},
                    LicenseShortName={"value": "CC BY-SA 4.0"},
                    LicenseUrl={"value": LICENSE_URL}))
    info.update(info_overrides)
    return dict(title="File:Bell.ogg", index=1, imageinfo=[info])


def sound():
    return CommonsGallery._parse(page())


class Response(io.BytesIO):
    def __init__(self, data, url=AUDIO_URL, headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers or {"Content-Type": "application/ogg", "Content-Length": str(len(data))}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        return self.response


class SearchTests(unittest.TestCase):
    def test_search_audio_filter_strips_html_and_accepts_ogg(self):
        payload = dict(query=dict(pages={"1": page()}))
        opener = Opener(Response(json.dumps(payload).encode(), API_URL))
        found = CommonsGallery(opener).search("bell")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].author, "Example & artist")
        self.assertEqual(found[0].duration_seconds, 2.5)
        self.assertIn("filetype%3Aaudio+bell", opener.calls[0][0])
        self.assertGreater(opener.calls[0][1], 0)

    def test_search_excludes_bad_source_formats_sizes_and_licenses(self):
        variants = [page(url="https://evil.invalid/Bell.ogg"), page(url=AUDIO_URL.replace("https:", "http:")),
                    page(size=MAX_AUDIO_BYTES + 1), page(mime="text/html"),
                    page(descriptionurl="https://evil.invalid/source"), page(url=AUDIO_URL + ".txt"),
                    page(extmetadata=dict(LicenseUrl={"value": "https://creativecommons.org/licenses/by-nc/4.0/"})),
                    page(extmetadata=dict(LicenseUrl={"value": LICENSE_URL}, Restrictions={"value": "trademark"}))]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertIsNone(CommonsGallery._parse(variant))

    def test_plain_public_domain_label_is_normalized(self):
        parsed = CommonsGallery._parse(page(extmetadata=dict(LicenseShortName={"value": "Public domain"})))
        self.assertEqual(parsed.license_url, "https://creativecommons.org/publicdomain/mark/1.0/")
        self.assertTrue(allowed_license(parsed.license_url))

    def test_bad_json_and_oversized_response_are_actionable(self):
        for data in (b"<html>error</html>", b"x" * (MAX_JSON_BYTES + 1)):
            with self.assertRaises(GalleryError):
                CommonsGallery(Opener(Response(data, API_URL))).search("bell")

    def test_error_empty_query_cancel_and_network_failure(self):
        for query in ("", "x" * 121):
            with self.assertRaises(GalleryError):
                CommonsGallery().search(query)
        cancelled = threading.Event()
        cancelled.set()
        opener = Opener(None)
        with self.assertRaises(Cancelled):
            CommonsGallery(opener).search("bell", cancelled)
        self.assertFalse(opener.calls)
        class Offline:
            def open(self, *args, **kwargs):
                raise URLError("offline")
        with self.assertRaisesRegex(GalleryError, "Check your connection"):
            CommonsGallery(Offline()).search("bell")

    def test_redirects_reject_external_host_before_following(self):
        with self.assertRaises(GalleryError):
            _Redirects().redirect_request(None, None, 302, "redirect", {}, "https://evil.invalid/file.ogg")
        with self.assertRaises(GalleryError):
            CommonsGallery(Opener(Response(b"", "https://evil.invalid/file.ogg"))).search("bell")


class DownloadTests(unittest.TestCase):
    def test_complete_audio_and_attribution_join_library_without_clobber(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "Bell.ogg"
            existing.write_bytes(b"existing")
            gallery = CommonsGallery(Opener(Response(AUDIO)))
            destination = gallery.download(sound(), directory)
            self.assertEqual(destination.read_bytes(), AUDIO)
            self.assertEqual(existing.read_bytes(), b"existing")
            metadata = json.loads(destination.with_name(destination.name + ".json").read_text())
            self.assertEqual(metadata["author"], "Example & artist")
            self.assertEqual(metadata["source_url"], SOURCE_URL)
            self.assertEqual(metadata["license_url"], LICENSE_URL)
            self.assertEqual(metadata["audio_url"], AUDIO_URL)
            self.assertIn("downloaded_at", metadata)
            self.assertEqual(SoundLibrary(directory).resolve(f"file:{destination.name}").path, destination)
            self.assertFalse(list(Path(directory).glob("*.part")))

    def assert_failure_leaves_no_files(self, response, expected=GalleryError, cancel=None):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(expected):
                CommonsGallery(Opener(response)).download(sound(), directory, cancel)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_mismatched_length_empty_and_html_rejected(self):
        self.assert_failure_leaves_no_files(Response(AUDIO, headers={"Content-Type": "audio/ogg", "Content-Length": "2"}))
        self.assert_failure_leaves_no_files(Response(b"", headers={"Content-Type": "application/ogg"}))
        self.assert_failure_leaves_no_files(Response(b"<html>error</html>", headers={"Content-Type": "application/ogg"}))
        self.assert_failure_leaves_no_files(Response(AUDIO, headers={"Content-Type": "text/html"}))
        self.assert_failure_leaves_no_files(Response(AUDIO[:-1], headers={"Content-Type": "application/ogg"}))

    def test_cancellation_during_read_cleans_partial_download(self):
        cancel = threading.Event()
        class CancelResponse(Response):
            def read(self, *args):
                result = super().read(*args)
                cancel.set()
                return result
        self.assert_failure_leaves_no_files(CancelResponse(AUDIO), Cancelled, cancel)

    def test_invalid_manual_result_is_rejected_before_network(self):
        opener = Opener(None)
        with tempfile.TemporaryDirectory() as directory:
            for invalid in (replace(sound(), audio_url="http://upload.wikimedia.org/audio.ogg"),
                            replace(sound(), size_bytes=MAX_AUDIO_BYTES + 1),
                            replace(sound(), license_url="https://evil.invalid/license")):
                with self.assertRaises(GalleryError):
                    CommonsGallery(opener).download(invalid, directory)
        self.assertFalse(opener.calls)

    def test_cancellation_between_publication_steps_removes_metadata(self):
        import os
        cancel = threading.Event()
        original_link = os.link
        def cancel_after_link(source, destination):
            original_link(source, destination)
            cancel.set()
        with patch("simplepomodoro.gallery.os.link", side_effect=cancel_after_link):
            self.assert_failure_leaves_no_files(Response(AUDIO), Cancelled, cancel)

    def test_filename_collision_never_overwrites_existing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "Bell-collision.ogg"
            existing.write_bytes(b"keep me")
            class Identifier:
                hex = "collision"
            with patch("simplepomodoro.gallery.uuid.uuid4", return_value=Identifier()):
                with self.assertRaises(GalleryError):
                    CommonsGallery(Opener(Response(AUDIO))).download(sound(), directory)
            self.assertEqual(existing.read_bytes(), b"keep me")
            self.assertEqual(list(Path(directory).iterdir()), [existing])


if __name__ == "__main__":
    unittest.main()
