import { openPath } from "@tauri-apps/plugin-opener";
import type { Meta, Mode, Result } from "./types";

const API = "http://127.0.0.1:8000"; // resident Python search service (auto-started by the shell)

export async function fetchMeta(): Promise<Meta> {
  const r = await fetch(`${API}/meta`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function search(keywords: string[], mode: Mode, top: number): Promise<Result[]> {
  const url = `${API}/search?q=${encodeURIComponent(keywords.join(","))}&mode=${mode}&top=${top}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const d = await r.json();
  return d.results ?? [];
}

// open a local file with the system default program — native, no browser, no HTTP
export function openLocal(path: string): Promise<void> {
  return openPath(path);
}
