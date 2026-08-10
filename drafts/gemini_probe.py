#!/usr/bin/env python3
"""Probe: does gemini.google.com produce images reliably when driven by chrome-use?

Written to answer "should we add a gemini backend at all?" before writing one.
It answered yes (5/5 rounds, ~11s each), and `--backend gemini` in the CLI is the
result — so this is now a STANDALONE DIAGNOSTIC, deliberately kept independent of
the CLI it validated. When the real backend starts failing, the useful question is
"is it Gemini or is it us?", and a probe that imported the CLI's own selectors
could not tell you. Everything here is duplicated on purpose.

What it found, all of which shaped the shipped backend:
  • The composer is `rich-textarea .ql-editor`; Enter submits, and the English
    `aria-label="Send"` selector matches NOTHING on a localised UI.
  • Results render from a `blob:` src, so neither in-page fetch() nor
    `chrome-use download-url` can read them — hence the canvas route.
  • googleusercontent.com also serves the account avatar, so a bare host match
    grabs the avatar instead of the image.
  • A Google cookie proves a sign-in, not a subscription: the default profile
    was signed in to an account whose Gemini subscription had expired, and that
    page has no composer at all.

Usage:
    python3 drafts/gemini_probe.py --inspect                 # dump page state
    python3 drafts/gemini_probe.py -n 5 --profile "Profile 12"
    python3 drafts/gemini_probe.py -n 3 --keep-tab

Pass --profile: without it you get whatever Chrome is open, which is how the
expired-subscription account got picked in the first place.

Exit 0 if every round produced an image, 1 otherwise.
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

GEMINI_URL = "https://gemini.google.com/app"

# Gemini serves generated images off googleusercontent. Verified by --inspect:
# the SAME host also serves the account avatar (`/a/ACg8oc…`) and the profile
# chip (`/ogw/…`), so a bare host match would treat an avatar as a result.
# Require an image-ish path and exclude the two avatar shapes.
IMG_SRC_RE = r"^(?!.*googleusercontent\.com/(a/|ogw/))(?:.*googleusercontent\.com|blob:)"

# Ordered candidates. First that exists wins. Gemini is an Angular app whose
# classes are stable-ish but not contractual, so we lead with role/aria.
COMPOSER_SELECTORS = (
    "rich-textarea .ql-editor",
    'div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"]',
    "textarea",
)
# --inspect on a live page found ZERO matches for the obvious English aria-label
# and `.send-button` — the UI is localised (zh-CN here), so the label is 发送 /
# 提交, and the button only mounts once the composer is non-empty. Kept as a
# fallback list; Enter is the primary submit path.
SEND_SELECTORS = (
    'button[aria-label*="Send" i]',
    'button[aria-label*="发送"]',
    'button[aria-label*="提交"]',
    "button.send-button",
    'button[mattooltip*="Send" i]',
)

PROMPTS = [
    "Generate an image: a red ceramic teapot on a white table, soft daylight.",
    "Generate an image: a small blue paper boat on wet asphalt, top-down view.",
    "Generate an image: a single yellow sunflower against a plain grey wall.",
]


class ProbeError(RuntimeError):
    pass


def find_chrome_use() -> str:
    for name in ("chrome-use", "agent-browser"):
        p = shutil.which(name)
        if p:
            return p
    sys.exit("chrome-use is not installed — "
             "curl -fsSL https://raw.githubusercontent.com/leeguooooo/"
             "chrome-use/main/install.sh | sh")


def ab(cu: str, *args: str, session: str, timeout: float,
       profile: str | None = None) -> str:
    cmd = [cu]
    if profile:
        cmd += ["--profile", profile]
    cmd += [*args, "--session", session]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=max(5.0, timeout))
    except subprocess.TimeoutExpired:
        raise ProbeError(f"chrome-use timed out: {' '.join(args[:2])}") from None
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise ProbeError(f"chrome-use {args[0]} failed (exit {proc.returncode}): "
                         f"{' / '.join(tail)[:300]}")
    return proc.stdout


def ab_eval(cu: str, js: str, session: str, timeout: float):
    """Same double-decode convention as the main CLI: page returns
    JSON.stringify(value); chrome-use prints that string JSON-encoded."""
    out = ab(cu, "eval", js, session=session, timeout=timeout)
    for line in reversed([l for l in out.splitlines() if l.strip()]):
        try:
            inner = json.loads(line)
        except Exception:
            continue
        if isinstance(inner, str):
            try:
                return json.loads(inner)
            except Exception:
                return inner
        return inner
    raise ProbeError(f"could not parse eval output: {out[:200]!r}")


# ---------- page-side JS ----------

JS_INSPECT = r"""(() => {
  const sel = s => { try { return document.querySelectorAll(s).length; }
                     catch(e) { return -1; } };
  const imgs = [...document.querySelectorAll('img')]
    .map(i => (i.currentSrc || i.src || '').slice(0, 120))
    .filter(Boolean);
  return JSON.stringify({
    url: location.href,
    title: document.title,
    composer: {
      'rich-textarea .ql-editor': sel('rich-textarea .ql-editor'),
      'div[contenteditable=true][role=textbox]':
        sel('div[contenteditable="true"][role="textbox"]'),
      'div[contenteditable=true]': sel('div[contenteditable="true"]'),
      'textarea': sel('textarea'),
    },
    send: {
      'aria-label*=Send': sel('button[aria-label*="Send" i]'),
      'button.send-button': sel('button.send-button'),
    },
    responses: sel('model-response'),
    imgCount: imgs.length,
    imgs: imgs.slice(0, 25),
    // A login wall renders no composer at all; distinguish it from "slow app".
    signInLink: sel('a[href*="accounts.google.com"]'),
    bodyText: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 300),
  });
})()"""

JS_COMPOSER = r"""(() => {
  const sels = %s;
  let found = null;
  for (const s of sels) { try { if (document.querySelector(s)) { found = s; break; } }
                          catch(e) {} }
  const t = (document.body.innerText || '');
  return JSON.stringify({
    composer: found,
    signin: /sign in|Sign in to continue/i.test(t) && !found,
    limited: /you've reached your limit|try again later|rate.?limit/i.test(t),
  });
})()"""

JS_BASELINE = r"""(() => {
  const re = new RegExp(%s);
  return JSON.stringify([...document.querySelectorAll('img')]
    .map(i => i.currentSrc || i.src).filter(s => s && re.test(s)));
})()"""

# Poll snapshot. "Streaming" on Gemini is signalled by a stop button; we also
# report the last response's text so a refusal is legible instead of a timeout.
JS_STATE = r"""(() => {
  const seen = new Set(%s);
  const re = new RegExp(%s);
  const stop = !!document.querySelector(
    'button[aria-label*="Stop" i], button[aria-label*="stop response" i]');
  // Exclude anything inside the user's own turn (echoed uploads) and avatars.
  const userSrcs = new Set();
  document.querySelectorAll('user-query img, [class*="user-query"] img')
    .forEach(i => { const s = i.currentSrc || i.src; if (s) userSrcs.add(s); });
  const fresh = [...document.querySelectorAll('img')]
    .map(i => i.currentSrc || i.src)
    .filter(s => s && re.test(s) && !seen.has(s) && !userSrcs.has(s));
  const resp = document.querySelectorAll('model-response');
  const last = resp[resp.length - 1];
  const t = (document.body.innerText || '');
  return JSON.stringify({
    stop,
    last: fresh[fresh.length - 1] || null,
    answered: resp.length > 0,
    limited: /you've reached your limit|try again later/i.test(t),
    atext: last ? (last.innerText || '').trim().slice(0, 240) : '',
  });
})()"""

# Pull the bytes out of the already-rendered <img> via canvas. This is the path
# that actually works on Gemini: results render from a `blob:` src, which
# `download-url` rejects outright ("expected http:// or https://") and which
# in-page fetch() also fails on from chrome-use's eval context. The <img> is
# same-origin, so the canvas is untainted and toDataURL is allowed. PNG re-encode
# loses nothing visually but is NOT the original file — fine for a probe;
# a real backend should prefer the source bytes if we can find an http URL.
JS_CANVAS = r"""(() => {
  try {
    const want = %s;
    const img = [...document.querySelectorAll('img')]
      .find(i => (i.currentSrc || i.src) === want);
    if (!img) return JSON.stringify({ok: false, error: 'img element gone'});
    if (!img.complete || !img.naturalWidth)
      return JSON.stringify({ok: false, error: 'img not decoded yet'});
    const c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext('2d').drawImage(img, 0, 0);
    const url = c.toDataURL('image/png');
    return JSON.stringify({ok: true, type: 'image/png',
                           w: c.width, h: c.height,
                           b64: url.split(',')[1]});
  } catch (e) { return JSON.stringify({ok: false, error: String(e)}); }
})()"""

JS_FETCH = r"""(async () => {
  try {
    const r = await fetch(%s, {credentials: 'include'});
    if (!r.ok) return JSON.stringify({ok: false, status: r.status});
    const buf = new Uint8Array(await (await r.blob()).arrayBuffer());
    let bin = ''; const CH = 0x8000;
    for (let i = 0; i < buf.length; i += CH)
      bin += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
    return JSON.stringify({ok: true, type: r.headers.get('content-type'),
                           bytes: buf.length, b64: btoa(bin)});
  } catch (e) { return JSON.stringify({ok: false, error: String(e)}); }
})()"""


# ---------- probe ----------

def log(msg: str, t0: float) -> None:
    print(f"[{time.monotonic() - t0:6.1f}s] {msg}", file=sys.stderr)


def wait_composer(cu: str, session: str, timeout: float, t0: float,
                  tries: int = 20) -> str:
    js = JS_COMPOSER % json.dumps(list(COMPOSER_SELECTORS))
    for _ in range(tries):
        try:
            st = ab_eval(cu, js, session=session, timeout=min(20.0, timeout))
        except ProbeError:
            st = None
        if isinstance(st, dict):
            if st.get("limited"):
                raise ProbeError("gemini says the account hit a usage limit")
            if st.get("signin"):
                raise ProbeError("login wall — this Chrome isn't signed in to Gemini")
            if st.get("composer"):
                log(f"composer found: {st['composer']}", t0)
                return st["composer"]
        time.sleep(1.5)
    raise ProbeError("composer never appeared (run --inspect to see the page)")


def submit(cu: str, session: str, composer: str, prompt: str,
           budget, t0: float) -> None:
    ab(cu, "click", composer, session=session, timeout=min(20.0, budget()))
    # Real keystrokes, not `fill`: Gemini's composer is a Quill contenteditable
    # and a DOM-only mutation leaves the send button bound to empty state —
    # exactly the ProseMirror problem the ChatGPT path already hit.
    ab(cu, "keyboard", "type", prompt, session=session, timeout=min(60.0, budget()))

    empty_js = ("(() => { const e = document.querySelector(%s);"
                " return JSON.stringify(!e || (e.innerText||'').trim().length===0); })()"
                % json.dumps(composer))

    for attempt in range(6):
        ab(cu, "press", "Enter", session=session, timeout=min(20.0, budget()))
        time.sleep(1.2)
        try:
            if ab_eval(cu, empty_js, session=session, timeout=min(15.0, budget())):
                log(f"submitted (enter, attempt {attempt + 1})", t0)
                return
        except ProbeError:
            pass
        for s in SEND_SELECTORS:
            try:
                ab(cu, "click", s, session=session, timeout=min(15.0, budget()))
                break
            except ProbeError:
                continue
        time.sleep(1.5)
        try:
            if ab_eval(cu, empty_js, session=session, timeout=min(15.0, budget())):
                log(f"submitted (send button, attempt {attempt + 1})", t0)
                return
        except ProbeError:
            pass
    raise ProbeError("composer never cleared — prompt likely never sent")


def poll_for_image(cu: str, session: str, baseline, deadline: float,
                   budget, t0: float) -> str:
    js = JS_STATE % (json.dumps(baseline), json.dumps(IMG_SRC_RE))
    stable = None
    idle = 0
    phase = ""
    atext = ""
    while time.monotonic() < deadline:
        time.sleep(2.0)
        try:
            st = ab_eval(cu, js, session=session, timeout=min(20.0, budget()))
        except ProbeError:
            continue
        if not isinstance(st, dict):
            continue
        if st.get("limited"):
            raise ProbeError("hit a Gemini usage limit mid-generation")
        if st.get("stop"):
            if phase != "gen":
                phase = "gen"
                log("generating", t0)
            stable, idle = None, 0
            continue
        cur = st.get("last")
        if cur:
            if phase != "img":
                phase = "img"
                log("image appeared", t0)
            idle = 0
            if cur == stable:      # same src twice → not a mid-render partial
                return cur
            stable = cur
        elif st.get("answered"):
            if st.get("atext"):
                atext = st["atext"]
            idle += 1
            if idle >= 10:         # ~20s of answered-but-no-image
                raise ProbeError("responded without an image" +
                                 (f' — said: "{atext}"' if atext else ""))
    raise ProbeError("timed out waiting for an image")


def fetch_image(cu: str, session: str, src: str, budget,
                tmp: Path) -> tuple[bytes, str]:
    """Get the generated image's bytes, trying three routes in order.

    Canvas first, because it is the only one that actually works here — the
    other two are kept so that a future Gemini change that switches results back
    to an http(s) src is picked up automatically rather than silently failing:

      1. canvas off the rendered <img>  — works; re-encodes to PNG, which drops
         the C2PA manifest (SynthID lives in the pixels and survives).
      2. in-page fetch()                — dies on a blob: src with a bare
                                          "TypeError: Failed to fetch".
      3. chrome-use download-url        — refuses a blob: src outright:
                                          "expected http:// or https://".
    """
    errs: list[str] = []

    # 1. canvas off the rendered <img> — the only path proven to work here.
    for _ in range(5):
        try:
            res = ab_eval(cu, JS_CANVAS % json.dumps(src), session=session,
                          timeout=min(60.0, budget()))
        except ProbeError as e:
            res = {"ok": False, "error": str(e)}
        if isinstance(res, dict) and res.get("ok"):
            return base64.b64decode(res["b64"]), res.get("type", "image/png")
        errs.append(f"canvas: {res}")
        time.sleep(2.0)  # usually just "img not decoded yet"

    # 2. in-page fetch — works for http(s) srcs, dies on blob:.
    try:
        res = ab_eval(cu, JS_FETCH % json.dumps(src), session=session,
                      timeout=min(120.0, budget()))
        if isinstance(res, dict) and res.get("ok"):
            return base64.b64decode(res["b64"]), (res.get("type") or "")
        errs.append(f"in-page fetch: {res}")
    except ProbeError as e:
        errs.append(f"in-page fetch: {e}")

    # 3. browser-stack download. Only meaningful for a real http(s) URL —
    #    chrome-use rejects a blob: src outright ("expected http:// or https://").
    if not src.startswith("blob:"):
        tmp.parent.mkdir(parents=True, exist_ok=True)
        try:
            ab(cu, "download-url", src, str(tmp), session=session,
               timeout=min(120.0, budget()))
            for _ in range(20):   # the command returns before the file lands
                if tmp.is_file() and tmp.stat().st_size > 0:
                    break
                time.sleep(1.0)
            if tmp.is_file() and tmp.stat().st_size > 0:
                data = tmp.read_bytes()
                head = data[:12]
                ctype = ("image/png" if head.startswith(b"\x89PNG") else
                         "image/jpeg" if head.startswith(b"\xff\xd8") else
                         "image/webp" if head[:4] == b"RIFF"
                         and head[8:12] == b"WEBP" else
                         "application/octet-stream")
                return data, ctype
            errs.append(f"download-url: no file at {tmp}")
        except ProbeError as e:
            errs.append(f"download-url: {e}")

    raise ProbeError("could not extract image bytes — " + " | ".join(errs[-3:]))


def one_round(cu: str, session: str, prompt: str, timeout: float,
              profile: str | None, outdir: Path, idx: int) -> dict:
    t0 = time.monotonic()
    deadline = t0 + timeout

    def budget() -> float:
        return max(2.0, deadline - time.monotonic())

    rec: dict = {"round": idx, "prompt": prompt}
    try:
        log(f"opening {GEMINI_URL}", t0)
        ab(cu, "open", GEMINI_URL, session=session,
           timeout=min(45.0, budget()), profile=profile)
        composer = wait_composer(cu, session, budget(), t0)
        baseline = ab_eval(cu, JS_BASELINE % json.dumps(IMG_SRC_RE),
                           session=session, timeout=min(20.0, budget()))
        if not isinstance(baseline, list):
            baseline = []
        log(f"baseline images: {len(baseline)}", t0)
        submit(cu, session, composer, prompt, budget, t0)
        src = poll_for_image(cu, session, baseline, deadline, budget, t0)
        rec["src"] = src[:200]
        data, ctype = fetch_image(cu, session, src, budget,
                                  outdir / f"raw-{idx:02d}.download")
        ext = {"image/png": ".png", "image/jpeg": ".jpg",
               "image/webp": ".webp"}.get(ctype.split(";")[0].strip(), ".bin")
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"gemini-probe-{idx:02d}{ext}"
        path.write_bytes(data)
        rec.update(ok=True, bytes=len(data), type=ctype, path=str(path),
                   seconds=round(time.monotonic() - t0, 1), src=src[:120])
        log(f"OK — {len(data)} bytes → {path}", t0)
    except ProbeError as e:
        rec.update(ok=False, error=str(e), seconds=round(time.monotonic() - t0, 1))
        log(f"FAIL — {e}", t0)
    return rec


def inspect(cu: str, session: str, profile: str | None) -> int:
    t0 = time.monotonic()
    log(f"opening {GEMINI_URL}", t0)
    ab(cu, "open", GEMINI_URL, session=session, timeout=45.0, profile=profile)
    time.sleep(5.0)  # let the Angular app settle
    print(json.dumps(ab_eval(cu, JS_INSPECT, session=session, timeout=30.0),
                     indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--rounds", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=240.0,
                    help="per-round budget in seconds (default 240)")
    ap.add_argument("--profile", help="Chrome profile name; omit to use the relay "
                                      "(your currently open Chrome)")
    ap.add_argument("--session", default="gemini-probe")
    ap.add_argument("--prompt", help="override the built-in rotating prompts")
    ap.add_argument("--outdir", default="drafts/gemini-probe-out")
    ap.add_argument("--keep-tab", action="store_true")
    ap.add_argument("--inspect", action="store_true",
                    help="just open Gemini and dump selector/DOM diagnostics")
    args = ap.parse_args()

    cu = find_chrome_use()
    outdir = Path(args.outdir)

    try:
        if args.inspect:
            return inspect(cu, args.session, args.profile)

        results = []
        for i in range(1, args.rounds + 1):
            prompt = args.prompt or PROMPTS[(i - 1) % len(PROMPTS)]
            print(f"\n=== round {i}/{args.rounds} ===", file=sys.stderr)
            results.append(one_round(cu, args.session, prompt, args.timeout,
                                     args.profile, outdir, i))
            if i < args.rounds:
                time.sleep(5.0)  # don't hammer; a burst is its own failure mode

        ok = [r for r in results if r.get("ok")]
        times = [r["seconds"] for r in ok]
        print("\n--- summary ---")
        print(f"success: {len(ok)}/{len(results)}")
        if times:
            print(f"seconds: min {min(times)}  max {max(times)}  "
                  f"avg {sum(times) / len(times):.1f}")
        for r in results:
            mark = "ok  " if r.get("ok") else "FAIL"
            detail = (f"{r['bytes']}B {r['type']}" if r.get("ok")
                      else r.get("error", ""))
            print(f"  {mark} round {r['round']} {r['seconds']}s  {detail}")
        (outdir / "results.json").parent.mkdir(parents=True, exist_ok=True)
        (outdir / "results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False))
        return 0 if len(ok) == len(results) else 1
    finally:
        if not args.keep_tab:
            try:
                ab(cu, "close", session=args.session, timeout=15.0)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
