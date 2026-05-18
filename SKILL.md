---
name: "chatgpt-imagegen"
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
| `--size 1024x1024` | Square icons / logos |
| `--size 1536x1024` | Landscape hero banners, social cards |
| `--size 1024x1536` | Portrait covers, mobile splashes |
| `--size 2048x1152` or `3840x2160` | 2K / 4K landscape (slower) |
| `--format webp` | Smaller files for web assets when quality is fine |
| `--quiet` | Use this in agent contexts so stdout is *only* the saved path |

The script prints **just the saved path on stdout** when `--quiet` is set; progress goes to stderr. Capture it with `OUT=$(chatgpt-imagegen "..." --quiet)`.

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

- `quality: high` is **silently downgraded to `medium`** — tier cap, not a bug.
- `background: transparent` is **not supported** on the subscription path.
- A single image takes **15–40 s**. Don't fire many calls in parallel.
- Subscription quota is **shared** with the user's interactive ChatGPT use. Don't bulk-generate without permission.

## Error handling

| Symptom | Cause | Fix |
| --- | --- | --- |
| `~/.codex/auth.json not found` | Codex CLI never signed in | Tell user to run `npm i -g @openai/codex && codex login` |
| `HTTP 400 requires a newer version of Codex` | local codex CLI is outdated | Tell user to run `npm i -g @openai/codex@latest`; the script reads version from `~/.codex/version.json` which `codex` updates on launch |
| `HTTP 401` / `HTTP 403` | OAuth token expired and refresh failed | Tell user to run `codex login` again |
| `no image returned. events seen: ...` | model decided not to call the tool | rephrase prompt to explicitly say "Use the image_generation tool to render…" |
| `HTTP 429` | subscription rate-limited | wait a few minutes; do not retry in a loop |

## Internals (for maintainers / debugging)

- Reads `~/.codex/auth.json` for `access_token`, `account_id`, `refresh_token`.
- Reads `~/.codex/version.json` for the `version` header.
- POSTs to `https://chatgpt.com/backend-api/codex/responses` with `tools: [{"type": "image_generation"}]`.
- Streams the SSE response, extracts the `image_generation_call` output item, base64-decodes `item.result`, writes it to disk.
- Auto-refreshes the OAuth token on 401/403 via `https://auth.openai.com/oauth/token` using `client_id=app_EMoamEEZ73f0CkXaXp7hrann`. The refreshed token is persisted back to `auth.json`.

## Related

- HTTP gateway sibling (for multi-app / SDK-compatible usage): https://github.com/leeguooooo/agent-cli-to-api
