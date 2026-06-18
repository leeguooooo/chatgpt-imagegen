#!/usr/bin/env python3
"""Unit tests for chatgpt-imagegen's pure helpers — stdlib `unittest`, no deps.

The CLI ships as a single extension-less script, so we load it as a module via
the SourceFileLoader trick. These cover the browser-free logic (MIME sniffing,
version parsing, prompt building, path defaults, token extraction, the capped
ref download) so a refactor that breaks them fails loudly.

Run:  python3 -m unittest test_chatgpt_imagegen -v
"""

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

_loader = importlib.machinery.SourceFileLoader(
    "cig", os.path.join(os.path.dirname(__file__), "chatgpt-imagegen"))
_spec = importlib.util.spec_from_loader("cig", _loader)
cig = importlib.util.module_from_spec(_spec)
_loader.exec_module(cig)


@contextmanager
def _in_tmp_cwd():
    prev = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            yield Path(d)
        finally:
            os.chdir(prev)


class SniffMime(unittest.TestCase):
    def test_png(self):
        self.assertEqual(cig._sniff_mime(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8), "image/png")

    def test_jpeg(self):
        self.assertEqual(cig._sniff_mime(b"\xff\xd8\xff" + b"\x00" * 8), "image/jpeg")

    def test_webp(self):
        self.assertEqual(cig._sniff_mime(b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"), "image/webp")

    def test_unknown(self):
        self.assertIsNone(cig._sniff_mime(b"not an image at all"))


class VersionTuple(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(cig._version_tuple("1.5.23"), (1, 5, 23))
        self.assertEqual(cig._version_tuple("chrome-use 1.5.23"), (1, 5, 23))

    def test_ordering(self):
        self.assertLess(cig._version_tuple("1.4.9"), cig._version_tuple("1.5.0"))
        self.assertLess(cig._version_tuple("1.5.0"), cig._version_tuple("1.5.23"))

    def test_junk(self):
        self.assertEqual(cig._version_tuple("garbage"), (0,))

    def test_min_floor(self):
        self.assertGreaterEqual(cig._version_tuple("1.5.23"),
                                cig._version_tuple(cig.AB_MIN_VERSION))
        self.assertLess(cig._version_tuple("1.4.0"),
                        cig._version_tuple(cig.AB_MIN_VERSION))


class IsUrl(unittest.TestCase):
    def test_true(self):
        self.assertTrue(cig._is_url("http://x.com/a.png"))
        self.assertTrue(cig._is_url("https://x.com/a.png"))

    def test_false(self):
        self.assertFalse(cig._is_url("/local/a.png"))
        self.assertFalse(cig._is_url("a.png"))
        self.assertFalse(cig._is_url("ftp://x.com/a.png"))


class BuildWebText(unittest.TestCase):
    def test_plain_has_no_codex_tool_wording(self):
        t = cig._build_web_text("a red apple", "auto")
        self.assertIn("a red apple", t)
        self.assertNotIn("image_generation tool", t)
        self.assertNotIn("Output format", t)

    def test_size_folded_in(self):
        self.assertIn("1024x1536", cig._build_web_text("x", "1024x1536"))
        self.assertNotIn("auto", cig._build_web_text("x", "auto").lower())

    def test_edit_anchors_on_reference(self):
        t = cig._build_web_text("make it blue", "auto", is_edit=True)
        self.assertIn("attached", t.lower())


class BuildUserText(unittest.TestCase):
    def test_codex_keeps_tool_wording(self):
        t = cig._build_user_text("a cat", "auto", "png")
        self.assertIn("image_generation tool", t)
        self.assertIn("png", t)


class DefaultOutPath(unittest.TestCase):
    def test_slugifies_and_numbers(self):
        with _in_tmp_cwd():
            p1 = cig._default_out_path("A Red Apple!!", "png")
            self.assertEqual(p1, Path("assets/generated/a-red-apple.png"))
            p1.parent.mkdir(parents=True, exist_ok=True)
            p1.write_bytes(b"x")
            p2 = cig._default_out_path("A Red Apple!!", "png")
            self.assertEqual(p2.name, "a-red-apple-2.png")

    def test_empty_prompt_fallback(self):
        with _in_tmp_cwd():
            self.assertEqual(cig._default_out_path("!!!", "webp").name, "image.webp")


class ExtractAccessToken(unittest.TestCase):
    def test_reads_nested_tokens(self):
        auth = {"tokens": {"access_token": "AAA", "account_id": "acc",
                           "refresh_token": "RRR"}}
        access, account, refresh = cig._extract_access_token(auth)
        self.assertEqual((access, refresh), ("AAA", "RRR"))

    def test_missing(self):
        access, _account, _refresh = cig._extract_access_token({})
        self.assertIsNone(access)


class DownloadRefCap(unittest.TestCase):
    @contextmanager
    def _fake_urlopen(self, body: bytes):
        import urllib.request
        real = urllib.request.urlopen

        class _Resp:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_, n=-1):
                return body[:n] if n and n > 0 else body

        urllib.request.urlopen = lambda *a, **k: _Resp()
        try:
            yield
        finally:
            urllib.request.urlopen = real

    def test_small_ok(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with self._fake_urlopen(png):
            self.assertEqual(cig._download_ref_url("https://x/a.png"), png)

    def test_over_cap_exits(self):
        big = b"\x00" * (cig.REF_DOWNLOAD_MAX + 10)
        with self._fake_urlopen(big):
            with self.assertRaises(SystemExit):
                cig._download_ref_url("https://x/huge.png")


if __name__ == "__main__":
    unittest.main()
