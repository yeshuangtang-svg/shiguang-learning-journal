# 拾光学习日志

本地运行的学习记录助手，提供 Windows 桌面界面、浏览器界面和 HTTP API。
当前代码基线为 **v1.4.0**。

## 功能

- 用自然语言整理学习日志，支持手动记录、搜索、编辑和阶段复盘。
- 图文日志与 Markdown 文档库，支持粘贴图片、预览和图片缩放。
- 文档源文件与 PDF 归档、版本状态检查，以及系统阅读器和文件位置入口。
- 未来学习知识收藏，支持待学习、学习中、已学完状态。
- 图片清单、图片查看和文件定位。
- 本地数据存储、JSON 导入导出和结构化 Agent API。

学习概览按日志、主题和记录日期统计，不统计学习时长。
手动记录和结构化日志 API 无需配置模型；对话式助手需要兼容 Chat Completions tools 的模型服务。

## 运行

### Windows 桌面版

从仓库 Releases 下载 `Shiguang-Study-Journal-v1.4.0-windows-x64.exe`，放入可写目录后运行。
需要 Windows 10/11 64 位和 Microsoft Edge WebView2 Runtime。
程序会在 EXE 旁创建 `data/` 保存个人数据。

### 从源码启动

Web 服务使用 Python 3.10+ 标准库：

```powershell
cd source
python server.py
```

默认访问 `http://127.0.0.1:8787`。模型配置可在应用内填写，或参考 `source/.env.example`。
桌面版端口可能自动调整，实际 API 地址以其数据目录中的 `runtime.json` 为准。

## 构建与测试

建议使用 Python 3.12 独立环境构建 Windows 桌面版：

```powershell
cd source
python -m pip install -r requirements-desktop.txt
powershell -ExecutionPolicy Bypass -File .\build-desktop.ps1
```

构建结果位于 `source/拾光学习日志.exe`。构建不包含个人数据。

运行现有自动化检查：

```powershell
python -m unittest discover -s source/tests -p "test_*.py"
```

浏览器渲染检查需要 Playwright 及其 Chromium 浏览器；独立的 `qa_*.py` 界面检查还使用 Pillow。
详细功能与 API 说明见 [source/README.md](source/README.md)，接口规范见 [source/openapi.json](source/openapi.json)。

## 版本与个人数据

本仓库管理应用源码、测试、静态资源和构建配置。可执行程序通过 Releases 保存。
`v1.4.0` 标记首次纳入 Git 的现有版本，后续变更使用独立提交和版本标签。

本地学习日志、聊天历史、收藏、文档、PDF、图片资料、数据库、备份、API Key 和运行配置均不上传。
根目录采用允许列表，个人文件及生成目录默认忽略；本机 `AGENTS.md` 也保留在本地。
代码仓库不能替代个人资料备份：迁移完整资料时，关闭应用后自行备份整个 `data/` 目录。
JSON 备份不包含 PDF 和文件历史。

第三方前端组件的说明与许可证位于 [source/static/vendor](source/static/vendor)。
