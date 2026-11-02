# 拾光学习日志 · Shiguang Learning Journal

一个可以通过自然语言管理学习日志的个人 Agent，同时提供浏览器界面和 HTTP API。Python 3.10+ 即可运行，无需安装第三方依赖。

当前版本为 **v1.5.0**，完整功能介绍、安装步骤与备份说明见[仓库主页](../README.md)。

## v1.5 工作区升级

统一搜索 `/api/search` 和原文读取工具覆盖日志、文档与收藏；`workspace.py` 管理双向关联、持久化草稿、回收站和阅读位置。`/api/entries-page` 返回分页摘要；完整 ZIP 备份由 `backups.py` 管理，恢复前校验、预览并自动保存当前资料。文档页增加目录、历史版本和一键 PDF（需要本机 Edge）。详细操作与备份范围以[根目录 README](../README.md)为准。

## Windows 桌面版

1.3.1：文档页面右上方新增「打开 PDF」和「MD 文件原位置」。选中文档后可用系统阅读器打开 PDF，或在资源管理器中选中 MD。源文件与同名 PDF 统一归档在 `data/documents/<文档id>/`；库内图片会复制为源文件旁的相对路径资源。保存文档会更新源文件，旧文件保留在 `历史版本/`，PDF 需要重新生成后归档。原导入位置不受影响，定位按钮指向应用管理的源文件。

制作流程：创建/更新文档 → `GET /api/documents/{id}/files` 获取路径和 `source_sha256` → 用源文件生成并检查 PDF → `POST /api/documents/{id}/pdf` 上传 `{data_base64, source_sha256}`，PDF 最多 8 MiB。`GET .../files` 返回 `pdf_exists` 和 `pdf_current`；源文件更新后会提示 PDF 可能未更新。`POST .../open-pdf`、`POST .../reveal-md` 接收空 JSON，仅 Windows 桌面版可打开本机文件，不接受任意路径。

**PDF 备份**：JSON 备份仍包含库内文档和插图，不包含 PDF 与文件历史。迁移 PDF 请复制整个 `data/`。删除库内文档不会删除已归档的文件；原有文件保留在该 id 目录中。


1.3 新增「未来学习知识」：先收藏暂时没精力学习的知识点，支持标题、主题、资料链接和备注，以及待学习、学习中、已学完三种状态。支持搜索、编辑、删除与状态筛选，独立保存在本地，不计入学习日志统计。原侧栏「Markdown 文件」更名为「文档」，仍支持 Markdown 笔记。

含未来学习知识的完整备份使用版本 3，需用 1.3 或更新版本恢复；旧版 1/2 备份仍可导入，不会清空已有收藏。接口为 `GET/POST /api/future-learning` 和 `GET/PATCH/DELETE /api/future-learning/{id}`。


1.2.1 新增图片放大查看：点击 Markdown 文件、日志正文或编辑预览中的图片即可打开大图。可使用放大/缩小按钮、滚轮缩放、100% 原图和适应窗口；放大后拖动查看细节。点击空白处、关闭按钮或按 Esc 退出，日志编辑内容会保留。

### 1.2 图文记录与 Markdown 文件库

「记一笔」的正文支持 Markdown 格式，可用工具栏插入标题、粗体、列表、引用、代码与图片，并切换到预览。图片可以选择文件、粘贴截图或拖入编辑区；PNG、JPEG、GIF、WebP 单张不超过 8 MiB，上传后保存在本地数据库，原图片移动后仍可显示。原来的普通文字日志继续保留，列表会呈现排版与图片。

侧栏新增「Markdown 文件库」：导入 `.md` / `.markdown` 文件、新建笔记、搜索、预览、编辑保存和下载。文档使用 UTF-8，单份不超过 2 MiB；导入保存的是一份独立副本，不会修改外部原文件。Markdown 中的外部图片需要联网；相对路径图片请通过「插入图片」重新加入，导入单个文件不会扫描电脑上的图片目录。

Markdown 支持标题、段落、列表、引用、表格、任务清单、代码块和图片。原生 HTML 仅作为文字显示，不执行脚本。解析与过滤组件随 EXE 离线提供，许可证位于 `static/vendor/`。

导出备份会包含图片与 Markdown 文档；有这些内容时使用版本 2，须在 1.2 或更新的应用导入。旧版日志备份仍可导入。单独下载的 `.md` 文件保留 Markdown 源码，内部图片引用仍指向本应用；迁移含图笔记请使用完整 JSON 备份，或关闭应用后复制整个 `data/`。

双击同目录的 `拾光学习日志.exe` 即可打开独立窗口，无需安装 Python。桌面版沿用同目录 `data/` 中的日志与配置，关闭窗口会停止自有本地服务。重复双击会唤起现有窗口。

可把 EXE 与 `data/` 一起移动到其他可写目录；只复制 EXE 会从空白日志开始。便携 ZIP 不含个人日志或密钥。运行需要 Windows 10/11 64 位和 Microsoft Edge WebView2 Runtime（本机已检测到）。

当前 API 地址在连接设置页显示；8787 被其他程序占用时会自动选择空闲端口。接口只在应用运行时可用。

从源码重新打包：建立 Python 3.12 独立环境，安装 `requirements-desktop.txt`，运行 `build-desktop.ps1`。入口是 `desktop.py`，图标和版本信息位于 `assets/app.ico`、`desktop-version.txt`。

## 源码启动

Windows 双击 `start.cmd`，或在此目录执行：

```powershell
python server.py
```

打开 <http://127.0.0.1:8787>。进入「API 设置」，填写模型服务的 **Base URL、模型名称、API Key**。Base URL 是 API 根地址，不要包含 `/chat/completions`，例如 `https://api.openai.com/v1`。模型必须支持 OpenAI 风格的 Chat Completions `tools` 工具调用；其他兼容服务可填其根地址和模型名。本机模型允许 `http://localhost:端口/v1`，不需要密钥的服务可以留空。

也可以复制 `.env.example` 为 `.env` 后填写，重启服务生效。环境变量及 `.env` 优先于网页配置。没有模型配置时，手动新增、修改、搜索、统计和备份仍可使用。

## 和它聊什么

- “把我们刚才关于 Python 列表推导式的讨论整理成学习日志，记下嵌套循环还没弄清的部分。”
- “昨天练习了英语听力，理解了连读规则，帮我补一篇。”
- “这周讨论了哪些知识点？有哪些问题还没解决？”
- “帮我在刚才那篇日志里补上这个例子和结论。”
- “根据这周记录的困难，帮我安排明天的复习。”

Agent 会自行选择保存、查询、修改或统计工具，按问题、知识点、解决过程、收获和下一步整理对话。无需填写或估算学习时长、记录时长；只在学习内容本身不明确时追问。日志删除由列表中的显式操作完成。模型只提供复习建议，不运行提醒或定时任务。

## 接入自己的应用

在线接口说明：<http://127.0.0.1:8787/api/docs>；OpenAPI：<http://127.0.0.1:8787/api/openapi.json>。

最小 Python 调用：

```python
import json
import uuid
from urllib.request import Request, urlopen

payload = {
    "message": "今天理解了主动回忆法，帮我记录它与重复阅读的区别和应用方法。",
    "request_id": str(uuid.uuid4()),
    # 后续消息传入上一次返回的 session_id，以继续对话。
    # "session_id": "...",
}
request = Request(
    "http://127.0.0.1:8787/api/chat",
    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=300) as response:
    result = json.load(response)
print(result["reply"])
print(result["session_id"])
print(result["actions"])  # 实际执行的工具及结果
```

网络重试时使用**同一个 request_id 和同一份请求内容**，新问题使用新的编号，避免重复写入。`actions` 是实际执行结果，`warnings` 说明后续整理失败等情况。模型在日志保存后连接失败时，服务仍会返回已保存的记录，避免把写入成功误报为失败。

| 接口 | 用途 |
|---|---|
| `POST /api/chat` | 对话与工具调用，返回 `reply/session_id/actions/warnings` |
| `GET /api/sessions/{id}` | 读取可显示的聊天历史 |
| `GET /api/entries` | 日志检索：`date_from/date_to/subject/query/limit` |
| `POST /api/entries` | 手动新增日志 |
| `GET/PATCH/DELETE /api/entries/{id}` | 读取、部分更新、删除日志 |
| `GET /api/summary` | 统计，可按起止日期筛选 |
| `GET /api/export` | 导出日志、插图、Markdown 文档与知识收藏 JSON |
| `POST /api/import` | 原子合并备份；同编号覆盖，其余保留 |
| `GET/POST /api/config` | 读取脱敏配置、设置模型；不返回密钥 |
| `GET /api/health` | 服务及配置状态 |

手动新增日志的必填字段为 `date/title/subject/content`。日期使用 `YYYY-MM-DD`；`reflection/next/mood` 选填。心情为 `great/good/okay/tired`。新日志不传 `minutes`，保存为空；旧记录和备份中的历史时长仅为兼容保留，不展示、不用于统计。概览按日志篇数、主题和有记录的天数汇总。查询日期范围包含首尾；Agent 的“今天”和“本周”按 Asia/Shanghai 解释。列表默认最多100条，可设置 `limit`（上限10000）；统计与备份覆盖全部记录。

## 数据与密钥

- 日志与聊天历史保存到 `data/study.sqlite3`；重启、刷新页面都不会丢失，清理浏览器缓存不删除这些日志。
- 网页填写的模型密钥保存在本机 `data/config.json`，不会通过配置读取接口返回。此文件是本地明文配置，应保留在自己的设备上；也可用环境变量提供密钥。
- 聊天消息及为回答问题检索到的日志会发送到你选定的模型服务。手动记录不调用模型。
- JSON 导出包含学习日志、库内插图、Markdown 文档与未来学习知识，不包含密钥、聊天历史、PDF 及文件历史。完整迁移可先停止服务，再复制 `data/` 目录；分享源码时不要包含 `data/` 和 `.env`。
- 默认只监听本机。若其他本机程序需要鉴权，可设置 `AGENT_API_TOKEN`，调用时发送 `Authorization: Bearer <token>`。这个令牌与模型服务的 API Key 不同。
- 局域网访问须主动配置 `AGENT_HOST=0.0.0.0`、至少24字符的 `AGENT_API_TOKEN` 和 `AGENT_ALLOWED_HOSTS=你的局域网IP`。这是单用户服务；公开互联网部署需要额外的 HTTPS、用户隔离和运维措施。

## 实现与验证

`server.py` 提供 HTTP API、会话记忆和工具循环；`store.py` 管理 SQLite；`static/` 是交互界面。每轮最多6次模型调用、每次最多12个工具调用，保留最近12轮且限制历史长度，以控制上下文。

已验证 SQLite 持久化、日期校验、原子导入、HTTP CRUD、鉴权、工具调用、请求去重和模型失败后的保存结果。真实模型的表现取决于所配置服务；交付时未使用你的真实 API Key 发起付费调用。

复跑测试：`python -m unittest discover -s tests -v`。使用临时数据库和本机模拟模型，不修改真实日志、不调用外部模型。测试覆盖无时长记录、旧库迁移、导入导出、端口冲突、单实例、关闭服务与数据持久化。

工具消息结构依据 [OpenAI Function calling 文档](https://developers.openai.com/api/docs/guides/function-calling) 与 [Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 实现。

## 图片清单

文档页右上角“查看图片”打开图片清单，支持搜索、缩略图放大、系统打开及定位每个副本。每次打开或刷新时整理数据库插图和 `data/images/`、`data/documents/` 中的 PNG/JPEG/GIF/WebP（最大 8 MiB），排除历史版本及目录链接，按内容去重。数据库插图导出到 `data/images/`，名称与全部路径保存在 `data/images/图片清单.json`；清单自动重建，不要手动填写任意外部路径。完整备份时复制整个 data 目录。

`GET /api/images` 刷新清单；`GET /api/images/{id}/content` 读取图片；`POST /api/images/{id}/open` 与 `/reveal` 接收 `{}` 或 `{ "location": 0 }`，按 paths 数组下标选择副本，使用与其他接口相同的认证。
