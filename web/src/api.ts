import type {
  AuditEventRecord,
  DocumentDetailRecord,
  DocumentListItemRecord,
  DocumentSearchResultRecord,
  DocumentScanResult,
  ObsidianExportPreviewRecord,
  ObsidianExportWriteResultRecord,
  RootFolderStatusRecord,
  SummaryArtifactRecord
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  const responseText = await response.text();
  const responseBody = responseText ? JSON.parse(responseText) : null;

  if (!response.ok) {
    const detail =
      responseBody && typeof responseBody === "object" && "detail" in responseBody
        ? String(responseBody.detail)
        : `Request failed with status ${response.status}`;
    throw new ApiError(response.status, detail);
  }

  return responseBody as T;
}

export function getRootFolderStatus(): Promise<RootFolderStatusRecord> {
  return request<RootFolderStatusRecord>("/settings/root-folder");
}

export function setRootFolder(rootFolder: string): Promise<RootFolderStatusRecord> {
  return request<RootFolderStatusRecord>("/settings/root-folder", {
    method: "PUT",
    body: JSON.stringify({ root_folder: rootFolder })
  });
}

export function scanDocuments(): Promise<DocumentScanResult> {
  return request<DocumentScanResult>("/documents/scan", {
    method: "POST"
  });
}

export function getDocuments(): Promise<DocumentListItemRecord[]> {
  return request<DocumentListItemRecord[]>("/documents");
}

export function searchDocuments(query: string): Promise<DocumentSearchResultRecord[]> {
  return request<DocumentSearchResultRecord[]>(`/documents/search?q=${encodeURIComponent(query)}`);
}

export function getDocumentDetail(documentId: string): Promise<DocumentDetailRecord> {
  return request<DocumentDetailRecord>(`/documents/${documentId}`);
}

export function getDocumentSummary(documentId: string): Promise<SummaryArtifactRecord> {
  return request<SummaryArtifactRecord>(`/documents/${documentId}/summary`);
}

export function generateDocumentSummary(documentId: string): Promise<SummaryArtifactRecord> {
  return request<SummaryArtifactRecord>(`/documents/${documentId}/summary`, {
    method: "POST"
  });
}

export function getAuditEvents(): Promise<AuditEventRecord[]> {
  return request<AuditEventRecord[]>("/audit");
}


export function getObsidianExportPreview(documentId: string): Promise<ObsidianExportPreviewRecord> {
  return request<ObsidianExportPreviewRecord>(`/documents/${documentId}/obsidian-preview`);
}

export function writeObsidianExport(
  documentId: string,
  exportFolder: string,
  approved = true
): Promise<ObsidianExportWriteResultRecord> {
  return request<ObsidianExportWriteResultRecord>(`/documents/${documentId}/obsidian-export`, {
    method: "POST",
    body: JSON.stringify({ export_folder: exportFolder, approved })
  });
}
