import type { ActionRecord } from "../types";

interface ActionListProps {
  actions: ActionRecord[];
  selectedActionId: string | null;
  onSelect: (actionId: string) => void;
}

export function ActionList({ actions, selectedActionId, onSelect }: ActionListProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Actions</h2>
        <span className="muted">{actions.length} item(s)</span>
      </div>
      <div className="list">
        {actions.length === 0 ? (
          <p className="empty-state">No actions yet. Create a sample preview to start the flow.</p>
        ) : (
          actions.map((action) => (
            <button
              key={action.id}
              type="button"
              className={`list-item ${selectedActionId === action.id ? "selected" : ""}`}
              onClick={() => onSelect(action.id)}
            >
              <div className="list-item-title">{action.title}</div>
              <div className="list-item-meta">
                <span>{action.action_type}</span>
                <span className={`badge badge-${action.status}`}>{action.status}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </section>
  );
}

