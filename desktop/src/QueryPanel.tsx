import type { Mode } from "./types";

const MODE_DESC: Record<Mode, string> = {
  auto: "向量检索，embed 失败时自动降级到关键词",
  vector: "纯向量检索（FAISS 余弦相似度，0–1）",
  keyword: "关键词命中计数，无需 embedding 模型",
};

interface Props {
  keywords: string[];
  draft: string;
  mode: Mode;
  topK: number;
  loading: boolean;
  onDraft: (v: string) => void;
  onAdd: () => void;
  onRemove: (k: string) => void;
  onMode: (m: Mode) => void;
  onTopK: (n: number) => void;
  onRun: () => void;
}

export default function QueryPanel(p: Props) {
  return (
    <aside className="panel">
      <h2><span className="n">01</span> 查询构造器</h2>

      <div className="field">
        <span className="label">关键词（逗号可一次加多个）</span>
        <div className="kwrow">
          <input
            value={p.draft}
            placeholder="例如 llm, retrieval"
            onChange={(e) => p.onDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") p.onAdd(); }}
          />
          <button className="addbtn" onClick={p.onAdd} aria-label="添加">+</button>
        </div>
        <div className="chips">
          {p.keywords.length === 0 && <span className="empty">尚无关键词</span>}
          {p.keywords.map((k) => (
            <span className="chip" key={k}>{k}
              <button className="x" onClick={() => p.onRemove(k)} aria-label={"删除 " + k}>×</button>
            </span>
          ))}
        </div>
        <div className="hint">→ search.py 的逗号分隔输入，内部以空格拼接送 embedding</div>
      </div>

      <div className="field">
        <span className="label">检索模式 · --mode</span>
        <div className="modes">
          {(["auto", "vector", "keyword"] as Mode[]).map((m) => (
            <button key={m} className={p.mode === m ? "on" : ""} onClick={() => p.onMode(m)}>{m}</button>
          ))}
        </div>
        <div className="modedesc">{MODE_DESC[p.mode]}</div>
      </div>

      <div className="field">
        <span className="label">返回数量 · --top</span>
        <div className="stepper">
          <button onClick={() => p.onTopK(Math.max(1, p.topK - 1))} aria-label="减少">−</button>
          <span className="num">{p.topK}</span>
          <button onClick={() => p.onTopK(Math.min(50, p.topK + 1))} aria-label="增加">+</button>
        </div>
      </div>

      <button className="runbtn" disabled={p.keywords.length === 0 || p.loading} onClick={p.onRun}>
        {p.loading ? "检索中…" : "检索"}
      </button>
    </aside>
  );
}
