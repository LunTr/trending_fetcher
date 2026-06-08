import datetime
import os
import sys
import threading
import traceback
import urllib.parse
import urllib.request
import uuid

sys.dont_write_bytecode = True

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from search import build_query, clean_snippet, load_meta, parse_keywords, search_kb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(
    os.environ.get("TRENDING_FETCHER_DATA_DIR")
    or os.path.join(HERE, "..")
)          # data lives one level up in dev, or in app data after packaging
KB_DIR = os.path.join(ROOT, "kb_store")
API_KEY = os.environ.get("TRENDING_FETCHER_API_KEY") or os.path.join(ROOT, "API_KEY.json")
os.environ.setdefault("TRENDING_FETCHER_DATA_DIR", ROOT)
os.environ.setdefault("TRENDING_FETCHER_API_KEY", API_KEY)

app = FastAPI(title="KB Search")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def mask_proxy(value):
    if not value:
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "***"
    return value


def proxy_status():
    proxies = urllib.request.getproxies()
    return {
        "enabled": bool(proxies),
        "http": mask_proxy(proxies.get("http")),
        "https": mask_proxy(proxies.get("https")),
        "no_proxy": os.environ.get("NO_PROXY") or os.environ.get("no_proxy"),
        "source": "system/env" if proxies else "none",
    }


class TaskManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = self.idle_state()

    def idle_state(self):
        return {
            "id": None,
            "kind": None,
            "status": "idle",
            "stage": "idle",
            "message": "空闲",
            "progress": {},
            "stats": {},
            "logs": [],
            "started_at": None,
            "finished_at": None,
        }

    def snapshot(self):
        with self.lock:
            return {
                **self.state,
                "progress": dict(self.state.get("progress") or {}),
                "stats": dict(self.state.get("stats") or {}),
                "logs": list(self.state.get("logs") or []),
            }

    def start(self, kind):
        if kind not in {"main", "summarize", "kb-build"}:
            raise HTTPException(status_code=404, detail="Unknown task")
        with self.lock:
            if self.state.get("status") == "running":
                raise HTTPException(status_code=409, detail="Another task is already running")
            task_id = str(uuid.uuid4())
            self.state = {
                "id": task_id,
                "kind": kind,
                "status": "running",
                "stage": "starting",
                "message": "任务启动中",
                "progress": {},
                "stats": {},
                "logs": [],
                "started_at": now_iso(),
                "finished_at": None,
            }
        thread = threading.Thread(target=self.run, args=(task_id, kind), daemon=True)
        thread.start()
        return self.snapshot()

    def reporter_for(self, task_id):
        def report(event):
            self.apply_event(task_id, event)
        return report

    def apply_event(self, task_id, event):
        if not isinstance(event, dict):
            event = {"event": "log", "message": str(event)}
        stamped = {**event, "ts": now_iso()}
        with self.lock:
            if self.state.get("id") != task_id:
                return
            stage = stamped.get("stage")
            if stage:
                self.state["stage"] = stage
            message = stamped.get("message")
            if message:
                self.state["message"] = message
            event_name = stamped.get("event")
            if event_name in {"queue", "download_start", "download_progress", "download_done", "kb_file", "kb_progress"}:
                progress = {
                    key: value for key, value in stamped.items()
                    if key not in {"event", "ts", "message"}
                }
                self.state["progress"].update(progress)
            if event_name == "stats":
                self.state["stats"].update({
                    key: value for key, value in stamped.items()
                    if key not in {"event", "ts", "stage", "message"}
                })
            if event_name == "log":
                logs = self.state.setdefault("logs", [])
                logs.append({
                    "ts": stamped["ts"],
                    "stage": stamped.get("stage"),
                    "level": stamped.get("level", "info"),
                    "message": message or "",
                })
                del logs[:-200]

    def finish(self, task_id, status, message):
        with self.lock:
            if self.state.get("id") != task_id:
                return
            self.state["status"] = status
            self.state["message"] = message
            self.state["finished_at"] = now_iso()

    def run(self, task_id, kind):
        reporter = self.reporter_for(task_id)
        try:
            reporter({"event": "log", "stage": "starting", "message": f"Starting {kind} task"})
            if kind == "main":
                import main as fetch_main
                fetch_main.run_main(data_root=ROOT, reporter=reporter, build_index=True)
            elif kind == "summarize":
                import summarize as summarize_job
                summarize_job.process_files(data_root=ROOT, reporter=reporter, build_index=True)
            else:
                import createbase
                source_dir = os.path.join(ROOT, today_str())
                createbase.build_kb(source_dir=source_dir, kb_dir=KB_DIR, api_key_path=API_KEY, reporter=reporter)
            self.finish(task_id, "succeeded", "任务完成")
        except Exception as exc:
            reporter({
                "event": "log",
                "stage": "failed",
                "level": "error",
                "message": f"{exc}\n{traceback.format_exc()}",
            })
            self.finish(task_id, "failed", str(exc))


tasks = TaskManager()


@app.get("/runtime")
def runtime():
    return {
        "root": ROOT,
        "kb_dir": KB_DIR,
        "api_key": API_KEY,
        "api_key_exists": os.path.exists(API_KEY),
        "today": today_str(),
        "proxy": proxy_status(),
    }


@app.get("/meta")
def meta():
    m = load_meta(os.path.join(KB_DIR, "index_meta.json")) or {}
    return {
        "embedding_model": m.get("embedding_model"),
        "dimension": m.get("dimension"),
        "total_vectors": m.get("total_vectors"),
        "updated_at": m.get("updated_at"),
    }


@app.get("/search")
def search(q: str = Query(""), mode: str = Query("auto"), top: int = Query(10)):
    keywords = parse_keywords(q)
    results = search_kb(build_query(q), keywords, KB_DIR, API_KEY, top, mode)
    for item in results:
        item["snippet"] = clean_snippet(item["record"].get("text", ""))
    return {"keywords": keywords, "mode": mode, "results": results}


@app.get("/tasks/current")
def current_task():
    return tasks.snapshot()


@app.post("/tasks/{kind}")
def start_task(kind: str):
    return tasks.start(kind)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
