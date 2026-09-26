import { describe, expect, it } from "vitest";
import { segmentText } from "./redactions";

describe("segmentText", () => {
  it("uses code-point lengths for emoji inside overlapping redactions", () => {
    const first = {
      id: 1,
      source: "MANUAL",
      redaction_text: "😀 Ana",
      starting_position: 2,
      ending_position: 7,
      created_at: "",
      updated_at: "",
      redaction_type: { id: 1, name: "PERSONAL_INFO" },
      user: { id: 1, first_name: "Jordan", last_name: "Lee" },
    } as const;
    const second = {
      ...first,
      id: 2,
      redaction_text: "Ana",
      starting_position: 4,
    };
    const segments = segmentText("X 😀 Ana", [first, second]);
    expect(segments.map((segment) => segment.text).join("")).toBe("X 😀 Ana");
    expect(
      segments.map((segment) => [
        segment.text,
        segment.redactions.map((r) => r.id),
      ]),
    ).toEqual([
      ["X ", []],
      ["😀 ", [1]],
      ["Ana", [1, 2]],
    ]);
  });
  it("preserves Unicode and marks the requested range", () => {
    const redaction = {
      id: 1,
      source: "AI",
      redaction_text: "Maria",
      starting_position: 3,
      ending_position: 8,
      created_at: "",
      updated_at: "",
      redaction_type: { id: 1, name: "PERSONAL_INFO" },
      user: { id: 1, first_name: "Jordan", last_name: "Lee" },
    } as const;
    const segments = segmentText("😀  Maria", [redaction]);
    expect(segments.map((segment) => segment.text).join("")).toBe("😀  Maria");
    expect(segments.find((segment) => segment.redactions.length)?.text).toBe(
      "Maria",
    );
  });
});
