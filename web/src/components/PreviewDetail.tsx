import type { ActionRecord } from "../types";

interface PreviewDetailProps {
  action: ActionRecord | null;
  isSubmitting: boolean;
  onApprove: (actionId: string) => void;
  onCreateSample: () => void;
}

export function PreviewDetail({
  action,
  isSubmitting,
  onApprove,
  onCreateSample
}: PreviewDetailProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Preview</h2>
        <button type="button" className="secondary-button" onClick={onCreateSample} disabled={isSubmitting}>
          Create sample preview
        </button>
      </div>

      {action ? (
        <div className="preview-detail">
          <div className="detail-row">
            <span className="detail-label">Title</span>
            <span>{action.title}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Type</span>
            <span>{action.action_type}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Status</span>
            <span className={`badge badge-${action.status}`}>{action.status}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Created</span>
            <span>{action.created_at}</span>
          </div>
          <div className="detail-row stacked">
            <span className="detail-label">Preview payload</span>
            <pre>{JSON.stringify(action.preview_payload, null, 2)}</pre>
          </div>
          <button
            type="button"
            className="primary-button"
            disabled={isSubmitting || action.status !== "preview"}
            onClick={() => onApprove(action.id)}
          >
            {action.status === "approved" ? "Approved" : isSubmitting ? "Approving..." : "Approve"}
          </button>
        </div>
      ) : (
        <p className="empty-state">Select an action to inspect its preview payload.</p>
      )}
    </section>
  );
}

