import type { ActionRecord, AuditEventRecord, CreatePreviewRequest } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function getActions(): Promise<ActionRecord[]> {
  return request<ActionRecord[]>("/actions");
}

export function createPreviewAction(payload: CreatePreviewRequest): Promise<ActionRecord> {
  return request<ActionRecord>("/actions/preview", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function approveAction(actionId: string): Promise<ActionRecord> {
  return request<ActionRecord>(`/actions/${actionId}/approve`, {
    method: "POST"
  });
}

export function getAuditEvents(): Promise<AuditEventRecord[]> {
  return request<AuditEventRecord[]>("/audit");
}

