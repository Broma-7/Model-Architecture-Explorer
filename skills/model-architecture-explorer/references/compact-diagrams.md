# 紧凑计算图与原生 SVG 公式

用于有参考页面、用户反馈图太长或公式难看，或需要制作可导出的紧凑 SVG 架构图时。先决定计算单元与阅读路径，再选择渲染工具；不要把图变成源码调用清单。

## 把细节放到合适的位置

一张模块图说明主要计算关系。把连续、不分叉的操作合成语义单元：LN 与投影、Attention 与残差、FFN 与残差、动作 MLP 与输出激活。保留真正有解释价值的分支，例如独立 Value、反向 softmax、固定条件 Memory；残差可用短公式明确底座，无需每次绕行整张画布。

主图节点通常容纳名称、一条短公式和一行有用的配置 / 形状；不把这三项做成固定配额。形状没有变化时，在流的入口或出口标注一次即可。重复层只画一层加层号选择器，改变实例与输入来源；子层的 QKV、mask、dropout、投影细节放进点击详情的折叠步骤。用户明确要求全展开时可提供专门视图。

多路输入用并排支路，共享运算居中；解码器可用一侧放条件、另一侧顺序排三个子层。连续步骤之间采用短连线，避免每个子层占一整屏。与参考在相同宽度比较画布高度、节点间距和公式的实际字号，不能仅比较节点是否齐全。

内部视图可聚焦计算图区，把概览中已介绍的机制卡和张量表收起；原页面导航应能返回这些内容。检查器负责短说明和入口，完整公式与逐算子步骤在详情中呈现，减少同屏重复。

## 分开显示公式与形状

- 数据形状与运行时实例：等宽 `[B,N,256]`、`decoder.layers.2`。
- 架构参数与操作链：普通文字 `8 heads × 32`、`LN → Linear → GELU`。
- 决定计算关系的公式：正规数学排版，例如带分式的缩放点积、softmax 轴、残差底座。

图内公式用稳定的符号，动态数值由旁边的形状标签解释。不要把每个张量都改写成 `X ∈ ℝ^{…}`；也不要把长展开式自动缩成小字。相同宽度下，短公式与正文应有相近的视觉大小。

## 可选：预编译 TeX 为 SVG 路径

对于公式集合有限、需要可靠离线浏览与 SVG 导出的页面，可在构建阶段用 MathJax 生成路径。浏览器不再依赖数学字体或 foreignObject。动态数值使用普通文字，公式使用符号；若用户可输入任意新公式，则采用浏览器端数学渲染器。

将不带分隔符的 TeX 字符串数组写到 `formulas.json`。在项目工具目录中安装 MathJax 3（已有数学渲染环境时可复用），运行：

```bash
npm install --prefix /tmp/model-math --no-audit --no-fund mathjax-full@3.2.2
node <skill-dir>/scripts/render_math.mjs \
  --module-dir /tmp/model-math/node_modules \
  --input formulas.json --output math-svg.json
```

`render_math.mjs` 为每个表达式生成独立路径和 viewBox，拒绝解析错误。把输出 JSON 嵌入 `<script id="math-svg-data" type="application/json">`（JSON 中的 `<` 转义成 `\u003c`），再内联 [assets/svg-math.js](../assets/svg-math.js)。其中：

- `architectureMath.svg("\\(…\\)", x, baselineY, width, fontSize, color)` 返回可嵌入主 SVG 的公式，保留真实比例与基线；超出预留宽度会报错，要求重新排版。
- `architectureMath.text` 渲染混排正文；`formula` / `equations` 供详情使用。缓存缺少表达式时会报错，不静默显示伪公式。
- 外层 HTML 为 `.math-expression > svg` 设置正常的数学字号与基线；长详情公式在局部容器滚动。不要用通用 `svg{width:100%}` 选择器拉伸所有公式。

交付前遍历每个配置和条件分支，覆盖全部公式；切换 batch / 序列长度不应产生未编译表达式。导出的独立 SVG 应无外部字体、无丢失 glyph 引用、无 foreignObject，单独打开检查路径、颜色与尺寸。预编译只改善排版稳定性，不验证数学语义。
