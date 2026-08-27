const UNNAMED_PREFIX = "未命名题库";

export function isUnnamedTitle(title: string): boolean {
  const text = title.trim();
  return text === "" || text === UNNAMED_PREFIX;
}

export function nextUnnamedTitle(existing: string[]): string {
  const used = new Set(existing);
  let n = 1;
  while (used.has(`${UNNAMED_PREFIX}${n}`)) n += 1;
  return `${UNNAMED_PREFIX}${n}`;
}

export function withDuplicateSuffix(desired: string, existing: string[]): string {
  const text = desired.trim();
  if (!existing.includes(text)) return text;
  let n = 1;
  while (existing.includes(`${text}(${n})`)) n += 1;
  return `${text}(${n})`;
}
