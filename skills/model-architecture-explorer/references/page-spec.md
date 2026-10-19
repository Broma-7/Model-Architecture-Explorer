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
          "description": "输出为 skip(X) + MLP(LN(X))。",
          "input": "[B, N, 768]",
          "output": "[B, N, 256]",
          "params": [["宽度", "768 → 256"]],
          "source": {"file": "model.py", "symbol": "Projection.forward"},
          "expandTo": "projection-detail"
        },
        "linear": {
          "title": "线性 skip 分支",
          "kind": "encoder",
          "description": "与主分支独立计算，之后逐元素相加。",
          "input": "[B, N, 768]",
          "output": "[B, N, 256]",
          "params": [["bias", "False"]],
          "operations": ["读取原始输入 X", "Linear(768, 256, bias=False)"],
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

## 构建与更新

```bash
python <skill-dir>/scripts/build_explorer.py \
  --repo /path/to/repo --spec /path/to/spec.json --output /path/to/index.html
```

要保留项目内的 UI 定制，先复制模板到输出项目，例如 `visualization/architecture/template.html`，通过 `--template` 指定。HTML 必须保留 `architecture-data` 与 `source-data` 两个 JSON script 元素。标准构建器每次由模板重建网页，直接修改已生成的 `index.html` 会在下次构建中丢失。

输出页面内嵌所引用的源码，适合离线打开。构建器计算基于 spec、模板与源码快照的版本摘要用于诊断页面是否更新；这不是模型 checkpoint hash。若需要层选择器、可调 batch、时间步动画等额外控件，依据实际模型扩展模板与 spec，并为新增操作做浏览器行为验证。
