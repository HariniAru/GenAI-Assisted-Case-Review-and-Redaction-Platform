import { describe, expect, it } from "vitest";
import { segmentText } from "./redactions";

describe("segmentText", () => {
  it("preserves Unicode and marks the requested range", () => {
    const redaction = { id: 1, source: "AI", redaction_text: "Maria", starting_position: 3, ending_position: 8, created_at: "", updated_at: "", redaction_type: { id: 1, name: "PERSONAL_INFO" }, user: { id: 1, first_name: "Jordan", last_name: "Lee" } } as const;
    const segments = segmentText("😀  Maria", [redaction]);
    expect(segments.map((segment) => segment.text).join("")).toBe("😀  Maria");
    expect(segments.find((segment) => segment.redactions.length)?.text).toBe("Maria");
  });
});
