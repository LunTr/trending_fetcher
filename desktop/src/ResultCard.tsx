import type { ReactNode } from "react";
import type { Mode, Result } from "./types";
import { openLocal } from "./api";
import { openTargets, sourceOf } from "./util";

function highlight(text: string, keywords: string[]): ReactNode {
  const re = keywords
    .map((k) => k.trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!re.length) return text;
  const hits = new Set(keywords.map((k) => k.trim().toLowerCase()).filter(Boolean));
  return text.split(new RegExp(`(${re.join("|")})`, "gi")).map((part, i) =>
    hits.has(part.toLowerCase()) ? <mark key={i}>{part}</mark> : <span key={i}>{part}</span>
  );
}

export default function ResultCard({ item, mode, keywords }: { item: Result; mode: Mode; keywords: string[] }) {
  const r = item.record;
  const targets = openTargets(r.source_path);
  const src = sourceOf(r.source_path);
  const scoreLabel = mode === "keyword" ? "hits" : "cosine";
  const scoreText = mode === "keyword" ? String(Math.round(item.score)) : item.score.toFixed(3);
  const snippet = item.snippet || r.text || "";

  return (
    <div className="card" onClick={() => openLocal(targets[0].path)} title={"打开 " + targets[0].label}>
      <div className="rank mono">#{item.rank}</div>
      <div className="cmain">
        <h3 className="ctitle">{r.title || r.file_name}</h3>
        <div className="meta">
          <span><i>date</i><b className="mono">{r.date}</b></span>
          <span><i>type</i><b className="mono">{r.file_type}</b></span>
          <span><i>section</i>{r.section_title}</span>
          <span><i>chunk</i><b className="mono">{r.chunk_index}/{r.chunk_total}</b></span>
          <span className={"pill " + (src === "GitHub" ? "gh" : src === "HuggingFace" ? "hf" : "")}>{src}</span>
        </div>
        <div className="snip">{highlight(snippet, keywords)}</div>
        <div className="path">{r.source_path}</div>
      </div>
      <div className="cside">
        <div className="score">{scoreText}<small>{scoreLabel}</small></div>
        <div className="opens">
          {targets.map((t, i) => (
            <button
              key={t.path}
              className={"open" + (i ? " alt" : "")}
              onClick={(e) => { e.stopPropagation(); openLocal(t.path); }}
            >
              {t.label} ↗
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
