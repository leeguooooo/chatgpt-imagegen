# Design: Pinnable character / style assets (image + text, stackable)

**Date:** 2026-06-27
**Status:** Approved (brainstorm)
**Component:** `chatgpt-imagegen` CLI (single-file Python)

## Problem

> **Subcommand name:** the existing verb is **`style`** (singular) — `main()` dispatches on `sys.argv[1] == "style"` and `_style_command` sets `prog="chatgpt-imagegen style"`. This spec keeps `style` as canonical and adds a `styles` alias in the `main()` dispatch + help epilog (cheap, reads naturally). All command examples below use `style`.

Today the CLI has two half-features that don't connect:

- **Text styles** (`style add/use/...`, stored in `~/.config/chatgpt-imagegen/styles.json`): named *text* snippets appended to every prompt. Reusable, but words only.
- **`--ref` (img2img)**: attach one or more reference images per generation, on both the `web` and `codex` backends. Powerful, but the user must pass the image path on **every** invocation.

Users who have a custom cartoon character or a signature art style want to **pin it once and reuse it** — without re-typing a `--ref` each time. The goal is character consistency (the same mascot recurs across scenes) AND style consistency (a uniform aesthetic), and the two must be **stackable** (e.g. "my mascot" + "watercolor" at once).

## Key insight that shapes the design

The existing img2img path (`_build_web_text` / `_build_user_text`, gated by a binary `is_edit` flag) frames an attached reference as **"the canonical subject — reproduce it faithfully."** That is exactly **character** semantics.

A **style** reference needs the *opposite* framing: **"match the aesthetic, do NOT copy the content."**

So even though both cases are "pin some images," a character image and a style image must be described to the model with **different wording**. This is why each asset needs a `kind` field, and why the prompt builder must stop being binary.

## Solution overview (Approach A — enrich `styles` into "assets")

Upgrade each `styles` entry from a bare string into an object carrying `kind` + `snippet` + `refs[]`. Fully backward compatible: a legacy string entry is read as `kind: style`, no refs. Reference image files are **copied into a managed asset library** so assets are self-contained and portable. `--style` becomes repeatable so assets stack.

This was chosen over (B) a separate `character` namespace (two vocabularies, duplicated commands, cross-namespace stacking) and (C) a bare named `--ref` bundle (no text pairing, no character/style framing).

## Data model — `styles.json` (version 2, backward compatible)

```jsonc
{
  "version": 2,
  "default": ["mascot", "watercolor"],   // legacy single-string value is coerced to a 1-element list on load
  "styles": {
    "watercolor": "soft watercolor, visible paper texture",   // legacy bare string = {kind:style, snippet, refs:[]}
    "mascot": {
      "kind": "character",                 // "character" | "style"
      "snippet": "a round orange fox mascot named Pip",   // optional if refs present
      "refs": ["ref-1.png", "ref-2.png"]   // filenames; the bytes live in assets/mascot/
    }
  }
}
```

**Read compatibility — normalization is centralized so all downstream code sees objects.**
`_load_styles` runs a new `_normalize_doc(doc)` immediately after parsing:
- Every `styles[name]` value that is a `str` → `{kind: "style", snippet: <str>, refs: []}`.
- A `default` value that is a `str` → `[]` if empty, else `[<str>]`.
- `version` set to 2 in memory; the upgraded shape is rewritten on the next mutating command (no destructive auto-migration on plain reads).

This is required because three current sites assume the value is a `str` and will crash on an object — they all read post-normalization after this change:
- generation hot path (~line 2581): change `_styles_doc["styles"][name]` → `entry["snippet"]`.
- `style list` (~line 2240): `styles[name].split()` → operate on `entry["snippet"]`.
- `style show` (~line 2253): `print(styles[name])` → print snippet + kind + refs.

`_default_styles_doc()` (~line 2146) must change from `{"version": 1, "default": ""}` to `{"version": 2, "default": []}`, because `_load_styles` writes it on first run **and** `reset` writes it (~line 2302) — otherwise fresh installs and resets produce v1 string-default docs that contradict the data model.

**Validation:** `kind ∈ {character, style}`; names keep the existing `_STYLE_NAME_RE` slug rule; an entry must have a non-empty `snippet` OR at least one ref.

(`watercolor`/`mascot` above are illustrative user-created assets; the only seeded built-in today is `doodle`.)

## Asset library on disk

```
~/.config/chatgpt-imagegen/
  styles.json
  assets/
    mascot/
      ref-1.png
      ref-2.png
```

- `add` / `add-ref` **copy** the source image into `assets/<name>/`, validating the type with `_sniff_mime` (PNG/JPEG/WEBP) and downsizing oversized images by calling `_downsize_reference` (~line 426) **directly**. Do **not** route library copies through `_load_reference` (~line 384) — that helper is codex-only (base64s, only downsizes over `REF_B64_BUDGET`). Copied filenames are normalized to `ref-<n>.<ext>` to avoid collisions.
- `rm` deletes the asset's directory along with its entry.
- `reset` wipes the entire `assets/` tree along with re-seeding built-ins (guarded by the existing `-y/--yes` confirmation).

## Commands (all under the existing `style` subcommand; `styles` is an alias)

| Command | Behavior |
|---|---|
| `style add <name> [snippet] [--ref IMG]... [--kind character\|style]` | Create/overwrite an asset. `snippet` becomes `nargs="?"` (currently required positional, ~line 2217); must supply a `snippet` and/or at least one `--ref`. `--kind` defaults to `style`. Copies refs into the library. |
| `style add-ref <name> <img>...` | Append image(s) to an existing asset. |
| `style rm-ref <name> <file>` | Remove one image (by stored filename) from an asset. |
| `style show <name>` | Print kind + snippet + ref filenames + the asset directory path. |
| `style list` | List entries marking `kind`, a `📎N` image badge, and the active `*` markers. |
| `style use <name>...` | Set the active default set (**accepts multiple names** → they stack). |
| `style clear` | Empty the active default set. |
| `style rm <name>` | Delete entry + asset dir. |
| `style reset [-y]` | Re-seed built-ins and wipe `assets/`. |

Generation side:
- `--style NAME` becomes **repeatable** (`action="append"`); multiple values stack.
- `--no-style` disables all asset application (text + refs) for that run.
- Active set resolution: explicit `--style` values if any, else `default` list, minus everything when `--no-style`.

### Capture sugar — `--from-last` (included)

`styles add <name> --from-last [--kind ...]` (and `styles add-ref <name> --from-last`) pins the **most recently generated image** as a reference, so the flow becomes: generate → like it → pin it → reuse.

- On every successful generation the CLI records the absolute output path to a small state file `~/.config/chatgpt-imagegen/last-output.json` (`{path, ts}`).
- `--from-last` reads that path and copies it in like any other ref. If no recorded path exists (or the file is gone), it exits with a clear message telling the user to pass `--ref <path>` instead.

## Prompt construction

At generation time:

1. Resolve the active asset set (per resolution rule above).
2. Partition into a **character group** and a **style group** by each asset's `kind`.
3. Collect reference image files in a deterministic order: **character group first, then style group**. Within the character group, order is: character assets in `--style`/`default` append order, then the user's ad-hoc `--ref` images last (ad-hoc refs are treated as character/subject, preserving current `is_edit` behavior). Within the style group: `--style`/`default` append order.
4. Append snippets to the prompt text. `_compose_prompt` takes a single snippet (~line 2028), so stacking = **repeated application** (fold over the ordered snippets); the trailing-comma trim still behaves under repetition.
5. Build the model instruction from the **counts** `(n_character_refs, n_style_refs)`, replacing the binary `is_edit`:
   - **Style only:** "Match the visual style of the attached reference image(s); do **not** copy their content."
   - **Character only:** (current behavior) "Reproduce the character shown in the reference image(s) as the canonical subject … Scene: `<prompt>`."
   - **Mixed:** "The first N image(s) show a recurring character — reproduce them faithfully as the subject. The remaining image(s) are style references — match their aesthetic, **not** their content. Scene: `<prompt>`."
6. Feed images to each backend in the resolved order:
   - **web:** `_upload_references` uploads the files (already real files on disk in `assets/<name>/`) in order.
   - **codex:** attach as `input_image` content parts in the same order, with `tool_choice: required`.

The text builders (`_build_web_text` ~456, `_build_user_text` ~481) are refactored to accept `(n_character_refs, n_style_refs)` instead of the single `is_edit` boolean. `is_edit == True` (ad-hoc `--ref` only) maps to "character-only" so existing behavior is unchanged. The counts must be threaded through **all** call sites, not just the builders:
- `_build_payload` (~521, derives `is_edit = bool(refs)` and sets `tool_choice`) and its caller (~1867).
- the web call site (~1469).

`tool_choice` stays `"required"` whenever any reference is attached — including style-only, since images are still attached and the tool must fire.

## Error handling & limits

- **Missing ref bytes** (an asset references a file no longer on disk): exit with an error naming the asset and the expected path — never silently skip.
- **Total attached-ref cap:** default max 4 images per generation. If the resolved set exceeds it, attach the first N (character-first ordering) and **log exactly which refs were dropped** — never silently truncate.
- **Unknown style name:** reuse the existing `_die_unknown_style` message.
- **Invalid `kind`:** reject at `add` time with the allowed values.
- **`--from-last` with no recorded/extant output:** clear, actionable error.

## Testing (extends `test_chatgpt_imagegen.py`, all pure-logic / offline)

- Legacy migration: a version-1 file with a bare-string entry and a string `default` loads as normalized objects/list; rewrite bumps to version 2.
- `add --ref` copies the file into `assets/<name>/`; `show` lists it; filename normalization to `ref-<n>.<ext>`.
- `add-ref` / `rm-ref` mutate the library and entry correctly.
- Active-set resolution: multiple `--style`, fallback to `default` list, `--no-style` empties it.
- Partition + ordering: character refs precede style refs; ad-hoc `--ref` grouped with characters.
- Prompt wording: assert the distinguishing phrases for style-only, character-only, and mixed.
- Ref cap: over-limit set attaches N and logs the dropped names.
- Missing ref file → `SystemExit` with the asset/path in the message.
- `reset` wipes `assets/`.
- `--from-last`: records last output on generation; pins it; clear error when absent.

## Implementation note

The change touches widely separated regions of the single file — text builders (~456/481/513), web upload + codex ref load (~1469/1610/1857), the whole styles block (~2007–2306), and the main argparser + post-write last-output recording (~2455–2608). These must be done by **one implementer or strictly sequentially** — parallel edits to the one file collide. The `--from-last` recording has exactly one write site (~line 2608, `out_path.write_bytes`); the `style` subcommand returns early (~2442) so it correctly never records.

## Out of scope (YAGNI)

- Character turnaround / reference-sheet auto-generation.
- Per-asset strength/weight knobs.
- Renaming assets in place.
- Remote/shared asset libraries.
```
