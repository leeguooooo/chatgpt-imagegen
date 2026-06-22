# Style Presets — Design

**Date:** 2026-06-22
**Status:** Approved (design)
**Scope:** Named, reusable prompt-style snippets for `chatgpt-imagegen`, with an optional active default and per-run override.

---

## Problem

Today every image is generated from exactly the prompt the user types. There is no
way to say "always render in this look" or to keep a small library of reusable style
descriptions. Users who want a consistent aesthetic (e.g. the repo's own README
doodles) must paste the same long style text into every prompt.

This feature adds **style presets**: named text snippets that are appended to the
user's prompt. It is also the tool's **first persistent user-config file**, so the
storage decisions here set the precedent for any future config.

## Goals

- Define, list, show, edit, and delete named style snippets.
- Optionally mark one style as the **active default**, applied automatically.
- Override per run (`--style NAME`) or skip entirely (`--no-style`).
- Ship one built-in style (`doodle`) so the feature is discoverable out of the box.
- Zero new dependencies; stay one-file, stdlib-only.
- 100% backward compatible — existing `chatgpt-imagegen "<prompt>"` invocations are unchanged.

## Non-goals (YAGNI)

- Styles do **not** carry generation params (size/format/model/backend). A style is
  pure prompt text only. Params stay as their own flags.
- No prefix/template/placeholder model — snippets are always appended as a suffix.
- No stacking multiple styles in one run.
- No project-local config layer — global only.
- Built-in styles are **not** re-seeded or merged on upgrade (see Storage).

---

## Data model

A single JSON file: `${XDG_CONFIG_HOME:-~/.config}/chatgpt-imagegen/styles.json`

```json
{
  "version": 1,
  "default": "",
  "styles": {
    "doodle": "drawn as a deliberately crude doodle using the biggest possible blocks of color, leaning hard into a scribbly, pathetically bad look. White background, as if drawn with a mouse in an old-school computer paint program. It should be faintly recognizable yet not quite right — like it almost matches but everything is subtly off, awkward and confusing. Low-res, smeared together pixel by pixel, showing off just how absurdly bad it is. Honestly, draw it however you want — but the content must still be readable."
  }
}
```

- `version` — schema version, for future migrations.
- `default` — name of the active default style, or `""`/absent for none. **Seeded empty.**
- `styles` — map of `name → snippet text`.

A style name is a short slug: `^[a-z0-9][a-z0-9_-]*$` (lowercase, digits, `-`, `_`;
must start alphanumeric). Names are validated on `style add`.

### Built-in seeding

On first use, if the file does **not** exist, it is created with the built-in set
(currently just `doodle`) and `default: ""`. Once the file exists it is **never**
auto-overwritten — a deleted built-in stays deleted, and new built-ins added in a
later release will **not** appear automatically. `style reset` re-seeds the built-in
set on demand (overwrites the `styles` map back to built-ins; see CLI).

> Rationale: simplest possible behavior, no surprise clobbering of user edits. The
> upgrade-doesn't-propagate trade-off is accepted and documented; `style reset` is the
> escape hatch.

`doodle` is the repo's own README-illustration look (deliberately crappy MS-Paint
doodles). It is **only a built-in option, never the default** — defaulting a
general-purpose image tool to "intentionally ugly" would be a bad first run.

---

## Prompt composition

The chosen style snippet is appended to the raw user prompt as a comma-joined suffix
**before** the existing backend wrappers (`_build_web_text` / `_build_user_text`):

```
effective_prompt = f"{user_prompt}, {snippet}"   # only when a style applies
effective_prompt = user_prompt                    # when no style applies
```

The rest of the pipeline (size/format hints, backend framing) is unchanged and
operates on `effective_prompt`.

### Composition affects ONLY the backend text

`args.prompt` is read in three places today: the stderr preview (`prompt:` line ~1958),
the backend dispatch (`_dispatch` ~1968 → `_build_web_text`/`_build_user_text`), and the
output filename slug (`_default_out_path` ~1968). The composed `effective_prompt` flows
into **only the backend dispatch**. The **filename slug** and the **stderr `prompt:`
preview** must stay derived from the **raw user prompt** — otherwise the long `doodle`
snippet would pollute the output filename and hide the user's actual prompt in the log.
Do **not** mutate `args.prompt` in place; compute `effective_prompt` separately and pass
it only into the dispatch path. The stderr preamble's separate `style: NAME` line (above)
is how the applied style surfaces in the log.

### Join edge cases

`_compose_prompt` joins with a literal `", "`. If the user prompt already ends in `,`,
`.`, or whitespace, strip trailing whitespace and a single trailing `,`/`.` before
joining so the result reads cleanly (e.g. `"a cat."` + snippet → `"a cat, drawn as…"`).
Empty/whitespace-only snippet → return the prompt unchanged.

### Resolution order (per run)

1. `--no-style` given → no style (snippet not applied).
2. else `--style NAME` given → use `NAME`; if unknown, **error** and list available names.
3. else `default` is set and non-empty → use it.
4. else → no style.

`--style` and `--no-style` are mutually exclusive (argparse error if both given).

---

## CLI surface

### Generation (unchanged positional `prompt`, two new flags)

```
chatgpt-imagegen "a cat on a windowsill"                 # no style (default empty)
chatgpt-imagegen "a cat on a windowsill" --style doodle  # apply the doodle style
chatgpt-imagegen "a cat on a windowsill" --no-style       # force-skip even if a default is set
```

When a style is applied, the run's stderr preamble notes it (e.g. `style: doodle`)
so users/agents can see what was added.

### Management (`style` subcommand)

```
chatgpt-imagegen style list            # list all names; mark the active default; preview each snippet (truncated to ~60 chars + "…")
chatgpt-imagegen style show NAME       # print one snippet in full
chatgpt-imagegen style add NAME "..."  # create or overwrite NAME with the given snippet
chatgpt-imagegen style rm NAME         # delete NAME (clears default if it pointed here)
chatgpt-imagegen style use NAME        # set NAME as the active default
chatgpt-imagegen style clear           # unset the active default ("清空")
chatgpt-imagegen style reset           # re-seed the built-in styles (with confirmation)
```

- `add` to an existing name overwrites (no separate edit verb).
- `rm` of the style currently named in `default` also clears `default`.
- `use`/`add`/`rm`/`clear`/`reset` write the file; `list`/`show` are read-only.
- Unknown name on `show`/`rm`/`use` → error listing available names, non-zero exit.
- `reset` prompts for confirmation (or `--yes`/`-y` to skip) since it discards user edits.

---

## Parsing implementation

Do **not** convert the existing parser to argparse subparsers — the generation parser
relies on a bare positional `prompt`, and subparsers would collide with it and risk
regressing every existing invocation.

Instead, route at the top of `main()` **before** building the generation parser:

```python
if len(sys.argv) > 1 and sys.argv[1] == "style":
    return _style_command(sys.argv[2:])   # own tiny argparse / manual dispatch
# else: existing generation parser, unchanged
```

`_style_command` owns its own small argparse (or manual verb dispatch) for the
`list/show/add/rm/use/clear/reset` verbs. The generation path is otherwise untouched
aside from adding `--style` / `--no-style` and the snippet-composition step.

> Edge case: a literal prompt of exactly `"style"` (`chatgpt-imagegen style`) now routes
> to management. This is acceptable — a single-word prompt of "style" with no other args
> was never a useful generation call, and any real prompt has more tokens. Documented.

---

## Modules / units

Keep everything in the one file, but as small, independently-testable pure functions:

- `_styles_path() -> Path` — resolve config path (honors `XDG_CONFIG_HOME`).
- `_builtin_styles() -> dict` — the hardcoded built-in map (source of truth for seed/reset).
- `_load_styles() -> dict` — read+seed-if-missing; returns the full `{version, default, styles}` doc.
- `_save_styles(doc) -> None` — atomic write (temp file + rename), creating parent dir.
- `_resolve_style(doc, *, style_arg, no_style) -> str | None` — pure resolution logic (order above). **Heavily unit-tested.**
- `_compose_prompt(user_prompt, snippet) -> str` — the comma-join. Pure. Unit-tested.
- `_valid_style_name(name) -> bool` — slug validation. Pure. Unit-tested.
- `_style_command(argv) -> int` — the management dispatcher (does I/O).

The pure functions (`_resolve_style`, `_compose_prompt`, `_valid_style_name`) are the
testable core and mirror the repo's existing "pure functions + unit tests" pattern
(see `test_chatgpt_imagegen.py`, commit #12).

---

## Error handling

- Corrupt / unparseable `styles.json` → clear error pointing at the file path; do not
  silently overwrite. (User can `style reset` or fix by hand.)
- Unknown style name (generation `--style` or `style show/rm/use`) → error listing the
  available names, non-zero exit.
- Invalid name on `add` → error explaining the slug rule.
- Atomic save (temp + `os.replace`) so an interrupted write can't corrupt the file.
- File-not-writable / dir-not-creatable → surfaced with the path and the OS error.

---

## Testing

Extend `test_chatgpt_imagegen.py` (stdlib `unittest`, runs in CI):

- `_compose_prompt`: snippet appended with `, `; empty/None snippet → prompt unchanged.
- `_resolve_style`: full truth table — no-style wins over --style wins over default;
  unknown `--style` raises; empty default → None.
- `_valid_style_name`: accepts slugs, rejects spaces/uppercase/leading punctuation.
- `_load_styles`: missing file seeds built-ins with empty default; existing file is not
  re-seeded; corrupt file raises.
- `_save_styles`: round-trips; writes atomically (parent dir created).
- Use a temp `XDG_CONFIG_HOME` (or monkeypatch `_styles_path`) so tests never touch the
  real `~/.config`.

## Docs & release scope

- `SKILL.md` — teach agents the style mechanism: `--style`/`--no-style` at generation,
  and `style add` to capture a project-specific look once and reuse it.
- `README.md` + `README.zh-CN.md` — a "Styles" section (CLI table + the `doodle` example,
  ideally with the existing `docs/example-doodle.png`).
- Release notes — polished, bilingual; lead with the `style` subcommand and `--style`,
  call out that nothing changes for existing users (default stays empty).

---

## Open questions

None blocking. Deferred (revisit only if requested): per-project config layer, styles
carrying generation params, multi-style stacking, automatic built-in merge on upgrade.
