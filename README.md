# 拾光学习日志 · Shiguang Learning Journal

把对话中的问题、知识点和解决过程，整理成可以回顾的学习积累。

**拾光学习日志**是一款在本地运行的个人学习记录助手，提供 Windows 桌面应用、浏览器界面和 HTTP API。你可以用自然语言记录学习，也可以直接编辑图文日志、整理 Markdown 文档、收藏以后想学的知识，并根据已有记录回顾自己的进展。

**当前应用版本：v1.4.0** · **数据存储：本地 SQLite 与文件目录** · **界面语言：中文**

[下载桌面版](https://github.com/yeshuangtang-svg/shiguang-learning-journal/releases/latest) · [版本记录](https://github.com/yeshuangtang-svg/shiguang-learning-journal/releases) · [接口规范](source/openapi.json) · [反馈问题](https://github.com/yeshuangtang-svg/shiguang-learning-journal/issues)

## 目录

- [功能介绍](#功能介绍)
- [使用示例](#使用示例)
- [快速开始](#快速开始)
- [模型连接与数据去向](#模型连接与数据去向)
- [资料保存与备份](#资料保存与备份)
- [HTTP API 与工具接入](#http-api-与工具接入)
- [开发构建与测试](#开发构建与测试)
- [常见问题](#常见问题)
- [版本与第三方组件](#版本与第三方组件)

## 功能介绍

### 1. 学习助手：通过对话整理记录

把一次讨论、一道题的解法或刚理解的概念发给助手，即可围绕问题、知识点和收获生成日志。

- **自然语言记录**：从输入内容中整理日期、主题、标题和正文并保存。
- **查找与补充**：查询已有日志，根据明确的修改要求补充或修订记录。
- **阶段复盘**：查询真实日志和统计结果，回顾一周或指定时间段的学习情况。
- **复习建议**：根据近期记录整理薄弱点和下一步学习建议。
- **连续对话**：在当前会话中接着讨论，也可以开启新对话。

应用内助手目前通过工具访问学习日志和统计。文档与知识收藏在各自页面管理；复习计划以对话建议呈现，尚未提供定时提醒。对话功能需要连接模型服务。

### 2. 学习日志：保存问题、理解与解决过程

每条日志包含日期、标题、主题和学习内容，可按需补充思考、下一步和状态。

| 能力 | 使用方式 |
| --- | --- |
| 手动记录 | 点击“手动记一笔”或“记一笔”，无需模型即可保存 |
| 图文编辑 | 使用 Markdown 和格式工具栏添加标题、列表、引用、代码及图片 |
| 图片输入 | 选择文件、粘贴截图或拖入图片 |
| 编辑预览 | 在编辑和预览之间切换，检查正文排版 |
| 检索筛选 | 按关键词、主题和起止日期查找记录 |
| 修改与删除 | 从日志列表进入编辑，删除前进行确认 |

日志记录学习内容，不要求填写或估算学习时长。旧备份的历史时长字段仅用于兼容，界面与统计均不展示时长。

### 3. 文档：管理 Markdown 笔记与 PDF

“文档”页面适合保存较长的知识整理、教程和专题笔记。

- 导入 `.md` / `.markdown` 文件，或直接新建文档。
- 搜索文件名及正文，切换阅读与编辑模式。
- 支持标题、表格、任务清单、代码块、引用和图片等 Markdown 内容。
- 支持插入、粘贴和拖入图片，单份 Markdown 上限为 **2 MiB**，采用 UTF-8 编码。
- 下载 Markdown，或使用“MD 文件原位置”定位应用归档的源文件。
- 已关联 PDF 的文档可通过“打开 PDF”交给系统阅读器查看。

源文件与同名 PDF 归档在 `data/documents/<文档id>/`，内嵌的本地插图整理到旁边的 `assets/`。源文件更新后，应用保留被替换文件的历史版本，并标记 PDF 是否对应当前内容。

**PDF 制作流程**：保存 Markdown → 获取归档路径与源文件哈希 → 使用外部工具生成 PDF → 通过 API 关联 PDF。当前应用负责归档、版本核对和打开文件，编辑后不会自动重新生成 PDF；单份上传的 PDF 上限为 **8 MiB**。

### 4. 图片：放大查看与统一清单

日志和文档中的图片可以点击放大，支持滚轮缩放、按钮缩放、100% 原图、适应窗口和放大后拖动。按 Esc、点击关闭按钮或空白区域可退出。

文档页的“查看图片”入口提供独立的图片清单：

- 搜索图片名称，查看缩略图和大图。
- 使用系统阅读器打开图片，或在资源管理器中定位副本。
- 整理数据库插图以及 `data/images/`、`data/documents/` 中的图片。
- 按图片内容去重，同时保留各个副本的位置。

支持 **PNG、JPEG、GIF、WebP**，单张上限为 **8 MiB**。图片清单会在打开或刷新时重新整理，文件历史目录不参与清单扫描。

### 5. 未来学习知识：先收藏，再学习

看到想学的文章、课程或概念时，可以先保存标题，再按需补充主题、资料链接和备注。

支持搜索、编辑、删除与状态筛选，并在以下状态之间切换：

**待学习 → 学习中 → 已学完**

收藏独立保存，不计入学习日志篇数。当前的“标记学完”更新收藏状态，学习成果可以另行写入日志或文档。

### 6. 学习概览：查看积累与主题分布

概览展示日志总篇数、有记录的日数、探索的主题、近期记录趋势和主题分布。点击“让拾光帮我复盘”，可进入对话，结合已有记录总结进步、薄弱点和复习方向。

### 7. 本地应用与工具接入

- **Windows 独立窗口**：直接运行 EXE，使用 WebView2 展示应用界面。
- **单实例运行**：重复启动会唤起已有窗口；关闭窗口后停止该实例的本机服务。
- **自动选择端口**：桌面版遇到默认端口被占用时，会选择可用端口。
- **结构化 API**：脚本或其他助手可以直接创建、查询和更新日志，也能管理文档、收藏和图片。
- **JSON 导入导出**：在连接设置中备份或恢复库内学习资料。

## 使用示例

以下是可以发给应用内助手的示例请求：

> 帮我记录这次关于 Python 列表推导式的讨论：我理解了基本语法，但嵌套循环的执行顺序还需要再练习。

> 查找最近两周关于模型训练的日志，帮我回顾混合精度和梯度累积的区别。

> 在刚才那条学习记录里补充：梯度累积可以增大有效批量，但不会减少模型参数本身占用的显存。

> 根据本周的学习记录，整理已经理解的内容和还需要复习的问题。

日常可以先用收藏留住兴趣，用日志记下一次学习中的关键发现，再把完整的专题整理收入文档。需要回顾时，使用日志筛选和对话复盘找到线索。

## 快速开始

### Windows 桌面版

1. 前往 [Releases](https://github.com/yeshuangtang-svg/shiguang-learning-journal/releases/latest) 下载 Windows x64 EXE。
2. 将程序放在有写入权限的文件夹中，双击启动。
3. 点击“手动记一笔”开始记录；需要对话时，在“连接设置”中配置模型。

运行环境为 **Windows 10/11 64 位**，需要 **Microsoft Edge WebView2 Runtime**，无需安装 Python。当前版本的程序文件名为 `Shiguang-Learning-Journal-v1.4.0-windows-x64.exe`，应用界面名称为“拾光学习日志”。

桌面程序将个人数据保存在 EXE 旁的 `data/` 中。更新程序时关闭旧版本、保留该目录，并替换 EXE。

### 从源码启动 Web 服务

Web 服务使用 **Python 3.10+** 标准库：

```powershell
git clone https://github.com/yeshuangtang-svg/shiguang-learning-journal.git
cd shiguang-learning-journal/source
python server.py
```

在浏览器中打开 `http://127.0.0.1:8787`。源码 Web 模式默认使用 `source/data/`，按 Ctrl+C 停止服务。

可指定端口和数据目录：

```powershell
python server.py --port 8790 --data-dir ./data
```

## 模型连接与数据去向

在“连接设置”中填写以下配置：

| 配置 | 含义 |
| --- | --- |
| Base URL | 模型服务的 API 根地址，不包含 `/chat/completions` |
| 模型名称 | 服务提供的模型标识 |
| API Key | 访问模型服务所需的密钥 |

模型服务需要支持 **Chat Completions tools**。也可以将 [source/.env.example](source/.env.example) 复制为 `source/.env`，按示例填写环境变量；环境变量与 `.env` 配置优先于界面保存的模型配置。

手动记录、文档管理、收藏、搜索和统计均可在未配置模型时使用。使用 AI 对话时，消息及工具查询到的相关日志会发送给所配置的模型服务商。界面保存的模型密钥位于本机 `data/config.json`，为明文配置，读取配置的 API 不返回密钥。

## 资料保存与备份

### 数据目录

```text
data/
├── study.sqlite3        # 日志、聊天历史、文档、收藏及库内插图
├── config.json         # 本机模型配置
├── runtime.json        # 桌面实例的运行状态与 API 地址
├── documents/          # Markdown 源文件、PDF、配图和文件历史
└── images/             # 图片导出副本与重建的图片清单
```

该结构列出主要资料路径，应用可能另建界面运行所需的目录。桌面版以 EXE 所在目录为基准，源码 Web 模式以启动参数指定的数据目录为准。

### 选择合适的备份方式

| 方式 | 包含内容 | 适用场景 |
| --- | --- | --- |
| 应用内 JSON 导出 | 日志、库内插图、Markdown 文档、未来学习知识 | 合并或恢复库内学习资料 |
| 关闭应用后复制整个 `data/` | 数据库、聊天、配置、PDF、文件历史及其他本地资料 | 完整备份、迁移个人工作环境 |
| GitHub 仓库和 Release | 源码、构建配置、测试、前端资源及桌面程序 | 应用版本管理与程序下载 |

JSON 备份不包含聊天历史、密钥配置、PDF 和文件历史。导入按编号合并：相同编号的记录会被备份覆盖，其他记录保留。包含未来学习知识的版本 3 备份需要 1.3 或更新的应用恢复。

本仓库通过 `.gitignore` 排除个人学习记录、文档、数据库、备份、密钥和运行数据。复制整个 `data/` 做备份时，它也会包含本机配置，应自行妥善保存。

## HTTP API 与工具接入

应用运行后，可以访问 `/api/docs` 查看接口说明，访问 `/api/openapi.json` 读取结构规范。桌面版每次连接应先读取 `data/runtime.json` 中的 `api_url`，因为端口可能变化。

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 查看服务状态 |
| `POST /api/chat` | 发起助手对话，执行模型工具调用 |
| `GET /api/sessions/{id}` | 读取指定会话历史 |
| `GET/POST /api/entries` | 查询或新增日志 |
| `GET/PATCH/DELETE /api/entries/{id}` | 读取、修改或删除指定日志 |
| `GET /api/summary` | 获取日志篇数、记录日数和主题分布 |
| `GET/POST /api/documents` | 查询或新建 Markdown 文档 |
| `GET/PATCH/DELETE /api/documents/{id}` | 读取、修改或删除文档 |
| `GET /api/documents/{id}/files` | 获取源文件路径、哈希及 PDF 状态 |
| `POST /api/documents/{id}/pdf` | 上传与当前源文件对应的 PDF |
| `GET/POST /api/future-learning` | 查询或创建知识收藏 |
| `GET/PATCH/DELETE /api/future-learning/{id}` | 管理指定收藏 |
| `GET /api/images` | 整理并返回图片清单 |
| `GET /api/export`、`POST /api/import` | 导出或导入 JSON 备份 |

直接使用结构化日志 API 无需调用模型。下面的 PowerShell 示例读取桌面版运行地址，并获取当天日志；在应用目录中执行：

```powershell
$runtime = Get-Content -Raw -Encoding UTF8 './data/runtime.json' | ConvertFrom-Json
$api = [uri]$runtime.api_url
if (-not $api.IsLoopback) { throw '只连接本机回环地址' }
$today = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'China Standard Time').ToString('yyyy-MM-dd')
Invoke-RestMethod "$($api.AbsoluteUri.TrimEnd('/'))/api/entries?date_from=$today&date_to=$today"
```

启用 `AGENT_API_TOKEN` 后，调用需附带 `Authorization: Bearer <token>`。它与模型 API Key 是两种独立配置。`POST /api/chat` 支持 `request_id` 去重；重试同一个请求时沿用原 ID 与原请求内容。

日志新增必填 `date`、`title`、`subject`、`content`，日期格式为 `YYYY-MM-DD`，新日志不传 `minutes`。更多请求示例见 [源码说明](source/README.md)。

## 开发构建与测试

### 项目结构

```text
source/
├── desktop.py              # Windows 窗口、单实例与服务生命周期
├── server.py               # HTTP API、模型连接和工具循环
├── store.py                # SQLite 日志、统计和备份
├── library.py              # Markdown 文档与插图存储
├── document_files.py       # MD/PDF 文件归档与版本核对
├── future.py               # 未来学习知识收藏
├── image_catalog.py        # 图片清单与文件定位
├── static/                 # HTML、CSS、JavaScript 和离线前端依赖
├── assets/                 # 应用图标
├── tests/                  # 后端、生命周期和界面检查
├── openapi.json            # 接口规范
├── requirements-desktop.txt # 桌面构建依赖
└── build-desktop.ps1        # Windows 打包脚本
```

### 构建 Windows 桌面版

建议使用 Python 3.12 独立环境，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r source/requirements-desktop.txt
$env:PATH = "$((Resolve-Path .venv/Scripts).Path);$env:PATH"
powershell -ExecutionPolicy Bypass -File .\source\build-desktop.ps1
```

产物为 `source/拾光学习日志.exe`。打包包含界面资源、接口规范和图标，个人数据由运行时单独创建。

### 运行检查

从仓库根目录运行：

```powershell
python -m unittest discover -s source/tests -p "test_*.py"
```

测试使用临时数据库及本机模拟服务。覆盖日志读写、无时长记录、旧库兼容、备份导入、模型工具调用、请求去重、图片与文档管理，以及桌面服务生命周期。

浏览器渲染与图片交互测试默认跳过。安装 Playwright 并确保 Microsoft Edge 可用后，可显式启用：

```powershell
python -m pip install playwright
$env:RUN_BROWSER_TESTS = '1'
python -m unittest discover -s source/tests -p "test_*.py"
Remove-Item Env:RUN_BROWSER_TESTS
```

独立的 `qa_*.py` 界面检查另外使用 Pillow 和 Playwright Chromium。首次归档 v1.4.0 时，默认测试共 59 项，其中 42 项通过，17 项浏览器检查跳过。

## 常见问题

**没有模型 API Key，可以使用吗？**

可以。手动日志、文档、图片、收藏、搜索、统计和备份均可使用；AI 对话需要连接兼容的模型服务。

**保存 Markdown 后，PDF 为什么还是旧内容？**

Markdown 保存与 PDF 制作是两个步骤。修改源文件后，需要重新生成并提交 PDF，应用会核对它是否对应当前源文件。

**导入 Markdown 后，相对路径图片为什么没有显示？**

单个 Markdown 导入不会扫描原文件旁的图片目录。通过“插入图片”加入配图，或使用应用的 JSON 备份迁移库内文档与插图。

**换电脑时，怎样完整迁移？**

关闭应用后，一并复制 EXE 和整个 `data/`，并确保新电脑具备 WebView2 Runtime。只下载程序会创建新的空白数据目录。

**它会自动读取其他聊天软件的学习内容吗？**

学习内容来自手动输入、导入或经过授权的 API 写入。外部助手可以调用接口整理指定内容，应用本身不自动收集其他软件的聊天。

## 版本与第三方组件

`v1.4.0` 是首次纳入 Git 的现有应用基线，包含图文日志、文档与 PDF 归档、知识收藏和图片清单。仓库更名为 `shiguang-learning-journal` 后，后续代码和说明更新继续使用 Git 提交管理；已发布的版本标签保留原有代码快照。

前端 Markdown 解析与内容过滤使用随应用提供的 marked 和 DOMPurify。组件版本及许可证见 [source/static/vendor](source/static/vendor)。
