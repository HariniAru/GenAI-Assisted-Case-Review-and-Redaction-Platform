import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityCard } from "./ActivityCard";
import { api, ApiError } from "./api";
import type { Activity, AIRecommendation, Redaction } from "./types";

const activity: Activity = {
  id: 3,
  case_id: 2,
  activity_uid: "ACT-1002-01",
  activity_type: "Call",
  description: "Clld cust Daniel Kim.",
  created_at: "2026-09-25T12:00:00Z",
  redactions: [],
};
const suggestion: AIRecommendation = {
  redaction_type: "PERSONAL_INFO",
  redaction_text: "Daniel Kim",
  starting_position: 10,
  reason: "Customer name in the current note.",
  supporting_policy: {
    chunk_id: "policy-id",
    content_sha256: "policy-hash",
    section: "1. PERSONAL_INFO",
    excerpt: "Protect a customer's full name.",
  },
};
const saved: Redaction = {
  id: 7,
  source: "AI",
  redaction_text: "Daniel Kim",
  starting_position: 10,
  ending_position: 20,
  created_at: "2026-09-25T12:00:00Z",
  updated_at: "2026-09-25T12:00:00Z",
  redaction_type: { id: 1, name: "PERSONAL_INFO" },
  user: { id: 1, first_name: "Jordan", last_name: "Lee" },
};
afterEach(() => vi.restoreAllMocks());

describe("grounded recommendations", () => {
  it("shows the policy and only saves on explicit acceptance; rejection stays local", async () => {
    const user = userEvent.setup();
    const generate = vi
      .spyOn(api, "aiRecommendations")
      .mockResolvedValue({ recommendations: [suggestion] });
    const accept = vi
      .spyOn(api, "acceptRecommendation")
      .mockResolvedValue(saved);
    const manual = vi.spyOn(api, "createRedaction");
    const onChanged = vi.fn();
    render(
      <ActivityCard activity={activity} types={[]} onChanged={onChanged} />,
    );
    await user.click(
      screen.getByRole("button", { name: "Generate AI recommendations" }),
    );
    expect(
      await screen.findByText("Supporting rule: 1. PERSONAL_INFO"),
    ).toBeVisible();
    expect(
      screen.getByText(suggestion.supporting_policy.excerpt),
    ).toBeVisible();
    expect(accept).not.toHaveBeenCalled();
    expect(manual).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(
      screen.queryByText("Supporting rule: 1. PERSONAL_INFO"),
    ).not.toBeInTheDocument();
    expect(accept).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Generate AI recommendations" }),
    );
    await user.click(await screen.findByRole("button", { name: "Accept" }));
    expect(generate).toHaveBeenCalledTimes(2);
    expect(accept).toHaveBeenCalledWith(activity.id, suggestion);
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(
      screen.queryByRole("button", { name: "Accept" }),
    ).not.toBeInTheDocument();
  });

  it("shows a useful retrieval error and clears old pending suggestions", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "aiRecommendations")
      .mockResolvedValueOnce({ recommendations: [suggestion] })
      .mockRejectedValueOnce(
        new ApiError(
          503,
          "Reference retrieval is unavailable. Check ingestion and retry.",
        ),
      );
    render(<ActivityCard activity={activity} types={[]} onChanged={vi.fn()} />);
    await user.click(
      screen.getByRole("button", { name: "Generate AI recommendations" }),
    );
    expect(await screen.findByRole("button", { name: "Accept" })).toBeEnabled();
    await user.click(
      screen.getByRole("button", { name: "Generate AI recommendations" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reference retrieval is unavailable. Check ingestion and retry.",
    );
    expect(
      screen.queryByRole("button", { name: "Accept" }),
    ).not.toBeInTheDocument();
  });

  it("keeps a failed acceptance pending and explains invalid evidence", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "aiRecommendations").mockResolvedValue({
      recommendations: [suggestion],
    });
    vi.spyOn(api, "acceptRecommendation").mockRejectedValue(
      new ApiError(
        422,
        "Supporting policy changed or is invalid. Generate recommendations again.",
      ),
    );
    const onChanged = vi.fn();
    render(
      <ActivityCard activity={activity} types={[]} onChanged={onChanged} />,
    );
    await user.click(
      screen.getByRole("button", { name: "Generate AI recommendations" }),
    );
    await user.click(await screen.findByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Generate recommendations again.",
    );
    expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("preserves manual selection and save", async () => {
    const user = userEvent.setup();
    const create = vi
      .spyOn(api, "createRedaction")
      .mockResolvedValue({ ...saved, source: "MANUAL" });
    const onChanged = vi.fn();
    const { container } = render(
      <ActivityCard
        activity={activity}
        types={[{ id: 1, name: "PERSONAL_INFO" }]}
        onChanged={onChanged}
      />,
    );
    const description = container.querySelector(".description")!;
    const node = within(description as HTMLElement).getByText(
      activity.description,
    ).firstChild!;
    const range = document.createRange();
    range.setStart(node, 10);
    range.setEnd(node, 20);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(description);
    await user.selectOptions(screen.getByLabelText("Type"), "1");
    await user.click(screen.getByRole("button", { name: "Apply Redaction" }));
    expect(create).toHaveBeenCalledWith(3, {
      redaction_type_id: 1,
      redaction_text: "Daniel Kim",
      starting_position: 10,
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    window.getSelection()!.removeAllRanges();
  });
});
