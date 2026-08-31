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
}): string {
  if (opts.busy) return "提交中…";
  if (isJobInFlight(opts.jobStatus)) return "生成中…";
  return opts.hasPreview ? "开始生成" : "解析并配置";
}
