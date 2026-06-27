---
name: "chatgpt-imagegen"
version: "0.15.0"
description: "Generate raster images (PNG/JPEG/WebP) using the user's ChatGPT subscription via a local one-file Python CLI — no OPENAI_API_KEY, no gateway, no daemon. Two backends: web (default) drives the user's logged-in ChatGPT browser so generation runs on the conversation surface and does NOT consume Codex-usage limits; codex is a headless fallback that bills the Codex-usage bucket. Use when an agent needs to create a brand-new bitmap asset for the current project (photos, illustrations, icons, hero banners, mockups, sprites, concept art) and the output should be a bitmap file saved into the workspace. Do not use when the task is better solved by editing existing SVG/vector assets, writing code-native graphics (HTML/CSS/canvas), or extending an established repo icon system. Also use proactively: when authoring a document, blog post, technical proposal, design doc, README, or other long-form explanatory content, propose illustrations for the key concepts and generate them as background tasks — don't wait to be asked for an image."
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
- You're authoring long-form or explanatory content — a blog post, technical proposal, design doc, tutorial, postmortem, or README — and a figure would help a concept land. **You don't need to be asked**: propose the figures and generate them (see *[Illustrating documents](#illustrating-documents)* below).

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

Call the script by its absolute path next to this `SKILL.md` — that's the most reliable way and never depends on `$PATH`. If your agent harness exposes a variable pointing to the skill's install directory, use it; otherwise expand the path you read this file from.

### First: self-heal a missing CLI

**`npx skills add` copies only the markdown — it often does *not* drop the `chatgpt-imagegen` script next to this file.** So before the first run, check that the CLI exists and fetch it if absent. It's a single self-contained, pure-stdlib Python file (no `pip`, no deps), so the heal is one `curl`:

```bash
CLI="<skill-dir>/chatgpt-imagegen"   # same directory as this SKILL.md
if [ ! -x "$CLI" ]; then
  curl -fsSL https://raw.githubusercontent.com/leeguooooo/chatgpt-imagegen/main/chatgpt-imagegen -o "$CLI" \
    && chmod +x "$CLI"
fi
"$CLI" --version   # confirm it runs (needs python3 ≥ 3.10 on PATH)
```

Do this silently — don't ask the user. If the `curl` fails (offline/proxy), fall back to `git clone https://github.com/leeguooooo/chatgpt-imagegen` and run `chatgpt-imagegen/chatgpt-imagegen`, or tell the user to install it standalone (see README). Only `python3` is required to run it.

If the user has separately put `chatgpt-imagegen` on `$PATH` (Option B in the README), you can also just run `chatgpt-imagegen "<prompt>"` directly and skip the self-heal.

Useful flags:

| Flag | When to use |
| --- | --- |
| `--backend auto` \| `web` \| `codex` | `auto` (default) prefers web and falls back to codex only when the browser is unavailable/not-logged-in; `web` forces the logged-in-browser path (spares Codex-usage); `codex` forces the headless path (bills Codex-usage). Also settable via `CHATGPT_IMAGEGEN_BACKEND`. |
| `--profile auto` \| `relay` \| `NAME` | (web) Which Chrome profile to drive. `auto` (default): use the open Chrome if it's logged in, else auto-switch to a profile that is (detected offline from the cookie DB, read-only). `relay`: only the open Chrome. `"Profile 3"`: that profile. Note: *logged in* ≠ *able to generate* — a free-tier account can still hit its daily image cap. |
| `--session NAME` | (web) Reuse a named Chrome tab group across runs instead of `imagegen-<pid>`. |
| `--project NAME` | (web) ChatGPT Project to file the run's conversation under — matched by exact name, **created automatically if absent**, reused if present. Default `imagegen` (or `CHATGPT_IMAGEGEN_PROJECT`). Pass `--project ""` for a plain top-level chat. If the project step fails, the run warns and continues in a plain chat — it never blocks generation. |
| `--keep-tab` | (web) Leave the ChatGPT tab open after generating (default closes it). Useful for debugging. Implies `--keep-conversation`. |
| `--keep-conversation` | (web) Keep the ChatGPT conversation after generating. **Default deletes it** (`PATCH is_visible:false`) so the run leaves no history — it's filed under the project only transiently. Also `CHATGPT_IMAGEGEN_KEEP_CONVERSATION=1`. |
| `-o PATH` | Always use when you know where the file should go in the repo. |
| `--size 1024x1024` | Square icons / logos (verified) |
| `--size 1536x1024` | Landscape hero banners, social cards (verified) |
| `--size 1024x1536` | Portrait covers, mobile splashes (verified) |
| `--size 3840x2160` or similar | 4K landscape (forwarded as-is; backend may reject — fall back to a smaller verified size on failure) |
| `--format webp` | Smaller files for web assets |
| `--style NAME` | Apply a saved asset (a style snippet and/or pinned reference images). **Repeatable** — stack a character + a style, e.g. `--style mascot --style watercolor`. See [Styles & assets](#styles--assets). Overrides any active default set for this run. |
| `--no-style` | Skip all assets (text *and* pinned refs) for this run even if the user set an active default. |
| `--quiet` | Use in agent contexts so stdout is *only* the saved path. Progress still streams to stderr (use `--no-progress` to silence it). |
| `--no-progress` | Fully silence the stderr progress timeline (errors still print). |
| `--timeout SECONDS` | Total wall-clock budget (default 300). Large/detailed images can take 2–3 min — raise it if you see a `timed out` error. |
| `--stall-timeout SECONDS` | Max silence (no data from backend) before declaring a stall (default 120, clamped to `--timeout`). Lower it to fail faster on a hung backend. |
| `-V`, `--version` | Print the CLI version and exit. Run `chatgpt-imagegen --version` to confirm which build is installed. |

The script prints **just the saved path on stdout** in every mode; the readable progress timeline and any errors go to **stderr**, so `OUT=$(chatgpt-imagegen "..." --quiet)` captures only the path while you still see the timeline. Each timeline line is stamped with elapsed seconds (`[ 12.3s] generating`), so a slow run is legible and a stall is obvious.

## Styles & assets

An **asset** is a named, reusable look stored in `~/.config/chatgpt-imagegen/styles.json` (honours `$XDG_CONFIG_HOME`). Each asset carries a text snippet **and/or pinned reference images**, plus a `kind`:

- **`--kind style`** (default) — a visual aesthetic (line, palette, texture). Its refs tell the model *"match this style, **don't** copy the content."*
- **`--kind character`** — a recurring subject (a mascot, a persona). Its refs tell the model *"reproduce this character faithfully as the subject."*

This is what lets a user **pin their own cartoon character or house style once and reuse it** — no re-passing `--ref` every time. Generation is unchanged unless the user opts in (no default out of the box).

**Pinning & reusing:**
- Pin a character from image files: `chatgpt-imagegen style add mascot "a round orange fox named Pip" --kind character --ref a.png --ref b.png` (a few angles → better consistency). The images are **copied into the asset library**, so the asset survives even if you move/delete the originals.
- Pin the image you just liked: `chatgpt-imagegen style add mascot --from-last --kind character` (also works on `style add-ref mascot --from-last`). Flow: generate → like it → pin it → reuse.
- Pin a pure-text style as before: `chatgpt-imagegen style add watercolor "soft watercolor, visible paper texture"`.
- **Stack them**: `chatgpt-imagegen "Pip ordering coffee" --style mascot --style watercolor` (the same fox, in watercolor). Or set a default set: `chatgpt-imagegen style use mascot watercolor`.

**Managing:**
- `style list` — kind, a `📎N` badge for pinned refs, and `*` on the active default set.
- `style show NAME` — kind + snippet + ref filenames + the asset's on-disk path.
- `style add-ref NAME <img>` / `style rm-ref NAME <file>` — add/remove pinned images on an existing asset.
- `style rm NAME` deletes the entry **and** its images; `style clear` empties the active set; `style reset` re-seeds built-ins and wipes the library.
- `styles` (plural) is accepted as an alias for `style`.

**Behavior:** `--ref` images passed at generation time are treated as the subject and stack on top of the active assets. At most **4** reference images attach per run; if more resolve, the first 4 (character-first) are used and the dropped ones are logged to stderr (never silent). Resolution order: `--no-style` > `--style NAME…` > active default set > none. One built-in style ships: `doodle` (the deliberately-crude MS-Paint look). An unknown `--style` fails fast, listing the available names.

Legacy `styles.json` files (text-only entries from older versions) keep working and upgrade automatically on the next change.

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

## Illustrating documents

When you're authoring a document, blog post, technical proposal, design doc, or other long-form explanatory content, **proactively illustrate the key concepts** — you don't need to be asked. The flow:

1. **Announce a brief plan first.** In one or two lines, say where figures will go and what each depicts (e.g. *"I'll add two figures: (1) the request→SSE flow, (2) the token-refresh path."*). Then generate — don't wait for approval; the plan is the reader's chance to redirect.
2. **Fan out background subagents — one per figure.** Each runs the CLI with `--quiet -o <path>` so stdout is just the saved path; keep writing the prose while they render, and embed each image when it lands. Spawn them as background tasks with your own agent/task tooling — one figure per task, never blocking the writing.
3. **Parallelism depends on the user's backend — don't override it.** Honour the user's `--backend` / `CHATGPT_IMAGEGEN_BACKEND` (default `auto`). On the **`web`** backend, concurrency is **1** — background figures **queue** and render one at a time (still fine: it's in the background, and it spends no Codex-usage). On **`codex`**, up to **4** render in parallel but each bills the metered Codex-usage bucket. Which backend to spend is the user's trade-off, not yours.
4. **Choose a style to fit the document's tone.** There's no default illustration style. For informal or blog-style explainers, the built-in **`doodle`** look fits well — deliberately crude, content-accurate (`--style doodle`). For polished specs, pick a cleaner look or a style you've defined (see [Styles & assets](#styles--assets)). To keep one character or look consistent across a document's figures, pin it as an asset and stack it with `--style`.
5. **Don't over-illustrate.** At most one figure per major concept; never decorate for its own sake; and **never loop generating "variants" of the same figure** — that just burns subscription quota. If a figure comes out wrong, change the prompt once and regenerate, don't spray.

### Writing figure prompts

A vague prompt yields a useless figure. Make the prompt describe the figure's **content**, not just name it:

- Spell out the **boxes, arrows, labels, layout, and relationships** — "an architecture diagram" is too vague; say *what's in it* and how the parts connect.
- **One subject, one concept** per figure. Split a busy diagram into two.
- **Name the style** you want explicitly in the prompt or via `--style`.
- For the **`doodle`** look, remember **content accuracy beats polish** — it's supposed to look crude and hand-drawn, but the labels and structure must still be readable.

## Limits

- **Image quality** is chosen by the backend; this skill has no `--quality` flag, and the subscription path does not honour explicit quality requests reliably. Don't promise a specific quality level to the user. If they need explicit `quality=high`, route them to the official `/v1/images/generations` API with their own `OPENAI_API_KEY`.
- `background: transparent` is **not supported** on the subscription path.
- A single image typically takes **15–60 s**, but large or detailed ones occasionally run **2–3 min**. The default `--timeout` is 300 s to cover this; a genuine hang is caught sooner by the `--stall-timeout` idle window (default 120 s).
- **Per-backend concurrency caps** (cross-process, flock slot pool; excess runs queue safely, waiters print "waiting…", and `--timeout` starts only once a slot is acquired): `web` = **1** (the page surface rate-limits aggressively — "Too many requests"; also one shared Chrome), `codex` = **4** (measured safe on Plus, capped so big fan-outs can't trip the account limiter). Override via `CHATGPT_IMAGEGEN_WEB_CONCURRENCY` / `CHATGPT_IMAGEGEN_CODEX_CONCURRENCY` (`0` = unlimited). For parallel batches use `--backend codex` + shell `&` + `wait`; firing parallel `web` runs is safe but executes one at a time. Do not loop blindly for "variants of the same prompt" — that just burns quota; iterate on the prompt instead.
- Subscription quota is **shared** with the user's interactive ChatGPT use. Don't bulk-generate (>10 images / minute sustained) without permission — you'll hit per-day caps.

## Error handling

**First step for any "which backend / why isn't web working" failure:** run `chatgpt-imagegen doctor`. It reports, read-only, the CLI's own version vs. the latest on `main`, whether each backend is set up (codex token; chrome-use installed + version; relay connected; logged-in Chrome profiles), and **which one `auto` would pick** — turning a vague "no logged-in browser" into a precise checklist.

**Self-update reminder.** `skills` has no auto-update, so the CLI nudges instead: at most once a day it reads its own `__version__` (plus a terse per-release changelog) from `main` and, if a newer one exists, prints a short stderr notice that **lists what changed** since your version — so you know *why* to update, not just that you can:

```
提示:chatgpt-imagegen 0.14.0 可用(当前 0.12.0)。更新:skills update chatgpt-imagegen
  • 0.14.0:更新提示现在会列出每个新版本改了什么
  • 0.13.0:新增每天一次的新版本提示…
```

It never touches stdout, never blocks a run, and is skipped under `--quiet`/`--no-progress`; `doctor` checks unconditionally and prints the same change list. To turn it off entirely, set `CHATGPT_IMAGEGEN_NO_UPDATE_CHECK=1`. When you see the notice, the fix is `skills update chatgpt-imagegen` (or re-run the self-heal `curl`).

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

## Reporting issues — you are the feedback channel

This tool is used mostly *through other people's agents*, so **maintainers rarely see failures directly — the agent running it is the main way bugs surface.** When you hit something that looks like a tool bug, help get it reported instead of silently working around it.

- **What's worth reporting:** a crash/traceback, a backend that *should* work but doesn't, wrong or garbled output, a misleading/wrong error message, a `web`/`chrome-use` failure that `chatgpt-imagegen doctor` says should be fine, or behavior that contradicts this SKILL.
- **What's NOT a bug (handle, don't file):** the user simply isn't logged in or hasn't installed a backend (setup — point them at `doctor` + the install steps), or a deliberate content refusal by the model.
- **How:** offer to file it — or hand the user a ready-to-paste report — at **https://github.com/leeguooooo/chatgpt-imagegen/issues**. Search open issues first to avoid duplicates. Include:
  - the exact command you ran,
  - `chatgpt-imagegen -V` (version),
  - the full error text / unexpected output,
  - the output of `chatgpt-imagegen doctor`.
- A 30-second issue with a repro is worth far more than a quiet workaround — it's how this tool gets fixed.

## Related

- HTTP gateway sibling (for multi-app / SDK-compatible usage): https://github.com/leeguooooo/agent-cli-to-api
