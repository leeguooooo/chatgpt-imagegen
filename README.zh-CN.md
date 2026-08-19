# chatgpt-imagegen

[![CI](https://github.com/leeguooooo/chatgpt-imagegen/actions/workflows/ci.yml/badge.svg)](https://github.com/leeguooooo/chatgpt-imagegen/actions/workflows/ci.yml)

[English](./README.md) | **中文**

**用你的 ChatGPT 订阅生图 —— 不需要 `OPENAI_API_KEY`。**

一个零依赖的单文件 Python 命令行工具(也是 AI-agent skill),纯 stdlib。**免费 ChatGPT 账号也能用**——默认后端就是驱动普通的 ChatGPT 网页对话,免费档也能生图。

```bash
chatgpt-imagegen "一只坐在窗台的水彩橘猫" -o cat.png
# -> saved: cat.png  (812,344 bytes)  size=1024x1024  quality=medium
```

<img width="1494" height="870" alt="image" src="https://github.com/user-attachments/assets/b48b0563-58a3-41ff-a207-f01eafbf2ccb" />

---

## 安装

需要 Python 3.10+ 和一个 ChatGPT 订阅(免费档也行)。

**给 AI agent 用(推荐)**——把 skill 装进 Claude Code、Codex、Cursor 等:

```bash
npx skills add leeguooooo/chatgpt-imagegen -g
```

然后直接说:*"画一张 …"*。

**独立命令行**——不用 `pip`、不用虚拟环境:

```bash
git clone https://github.com/leeguooooo/chatgpt-imagegen
sudo install chatgpt-imagegen/chatgpt-imagegen /usr/local/bin/chatgpt-imagegen
```

还需要**一个后端**——`web`(默认,驱动你登录着的 Chrome,不花 Codex 用量)或 `codex`(无头兜底)。`chatgpt-imagegen doctor` 看哪个就绪。→ **[后端与排错](https://drawstyle.leeguoo.com/zh/docs/backends)**

也有 **Gemini** 订阅?还有两个走 Google 账号的后端:`--backend gemini`(驱动登录着 `gemini.google.com` 的 Chrome)和 `--backend agy`(Antigravity CLI,无头)。两者**额度互相独立**,一个用完另一个还能顶上。它们都不会被自动选中,得点名使用。用 `--gemini-profile` 指定有订阅的那个 Chrome profile——因为几乎每个 profile 都登录着*某个* Google 账号,自动探测分不出来。另外注意:Gemini 的**文生图**结果右下角带可见水印(图生图没有);`--size` 在这条路上控制的是画面比例,不是精确像素数。

## 升级

```bash
chatgpt-imagegen update
```

它会替你调用 `skills` 管理器——PATH 上有 `skills` 就直接用,没有则走 `npx`(通常都没有)。另外 CLI 每天最多提醒你一次有新版,并列出你那版之后改了什么;`CHATGPT_IMAGEGEN_NO_UPDATE_CHECK=1` 可以关掉。

**还停在 0.23.1 或更早?** 那时的自升级只找全局 `skills`,找不到就放弃,所以它没法把这个修复本身装进来。先手动破一次局:

```bash
npx -y skills update chatgpt-imagegen
```

之后 `chatgpt-imagegen update` 就能自己跑了。

## 用法

```bash
chatgpt-imagegen "阴郁的山间日落" -o web/hero.png --size 1536x1024
chatgpt-imagegen "改成暖调黄昏、电影感 35mm" -i photo.jpg          # 以参考图为主体
chatgpt-imagegen "换成另一个虚构的人" --composition-ref photo.jpg  # 只借构图,不复刻人脸
chatgpt-imagegen "一个机器人吉祥物" --style doodle                  # 套用画廊风格(本地没有会自动拉取并保存)
chatgpt-imagegen animate "小狗开心地摇尾巴" --style-online snoopy --also-gif
OUT=$(chatgpt-imagegen "icon" --quiet)                             # 只拿路径(便于管道)
```

下面三张都是上面这些命令直接出的图,没有后期修饰:

<table>
<tr>
<td width="33%"><img src="./docs/gallery/watercolor-cat.png" alt="窗台上的水彩猫"></td>
<td width="33%"><img src="./docs/gallery/mountain-sunset.png" alt="阴郁的山间日落"></td>
<td width="33%"><img src="./docs/gallery/coffee-logo.png" alt="咖啡店 logo"></td>
</tr>
<tr>
<td><sub><code>"一只坐在窗台的水彩橘猫"</code></sub></td>
<td><sub><code>"阴郁的山间日落" --size 1536x1024</code></sub></td>
<td><sub><code>"一个咖啡店 logo,圆形徽章"</code></sub></td>
</tr>
</table>

`animate` 会让模型生成严格的 4×2 雪碧图,等分裁出 8 帧,检测明显的主体漂移,
再编码成平滑的往返循环。默认输出动态 WebP;需要 GIF 时使用
`--animation-format gif` 或 `--also-gif`。原始雪碧图 PNG 会始终保存在动图旁边。
动画后处理需要 [ImageMagick](https://imagemagick.org/)(`magick`);输出 WebP
还需要 [libwebp](https://developers.google.com/speed/webp/download)(`img2webp`)。
`chatgpt-imagegen doctor` 会检查两者是否就绪。

完整参数:`chatgpt-imagegen --help`。→ **[生成图片](https://drawstyle.leeguoo.com/zh/docs/generate)** · **[风格系统](https://drawstyle.leeguoo.com/zh/docs/styles)**

## 社区风格

浏览、复用别人调好的画风——公共画廊在 **[drawstyle.leeguoo.com](https://drawstyle.leeguoo.com)**,不用更新脚本:

```bash
chatgpt-imagegen "一只狐狸咖啡师" --style-online doodle  # 直接用画廊风格生图,本地不落盘
chatgpt-imagegen style search "水彩 吉祥物"              # 搜索画廊
chatgpt-imagegen style publish mystyle --category cute --from-last   # 分享你的(需一次登录)
```

风格不只能固定画风,还能**固定角色**。风格资产可以绑参考图,同一个角色能在全新场景里复现:

```bash
chatgpt-imagegen style add pip --kind character --ref pip-ref.png
chatgpt-imagegen "一只狐狸咖啡师" --style pip
```

<table>
<tr>
<td width="50%"><img src="./docs/gallery/pip-ref.png" alt="小狐狸 Pip —— 角色参考图"></td>
<td width="50%"><img src="./docs/gallery/pip-cafe.png" alt="小狐狸 Pip 在咖啡馆场景中重绘"></td>
</tr>
<tr>
<td align="center"><sub>绑定的参考图</sub></td>
<td align="center"><sub>用 <code>"一只狐狸咖啡师"</code> 生成</sub></td>
</tr>
</table>

画廊里的包也可以是角色包——`xiaohei` 就是。

→ **[用画廊的风格](https://drawstyle.leeguoo.com/zh/docs/community)** · **[投稿与审核](https://drawstyle.leeguoo.com/zh/docs/submit)**

## 了解更多

- 📖 **[完整文档](https://drawstyle.leeguoo.com/zh/docs)** —— 安装、生图、风格、后端、平台。
- 🎨 **[画风画廊](https://drawstyle.leeguoo.com)** —— 浏览与投稿社区画风。
- 📝 **[博客深入](https://blog.leeguoo.com/zh/posts/chatgpt-imagegen/)** —— 背后的设计与原理。
- ⚙️ **[工作原理](./docs/how-it-works.zh-CN.md)** · **[HTTP API 封装](https://github.com/leeguooooo/agent-cli-to-api)**

## 许可

MIT —— 见 [LICENSE](./LICENSE)。

## 免责声明

本工具调用 ChatGPT 内部的 `backend-api/codex` 接口——和官方 Codex CLI 用的是同一个。它不是有文档的公开 API,OpenAI 随时可能更改或限制。请自担风险,并遵守 [OpenAI 使用条款](https://openai.com/policies/row-terms-of-use/)——尤其**不要用你的 ChatGPT 订阅去支撑一个对外公开的生图服务**。

<details>
<summary>关键词</summary>

用 ChatGPT 订阅生成图片、免费 ChatGPT 账号生图、ChatGPT Plus 生图工具、不用 API key 生图、gpt-image-2 用订阅、ChatGPT 订阅生图 CLI、Codex CLI 生图能力独立工具、给 AI agent 用的生图 skill、本地生图脚本、零依赖 Python 生图工具。
</details>
