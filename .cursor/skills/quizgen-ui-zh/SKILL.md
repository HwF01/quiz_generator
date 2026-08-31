---
name: quizgen-ui-zh
description: 中文产品 UI 约定：zh-CN 文案、现有 Tailwind/Shadcn 风格、禁止 Inter/紫渐变/英文假文。在改 frontend/ 页面、组件、globals.css 或用户可见文案时使用。
---

# 中文界面

产品名「智能题库生成器」，`html lang="zh-CN"`。面向中国用户的练习工具，不是欧美营销站。

## 文案与语言

- 用户可见字符串用简体中文。不要用英文假文（Lorem ipsum）或未翻译的按钮。
- 数字、日期、相对时间用 `Intl`，locale 为 `zh-CN`。
- 导航与页面用语与现有一致：上传出题、社区广场、点击刷题、题库管理/审校、错题本、收藏、开始出题。

## 视觉

沿用现有 token，不要另起一套设计系统：

- 背景 `bg-slate-50`，卡片 `.card`，主按钮 `.btn-primary`（`brand-600` 蓝），次按钮 `.btn-ghost`
- 品牌色在 `frontend/tailwind.config.js` 的 `brand.*`，不是紫色渐变
- 圆角、边框、阴影跟 `frontend/app/globals.css` 已有 utility
- 字体走系统/现有 Tailwind 栈。禁止引入 Inter、Roboto、Playfair 等「AI 默认英文字体」

## 组件

- 函数组件 + hooks；`'use client'` 仅在需要浏览器 API 时加
- TypeScript strict，禁止 `any`
- 触控：按钮已有 `min-h-11` / `touch-manipulation`，新控件保持可点区域
- 表单用现有 `.input`；错误信息中文、靠近字段
- 与 Vercel `web-design-guidelines` 一起用时：无障碍与表单规则可采纳，但视觉与文案以本 skill 为准
- 不要同时套 Anthropic `frontend-design` 做风格重设计

## 不要做

- 不要把产品做成 Vercel 模板风展示页
- 不要为装饰加无意义动效或深色主题（当前是 light `color-scheme`）
- 不要把 API 错误原文（英文 traceback）直接展示给用户
