# Release draft — Style presets (v0.11.0)

> Working draft for the GitHub Release body. Bilingual (EN first, 中文 below).
> Before publishing: bump `__version__` to `0.11.0` in `chatgpt-imagegen`, update the
> `-V` example in `README.md` (line ~122) to `0.11.0`, and tag `v0.11.0`.

---

## English

### 🎨 Style presets — reusable prompt looks

You can now save a **style** — a named snippet of prompt text — and apply it with one flag, so a consistent look no longer means pasting the same paragraph into every prompt.

```bash
# Apply a style for one run (appended to your prompt as a suffix)
chatgpt-imagegen "a robot mascot" --style doodle

# Save your own house style once, then make it the default
chatgpt-imagegen style add brand "flat vector, bold shapes, teal #00b3a4 accent, white background"
chatgpt-imagegen style use brand
chatgpt-imagegen "a settings icon"      # → uses brand automatically
```

**What's new**

- **`style` subcommand** — `list` · `show` · `add` · `rm` · `use` · `clear` · `reset`.
- **`--style NAME`** to apply a preset for one run, **`--no-style`** to skip an active default.
- **One built-in style: `doodle`** — the deliberately-crude MS-Paint look every illustration in the README is drawn in.
- Styles persist in `~/.config/chatgpt-imagegen/styles.json` (honours `$XDG_CONFIG_HOME`), seeded once and never silently overwritten — `style reset` re-seeds on demand.

**Nothing changes for existing users.** There is **no default style out of the box**; `chatgpt-imagegen "<prompt>"` behaves exactly as before unless you opt in. The snippet only affects the text sent to the model — your output filename and the prompt shown in the progress log stay your raw prompt. An unknown `--style` fails fast, before any browser/codex work, and lists the names you do have.

Resolution order per run: `--no-style` > `--style NAME` > active default > none.

Docs: see the **Styles** section in the [README](../../README.md#styles) · [中文 README](../../README.zh-CN.md#风格).

---

## 中文

### 🎨 风格预设 —— 可复用的提示词风格

现在可以把一段提示词文字存成有名字的**风格**,一个参数就套用 —— 想要统一的画风,不用再把同一段话粘进每一条 prompt。

```bash
# 单次套用某风格(作为后缀拼到 prompt 后面)
chatgpt-imagegen "a robot mascot" --style doodle

# 把自己的品牌风格存一次,再设成默认
chatgpt-imagegen style add brand "flat vector, bold shapes, teal #00b3a4 accent, white background"
chatgpt-imagegen style use brand
chatgpt-imagegen "a settings icon"      # → 自动用 brand
```

**新增**

- **`style` 子命令** —— `list` · `show` · `add` · `rm` · `use` · `clear` · `reset`。
- **`--style NAME`** 单次套用,**`--no-style`** 单次跳过 active 默认。
- **内置一个风格 `doodle`** —— 就是 README 里每张插图那种"故意很烂"的鼠绘画图程序风。
- 风格存在 `~/.config/chatgpt-imagegen/styles.json`(遵循 `$XDG_CONFIG_HOME`),只在首次预置、之后绝不悄悄覆盖 —— 需要时用 `style reset` 重新预置。

**老用户零影响。** **开箱没有默认风格**;不主动 `--style`,`chatgpt-imagegen "<prompt>"` 和以前完全一样。片段只影响发给模型的文字 —— 输出文件名和进度日志里的 prompt 仍是你的原始 prompt。`--style` 写了不存在的名字会立刻报错(在动浏览器/codex 之前),并列出你已有的名字。

每次出图的解析顺序:`--no-style` > `--style NAME` > active 默认 > 不套。

文档:见 [README](../../README.md#styles) · [中文 README](../../README.zh-CN.md#风格) 的**风格**小节。
