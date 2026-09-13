import type { Redaction } from "./types";

export function selectedRange(container: HTMLElement): { text: string; starting_position: number } | null {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.toString().trim()) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
  const before = range.cloneRange(); before.selectNodeContents(container); before.setEnd(range.startContainer, range.startOffset);
  const text = selection.toString(); const start = Array.from(before.toString()).length;
  if (Array.from(container.textContent ?? "").slice(start, start + Array.from(text).length).join("") !== text) return null;
  return { text, starting_position: start };
}

export function segmentTextForTest(description: string, redactions: Redaction[]) { return { description, redactions }; }
