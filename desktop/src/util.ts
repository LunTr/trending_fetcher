export type Source = "GitHub" | "HuggingFace" | "—";

// source_path is an absolute Windows path → match either separator
export function sourceOf(p: string): Source {
  if (/[\\/]GitHub[\\/]/.test(p)) return "GitHub";
  if (/[\\/]HuggingFace[\\/]/.test(p)) return "HuggingFace";
  return "—";
}

export interface Target {
  label: string;
  path: string;
}

// HuggingFace 论文_id.pdf ↔ 论文_id_summary.md (摘要译文)
// GitHub      README.md   ↔ README_zh.md (中文翻译)
export function openTargets(p: string): Target[] {
  const src = sourceOf(p);
  if (src === "HuggingFace") {
    if (/_summary\.md$/i.test(p))
      return [{ label: "摘要·译文", path: p }, { label: "原文 PDF", path: p.replace(/_summary\.md$/i, ".pdf") }];
    if (/\.pdf$/i.test(p))
      return [{ label: "原文 PDF", path: p }, { label: "摘要·译文", path: p.replace(/\.pdf$/i, "_summary.md") }];
  }
  if (src === "GitHub") {
    if (/README_zh\.md$/i.test(p))
      return [{ label: "中文 README", path: p }, { label: "原文 README", path: p.replace(/README_zh\.md$/i, "README.md") }];
    if (/README\.md$/i.test(p))
      return [{ label: "README", path: p }, { label: "中文翻译", path: p.replace(/README\.md$/i, "README_zh.md") }];
  }
  return [{ label: "打开", path: p }];
}
