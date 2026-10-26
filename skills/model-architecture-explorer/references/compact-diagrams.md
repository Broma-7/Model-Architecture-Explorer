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

## 选择渲染器，统一数学表示

HTML 中已有稳定的 KaTeX 可继续使用；需要任意用户输入或数值直接写进公式时，它比有限缓存合适。先检查数学字体是否加载、是否有全局 CSS 覆盖 `.katex` 的字体与行高，以及容器是否裁切。不要仅凭 `.katex` 元素存在就判断显示正常。

公式集合有限、要求可靠离线显示或独立 SVG 导出时，可用 MathJax 预编译为原生字形路径。图、核心公式和详情弹窗使用同一缓存，避免同时维护一套 Unicode 伪公式和一套 LaTeX。分式用 `\frac`，根号用 `\sqrt`，上下标用 TeX 分组，算子名用 `\operatorname`；形状和源码调用仍保留普通文字。

## 预编译与构建

安装到临时工具目录即可，不必为可视化修改模型依赖。已有 MathJax 环境时可复用：

```bash
npm install --prefix /tmp/model-math --no-audit --no-fund mathjax-full@3.2.2
node <skill-dir>/scripts/render_math.mjs \
  --module-dir /tmp/model-math/node_modules \
  --spec /path/to/spec.json --output /path/to/math-svg.json
python <skill-dir>/scripts/build_explorer.py \
  --repo /path/to/model-repo --spec /path/to/spec.json \
  --math-svg /path/to/math-svg.json --output /path/to/index.html
```

`--spec` 从 spec 字符串中提取所有显式公式并去重；也可沿用 `--input formulas.json` 传入不带分隔符的 TeX 数组。解析错误会使编译失败。使用符号公式，将 Batch、token 数等动态数值放在相邻的形状标签；编译器会拒绝公式内的 `{{…}}` 占位符。需要这种动态公式时保留 KaTeX，或在项目定制逻辑中预编译有限的实际取值。

构建器嵌入缓存与 [assets/svg-math.js](../assets/svg-math.js)，不需要在用户打开网页时安装 Node 或加载数学字体。缺失公式会在构建时报告；修改 spec 后重新编译。缓存可与项目一起保存，以后重建不必重新安装 MathJax。两种内置渲染方式都保留模板中的 `KATEX_STYLES` / `KATEX_SCRIPTS` 注入标记；`--math-svg` 会用矢量渲染器替换它们。

已有自定义页面不必迁移到模板：将缓存嵌入 `<script id="math-svg-data" type="application/json">`，JSON 中 `<` 转义成 `\u003c`，再内联 helper。`architectureMath.text` 用于混排正文，`formula` 用于详情。每个图内数学标签应只包含一个完整公式，说明文字放在相邻标签。

## 按公式实际尺寸排版

不要让图内公式继承固定文本行高。分式、根号和带上下标的表达式高度不同，公式基线相同也可能向上撞到标题。用 viewBox 推导实际尺寸：

```javascript
const box = architectureMath.dimensions(formula, fontSize);
const baseline = top - box.top;
markup += architectureMath.svg(formula, x, baseline, availableWidth, fontSize, color);
top += Math.max(lineHeight, box.height + gap);
```

`dimensions` 返回当前字号下的 `top / width / height`；`svg` 保留比例与基线，超出预留宽度时要求简写或扩大节点，不自动缩小。自带模板的原生 SVG 模式会按这一方式排列 `lines`，`mathSize` 可单独指定公式字号。节点高度和页脚仍应为实际内容留出空间。

正文公式按 em 设置自然宽高，避免通用 `svg { width:100% }` 拉伸；长公式的直接容器使用 `overflow-x:auto`，给分子、上下标和下缘留 padding。不要让整页或弹窗本身横向溢出。已有绘图代码若按基线放置公式，可继续使用 `svg`，无需重做布局。

## 核对真实显示

- 遍历配置、层号与全部公式，确认缓存覆盖实际显示内容、字形路径非空；检查错误、分式线、根号、上下标和矩阵。
- 在相同视口下查看总览、核心细图、详情及手机截图，检查字号是否可读，公式是否撞标题、形状或页脚，长公式是否可以在局部滚动。
- 独立打开导出的 SVG，核对 viewBox、宽高与公式。原生路径模式不应需要 `foreignObject`、外部数学字体或外部 glyph 引用；仅存在公式标签不证明导出可见。
- 浏览器检查器同时支持 KaTeX 与原生 SVG，会检查后者的公式碰撞和导出；额外控件与自定义绘图仍应按实际行为补充验证。预编译只保证渲染稳定，不判断公式的数学语义。
