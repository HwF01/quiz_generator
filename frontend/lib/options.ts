const TF_TRUE = new Set(["true", "t", "1", "yes", "对", "正确"]);
const TF_FALSE = new Set(["false", "f", "0", "no", "错", "错误"]);

function isTfTrue(value: string): boolean {
  const token = value.trim().toLowerCase();
  if (TF_FALSE.has(token)) return false;
  return TF_TRUE.has(token);
}

function isTrueFalseQuestion(type?: string, options?: { key: string; text: string }[] | null): boolean {
  if (type === "true_false") return true;
  if (!options || options.length !== 2) return false;
  return options.every((o) => {
    const key = o.key.trim().toLowerCase();
    const text = o.text.trim();
    return TF_TRUE.has(key) || TF_FALSE.has(key) || ["对", "错", "正确", "错误"].includes(text);
  });
}

export function formatOptionLabel(
  option: { key: string; text: string },
  type?: string,
  options?: { key: string; text: string }[] | null,
): string {
  if (isTrueFalseQuestion(type, options)) {
    return isTfTrue(option.key) || isTfTrue(option.text) ? "对" : "错";
  }
  return `${option.key}. ${option.text}`;
}
