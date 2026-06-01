import { useEffect, useState } from "react";
import QueryPanel from "./QueryPanel";
import ResultCard from "./ResultCard";
import { fetchMeta, search } from "./api";
import type { Meta, Mode, Result } from "./types";

export default function App() {
  const [draft, setDraft] = useState("");
  const [keywords, setKeywords] = useState<string[]>(["llm", "agent"]);
  const [mode, setMode] = useState<Mode>("auto");
  const [topK, setTopK] = useState(10);
  const [results, setResults] = useState<Result[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  // poll /meta until the auto-started backend finishes loading the FAISS index
  useEffect(() => {
    let stop = false;
    const tick = () => {
      fetchMeta()
        .then((m) => { if (!stop) { setMeta(m); setOnline(true); } })
        .catch(() => { if (!stop) { setOnline(false); setTimeout(tick, 1500); } });
    };
    tick();
    return () => { stop = true; };
  }, []);

  const addKw = () => {
    const parts = draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    setKeywords([...new Set([...keywords, ...parts])]);
    setDraft("");
  };
  const removeKw = (k: string) => setKeywords(keywords.filter((x) => x !== k));

  const run = () => {
    if (!keywords.length) return;
    setLoading(true);
    setError("");
    search(keywords, mode, topK)
      .then((rs) => { setResults(rs); setOnline(true); })
      .catch((e) => { setError(String(e.message || e)); setResults([]); setOnline(false); })
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <header className="topbar">
        <div className="brand">
          <div className="glyph"></div>
          <b>KB Search</b>
          <span className="label">trending_fetcher</span>
        </div>
        <div className="kbstat">
          <div><span className="label">model</span><span className="v">{meta?.embedding_model || "—"}</span></div>
          <div><span className="label">dim</span><span className="v">{meta?.dimension ?? "—"}</span></div>
          <div><span className="label">vectors</span><span className="v">{meta?.total_vectors?.toLocaleString?.() ?? "—"}</span></div>
        </div>
        <span className={"conn " + (online === true ? "on" : online === false ? "off" : "")}>
          {online === true ? "● 已连接" : online === false ? "● 启动中…" : "○ 连接中…"}
        </span>
      </header>

      <div className="layout">
        <QueryPanel
          keywords={keywords}
          draft={draft}
          mode={mode}
          topK={topK}
          loading={loading}
          onDraft={setDraft}
          onAdd={addKw}
          onRemove={removeKw}
          onMode={setMode}
          onTopK={setTopK}
          onRun={run}
        />

        <main className="results">
          {loading ? (
            <div className="loading">检索中…</div>
          ) : results === null ? (
            <div className="empty-state">
              <div className="big">还没有检索结果</div>
              <div>在左侧添加关键词后点「检索」。每篇结果可用系统默认程序打开<b>原文 PDF</b>或<b>摘要·译文 MD</b>（GitHub 则为 README / 中文翻译）。</div>
            </div>
          ) : error ? (
            <div className="empty-state">
              <div className="big">后端未就绪</div>
              <div>无法连接本地检索服务（{error}）。窗口启动时会自动拉起后端，请稍候；若长时间未连接，请检查 Python 环境。</div>
            </div>
          ) : results.length === 0 ? (
            <div className="empty-state"><div className="big">无匹配结果</div></div>
          ) : (
            <div>
              <div className="rhead">
                <span className="count">{results.length} 条结果</span>
                <span className="sub mono">{keywords.join(", ")} · {mode}</span>
                <span className="rsort">按后端 rank 排序（{mode === "keyword" ? "命中数" : "相似度"} 降序）</span>
              </div>
              {results.map((it) => <ResultCard key={it.rank} item={it} mode={mode} keywords={keywords} />)}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
