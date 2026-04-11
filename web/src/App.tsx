import { useEffect, useState } from "react";

import { approveAction, createPreviewAction, getActions, getAuditEvents } from "./api";
import { ActionList } from "./components/ActionList";
import { AuditList } from "./components/AuditList";
import { PreviewDetail } from "./components/PreviewDetail";
import type { ActionRecord, AuditEventRecord } from "./types";

const samplePreview = {
  action_type: "stub_email_draft" as const,
  title: "Draft follow-up email",
  preview_payload: {
    subject: "Follow-up",
    to: ["demo@example.com"],
    body: "Thanks for the update. Here is a suggested follow-up draft."
  }
};

export default function App() {
  const [actions, setActions] = useState<ActionRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventRecord[]>([]);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setError(null);
    setIsLoading(true);
    try {
      const [nextActions, nextAuditEvents] = await Promise.all([getActions(), getAuditEvents()]);
      setActions(nextActions);
      setAuditEvents(nextAuditEvents);
      setSelectedActionId((current) => {
        if (current && nextActions.some((action) => action.id === current)) {
          return current;
        }
        return nextActions[0]?.id ?? null;
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load prototype data.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleCreateSample() {
    setIsSubmitting(true);
    setError(null);
    try {
      const action = await createPreviewAction(samplePreview);
      await loadData();
      setSelectedActionId(action.id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to create sample preview.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleApprove(actionId: string) {
    setIsSubmitting(true);
    setError(null);
    try {
      await approveAction(actionId);
      await loadData();
      setSelectedActionId(actionId);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to approve action.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const selectedAction = actions.find((action) => action.id === selectedActionId) ?? null;

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">M1 local prototype</p>
          <h1>Preview / Approve / Audit</h1>
        </div>
        <p className="hero-copy">
          This local UI exercises the controlled action flow without real LLM, Google, or external writes.
        </p>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      {isLoading ? (
        <section className="panel">
          <p className="empty-state">Loading prototype data...</p>
        </section>
      ) : (
        <div className="grid">
          <ActionList
            actions={actions}
            selectedActionId={selectedActionId}
            onSelect={setSelectedActionId}
          />
          <PreviewDetail
            action={selectedAction}
            isSubmitting={isSubmitting}
            onApprove={handleApprove}
            onCreateSample={handleCreateSample}
          />
          <AuditList events={auditEvents} />
        </div>
      )}
    </main>
  );
}

