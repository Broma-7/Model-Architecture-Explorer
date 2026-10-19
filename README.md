# Model Architecture Explorer

根据机器学习模型的**实际源码**，制作可逐层展开的交互式架构网页。

Model Architecture Explorer 是一个 Codex skill，适合希望理解模型实现、讲解前向数据流或为模型仓库补充可视化文档的开发者与研究者。它指导 Codex 阅读模型构建入口、前向调用链与配置，将整体架构、模块内部计算、张量形状和源码位置组织成可离线浏览的网页。

典型浏览路径：**整体架构 → 模块内部计算图 → 算子详情 → 对应源码**。

## 能做什么

- 根据实际实现确认结构，区分模型内计算与模型外预处理 / rollout。
- 整体图单击模块进入内部细图，细图单击算子弹出计算详情。
- 根据模型配置展示张量形状、归一化位置、残差连接、注意力掩码、注意力头数量与每个头的维度。
- 将源码快照嵌入 HTML，离线查看并定位类 / 方法的原始行号。
- 导出 SVG，支持缩放、键盘操作、移动端内部滚动与打印。
- 提供可选 Playwright 工具，实际验证下钻、弹窗、源码范围与导出。

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

默认工作流程优先生成离线可用的 HTML 网页，常用输出位置为目标模型仓库中的 `visualization/architecture/index.html`；具体位置以 Codex 的交付说明为准。

- 点击整体图中的模块，进入内部计算图。
- 点击细图中的算子，查看计算说明、输入输出形状和源码入口。
- 通过返回导航切换视图，或导出 SVG 用于文档和分享。

本地生成的单文件 HTML 可以直接用浏览器打开。远程环境生成的页面可下载到本机打开；需要 HTTP 预览时，在模型仓库根目录执行：

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory visualization/architecture
```

本地运行时访问 `http://127.0.0.1:8765/`。远程运行时，先通过 IDE 或 SSH 将服务器的 `8765` 端口转发到本机，再打开对应的本地地址。

## 文件结构

```text
skills/model-architecture-explorer/
├── SKILL.md                      工作流程与交互要求
├── agents/openai.yaml            UI 元数据与示例调用
├── assets/explorer.html          离线 HTML / SVG 网页模板
├── references/page-spec.md       声明式架构 spec 的格式
└── scripts/
    ├── build_explorer.py         校验 spec 并嵌入源码快照
    └── check_explorer.py         可选 Playwright 行为检查
```

## 单独运行构建工具

构建器使用 Python 3.10+ 标准库，无需安装模型依赖或加载模型权重。

先按照 [spec 说明](skills/model-architecture-explorer/references/page-spec.md) 编写已经核对的结构数据，然后运行：

```bash
python skills/model-architecture-explorer/scripts/build_explorer.py \
  --repo /path/to/model-repo \
  --spec /path/to/model-repo/visualization/architecture/spec.json \
  --output /path/to/model-repo/visualization/architecture/index.html
```

需要定制模板时，复制模板到目标项目并传入 `--template`。每次构建都会重新生成 HTML，不应只修改生成后的页面再期望下次构建保留这些改动。

## 可选浏览器验证

在合适的 Python 环境中安装 Playwright 及 Chromium：

```bash
python -m pip install playwright
python -m playwright install chromium
```

然后检查离线页面或实际预览地址：

```bash
python skills/model-architecture-explorer/scripts/check_explorer.py \
  --page /path/to/index.html

python skills/model-architecture-explorer/scripts/check_explorer.py \
  --url http://127.0.0.1:8765/ \
  --screenshot /path/to/preview.png
```

检查器面向自带模板的 DOM，定制了页面结构或额外控件时需相应调整。浏览器环境可能还需要系统运行库；检查结果不代替模型语义核对。

## 使用范围与维护

- **结构依据**：以当前源码和选定配置为准。未执行模型推理时，张量形状属于静态推导结果。
- **更新方式**：模型实现或配置变更后，需要重新核对结构数据并构建页面；刷新源码快照不会自动修正架构图。
- **源码快照**：生成的 HTML 包含 spec 引用的源码。分享网页前，请确认这些源码适合随页面一起分发。

欢迎通过 Issues 反馈问题或通过 Pull Requests 改进模板与工具。反馈交互问题时，请附上复现步骤、浏览器版本和报错信息；反馈模型结构问题时，请提供相关源码位置及使用的模型配置。
