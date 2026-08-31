export function isJobInFlight(status: string | null | undefined): boolean {
  return Boolean(status && status !== "succeeded" && status !== "failed");
}

export function isGenerateSubmitLocked(busy: boolean, jobStatus: string | null | undefined): boolean {
  return busy || isJobInFlight(jobStatus);
}

export function generateSubmitLabel(opts: {
  busy: boolean;
  jobStatus: string | null | undefined;
  hasPreview: boolean;
  canRetry?: boolean;
}): string {
  if (opts.busy) return "提交中…";
  if (isJobInFlight(opts.jobStatus)) return "生成中…";
  if (opts.canRetry && opts.jobStatus === "failed") return "用同一文档重试";
  return opts.hasPreview ? "开始生成" : "解析并配置";
}
