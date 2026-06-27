# chatgpt-imagegen

[![CI](https://github.com/leeguooooo/chatgpt-imagegen/actions/workflows/ci.yml/badge.svg)](https://github.com/leeguooooo/chatgpt-imagegen/actions/workflows/ci.yml)

[English](./README.md) | **中文**

**用你的 ChatGPT 订阅生成图片 —— 不需要 `OPENAI_API_KEY`。**

一个零依赖的单文件 Python CLI(同时也是 AI agent skill):一个文件、只用标准库。**免费 ChatGPT 账号也能用** —— 默认后端走的就是普通 ChatGPT 网页对话,免费用户在网页里本来也能生图。

```bash
chatgpt-imagegen "a watercolor cat sitting on a windowsill" -o cat.png
# -> saved: cat.png  (812,344 bytes)  size=1024x1024  quality=medium
```

<img width="1494" height="870" alt="image" src="https://github.com/user-attachments/assets/b48b0563-58a3-41ff-a207-f01eafbf2ccb" />

---

## 安装

需要 Python 3.10+ 和一份 ChatGPT 订阅(免费档也行)。配好至少一个后端 —— `auto` 会用配好的那个。

**给 AI agent 用(推荐)** —— 把 skill 放进 Claude Code、Codex、Cursor 等:

```bash
npx skills add leeguooooo/chatgpt-imagegen -g
```

然后直接说:*"画一张 …"* / *"generate a hero banner for the README"*。

> 注意:`skills add` 只会复制 `SKILL.md`,不会带上 `chatgpt-imagegen` 脚本本体。没关系 —— skill 会
> **自愈**:首次使用时 agent 会用一条 `curl` 把这个单文件 CLI 拉到 `SKILL.md` 旁边(纯标准库 Python、
> 零依赖),你只需要 `PATH` 上有 `python3` ≥ 3.10。想自己预先放好:
> `curl -fsSL https://raw.githubusercontent.com/leeguooooo/chatgpt-imagegen/main/chatgpt-imagegen -o ~/.agents/skills/chatgpt-imagegen/chatgpt-imagegen && chmod +x $_`。

**独立 CLI** —— 不用 `pip`、不用虚拟环境、不用守护进程:

```bash
git clone https://github.com/leeguooooo/chatgpt-imagegen
sudo install chatgpt-imagegen/chatgpt-imagegen /usr/local/bin/chatgpt-imagegen
```

**更新** —— `skills` 没有自动更新,所以 CLI 自己提醒:每天最多查一次 `main`,有新版就打一段提示,并**列出相比你当前版本改了哪些功能**。更新执行 `skills update chatgpt-imagegen`(或重跑自愈 `curl`);`chatgpt-imagegen doctor` 会显示当前版本与最新版及同样的更新清单。想关掉:`CHATGPT_IMAGEGEN_NO_UPDATE_CHECK=1`。

**后端**(配一个即可):

- **`web`**(默认,不花 Codex 用量)—— 经 [`chrome-use`](https://github.com/leeguooooo/chrome-use) 驱动你已登录的 Chrome:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/leeguooooo/chrome-use/main/install.sh | sh
  chrome-use extension install   # 然后装扩展、重启 Chrome、登录 chatgpt.com
  ```
- **`codex`**(兜底,花 Codex 用量)—— `npm i -g @openai/codex && codex login`。

没装 `chrome-use`?`auto` 会自己回退到 `codex` 并提示你。

## 两个后端

同一份订阅分两个限流桶;你花哪个,取决于图在**哪儿**生成:

| 后端 | 怎么生成 | 花哪个桶 | 前置条件 |
| --- | --- | --- | --- |
| **`web`**(默认) | 驱动你已登录的 ChatGPT 浏览器 —— 普通对话,出图后默认删除。 | ChatGPT 对话 —— **不花 Codex 用量** | 登录的 Chrome + `chrome-use` |
| **`codex`** | 无头 POST 到 Codex responses 接口。 | **Codex 用量**(计量桶) | `codex login` |

`auto` 优先 `web`(省 Codex 用量),没有可用登录浏览器时回退 `codex` —— 所以开着 Chrome 的笔记本走 `web`,无头服务器走 `codex`,自动判断。`web` 用浏览器当前登录的账号出图。用 `--backend web` / `--backend codex`(或 `CHATGPT_IMAGEGEN_BACKEND`)强制其一。

## 用法

```bash
chatgpt-imagegen "<prompt>" [options]
```

常用参数 —— 完整列表见 `chatgpt-imagegen --help`:

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--backend` | `auto` | `auto` \| `web` \| `codex` |
| `-o`, `--out PATH` | `assets/generated/<slug>.<ext>` | 输出文件;父目录自动创建 |
| `--size` | `auto` | `auto` 或 `WIDTHxHEIGHT`(如 `1024x1024`、`1536x1024`) |
| `--format` | `png` | `png` \| `jpeg` \| `webp` |
| `-i`, `--ref PATH_OR_URL` | — | [图生图](#图生图):编辑一张参考图(可重复) |
| `--style NAME` | — | 套用保存的[风格/资产](#风格)(文字 + 钉住的参考图);可重复以叠加 |
| `--profile` | `auto` | *(web)* 驱动哪个 Chrome profile(`auto` / `relay` / profile 名) |
| `--open` | 关 | 出图后用默认看图器打开 |
| `--quiet` | 关 | stdout **只**打印保存路径(适合管道) |

子命令:`chatgpt-imagegen doctor`(看哪个后端就绪)· `chatgpt-imagegen style <verb>`(管理[风格](#风格)预设)。

```bash
chatgpt-imagegen "logo for a coffee shop, vector style" -o brand/logo.png --size 1024x1024
chatgpt-imagegen "moody mountain sunset" -o web/hero.png --size 1536x1024
OUT=$(chatgpt-imagegen "icon" --quiet)      # 在 shell 管道里拿到路径
```

## 图生图

用 `-i`/`--ref` 传一张参考图,就是**编辑它**而不是从文字生成 —— 等同于把图拖进 ChatGPT 输入框让它改风格。两个后端都支持(`auto` 自动选);参考图可以是本地路径或 `http(s)` URL(PNG/JPEG/WEBP),重复 `-i` 可传多张。

```bash
chatgpt-imagegen "make it a warm golden-hour photo, cinematic 35mm" -i photo.jpg -o out.png
```

本 README 里每张图都是这个工具生成的:

| `水彩猫坐在窗台上` | `咖啡店 logo,矢量风格` | `氛围感雪山日落`(1536×1024) |
| --- | --- | --- |
| <img src="./docs/gallery/watercolor-cat.png" width="240" alt="水彩猫"> | <img src="./docs/gallery/coffee-logo.png" width="240" alt="咖啡店 logo"> | <img src="./docs/gallery/mountain-sunset.png" width="240" alt="雪山日落"> |

## 风格

**风格(资产)**是可复用的「外观」,用 `--style NAME` 套用 —— 一段文字片段**和/或钉住的参考图**。两种 kind:`--kind style`(学画风,别抄内容)和 `--kind character`(还原一个固定主体 —— 你的吉祥物/角色)。把自己的卡通形象或品牌画风**钉一次**,以后无需每次再传 `--ref`;`--style` 可重复,于是角色和画风能**叠加**。用 `style` 子命令管理(`list` / `show` / `add` / `add-ref` / `rm-ref` / `rm` / `use` / `clear` / `reset`),存在 `~/.config/chatgpt-imagegen/styles.json`,图片复制进 `assets/`。

```bash
chatgpt-imagegen "a robot mascot" --style doodle           # 文字风格,单次
chatgpt-imagegen style add brand "flat vector, bold shapes, teal accent, white background"
chatgpt-imagegen style add pip "一只圆滚滚的橙色狐狸" --kind character --ref pip-a.png --ref pip-b.png
chatgpt-imagegen "Pip 在点咖啡" --style pip --style brand   # 同一只狐狸 + 品牌画风(叠加)
chatgpt-imagegen style add pip --from-last --kind character # 把刚生成、满意的那张钉成角色
chatgpt-imagegen "a photorealistic forest" --no-style      # 单次跳过所有活跃资产
```

## 排错

**报 `no logged-in ChatGPT browser available`,但我明明登录着**（[#15](https://github.com/leeguooooo/chatgpt-imagegen/issues/15)）

`web` 后端够到浏览器有两条路,即便你已登录,两条都可能失手:

- **relay**(复用你**已经开着**的 Chrome)需要连上 **ab-connect 浏览器扩展** —— 普通启动的 Chrome 没调试端口,没扩展 `chrome-use` 就看不到你的标签页。
- **profile 启动**会把已登录的 profile 拷一份再起一个窗口 —— 这步也可能自己失败(profile 拷贝、找不到 Chrome、被限流)。

先跑 **`chatgpt-imagegen doctor`** —— 它会报清楚哪个后端就绪(codex token、chrome-use 版本、relay、已登录 profile)以及 `auto` 会选哪个。另外从 v0.11.1 起,报错本身也会逐个候选打印 `chrome-use` 的**真实原因**并显示 relay 是否连上。三选一:

1. **连上 relay**(推荐 —— 复用你开着的标签页,不花 Codex 用量):`chrome-use extension install`,加载 ab-connect 扩展(`chrome://extensions` → 开发者模式 → 加载已解压),重启 Chrome。用 `chrome-use daemon status --json` 验证 `"relay": true`。
2. **彻底退出 Chrome 再跑** —— `chrome-use` 会自己启动那个已登录的 profile。
3. **`--backend codex`** —— headless 兜底(花 Codex 用量)。

用 `--profile "Profile 1"` 指定 profile,或 `--profile relay` 强制走「开着的 Chrome」。

## 并发

`web` **串行**(一次一张 —— 它驱动同一个 Chrome,且页面侧限流很凶);`codex` 最多 **4** 个并行。多 fire 是安全的 —— 多出来的在锁池上排队,`--timeout` 预算从拿到槽位才开始计。用 `CHATGPT_IMAGEGEN_WEB_CONCURRENCY` / `CHATGPT_IMAGEGEN_CODEX_CONCURRENCY`(`0` = 不限)调整。

订阅额度和 ChatGPT app 共享 —— 别持续 >10 张/分钟。批量请用官方 `/v1/images/generations` API + `OPENAI_API_KEY`。

## 什么时候别用这个

符合下面任一条,就改用官方 `/v1/images/generations` API(配 `OPENAI_API_KEY`):

- 要**真正的 `quality=high`** 或**原生透明背景**(订阅都不支持);
- 做**对外公开的服务** —— 用个人订阅支撑它违反 OpenAI 条款;
- 需要**可逐次结算、能转嫁客户的计费**;
- 持续 **>10 张/分钟**(订阅限流比 API 紧)。

## 更多

- **工作原理(技术):** [docs/how-it-works.zh-CN.md](./docs/how-it-works.zh-CN.md) —— web/codex 流程、Cloudflare Turnstile 防线、OAuth/SSE。
- **需要 HTTP API?** [agent-cli-to-api](https://github.com/leeguooooo/agent-cli-to-api) 把同一个工具暴露成 OpenAI 兼容的 `/v1/chat/completions` 服务。
- **深入(博客):** [chatgpt-imagegen 的设计与原理](https://blog.leeguoo.com/en/posts/chatgpt-imagegen/)。

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。

## 免责声明

本工具调用的是 ChatGPT 内部的 `backend-api/codex` 接口,也就是官方 Codex CLI 用的同一个接口。它不是有文档的公开 API,OpenAI 随时可能更改或限制。使用风险自负,且须遵守 [OpenAI 使用条款](https://openai.com/policies/row-terms-of-use/) —— 尤其**不要用你的 ChatGPT 订阅去支撑对外公开的图像生成服务**。

<details>
<summary>关键词</summary>

用 ChatGPT 订阅生成图片、免费 ChatGPT 账号生图、ChatGPT Plus 生图工具、不用 API key 生图、gpt-image-2 用订阅、ChatGPT 订阅生图 CLI、Codex CLI 生图能力独立工具、给 AI agent 用的生图 skill、本地生图脚本、零依赖 Python 生图工具。

**English:** `ChatGPT subscription image generation`, `free ChatGPT account image generation`, `use ChatGPT Plus for image API`, `gpt-image-2 without OPENAI_API_KEY`, `image_generation tool Responses API`, `ChatGPT image CLI`, `Codex CLI image_gen as standalone tool`, `no-API-key image generation`, `AI agent image generation skill`, `Claude Code image skill`.
</details>
