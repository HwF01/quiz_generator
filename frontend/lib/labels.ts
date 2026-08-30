const QUIZ_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  ready: "可练习",
  generating: "生成中",
  failed: "生成失败",
};

const MICRO_SKILL_LABELS: Record<string, string> = {
  gist: "主旨",
  detail: "细节",
  inference: "推断",
  theme: "主题",
  attitude: "态度",
  cohesion: "衔接",
};

export function quizStatusLabel(status: string): string {
  return QUIZ_STATUS_LABELS[status] || status;
}

export function microSkillLabel(skill: string): string {
  return MICRO_SKILL_LABELS[skill] || skill;
}

export type SetupStatus = {
  llm_mode: string;
  qwen_configured: boolean;
  deepseek_configured: boolean;
  tavily_configured: boolean;
  editable: boolean;
};

export function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("://")) {
    return "/profile";
  }
  return raw;
}
