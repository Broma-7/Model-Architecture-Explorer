# Model Architecture Explorer

根据机器学习模型的**实际源码**，制作可逐层展开的交互式架构网页。

Model Architecture Explorer 是一个 Codex skill，适合希望理解模型实现、讲解前向数据流或为模型仓库补充可视化文档的开发者与研究者。它指导 Codex 阅读模型构建入口、前向调用链与配置，将整体架构、模块内部计算、张量形状和源码位置组织成可离线浏览的网页。

典型浏览路径：**整体架构 → 模块内部计算图 → 算子详情 → 对应源码**。

图中的计算单元采用紧凑布局，连续的归一化、变换与残差可合并展示；完整逐算子步骤按需展开。有参考 HTML 时优先沿用其布局，自带 spec 模板属于可选方案。SVG 图内公式还可使用 MathJax 预编译为原生路径，见 [紧凑布局与公式排版](skills/model-architecture-explorer/references/compact-diagrams.md)。

## 能做什么

- 根据实际实现确认结构，区分模型内计算与模型外预处理 / rollout。
- 整体图单击模块进入内部细图，细图单击算子弹出计算详情。
- 下钻后显示输入来源、形状及图内同号入口；支持定位入口、返回来源，并随层号更新上一层依赖。
- 根据模型配置展示张量形状、归一化位置、残差连接、注意力掩码、注意力头数量与每个头的维度。
- 说明与计算步骤支持 LaTeX：可内嵌 KaTeX，或预编译为不依赖数学字体的 SVG 路径，供图、正文与详情共用；分式按实际高度排列。
- 将源码快照嵌入 HTML，离线查看并定位类 / 方法的原始行号。
- 导出 SVG，支持缩放、键盘操作、移动端内部滚动与打印。
- 完整页面可配置模型参数卡、核心机制、实现要点、张量追踪和前向演示；形状控制项联动图、检查器和表格。
- 主视图与子图支持分级导航；算子细图使用独立字号与画布尺度，重复层选择器可按相关视图显示。
- 提供可选 Playwright 工具，实际验证下钻、弹窗、源码范围、公式碰撞与独立 SVG 导出。

**模型分析由代理读源码完成。构建脚本不会自动推断任意模型架构，也不会自动确认数学关系正确。**

## 快速开始

### 1. 安装 skill

下载并解压本仓库，或使用 Git 克隆仓库。将 `skills/model-architecture-explorer` 文件夹复制到 Codex 的用户级 skills 目录。

在 macOS / Linux 的终端中，进入本仓库根目录后执行：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/model-architecture-explorer "${CODEX_HOME:-$HOME/.codex}/skills/"
```

默认安装位置为 `~/.codex/skills/model-architecture-explorer`；如果设置了 `CODEX_HOME`，则安装到其下的 `skills` 目录。Windows 用户也可以手动将该文件夹复制到对应的 Codex skills 目录。

如果 Codex 运行在远程服务器或容器中，请在该环境中安装 skill，并确保模型源码也可从该环境访问。

### 2. 提出可视化请求

安装后重新开启 Codex 会话，在模型仓库中输入下面的请求，将路径替换为实际的模型仓库路径：

```text
使用 $model-architecture-explorer，根据 /path/to/model 的源码制作可点击展开、带张量形状和源码定位的架构网页。
```

也可以指定需要重点解释的模块或配置：

```text
使用 $model-architecture-explorer，可视化当前仓库的模型架构。
重点展开注意力模块和输出头，标注关键张量形状、残差连接及对应源码。
如果存在多种模型配置，请说明页面采用哪一种配置。
```

已有网页也可以按 skill 的交互规范逐步改造，不要求迁移到自带模板。

### 3. 查看生成结果

默认生成离线可用的单文件网页，保存为目标模型工作区的 `visualization/<model-slug>-architecture.html`，例如 `visualization/evo1-architecture.html`。路径只有一层目录加文件名，不再默认增加 `architecture/` 子目录，页面也不命名为 `index.html`。交付时会直接提供包含模型名的页面链接；用户指定路径或修改已有页面时遵循其位置。

`visualization/` 的直属文件只保留架构 HTML，其他辅助文件集中放入同名文件夹；单独复制 HTML 即可离线浏览：

```text
visualization/
├── evo1-architecture.html
└── evo1-architecture/
    ├── spec.json
    ├── template.html       # 可选
    ├── preview.png         # 可选
    └── vendor/             # 外部源码快照（按需）
```

- 点击整体图中的模块，进入内部计算图。
- 点击细图中的算子，查看计算说明、输入输出形状和源码入口。
- 通过返回导航切换视图，或导出 SVG 用于文档和分享。

本地生成的单文件 HTML 可以直接用浏览器打开。远程环境生成的页面可下载到本机打开；需要 HTTP 预览时，在模型仓库根目录执行：

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory visualization
```

将下文路径和 URL 中的 `model-name` 替换为实际模型名，本地运行时直接访问 `http://127.0.0.1:8765/model-name-architecture.html`（例如 `http://127.0.0.1:8765/evo1-architecture.html`）。远程运行时，先通过 IDE 或 SSH 将服务器的 `8765` 端口转发到本机，再打开对应的本地地址。

## 文件结构

```text
skills/model-architecture-explorer/
├── SKILL.md                      工作流程与交互要求
├── agents/openai.yaml            UI 元数据与示例调用
├── assets/explorer.html          离线 HTML / SVG 网页模板
├── assets/svg-math.js            原生 SVG 公式与尺寸计算
├── assets/katex/                 KaTeX 0.16.22、字体与 MIT 许可证
├── references/page-spec.md       声明式架构 spec 的格式
├── references/design-guide.md    阅读层次、参考页保真与视觉验收
└── scripts/
    ├── build_explorer.py         校验 spec、嵌入源码与可选 SVG 公式缓存
    ├── render_math.mjs           从 spec 或公式列表预编译字形路径
    └── check_explorer.py         可选 Playwright 行为检查
```

## 单独运行构建工具

构建器使用 Python 3.10+ 标准库，无需安装模型依赖或加载模型权重。

数学内容在 spec 中使用 `\\(...\\)`（行内）或 `\\[...\\]`（独立公式），这是 JSON 转义后的写法。模板会在检查器、详情弹窗和配置切换后渲染公式；已有 spec 的普通文本公式需要按 [公式说明](skills/model-architecture-explorer/references/page-spec.md#latex-公式) 改写后重新构建。

先按照 [spec 说明](skills/model-architecture-explorer/references/page-spec.md) 编写已经核对的结构数据，然后运行：

```bash
python skills/model-architecture-explorer/scripts/build_explorer.py \
  --repo /path/to/model-repo \
  --spec /path/to/model-repo/visualization/model-name-architecture/spec.json \
  --output /path/to/model-repo/visualization/model-name-architecture.html
```

需要定制模板时，复制模板到目标项目并传入 `--template`。每次构建都会重新生成 HTML，不应只修改生成后的页面再期望下次构建保留这些改动。

需要不依赖数学字体的公式和独立 SVG 导出时，先用 `render_math.mjs --spec ... --output /path/to/model-repo/visualization/model-name-architecture/math-svg.json` 编译符号公式，再向上述构建命令增加 `--math-svg /path/to/model-repo/visualization/model-name-architecture/math-svg.json`。缓存会直接内嵌进 HTML；之后重建只需要 Python。编译环境、普通文字与公式的区分、动态数值的处理见 [公式排版说明](skills/model-architecture-explorer/references/compact-diagrams.md#预编译与构建)。


## 可选浏览器验证

在合适的 Python 环境中安装 Playwright 及 Chromium：

```bash
python -m pip install playwright
python -m playwright install chromium
```

然后检查离线页面或实际预览地址：

```bash
python skills/model-architecture-explorer/scripts/check_explorer.py \
  --page /path/to/model-repo/visualization/model-name-architecture.html

python skills/model-architecture-explorer/scripts/check_explorer.py \
  --url http://127.0.0.1:8765/model-name-architecture.html \
  --screenshot /path/to/model-repo/visualization/model-name-architecture/preview.png
```

检查器面向自带模板的 DOM，验证下钻、详情、源码与导出，并检查越出画布或穿过无关节点的连线。公式同时支持 KaTeX 与原生 SVG；原生公式会检查与标题、形状等文字的碰撞，并独立打开下载的 SVG 验证字形路径。定制了页面结构或额外控件时需相应调整。浏览器环境可能还需要系统运行库；检查结果不代替模型语义核对或同配置的参考截图对比。

## 使用范围与维护

- **结构依据**：以当前源码和选定配置为准。未执行模型推理时，张量形状属于静态推导结果。
- **更新方式**：模型实现或配置变更后，需要重新核对结构数据并构建页面；刷新源码快照不会自动修正架构图。
- **源码快照**：生成的 HTML 包含 spec 引用的源码。分享网页前，请确认这些源码适合随页面一起分发。

欢迎通过 Issues 反馈问题或通过 Pull Requests 改进模板与工具。反馈交互问题时，请附上复现步骤、浏览器版本和报错信息；反馈模型结构问题时，请提供相关源码位置及使用的模型配置。


开发者回归测试使用 `python -m unittest discover -s tests -v`。启用原生 SVG 测试时，将 `ARCHITECTURE_MATHJAX_MODULE_DIR` 设为含 `mathjax-full@3.2.2` 的 `node_modules` 路径；测试覆盖离线显示、分式 / 矩阵、手机长公式滚动、缓存缺失、无效 TeX 和导出。
