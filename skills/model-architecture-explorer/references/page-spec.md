# 单文件架构网页的声明式 spec

用于采用 skill 自带 `assets/explorer.html` 的新页面。实际源码负责语义，spec 只记录已经核对的结果。下面使用一个简单残差投影示意数据结构；文件与符号必须替换为目标仓库真实存在的定义。

## 顶层结构

```json
{
  "title": "模型名 · 架构探索器",
  "subtitle": "基于当前模型源码的前向数据流",
  "defaultProfile": "base",
  "sourceFiles": [],
  "profiles": [
    {
      "id": "base",
      "label": "Base 配方",
      "defaultView": "overview",
      "assumptions": "B 为 batch；形状由配置推导，未执行推理。",
      "modules": {
        "projection": {
          "title": "残差投影",
          "kind": "encoder",
          "description": "输出为 \\(Y = \\operatorname{skip}(X) + \\operatorname{MLP}(\\operatorname{LN}(X))\\)。",
          "input": "\\(X \\in \\mathbb{R}^{B \\times N \\times 768}\\)",
          "output": "\\(Y \\in \\mathbb{R}^{B \\times N \\times 256}\\)",
          "params": [["宽度", "768 → 256"]],
          "source": {"file": "model.py", "symbol": "Projection.forward"},
          "expandTo": "projection-detail"
        },
        "linear": {
          "title": "线性 skip 分支",
          "kind": "encoder",
          "description": "与主分支独立计算，之后逐元素相加。",
          "input": "\\(X \\in \\mathbb{R}^{B \\times N \\times 768}\\)",
          "output": "\\(S \\in \\mathbb{R}^{B \\times N \\times 256}\\)",
          "params": [["bias", "False"]],
          "operations": ["读取原始输入 \\(X\\)", "\\[S = X W_{\\mathrm{skip}}^{\\mathsf{T}}, \\qquad W_{\\mathrm{skip}} \\in \\mathbb{R}^{256 \\times 768}\\]"],
          "source": {"file": "model.py", "symbol": "Projection.forward"}
        }
      },
      "views": [
        {
          "id": "overview",
          "label": "整体架构",
          "width": 900,
          "height": 300,
          "nodes": [
            {"id": "proj", "module": "projection", "x": 80, "y": 90,
             "width": 330, "height": 120,
             "lines": ["残差 MLP + skip", "[B,N,768] → [B,N,256]"]}
          ],
          "edges": [],
          "notes": [{"x": 80, "y": 260, "text": "点击模块展开内部计算", "size": 14}]
        },
        {
          "id": "projection-detail",
          "label": "投影内部",
          "width": 900,
          "height": 330,
          "nodes": [
            {"id": "skip", "module": "linear", "x": 80, "y": 100,
             "width": 440, "height": 130, "lines": ["Linear(768,256)", "输入来自未归一化的 X"]}
          ],
          "edges": [],
          "notes": [{"x": 80, "y": 285, "text": "此处仅示例 skip 分支；实际建图应包含主分支与相加节点。"}]
        }
      ]
    }
  ]
}
```

示例用于说明协议，不是可直接交付的完整模型图。

## 字段与行为

- 每个 profile 自带 `modules` 和 `views`，使实际配置差异可以被清晰表达，避免只换标题。`defaultView` 默认第一个视图。
- `modules` 的 key 是逻辑模块标识，`nodes[].id` 是当前图内唯一的实例标识。一个模块允许在同一张图里出现多个实例；若实例参数不同，应使用独立 module 条目。
- 节点点击时，若对应 module 的 `expandTo` 指向别的视图，就下钻；否则打开详情弹窗。`expandTo` 只表示导航，不表示模型数据边。
- 每个 module 通过 `source.file` 对应仓库内的 UTF-8 源码，`source.symbol` 对应 Python AST 限定名，例如 `Model.forward`。Python 定义可以带 decorator；快照高亮范围包含 decorator。非 Python 文件可省略 symbol，展示完整文件；若需要精确片段，可扩展构建器，不能伪造行号。
- `sourceFiles` 可另外列出配置等明确需要展示的文件。构建器只读取这份显式列表和 modules 中引用的文件。
- `params` 是 `[标签, 值]` 数组。`operations` 是可选的、按真实执行顺序列出的字符串数组，在详情弹窗展示。
- 节点 `title` 可覆盖模块标题；`lines` 是直接画到框中的摘要，每行约 20 px。为正文预留足够高度（大致 `60 + 22 × 行数`），长标题应加宽或简化。
- `kind` 支持 `input`、`encoder`、`fusion`、`decoder`、`output`、`neutral`，也提供 `vision`、`language`、`state`、`action` 的配色。它只是视觉语义，不规定模型结构。

## 完整页面的阅读区与联动

上面的最小 spec 仅说明协议。新建完整模型页面时，根据实际源码补充下面这些字段；布局与验收原则见 [design-guide.md](design-guide.md)。所有字段均可省略以兼容旧 spec，但只有最小节点列表的页面不能代表复杂模型的完整交付质量。

顶层 `presentation` 提供页面身份与概览文案：

```json
{
  "presentation": {
    "brand": "ModelName",
    "headline": "一句话说明模型核心思路",
    "eyebrow": "ENCODE · INTERACT · DECODE",
    "signature": "X → Z → Y",
    "repository": "model-repo / source snapshot"
  }
}
```

每个 profile 可以声明模型参数、解释区、形状控制项和张量表：

```json
{
  "dimensions": {"N": 32, "D": 256},
  "controls": [
    {"id": "B", "label": "Batch", "value": 1, "min": 1, "max": 128}
  ],
  "stats": [
    {"label": "输入宽度 / INPUT", "value": 768},
    {"label": "输出宽度 / OUTPUT", "value": "{{D}}", "detail": "projection"}
  ],
  "mechanism": {
    "title": "残差投影",
    "equations": ["\\[Y = W_s X + \\operatorname{MLP}(\\operatorname{LN}(X))\\]"],
    "description": "主分支先归一化；skip 读取原始输入，两路在相同形状下逐元素相加。",
    "module": "projection"
  },
  "notes": [
    {"title": "skip 保留原始输入", "text": "不要将主分支的 LayerNorm 误画到 skip 上。", "module": "linear"}
  ],
  "trace": ["projection", "linear"],
  "tensorCaption": "关键前向阶段 · 形状由源码和配置推导"
}
```

- `stats` 显示实际模型参数；未声明时隐藏该区域，不用文档规模统计冒充模型信息。新页面应填写有解释价值的模型信息。
- `mechanism` 的 `equations` 和说明支持 LaTeX；`notes` 是实现要点。可选的 `module` 链接指向当前 profile 的模块，跳转到对应计算图或详情。
- `trace` 是按阅读路径排列的模块 id 列表，每行关联该模块的输入、输出和真实源码。不声明时按默认整体视图的模块顺序生成；它不推断真实执行时序。
- `dimensions` 提供数值常量；`controls` 提供可调数值，每项有 `id`、`value`，可选 `label`、`min`、`max`、`step`。未给出的边界为 1 至 4096，步长为 1；初值必须有效。切换 profile 会重置其控制项。
- 文本内的 `{{B}}`、`{{B * N}}`、`{{N + 2}}` 会由当前数值替换，支持括号、加减乘除与一元正负号，使用受限算术解析器而非 JavaScript eval。不要把任意代码放进表达式，也不要对无法从源码推导的关系提供可调控件。未知变量会保持原样，交付时应修正所有未替换的形状表达式。
- 参数卡、说明、节点文字、检查器、公式和张量表使用同一组数值。源文件与原始源码行号不做字符串替换。

复杂模块的节点可以在保留一次点击下钻的同时展示内部摘要：

```json
{
  "id": "interaction", "module": "fusion",
  "x": 480, "y": 150, "width": 250, "height": 220,
  "title": "跨模态交互", "badge": "×6",
  "blocks": [
    {"title": "V ⇄ L", "text": "双向 Cross-Attention", "kind": "vision"},
    {"title": "文本 Self-Attention", "text": "+ FFN", "kind": "language"}
  ],
  "foot": "输出 token 数不变"
}
```

`blocks` 替代该节点的 `lines`，`foot` 放在底部，`badge` 放在标题右侧；为标题与 badge 留出空间。可选 `titleSize` 默认 13；`lineHeight` 默认 20。图内公式用显式 LaTeX 分隔符，通过 SVG `foreignObject` 排版；有分式或多行公式时增大行距和框高，检查真实边界。SVG 导出会内嵌公式样式和字体。普通 SVG 的纯文本标签仍可使用。

视图可声明 `defaultModule` 指定初始检查器，并用 `flow` 明确前向演示步骤，例如：

```json
{
  "defaultModule": "fusion",
  "flow": [
    {"label": "编码两路输入", "modules": ["vision", "language"]},
    {"label": "跨模态交互", "modules": ["fusion"]}
  ]
}
```

这些模块必须出现在该视图。每步允许同时高亮多个模块；播放与单步更新检查器，不触发下钻或弹窗。没有 `flow` 时不展示播放控件，也不会擅自将节点排列当成执行顺序。`legend` 可在 profile 中用 `[{"kind":"vision","label":"视觉流"}]` 覆盖默认图例。

图可以另外声明：

```json
{
  "groups": [
    {"x": 30, "y": 65, "width": 800, "height": 230, "label": "一个独立参数的 Transformer 层"}
  ],
  "edges": [
    {"d": "M 360 160 H 440", "kind": "encoder", "arrow": true,
     "label": "[B,N,256]", "labelX": 365, "labelY": 145}
  ],
  "notes": [
    {"x": 50, "y": 320, "text": "形状推导的前提", "size": 13}
  ]
}
```

`edges.d` 是 SVG path；边线先绘制，节点后绘制。端点应落在节点边界。残差支路、Value 支路等需要实际画出，或在子层公式中明确写出；不能让普通数据线穿过另一个无关模块。

`width/height` 是当前图的 viewBox 尺寸，同时决定 SVG 导出尺寸。不同视图可有不同长宽比。构建器检查节点 / group / note 的基本边界，实际文字和 edge 路径仍需浏览器检查。

## 算子排版、导航层级与层实例

为细图声明 `variant: "operator"`，默认使用更大的标题与正文；节点可用 `fontSize`、`titleSize`、`lineHeight` 单独覆盖，`kind` 可覆盖该实例的颜色。KaTeX 模式默认正文基线在节点顶部下方 59 个单位，行距 26；原生 SVG 模式按字形实际高度顺序排列，分式不会沿用普通文本行高。可用节点 `mathSize` 指定数学字号，为公式和页脚保留足够的节点高度。总览继续使用原有的紧凑卡片样式。

```json
{
  "id": "attention-detail",
  "label": "注意力算子",
  "parent": "interaction",
  "variant": "operator",
  "heading": "一层内部：两路投影与跨路读取",
  "description": "沿线查看评分、归一化和 Value 的流向；点击算子查看源码。",
  "width": 1200,
  "height": 1600,
  "minWidth": 1020
}
```

此片段只说明视图元数据；仍需填写完整 `nodes` / `edges`。`parent` 指向当前 profile 中的另一视图，不允许循环。不填 parent 的视图显示在主标签栏；子图通过模块下钻、面包屑和“全部计算图”选择器访问。`parent` 表示阅读层级，不是数据依赖。`heading` / `description` 支持形状替换和公式。`minWidth` 控制内部滚动画布的最小 CSS 宽度；未声明时算子图为 viewBox 宽度的 85%，其他视图为 650。

在 profile 中声明独立于形状输入框的层号选择器：

```json
{
  "layerControls": [
    {"id": "I", "label": "交互层", "value": 1, "max": 6,
     "views": ["interaction", "attention-detail"]}
  ]
}
```

`views` 可省略，省略时在全部视图显示；通常应限制到相关细图。层号为 1..max 的整数，通过 `{{I}}`、`{{I-1}}` 更新标题、参数和实例路径说明，不能与 `controls` 重名。源码 `source.symbol` 仍定位实际类 / 方法定义；独立层的运行时实例路径写在 `params`，不要伪造 Python 定义。首层与后续层输入关系若不同，图和说明必须表达该区别。更复杂的条件文案可用项目定制模板实现。

## 构建与更新

### LaTeX 公式

`description`、`input`、`output`、`params` 的标签和值、`operations`、顶层 `subtitle` 及 profile 的 `assumptions` 支持混排文字与 LaTeX。普通形状优先保留 `[B,N,256]` 等等宽标签，只有数学关系需要公式排版。行内用 `\(...\)` 或 `$...$`，独立公式用 `\[...\]` 或 `$$...$$`。只渲染显式分隔符中的公式，不会把普通字符串自动转换成数学表达式。

JSON 必须转义反斜杠，例如下面的内容会显示带有转置、分式和根号的注意力公式：

```json
{
  "description": "用 \\(d_k\\) 缩放点积，再沿键序列维度归一化。",
  "operations": [
    "\\[A = \\operatorname{softmax}\\left(\\frac{QK^{\\mathsf{T}}}{\\sqrt{d_k}} + M\\right)V\\]"
  ]
}
```

Python 构建 spec 时可用原始字符串，例如 `r"\(X \in \mathbb{R}^{B \times N \times D}\)"`，再由 `json.dumps` 转义。金额中的字面美元符号可写成 `\(\$5\)`（JSON 中为 `\\(\\$5\\)`）。字段不解析 Markdown / HTML，不要用反引号或代码围栏包住公式；代码标识、文件路径和源码快照按普通文本保留。节点摘要和图注也支持 LaTeX；为图内公式预留足够空间，避免长推导遮挡相邻节点。

KaTeX 0.16.22 的脚本、CSS 和 WOFF2 字体随 skill 分发，构建时内嵌到 HTML，不依赖 CDN 或模型运行环境的额外 Python 包。长的独立公式在其容器中横向滚动。解析失败会保留可见的错误表达式，交付前应通过浏览器检查并修正。

### 运行构建器

默认交付路径为 `visualization/<model-slug>-architecture.html`；例如 `visualization/evo1-architecture.html`。`visualization/` 的直属文件只保留架构 HTML；该模型的 spec、定制模板、截图和其他辅助文件统一放进 `visualization/<model-slug>-architecture/`，例如 `visualization/evo1-architecture/spec.json`。HTML 内嵌浏览所需资源。以下 `model-name` 替换为实际模型名。

```bash
python <skill-dir>/scripts/build_explorer.py \
  --repo /path/to/model-repo --spec /path/to/model-repo/visualization/model-name-architecture/spec.json --output /path/to/model-repo/visualization/model-name-architecture.html
```

要保留项目内的 UI 定制，先复制模板到输出项目，例如 `visualization/model-name-architecture/template.html`，通过 `--template` 指定。HTML 必须保留 `architecture-data` 与 `source-data` 两个 JSON script 元素。标准构建器每次由模板重建网页，直接修改已生成的模型架构 HTML 会在下次构建中丢失。

沿用自带 LaTeX 渲染时，还要保留 `<head>` 中的 `<!-- KATEX_STYLES -->` 与应用脚本前的 `<!-- KATEX_SCRIPTS -->`；构建器会从已安装 skill 的资源目录填入完整内容。两个标记都没有的旧定制模板仍可构建，但需要自行接入数学渲染器。

输出页面内嵌所引用的源码，适合离线打开。构建器计算基于 spec、模板与源码快照的版本摘要用于诊断页面是否更新；这不是模型 checkpoint hash。若需要层选择器、可调 batch、时间步动画等额外控件，依据实际模型扩展模板与 spec，并为新增操作做浏览器行为验证。


### 可选原生 SVG 公式

构建器的 `--math-svg /path/to/math-svg.json` 参数会在同一模板中启用预编译字形路径，图、正文和详情共用缓存。原有 KaTeX 构建方式不变。编译命令、渲染选择与尺寸计算见 [compact-diagrams.md](compact-diagrams.md#预编译与构建)。

图中每条数学 `lines` 应是单个带分隔符的完整公式，说明与形状放在独立行。不要把 `{{B}}` 等动态占位符写进预编译公式；它们仍可用于普通形状、参数卡与实例标签。缓存缺失或公式过宽会明确报错，不会静默显示原始 LaTeX 或缩小字号。
