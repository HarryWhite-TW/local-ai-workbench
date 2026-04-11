export type ActionType = "stub_email_draft" | "stub_calendar_event" | "stub_export";
export type ActionStatus = "preview" | "approved";

export interface ActionRecord {
  id: string;
  action_type: ActionType;
  title: string;
  status: ActionStatus;
  preview_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
}

export interface AuditEventRecord {
  id: number;
  action_id: string | null;
  event_type: string;
  event_payload: Record<string, unknown>;
  created_at: string;
}

export interface CreatePreviewRequest {
  action_type: ActionType;
  title: string;
  preview_payload: Record<string, unknown>;
}

