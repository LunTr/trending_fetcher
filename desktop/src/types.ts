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
}

export type Mode = "auto" | "vector" | "keyword";
