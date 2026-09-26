import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api, ApiError } from "./api";
import type { Activity, AIRecommendation, Case, Redaction } from "./types";

const item: Case = { id: 2, case_number: "CASE-1002", status: "OPEN", ai_summary: "Previously saved summary.", created_at: "2026-09-25T12:00:00Z", updated_at: "2026-09-25T12:00:00Z" };
const activity: Activity = { id: 3, case_id: 2, activity_uid: "ACT-1002-01", activity_type: "Call", description: "Clld cust Daniel Kim.", created_at: item.created_at, redactions: [] };
const suggestion: AIRecommendation = { redaction_type: "PERSONAL_INFO", redaction_text: "Daniel Kim", starting_position: 10, reason: "Customer name", supporting_policy: { chunk_id: "policy-id", content_sha256: "hash", section: "1. PERSONAL_INFO", excerpt: "Protect the customer's full name." } };
const saved: Redaction = { id: 7, source: "AI", redaction_text: "Daniel Kim", starting_position: 10, ending_position: 20, created_at: item.created_at, updated_at: item.updated_at, redaction_type: { id: 1, name: "PERSONAL_INFO" }, user: { id: 1, first_name: "Jordan", last_name: "Lee" } };

beforeEach(() => {
  vi.spyOn(api, "getCase").mockResolvedValue({ ...item });
  vi.spyOn(api, "listCases").mockResolvedValue([{ ...item }]);
  vi.spyOn(api, "listActivities").mockResolvedValue([activity]);
  vi.spyOn(api, "listTypes").mockResolvedValue([{ id: 1, name: "PERSONAL_INFO" }]);
  vi.spyOn(api, "analyzeCase").mockResolvedValue({ case_id: 2, summary_draft: "Draft for review.", activities: [{ activity_id: 3, recommendations: [suggestion] }] });
  vi.spyOn(api, "approveSummary").mockImplementation(async (_id, summary) => ({ ...item, ai_summary: summary }));
  vi.spyOn(api, "acceptRecommendation").mockResolvedValue(saved);
});
afterEach(() => vi.restoreAllMocks());

function open(path = "/cases/2") {
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  return userEvent.setup();
}
async function analyze() {
  const user = open();
  await user.click(await screen.findByRole("button", { name: "Analyze case" }));
  await screen.findByLabelText("Summary draft");
  return user;
}

describe("case analysis drafts", () => {
  it("does not generate or approve anything on list/detail loading", async () => {
    const user = open("/cases");
    await user.click(await screen.findByRole("link", { name: "Open case" }));
    await screen.findByRole("button", { name: "Analyze case" });
    expect(api.analyzeCase).not.toHaveBeenCalled();
    expect(api.approveSummary).not.toHaveBeenCalled();
    expect(api.acceptRecommendation).not.toHaveBeenCalled();
    expect(screen.getByText("Previously saved summary.")).toBeVisible();
  });

  it("redaction Accept/Reject never approves or discards the summary", async () => {
    const user = await analyze();
    expect(screen.getByText("Unsaved summary draft")).toBeVisible();
    expect(screen.getByText("Supporting rule: 1. PERSONAL_INFO")).toBeVisible();
    expect(api.approveSummary).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(api.acceptRecommendation).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Summary draft")).toHaveValue("Draft for review.");
    await user.click(screen.getByRole("button", { name: "Analyze case" }));
    await user.click(await screen.findByRole("button", { name: "Accept" }));
    await waitFor(() => expect(api.acceptRecommendation).toHaveBeenCalledOnce());
    expect(api.approveSummary).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Summary draft")).toHaveValue("Draft for review.");
    expect(screen.getByText("Previously saved summary.")).toBeVisible();
  });

  it("summary edit/approval persists only summary and leaves redactions pending", async () => {
    const user = await analyze();
    await user.clear(screen.getByLabelText("Summary draft"));
    await user.type(screen.getByLabelText("Summary draft"), "Reviewer edited text.");
    await user.click(screen.getByRole("button", { name: "Approve summary" }));
    expect(api.approveSummary).toHaveBeenCalledWith(2, "Reviewer edited text.", "Previously saved summary.");
    expect(await screen.findByText("Reviewer edited text.")).toBeVisible();
    expect(screen.queryByLabelText("Summary draft")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeVisible();
    expect(api.acceptRecommendation).not.toHaveBeenCalled();
  });

  it("discarding the summary leaves both saved summary and pending redactions", async () => {
    const user = await analyze();
    await user.click(screen.getByRole("button", { name: "Discard summary draft" }));
    expect(screen.queryByLabelText("Summary draft")).not.toBeInTheDocument();
    expect(screen.getByText("Previously saved summary.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Accept" })).toBeVisible();
    expect(api.approveSummary).not.toHaveBeenCalled();
  });

  it("shows analysis failure without a partial draft or overwriting saved content", async () => {
    vi.mocked(api.analyzeCase).mockRejectedValue(new ApiError(503, "Summary guidance is unavailable; re-ingest the corpus"));
    const user = open();
    await user.click(await screen.findByRole("button", { name: "Analyze case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Summary guidance is unavailable");
    expect(screen.queryByLabelText("Summary draft")).not.toBeInTheDocument();
    expect(screen.getByText("Previously saved summary.")).toBeVisible();
    expect(api.approveSummary).not.toHaveBeenCalled();
  });

  it("retains edited draft on approval conflict", async () => {
    vi.mocked(api.approveSummary).mockRejectedValue(new ApiError(409, "Saved summary changed; reload the case before approving"));
    const user = await analyze();
    await user.click(screen.getByRole("button", { name: "Approve summary" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Saved summary changed");
    expect(screen.getByLabelText("Summary draft")).toHaveValue("Draft for review.");
    expect(screen.getByRole("button", { name: "Accept" })).toBeVisible();
  });
});
