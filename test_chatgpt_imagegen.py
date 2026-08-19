#!/usr/bin/env python3
"""Unit tests for chatgpt-imagegen's pure helpers — stdlib `unittest`, no deps.

The CLI ships as a single extension-less script, so we load it as a module via
the SourceFileLoader trick. These cover the browser-free logic (MIME sniffing,
version parsing, prompt building, path defaults, token extraction, the capped
ref download) so a refactor that breaks them fails loudly.

Run:  python3 -m unittest test_chatgpt_imagegen -v
"""

import argparse
import importlib.machinery
import importlib.util
import inspect
import io
import sys
import time
import json
import os
import re
import ssl
import tempfile
import unittest
import unittest.mock
from contextlib import contextmanager
from contextlib import redirect_stderr
from contextlib import redirect_stdout
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


class SelfUpdate(unittest.TestCase):
    """`update` / `upgrade` shells out to `skills update` instead of drawing."""

    def test_runs_skills_update(self):
        calls = []

        class _Res:
            returncode = 0

        def fake_run(argv, *a, **k):
            calls.append(argv)
            return _Res()

        with unittest.mock.patch.object(cig.shutil, "which",
                                        return_value="/usr/bin/skills"), \
             unittest.mock.patch.object(cig.subprocess, "run", fake_run), \
             unittest.mock.patch.object(cig, "_fetch_latest_info",
                                        return_value=(None, {})):
            rc = cig._self_update()
        self.assertEqual(rc, 0)
        self.assertEqual(calls,
                         [["/usr/bin/skills", "update", "chatgpt-imagegen"]])

    def test_missing_skills_falls_back_to_npx(self):
        """`skills` is usually only reachable via npx — that must not be a dead end."""
        calls = []

        class _Res:
            returncode = 0

        def fake_which(name):
            return "/usr/bin/npx" if name == "npx" else None

        def fake_run(argv, *a, **k):
            calls.append(argv)
            return _Res()

        with unittest.mock.patch.object(cig.shutil, "which", fake_which), \
             unittest.mock.patch.object(cig.subprocess, "run", fake_run), \
             unittest.mock.patch.object(cig, "_fetch_latest_info",
                                        return_value=(None, {})):
            rc = cig._self_update()
        self.assertEqual(rc, 0)
        self.assertEqual(
            calls,
            [["/usr/bin/npx", "-y", "skills", "update", "chatgpt-imagegen"]])

    def test_path_skills_wins_over_npx(self):
        """A real `skills` on PATH is cheaper than spinning up npx."""
        calls = []

        class _Res:
            returncode = 0

        def fake_run(argv, *a, **k):
            calls.append(argv)
            return _Res()

        with unittest.mock.patch.object(cig.shutil, "which",
                                        lambda name: f"/usr/bin/{name}"), \
             unittest.mock.patch.object(cig.subprocess, "run", fake_run), \
             unittest.mock.patch.object(cig, "_fetch_latest_info",
                                        return_value=(None, {})):
            cig._self_update()
        self.assertEqual(calls,
                         [["/usr/bin/skills", "update", "chatgpt-imagegen"]])

    def test_no_runner_at_all_prints_command_and_fails(self):
        with unittest.mock.patch.object(cig.shutil, "which", return_value=None):
            buf = io.StringIO()
            with redirect_stderr(buf):
                rc = cig._self_update()
        self.assertEqual(rc, 1)
        self.assertIn("npx -y skills update chatgpt-imagegen", buf.getvalue())

    def test_propagates_nonzero_exit(self):
        class _Res:
            returncode = 3

        with unittest.mock.patch.object(cig.shutil, "which",
                                        return_value="/usr/bin/skills"), \
             unittest.mock.patch.object(cig.subprocess, "run",
                                        return_value=_Res()), \
             unittest.mock.patch.object(cig, "_fetch_latest_info",
                                        return_value=(None, {})):
            self.assertEqual(cig._self_update(), 3)


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

    def test_load_starts_empty_when_missing(self):
        # There are no built-in styles: a fresh install has an empty library.
        with _tmp_xdg():
            doc = cig._load_styles()
            self.assertEqual(doc["default"], [])          # v2: default is a list
            self.assertEqual(doc["styles"], {})           # nothing seeded
            self.assertNotIn("seeded", doc)               # machinery gone
            self.assertTrue(cig._styles_path().exists())  # empty doc written

    def test_load_never_injects_styles(self):
        # Loading must never add styles the user didn't put there — the only
        # sources are `style pull` / auto-pull, never the CLI itself.
        with _tmp_xdg():
            cig._save_styles({"version": 2, "default": [],
                              "styles": {"mine": {"kind": "style",
                                                  "snippet": "x", "refs": []}}})
            doc = cig._load_styles()
            self.assertEqual(list(doc["styles"]), ["mine"])  # nothing added

    def test_save_roundtrip_and_atomic(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["custom"] = {"kind": "style", "snippet": "neon glow",
                                       "refs": []}
            doc["default"] = ["custom"]
            cig._save_styles(doc)
            reread = cig._load_styles()
            self.assertEqual(reread["styles"]["custom"]["snippet"], "neon glow")
            self.assertEqual(reread["default"], ["custom"])
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
            text = out.getvalue()
            self.assertIn("kind: style", text)
            self.assertIn("snippet: neon glow", text)
            self.assertIn("path:", text)

    def test_add_invalid_name_raises(self):
        with _tmp_xdg():
            with self.assertRaises(SystemExit):
                cig._style_command(["add", "Bad Name", "x"])

    def test_use_and_clear_default(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            cig._style_command(["use", "neon"])
            self.assertEqual(cig._load_styles()["default"], ["neon"])
            cig._style_command(["clear"])
            self.assertEqual(cig._load_styles()["default"], [])

    def test_rm_clears_default_if_pointed_there(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            cig._style_command(["use", "neon"])
            cig._style_command(["rm", "neon"])
            doc = cig._load_styles()
            self.assertNotIn("neon", doc["styles"])
            self.assertEqual(doc["default"], [])

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

    def test_v2_object_entry_does_not_crash_list_show_compose(self):
        # Regression: a v2 styles.json (entries are {kind,snippet,refs} objects)
        # must not raise "AttributeError: 'dict' object has no attribute 'strip'"
        # on `style list`, `style show`, or the resolve+compose generation path —
        # the crash old (string-only) builds hit against a v2 file.
        with _tmp_xdg():
            cig._save_styles({
                "version": 2, "default": ["xiaohei"],
                "styles": {"xiaohei": {"kind": "style",
                                       "snippet": "hand-drawn 小黑", "refs": []}},
            })
            out = io.StringIO()
            with redirect_stdout(out):
                cig._style_command(["list"])
                cig._style_command(["show", "xiaohei"])
            self.assertIn("xiaohei", out.getvalue())
            doc = cig._load_styles()
            active = cig._resolve_active_styles(doc, style_args=None, no_style=False)
            self.assertEqual(active, ["xiaohei"])
            composed = cig._compose_prompt(
                "a cat", doc["styles"]["xiaohei"]["snippet"])
            self.assertIn("hand-drawn 小黑", composed)

    def test_reset_empties_library(self):
        with _tmp_xdg():
            cig._style_command(["add", "neon", "x"])
            self.assertEqual(cig._style_command(["reset", "-y"]), 0)
            doc = cig._load_styles()
            self.assertEqual(doc["styles"], {})      # wiped, nothing re-seeded
            self.assertEqual(doc["default"], [])


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
        # character-only framing (the old is_edit==True case) → counts API.
        t = cig._build_web_text("make it blue", "auto", n_character_refs=1)
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


class AnimationHelpers(unittest.TestCase):
    def test_prompt_locks_grid_and_subject(self):
        text = cig._build_animation_prompt("a dog wags its tail")
        self.assertIn("exactly 4 columns by 2 rows", text)
        self.assertIn("exactly eight", text)
        self.assertIn("body center", text)
        self.assertIn("a dog wags its tail", text)

    def test_png_dimensions_reads_ihdr(self):
        data = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
                (1774).to_bytes(4, "big") + (887).to_bytes(4, "big"))
        self.assertEqual(cig._png_dimensions(data), (1774, 887))

    def test_png_dimensions_rejects_non_png(self):
        with self.assertRaises(cig.AnimationError):
            cig._png_dimensions(b"not a png")

    def test_ping_pong_order_avoids_duplicate_endpoints(self):
        self.assertEqual(
            cig._animation_frame_order(),
            [0, 1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 3, 2, 1],
        )
        self.assertEqual(cig._animation_frame_order(ping_pong=False), list(range(8)))

    def test_output_extension_is_authoritative(self):
        path, fmt = cig._animation_output_path("wave", "out/wave.gif", None)
        self.assertEqual((path, fmt), (Path("out/wave.gif"), "gif"))
        with self.assertRaises(cig.AnimationError):
            cig._animation_output_path("wave", "wave.gif", "webp")

    def test_component_parser_filters_background_and_specks(self):
        output = """Objects (id: bounding-box centroid area mean-color):
  0: 443x443+0+0 221.0,221.0 170000 gray(255)
  1: 120x120+100+80 160.5,140.5 9000 gray(255)
  2: 2x2+0+0 1.0,1.0 4 gray(255)
"""
        self.assertEqual(
            cig._connected_component_candidates(output, 443 * 443, 443),
            [(160.5, 140.5, 9000)],
        )

    def test_render_crops_eight_cells_and_encodes_webp_plus_gif(self):
        data = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
                (1774).to_bytes(4, "big") + (887).to_bytes(4, "big"))
        commands = []
        with tempfile.TemporaryDirectory() as d, \
             unittest.mock.patch.object(cig.shutil, "which",
                                        side_effect=lambda name: f"/bin/{name}"), \
             unittest.mock.patch.object(cig, "_run_checked",
                                        side_effect=lambda command, label: commands.append((command, label))), \
             unittest.mock.patch.object(cig, "_subject_drift", return_value=(1.0, 0.0)):
            root = Path(d)
            outputs = cig._render_animation(
                root / "sheet.png", data, root / "wave.webp", "webp", 8,
                also_gif=True, keep_frames=False, ping_pong=True,
                max_drift=8.0, allow_drift=False, progress=False,
            )
        self.assertEqual([p.name for p in outputs], ["wave.webp", "wave.gif"])
        self.assertEqual(sum(label.startswith("crop frame") for _, label in commands), 8)
        self.assertEqual(commands[-2][1], "animated WebP encoding")
        self.assertEqual(commands[-1][1], "GIF encoding")

    def test_render_rejects_detected_drift(self):
        data = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
                (1600).to_bytes(4, "big") + (800).to_bytes(4, "big"))
        with tempfile.TemporaryDirectory() as d, \
             unittest.mock.patch.object(cig.shutil, "which", return_value="/bin/tool"), \
             unittest.mock.patch.object(cig, "_run_checked"), \
             unittest.mock.patch.object(cig, "_subject_drift", return_value=(20.0, 3.0)):
            with self.assertRaisesRegex(cig.AnimationError, "subject drift"):
                cig._render_animation(
                    Path(d) / "sheet.png", data, Path(d) / "wave.gif", "gif", 8,
                    also_gif=False, keep_frames=False, ping_pong=True,
                    max_drift=8.0, allow_drift=False, progress=False,
                )


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


def _write_png(path) -> str:
    """Write a tiny but valid-enough PNG (passes _sniff_mime). Returns the path."""
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    return str(path)


def _write_jpeg(path) -> str:
    Path(path).write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
    return str(path)


class NormalizeDoc(unittest.TestCase):
    """Legacy v1 → v2 normalization: bare-string entries become objects, a
    string `default` becomes a list, version bumps to 2."""

    def test_legacy_migration_on_load(self):
        with _tmp_xdg():
            p = cig._styles_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({
                "version": 1,
                "default": "watercolor",
                "styles": {"watercolor": "soft watercolor"},
            }), encoding="utf-8")
            doc = cig._load_styles()
            self.assertEqual(doc["version"], 2)
            self.assertEqual(doc["default"], ["watercolor"])
            entry = doc["styles"]["watercolor"]
            self.assertEqual(entry, {"kind": "style",
                                     "snippet": "soft watercolor", "refs": []})

    def test_empty_string_default_becomes_empty_list(self):
        self.assertEqual(
            cig._normalize_doc({"default": "", "styles": {}})["default"], [])

    def test_rewrite_bumps_version_on_disk(self):
        with _tmp_xdg():
            p = cig._styles_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({
                "version": 1, "default": "x",
                "styles": {"x": "snip"},
            }), encoding="utf-8")
            cig._style_command(["use", "x"])           # any mutating command
            on_disk = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["version"], 2)
            self.assertEqual(on_disk["default"], ["x"])
            self.assertEqual(on_disk["styles"]["x"]["snippet"], "snip")


class AssetAddRef(unittest.TestCase):
    """add --ref copies the file in, normalizes the filename, and show lists it."""

    def test_add_ref_copies_and_normalizes_name(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as src:
            img = _write_png(os.path.join(src, "Weird Name.PNG"))
            self.assertEqual(
                cig._style_command(["add", "mascot", "a fox", "--ref", img,
                                    "--kind", "character"]), 0)
            doc = cig._load_styles()
            entry = doc["styles"]["mascot"]
            self.assertEqual(entry["kind"], "character")
            self.assertEqual(entry["refs"], ["ref-1.png"])     # normalized
            self.assertTrue((cig._asset_dir("mascot") / "ref-1.png").is_file())

    def test_add_requires_snippet_or_ref(self):
        with _tmp_xdg():
            with self.assertRaises(SystemExit):
                cig._style_command(["add", "empty"])

    def test_add_ref_then_rm_ref(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as src:
            a = _write_png(os.path.join(src, "a.png"))
            b = _write_jpeg(os.path.join(src, "b.jpg"))
            cig._style_command(["add", "mascot", "--ref", a, "--kind", "character"])
            cig._style_command(["add-ref", "mascot", b])
            entry = cig._load_styles()["styles"]["mascot"]
            self.assertEqual(entry["refs"], ["ref-1.png", "ref-2.jpg"])
            self.assertTrue((cig._asset_dir("mascot") / "ref-2.jpg").is_file())
            cig._style_command(["rm-ref", "mascot", "ref-1.png"])
            entry = cig._load_styles()["styles"]["mascot"]
            self.assertEqual(entry["refs"], ["ref-2.jpg"])
            self.assertFalse((cig._asset_dir("mascot") / "ref-1.png").exists())

    def test_rm_ref_unknown_file_raises(self):
        with _tmp_xdg():
            cig._style_command(["add", "mascot", "snip"])
            with self.assertRaises(SystemExit):
                cig._style_command(["rm-ref", "mascot", "nope.png"])


class ResolveActiveStyles(unittest.TestCase):
    def _doc(self):
        return cig._normalize_doc({
            "default": ["a", "b"],
            "styles": {"a": {"kind": "character", "snippet": "", "refs": []},
                       "b": "snip-b", "c": "snip-c"},
        })

    def test_falls_back_to_default_list(self):
        self.assertEqual(
            cig._resolve_active_styles(self._doc(), style_args=None,
                                       no_style=False), ["a", "b"])

    def test_explicit_styles_override_default_in_order(self):
        self.assertEqual(
            cig._resolve_active_styles(self._doc(), style_args=["c", "a"],
                                       no_style=False), ["c", "a"])

    def test_no_style_empties(self):
        self.assertEqual(
            cig._resolve_active_styles(self._doc(), style_args=["a"],
                                       no_style=True), [])

    def test_unknown_raises(self):
        with self.assertRaises(SystemExit):
            cig._resolve_active_styles(self._doc(), style_args=["ghost"],
                                       no_style=False)


class CollectRefsOrdering(unittest.TestCase):
    """Partition + ordering: character group first (assets then ad-hoc), then
    the style group."""

    def test_partition_and_order(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as src:
            ch = _write_png(os.path.join(src, "ch.png"))
            st = _write_png(os.path.join(src, "st.png"))
            cig._style_command(["add", "ch", "--ref", ch, "--kind", "character"])
            cig._style_command(["add", "st", "--ref", st, "--kind", "style"])
            doc = cig._load_styles()
            # active order deliberately style-first to prove repartition.
            ordered = cig._collect_refs(doc, ["st", "ch"], ["/adhoc.png"])
            groups = [r["group"] for r in ordered]
            self.assertEqual(groups, ["character", "character", "style"])
            ch_path = str(cig._asset_dir("ch") / "ref-1.png")
            st_path = str(cig._asset_dir("st") / "ref-1.png")
            self.assertEqual([r["ref"] for r in ordered],
                             [ch_path, "/adhoc.png", st_path])

    def test_missing_ref_file_raises_naming_asset_and_path(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as src:
            img = _write_png(os.path.join(src, "x.png"))
            cig._style_command(["add", "ch", "--ref", img, "--kind", "character"])
            # delete the copied byte on disk → load still lists the ref name
            (cig._asset_dir("ch") / "ref-1.png").unlink()
            doc = cig._load_styles()
            with self.assertRaises(SystemExit) as ctx:
                cig._collect_refs(doc, ["ch"], None)
            msg = str(ctx.exception)
            self.assertIn("ch", msg)
            self.assertIn("ref-1.png", msg)


class RefCap(unittest.TestCase):
    def test_caps_and_reports_dropped(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as src:
            refs = [_write_png(os.path.join(src, f"r{i}.png")) for i in range(6)]
            cmd = ["add", "many", "--kind", "character"]
            for r in refs:
                cmd += ["--ref", r]
            cig._style_command(cmd)
            doc = cig._load_styles()
            ordered = cig._collect_refs(doc, ["many"], None)
            self.assertEqual(len(ordered), 6)
            kept, dropped = cig._cap_refs(ordered, cig.REF_ATTACH_CAP)
            self.assertEqual(len(kept), cig.REF_ATTACH_CAP)
            self.assertEqual(len(dropped), 6 - cig.REF_ATTACH_CAP)
            # the dropped ones are the trailing refs, identifiable by label
            self.assertTrue(all("many/ref-" in r["label"] for r in dropped))


class ResetWipesAssets(unittest.TestCase):
    def test_reset_deletes_asset_tree(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as src:
            img = _write_png(os.path.join(src, "x.png"))
            cig._style_command(["add", "mascot", "--ref", img, "--kind", "character"])
            self.assertTrue(cig._asset_dir("mascot").is_dir())
            self.assertEqual(cig._style_command(["reset", "-y"]), 0)
            self.assertFalse(cig._asset_dir("mascot").exists())
            self.assertFalse(cig._assets_root().exists())
            doc = cig._load_styles()
            self.assertEqual(doc["styles"], {})        # empty library after reset


class FromLast(unittest.TestCase):
    def test_record_then_read_roundtrip(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as d:
            img = Path(_write_png(os.path.join(d, "out.png")))
            cig._record_last_output(img)
            self.assertEqual(cig._read_last_output(), img.resolve())

    def test_pin_from_last(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as d:
            img = Path(_write_png(os.path.join(d, "out.png")))
            cig._record_last_output(img)
            self.assertEqual(
                cig._style_command(["add", "pinned", "--from-last",
                                    "--kind", "character"]), 0)
            entry = cig._load_styles()["styles"]["pinned"]
            self.assertEqual(entry["refs"], ["ref-1.png"])
            self.assertTrue((cig._asset_dir("pinned") / "ref-1.png").is_file())

    def test_from_last_absent_errors(self):
        with _tmp_xdg():
            with self.assertRaises(SystemExit):
                cig._style_command(["add", "x", "--from-last"])

    def test_from_last_file_gone_errors(self):
        with _tmp_xdg(), tempfile.TemporaryDirectory() as d:
            img = Path(_write_png(os.path.join(d, "out.png")))
            cig._record_last_output(img)
            img.unlink()
            with self.assertRaises(SystemExit):
                cig._style_command(["add", "x", "--from-last"])


class PromptWordingByKind(unittest.TestCase):
    """The three instruction framings keyed off (n_character_refs, n_style_refs)."""

    def test_style_only(self):
        t = cig._build_web_text("a cat", "auto", n_character_refs=0, n_style_refs=2)
        self.assertIn("Match the visual style", t)
        self.assertIn("do NOT copy", t)
        self.assertNotIn("recurring character", t)
        u = cig._build_user_text("a cat", "auto", "png",
                                 n_character_refs=0, n_style_refs=2)
        self.assertIn("visual style", u)
        self.assertIn("do not copy their content", u)
        self.assertNotIn("recurring character", u)

    def test_character_only(self):
        t = cig._build_web_text("a cat", "auto", n_character_refs=1, n_style_refs=0)
        self.assertIn("canonical subject", t)
        self.assertNotIn("recurring character", t)
        u = cig._build_user_text("a cat", "auto", "png",
                                 n_character_refs=1, n_style_refs=0)
        self.assertIn("canonical subject", u)

    def test_mixed(self):
        t = cig._build_web_text("a cat", "auto", n_character_refs=1, n_style_refs=2)
        self.assertIn("recurring character", t)
        self.assertIn("style references", t)
        u = cig._build_user_text("a cat", "auto", "png",
                                 n_character_refs=1, n_style_refs=2)
        self.assertIn("recurring character", u)
        self.assertIn("style references", u)

    def test_payload_tool_choice_required_for_style_only(self):
        payload = cig._build_payload(
            "a cat", "auto", "png", "gpt-5.5",
            refs=[("Zm9v", "image/png")], n_character_refs=0, n_style_refs=1)
        self.assertEqual(payload["tool_choice"], "required")


class StylesAlias(unittest.TestCase):
    def test_use_accepts_multiple(self):
        with _tmp_xdg():
            cig._style_command(["add", "a", "x"])
            cig._style_command(["add", "b", "y"])
            cig._style_command(["use", "a", "b"])
            self.assertEqual(cig._load_styles()["default"], ["a", "b"])


class OriginRoundTrip(unittest.TestCase):
    def test_origin_preserved(self):
        e = cig._normalize_entry({
            "kind": "style", "snippet": "s", "refs": ["a.png"],
            "origin": {"platform": "drawstyle", "slug": "pip", "version": 3}})
        self.assertEqual(e["origin"],
                         {"platform": "drawstyle", "slug": "pip", "version": 3})

    def test_platform_defaults_when_missing(self):
        e = cig._normalize_entry({
            "kind": "style", "snippet": "s", "refs": [],
            "origin": {"slug": "pip", "version": 1}})
        self.assertEqual(e["origin"]["platform"], "drawstyle")

    def test_bad_origin_dropped(self):
        for bad in ("str", 7, ["x"], {"platform": "drawstyle"},  # missing slug/version
                    {"slug": "x", "version": True}):  # bool is not a version
            e = cig._normalize_entry({"kind": "style", "snippet": "s",
                                      "refs": [], "origin": bad})
            self.assertNotIn("origin", e)

    def test_absent_origin_absent(self):
        e = cig._normalize_entry({"kind": "style", "snippet": "s", "refs": []})
        self.assertNotIn("origin", e)


class PlatformRequest(unittest.TestCase):
    def test_base_default_and_env(self):
        prev = os.environ.pop("DRAWSTYLE_API", None)
        try:
            self.assertEqual(cig._platform_base(),
                             "https://drawstyle.leeguoo.com")
            os.environ["DRAWSTYLE_API"] = "http://localhost:8787/"
            self.assertEqual(cig._platform_base(), "http://localhost:8787")
        finally:
            if prev is None:
                os.environ.pop("DRAWSTYLE_API", None)
            else:
                os.environ["DRAWSTYLE_API"] = prev

    def test_error_payload_surfaced(self):
        import urllib.error
        body = json.dumps({"error": {"code": "not_found",
                                     "message": "no such style"}}).encode()
        err = urllib.error.HTTPError("u", 404, "Not Found", {},
                                     io.BytesIO(body))
        with unittest.mock.patch.object(cig, "_urlopen", side_effect=err):
            with self.assertRaises(SystemExit) as cm:
                cig._platform_request("GET", "/api/styles/nope")
            self.assertIn("no such style", str(cm.exception))

    def test_offline_hint(self):
        import urllib.error
        with unittest.mock.patch.object(
                cig, "_urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(SystemExit) as cm:
                cig._platform_request("GET", "/api/styles")
            self.assertIn("unaffected", str(cm.exception))
            self.assertIn("retry when online", str(cm.exception))

    @staticmethod
    def _fake_urlopen(body: bytes):
        resp = unittest.mock.MagicMock()
        resp.read.return_value = body
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return unittest.mock.Mock(return_value=resp)

    def test_happy_path_json(self):
        fake = self._fake_urlopen(b'{"ok": true}')
        with unittest.mock.patch.object(cig, "_urlopen", fake):
            self.assertEqual(cig._platform_request("GET", "/api/styles"),
                             {"ok": True})

    def test_reference_download_sends_user_agent(self):
        fake = self._fake_urlopen(_PNG)
        with unittest.mock.patch.object(cig, "_urlopen", fake):
            self.assertEqual(cig._download_bytes("https://example.test/ref.png"),
                             _PNG)
        req = fake.call_args[0][0]
        self.assertIn("chatgpt-imagegen/", req.get_header("User-agent"))

    def test_non_json_200_exits(self):
        fake = self._fake_urlopen(b"<html>")
        with unittest.mock.patch.object(cig, "_urlopen", fake):
            with self.assertRaises(SystemExit) as cm:
                cig._platform_request("GET", "/api/styles")
            self.assertIn("not JSON", str(cm.exception))


_SEARCH_PAYLOAD = {"styles": [
    {"slug": "pip", "name": "Pip the fox", "kind": "character",
     "category": "avatar-ip", "likes_count": 12, "pulls_count": 90,
     "snippet": "a round orange fox named Pip, thick outlines"},
]}


class StyleSearch(unittest.TestCase):
    def test_renders_rows_and_pull_hint(self):
        with unittest.mock.patch.object(
                cig, "_platform_request", return_value=_SEARCH_PAYLOAD) as m:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cig._style_command(["search", "fox", "--category",
                                         "avatar-ip", "--tag", "cute"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("pip", out)
        self.assertIn("character", out)
        self.assertIn("style pull pip", out)
        path = m.call_args[0][1]
        self.assertIn("q=fox", path)
        self.assertIn("category=avatar-ip", path)
        self.assertIn("tag=cute", path)

    def test_empty_result(self):
        with unittest.mock.patch.object(
                cig, "_platform_request", return_value={"styles": []}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cig._style_command(["search", "nothing"])
        self.assertEqual(rc, 0)
        self.assertIn("no styles found", buf.getvalue())


_PKG = {"slug": "pip", "name": "Pip the fox", "kind": "character",
        "snippet": "a round orange fox", "version": 3,
        "refs": [{"url": "https://drawstyle.leeguoo.com/img/abc",
                  "content_type": "image/png"}]}
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class ResolveOnlineStyles(unittest.TestCase):
    def test_fetches_snippet_and_refs_without_persisting(self):
        with _tmp_xdg():
            with unittest.mock.patch.object(cig, "_platform_request",
                                            return_value=_PKG), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=_PNG):
                snippets, refs = cig._resolve_online_styles(["pip"])
            # snippet folded, one ref downloaded to a temp path, grouped by kind
            self.assertEqual(snippets, ["a round orange fox"])
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["group"], "character")  # _PKG kind=character
            self.assertTrue(Path(refs[0]["ref"]).is_file())
            self.assertIn("online:pip", refs[0]["label"])
            # provenance: the gallery source URL rides along for the run log
            self.assertEqual(refs[0]["source"],
                             "https://drawstyle.leeguoo.com/img/abc")
            # nothing was written to the local style library
            doc = cig._load_styles()
            self.assertNotIn("pip", doc["styles"])

    def test_invalid_slug_and_malformed_package_exit(self):
        with self.assertRaises(SystemExit):
            cig._resolve_online_styles(["../../etc"])
        with unittest.mock.patch.object(cig, "_platform_request",
                                        return_value={"no": "kind"}):
            with self.assertRaises(SystemExit):
                cig._resolve_online_styles(["pip"])


class RefProvenance(unittest.TestCase):
    """Issue #18: the run log must name each attached ref's source, not a count."""

    def test_online_ref_shows_source_url_and_sha(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ref-1.jpg"
            f.write_bytes(b"hello-bytes")
            lines = cig._format_ref_provenance([{
                "ref": str(f), "group": "style",
                "label": "online:snoopy/ref-1.jpg",
                "source": "https://drawstyle.leeguoo.com/img/deadbeef.jpg"}])
        self.assertEqual(len(lines), 1)
        self.assertIn("[style]", lines[0])
        self.assertIn("online:snoopy/ref-1.jpg", lines[0])
        self.assertIn("source=https://drawstyle.leeguoo.com/img/deadbeef.jpg", lines[0])
        # sha256 of b"hello-bytes", first 16 hex
        import hashlib as _h
        self.assertIn(_h.sha256(b"hello-bytes").hexdigest()[:16], lines[0])

    def test_local_ref_shows_path_not_source(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ref-1.png"
            f.write_bytes(b"x")
            lines = cig._format_ref_provenance([{
                "ref": str(f), "group": "character", "label": "leo/ref-1.png"}])
        self.assertIn(f"path={f}", lines[0])
        self.assertNotIn("source=", lines[0])

    def test_unreadable_ref_degrades_gracefully(self):
        lines = cig._format_ref_provenance([{
            "ref": "/no/such/file.png", "group": "style", "label": "x"}])
        self.assertIn("sha256=?", lines[0])


class StylePull(unittest.TestCase):
    def _pull(self, argv, pkg=None, blobs=None):
        def fake_request(method, path, **kw):
            return pkg or _PKG

        def fake_download(url):
            if blobs is not None and url in blobs:
                raise OSError("boom")
            return _PNG

        with unittest.mock.patch.object(cig, "_platform_request", fake_request), \
             unittest.mock.patch.object(cig, "_download_bytes", fake_download):
            return cig._style_command(argv)

    def test_happy_path_writes_entry_refs_and_origin(self):
        with _tmp_xdg():
            rc = self._pull(["pull", "pip"])
            self.assertEqual(rc, 0)
            doc = cig._load_styles()
            e = doc["styles"]["pip"]
            self.assertEqual(e["kind"], "character")
            self.assertEqual(e["origin"],
                             {"platform": "drawstyle", "slug": "pip", "version": 3})
            self.assertEqual(len(e["refs"]), 1)
            self.assertTrue((cig._asset_dir("pip") / e["refs"][0]).exists())

    def test_collision_aborts_with_as_hint(self):
        with _tmp_xdg():
            self._pull(["pull", "pip"])
            with self.assertRaises(SystemExit) as cm:
                self._pull(["pull", "pip"])
            self.assertIn("--as", str(cm.exception))

    def test_as_renames_locally_keeps_origin_slug(self):
        with _tmp_xdg():
            self._pull(["pull", "pip", "--as", "fox2"])
            doc = cig._load_styles()
            self.assertIn("fox2", doc["styles"])
            self.assertEqual(doc["styles"]["fox2"]["origin"]["slug"], "pip")

    def test_failed_ref_download_leaves_no_entry(self):
        with _tmp_xdg():
            with self.assertRaises(SystemExit):
                self._pull(["pull", "pip"],
                           blobs={"https://drawstyle.leeguoo.com/img/abc"})
            doc = cig._load_styles()
            self.assertNotIn("pip", doc["styles"])
            self.assertFalse(cig._asset_dir("pip").exists())

    def test_non_image_payload_refused(self):
        with _tmp_xdg():
            with unittest.mock.patch.object(cig, "_platform_request",
                                            return_value=_PKG), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=b"<html>nope</html>"):
                with self.assertRaises(SystemExit) as cm:
                    cig._style_command(["pull", "pip"])
            self.assertIn("not an image", str(cm.exception))

    def test_invalid_slug_exits_without_request(self):
        with _tmp_xdg():
            called = []

            def fake_request(method, path, **kw):
                called.append(path)
                return _PKG

            with unittest.mock.patch.object(cig, "_platform_request",
                                            fake_request):
                with self.assertRaises(SystemExit) as cm:
                    cig._style_command(["pull", "../../etc"])
            self.assertIn("invalid slug", str(cm.exception))
            self.assertEqual(called, [])


class EnsureStylesLocal(unittest.TestCase):
    """`--style NAME` auto-pulls a missing name from the gallery and persists it."""

    def test_local_name_no_network(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["mine"] = {"kind": "style", "snippet": "x", "refs": []}
            def boom(*a, **k):  # any network call would fail the test
                raise AssertionError("should not hit the platform")
            with unittest.mock.patch.object(cig, "_platform_request", boom):
                self.assertFalse(cig._ensure_styles_local(doc, ["mine"]))

    def test_missing_name_is_pulled_and_persisted(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            with unittest.mock.patch.object(cig, "_platform_request",
                                            return_value=_PKG), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=_PNG):
                changed = cig._ensure_styles_local(doc, ["pip"])
            self.assertTrue(changed)
            self.assertIn("pip", doc["styles"])                 # in the live doc
            self.assertEqual(doc["styles"]["pip"]["origin"]["slug"], "pip")
            reread = cig._load_styles()                         # and on disk
            self.assertIn("pip", reread["styles"])

    def test_not_on_gallery_dies_with_guidance(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            def not_found(*a, **k):
                raise SystemExit("error: platform: not found")
            with unittest.mock.patch.object(cig, "_platform_request", not_found):
                with self.assertRaises(SystemExit) as cm:
                    cig._ensure_styles_local(doc, ["ghost"])
            msg = str(cm.exception)
            self.assertIn("unknown style", msg)
            self.assertIn("style search ghost", msg)            # points at gallery
            self.assertNotIn("ghost", doc["styles"])            # nothing persisted

    def test_invalid_name_dies_without_network(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            def boom(*a, **k):
                raise AssertionError("should not hit the platform")
            with unittest.mock.patch.object(cig, "_platform_request", boom):
                with self.assertRaises(SystemExit):
                    cig._ensure_styles_local(doc, ["Bad Name"])


_SNOOPY_PKG = {"slug": "snoopy", "name": "Snoopy Comic", "kind": "style",
               "snippet": "peanuts newspaper look", "version": 1,
               "refs": [{"url": "https://drawstyle.leeguoo.com/img/s",
                         "content_type": "image/jpeg"}]}


class StaleLegacyBuiltin(unittest.TestCase):
    """0.16-era text-only doodle/xiaohei/snoopy self-heal to the gallery version."""

    def test_predicate(self):
        stale = {"kind": "style", "snippet": "x", "refs": []}
        self.assertTrue(cig._is_stale_legacy_builtin("snoopy", stale))
        self.assertTrue(cig._is_stale_legacy_builtin("doodle", stale))
        # has pinned refs → user-customized, leave it
        self.assertFalse(cig._is_stale_legacy_builtin(
            "xiaohei", {"snippet": "x", "refs": ["ref-1.jpg"]}))
        # already pulled (has origin) → not stale
        self.assertFalse(cig._is_stale_legacy_builtin(
            "snoopy", {"snippet": "x", "refs": [],
                       "origin": {"platform": "drawstyle", "slug": "snoopy",
                                  "version": 1}}))
        # not a legacy name → never touched
        self.assertFalse(cig._is_stale_legacy_builtin("mine", stale))

    def test_upgraded_in_place_to_gallery_version(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["snoopy"] = {"kind": "style",
                                       "snippet": "old text-only", "refs": []}
            with unittest.mock.patch.object(cig, "_platform_request",
                                            return_value=_SNOOPY_PKG), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=_PNG):
                changed = cig._ensure_styles_local(doc, ["snoopy"])
            self.assertTrue(changed)
            e = doc["styles"]["snoopy"]
            self.assertEqual(e["origin"]["slug"], "snoopy")   # now gallery-backed
            self.assertEqual(len(e["refs"]), 1)               # now has a ref image

    def test_offline_keeps_old_copy(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            old = {"kind": "style", "snippet": "old", "refs": []}
            doc["styles"]["snoopy"] = dict(old)
            def offline(*a, **k):
                raise SystemExit("error: cannot reach gallery")
            with unittest.mock.patch.object(cig, "_platform_request", offline):
                changed = cig._ensure_styles_local(doc, ["snoopy"])
            self.assertFalse(changed)
            self.assertEqual(doc["styles"]["snoopy"], old)    # untouched, no crash

    def test_customized_legacy_name_not_touched(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["xiaohei"] = {"kind": "style", "snippet": "mine",
                                        "refs": ["ref-1.jpg"]}
            def boom(*a, **k):
                raise AssertionError("should not hit the platform")
            with unittest.mock.patch.object(cig, "_platform_request", boom):
                self.assertFalse(cig._ensure_styles_local(doc, ["xiaohei"]))

    def test_pull_replaces_stale_legacy_instead_of_colliding(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["snoopy"] = {"kind": "style",
                                       "snippet": "old text-only", "refs": []}
            cig._save_styles(doc)
            with unittest.mock.patch.object(cig, "_platform_request",
                                            return_value=_SNOOPY_PKG), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=_PNG):
                rc = cig._style_command(["pull", "snoopy"])
            self.assertEqual(rc, 0)
            e = cig._load_styles()["styles"]["snoopy"]
            self.assertEqual(e["origin"]["slug"], "snoopy")
            self.assertEqual(len(e["refs"]), 1)


class StyleUpdate(unittest.TestCase):
    def test_version_check_uses_detail_not_package(self):
        calls = []

        def fake_request(method, path, **kw):
            calls.append(path)
            if path.endswith("/package"):
                return dict(_PKG, version=4)
            return {"slug": "pip", "version": 4}

        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["pip"] = {
                "kind": "character", "snippet": "old", "refs": [],
                "origin": {"platform": "drawstyle", "slug": "pip", "version": 3}}
            cig._save_styles(doc)
            with unittest.mock.patch.object(cig, "_platform_request", fake_request), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=_PNG):
                rc = cig._style_command(["update", "pip"])
            updated_version = (
                cig._load_styles()["styles"]["pip"]["origin"]["version"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0], "/api/styles/pip")
        self.assertIn("/api/styles/pip/package", calls[1])
        self.assertEqual(updated_version, 4)

    def test_up_to_date_skips_package(self):
        calls = []

        def fake_request(method, path, **kw):
            calls.append(path)
            if path.endswith("/package"):
                return _PKG
            return {"slug": "pip", "version": 3}

        with _tmp_xdg():
            with unittest.mock.patch.object(cig, "_platform_request", fake_request), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            return_value=_PNG):
                cig._style_command(["pull", "pip"])
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cig._style_command(["update"])
        self.assertEqual(rc, 0)
        self.assertIn("up to date", buf.getvalue())
        self.assertEqual([p for p in calls if p.endswith("/package")],
                         ["/api/styles/pip/package"])

    def test_entry_without_origin_skipped(self):
        with _tmp_xdg():
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cig._style_command(["update"])
        self.assertEqual(rc, 0)
        self.assertIn("no pulled styles", buf.getvalue())

    def test_named_entry_without_origin_errors(self):
        with _tmp_xdg():
            cig._style_command(["add", "local", "local only"])
            with self.assertRaises(SystemExit) as cm:
                cig._style_command(["update", "local"])
        self.assertIn("has no platform origin", str(cm.exception))


class OidcPkce(unittest.TestCase):
    def test_challenge_is_s256_of_verifier(self):
        import base64
        import hashlib
        verifier, challenge = cig._pkce_pair()
        want = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(challenge, want)
        self.assertGreaterEqual(len(verifier), 43)

    def test_token_cache_roundtrip_and_mode(self):
        with _tmp_xdg():
            cig._save_platform_auth({"access_token": "at", "refresh_token": "rt",
                                     "expires_at": 9999999999})
            p = cig._platform_auth_path()
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(cig._load_platform_auth()["access_token"], "at")

    def test_expired_token_triggers_refresh(self):
        with _tmp_xdg():
            cig._save_platform_auth({"access_token": "old", "refresh_token": "rt",
                                     "expires_at": 1})
            with unittest.mock.patch.object(
                    cig, "_oidc_token_request",
                    return_value={"access_token": "new", "refresh_token": "rt2",
                                  "expires_in": 3600}) as m:
                token = cig._platform_access_token(interactive=False)
        self.assertEqual(token, "new")
        self.assertEqual(m.call_args[0][0]["grant_type"], "refresh_token")

    def test_login_errors_when_fixed_callback_port_unavailable(self):
        with unittest.mock.patch.object(cig.http.server, "HTTPServer",
                                        side_effect=OSError("in use")):
            with self.assertRaises(SystemExit) as cm:
                cig._oidc_login_interactive()
        self.assertIn("127.0.0.1:45898", str(cm.exception))


class StylePublish(unittest.TestCase):
    def _setup_local(self):
        cig._style_command(["add", "mylook", "soft watercolor"])

    def test_category_required(self):
        with _tmp_xdg():
            self._setup_local()
            with self.assertRaises(SystemExit) as cm:
                cig._style_command(["publish", "mylook", "--example", "x.png"])
            self.assertIn("--category", str(cm.exception))
            self.assertIn("report", str(cm.exception))

    def test_example_required(self):
        with _tmp_xdg():
            self._setup_local()
            with self.assertRaises(SystemExit) as cm:
                cig._style_command(["publish", "mylook", "--category", "cute"])
            self.assertIn("--example", str(cm.exception))

    def test_no_example_hint_suggests_from_last(self):
        # the friendly error should show the one-liner using --from-last
        with _tmp_xdg():
            self._setup_local()
            with self.assertRaises(SystemExit) as cm:
                cig._style_command(["publish", "mylook", "--category", "cute"])
            self.assertIn("--from-last", str(cm.exception))

    def test_prints_preupload_summary(self):
        import io as _io
        from contextlib import redirect_stderr
        with _tmp_xdg() as root:
            self._setup_local()
            ex = Path(root) / "ex.png"
            ex.write_bytes(_PNG)
            buf = _io.StringIO()
            with unittest.mock.patch.object(cig, "_platform_access_token",
                                            return_value="tok"), \
                 unittest.mock.patch.object(
                     cig, "_platform_request",
                     return_value={"slug": "mylook", "status": "pending"}), \
                 redirect_stderr(buf):
                cig._style_command(["publish", "mylook", "--category", "cute",
                                    "--tag", "watercolor", "--example", str(ex)])
            out = buf.getvalue()
            self.assertIn("publishing 'mylook'", out)
            self.assertIn("category: cute", out)
            self.assertIn("examples: 1", out)
            self.assertIn("track approval", out)

    def test_republish_own_origin_errors(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            doc["styles"]["mine"] = {"kind": "style", "snippet": "s", "refs": [],
                                     "origin": {"platform": "drawstyle",
                                                "slug": "mine", "version": 1}}
            cig._save_styles(doc)
            with self.assertRaises(SystemExit) as cm:
                cig._style_command(["publish", "mine", "--category", "cute",
                                    "--example", "x.png"])
            self.assertIn("edit", str(cm.exception))

    def test_happy_path_posts_multipart(self):
        with _tmp_xdg() as root:
            self._setup_local()
            ex = Path(root) / "ex.png"
            ex.write_bytes(_PNG)
            with unittest.mock.patch.object(cig, "_platform_access_token",
                                            return_value="tok"), \
                 unittest.mock.patch.object(
                     cig, "_platform_request",
                     return_value={"slug": "mylook", "status": "pending"}) as m:
                rc = cig._style_command(["publish", "mylook", "--category",
                                         "cute", "--example", str(ex)])
        self.assertEqual(rc, 0)
        method, path = m.call_args[0][0], m.call_args[0][1]
        self.assertEqual((method, path), ("POST", "/api/styles"))
        hdrs = m.call_args[1]["headers"]
        self.assertEqual(hdrs["Authorization"], "Bearer tok")
        self.assertIn("multipart/form-data", hdrs["Content-Type"])
        body = m.call_args[1]["data"]
        self.assertIn(b'name="category"', body)
        self.assertIn(b"cute", body)
        self.assertIn(_PNG, body)

    def test_publish_records_origin_and_blocks_second_publish(self):
        with _tmp_xdg() as root:
            self._setup_local()
            ex = Path(root) / "ex.png"
            ex.write_bytes(_PNG)
            with unittest.mock.patch.object(cig, "_platform_access_token",
                                            return_value="tok"), \
                 unittest.mock.patch.object(
                     cig, "_platform_request",
                     return_value={"slug": "mylook", "status": "pending"}):
                rc = cig._style_command(["publish", "mylook", "--category",
                                         "cute", "--example", str(ex)])
            self.assertEqual(rc, 0)
            entry = cig._load_styles()["styles"]["mylook"]
            self.assertEqual(
                entry["origin"],
                {"platform": "drawstyle", "slug": "mylook", "version": 1})
            # a second publish now hits the friendly already-published guard
            with self.assertRaises(SystemExit) as cm:
                cig._style_command(["publish", "mylook", "--category", "cute",
                                    "--example", str(ex)])
            self.assertIn("edit", str(cm.exception))

    def test_too_many_examples_errors_before_auth(self):
        with _tmp_xdg() as root:
            self._setup_local()
            paths = []
            for n in range(4):
                p = Path(root) / f"ex{n}.png"
                p.write_bytes(_PNG)
                paths.extend(["--example", str(p)])
            with unittest.mock.patch.object(cig, "_platform_access_token") as auth:
                with self.assertRaises(SystemExit) as cm:
                    cig._style_command(["publish", "mylook", "--category",
                                        "cute", *paths])
        self.assertIn("at most 3", str(cm.exception))
        auth.assert_not_called()

    def test_pinned_refs_are_uploaded_as_ref_parts(self):
        with _tmp_xdg() as root:
            self._setup_local()
            ref = Path(root) / "ref.png"
            ref.write_bytes(_PNG)
            ex = Path(root) / "ex.png"
            ex.write_bytes(_PNG)
            cig._style_command(["add-ref", "mylook", str(ref)])
            with unittest.mock.patch.object(cig, "_platform_access_token",
                                            return_value="tok"), \
                 unittest.mock.patch.object(
                     cig, "_platform_request",
                     return_value={"slug": "mylook", "status": "pending"}) as m:
                rc = cig._style_command(["publish", "mylook", "--category",
                                         "cute", "--example", str(ex)])
        self.assertEqual(rc, 0)
        body = m.call_args[1]["data"]
        self.assertIn(b'name="example[]"', body)
        self.assertIn(b'name="ref[]"', body)


class PlatformAccessTokenRefreshFallback(unittest.TestCase):
    def _expired(self):
        cig._save_platform_auth({"access_token": "old", "refresh_token": "rt",
                                 "expires_at": 1})

    @staticmethod
    def _boom(form):
        raise SystemExit("error: drawstyle login token exchange failed (HTTP 400)")

    def test_interactive_falls_back_to_login_when_refresh_fails(self):
        with _tmp_xdg():
            self._expired()
            with unittest.mock.patch.object(cig, "_oidc_token_request",
                                            self._boom), \
                 unittest.mock.patch.object(
                     cig, "_oidc_login_interactive",
                     return_value={"access_token": "fresh"}) as login:
                token = cig._platform_access_token(interactive=True)
            self.assertEqual(token, "fresh")
            login.assert_called_once()

    def test_non_interactive_still_fails_fast_on_refresh_failure(self):
        with _tmp_xdg():
            self._expired()
            with unittest.mock.patch.object(cig, "_oidc_token_request",
                                            self._boom), \
                 unittest.mock.patch.object(
                     cig, "_oidc_login_interactive") as login:
                with self.assertRaises(SystemExit):
                    cig._platform_access_token(interactive=False)
            login.assert_not_called()


class OidcCallbackMatch(unittest.TestCase):
    def test_matching_cb_with_state_and_code(self):
        ok, code = cig._oidc_callback_match("/cb?state=S&code=XYZ", "S")
        self.assertTrue(ok)
        self.assertEqual(code, "XYZ")

    def test_non_cb_path_ignored(self):
        # a stray favicon/prefetch must not consume the handshake
        self.assertEqual(
            cig._oidc_callback_match("/favicon.ico?state=S&code=XYZ", "S"),
            (False, ""))

    def test_state_mismatch_ignored(self):
        self.assertEqual(
            cig._oidc_callback_match("/cb?state=other&code=XYZ", "S"),
            (False, ""))

    def test_missing_code_ignored(self):
        self.assertEqual(cig._oidc_callback_match("/cb?state=S", "S"),
                         (False, ""))


class StyleUpdatePartial(unittest.TestCase):
    def test_mid_list_failure_saves_earlier_entry(self):
        def fake_request(method, path, **kw):
            if path.endswith("/package"):
                slug = path.split("/")[3]
                return dict(_PKG, slug=slug, version=4,
                            refs=[{"url": f"https://drawstyle.leeguoo.com/img/{slug}",
                                   "content_type": "image/png"}])
            slug = path.rsplit("/", 1)[-1]
            return {"slug": slug, "version": 4}

        def fake_download(url):
            if url.endswith("/bb"):
                raise OSError("boom")
            return _PNG

        with _tmp_xdg():
            doc = cig._load_styles()
            for slug in ("aa", "bb"):
                doc["styles"][slug] = {
                    "kind": "character", "snippet": "old", "refs": [],
                    "origin": {"platform": "drawstyle", "slug": slug,
                               "version": 3}}
            cig._save_styles(doc)
            with unittest.mock.patch.object(cig, "_platform_request",
                                            fake_request), \
                 unittest.mock.patch.object(cig, "_download_bytes",
                                            fake_download):
                with self.assertRaises(SystemExit):
                    cig._style_command(["update"])
            reloaded = cig._load_styles()["styles"]
            # first entry fully updated AND persisted before the failure
            self.assertEqual(reloaded["aa"]["origin"]["version"], 4)
            self.assertEqual(len(reloaded["aa"]["refs"]), 1)
            self.assertTrue(
                (cig._asset_dir("aa") / reloaded["aa"]["refs"][0]).exists())
            # second entry untouched (still old version, no refs on disk)
            self.assertEqual(reloaded["bb"]["origin"]["version"], 3)
            self.assertEqual(reloaded["bb"]["refs"], [])
            self.assertFalse(cig._asset_dir("bb").exists())


class ApplyPackageMalformed(unittest.TestCase):
    def test_missing_keys_exits_cleanly(self):
        with self.assertRaises(SystemExit) as cm:
            cig._apply_package({"styles": {}}, "x", {"refs": []})
        self.assertIn("malformed package response", str(cm.exception))

    def test_non_dict_payload_exits_cleanly(self):
        with self.assertRaises(SystemExit) as cm:
            cig._apply_package({"styles": {}}, "x", ["not", "a", "dict"])
        self.assertIn("malformed package response", str(cm.exception))


class UploadReferences(unittest.TestCase):
    """The composer's file input moved (issue #19) — the selector cascade is what
    keeps img2img working across that reshuffle, so pin its behaviour."""

    @staticmethod
    def _run(fail_selectors):
        """Drive _upload_references with a fake _ab that rejects some selectors.

        Returns (selectors tried, emitted lines) or raises whatever it raises.
        """
        tried, emitted = [], []

        def fake_ab(ab, *args, session=None, timeout=None, profile=None):
            if args[0] == "upload":
                tried.append(args[1])
                if args[1] in fail_selectors:
                    raise cig.GatewayError(f"chrome-use upload failed: {args[1]}")
                return ""
            return json.dumps(json.dumps(1))  # _JS_PENDING_UPLOADS → 1 thumbnail

        with unittest.mock.patch.object(cig, "_ab", fake_ab), \
                unittest.mock.patch.object(cig.time, "sleep", lambda *_: None):
            cig._upload_references("ab", "s", ["/tmp/a.png"],
                                   lambda: 90.0, emitted.append)
        return tried, emitted

    def test_uses_current_composer_input_first(self):
        tried, emitted = self._run(fail_selectors=())
        self.assertEqual(tried, ["#upload-files"])
        self.assertIn("reference attached", emitted)

    def test_falls_back_to_next_selector(self):
        tried, _ = self._run(fail_selectors=("#upload-files",))
        self.assertEqual(tried, ["#upload-files", "form input[type=file]"])

    def test_reraises_last_error_when_all_selectors_fail(self):
        with self.assertRaises(cig.GatewayError) as cm:
            self._run(fail_selectors=tuple(cig._UPLOAD_SELECTORS))
        self.assertIn(cig._UPLOAD_SELECTORS[-1], str(cm.exception))

    def test_legacy_selector_is_still_last_resort(self):
        # Old DOMs exposed only input[accept="image/*"]; keep them working.
        self.assertIn('input[accept="image/*"]', cig._UPLOAD_SELECTORS)


class SslContext(unittest.TestCase):
    """The gallery's Cloudflare chain trips Python 3.13+'s VERIFY_X509_STRICT
    (issue #20). We clear that ONE flag — and nothing else."""

    def test_strict_x509_is_cleared(self):
        self.assertFalse(cig._ssl_ctx().verify_flags & ssl.VERIFY_X509_STRICT)

    def test_certificate_verification_stays_on(self):
        # The whole point: relax RFC-strictness, never verification itself.
        ctx = cig._ssl_ctx()
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_only_strict_differs_from_the_default_context(self):
        # Guards against a future edit quietly widening this into "trust all".
        default = ssl.create_default_context().verify_flags
        self.assertEqual(cig._ssl_ctx().verify_flags,
                         default & ~ssl.VERIFY_X509_STRICT)


class GeminiPromptFraming(unittest.TestCase):
    """Style references must not become the subject.

    Regression guard for a real failure: an agy run that described every
    attached reference as "the subject" answered a prompt about a green glass
    bottle with a four-panel comic strip of the style reference's cartoon dog.
    """

    def test_style_refs_are_not_the_subject(self):
        t = cig._build_reference_framing(0, 2)
        self.assertIn("do NOT copy their content", t)
        self.assertNotIn("as the subject", t)

    def test_character_refs_are_reproduced(self):
        self.assertIn("canonical subject", cig._build_reference_framing(1, 0))

    def test_mixed_refs_spell_out_the_split(self):
        t = cig._build_reference_framing(2, 3)
        self.assertIn("first 2", t)
        self.assertIn("remaining 3", t)

    def test_no_refs_yields_no_framing(self):
        self.assertEqual(cig._build_reference_framing(0, 0), "")

    def test_gemini_text_carries_the_prompt_and_style_framing(self):
        t = cig._build_gemini_text("a green glass bottle", "1024x1024",
                                   n_character_refs=0, n_style_refs=1)
        self.assertIn("a green glass bottle", t)
        self.assertIn("do NOT copy their content", t)
        self.assertIn("square 1:1", t)

    def test_gemini_asks_for_a_ratio_even_on_auto(self):
        # Silence is not neutral here: with no ratio requested Gemini defaults
        # to 16:9 (five probe runs, all 1024x559). Asking for square is the
        # less surprising default for a caller who specified no shape.
        self.assertIn("square 1:1", cig._build_gemini_text("x", "auto"))

    def test_gemini_honours_each_named_size(self):
        for size, want in (("1024x1024", "square 1:1"),
                           ("1024x1536", "portrait 2:3"),
                           ("1536x1024", "landscape 3:2")):
            self.assertIn(want, cig._build_gemini_text("x", size))


class GeminiImageToolLabels(unittest.TestCase):
    """The image-tool switch matches on localised menu text."""

    def test_the_observed_chinese_label_is_covered(self):
        # This is the exact string read off the live menu; it is the one label
        # verified to work, so it must not be dropped in a future tidy-up.
        self.assertIn("制作图片", cig.GEMINI_IMAGE_TOOL_LABELS)

    def test_english_label_is_covered(self):
        self.assertIn("Create image", cig.GEMINI_IMAGE_TOOL_LABELS)


class GeminiImageSrcMatching(unittest.TestCase):
    """The result regex has to reject Google's own avatars.

    gemini.google.com serves the generated image AND the account avatar off
    googleusercontent.com; matching the bare host grabs the avatar instead.
    """

    def _m(self, src):
        return re.search(cig.GEMINI_IMG_SRC_RE, src) is not None

    def test_blob_result_matches(self):
        self.assertTrue(self._m("blob:https://gemini.google.com/dd0d-3e3f"))

    def test_account_avatar_is_rejected(self):
        self.assertFalse(self._m(
            "https://lh3.googleusercontent.com/a/ACg8ocJ2KygVENyOIg=s64-c-v1-rj"))

    def test_profile_chip_is_rejected(self):
        self.assertFalse(self._m(
            "https://lh3.google.com/u/0/ogw/AF2bZyhScQBt51px0SmUvlC8=s64-c-mo"))


class AgyOutputHandling(unittest.TestCase):
    """agy reports where it saved the file; it does not obey a path we pick."""

    def test_path_is_read_from_a_file_url(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as fh:
            out = f"Saved it as [teapot.png](file://{fh.name}) for you."
            self.assertEqual(cig._agy_extract_path(out), fh.name)

    def test_bare_absolute_path_on_the_last_line(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as fh:
            self.assertEqual(cig._agy_extract_path(f"done\n{fh.name}\n"), fh.name)

    def test_nonexistent_path_is_not_accepted(self):
        self.assertIsNone(cig._agy_extract_path("/nope/does/not/exist.png"))

    def test_prose_only_reply_yields_nothing(self):
        self.assertIsNone(cig._agy_extract_path("I could not generate that."))


class GeminiBackendsAreOptIn(unittest.TestCase):
    """auto must never route to a different vendor's account on its own."""

    def test_auto_pick_never_returns_gemini_or_agy(self):
        for web, codex in ((True, True), (True, False),
                           (False, True), (False, False)):
            self.assertIn(cig._auto_backend_pick(web, codex),
                          ("web", "codex", "neither"))

    def test_both_backends_are_selectable_by_name(self):
        src = Path(cig.__file__).read_text()
        self.assertIn('"auto", "web", "codex", "gemini", "agy"', src)


class GoogleProfileDetection(unittest.TestCase):
    """The Google scan must differ from the chatgpt.com one in the cookie only."""

    def test_it_queries_google_session_cookies(self):
        seen = {}

        def fake(host_like, name_clause):
            seen["host"] = host_like
            seen["name"] = name_clause
            return ["Profile 12"]

        with unittest.mock.patch.object(cig, "_detect_logged_in_profiles", fake):
            self.assertEqual(cig._detect_google_profiles(), ["Profile 12"])
        self.assertIn("google.com", seen["host"])
        self.assertIn("__Secure-1PSID", seen["name"])

    def test_chatgpt_detection_defaults_are_unchanged(self):
        import inspect
        sig = inspect.signature(cig._detect_logged_in_profiles)
        self.assertEqual(sig.parameters["host_like"].default, "%chatgpt.com%")
        self.assertIn("__Secure-next-auth.session-token",
                      sig.parameters["name_clause"].default)


class RefRoles(unittest.TestCase):
    """issue #26 — an ad-hoc --ref must be expressible as style/composition,
    not only as the canonical subject."""

    def test_ref_role_rehomes_adhoc_refs(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            for role in ("character", "style", "composition"):
                ordered = cig._collect_refs(doc, [], ["/a.png"], adhoc_role=role)
                self.assertEqual([r["group"] for r in ordered], [role])

    def test_role_shorthands_order_character_style_composition(self):
        with _tmp_xdg():
            doc = cig._load_styles()
            ordered = cig._collect_refs(
                doc, [], ["/subj.png"],
                adhoc_style_refs=["/st.png"],
                adhoc_composition_refs=["/comp.png"])
            self.assertEqual([r["group"] for r in ordered],
                             ["character", "style", "composition"])
            self.assertEqual([r["ref"] for r in ordered],
                             ["/subj.png", "/st.png", "/comp.png"])

    def test_composition_only_never_claims_the_reference_as_subject(self):
        for text in (
            cig._build_web_text("a man", "auto", n_composition_refs=1),
            cig._build_user_text("a man", "auto", "png", n_composition_refs=1),
            cig._build_gemini_text("a man", "auto", n_composition_refs=1),
            cig._build_reference_framing(0, 0, 1),
        ):
            self.assertIn("composition reference", text)
            self.assertIn("do NOT reproduce", text)
            self.assertNotIn("canonical subject", text)

    def test_zero_composition_refs_leaves_existing_wording_untouched(self):
        self.assertEqual(cig._composition_clause(0, True), "")
        self.assertEqual(
            cig._build_web_text("a cat", "auto", n_character_refs=1),
            cig._build_web_text("a cat", "auto", n_character_refs=1,
                                n_composition_refs=0))

    def test_ref_counts_falls_back_to_subject_without_the_asset_machinery(self):
        self.assertEqual(
            cig._ref_counts(argparse.Namespace(), ["/a.png", "/b.png"]), (2, 0, 0))


class AgyStallTimeout(unittest.TestCase):
    """issue #24 — --stall-timeout was documented but only --timeout enforced."""

    def test_silent_child_is_killed_at_the_idle_deadline(self):
        t0 = time.monotonic()
        with self.assertRaises(cig.GatewayError) as ctx:
            cig._run_agy_watched(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                tempfile.gettempdir(), total_timeout=30.0, stall_timeout=0.6)
        self.assertLess(time.monotonic() - t0, 10.0)
        self.assertIn("stalled", str(ctx.exception))

    def test_chatty_child_survives_a_shorter_stall_window(self):
        rc, out, _err = cig._run_agy_watched(
            [sys.executable, "-c",
             "import sys,time\n"
             "for _ in range(6):\n"
             "    print('tick', flush=True); time.sleep(0.2)"],
            tempfile.gettempdir(), total_timeout=30.0, stall_timeout=0.6)
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("tick"), 6)

    def test_stdout_and_exit_code_are_preserved(self):
        rc, out, err = cig._run_agy_watched(
            [sys.executable, "-c",
             "import sys; print('o'); print('e', file=sys.stderr); sys.exit(3)"],
            tempfile.gettempdir(), total_timeout=10.0, stall_timeout=5.0)
        self.assertEqual((rc, out.strip(), err.strip()), (3, "o", "e"))

    def test_run_agy_accepts_a_stall_timeout(self):
        self.assertIn("stall_timeout", inspect.signature(cig.run_agy).parameters)


class ContentTypeMismatch(unittest.TestCase):
    """issue #25 — a .jpg must not silently contain PNG bytes."""

    def test_fmt_from_mime(self):
        self.assertEqual(cig._fmt_from_mime("image/png"), "png")
        self.assertEqual(cig._fmt_from_mime("image/jpeg; charset=binary"), "jpeg")
        self.assertIsNone(cig._fmt_from_mime("application/octet-stream"))
        self.assertIsNone(cig._fmt_from_mime(None))

    def test_mismatch_warns_naming_both_formats(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            cig._warn_content_type_mismatch(Path("a.jpg"), "jpeg", "image/png")
        msg = buf.getvalue()
        self.assertIn("--format=jpeg", msg)
        self.assertIn("png", msg)

    def test_matching_or_unknown_type_stays_silent(self):
        for ctype in ("image/jpeg", "application/octet-stream", None):
            buf = io.StringIO()
            with redirect_stderr(buf):
                cig._warn_content_type_mismatch(Path("a.jpg"), "jpeg", ctype)
            self.assertEqual(buf.getvalue(), "")

    def test_default_out_path_follows_the_sniffed_type(self):
        src = Path(cig.__file__).read_text()
        self.assertIn("_default_out_path(args.prompt, _actual_fmt)", src)


class GeminiBlobDownload(unittest.TestCase):
    """issue #27 — prefer the byte-exact blob route so Google's C2PA
    provenance manifest survives; fall back to the canvas, never fail."""

    def test_non_blob_src_is_not_attempted(self):
        self.assertIsNone(cig._gemini_blob_download(
            "chrome-use", "s", "https://x/y.png", lambda: 30.0))

    def test_blob_bytes_are_returned_with_the_sniffed_type(self):
        png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 24)

        def fake_ab(ab, *a, **kw):
            self.assertEqual(a[0], "download-url")
            Path(a[2]).write_bytes(png)
            return ""

        with unittest.mock.patch.object(cig, "_ab", fake_ab):
            data, meta = cig._gemini_blob_download(
                "chrome-use", "s", "blob:https://gemini.google.com/x",
                lambda: 30.0)
        self.assertEqual(data, png)
        self.assertEqual(meta["content_type"], "image/png")
        self.assertEqual(meta["provenance"], "preserved")

    def test_old_chrome_use_falls_back_instead_of_raising(self):
        def boom(*a, **kw):
            raise cig.GatewayError("Invalid download URL: expected http://")

        with unittest.mock.patch.object(cig, "_ab", boom):
            self.assertIsNone(cig._gemini_blob_download(
                "chrome-use", "s", "blob:https://gemini.google.com/x",
                lambda: 30.0))

    def test_non_image_payload_is_treated_as_a_miss(self):
        def fake_ab(ab, *a, **kw):
            Path(a[2]).write_bytes(b"<html>nope</html>")
            return ""

        with unittest.mock.patch.object(cig, "_ab", fake_ab):
            self.assertIsNone(cig._gemini_blob_download(
                "chrome-use", "s", "blob:https://gemini.google.com/x",
                lambda: 30.0))

    def test_canvas_path_still_labels_itself_as_provenance_stripped(self):
        src = Path(cig.__file__).read_text()
        self.assertIn('"transport": "canvas", "provenance": "stripped"', src)
        # The C2PA warning must not fire on the byte-exact path.
        self.assertIn('if meta.get("provenance") == "stripped":', src)


if __name__ == "__main__":
    unittest.main()
