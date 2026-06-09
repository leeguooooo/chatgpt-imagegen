---
name: "chatgpt-imagegen"
version: "0.2.1"
description: "Generate raster images (PNG/JPEG/WebP) using the user's ChatGPT subscription via a local one-file Python CLI — no OPENAI_API_KEY, no gateway, no daemon. Use when an agent needs to create a brand-new bitmap asset for the current project (photos, illustrations, icons, hero banners, mockups, sprites, concept art) and the output should be a bitmap file saved into the workspace. Do not use when the task is better solved by editing existing SVG/vector assets, writing code-native graphics (HTML/CSS/canvas), or extending an established repo icon system."
---

# chatgpt-imagegen — agent skill

A standalone Python CLI that produces images via the user's ChatGPT subscription. It is a thin wrapper around ChatGPT's internal `image_generation` Responses-API tool, the same one the Codex CLI invokes. No API key, no network service, no extra config.

## Prerequisites

The user must have run, **once, ever**:

```bash
npm i -g @openai/codex
codex login    # opens browser to sign in to ChatGPT
```

That writes `~/.codex/auth.json`, which this skill reads. If the file is missing, tell the user to run the two commands above and stop. Do not try to authenticate any other way.

No `OPENAI_API_KEY` is required — and setting one will not help. This is the subscription path, not the API path.

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
- **Parallel execution is supported** — the backend handles ≥4 concurrent requests with no serialization or 429s on a Plus account. If the user asks for several distinct assets, you may fire `chatgpt-imagegen` in parallel (e.g. shell `&` + `wait`). Do not loop blindly for "variants of the same prompt" — that just burns quota; iterate on the prompt instead.
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

## Internals (for maintainers / debugging)

- Reads `~/.codex/auth.json` for `access_token`, `account_id`, `refresh_token`.
- Reads `~/.codex/version.json` for the `version` header.
- POSTs to `https://chatgpt.com/backend-api/codex/responses` with `tools: [{"type": "image_generation"}]`.
- Streams the SSE response, extracts the `image_generation_call` output item, base64-decodes `item.result`, writes it to disk.
- Auto-refreshes the OAuth token on 401/403 via `https://auth.openai.com/oauth/token` using `client_id=app_EMoamEEZ73f0CkXaXp7hrann`. The refreshed token is persisted back to `auth.json`.

## Related

- HTTP gateway sibling (for multi-app / SDK-compatible usage): https://github.com/leeguooooo/agent-cli-to-api
