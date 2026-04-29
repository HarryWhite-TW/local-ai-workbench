import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  generateDocumentSummary,
  getAuditEvents,
  getDocumentDetail,
  getDocumentSummary,
  getDocuments,
  getRootFolderStatus,
  scanDocuments,
  searchDocuments,
  setRootFolder as saveRootFolder
} from "./api";
import { AuditList } from "./components/AuditList";
import type {
  AuditEventRecord,
  DocumentDetailRecord,
  DocumentListItemRecord,
  DocumentScanResult,
  DocumentSearchResultRecord,
  RootFolderStatusRecord,
  SummaryArtifactRecord
} from "./types";

type SummaryState = "idle" | "loading" | "empty" | "ready";

function getLatestScanResult(events: AuditEventRecord[]): DocumentScanResult | null {
  for (const event of events) {
    if (event.event_type !== "documents_scanned") {
      continue;
    }

    const { root_folder, found, created, skipped } = event.event_payload;
    if (
      typeof root_folder === "string" &&
      typeof found === "number" &&
      typeof created === "number" &&
      typeof skipped === "number"
    ) {
      return {
        root_folder,
        found,
        created,
        skipped,
        scanned_at: event.created_at
      };
    }
  }

  return null;
}

function formatScanSummary(scanResult: DocumentScanResult | null): string {
  if (!scanResult) {
    return "No scan run yet.";
  }

  return `${scanResult.found} found · ${scanResult.created} created · ${scanResult.skipped} skipped`;
}

function getErrorDetail(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export default function App() {
  const [rootFolder, setRootFolder] = useState<RootFolderStatusRecord | null>(null);
  const [documents, setDocuments] = useState<DocumentListItemRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventRecord[]>([]);
  const [lastScanResult, setLastScanResult] = useState<DocumentScanResult | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<DocumentDetailRecord | null>(null);
  const [summaryArtifact, setSummaryArtifact] = useState<SummaryArtifactRecord | null>(null);
  const [summaryState, setSummaryState] = useState<SummaryState>("idle");
  const [rootFolderInput, setRootFolderInput] = useState("");
  const [rootFolderMessage, setRootFolderMessage] = useState<string | null>(null);
  const [rootFolderError, setRootFolderError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [searchResults, setSearchResults] = useState<DocumentSearchResultRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [isLoadingDocument, setIsLoadingDocument] = useState(false);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [pendingSearchQuery, setPendingSearchQuery] = useState<string | null>(null);
  const [isSavingRootFolder, setIsSavingRootFolder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  async function loadAudit() {
    const nextAuditEvents = await getAuditEvents();
    setAuditEvents(nextAuditEvents);
    setLastScanResult(getLatestScanResult(nextAuditEvents));
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

      setError(
        `Could not load document details. ${getErrorDetail(
          loadError,
          "The API did not return an error detail."
        )} Run Scan documents to refresh the local index, then select the document again.`
      );
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
      setError(
        `Could not load the latest summary. ${getErrorDetail(
          loadError,
          "The API did not return an error detail."
        )} You can still read the document or generate a new summary.`
      );
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
      setRootFolderInput(nextRootFolder.root_folder ?? "");
      setDocuments(nextDocuments);
      setAuditEvents(nextAuditEvents);
      setLastScanResult(getLatestScanResult(nextAuditEvents));

      if (nextDocuments.length === 0) {
        setSelectedDocumentId(null);
        setSelectedDocument(null);
        setSummaryArtifact(null);
        setSummaryState("idle");
        setSearchResults([]);
        setActiveQuery("");
        return;
      }

      const nextDocumentId =
        preferredDocumentId && nextDocuments.some((document) => document.id === preferredDocumentId)
          ? preferredDocumentId
          : nextDocuments[0].id;

      await loadSelectedDocument(nextDocumentId);
    } catch (loadError) {
      setError(
        `Could not load the local workbench. ${getErrorDetail(
          loadError,
          "The API did not return an error detail."
        )} Confirm the API is running, then refresh the page.`
      );
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
      const result = await scanDocuments();
      setLastScanResult(result);
      setSearchInput("");
      setActiveQuery("");
      setSearchResults([]);
      setSearchError(null);
      await loadOverview(selectedDocumentId);
    } catch (scanError) {
      setError(
        `Could not scan documents. ${getErrorDetail(
          scanError,
          "The API did not return an error detail."
        )} Confirm the configured folder still exists, then try Scan documents again.`
      );
    } finally {
      setIsScanning(false);
    }
  }

  async function handleRootFolderSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedRootFolder = rootFolderInput.trim();

    setRootFolderMessage(null);
    setRootFolderError(null);

    if (!normalizedRootFolder) {
      setRootFolderError("Enter an absolute folder path before saving.");
      return;
    }

    setIsSavingRootFolder(true);
    setError(null);
    try {
      const nextRootFolder = await saveRootFolder(normalizedRootFolder);
      setRootFolder(nextRootFolder);
      setRootFolderInput(nextRootFolder.root_folder ?? "");
      setRootFolderMessage("Root folder saved. You can scan documents when ready.");
      await loadAudit();
    } catch (saveError) {
      setRootFolderError(
        `Could not save root folder. ${getErrorDetail(
          saveError,
          "The API did not return an error detail."
        )} Use an existing absolute folder path on this computer.`
      );
    } finally {
      setIsSavingRootFolder(false);
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
      setError(
        `Could not generate summary. ${getErrorDetail(
          generateError,
          "The API did not return an error detail."
        )} The source document stays unchanged; try again after selecting the document.`
      );
    } finally {
      setIsGeneratingSummary(false);
    }
  }

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearchError(null);

    const normalizedQuery = searchInput.trim();
    if (!normalizedQuery) {
      setActiveQuery("");
      setSearchResults([]);
      setPendingSearchQuery(null);
      return;
    }

    if (pendingSearchQuery !== null) {
      return;
    }

    setPendingSearchQuery(normalizedQuery);
    try {
      const results = await searchDocuments(normalizedQuery);
      setActiveQuery(normalizedQuery);
      setSearchResults(results);
      setPendingSearchQuery(null);
    } catch (searchRequestError) {
      setSearchError(
        `Search failed. ${getErrorDetail(
          searchRequestError,
          "The API did not return an error detail."
        )} Confirm the API is running and try again.`
      );
      setPendingSearchQuery(null);
    }
  }

  function handleClearSearch() {
    setSearchInput("");
    setActiveQuery("");
    setSearchResults([]);
    setSearchError(null);
    setPendingSearchQuery(null);
  }

  const hasRootFolder = Boolean(rootFolder?.root_folder);
  const hasDocuments = documents.length > 0;
  const hasCompletedScan = Boolean(lastScanResult);
  const latestScanFoundNoFiles = Boolean(lastScanResult && lastScanResult.found === 0);
  const hasActiveSearch = Boolean(activeQuery);
  const hasSearchResults = searchResults.length > 0;
  const normalizedSearchInput = searchInput.trim();
  const normalizedRootFolderInput = rootFolderInput.trim();
  const isSearching = pendingSearchQuery !== null;
  const canSaveRootFolder = !isLoading && !isScanning && !isSavingRootFolder && normalizedRootFolderInput.length > 0;
  const canSubmitSearch = hasDocuments && !isLoading && !isScanning && !isSearching && normalizedSearchInput.length > 0;
  const canClearSearch =
    !isSearching && (searchInput.length > 0 || activeQuery.length > 0 || searchResults.length > 0 || Boolean(searchError));
  const selectedDocumentInSearchResults = Boolean(
    selectedDocumentId && searchResults.some((result) => result.document_id === selectedDocumentId)
  );
  const showSearchIdleState = hasRootFolder && hasDocuments && !hasActiveSearch;
  const showSearchNoMatchState = hasRootFolder && hasDocuments && hasActiveSearch && !hasSearchResults;
  const showSearchResultState = hasRootFolder && hasDocuments && hasActiveSearch && hasSearchResults;
  const showSearchOutsideResultHint = showSearchResultState && Boolean(selectedDocumentId) && !selectedDocumentInSearchResults;

  return (
    <main className="app-shell">
      <header className="panel workspace-header">
        <div className="workspace-header-top">
          <div className="workspace-title-block">
            <p className="eyebrow">Local document assistant v1</p>
            <h1>Local Document Workbench</h1>
            <p className="workspace-intro">
              A local document workspace for scan, read, search, summary, and audit. Search and summary stay attached
              to the selected document instead of taking over the page.
            </p>
          </div>
          <div className="workspace-header-actions">
            <span className={`status-pill ${hasRootFolder ? "configured" : "missing"}`}>
              {hasRootFolder ? "Root folder ready" : "Root folder required"}
            </span>
            <button
              type="button"
              className="primary-button"
              disabled={!hasRootFolder || isScanning || isLoading || isSavingRootFolder}
              onClick={() => void handleScan()}
            >
              {isScanning ? "Scanning..." : "Scan documents"}
            </button>
          </div>
        </div>

        <div className="header-status-grid">
          <div className="status-card">
            <span className="status-card-label">Data source</span>
            <strong>{hasRootFolder ? "Root folder configured" : "Choose a local folder to begin"}</strong>
            <form className="root-folder-form" onSubmit={(event) => void handleRootFolderSubmit(event)}>
              <label htmlFor="root-folder-input" className="sr-only">
                Local root folder
              </label>
              <input
                id="root-folder-input"
                type="text"
                className="root-folder-input"
                value={rootFolderInput}
                onChange={(event) => {
                  setRootFolderInput(event.target.value);
                  setRootFolderMessage(null);
                  setRootFolderError(null);
                }}
                placeholder={"C:\\Users\\harry\\Documents\\notes"}
                disabled={isLoading || isSavingRootFolder || isScanning}
              />
              <button type="submit" className="secondary-button" disabled={!canSaveRootFolder}>
                {isSavingRootFolder ? "Saving..." : hasRootFolder ? "Update folder" : "Save folder"}
              </button>
            </form>
            <p>
              {rootFolder?.root_folder ??
                "Paste an existing absolute folder path. The workbench indexes supported files only after you run Scan documents."}
            </p>
            {rootFolderMessage ? <p className="inline-success">{rootFolderMessage}</p> : null}
            {rootFolderError ? <p className="inline-error">{rootFolderError}</p> : null}
          </div>

          <div className="status-card">
            <span className="status-card-label">Scan status</span>
            <strong>{lastScanResult ? `Last scan: ${lastScanResult.scanned_at}` : "No scan completed yet"}</strong>
            <p>
              {!hasRootFolder
                ? "Save a root folder before scanning."
                : latestScanFoundNoFiles
                  ? "Scan completed but found no supported md, txt, pdf, or docx files. Add supported files or choose another folder, then scan again."
                  : hasCompletedScan
                    ? formatScanSummary(lastScanResult)
                    : "Ready for the first manual scan. Scan documents reads the configured folder into the local SQLite index."}
            </p>
          </div>

          <div className="status-card">
            <span className="status-card-label">Workspace focus</span>
            <strong>
              {selectedDocument
                ? selectedDocument.title
                : !hasRootFolder
                  ? "Set a root folder to start"
                  : hasDocuments
                    ? "Select a document from the left column"
                    : latestScanFoundNoFiles
                      ? "No supported files found"
                      : "Scan documents to start reading"}
            </strong>
            <p>
              {selectedDocument
                ? `${selectedDocument.file_type.toUpperCase()} · ${selectedDocument.relative_path}`
                : !hasRootFolder
                  ? "The workbench stays local. Choose one folder, save it, then scan when ready."
                  : latestScanFoundNoFiles
                    ? "The latest scan finished, but there are no supported files to open yet."
                    : `${documents.length} indexed document(s) currently loaded in this workspace.`}
            </p>
          </div>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      {isLoading ? (
        <section className="panel loading-panel">
          <p className="empty-state">Loading the local document workspace...</p>
        </section>
      ) : (
        <div className="workspace-layout">
          <aside className="left-column panel-stack">
            <section className="panel search-panel">
              <div className="panel-header">
                <div>
                  <h2>Search</h2>
                  <p className="muted compact">
                    Manual keyword search across indexed title, relative path, and extracted content.
                  </p>
                </div>
              </div>
              <form className="search-form" onSubmit={(event) => void handleSearchSubmit(event)}>
                <input
                  type="text"
                  className="search-input"
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search indexed documents"
                  disabled={!hasDocuments || isLoading || isScanning || isSearching}
                />
                <div className="search-actions">
                  <button type="submit" className="secondary-button" disabled={!canSubmitSearch}>
                    {isSearching ? "Searching..." : "Search"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button clear-button"
                    disabled={!canClearSearch}
                    onClick={handleClearSearch}
                  >
                    Clear search
                  </button>
                </div>
              </form>
              {searchError ? <div className="error-banner search-error">{searchError}</div> : null}
              {!hasRootFolder ? (
                <p className="empty-state">
                  Save a root folder first. Search uses the local index created by Scan documents.
                </p>
              ) : !hasDocuments ? (
                <p className="empty-state">
                  {latestScanFoundNoFiles
                    ? "The latest scan found no supported files, so there is nothing to search yet."
                    : "Run Scan documents before searching. Search covers indexed title, relative path, and extracted content."}
                </p>
              ) : showSearchIdleState ? (
                <>
                  <p className="empty-state">Search is ready. Submit a keyword to build a local result set.</p>
                  <p className="muted compact">
                    Clear search only resets the search state. It does not reload document detail or summary.
                  </p>
                </>
              ) : showSearchNoMatchState ? (
                <>
                  <p className="empty-state">No indexed documents matched "{activeQuery}".</p>
                  <p className="muted compact">
                    Try a different keyword, or scan again if files changed in the configured folder.
                  </p>
                </>
              ) : showSearchResultState ? (
                <>
                  <div className="search-summary-row">
                    <span className="search-query-chip">Active query: "{activeQuery}"</span>
                    <span className="muted">{searchResults.length} result(s)</span>
                  </div>
                  <p className={`search-context ${showSearchOutsideResultHint ? "warning" : ""}`}>
                    {showSearchOutsideResultHint
                      ? "The selected document is outside the current results. Search results stay in place until you clear them."
                      : "The selected document belongs to the current result set."}
                  </p>
                  <div className="list search-results-list">
                    {searchResults.map((result) => (
                      <button
                        key={`${result.document_id}-${result.relative_path}`}
                        type="button"
                        className={`list-item ${selectedDocumentId === result.document_id ? "selected" : ""}`}
                        onClick={() => void handleSelectDocument(result.document_id)}
                      >
                        <div className="list-item-title">{result.title}</div>
                        <div className="list-item-meta">
                          <span>{result.file_type}</span>
                          <span>{result.relative_path}</span>
                        </div>
                        {selectedDocumentId === result.document_id ? (
                          <div className="search-selection-note">Open in the detail and summary panels.</div>
                        ) : null}
                        <p className="search-snippet">{result.snippet}</p>
                      </button>
                  ))}
                </div>
              </>
            ) : null}
          </section>

            <section className="panel documents-panel">
              <div className="panel-header">
                <div>
                  <h2>Documents</h2>
                  <p className="muted compact">The local index currently loaded in this workbench.</p>
                </div>
                <span className="muted">{documents.length} item(s)</span>
              </div>
              {hasDocuments ? (
                <div className="list documents-list">
                  {documents.map((document) => (
                    <button
                      key={document.id}
                      type="button"
                      className={`list-item ${selectedDocumentId === document.id ? "selected" : ""}`}
                      onClick={() => void handleSelectDocument(document.id)}
                    >
                      <div className="list-item-title">{document.title}</div>
                      <div className="list-item-meta">
                        <span>{document.file_type}</span>
                        <span>{document.relative_path}</span>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="empty-state">
                  {!hasRootFolder
                    ? "Save a root folder in Data source, then run Scan documents to build the local index."
                    : latestScanFoundNoFiles
                      ? "The latest scan found no supported files. Add md, txt, pdf, or docx files to the configured folder, or choose another folder."
                      : "No indexed documents yet. Run Scan documents to load files from the configured root folder."}
                </p>
              )}
            </section>
          </aside>

          <section className="center-column">
            <section className="panel detail-panel">
              <div className="panel-header">
                <div>
                  <h2>Document detail</h2>
                  <p className="muted compact">
                    The main reading area shows extracted plain text for the selected document.
                  </p>
                </div>
                <span className="muted">
                  {selectedDocument ? selectedDocument.file_type.toUpperCase() : "No document selected"}
                </span>
              </div>
              {!selectedDocumentId ? (
                <p className="empty-state">
                  {!hasRootFolder
                    ? "Configure a root folder and run a scan before opening document detail."
                    : !hasDocuments && latestScanFoundNoFiles
                      ? "No document can be selected because the latest scan found no supported files."
                      : !hasDocuments
                        ? "Run Scan documents, then select a document from the left column to inspect its extracted content."
                        : "Select a document from the left column to inspect its extracted content."}
                </p>
              ) : isLoadingDocument && !selectedDocument ? (
                <p className="empty-state">Loading extracted document content...</p>
              ) : selectedDocument ? (
                <div className="detail-layout">
                  <div className="detail-meta-grid">
                    <div className="meta-card">
                      <span className="detail-label">Title</span>
                      <strong>{selectedDocument.title}</strong>
                    </div>
                    <div className="meta-card">
                      <span className="detail-label">Relative path</span>
                      <strong>{selectedDocument.relative_path}</strong>
                    </div>
                    <div className="meta-card">
                      <span className="detail-label">Modified</span>
                      <strong>{selectedDocument.modified_at}</strong>
                    </div>
                    <div className="meta-card">
                      <span className="detail-label">Scanned</span>
                      <strong>{selectedDocument.scanned_at}</strong>
                    </div>
                  </div>
                  <div className="content-block detail-content-block">
                    <div className="detail-row">
                      <span className="detail-label">Extracted content</span>
                      <span className="muted">{selectedDocument.size_bytes} bytes</span>
                    </div>
                    <pre>{selectedDocument.content}</pre>
                  </div>
                </div>
              ) : (
                <p className="empty-state">Document detail is unavailable.</p>
              )}
            </section>
          </section>

          <aside className="right-column panel-stack">
            <section className="panel summary-panel">
              <div className="panel-header">
                <div>
                  <h2>Summary</h2>
                  <p className="muted compact">
                    Deterministic extractive_v1 summary for the selected document. This is the main secondary panel.
                  </p>
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
                <p className="empty-state">
                  {!hasRootFolder
                    ? "Summary stays unavailable until a root folder is configured, scanned, and a document is selected."
                    : !hasDocuments && latestScanFoundNoFiles
                      ? "There is no document to summarize because the latest scan found no supported files."
                      : !hasDocuments
                        ? "Run Scan documents, then choose a document before generating or reviewing a summary."
                        : "Choose a document before generating or reviewing a summary."}
                </p>
              ) : summaryState === "loading" ? (
                <p className="empty-state">Loading the latest summary artifact for this document...</p>
              ) : summaryState === "empty" || !summaryArtifact ? (
                <>
                  <p className="empty-state">No summary artifact exists for the selected document yet.</p>
                  <p className="muted compact">
                    Generate one to keep a grounded, deterministic summary beside the main reading view.
                  </p>
                </>
              ) : (
                <div className="content-block summary-content-block">
                  <div className="detail-row">
                    <span className="detail-label">Method</span>
                    <span>{summaryArtifact.method}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Created</span>
                    <span>{summaryArtifact.created_at}</span>
                  </div>
                  <div className="detail-row stacked">
                    <span className="detail-label">Summary text</span>
                    <p className="summary-paragraph">{summaryArtifact.summary_text}</p>
                  </div>
                </div>
              )}
            </section>
            <div className="audit-panel-wrap">
              <AuditList
                events={auditEvents}
                emptyMessage="Audit events will appear after saving a root folder, scanning documents, or generating a summary."
              />
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
