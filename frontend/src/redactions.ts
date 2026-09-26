import type { Redaction } from "./types";

export interface Segment {
  text: string;
  redactions: Redaction[];
}

export function segmentText(
  description: string,
  redactions: Redaction[],
): Segment[] {
  const characters = Array.from(description);
  const valid = redactions.flatMap((redaction) => {
    const start = redaction.starting_position;
    const end = start + Array.from(redaction.redaction_text).length;
    if (
      start < 0 ||
      end > characters.length ||
      characters.slice(start, end).join("") !== redaction.redaction_text
    ) {
      console.warn("Ignoring invalid redaction range");
      return [];
    }
    return [{ redaction, start, end }];
  });

  const boundaries = new Set([0, characters.length]);
  for (const { start, end } of valid) {
    boundaries.add(start);
    boundaries.add(end);
  }
  const sorted = [...boundaries].sort((a, b) => a - b);
  return sorted
    .slice(0, -1)
    .map((start, index) => {
      const end = sorted[index + 1];
      return {
        text: characters.slice(start, end).join(""),
        redactions: valid
          .filter((range) => start < range.end && end > range.start)
          .map((range) => range.redaction),
      };
    })
    .filter((segment) => segment.text.length > 0);
}
