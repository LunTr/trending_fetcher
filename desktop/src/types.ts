export interface KbRecord {
  title?: string;
  file_name?: string;
  file_type?: string;
  date?: string;
  section_title?: string;
  chunk_index?: number;
  chunk_total?: number;
  source_path: string;
  text?: string;
}

export interface Result {
  rank: number;
  score: number;
  snippet?: string;
  record: KbRecord;
}

export interface Meta {
  embedding_model?: string;
  dimension?: number;
  total_vectors?: number;
  updated_at?: string;
}

export type Mode = "auto" | "vector" | "keyword";

export type Page = "main" | "summarize" | "kb";
export type TaskKind = "main" | "summarize" | "kb-build";
export type TaskStatus = "idle" | "running" | "succeeded" | "failed";

export interface ProxyStatus {
  enabled: boolean;
  http?: string | null;
  https?: string | null;
  no_proxy?: string | null;
  source: string;
}

export interface RuntimeInfo {
  root: string;
  kb_dir: string;
  api_key: string;
  api_key_exists: boolean;
  today: string;
  proxy: ProxyStatus;
}

export interface TaskLog {
  ts: string;
  stage?: string;
  level?: string;
  message: string;
}

export interface TaskProgress {
  stage?: string;
  current?: number;
  total?: number;
  file_name?: string;
  file_path?: string;
  arxiv_id?: string;
  title?: string;
  downloaded_bytes?: number;
  total_bytes?: number;
  percent?: number | null;
  added_chunks?: number;
  total_vectors?: number;
}

export interface TaskState {
  id?: string | null;
  kind?: TaskKind | null;
  status: TaskStatus;
  stage: string;
  message: string;
  progress: TaskProgress;
  stats: Record<string, number | string>;
  logs: TaskLog[];
  started_at?: string | null;
  finished_at?: string | null;
}
