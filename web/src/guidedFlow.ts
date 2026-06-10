export type GuidedFlowStep =
  | "set-root"
  | "scan"
  | "select-document"
  | "summarize"
  | "preview"
  | "check-destination"
  | "export"
  | "complete";

export type GuidedFlowAction =
  | "save-root-folder"
  | "scan-documents"
  | "select-document"
  | "generate-summary"
  | "preview-markdown"
  | "check-destination"
  | "export-markdown"
  | "review-result";

export interface GuidedFlowInput {
  hasRootFolder: boolean;
  hasCompletedScan: boolean;
  documentCount: number;
  selectedDocumentId: string | null;
  selectedDocumentLoaded: boolean;
  summaryDocumentId: string | null;
  previewDocumentId: string | null;
  destinationCanExport: boolean;
  exportResultDocumentId: string | null;
  isLoading: boolean;
  isScanning: boolean;
  isLoadingDocument: boolean;
  isGeneratingSummary: boolean;
  isLoadingPreview: boolean;
  isCheckingDestination: boolean;
  isWritingExport: boolean;
}

export interface GuidedFlowState {
  step: GuidedFlowStep;
  primaryAction: GuidedFlowAction;
  title: string;
  description: string;
  primaryLabel: string;
  isPrimaryDisabled: boolean;
  completedSteps: GuidedFlowStep[];
  activeStep: GuidedFlowStep;
  hasCurrentSummary: boolean;
  hasCurrentPreview: boolean;
  hasCurrentExportResult: boolean;
}

interface StepCopy {
  title: string;
  description: string;
  primaryLabel: string;
}

const STEP_COPY: Record<GuidedFlowStep, StepCopy> = {
  "set-root": {
    title: "設定本機資料來源",
    description: "選擇一個本機資料夾，工作台只會處理你明確指定的文件來源。",
    primaryLabel: "設定資料夾"
  },
  scan: {
    title: "掃描本機文件",
    description: "建立目前資料夾的本機索引，讓搜尋、閱讀、摘要與匯出可以使用同一份文件清單。",
    primaryLabel: "掃描文件"
  },
  "select-document": {
    title: "選擇要處理的文件",
    description: "從本機索引中選擇一份文件，後續摘要與 Markdown 匯出會以這份文件為主。",
    primaryLabel: "選擇文件"
  },
  summarize: {
    title: "產生文件摘要",
    description: "摘要會成為後續 Markdown 筆記的主要上下文，也能幫助你快速確認文件重點。",
    primaryLabel: "產生摘要"
  },
  preview: {
    title: "預覽 Markdown 筆記",
    description: "匯出前先檢查 Markdown 內容，避免建立不符合預期的筆記。",
    primaryLabel: "預覽 Markdown"
  },
  "check-destination": {
    title: "檢查匯出目的地",
    description: "確認目標資料夾可用，並避免覆蓋既有 Markdown 文件。",
    primaryLabel: "檢查目的地"
  },
  export: {
    title: "匯出 Markdown 筆記",
    description: "把目前選中文件的摘要與上下文寫成一份本機 Markdown 文件。",
    primaryLabel: "匯出 Markdown"
  },
  complete: {
    title: "檢查匯出結果",
    description: "Markdown 已完成匯出，可以複製路徑、打開文件，或開始處理下一份文件。",
    primaryLabel: "查看結果"
  }
};

const ACTION_BY_STEP: Record<GuidedFlowStep, GuidedFlowAction> = {
  "set-root": "save-root-folder",
  scan: "scan-documents",
  "select-document": "select-document",
  summarize: "generate-summary",
  preview: "preview-markdown",
  "check-destination": "check-destination",
  export: "export-markdown",
  complete: "review-result"
};

const ORDERED_STEPS: GuidedFlowStep[] = [
  "set-root",
  "scan",
  "select-document",
  "summarize",
  "preview",
  "check-destination",
  "export",
  "complete"
];

export function getGuidedDocumentId(record: unknown): string | null {
  if (!record || typeof record !== "object" || !("document_id" in record)) {
    return null;
  }

  const documentId = (record as { document_id?: unknown }).document_id;
  return typeof documentId === "string" && documentId.length > 0 ? documentId : null;
}

function getCompletedSteps(step: GuidedFlowStep): GuidedFlowStep[] {
  const activeIndex = ORDERED_STEPS.indexOf(step);

  if (activeIndex <= 0) {
    return [];
  }

  return ORDERED_STEPS.slice(0, activeIndex);
}

function isCurrentDocumentResult(selectedDocumentId: string | null, resultDocumentId: string | null): boolean {
  return Boolean(selectedDocumentId && resultDocumentId && selectedDocumentId === resultDocumentId);
}

export function deriveGuidedFlowState(input: GuidedFlowInput): GuidedFlowState {
  const hasCurrentSummary = isCurrentDocumentResult(input.selectedDocumentId, input.summaryDocumentId);
  const hasCurrentPreview = isCurrentDocumentResult(input.selectedDocumentId, input.previewDocumentId);
  const hasCurrentExportResult = isCurrentDocumentResult(input.selectedDocumentId, input.exportResultDocumentId);

  let step: GuidedFlowStep = "complete";

  if (!input.hasRootFolder) {
    step = "set-root";
  } else if (!input.hasCompletedScan) {
    step = "scan";
  } else if (input.documentCount === 0 || !input.selectedDocumentId || !input.selectedDocumentLoaded) {
    step = "select-document";
  } else if (!hasCurrentSummary) {
    step = "summarize";
  } else if (!hasCurrentPreview) {
    step = "preview";
  } else if (!input.destinationCanExport) {
    step = "check-destination";
  } else if (!hasCurrentExportResult) {
    step = "export";
  }

  const copy = STEP_COPY[step];
  const isAnyGlobalLoading = input.isLoading || input.isScanning || input.isLoadingDocument;
  const isPrimaryDisabled =
    isAnyGlobalLoading ||
    input.isGeneratingSummary ||
    input.isLoadingPreview ||
    input.isCheckingDestination ||
    input.isWritingExport ||
    step === "select-document" ||
    step === "complete";

  return {
    step,
    primaryAction: ACTION_BY_STEP[step],
    title: copy.title,
    description: copy.description,
    primaryLabel: copy.primaryLabel,
    isPrimaryDisabled,
    completedSteps: getCompletedSteps(step),
    activeStep: step,
    hasCurrentSummary,
    hasCurrentPreview,
    hasCurrentExportResult
  };
}
