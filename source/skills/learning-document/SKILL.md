---
name: learning-document
description: 学习文档：当用户要求生成、整理、保存或修改 Markdown、MD、PDF、教程或学习说明文档时使用；将源文件与 PDF 归档到拾光文档库。
---

# 学习文档

1. 从当前对话确定主题、读者与交付范围。用户已给出主题就直接推进；缺少实质内容才简短追问。用户最新要求优先。
2. 涉及历史材料或修订时，用 search_knowledge 查找，再用 read_knowledge 分页读完相关部分。只能引用实际读取的资料，不声称能读取其他聊天或联网查证。
3. 修订同一文档优先沿用原 id。先用 document_files 获取 source_sha256，再阅读原文；有多个无法区分的候选时才询问。保留未要求删掉的正文、插图和来源，不用摘要替换全文。
4. 写中文 Markdown：具体标题、简短导读、自然章节、必要的公式与例子。先说清过程和结论，删掉无用的免责声明、反复铺垫和空泛总结。保留真实适用条件、证据边界与未知项。技术讲解同时加载 visual-explanation。
5. 用 create_document 写入完整 Markdown；修订用 update_document，传入读取前取得的 expected_source_sha256。冲突时重新读取并合并，禁止直接用新 hash 覆盖。工具完成后文件才算保存，聊天中的代码块不算交付。
6. 默认调用 generate_document_pdf，同时交付同名 MD 与 PDF。用户明确只要 MD 时不生成 PDF。生成失败则说明 MD 已保存、PDF 未完成及工具返回的原因；不重复创建文档。
7. 用 document_files 回读，核对 md_path、pdf_exists、pdf_current；只确认实际成功的文件。返回工具给出的文档链接，说明可在文档页使用“打开 PDF”“MD 文件原位置”。不要伪造下载地址。

图像使用绘图工具返回的 markdown 插入正文，归档时会复制到 assets。技术内容按 visual-explanation 选择架构、矩阵、张量、流程或数据图；图文并茂应围绕重点安排全局与局部图，而不是在文末堆图片。不要编造图片路径或使用未实际生成的图片。PDF 当前支持普通 Markdown、表格、代码块和内嵌图片；公式用可读的 Unicode 或代码表达并解释符号，不承诺渲染 LaTeX 或 Mermaid。

日常问答不必自动制作长文档；只有明确的制作、保存、修订请求才写文档。日志另用日志工具，简洁概括，不复制整篇文档。
