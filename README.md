# chatgpt-imagegen

**Generate images using your ChatGPT subscription — no `OPENAI_API_KEY` needed.**

A tiny, zero-dependency Python CLI (and AI-agent skill) that talks directly to ChatGPT's internal `image_generation` tool. If you already pay for ChatGPT Plus / Pro / Team, you can already generate images — this just exposes that capability on the command line and to any AI agent.

```bash
chatgpt-imagegen "a watercolor cat sitting on a windowsill" -o cat.png
# -> saved: cat.png  (812,344 bytes)  size=1024x1024  quality=medium
```

No server. No proxy. No API key. One Python file, stdlib only.

---

## Why this exists

OpenAI offers image generation in two completely separate ways:

| Path | What you pay | How |
| --- | --- | --- |
| **Direct API** (`/v1/images/generations`) | per-image, on top of an `OPENAI_API_KEY` | curl / OpenAI SDK / etc. |
| **ChatGPT subscription** (Plus / Pro / Team) | flat monthly fee | ChatGPT web/desktop app, or the Codex CLI's built-in `image_gen` |

The **subscription path is invisible** to people who don't use the Codex CLI. It runs on ChatGPT's internal `backend-api/codex/responses` endpoint as a Responses-API tool, authenticated by the OAuth token written into `~/.codex/auth.json` when you run `codex login`.

`chatgpt-imagegen` is a 300-line wrapper that does exactly two things:
1. Reads that OAuth token.
2. Calls the same endpoint the Codex CLI calls — but lets you script it directly.

That's it. Same wire protocol, same model quality, same subscription quota.

## Install

You need:
- Python 3.10+
- The OpenAI Codex CLI (`npm i -g @openai/codex`)
- A ChatGPT subscription (Plus / Pro / Team) and a one-time `codex login`

### Option A — for AI agents (recommended)

Install via [skills.sh](https://www.skills.sh) — works with Claude Code, Codex Agent, Cursor, OpenClaw, etc.:

```bash
npx skills add leeguooooo/chatgpt-imagegen -g
```

This drops both the agent instructions (`SKILL.md`) and the CLI itself into your agent's skill directory. Just ask any compatible agent: *"画一张 xxx"* / *"generate a hero banner for the README"*.

### Option B — standalone CLI

```bash
git clone https://github.com/leeguooooo/chatgpt-imagegen
cd chatgpt-imagegen
chmod +x chatgpt-imagegen
./chatgpt-imagegen "a tiny pixel-art mushroom"
```

Or put it on your `$PATH`:

```bash
sudo install chatgpt-imagegen /usr/local/bin/chatgpt-imagegen
```

That's the entire setup. No `pip install`, no virtualenv, no daemon.

## Usage

```bash
chatgpt-imagegen "<prompt>" [options]
```

| Flag | Default | Notes |
| --- | --- | --- |
| `-o`, `--out PATH` | `assets/generated/<slug>.<ext>` | Output file; parent dirs created |
| `--size` | `auto` | `1024x1024`, `1536x1024`, `1024x1536`, `2048x2048`, `3840x2160`, `2160x3840` |
| `--format` | `png` | `png` \| `jpeg` \| `webp` |
| `--model` | `gpt-5.5` | Chat model that hosts the `image_generation` tool |
| `--timeout` | `180` | Seconds before bailing |
| `--quiet` | off | Print **only** the saved path on stdout (perfect for agent pipelines) |

Examples:

```bash
# Default → assets/generated/<slugified-prompt>.png
chatgpt-imagegen "watercolor cat"

# Pick the path
chatgpt-imagegen "logo for a coffee shop, vector style" -o brand/logo.png --size 1024x1024

# Landscape hero banner
chatgpt-imagegen "moody mountain sunset" -o web/hero.png --size 1536x1024

# Use in a shell pipeline
OUT=$(chatgpt-imagegen "icon" --quiet)
echo "saved to $OUT"
```

## AI-agent skill

Drop the repo into any AI-agent's skill directory (Claude Code, Codex Agent, Cursor, etc.):

```bash
# Claude Code example
npx skills add leeguooooo/chatgpt-imagegen -g
# or symlink directly into ~/.claude/skills/
```

The bundled [`SKILL.md`](./SKILL.md) tells the agent when to invoke it, sizing recipes, where to save outputs, and how to handle errors. Just ask any compatible agent: *"画一张 xxx 给我看看"* / *"generate a hero banner for the README"*.

## What works / what doesn't

| Parameter | Subscription path | Notes |
| --- | --- | --- |
| `size` | ✅ honoured | `auto` / arbitrary `WxH` within model limits |
| `output_format` | ✅ honoured | `png` / `jpeg` / `webp` |
| `quality: low/medium/auto` | ✅ honoured | model picks `medium` by default |
| `quality: high` | ⚠️ silently downgraded to `medium` | subscription tier cap |
| `background: transparent` | ❌ not supported on subscription | needs API-key path with `gpt-image-1.5` |
| Image edits (`/v1/images/edits`) | ❌ not exposed yet | open an issue if you need this |
| Speed | typical 15–40 s per image | streamed end-to-end |

## When NOT to use this — use the API instead

If any of these apply, this tool is the wrong fit:

- You want **true `quality=high`** or **native transparent backgrounds** — both require the official `/v1/images/generations` API with an `OPENAI_API_KEY`.
- You're building a **production service** that serves images to end users — using your personal ChatGPT subscription for that violates OpenAI's ToS and burns the quota you use for actual ChatGPT.
- You need **deterministic per-call billing** that you can pass through to customers — the API has that, the subscription doesn't.
- You want **>10 images per minute** sustained — subscription rate limits are tighter than the API.

For those cases, just call OpenAI's official endpoint:

```bash
curl https://api.openai.com/v1/images/generations \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-image-2","prompt":"...","size":"1024x1024"}'
```

## Want this as an OpenAI-compatible HTTP API?

If you need an **HTTP gateway** (so any OpenAI SDK / LangChain / OpenWebUI / Dify / your-own-app can `POST /v1/chat/completions` and get an image back) — use the sister project:

➡️ **[leeguooooo/agent-cli-to-api](https://github.com/leeguooooo/agent-cli-to-api)** — exposes the same ChatGPT-subscription `image_generation` tool as an OpenAI-compatible `/v1/chat/completions` server. Pick that one when you want network-callable, multi-client, or remote-host usage.

| You want | Use |
| --- | --- |
| Run on my laptop, occasional images, agent-driven | **this repo** (chatgpt-imagegen) |
| Multi-app server, team-shared, OpenAI-SDK compatible | [**agent-cli-to-api**](https://github.com/leeguooooo/agent-cli-to-api) |

## How it works (technical)

The Codex CLI's built-in `image_gen` skill is implemented as a native Responses-API tool:

```jsonc
// Codex CLI's request to chatgpt.com/backend-api/codex/responses:
{
  "model": "gpt-5.5",
  "tools": [{"type": "image_generation"}],
  "input": [{"role": "user", "content": [{"type":"input_text","text":"draw a cat"}]}],
  // ...
}
```

The server replies with an SSE stream whose `response.output_item.done` events carry an `item.type === "image_generation_call"` payload, where `item.result` is base64 PNG. `chatgpt-imagegen` does exactly that:

```
chatgpt-imagegen
   │
   ├── reads ~/.codex/auth.json     (OAuth access_token, account_id, refresh_token)
   ├── reads ~/.codex/version.json  (codex CLI version → matches server expectations)
   │
   └── POST https://chatgpt.com/backend-api/codex/responses
       headers: Authorization, version, originator, session_id, …
       body:    tools: [image_generation]
       │
       └── SSE stream
           ├── response.image_generation_call.in_progress
           ├── response.image_generation_call.generating
           ├── response.image_generation_call.partial_image   (ignored)
           ├── response.output_item.done  ← item.result = base64 PNG
           └── response.completed
```

If the OAuth token has expired the script auto-refreshes via `https://auth.openai.com/oauth/token` (using the refresh_token already stored by `codex login`) and persists the new token back to `~/.codex/auth.json`.

## License

MIT — see [LICENSE](./LICENSE).

## Disclaimer

This tool calls ChatGPT's internal `backend-api/codex` endpoint, which is the same endpoint the official Codex CLI uses. It is not a documented public API. OpenAI could change or restrict it at any time. Use is at your own risk and within the [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) — in particular, **do not use your ChatGPT subscription to power a public-facing image generation service**.

---

## Keywords

`ChatGPT subscription image generation`, `use ChatGPT Plus for image API`, `gpt-image-2 without OPENAI_API_KEY`, `gpt-image-2 ChatGPT subscription`, `image_generation tool Responses API`, `ChatGPT image CLI`, `Codex CLI image_gen as standalone tool`, `DALL-E via ChatGPT Plus`, `OAuth-backed OpenAI image generation`, `no-API-key image generation`, `AI agent image generation skill`, `Claude Code image skill`, `OpenAI image generation without billing`.

**中文：** 用 ChatGPT 订阅生成图片、ChatGPT Plus 生图工具、不用 API key 生图、gpt-image-2 用订阅、ChatGPT 订阅生图 CLI、Codex CLI 生图能力独立工具、给 AI agent 用的生图 skill、本地生图脚本、零依赖 Python 生图工具。
