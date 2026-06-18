---
name: "chatgpt-imagegen"
version: "0.7.0"
description: "Generate raster images (PNG/JPEG/WebP) using the user's ChatGPT subscription via a local one-file Python CLI — no OPENAI_API_KEY, no gateway, no daemon. Two backends: web (default) drives the user's logged-in ChatGPT browser so generation runs on the conversation surface and does NOT consume Codex-usage limits; codex is a headless fallback that bills the Codex-usage bucket. Use when an agent needs to create a brand-new bitmap asset for the current project (photos, illustrations, icons, hero banners, mockups, sprites, concept art) and the output should be a bitmap file saved into the workspace. Do not use when the task is better solved by editing existing SVG/vector assets, writing code-native graphics (HTML/CSS/canvas), or extending an established repo icon system."
---

# chatgpt-imagegen — agent skill

A standalone Python CLI that produces images via the user's ChatGPT subscription. No API key, no network service, no extra config. It has **two backends** that hit different OpenAI usage buckets — pick with `--backend`.

## Backends

| Backend | Surface | Usage bucket | Needs | Speed |
| --- | --- | --- | --- | --- |
| **`web`** | Drives the user's logged-in ChatGPT browser (via **`chrome-use`**, formerly `agent-browser-stealth`; older installs expose the same binary as `agent-browser`/`abs`) and generates in a regular chat — the same surface as typing in the app. Its real-Chrome connect is what clears Cloudflare + the sentinel proof-of-work a plain/headless client can't. | **ChatGPT conversation** — does **not** consume the metered Codex-usage limit. Works on **any** account, **including free tier** (subject to its daily image cap). | `chrome-use` installed and its extension connected to a Chrome **signed in to chatgpt.com**. | ~30–60 s; each run's chat is filed under a ChatGPT **Project** (default `imagegen`, auto-created) instead of littering the history. |
| **`codex`** | Headless POST to `chatgpt.com/backend-api/codex/responses` with the `image_generation` tool, reusing `~/.codex/auth.json`. | **Codex-usage** (metered — this is the bucket the user usually wants to spare). | `codex login` (writes `~/.codex/auth.json`). | Fast; no browser, no history. |

**Default is `auto`** (`--backend auto`, or `CHATGPT_IMAGEGEN_BACKEND`): it tries **web first** because that spares the Codex-usage limit, and falls back to **codex only when web is unavailable** — i.e. `chrome-use` isn't installed, the browser isn't reachable, or chatgpt.com isn't logged in. The two not-set-up cases are handled explicitly:

- **Browser not logged in / chrome-use missing** → auto silently falls back to codex (a one-line notice prints to stderr). If codex is *also* not set up, it exits naming both fixes.
- **codex not logged in** (`~/.codex/auth.json` absent) → auto still uses web; codex is only the fallback.

Auto does **not** fall back to codex if web was reachable but the generation itself failed after submitting — that would spend the very bucket auto-mode protects. In that case it errors and tells you to rerun with `--backend codex` if you want the Codex-usage path. Force a single backend with `--backend web` or `--backend codex`.

## Prerequisites

**For the default `web` backend:** the user must have **`chrome-use`** (formerly `agent-browser-stealth`; older installs expose the same binary as `agent-browser` / `abs`) and its extension connected to a Chrome that is signed in to chatgpt.com. chrome-use specifically is required — its real-logged-in-Chrome connect is what passes Cloudflare's bot-detection; a plain headless driver will not. The "Temporary Chat" mode disables image generation, so this backend always opens a *regular* chat.

### Install policy — never install chrome-use for the user

If `chrome-use` is **not installed**, do **not** install it on your own initiative:

1. **Generate anyway** via the codex fallback (auto mode does this by itself) — the task comes first.
2. Add a **single gentle tip** to your reply, e.g.: *"提示：装上 chrome-use 后，出图会走你已登录的 ChatGPT 浏览器，不消耗 Codex 额度。想配的话我可以一步步带你装好（含浏览器插件）。"* — and stop there.
3. **Only when the user explicitly says yes**, walk them through the guided setup below, step by step, verifying each step before the next.

Guided setup (opt-in only):

```bash
# 1. Install the CLI (no npm, no token — provides `chrome-use`)
curl -fsSL https://raw.githubusercontent.com/leeguooooo/chrome-use/main/install.sh | sh
# 2. Register the native-messaging host
chrome-use extension install
# 3. Add the Chrome extension, then restart Chrome:
#    https://chromewebstore.google.com/detail/agent-browser-stealth/knfcmbamhjmaonkfnjhldjedeobeafmk
# 4. Sign in to https://chatgpt.com in that Chrome
# 5. Verify: a quick `chatgpt-imagegen "test" --backend web` should print "using current Chrome (relay)"
```

- **Repo:** https://github.com/leeguooooo/chrome-use
- The `chrome-use` skill (`chrome-use skills get core`) covers the extension-connect flow in depth.

**For the `codex` backend:** the user must have run, **once, ever**:

```bash
npm i -g @openai/codex
codex login    # opens browser to sign in to ChatGPT
```

That writes `~/.codex/auth.json`, which the codex backend reads. No `OPENAI_API_KEY` is required for either backend — and setting one will not help. This is the subscription path, not the API path.

## When to use

- The user asks for a new photo, illustration, icon, hero banner, sprite, cover image, infographic, product mockup, concept art, or any other bitmap deliverable for the current project.
- The user is happy with subscription-tier quality (`medium` quality, no native transparent backgrounds — see *Limits* below).
- The deliverable is intended to be saved into the repo or build inputs.

## When not to use

- The user wants an SVG icon that matches an in-repo vector set — edit those instead.
- The task is better solved with code (HTML/CSS, canvas, Mermaid, PlantUML).
- The user already has an image on disk and wants to *edit* it — this skill is generate-only.
- The user explicitly needs **true `quality=high`** or **`background=transparent`** — the subscription path caps quality at `medium` and rejects transparent. Tell the user to use the official `/v1/images/generations` API with their `OPENAI_API_KEY` for those cases.
- The deliverable will be served to end users (e.g. a public service generating images for visitors) — that violates OpenAI's ToS for personal subscriptions. Refuse and explain.

## How to invoke

```bash
"<skill-dir>/chatgpt-imagegen" "<prompt>" [options]
```

When this skill is installed via `npx skills add leeguooooo/chatgpt-imagegen -g`, the bundled `chatgpt-imagegen` script sits next to this `SKILL.md`. Call it by its absolute path — that is the most reliable way and never depends on `$PATH`. If your agent harness exposes a variable that points to the skill's install directory, use it; otherwise expand the path you read this file from.

If the user has separately put `chatgpt-imagegen` on `$PATH` (Option B in the README), you can also just run `chatgpt-imagegen "<prompt>"` directly.

Useful flags:

| Flag | When to use |
| --- | --- |
| `--backend auto` \| `web` \| `codex` | `auto` (default) prefers web and falls back to codex only when the browser is unavailable/not-logged-in; `web` forces the logged-in-browser path (spares Codex-usage); `codex` forces the headless path (bills Codex-usage). Also settable via `CHATGPT_IMAGEGEN_BACKEND`. |
| `--profile auto` \| `relay` \| `NAME` | (web) Which Chrome profile to drive. `auto` (default): use the open Chrome if it's logged in, else auto-switch to a profile that is (detected offline from the cookie DB, read-only). `relay`: only the open Chrome. `"Profile 3"`: that profile. Note: *logged in* ≠ *able to generate* — a free-tier account can still hit its daily image cap. |
| `--session NAME` | (web) Reuse a named Chrome tab group across runs instead of `imagegen-<pid>`. |
| `--project NAME` | (web) ChatGPT Project to file the run's conversation under — matched by exact name, **created automatically if absent**, reused if present. Default `imagegen` (or `CHATGPT_IMAGEGEN_PROJECT`). Pass `--project ""` for a plain top-level chat. If the project step fails, the run warns and continues in a plain chat — it never blocks generation. |
| `--keep-tab` | (web) Leave the ChatGPT tab open after generating (default closes it). Useful for debugging. |
| `-o PATH` | Always use when you know where the file should go in the repo. |
| `--size 1024x1024` | Square icons / logos (verified) |
| `--size 1536x1024` | Landscape hero banners, social cards (verified) |
| `--size 1024x1536` | Portrait covers, mobile splashes (verified) |
| `--size 3840x2160` or similar | 4K landscape (forwarded as-is; backend may reject — fall back to a smaller verified size on failure) |
| `--format webp` | Smaller files for web assets |
| `--quiet` | Use in agent contexts so stdout is *only* the saved path. Progress still streams to stderr (use `--no-progress` to silence it). |
| `--no-progress` | Fully silence the stderr progress timeline (errors still print). |
| `--timeout SECONDS` | Total wall-clock budget (default 300). Large/detailed images can take 2–3 min — raise it if you see a `timed out` error. |
| `--stall-timeout SECONDS` | Max silence (no data from backend) before declaring a stall (default 120, clamped to `--timeout`). Lower it to fail faster on a hung backend. |
| `-V`, `--version` | Print the CLI version and exit. Run `chatgpt-imagegen --version` to confirm which build is installed. |

The script prints **just the saved path on stdout** in every mode; the readable progress timeline and any errors go to **stderr**, so `OUT=$(chatgpt-imagegen "..." --quiet)` captures only the path while you still see the timeline. Each timeline line is stamped with elapsed seconds (`[ 12.3s] generating`), so a slow run is legible and a stall is obvious.

## Save-path policy

1. **Always save into the workspace**, never into `/tmp`, `$HOME`, or `~/.codex/...`.
2. If the user named a destination, pass it via `-o`.
3. If they didn't, pick a sensible subdirectory: `assets/`, `public/`, `static/`, `docs/img/`, `web/img/`, `assets/brand/`, etc. Default to `assets/generated/` only if nothing better fits.
4. Don't overwrite existing files unless the user asked. With `-o` the script overwrites silently; without `-o` it auto-numbers (`name.png`, `name-2.png`).
5. After saving, **echo the final path back to the user**.

## Workflow

1. **Clarify** the prompt enough to write 1–3 sentences: subject, style, composition, mood, constraints. Don't over-augment when the user's prompt is already specific.
2. **Pick size and format** based on intended use (see table above).
3. **Pick the output path** inside the workspace.
4. **Run** `chatgpt-imagegen "<prompt>" -o <path> --size <wxh> --quiet`.
5. **Inspect the result** if you can (e.g. with a `view_image` tool or by reading the file). If clearly wrong, iterate with a single targeted prompt change — do not loop blindly (each call costs subscription quota).
6. **Report the saved path** plus the final prompt used.

## Limits

- **Image quality** is chosen by the backend; this skill has no `--quality` flag, and the subscription path does not honour explicit quality requests reliably. Don't promise a specific quality level to the user. If they need explicit `quality=high`, route them to the official `/v1/images/generations` API with their own `OPENAI_API_KEY`.
- `background: transparent` is **not supported** on the subscription path.
- A single image typically takes **15–60 s**, but large or detailed ones occasionally run **2–3 min**. The default `--timeout` is 300 s to cover this; a genuine hang is caught sooner by the `--stall-timeout` idle window (default 120 s).
- **Per-backend concurrency caps** (cross-process, flock slot pool; excess runs queue safely, waiters print "waiting…", and `--timeout` starts only once a slot is acquired): `web` = **1** (the page surface rate-limits aggressively — "Too many requests"; also one shared Chrome), `codex` = **4** (measured safe on Plus, capped so big fan-outs can't trip the account limiter). Override via `CHATGPT_IMAGEGEN_WEB_CONCURRENCY` / `CHATGPT_IMAGEGEN_CODEX_CONCURRENCY` (`0` = unlimited). For parallel batches use `--backend codex` + shell `&` + `wait`; firing parallel `web` runs is safe but executes one at a time. Do not loop blindly for "variants of the same prompt" — that just burns quota; iterate on the prompt instead.
- Subscription quota is **shared** with the user's interactive ChatGPT use. Don't bulk-generate (>10 images / minute sustained) without permission — you'll hit per-day caps.

## Error handling

| Symptom | Cause | Fix |
| --- | --- | --- |
| `~/.codex/auth.json not found` | Codex CLI never signed in | Tell user to run `npm i -g @openai/codex && codex login` |
| `no ChatGPT OAuth access_token in ~/.codex/auth.json` | Only an API key is present, not a subscription OAuth token | Tell user to run `codex login`; an `OPENAI_API_KEY` value in that file is not a substitute |
| `HTTP 400 requires a newer version of Codex` | local codex CLI is outdated | Tell user to run `npm i -g @openai/codex@latest`; the script reads version from `~/.codex/version.json` which `codex` updates on launch |
| `HTTP 401` / `HTTP 403` then refresh works | Token expired and refresh succeeded | No action needed — script auto-retried |
| `refresh_token is no longer valid — run codex login again` | Refresh token revoked or rotated | Tell user to run `codex login` again |
| `stalled: the image backend sent no data for ~Ns (last phase: …)` | No data for the whole `--stall-timeout` idle window — backend hung or overloaded | Retry; if it recurs, raise `--stall-timeout` (and `--timeout`). The message names the phase it stalled in. |
| `timed out: no image within the Ns total budget (last phase: …)` | The whole `--timeout` budget elapsed — usually a genuinely large image | Raise `--timeout` (e.g. `--timeout 420`) and retry |
| `no image returned. events seen: ...` | Model decided not to call the tool | Rephrase prompt to explicitly say "Use the image_generation tool to render…" |
| `HTTP 429` | Subscription rate-limited | Wait a few minutes; do not retry in a loop |
| `warning: --format=X but FILE.Y has .Y extension` | `-o` extension disagrees with `--format` | Fix the path or the format flag; the file IS written with the format you specified |
| `warning: project 'X' unavailable (…); using a plain chat` | (web) Project list/create API hiccup, or the project page's composer didn't render | Nothing — the image still generated, just in a top-level chat. If it recurs, check the name or pass `--project ""` |
| `chatgpt.com rate-limited this account ('Too many requests') …` | (web) The page surface temporarily blocked the account for making requests too quickly | Wait a few minutes. If it fired *before* submit, `auto` mode already fell back to codex; if *after* submit, check the conversation later — the image may still appear there. Don't retry in a loop |
| `waiting for a free web/codex slot (max N concurrent …)` | More parallel runs than the backend's concurrency cap | Nothing — the run starts when a slot frees up; queue time doesn't eat `--timeout` |

## Internals (for maintainers / debugging)

**web backend (`run_web`)**
- Shells out to `chrome-use` against a session-named Chrome tab group.
- Opens a *regular* `https://chatgpt.com/` chat (Temporary Chat disables the image tool).
- Resolves the target ChatGPT Project from inside the authenticated page (undocumented endpoints, probed live): `GET /backend-api/gizmos/snorlax/sidebar` lists projects (a project is a gizmo with id `g-p-…`); `POST /backend-api/projects {name, instructions}` creates one. It then navigates to `https://chatgpt.com/g/<g-p-id>/project` and submits from that composer, which files the conversation inside the project. Any failure degrades to a plain chat with a stderr warning.
- Submits via `keyboard type` + Enter — **not** `fill`: the composer is a ProseMirror/React contenteditable, and `fill` mutates the DOM without firing the input events React needs, so the send button stays bound to empty state. A send-button click is the fallback.
- Polls page state via `eval`: waits until the streaming/stop control is gone AND a brand-new `<img>` (src matching `estuary/content|files/download|oaiusercontent`) is present and stable across two reads. The img scan is scoped to `main img` (the tab's own conversation thread) — ChatGPT pushes an "Image created" toast with a matching thumbnail into any open tab when *another* conversation finishes an image, and a document-wide scan grabs that sibling's image (issue #7). The generated img is NOT inside `[data-message-author-role="assistant"]`, so `<main>` is the right scope.
- Downloads the bytes with an in-page `fetch(src, {credentials:'include'})` → base64, so the browser's own session cookies authorize the signed asset URL. No tokens leave the browser.

**codex backend (`run_codex`)**
- Reads `~/.codex/auth.json` for `access_token`, `account_id`, `refresh_token`; reads `~/.codex/version.json` for the `version` header.
- POSTs to `https://chatgpt.com/backend-api/codex/responses` with `tools: [{"type": "image_generation"}]`, streams the SSE response, base64-decodes the `image_generation_call` result.
- Auto-refreshes the OAuth token on 401/403 via `https://auth.openai.com/oauth/token` (`client_id=app_EMoamEEZ73f0CkXaXp7hrann`); the refreshed token is persisted back to `auth.json`.

Why the web surface is reachable only through a real browser: the consumer `backend-api/*` paths are gated by three layers — Cloudflare's edge check, a sentinel proof-of-work (`sentinel/chat-requirements` + an in-page `sentinel/sdk.js` that computes the token), and a **Cloudflare Turnstile** token. Tested empirically: a bare bearer-token request from a residential IP **passes** the Cloudflare edge and the PoW (CF is IP-reputation-based; the PoW is hashcash-style and replicable offline) — the actual wall is **Turnstile**, an interactive token a headless client can't forge. And "borrow a browser only for the Turnstile token, then go headless" is self-defeating: the token is single-use and short-lived, so you'd open a browser every request anyway. That's why the web backend drives a genuine logged-in browser; the only true no-browser path is the `codex` backend (which bills Codex-usage).

## Related

- HTTP gateway sibling (for multi-app / SDK-compatible usage): https://github.com/leeguooooo/agent-cli-to-api
