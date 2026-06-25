# chatgpt-imagegen

[![CI](https://github.com/leeguooooo/chatgpt-imagegen/actions/workflows/ci.yml/badge.svg)](https://github.com/leeguooooo/chatgpt-imagegen/actions/workflows/ci.yml)

**English** | [中文](./README.zh-CN.md)

**Generate images with your ChatGPT subscription — no `OPENAI_API_KEY`.**

A tiny zero-dependency Python CLI (and AI-agent skill): one file, stdlib only. Works on a **free ChatGPT account** too — the default backend just drives the normal ChatGPT web chat, where even free-tier users get image generation.

```bash
chatgpt-imagegen "a watercolor cat sitting on a windowsill" -o cat.png
# -> saved: cat.png  (812,344 bytes)  size=1024x1024  quality=medium
```

<img width="1494" height="870" alt="image" src="https://github.com/user-attachments/assets/b48b0563-58a3-41ff-a207-f01eafbf2ccb" />

---

## Install

Needs Python 3.10+ and a ChatGPT subscription (free tier works). Set up at least one backend — `auto` uses whichever is ready.

**For AI agents (recommended)** — drops the skill into Claude Code, Codex, Cursor, etc.:

```bash
npx skills add leeguooooo/chatgpt-imagegen -g
```

Then just ask: *"画一张 …"* / *"generate a hero banner for the README"*.

> Note: `skills add` copies only `SKILL.md`, not the `chatgpt-imagegen` script. That's fine — the
> skill **self-heals**: on first use the agent fetches the one-file CLI next to `SKILL.md` with a
> single `curl` (it's pure-stdlib Python, no deps). You only need `python3` ≥ 3.10 on `PATH`. To
> pre-seed it yourself: `curl -fsSL https://raw.githubusercontent.com/leeguooooo/chatgpt-imagegen/main/chatgpt-imagegen -o ~/.agents/skills/chatgpt-imagegen/chatgpt-imagegen && chmod +x $_`.

**Standalone CLI** — no `pip`, no virtualenv, no daemon:

```bash
git clone https://github.com/leeguooooo/chatgpt-imagegen
sudo install chatgpt-imagegen/chatgpt-imagegen /usr/local/bin/chatgpt-imagegen
```

**Updating** — `skills` has no auto-update, so the CLI reminds you: once a day it checks `main` and, if a newer version exists, prints a short notice **listing what changed** since your version. Run `skills update chatgpt-imagegen` (or re-run the self-heal `curl`) to update; `chatgpt-imagegen doctor` shows your version vs. latest with the same change list. Silence it with `CHATGPT_IMAGEGEN_NO_UPDATE_CHECK=1`.

**Backends** (need one):

- **`web`** (default, spends no Codex-usage) — drives your logged-in Chrome via [`chrome-use`](https://github.com/leeguooooo/chrome-use):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/leeguooooo/chrome-use/main/install.sh | sh
  chrome-use extension install   # then load the extension, restart Chrome, sign in to chatgpt.com
  ```
- **`codex`** (fallback, bills Codex-usage) — `npm i -g @openai/codex && codex login`.

No `chrome-use`? `auto` falls back to `codex` on its own and tells you.

## Backends

The same subscription meters two buckets; which you spend depends on *where* the image is made:

| Backend | How it generates | Bucket | Needs |
| --- | --- | --- | --- |
| **`web`** (default) | Drives your logged-in ChatGPT browser — a normal chat, deleted afterwards. | ChatGPT chat — **no Codex-usage** | A signed-in Chrome + `chrome-use` |
| **`codex`** | Headless POST to the Codex responses endpoint. | **Codex-usage** (metered) | `codex login` |

`auto` prefers `web` (to spare Codex-usage) and falls back to `codex` when no logged-in browser is reachable — so a laptop with Chrome open uses `web`, a headless server uses `codex`, automatically. `web` generates under whatever account that browser is signed into. Force one with `--backend web` / `--backend codex` (or `CHATGPT_IMAGEGEN_BACKEND`).

## Usage

```bash
chatgpt-imagegen "<prompt>" [options]
```

Common options — full list with `chatgpt-imagegen --help`:

| Flag | Default | Notes |
| --- | --- | --- |
| `--backend` | `auto` | `auto` \| `web` \| `codex` |
| `-o`, `--out PATH` | `assets/generated/<slug>.<ext>` | output file; parent dirs created |
| `--size` | `auto` | `auto` or `WIDTHxHEIGHT` (e.g. `1024x1024`, `1536x1024`) |
| `--format` | `png` | `png` \| `jpeg` \| `webp` |
| `-i`, `--ref PATH_OR_URL` | — | [image-to-image](#image-to-image): edit a reference (repeatable) |
| `--style NAME` | — | apply a saved [style](#styles) preset |
| `--profile` | `auto` | *(web)* which Chrome profile to drive (`auto` / `relay` / a name) |
| `--open` | off | open the saved image in your default viewer |
| `--quiet` | off | print **only** the saved path (for pipelines) |

Subcommands: `chatgpt-imagegen doctor` (check which backend is ready) · `chatgpt-imagegen style <verb>` (manage [style](#styles) presets).

```bash
chatgpt-imagegen "logo for a coffee shop, vector style" -o brand/logo.png --size 1024x1024
chatgpt-imagegen "moody mountain sunset" -o web/hero.png --size 1536x1024
OUT=$(chatgpt-imagegen "icon" --quiet)      # capture the path in a shell pipeline
```

## Image-to-image

Pass a reference with `-i`/`--ref` to **edit it** instead of generating from text — the same as dragging an image into the ChatGPT composer and asking for a restyle. Works on both backends (`auto` picks); references are local paths or `http(s)` URLs (PNG/JPEG/WEBP), repeat `-i` for several.

```bash
chatgpt-imagegen "make it a warm golden-hour photo, cinematic 35mm" -i photo.jpg -o out.png
```

Every image in this README is made by this tool:

| `watercolor cat` | `coffee shop logo` | `moody mountain sunset` (1536×1024) |
| --- | --- | --- |
| <img src="./docs/gallery/watercolor-cat.png" width="240" alt="watercolor cat"> | <img src="./docs/gallery/coffee-logo.png" width="240" alt="coffee shop logo"> | <img src="./docs/gallery/mountain-sunset.png" width="240" alt="mountain sunset"> |

## Styles

A **style** is a reusable prompt snippet appended with `--style NAME` — so `--style doodle` turns `a cat` into `a cat, drawn as a deliberately crude doodle …`. There's one built-in (`doodle`) and no default until you opt in. Add your own and manage them with the `style` subcommand (`list` / `show` / `add` / `rm` / `use` / `clear` / `reset`); they live in `~/.config/chatgpt-imagegen/styles.json`.

```bash
chatgpt-imagegen "a robot mascot" --style doodle           # one run
chatgpt-imagegen style add brand "flat vector, bold shapes, teal accent, white background"
chatgpt-imagegen style use brand                           # make it the default
chatgpt-imagegen "a settings icon"                         # uses brand automatically
chatgpt-imagegen "a photorealistic forest" --no-style      # skip the default once
```

## Troubleshooting

**`no logged-in ChatGPT browser available` — but I *am* signed in** ([#15](https://github.com/leeguooooo/chatgpt-imagegen/issues/15))

The `web` backend reaches a browser two ways, and both can miss even when you're logged in:

- **relay** (your *already-open* Chrome) needs the **ab-connect browser extension** connected — a normally-launched Chrome has no debug port, so without it `chrome-use` can't see your tab.
- **profile launch** copies a logged-in profile and starts its own window — which can fail on its own (profile copy, Chrome not found, a rate-limit).

Run **`chatgpt-imagegen doctor`** first — it reports which backend is ready (codex token, chrome-use version, relay, logged-in profiles) and which one `auto` would pick. From v0.11.1 the error itself also prints the *actual* `chrome-use` reason per attempt and whether the relay is connected. Fix any one:

1. **Connect the relay** (best — drives your open tab, no Codex-usage): `chrome-use extension install`, load the ab-connect extension (`chrome://extensions` → Developer mode → Load unpacked), restart Chrome. Verify with `chrome-use daemon status --json` → `"relay": true`.
2. **Fully quit Chrome, then rerun** — `chrome-use` then launches the logged-in profile itself.
3. **`--backend codex`** — headless fallback (bills Codex-usage).

Pick a specific profile with `--profile "Profile 1"`, or force the open-Chrome path with `--profile relay`.

## Concurrency

`web` runs **serialized** (1 at a time — it drives the one shared Chrome, and the page surface rate-limits hard); `codex` runs up to **4** in parallel. Firing more is safe — excess runs queue on a lock pool, and the `--timeout` budget only starts once a slot frees. Override via `CHATGPT_IMAGEGEN_WEB_CONCURRENCY` / `CHATGPT_IMAGEGEN_CODEX_CONCURRENCY` (`0` = unlimited).

Subscription quota is shared with the ChatGPT app — don't sustain >10 images/min. For bulk batches, use the official `/v1/images/generations` API with an `OPENAI_API_KEY`.

## When NOT to use this

Use the official `/v1/images/generations` API (with `OPENAI_API_KEY`) instead if you need any of:

- true **`quality=high`** or native **transparent backgrounds** (subscription exposes neither);
- a **public-facing service** — powering one with a personal ChatGPT subscription violates OpenAI's ToS;
- **deterministic per-call billing** you can pass to customers;
- sustained **>10 images/min** (subscription limits are tighter than the API).

## More

- **How it works (technical):** [docs/how-it-works.md](./docs/how-it-works.md) — the web/codex flows, the Cloudflare Turnstile gate, OAuth/SSE.
- **Need an HTTP API?** [agent-cli-to-api](https://github.com/leeguooooo/agent-cli-to-api) exposes the same tool as an OpenAI-compatible `/v1/chat/completions` server.
- **Deep dive (blog):** [the design and principles behind chatgpt-imagegen](https://blog.leeguoo.com/en/posts/chatgpt-imagegen/).

## License

MIT — see [LICENSE](./LICENSE).

## Disclaimer

This tool calls ChatGPT's internal `backend-api/codex` endpoint — the same one the official Codex CLI uses. It is not a documented public API; OpenAI could change or restrict it at any time. Use at your own risk and within the [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) — in particular, **do not use your ChatGPT subscription to power a public-facing image generation service**.

<details>
<summary>Keywords</summary>

`ChatGPT subscription image generation`, `free ChatGPT account image generation`, `use ChatGPT Plus for image API`, `gpt-image-2 without OPENAI_API_KEY`, `gpt-image-2 ChatGPT subscription`, `image_generation tool Responses API`, `ChatGPT image CLI`, `Codex CLI image_gen as standalone tool`, `DALL-E via ChatGPT Plus`, `OAuth-backed OpenAI image generation`, `no-API-key image generation`, `AI agent image generation skill`, `Claude Code image skill`, `OpenAI image generation without billing`.

**中文：** 用 ChatGPT 订阅生成图片、免费 ChatGPT 账号生图、ChatGPT Plus 生图工具、不用 API key 生图、gpt-image-2 用订阅、ChatGPT 订阅生图 CLI、Codex CLI 生图能力独立工具、给 AI agent 用的生图 skill、本地生图脚本、零依赖 Python 生图工具。
</details>
