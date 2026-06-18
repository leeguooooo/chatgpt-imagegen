# chatgpt-imagegen

[English](./README.md) | **中文**

**用你的 ChatGPT 订阅生成图片 —— 不需要 `OPENAI_API_KEY`。**

一个零依赖的单文件 Python CLI(同时也是 AI agent skill)—— 一个文件、只用标准库 —— 用你的 ChatGPT 账号生成图片,在命令行、也给任意 AI agent 用。

> **✨ 免费 ChatGPT 账号也能用。** 默认的 `web` 后端走的就是普通 ChatGPT 网页对话,而**免费用户在网页里本来也能生图** —— 所以不用付费套餐、不用 API key、不用 Codex 也能出图(受免费档每日生图上限约束)。付费套餐只是额度更高而已。

```bash
chatgpt-imagegen "a watercolor cat sitting on a windowsill" -o cat.png
# -> saved: cat.png  (812,344 bytes)  size=1024x1024  quality=medium
```

---

## 为什么有这个项目

OpenAI 的图像生成有两条完全独立的路:

| 路径 | 怎么收费 | 怎么用 |
| --- | --- | --- |
| **直连 API**（`/v1/images/generations`） | 按张计费,需要 `OPENAI_API_KEY` | curl / OpenAI SDK 等 |
| **ChatGPT 订阅**（Plus / Pro / Team） | 每月固定费 | ChatGPT 网页/桌面 app,或 Codex CLI 内置的 `image_gen` |

对不用 Codex CLI 的人来说,**订阅这条路是隐形的**。它跑在 ChatGPT 内部的 `backend-api/codex/responses` 接口上(作为 Responses-API 工具),用 `codex login` 写进 `~/.codex/auth.json` 的 OAuth token 鉴权。

`chatgpt-imagegen` 把这份能力搬到命令行、也给任意 AI agent 用 —— 并提供**两个后端**,分别命中你订阅里的不同部分。

## 两个后端

<img src="./docs/two-backends.svg" width="760" alt="chatgpt-imagegen —— web 与 codex 后端流程">

同一份订阅,OpenAI 分了**两个独立的限流桶**;你花哪个桶,取决于图是在**哪儿**生成的:

| 后端 | 怎么生成 | 花哪个桶 | 前置条件 |
| --- | --- | --- | --- |
| **`web`** | 驱动你**已登录的 ChatGPT 浏览器**(经 [`chrome-use`](https://github.com/leeguooooo/chrome-use),原名 `agent-browser-stealth`),在普通对话里出图 —— 跟你在 app 里打字出图是同一个界面。靠真 Chrome 连接过掉 Cloudflare + sentinel 工作量证明(无头/普通客户端过不了)。每次的对话自动归档进一个 ChatGPT **项目**(默认 `imagegen`,首次自动创建),不再刷屏历史列表。 | **ChatGPT 对话** —— **不**占用计量的 **Codex 用量**额度。 | 任意登录了 chatgpt.com 的浏览器(**免费档也行**)+ `chrome-use`。 |
| **`codex`** | 无头 POST 到 `backend-api/codex/responses`,复用 `~/.codex/auth.json`。 | **Codex 用量**(计量的那个桶)。 | `codex login`。 |

**默认 `auto`**:先试 `web`(省 Codex 用量),没有可用登录浏览器时回退 `codex`。用 `--backend web` / `--backend codex` 强制其一(或环境变量 `CHATGPT_IMAGEGEN_BACKEND`)。

- **笔记本/台式机**（Chrome 开着且登录）→ `web` —— 不花 Codex 用量。
- **服务器 / 无头 agent 机器** → `codex` —— 那里没浏览器,`auto` 会自己回退。

`web` 用的是**浏览器当前登录的那个账号**出图,可能和 `~/.codex/auth.json` 不是同一个 —— 让浏览器登录你想用其额度的那个账号。

## 安装

你需要 Python 3.10+、一份 ChatGPT 订阅,以及**至少配好一个后端**(`auto` 会用其中配好的那个,优先 `web`):

**`codex` 后端** —— `npm i -g @openai/codex` 然后 `codex login`(写入 `~/.codex/auth.json`)。

**`web` 后端** —— 装好 [`chrome-use`](https://github.com/leeguooooo/chrome-use)(原名 `agent-browser-stealth`;它通过扩展驱动你真实已登录的 Chrome,正是这点能过 Cloudflare + ChatGPT 反爬),并连到一个登录了 chatgpt.com 的 Chrome:

```bash
curl -fsSL https://raw.githubusercontent.com/leeguooooo/chrome-use/main/install.sh | sh
chrome-use extension install
# 然后:给 Chrome 装扩展 → 重启 Chrome → 登录 chatgpt.com
```

扩展:[Chrome 应用商店](https://chromewebstore.google.com/detail/agent-browser-stealth/knfcmbamhjmaonkfnjhldjedeobeafmk)。旧版装出来的 `agent-browser` / `abs` 命令名继续可用,CLI 两个名字都认。

> 没装 `chrome-use`?不影响出图,也**绝不会替你自动安装**:`auto` 模式自己回退到 `codex`,只在 stderr 轻轻提示一句"装上 chrome-use 出图可以不耗 Codex 额度"。

### 方式 A —— 给 AI agent 用(推荐)

经 [skills.sh](https://www.skills.sh) 安装 —— 支持 Claude Code、Codex Agent、Cursor、OpenClaw 等:

```bash
npx skills add leeguooooo/chatgpt-imagegen -g
```

这会把 agent 说明(`SKILL.md`)和 CLI 本体一起放进你 agent 的 skill 目录。然后对任意兼容的 agent 说:*"画一张 xxx"* / *"generate a hero banner for the README"*。

### 方式 B —— 独立 CLI

```bash
git clone https://github.com/leeguooooo/chatgpt-imagegen
cd chatgpt-imagegen
chmod +x chatgpt-imagegen
./chatgpt-imagegen "a tiny pixel-art mushroom"
```

或放到 `$PATH` 上:

```bash
sudo install chatgpt-imagegen /usr/local/bin/chatgpt-imagegen
```

整个安装就这些。不用 `pip install`,不用虚拟环境,不用守护进程。

## 用法

```bash
chatgpt-imagegen "<prompt>" [options]
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--backend` | `auto` | `auto` \| `web` \| `codex`。`auto` 优先 web(省 Codex 用量),没有登录浏览器时回退 codex。见[两个后端](#两个后端)。也可用 `CHATGPT_IMAGEGEN_BACKEND`。 |
| `--profile` | `auto` | *(web)* 驱动哪个 Chrome profile。`auto`:你开着的 Chrome 登录了就用它,否则自动换到一个登录了的(离线探测)。`relay`:只用你开着的 Chrome。或写 profile 名如 `"Profile 3"`。 |
| `--session` | `imagegen-<pid>` | *(web)* 跨次运行复用一个命名的 `chrome-use` Chrome 标签组。 |
| `--project` | `imagegen` | *(web)* 对话归档到哪个 ChatGPT 项目 —— 按名字精确匹配,**没有就自动创建**,有就直接复用。传 `--project ""` 用普通顶层对话。也可用 `CHATGPT_IMAGEGEN_PROJECT`。项目步骤失败只降级为普通对话并告警,绝不阻塞出图。 |
| `--keep-tab` | 关 | *(web)* 出图后保留 ChatGPT 标签页(默认关闭它)。 |
| `-o`, `--out PATH` | `assets/generated/<slug>.<ext>` | 输出文件;父目录自动创建。后缀与 `--format` 不一致时会告警(如 `-o foo.jpg --format png`)。 |
| `--size` | `auto` | `auto` 或任意 `WIDTHxHEIGHT`。已验证:`1024x1024`、`1024x1536`、`1536x1024`。更大尺寸原样透传。 |
| `--format` | `png` | `png` \| `jpeg` \| `webp` |
| `--model` | `gpt-5.5` | 承载 `image_generation` 工具的对话模型 |
| `--timeout` | `300` | 整个请求的**总墙钟预算**(秒)。大图/细节图可能 2–3 分钟。 |
| `--stall-timeout` | `120` | 后端静默多少秒判定为**卡死**(早于总预算触发)。会被钳制到 `--timeout`。 |
| `--quiet` | 关 | stdout **只**打印保存路径(适合 agent 管道)。进度仍走 stderr —— 用 `--no-progress` 静音。 |
| `--no-progress` | 关 | 关掉 stderr 的进度时间线(错误仍打印)。 |
| `-V`, `--version` | — | 打印 CLI 版本(`chatgpt-imagegen 0.7.0`)后退出。 |

示例:

```bash
# 默认 → assets/generated/<提示词slug>.png
chatgpt-imagegen "watercolor cat"

# 指定路径
chatgpt-imagegen "logo for a coffee shop, vector style" -o brand/logo.png --size 1024x1024

# 横版 hero banner
chatgpt-imagegen "moody mountain sunset" -o web/hero.png --size 1536x1024

# 在 shell 管道里用
OUT=$(chatgpt-imagegen "icon" --quiet)
echo "saved to $OUT"
```

上面那几条示例命令的真实输出 —— 本 README 里的每张图都是这个工具自己生成的:

| `水彩猫坐在窗台上` | `咖啡店 logo,矢量风格` | `氛围感雪山日落`(1536×1024) |
| --- | --- | --- |
| <img src="./docs/gallery/watercolor-cat.png" width="240" alt="水彩猫"> | <img src="./docs/gallery/coffee-logo.png" width="240" alt="咖啡店 logo"> | <img src="./docs/gallery/mountain-sunset.png" width="240" alt="雪山日落"> |

<img src="./docs/example-doodle.png" width="420" alt="出图示例"><br>
<sub>它还能干这个 —— 让它把自己的双后端架构画成一张"故意很烂"、鼠标在老式画图程序里蹭出来的涂鸦。</sub>

## 能做什么 / 不能做什么

| 参数 | 订阅路径 | 说明 |
| --- | --- | --- |
| `--size` | ✅ 生效 | `auto` 或任意 `WIDTHxHEIGHT`;后端会拒绝它不支持的尺寸。已验证:`auto`、`1024x1024`、`1024x1536`、`1536x1024`。更大尺寸(`2048x*`、`3840x*`)原样透传 —— 后端可能接受也可能拒绝,取决于订阅档位。 |
| `--format` | ✅ 生效 | `png` / `jpeg` / `webp` |
| 质量 | ⚠️ 由模型决定 | 脚本不提供 `--quality`,因为订阅路径不支持可靠的质量控制 —— 后端被观察到会自行选 `low` 或 `medium`,并忽略或降级 `high` 请求。需要显式质量控制就用官方 `/v1/images/generations` API + `OPENAI_API_KEY`。 |
| `background: transparent` | ❌ 订阅路径不支持 | 需要走 API-key 路径 + `gpt-image-1.5` |
| 图像编辑(`/v1/images/edits`) | ❌ 暂未暴露 | 需要的话开 issue |
| 速度 | 通常 15–60 秒,大图/细节图偶尔 2–3 分钟 | 全程流式;每个阶段的时间线打到 stderr,能看到它在干活 |

## 并发

两个后端各有独立的跨进程并发上限,因为它们撞的限制不一样:

| 后端 | 默认上限 | 原因 | 调整 |
| --- | --- | --- | --- |
| `web` | **1**(串行) | 驱动同一个登录的 Chrome,**而且** chatgpt.com 页面侧限流很凶("Too many requests… temporarily limited access to your conversations")。 | `CHATGPT_IMAGEGEN_WEB_CONCURRENCY` |
| `codex` | **4** | 独立 HTTP POST;Plus 账号实测 4 并发无 429、总墙钟 ≈ 最慢单张。设上限是防止 agent 大批量 fan-out 触发账号级限流。 | `CHATGPT_IMAGEGEN_CODEX_CONCURRENCY`(`0` = 不限) |

超过上限多 fire 是**安全**的——多出来的进程在 flock 槽位池上排队(等待者打印 "waiting…",且 `--timeout` 预算从拿到槽位才开始计,排队时间不吃预算)。

```bash
# 从 shell 并发跑 4 个(注意 --backend codex):
for p in apple sky tree sun; do
  chatgpt-imagegen "a tiny $p icon, flat vector, white background" \
    -o "icons/$p.png" --backend codex --quiet &
done
wait
```

web 为什么钉在 1:共享 Chrome 上并发曾互相串图([#7](https://github.com/leeguooooo/chatgpt-imagegen/issues/7),v0.6.0 已修),且页面侧本来就压快速突发。如果 chatgpt.com 真把账号限流了,web 后端会识别 "Too many requests" 弹窗并**立刻明确报错**——提交前撞到则 `auto` 模式降级 codex;已提交则干净停下,绝不重复花钱。

注意:订阅额度和 ChatGPT 网页 app、Codex CLI **共享**。别持续狂跑(>10 张/分钟)—— 早晚会撞每日限流。批量需求请用官方 `/v1/images/generations` API + `OPENAI_API_KEY`。

## 什么时候别用这个 —— 改用 API

只要符合下面任一条,这个工具就不合适:

- 你要**真正的 `quality=high`** 或**原生透明背景** —— 两者都需要官方 `/v1/images/generations` API + `OPENAI_API_KEY`。
- 你在做**面向终端用户的生产服务** —— 用个人 ChatGPT 订阅干这个违反 OpenAI 条款,还会烧掉你日常用 ChatGPT 的额度。
- 你需要**可逐次结算、能转嫁给客户的计费** —— API 有,订阅没有。
- 你要**持续 >10 张/分钟** —— 订阅限流比 API 紧。

这些情况直接打 OpenAI 官方接口:

```bash
curl https://api.openai.com/v1/images/generations \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-image-2","prompt":"...","size":"1024x1024"}'
```

## 相关

- **需要 HTTP API?** [**agent-cli-to-api**](https://github.com/leeguooooo/agent-cli-to-api) 把同一个工具暴露成 OpenAI 兼容的 `/v1/chat/completions` 服务 —— 需要可网络调用、多客户端、团队共享时选它。本仓库面向本地 / agent 使用。
- **深入(博客):** [为什么有这个项目 + OAuth/SSE 走读](https://blog.misonote.com/zh/posts/chatgpt-subscription-image-api/) · [可视化速览](https://blog.misonote.com/zh/posts/chatgpt-imagegen-visual-guide/)(中文;英/日文在 `/en/`、`/ja/` 下)。

## 工作原理(技术)

### `web` 后端(默认)

经 `chrome-use` 驱动你登录的浏览器,让出图跑在消费级 ChatGPT 界面上 —— 无头客户端够不着。防线分三层:Cloudflare 边缘和 sentinel 工作量证明(`backend-api/sentinel/chat-requirements` + 页面内 `sentinel/sdk.js` 算 token)裸客户端**都能过**,真正过不了的是 **Cloudflare Turnstile** token —— 这个交互式 token 只能由真浏览器现场产出,且单次有效,没有"取了 token 再 headless"的捷径。流程:

```
chatgpt-imagegen --backend web
   │
   ├── chrome-use open https://chatgpt.com/      (普通对话 —— Temporary Chat 禁用了出图工具)
   ├── 解析 ChatGPT 项目 (--project)              (页面内 fetch:gizmos/snorlax/sidebar 列项目,
   │   并打开 chatgpt.com/g/<g-p-id>/project       没有就 POST /backend-api/projects 创建)
   ├── 用真实键盘输入打提示词                       (ProseMirror/React 输入框不认纯 DOM 的 `fill`)
   ├── 轮询页面:等流结束 且 新的 <img> 资源稳定
   └── 在页面内 fetch 资源字节 (credentials:'include') → base64 → 存盘
       (签名的 estuary/content URL 由浏览器自己的 cookie 授权)
```

token 不出浏览器。每次的对话落在 `imagegen` 项目里(自动创建),不再堆在顶层历史;传 `--project ""` 可退回旧行为。

### `codex` 后端

Codex CLI 内置的 `image_gen` 能力是一个原生 Responses-API 工具:

```jsonc
// Codex CLI 发往 chatgpt.com/backend-api/codex/responses 的请求:
{
  "model": "gpt-5.5",
  "tools": [{"type": "image_generation"}],
  "input": [{"role": "user", "content": [{"type":"input_text","text":"draw a cat"}]}],
  // ...
}
```

服务器回一条 SSE 流,其 `response.output_item.done` 事件携带 `item.type === "image_generation_call"` 负载,其中 `item.result` 是 base64 PNG。`chatgpt-imagegen` 就是这么做的:

```
chatgpt-imagegen
   │
   ├── 读 ~/.codex/auth.json     (OAuth access_token、account_id、refresh_token)
   ├── 读 ~/.codex/version.json  (codex CLI 版本 → 匹配服务器预期;取不低于已知下限)
   │
   └── POST https://chatgpt.com/backend-api/codex/responses
       headers: Authorization、version、originator、session_id 等
       body:    tools: [image_generation]
       │
       └── SSE 流
           ├── response.image_generation_call.in_progress    → "queued"
           ├── response.image_generation_call.generating      → "generating"
           ├── response.image_generation_call.partial_image   → "receiving image (partial N)"
           ├── response.output_item.done  ← item.result = base64 PNG
           └── response.completed
```

OAuth token 过期时,脚本会经 `https://auth.openai.com/oauth/token`(用 `codex login` 已存的 refresh_token)自动刷新,并把新 token 写回 `~/.codex/auth.json`。

## 许可证

MIT —— 见 [LICENSE](./LICENSE)。

## 免责声明

本工具调用的是 ChatGPT 内部的 `backend-api/codex` 接口,也就是官方 Codex CLI 用的同一个接口。它不是有文档的公开 API,OpenAI 随时可能更改或限制。使用风险自负,且须遵守 [OpenAI 使用条款](https://openai.com/policies/row-terms-of-use/) —— 尤其**不要用你的 ChatGPT 订阅去支撑对外公开的图像生成服务**。

---

## 关键词

用 ChatGPT 订阅生成图片、免费 ChatGPT 账号生图、ChatGPT Plus 生图工具、不用 API key 生图、gpt-image-2 用订阅、ChatGPT 订阅生图 CLI、Codex CLI 生图能力独立工具、给 AI agent 用的生图 skill、本地生图脚本、零依赖 Python 生图工具。

**English:** `ChatGPT subscription image generation`, `free ChatGPT account image generation`, `use ChatGPT Plus for image API`, `gpt-image-2 without OPENAI_API_KEY`, `image_generation tool Responses API`, `ChatGPT image CLI`, `Codex CLI image_gen as standalone tool`, `no-API-key image generation`, `AI agent image generation skill`, `Claude Code image skill`.
