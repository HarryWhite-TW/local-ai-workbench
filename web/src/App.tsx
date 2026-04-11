import { useEffect, useState } from "react";

import {
  ApiError,
  generateDocumentSummary,
  getAuditEvents,
  getDocumentDetail,
  getDocumentSummary,
  getDocuments,
  getRootFolderStatus,
  scanDocuments
} from "./api";
import { AuditList } from "./components/AuditList";
import type {
  AuditEventRecord,
  DocumentDetailRecord,
  DocumentListItemRecord,
  RootFolderStatusRecord,
  SummaryArtifactRecord
} from "./types";

type SummaryState = "idle" | "loading" | "empty" | "ready";

export default function App() {
  const [rootFolder, setRootFolder] = useState<RootFolderStatusRecord | null>(null);
  const [documents, setDocuments] = useState<DocumentListItemRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventRecord[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<DocumentDetailRecord | null>(null);
  const [summaryArtifact, setSummaryArtifact] = useState<SummaryArtifactRecord | null>(null);
  const [summaryState, setSummaryState] = useState<SummaryState>("idle");
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [isLoadingDocument, setIsLoadingDocument] = useState(false);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadAudit() {
    const nextAuditEvents = await getAuditEvents();
    setAuditEvents(nextAuditEvents);
  }

  async function loadSelectedDocument(documentId: string) {
    setSelectedDocumentId(documentId);
    setIsLoadingDocument(true);
    setSelectedDocument(null);
    setSummaryState("loading");
    setSummaryArtifact(null);

    try {
      const detail = await getDocumentDetail(documentId);
      setSelectedDocument(detail);
    } catch (loadError) {
      setSelectedDocument(null);
      setSummaryState("idle");
      setIsLoadingDocument(false);

      if (loadError instanceof ApiError && loadError.status === 404) {
        setError("Selected document is no longer available.");
        setSelectedDocumentId(null);
        return;
      }

      setError(loadError instanceof Error ? loadError.message : "Failed to load document details.");
      return;
    }

    try {
      const artifact = await getDocumentSummary(documentId);
      setSummaryArtifact(artifact);
      setSummaryState("ready");
    } catch (loadError) {
      if (
        loadError instanceof ApiError &&
        loadError.status === 404 &&
        loadError.detail === "Summary artifact not found."
      ) {
        setSummaryArtifact(null);
        setSummaryState("empty");
        return;
      }

      if (
        loadError instanceof ApiError &&
        loadError.status === 404 &&
        loadError.detail === "Document not found."
      ) {
        setSelectedDocumentId(null);
        setSelectedDocument(null);
        setSummaryArtifact(null);
        setSummaryState("idle");
        setError("Selected document is no longer available.");
        return;
      }

      setSummaryArtifact(null);
      setSummaryState("empty");
      setError(loadError instanceof Error ? loadError.message : "Failed to load summary artifact.");
    } finally {
      setIsLoadingDocument(false);
    }
  }

  async function loadOverview(preferredDocumentId?: string | null) {
    setIsLoading(true);
    setError(null);

    try {
      const [nextRootFolder, nextDocuments, nextAuditEvents] = await Promise.all([
        getRootFolderStatus(),
        getDocuments(),
        getAuditEvents()
      ]);

      setRootFolder(nextRootFolder);
      setDocuments(nextDocuments);
      setAuditEvents(nextAuditEvents);

      if (nextDocuments.length === 0) {
        setSelectedDocumentId(null);
        setSelectedDocument(null);
        setSummaryArtifact(null);
        setSummaryState("idle");
        return;
      }

      const nextDocumentId =
        preferredDocumentId && nextDocuments.some((document) => document.id === preferredDocumentId)
          ? preferredDocumentId
          : nextDocuments[0].id;

      await loadSelectedDocument(nextDocumentId);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load document workspace.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadOverview();
  }, []);

  async function handleScan() {
    if (!rootFolder?.root_folder) {
      return;
    }

    setIsScanning(true);
    setError(null);
    try {
      await scanDocuments();
      await loadOverview(selectedDocumentId);
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : "Failed to scan documents.");
    } finally {
      setIsScanning(false);
    }
  }

  async function handleSelectDocument(documentId: string) {
    setError(null);
    await loadSelectedDocument(documentId);
  }

  async function handleGenerateSummary() {
    if (!selectedDocumentId) {
      return;
    }

    setIsGeneratingSummary(true);
    setError(null);
    try {
      const artifact = await generateDocumentSummary(selectedDocumentId);
      setSummaryArtifact(artifact);
      setSummaryState("ready");
      await loadAudit();
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "Failed to generate summary.");
    } finally {
      setIsGeneratingSummary(false);
    }
  }

  const hasRootFolder = Boolean(rootFolder?.root_folder);
  const hasDocuments = documents.length > 0;

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">M2 local documents prototype</p>
          <h1>Document Scan / Read / Summary</h1>
        </div>
        <p className="hero-copy">
          This local UI wires the existing root-folder, document scan, single-document read, summary artifact, and
          audit flow into one minimal workspace.
        </p>
      </header>

      <section className="panel status-panel">
        <div className="panel-header">
          <div>
            <h2>Root Folder</h2>
            <p className="muted compact">
              Configure the path via API first. This UI only reads the current root folder state.
            </p>
          </div>
          <button
            type="button"
            className="primary-button"
            disabled={!hasRootFolder || isScanning || isLoading}
            onClick={() => void handleScan()}
          >
            {isScanning ? "Scanning..." : "Scan documents"}
          </button>
        </div>
        <div className="root-folder-box">
          <div className="detail-row">
            <span className="detail-label">Current root folder</span>
            <span className={`status-pill ${hasRootFolder ? "configured" : "missing"}`}>
              {hasRootFolder ? "Configured" : "Not configured"}
            </span>
          </div>
          <pre>{rootFolder?.root_folder ?? "Set root folder with PUT /settings/root-folder before using Block D."}</pre>
        </div>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      {isLoading ? (
        <section className="panel">
          <p className="empty-state">Loading document workspace...</p>
        </section>
      ) : (
        <div className="workspace-grid">
          <section className="panel">
            <div className="panel-header">
              <h2>Documents</h2>
              <span className="muted">{documents.length} item(s)</span>
            </div>
            {hasDocuments ? (
              <div className="list">
                {documents.map((document) => (
                  <button
                    key={document.id}
                    type="button"
                    className={`list-item ${selectedDocumentId === document.id ? "selected" : ""}`}
                    onClick={() => void handleSelectDocument(document.id)}
                  >
                    <div className="list-item-title">{document.relative_path}</div>
                    <div className="list-item-meta">
                      <span>{document.file_type}</span>
                      <span>{document.modified_at}</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="empty-state">
                {hasRootFolder
                  ? "No indexed documents yet. Run a manual scan to load md/txt files from the configured root folder."
                  : "No root folder configured yet, so the document list is empty."}
              </p>
            )}
          </section>

          <div className="panel-stack">
            <section className="panel">
              <div className="panel-header">
                <h2>Document Content</h2>
                <span className="muted">
                  {selectedDocument ? selectedDocument.file_type.toUpperCase() : "No document selected"}
                </span>
              </div>
              {!selectedDocumentId ? (
                <p className="empty-state">Select a document to load its full content.</p>
              ) : isLoadingDocument && !selectedDocument ? (
                <p className="empty-state">Loading document content...</p>
              ) : selectedDocument ? (
                <div className="content-block">
                  <div className="detail-row">
                    <span className="detail-label">Path</span>
                    <span>{selectedDocument.relative_path}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Size</span>
                    <span>{selectedDocument.size_bytes} bytes</span>
                  </div>
                  <pre>{selectedDocument.content}</pre>
                </div>
              ) : (
                <p className="empty-state">Document content is unavailable.</p>
              )}
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Summary Artifact</h2>
                  <p className="muted compact">Deterministic extractive_v1 summary for the selected document.</p>
                </div>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!selectedDocumentId || isGeneratingSummary || isLoadingDocument}
                  onClick={() => void handleGenerateSummary()}
                >
                  {isGeneratingSummary ? "Generating..." : "Generate summary"}
                </button>
              </div>
              {!selectedDocumentId ? (
                <p className="empty-state">Select a document before generating a summary.</p>
              ) : summaryState === "loading" ? (
                <p className="empty-state">Loading latest summary artifact...</p>
              ) : summaryState === "empty" || !summaryArtifact ? (
                <p className="empty-state">No summary artifact yet. Generate one for the selected document.</p>
              ) : (
                <div className="content-block">
                  <div className="detail-row">
                    <span className="detail-label">Method</span>
                    <span>{summaryArtifact.method}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Created</span>
                    <span>{summaryArtifact.created_at}</span>
                  </div>
                  <div className="detail-row stacked">
                    <span className="detail-label">Summary</span>
                    <p className="summary-paragraph">{summaryArtifact.summary_text}</p>
                  </div>
                </div>
              )}
            </section>
          </div>

          <AuditList events={auditEvents} />
        </div>
      )}
    </main>
  );
}
