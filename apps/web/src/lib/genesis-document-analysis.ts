import type { DocumentRecord } from "./documents";

export type GenesisDocumentSource = {
  document_id: string;
  title: string;
  version_number: number;
  content_sha256: string;
  status: "APPROVED" | "ACTIVE";
  classification: DocumentRecord["classification"];
};

export type GenesisDocumentAnalysisResult = {
  conversation: {
    conversation_id: string;
    created_at: string;
  };
  source: GenesisDocumentSource;
  analysis: {
    artifact_id: string;
    digest: string;
    content: {
      prompt: string;
      reading: {
        content_characters: number;
        source_bound: boolean;
        source_modified: boolean;
      };
    };
  };
  draft: DocumentRecord;
  workflow: {
    workflow_id: string;
    status: "ANALYSIS_DRAFT";
  };
};

export function canGenesisReadDocument(document: DocumentRecord): boolean {
  return document.origin === "MANUAL" && (document.status === "APPROVED" || document.status === "ACTIVE");
}
