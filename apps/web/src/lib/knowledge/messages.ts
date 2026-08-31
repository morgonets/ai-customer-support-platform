const knowledgeMessages = {
  create_failed: "The knowledge source could not be created. Try again.",
  delete_failed: "The knowledge source could not be deleted. Try again.",
  deleted: "The knowledge source and its stored content were deleted.",
  download_failed: "The original file could not be downloaded.",
  file_too_large: "Choose a document no larger than 10 MiB.",
  invalid_article: "Enter a title and article content within the documented limits.",
  invalid_document: "Choose a valid UTF-8 text, Markdown, or text-based PDF document.",
  invalid_metadata: "Enter a title between 1 and 200 characters.",
  invalid_replacement: "Article content must contain readable text.",
  processing_in_progress: "This document is already being processed.",
  processing_not_retryable: "This document is not eligible for processing retry.",
  retry_failed: "Document processing could not be retried.",
  storage_unavailable: "Private document storage is temporarily unavailable.",
  unsupported_media_type: "Only UTF-8 text, Markdown, and text-based PDF files are supported.",
  update_failed: "The knowledge source could not be updated. Try again.",
  updated: "Knowledge source updated.",
} as const;

export function knowledgeMessage(code: string | undefined): string | null {
  return code !== undefined && code in knowledgeMessages
    ? knowledgeMessages[code as keyof typeof knowledgeMessages]
    : null;
}
