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
import re
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


@contextmanager
def _tmp_xdg():
    """Isolate styles.json under a temp XDG_CONFIG_HOME so tests never touch ~/.config."""
    prev = os.environ.get("XDG_CONFIG_HOME")
    with tempfile.TemporaryDirectory() as d:
        os.environ["XDG_CONFIG_HOME"] = d
        try:
            yield Path(d)
        finally:
            if prev is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = prev


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


class UpdateNotify(unittest.TestCase):
    """The once-a-day self-update reminder: throttle, cache, env-disable, parse,
    and the what's-new changelog surfaced in the notice."""

    @contextmanager
    def _patched_fetch(self, version, notes=None, counter=None):
        orig = cig._fetch_latest_info

        def fake(timeout=4.0):
            if counter is not None:
                counter["n"] += 1
            return version, (notes or {})
        cig._fetch_latest_info = fake
        try:
            yield
        finally:
            cig._fetch_latest_info = orig

    def test_notifies_when_newer(self):
        with _tmp_xdg(), self._patched_fetch("9.9.9", {"9.9.9": "shiny new thing"}):
            msgs = []
            cig._maybe_notify_update(msgs.append)
            self.assertTrue(msgs and "9.9.9" in msgs[0])

    def test_notice_lists_what_changed(self):
        with _tmp_xdg(), self._patched_fetch("9.9.9", {"9.9.9": "shiny new thing"}):
            msgs = []
            cig._maybe_notify_update(msgs.append)
            self.assertIn("shiny new thing", msgs[0])

    def test_silent_when_same_or_older(self):
        with _tmp_xdg(), self._patched_fetch(cig.__version__):
            msgs = []
            cig._maybe_notify_update(msgs.append)
            self.assertEqual(msgs, [])

    def test_throttled_no_network_within_interval(self):
        with _tmp_xdg():
            counter = {"n": 0}
            with self._patched_fetch("9.9.9", {"9.9.9": "x"}, counter):
                cig._maybe_notify_update(lambda _m: None)        # first: hits network
                cig._maybe_notify_update(lambda _m: None)        # second: cached
            self.assertEqual(counter["n"], 1)

    def test_uses_cached_latest_when_throttled(self):
        with _tmp_xdg():
            with self._patched_fetch("9.9.9", {"9.9.9": "cached note"}):
                cig._maybe_notify_update(lambda _m: None)        # populate cache
            # Network would now report an older version, but throttle keeps cached 9.9.9.
            with self._patched_fetch("0.0.1", {"0.0.1": "stale"}):
                msgs = []
                cig._maybe_notify_update(msgs.append)
            self.assertTrue(msgs and "9.9.9" in msgs[0] and "cached note" in msgs[0])

    def test_env_disable_is_noop(self):
        with _tmp_xdg():
            counter = {"n": 0}
            os.environ["CHATGPT_IMAGEGEN_NO_UPDATE_CHECK"] = "1"
            try:
                with self._patched_fetch("9.9.9", {"9.9.9": "x"}, counter):
                    msgs = []
                    cig._maybe_notify_update(msgs.append)
            finally:
                os.environ.pop("CHATGPT_IMAGEGEN_NO_UPDATE_CHECK", None)
            self.assertEqual((counter["n"], msgs), (0, []))

    def test_changes_since_filters_and_orders(self):
        notes = {"0.1.0": "old", "9.9.0": "mid", "9.9.9": "new"}
        self.assertEqual(cig._changes_since(notes, base="9.8.0"),
                         [("9.9.9", "new"), ("9.9.0", "mid")])

    def test_format_notice_caps_lines(self):
        notes = {f"9.0.{i}": f"change {i}" for i in range(1, 6)}
        out = cig._format_update_notice("9.0.5", notes, max_lines=3)
        self.assertEqual(out.count("\n  •"), 4)          # 3 changes + "另有 N 项"
        self.assertIn("另有 2 项", out)

    def test_parse_whatsnew_from_real_header(self):
        # Both __version__ and the newest WHATSNEW line must sit in the first 8KB,
        # since the reminder only reads that prefix of the remote script.
        head = Path(os.path.join(os.path.dirname(__file__),
                                 "chatgpt-imagegen")).read_text()[:8192]
        m = re.search(r'__version__\s*=\s*"([\d.]+)"', head)
        self.assertEqual(m.group(1), cig.__version__)
        notes = cig._parse_whatsnew(head)
        self.assertIn(cig.__version__, notes)            # current release is documented
        self.assertTrue(notes[cig.__version__])


class IsUrl(unittest.TestCase):
    def test_true(self):
        self.assertTrue(cig._is_url("http://x.com/a.png"))
        self.assertTrue(cig._is_url("https://x.com/a.png"))

    def test_false(self):
        self.assertFalse(cig._is_url("/local/a.png"))
        self.assertFalse(cig._is_url("a.png"))
        self.assertFalse(cig._is_url("ftp://x.com/a.png"))


class ValidStyleName(unittest.TestCase):
    def test_accepts_slugs(self):
        for ok in ("doodle", "flat-icon", "v2", "a", "my_style"):
            self.assertTrue(cig._valid_style_name(ok), ok)

    def test_rejects_bad(self):
        for bad in ("", "Doodle", "has space", "-leading", "_leading", "with.dot", "藝術"):
            self.assertFalse(cig._valid_style_name(bad), bad)


class ComposePrompt(unittest.TestCase):
    def test_appends_with_comma(self):
        self.assertEqual(cig._compose_prompt("a cat", "watercolor"), "a cat, watercolor")

    def test_none_or_blank_snippet_unchanged(self):
        self.assertEqual(cig._compose_prompt("a cat", None), "a cat")
        self.assertEqual(cig._compose_prompt("a cat", "   "), "a cat")

    def test_strips_one_trailing_punct(self):
        self.assertEqual(cig._compose_prompt("a cat.", "watercolor"), "a cat, watercolor")
        self.assertEqual(cig._compose_prompt("a cat, ", "watercolor"), "a cat, watercolor")

    def test_empty_prompt_yields_snippet(self):
        self.assertEqual(cig._compose_prompt("", "watercolor"), "watercolor")

    def test_snippet_is_trimmed(self):
        self.assertEqual(cig._compose_prompt("a cat", "  watercolor  "), "a cat, watercolor")


class StyleStorage(unittest.TestCase):
    def test_path_honors_xdg(self):
        with _tmp_xdg() as d:
            self.assertEqual(cig._styles_path(),
                             Path(d) / "chatgpt-imagegen" / "styles.json")

    def test_load_seeds_builtins_when_missing(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            self.assertEqual(doc["default"], "")
            self.assertIn("doodle", doc["styles"])
            self.assertTrue(cig._styles_path().exists())  # seeded to disk

    def test_existing_file_not_reseeded(self):
        with _tmp_xdg():
            cig._load_styles()                    # seed
            doc = cig._load_styles()
            del doc["styles"]["doodle"]           # user removes the builtin
            cig._save_styles(doc)
            again = cig._load_styles()
            self.assertNotIn("doodle", again["styles"])  # stays deleted

    def test_save_roundtrip_and_atomic(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["custom"] = "neon glow"
            doc["default"] = "custom"
            cig._save_styles(doc)
            reread = cig._load_styles()
            self.assertEqual(reread["styles"]["custom"], "neon glow")
            self.assertEqual(reread["default"], "custom")
            # no leftover temp file beside the target
            self.assertEqual(list(cig._styles_path().parent.glob("*.tmp")), [])

    def test_corrupt_file_raises(self):
        with _tmp_xdg():
            p = cig._styles_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{not json", encoding="utf-8")
            with self.assertRaises(SystemExit):
                cig._load_styles()


class ResolveStyleName(unittest.TestCase):
    DOC = {"version": 1, "default": "doodle",
           "styles": {"doodle": "d-snippet", "neon": "n-snippet"}}

    def test_no_style_wins_over_everything(self):
        self.assertIsNone(cig._resolve_style_name(
            self.DOC, style_arg="neon", no_style=True))

    def test_style_arg_overrides_default(self):
        self.assertEqual(cig._resolve_style_name(
            self.DOC, style_arg="neon", no_style=False), "neon")

    def test_falls_back_to_default(self):
        self.assertEqual(cig._resolve_style_name(
            self.DOC, style_arg=None, no_style=False), "doodle")

    def test_empty_default_is_none(self):
        doc = {"default": "", "styles": {"neon": "x"}}
        self.assertIsNone(cig._resolve_style_name(
            doc, style_arg=None, no_style=False))

    def test_unknown_style_arg_raises(self):
        with self.assertRaises(SystemExit):
            cig._resolve_style_name(self.DOC, style_arg="nope", no_style=False)


import io
from contextlib import redirect_stdout

class StyleCommand(unittest.TestCase):
    def test_add_then_show(self):
        with _tmp_xdg():
            self.assertEqual(cig._style_command(["add", "neon", "neon glow"]), 0)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cig._style_command(["show", "neon"]), 0)
            self.assertEqual(out.getvalue().strip(), "neon glow")

    def test_add_invalid_name_raises(self):
        with _tmp_xdg():
            with self.assertRaises(SystemExit):
                cig._style_command(["add", "Bad Name", "x"])

    def test_use_and_clear_default(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            cig._style_command(["use", "neon"])
            self.assertEqual(cig._load_styles()["default"], "neon")
            cig._style_command(["clear"])
            self.assertEqual(cig._load_styles()["default"], "")

    def test_rm_clears_default_if_pointed_there(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            cig._style_command(["use", "neon"])
            cig._style_command(["rm", "neon"])
            doc = cig._load_styles()
            self.assertNotIn("neon", doc["styles"])
            self.assertEqual(doc["default"], "")

    def test_rm_unknown_raises(self):
        with _tmp_xdg():
            with self.assertRaises(SystemExit):
                cig._style_command(["rm", "ghost"])

    def test_list_marks_default(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            cig._style_command(["use", "neon"])
            out = io.StringIO()
            with redirect_stdout(out):
                cig._style_command(["list"])
            lines = out.getvalue()
            self.assertIn("neon", lines)
            self.assertIn("*", lines)   # default marker

    def test_reset_restores_builtins(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            cig._style_command(["rm", "doodle"])
            self.assertEqual(cig._style_command(["reset", "-y"]), 0)
            doc = cig._load_styles()
            self.assertIn("doodle", doc["styles"])
            self.assertNotIn("neon", doc["styles"])


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


class WebUnavailableMessage(unittest.TestCase):
    """The diagnostic built when every browser candidate fails (issue #15)."""

    def test_includes_per_candidate_reasons(self):
        msg = cig._web_unavailable_message(
            detected_profiles=["Default"],
            reasons=["current Chrome (relay) — extension not connected",
                     "profile 'Default' — composer never appeared"],
            relay=False,
        )
        # chrome-use's actual errors are surfaced, not swallowed.
        self.assertIn("extension not connected", msg)
        self.assertIn("composer never appeared", msg)

    def test_logged_in_profile_but_no_relay_gives_three_remedies(self):
        # The issue-#15 shape: a login exists on disk, relay isn't connected.
        msg = cig._web_unavailable_message(["Default"], ["x — y"], relay=False)
        self.assertIn("'Default'", msg)
        self.assertIn("connect the relay", msg)
        self.assertIn("quit Chrome", msg)
        self.assertIn("--backend codex", msg)

    def test_relay_up_blames_signed_out_chrome(self):
        msg = cig._web_unavailable_message([], ["relay — composer never appeared"],
                                           relay=True)
        self.assertIn("relay is connected", msg)
        self.assertNotIn("connect the relay", msg)  # already connected

    def test_nothing_detected_no_relay(self):
        msg = cig._web_unavailable_message([], ["relay — extension not connected"],
                                           relay=False)
        self.assertIn("no logged-in Chrome profile was detected", msg)
        self.assertIn("--backend codex", msg)


class AutoCandidates(unittest.TestCase):
    def test_relay_up_tries_relay_first(self):
        self.assertEqual(cig._auto_candidates(["Default", "Profile 1"], True),
                         [None, "Default", "Profile 1"])

    def test_relay_down_tries_profiles_first_relay_last(self):
        # issue #15 shape: relay off, a login detected → don't waste the first
        # attempt on the signed-out throwaway relay launch.
        self.assertEqual(cig._auto_candidates(["Default"], False),
                         ["Default", None])

    def test_no_profiles_is_just_relay_either_way(self):
        self.assertEqual(cig._auto_candidates([], True), [None])
        self.assertEqual(cig._auto_candidates([], False), [None])


class RelayConnected(unittest.TestCase):
    @contextmanager
    def _fake_run(self, stdout: str, raises: bool = False):
        import subprocess
        real = subprocess.run

        def fake(*a, **k):
            if raises:
                raise subprocess.TimeoutExpired(cmd="chrome-use", timeout=10)
            return subprocess.CompletedProcess(a[0], 0, stdout=stdout, stderr="")

        subprocess.run = fake
        try:
            yield
        finally:
            subprocess.run = real

    def test_relay_true(self):
        with self._fake_run('{"data":{"relay":true,"sessions":[]},"success":true}'):
            self.assertTrue(cig._relay_connected("chrome-use"))

    def test_relay_false(self):
        with self._fake_run('{"data":{"relay":false},"success":true}'):
            self.assertFalse(cig._relay_connected("chrome-use"))

    def test_garbage_output_is_false(self):
        with self._fake_run("not json"):
            self.assertFalse(cig._relay_connected("chrome-use"))

    def test_subprocess_error_is_false(self):
        with self._fake_run("", raises=True):
            self.assertFalse(cig._relay_connected("chrome-use"))


class DoctorDecisions(unittest.TestCase):
    def test_web_ready(self):
        self.assertTrue(cig._web_ready(True, True, 0))    # relay alone
        self.assertTrue(cig._web_ready(True, False, 2))   # profiles alone
        self.assertFalse(cig._web_ready(True, False, 0))  # installed but nothing to reach
        self.assertFalse(cig._web_ready(False, True, 3))  # not installed

    def test_auto_backend_pick(self):
        self.assertEqual(cig._auto_backend_pick(True, False), "web")
        self.assertEqual(cig._auto_backend_pick(True, True), "web")    # web preferred
        self.assertEqual(cig._auto_backend_pick(False, True), "codex")
        self.assertEqual(cig._auto_backend_pick(False, False), "neither")


class Color(unittest.TestCase):
    class _Stream:
        def __init__(self, tty): self._tty = tty
        def isatty(self): return self._tty

    @contextmanager
    def _env(self, **kv):
        prev = {k: os.environ.get(k) for k in kv}
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            yield
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_no_color_env_disables(self):
        with self._env(NO_COLOR="1", TERM="xterm"):
            self.assertFalse(cig._use_color(self._Stream(True)))

    def test_non_tty_disables(self):
        with self._env(NO_COLOR=None, CHATGPT_IMAGEGEN_NO_COLOR=None, TERM="xterm"):
            self.assertFalse(cig._use_color(self._Stream(False)))

    def test_tty_enables(self):
        with self._env(NO_COLOR=None, CHATGPT_IMAGEGEN_NO_COLOR=None, TERM="xterm"):
            self.assertTrue(cig._use_color(self._Stream(True)))

    def test_paint_plain_when_off(self):
        # Color is off for a non-tty stream → string returned untouched.
        with self._env(NO_COLOR=None, CHATGPT_IMAGEGEN_NO_COLOR=None):
            out = cig._paint("31", "hi", stream=self._Stream(False))
            self.assertEqual(out, "hi")

    def test_fmt_progress_plain_has_timestamp_no_ansi(self):
        with self._env(NO_COLOR="1"):
            line = cig._fmt_progress(1.5, "generating")
            self.assertIn("1.5s]", line)
            self.assertNotIn("\033[", line)  # no ANSI when color off

    def test_fmt_progress_color_warns(self):
        # When color is on (forced via patched _use_color), a warn word tints.
        real = cig._use_color
        cig._use_color = lambda *a, **k: True
        try:
            line = cig._fmt_progress(2.0, "warning: relay not connected")
            self.assertIn("\033[33m", line)  # yellow
        finally:
            cig._use_color = real


if __name__ == "__main__":
    unittest.main()
