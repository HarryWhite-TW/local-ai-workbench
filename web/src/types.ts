export interface AuditEventRecord {
  id: number;
  action_id: string | null;
  event_type: string;
  event_payload: Record<string, unknown>;
  created_at: string;
}

export interface ActionRecord {
  id: string;
  action_type: string;
  title: string;
  status: "preview" | "approved";
  preview_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
}

export interface RootFolderStatusRecord {
  root_folder: string | null;
  updated_at: string | null;
}

export interface DocumentScanResult {
  root_folder: string;
  found: number;
  created: number;
  skipped: number;
  scanned_at: string;
}

export interface DocumentListItemRecord {
  id: string;
  relative_path: string;
  file_type: "md" | "txt" | "pdf" | "docx";
  title: string;
  modified_at: string;
  scanned_at: string;
}

export interface DocumentSearchResultRecord {
  document_id: string;
  relative_path: string;
  title: string;
  file_type: "md" | "txt" | "pdf" | "docx";
  snippet: string;
}

export interface DocumentDetailRecord {
  id: string;
  relative_path: string;
  file_type: "md" | "txt" | "pdf" | "docx";
  title: string;
  size_bytes: number;
  modified_at: string;
  content_hash: string;
  content: string;
  scanned_at: string;
}

export interface SummaryArtifactRecord {
  id: string;
  document_id: string;
  method: "extractive_v1";
  source_content_hash: string;
  summary_text: string;
  created_at: string;
}
