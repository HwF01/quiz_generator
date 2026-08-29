# 领域文档

工程类 skill 探索代码前应先读这些文件。

## 探索前阅读

- 仓库根目录 **`CONTEXT.md`**（词汇表）
- **`docs/adr/`**：与当前改动相关的决策记录。没有 ADR 时静默继续，不要催着补空文件。

`CONTEXT.md` 由 `/grill-with-docs`（内部走 `domain-modeling`）在术语真正敲定后更新。实现细节不要写进词汇表。

## 布局（单一上下文）

```
/
├── CONTEXT.md
├── docs/
│   ├── agents/
│   └── adr/
├── backend/
└── frontend/
```

## 用词汇表里的词

写 issue 标题、假设、测试名时用 `CONTEXT.md` 中的术语，不要用它明确避开的同义词。

## ADR 冲突

若输出与已有 ADR 矛盾，明确写出来，不要默默覆盖。
