# 议题跟踪：本地 Markdown

代码托管在 GitHub。议题与规格仍写在仓库内 `.scratch/` 下的 Markdown 文件里，不使用 GitHub Issues。

## 约定

- 每个功能一个目录：`.scratch/<feature-slug>/`
- 规格：`.scratch/<feature-slug>/spec.md`
- 实现票：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 编号，不要合成一个 tickets 文件
- 状态写在文件靠前的 `Status:` 行
- 讨论追加在文末 `## Comments`

## 当 skill 说「发布到 issue tracker」

在 `.scratch/<feature-slug>/` 下新建文件（目录不存在则创建）。

## 当 skill 说「读取相关 ticket」

读用户给出的路径或编号对应的文件。
