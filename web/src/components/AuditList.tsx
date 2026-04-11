import type { AuditEventRecord } from "../types";

interface AuditListProps {
  events: AuditEventRecord[];
}

export function AuditList({ events }: AuditListProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Audit</h2>
        <span className="muted">Newest first</span>
      </div>
      <div className="list audit-list">
        {events.length === 0 ? (
          <p className="empty-state">No audit events yet.</p>
        ) : (
          events.map((event) => (
            <div key={event.id} className="audit-item">
              <div className="list-item-title">{event.event_type}</div>
              <div className="list-item-meta">
                <span>{event.action_id ?? "no action"}</span>
                <span>{event.created_at}</span>
              </div>
              <pre>{JSON.stringify(event.event_payload, null, 2)}</pre>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

