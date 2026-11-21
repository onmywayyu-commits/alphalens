# AlphaLens ｜ AI 投研情报终端

AlphaLens 面向科技行业买方研究，将 X 情报整理成值得进一步验证的研究线索。研究流程从单帖判断出发，经过主题聚合、信号排序和投资假设构建，最后形成简报及证据时间线。

**在线 Demo**　[AlphaLens · GitHub Pages](https://onmywayyu-commits.github.io/alphalens/)

## 当前演示与未来扩展

研究演示使用预先准备的历史 X 存档与分析。总览、信息流、每日投研简报和投资假设跟踪共享同一份静态研究快照。单帖解读来自 Codex 离线整理，两期日报保留本地回复回放的说明。来源核实状态与作者观点、AI 推断分开记录。

项目保留 Python 数据导入与结构化分析、假设组织和日报输出模块。未来可接入合规的 X API 或其他授权数据源及 LLM 服务，支持增量采集、自动投研解读、定期简报和假设跟踪。

## 核心功能

| 模块 | 用途 |
| --- | --- |
| 投研总览 | 查看样本覆盖、有效存档与单帖分析进度。展示指标由载入的数据计算。 |
| 情报信息流 | 搜索或组合筛选情报，展开全文及已有解读，有来源时回查原帖和引用。 |
| 每日投研简报 | 阅读当期重点信号、行业主题、影响机制与下一步验证事项。 |
| 投资假设跟踪 | 追踪研究假设的成立条件、反方解释和证据变化。 |

## 投研判断与证据

- **事实性陈述**记录来源提出的可检验主张，并单独记录核实状态。
- **作者观点**保留作者的判断与转述关系，引用帖与原帖分别归属。
- **AI 推断**提出可能的传导机制、替代解释与验证指标，以存档证据为锚点。

研究优先级结合投资重要性、信息增量、研究价值、证据质量和可验证性。以企业级 SSD 为例，GPU 交付不足可能意味着采购延后，也可能与存储需求减弱同时发生。跟踪新订单、取消量、调期、交期和库存，可区分两类解释。同一帖或同一线程的多条引述归并为来源组。只有新增证据与原假设的指标、时间窗口相符，才据此更新方向。

## 系统架构

- Python 使用 Pydantic 校验导入、逐帖解读和日报结构，保留来源标识、正文与引用的区别、证据定位和版本信息。
- React、Vite 和 TypeScript 渲染静态 JSON。主题偏好存于浏览器，页面与筛选状态使用 URL 片段。
- 日报支持离线演练、已有模型回复回放和需凭据的本地生成。逐帖与简报的 Prompt 位于 [pipeline/prompts](pipeline/prompts/)。

## 本机运行

项目需要 Node.js 22.13+。如已准备了本机研究存档：

```powershell
cd frontend
npm ci
npm run dev
```

开发服务从 `frontend/.local-archive/dashboard.json` 和 `frontend/.local-archive/media/` 提供本机预览。如需从自己的 Excel 导入，在项目根目录依次运行 `py -3 -m pip install -r requirements.txt`、`py -3 -m scripts.import_x_posts` 和 `py -3 -m scripts.prepare_archive_preview`。

## 静态生产预览与发布

在 `frontend` 目录准备并预览本机快照：

```powershell
npm run sync:data -- --prepare-pages-preview
$env:ALPHALENS_PAGES_PREVIEW = '1'
npm run build -- --mode pages
npm run preview -- --mode pages
Remove-Item Env:ALPHALENS_PAGES_PREVIEW
```

预览地址末尾为 `/alphalens/`。本机候选快照位于 `frontend/.local-archive/pages-snapshot/`，构建输出位于 `frontend/dist-local/pages-preview/`。准备仅文字的快照时，可给同步命令加 `--without-media`。

GitHub Pages 从审阅后的 `data/public-snapshot/` 读取研究 JSON 和允许公开的配图。只有明确获准公开的内容能移入发布目录。原始 Excel、密钥、未授权图片和完整运行日志留在本机。Actions 负责测试、构建和发布静态网站，不执行采集或分析。发布仍使用 `/alphalens/`，页面通过 URL 片段保留路由和筛选。

在仓库的 **Settings → Pages** 选择 **GitHub Actions** 作为发布来源后，推送到 `main` 即触发 [部署工作流](.github/workflows/deploy.yml)。

执行 `npm test` 可运行前端测试，`py -3 -m unittest discover -s tests` 可运行 Python 测试。使用 `python -m pipeline.analyze_posts --help` 和 `python -m scripts.run_brief --help` 查看本地分析命令。
