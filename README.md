# AlphaLens ｜ AI 投研情报终端

AlphaLens 面向科技行业买方研究，将 X 情报整理成值得进一步验证的研究线索。研究流程从单帖判断出发，经过主题聚合、信号排序和投资假设构建，最后形成简报及证据时间线。

**在线 Demo**　[AlphaLens · GitHub Pages](https://onmywayyu-commits.github.io/alphalens/)

## 核心功能

| 模块 | 用途 |
| --- | --- |
| 投研总览 | 查看样本覆盖、有效存档与单帖分析进度。展示指标由载入的数据计算。 |
| 情报信息流 | 搜索或组合筛选情报，展开全文及已有解读，有来源时回查原帖和引用。 |
| 每日投研简报 | 阅读当期重点信号、行业主题、影响机制与下一步验证事项。 |
| 投资假设跟踪 | 追踪研究假设的成立条件、反方解释和证据变化。 |

公开 Demo 使用标明为合成示例的情报、投研线索和简报。本机研究预览可读取手动采集的历史 X 存档、图片和已准备的分析结果。本机的数据、证据摘录与图片由独立预览提供。

## 投研判断与证据

- **事实性陈述**记录来源提出的可检验主张，并单独记录核实状态。
- **作者观点**保留作者的判断与转述关系，引用帖与原帖分别归属。
- **AI 推断**提出可能的传导机制、替代解释与验证指标，以存档证据为锚点。

研究优先级结合投资重要性、信息增量、研究价值、证据质量和可验证性。以企业级 SSD 为例，GPU 交付不足可能意味着采购延后，也可能与存储需求减弱同时发生。跟踪新订单、取消量、调期、交期和库存，可区分两类解释。同一帖或同一线程的多条引述归并为来源组。只有新增证据与原假设的指标、时间窗口相符，才据此更新方向。

## 系统架构

- Python 使用 Pydantic 校验导入、逐帖解读和日报结构，保留来源标识、本文与引用的区别、证据定位和版本信息。
- React、Vite 和 TypeScript 消费静态 JSON。主题偏好存于浏览器，页面与筛选状态使用 URL 片段，可在 GitHub Pages 项目子路径下刷新。
- 日报支持离线演练、已有模型回复回放和需凭据的本地生成命令。当前真实存档的演示结果使用预先生成的资料。GitHub Actions 负责前端测试、构建及发布。
- 逐帖 Prompt 位于 [post_analysis_v1.md](pipeline/prompts/post_analysis_v1.md)，日报排序和生成约定见 [daily_brief_v2.md](pipeline/prompts/daily_brief_v2.md)。输入内容或配置变化后，存档版本可以分别核对。

## 本地运行

需要 Node.js 22.13+，部署使用 Node.js 24。在项目根目录执行：

```powershell
cd frontend
npm ci
npm run dev
```

打开终端打印的本机地址。执行 `npm test` 运行前端测试。执行 `npm run build` 进行 TypeScript 检查和生产构建。可用 `npm run dev -- --mode demo` 明确选择公开样本。构建前从 `data/processed/dashboard.json` 同步公开数据，产物写入 `frontend/dist/`。

有权使用的本地 Excel 可存入 `data/raw/x_posts.xlsx`，图片存入 `data/raw/media/`。使用 Python 3.11+，在项目根目录操作：

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m scripts.import_x_posts
py -3 -m scripts.prepare_archive_preview
py -3 -m unittest discover -s tests -v
```

`python -m pipeline.analyze_posts --help` 和 `python -m scripts.run_brief --help` 列出逐帖分析与日报命令。在线分析模式所需凭据由本地环境提供。真实 Excel、第三方配图、本机预览快照和研究归档均保留在本机。

## 部署和后续方向

仓库的 **Settings → Pages** 将发布来源设为 **GitHub Actions** 后，推送到 `main` 即触发 [部署工作流](.github/workflows/deploy.yml)。工作流依据 Pages 配置确定 Vite 的基路径，默认项目路径为 `/alphalens/`。

当前为静态研究 Demo。后续可接入合规数据源，加入自动采集与定期生成，并在公司公告、财报或其他一手证据到位后持续更新研究假设。
