import { useEffect, useMemo, useState } from "react";
import QueryPanel from "./QueryPanel";
import ResultCard from "./ResultCard";
import { fetchMeta, fetchRuntime, fetchTask, search, startTask } from "./api";
import type { Meta, Mode, Page, Result, RuntimeInfo, TaskKind, TaskState } from "./types";

const NAV: { id: Page; label: string; desc: string }[] = [
  { id: "main", label: "Main 下载", desc: "抓取 GitHub / HF Daily Papers" },
  { id: "summarize", label: "Summarize", desc: "摘要论文并翻译 README" },
  { id: "kb", label: "知识库", desc: "检索、增量建库、打开文件" },
];

const STAGE_LABELS: Record<string, string> = {
  idle: "空闲",
  starting: "启动中",
  proxy: "代理配置",
  history: "arXiv 历史",
  github: "GitHub Trending",
  "hf-list": "HF Daily Papers",
  "hf-pdf": "PDF 下载",
  main: "Main",
  "model-test": "模型探测",
  "pdf-summary": "PDF 摘要",
  "readme-translate": "README 翻译",
  "kb-build": "知识库构建",
  failed: "失败",
};

function formatBytes(value?: number) {
  if (!value || value <= 0) return "未知";
  const units = ["B", "KB", "MB", "GB"];
  let n = value;
  let idx = 0;
  while (n >= 1024 && idx < units.length - 1) {
    n /= 1024;
    idx += 1;
  }
  return `${n.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function stageLabel(stage?: string) {
  if (!stage) return "空闲";
  return STAGE_LABELS[stage] || stage;
}

function statusLabel(task?: TaskState | null) {
  if (!task || task.status === "idle") return "空闲";
  if (task.status === "running") return "运行中";
  if (task.status === "succeeded") return "已完成";
  return "失败";
}

function progressPercent(task?: TaskState | null) {
  const p = task?.progress;
  if (!p) return null;
  if (typeof p.percent === "number") return Math.max(0, Math.min(100, p.percent));
  if (p.current && p.total) return Math.max(0, Math.min(100, (p.current / p.total) * 100));
  return null;
}

function Metric({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="metric">
      <span className="label">{label}</span>
      <b>{value ?? "—"}</b>
    </div>
  );
}

function TopMetric({ label, value, tone }: { label: string; value?: string | number | null; tone?: "ok" | "warn" }) {
  return (
    <div>
      <span className="label">{label}</span>
      <span className={"v " + (tone || "")}>{value ?? "—"}</span>
    </div>
  );
}

function TaskPage({
  kind,
  title,
  summary,
  task,
  onStart,
}: {
  kind: TaskKind;
  title: string;
  summary: string;
  task: TaskState | null;
  onStart: (kind: TaskKind) => void;
}) {
  const isThisTask = task?.kind === kind;
  const running = task?.status === "running";
  const lockedByOther = running && !isThisTask;
  const percent = isThisTask ? progressPercent(task) : null;
  const p = isThisTask ? task?.progress : undefined;
  const logs = isThisTask ? task?.logs.slice(-12).reverse() : [];

  return (
    <section className="task-page">
      <div className="page-title">
        <div>
          <span className="label">workflow</span>
          <h1>{title}</h1>
          <p>{summary}</p>
        </div>
        <button className="primary-action" disabled={running} onClick={() => onStart(kind)}>
          {lockedByOther ? "等待当前任务" : running && isThisTask ? "运行中" : "开始执行"}
        </button>
      </div>

      <div className="task-layout">
        <div className="task-side">
          <div className="status-grid">
            <Metric label="状态" value={isThisTask ? statusLabel(task) : "未运行"} />
            <Metric label="阶段" value={isThisTask ? stageLabel(task?.stage) : "—"} />
            <Metric label="队列" value={p?.total ? `${p.current || 0}/${p.total}` : "—"} />
            <Metric label="下载" value={p?.downloaded_bytes ? `${formatBytes(p.downloaded_bytes)} / ${formatBytes(p.total_bytes)}` : "—"} />
          </div>

          <div className="progress-card">
            <div className="progress-copy">
              <span className="label">current</span>
              <b>{isThisTask ? task?.message : "等待启动"}</b>
              <small>{p?.file_name || p?.title || p?.file_path || "—"}</small>
            </div>
            <div className={"bar " + (percent === null && isThisTask && task?.status === "running" ? "indeterminate" : "")}>
              <span style={{ width: `${percent ?? 0}%` }} />
            </div>
            <div className="bar-foot">
              <span>{percent === null ? "不确定进度" : `${percent.toFixed(1)}%`}</span>
              <span>{p?.arxiv_id || p?.stage || ""}</span>
            </div>
          </div>

        </div>

        <div className="log-panel">
          <h2>实时日志</h2>
          {logs?.length ? (
            <div className="logs">
              {logs.map((log, idx) => (
                <div className={"log " + (log.level === "error" ? "err" : "")} key={`${log.ts}-${idx}`}>
                  <span className="mono">{log.ts.split("T").pop()}</span>
                  <b>{stageLabel(log.stage)}</b>
                  <p>{log.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-inline">暂无日志。</div>
          )}
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("main");
  const [draft, setDraft] = useState("");
  const [keywords, setKeywords] = useState<string[]>(["llm", "agent"]);
  const [mode, setMode] = useState<Mode>("auto");
  const [topK, setTopK] = useState(10);
  const [results, setResults] = useState<Result[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [taskError, setTaskError] = useState("");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [task, setTask] = useState<TaskState | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let stop = false;
    const tick = () => {
      Promise.all([fetchMeta(), fetchRuntime(), fetchTask()])
        .then(([m, r, t]) => {
          if (stop) return;
          setMeta(m);
          setRuntime(r);
          setTask(t);
          setOnline(true);
        })
        .catch(() => {
          if (!stop) setOnline(false);
        });
    };
    tick();
    const id = window.setInterval(tick, 1500);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  const addKw = () => {
    const parts = draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    setKeywords([...new Set([...keywords, ...parts])]);
    setDraft("");
  };
  const removeKw = (k: string) => setKeywords(keywords.filter((x) => x !== k));

  const runSearch = () => {
    if (!keywords.length) return;
    setLoading(true);
    setError("");
    search(keywords, mode, topK)
      .then((rs) => { setResults(rs); setOnline(true); })
      .catch((e) => { setError(String(e.message || e)); setResults([]); setOnline(false); })
      .finally(() => setLoading(false));
  };

  const launchTask = (kind: TaskKind) => {
    setTaskError("");
    startTask(kind)
      .then((next) => setTask(next))
      .catch((e) => setTaskError(String(e.message || e)));
  };

  const topStats = useMemo(() => {
    const summaryModels = runtime?.summary_models?.length ? runtime.summary_models.join(" / ") : "—";
    if (page === "main") {
      return [
        { label: "https proxy", value: runtime?.proxy?.https || "未启用", tone: runtime?.proxy?.https ? "ok" as const : undefined },
        { label: "data root", value: runtime?.root || "等待后端" },
        { label: "api_key", value: runtime?.api_key_exists ? "已找到" : "未找到", tone: runtime?.api_key_exists ? "ok" as const : "warn" as const },
        { label: "today", value: runtime?.today || "—" },
      ];
    }
    if (page === "summarize") {
      return [
        { label: "summary model", value: summaryModels },
        { label: "model count", value: runtime?.summary_models?.length ?? "—" },
        { label: "api_key", value: runtime?.api_key_exists ? "已找到" : "未找到", tone: runtime?.api_key_exists ? "ok" as const : "warn" as const },
        { label: "today", value: runtime?.today || "—" },
      ];
    }
    return [
      { label: "model", value: meta?.embedding_model || "—" },
      { label: "dim", value: meta?.dimension ?? "—" },
      { label: "vectors", value: meta?.total_vectors?.toLocaleString?.() ?? "—" },
      { label: "updated", value: meta?.updated_at ? meta.updated_at.replace("T", " ").slice(0, 19) : "—" },
    ];
  }, [meta, page, runtime]);

  return (
    <div className="app-shell">
      <main className="workspace">
        <header className="topbar">
          <div className="brand">
            <div className="glyph"></div>
            <div>
              <b>Trending Fetcher</b>
              <span className="label">single-window workstation</span>
            </div>
          </div>

          <nav className="topnav" aria-label="功能切换">
            {NAV.map((item) => (
              <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}>
                <b>{item.label}</b>
                <span>{item.desc}</span>
              </button>
            ))}
          </nav>

          <div className="topstats">
            {topStats.map((item) => (
              <TopMetric key={item.label} label={item.label} value={item.value} tone={item.tone} />
            ))}
          </div>
          <span className={"conn " + (online === true ? "on" : online === false ? "off" : "")}>
            {online === true ? "● 已连接" : online === false ? "● 后端启动中" : "● 连接中"}
          </span>
        </header>

        {taskError && <div className="task-error">{taskError}</div>}

        {page === "main" && (
          <TaskPage
            kind="main"
            title="Main 下载与增量建库"
            summary="执行 arXiv 历史刷新、GitHub Trending、HuggingFace Daily Papers PDF 下载，并把当天产出增量写入知识库。"
            task={task}
            onStart={launchTask}
          />
        )}

        {page === "summarize" && (
          <TaskPage
            kind="summarize"
            title="Summarize 摘要与翻译"
            summary="处理今日目录内 PDF 摘要、README 中文翻译，完成后可直接刷新知识库索引。"
            task={task}
            onStart={launchTask}
          />
        )}

        {page === "kb" && (
          <section className="kb-page">
            <div className="kb-actions">
              <div>
                <span className="label">knowledge base</span>
                <h1>知识库检索</h1>
                <p>保留原有搜索接口和本地文件打开能力；需要时可手动触发当天目录增量建库。</p>
              </div>
              <button className="primary-action ghost" disabled={task?.status === "running"} onClick={() => launchTask("kb-build")}>
                {task?.status === "running" ? "任务运行中" : "增量建库"}
              </button>
            </div>

            <div className="layout kb-layout">
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
                onRun={runSearch}
              />

              <div className="results">
                {loading ? (
                  <div className="loading">检索中…</div>
                ) : results === null ? (
                  <div className="empty-state">
                    <div className="big">还没有检索结果</div>
                    <div>在左侧添加关键词后点击“检索”。每条结果可用系统默认程序打开原文 PDF、摘要译文或 README。</div>
                  </div>
                ) : error ? (
                  <div className="empty-state">
                    <div className="big">后端未就绪</div>
                    <div>无法连接本地检索服务（{error}）。窗口启动时会自动拉起后端，请稍候。</div>
                  </div>
                ) : results.length === 0 ? (
                  <div className="empty-state"><div className="big">无匹配结果</div></div>
                ) : (
                  <div>
                    <div className="rhead">
                      <span className="count">{results.length} 条结果</span>
                      <span className="sub mono">{keywords.join(", ")} · {mode}</span>
                      <span className="rsort">按后端 rank 排序</span>
                    </div>
                    {results.map((it) => <ResultCard key={it.rank} item={it} mode={mode} keywords={keywords} />)}
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
