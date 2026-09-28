import { useRef, useState } from "react";
import type {
  Activity,
  AIRecommendation,
  Redaction,
  RedactionType,
} from "./types";
import { api, ApiError } from "./api";
import { segmentText } from "./redactions";
import { styleFor } from "./redactionConfig";
import { selectedRange } from "./selection";

export function ActivityCard({
  activity,
  types,
  onChanged,
  readOnly = false,
  draftRecommendations,
  onDraftsChanged,
}: {
  activity: Activity;
  types: RedactionType[];
  onChanged: () => void;
  readOnly?: boolean;
  draftRecommendations?: AIRecommendation[];
  onDraftsChanged?: (drafts: AIRecommendation[]) => void;
}) {
  const descriptionRef = useRef<HTMLParagraphElement>(null);
  const [form, setForm] = useState<{ text: string; start: number } | null>(
    null,
  );
  const [selectedTypeId, setSelectedTypeId] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [localRecommendations, setLocalRecommendations] = useState<
    AIRecommendation[]
  >([]);
  const recommendations = draftRecommendations ?? localRecommendations;
  const setRecommendations = (
    update:
      | AIRecommendation[]
      | ((current: AIRecommendation[]) => AIRecommendation[]),
  ) => {
    const next =
      typeof update === "function" ? update(recommendations) : update;
    if (draftRecommendations !== undefined && onDraftsChanged)
      onDraftsChanged(next);
    else setLocalRecommendations(next);
  };
  const [generating, setGenerating] = useState(false);
  const choose = () => {
    const selection =
      descriptionRef.current && selectedRange(descriptionRef.current);
    if (selection)
      setForm({ text: selection.text, start: selection.starting_position });
  };
  const generate = async () => {
    setGenerating(true);
    setError("");
    setRecommendations([]);
    try {
      setRecommendations(
        (await api.aiRecommendations(activity.id)).recommendations,
      );
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Unable to generate AI recommendations.",
      );
    } finally {
      setGenerating(false);
    }
  };
  const accept = async (recommendation: AIRecommendation) => {
    setBusy(true);
    setError("");
    try {
      await api.acceptRecommendation(activity.id, recommendation);
      setRecommendations((current) =>
        current.filter((item) => item !== recommendation),
      );
      onChanged();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Unable to accept recommendation.",
      );
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!form || !selectedTypeId) return;
    setBusy(true);
    setError("");
    try {
      await api.createRedaction(activity.id, {
        redaction_type_id: selectedTypeId,
        redaction_text: form.text,
        starting_position: form.start,
      });
      setForm(null);
      setSelectedTypeId(0);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  const remove = async (redaction: Redaction) => {
    if (!confirm("Delete this redaction?")) return;
    setBusy(true);
    try {
      await api.deleteRedaction(redaction.id);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  const orderedRedactions = [...activity.redactions].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime() ||
      a.id - b.id,
  );
  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(undefined, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  return (
    <article className="card activity-layout">
      <section>
        <h3>{activity.activity_type}</h3>
        <small>{activity.activity_uid}</small>
        <p ref={descriptionRef} className="description" onMouseUp={choose}>
          {segmentText(activity.description, activity.redactions).map(
            (segment, index) => {
              if (segment.redactions.length === 0) {
                return <span key={index}>{segment.text}</span>;
              }
              const style = styleFor(
                segment.redactions.length > 1
                  ? "OVERLAP"
                  : segment.redactions[0].redaction_type.name,
              );
              return (
                <mark
                  key={index}
                  style={{
                    backgroundColor: style.background,
                    borderColor: style.border,
                  }}
                >
                  {segment.text}
                </mark>
              );
            },
          )}
        </p>
        <ul className="redactions">
          {orderedRedactions.map((redaction) => (
            <li key={redaction.id}>
              <time dateTime={redaction.created_at}>
                {formatDate(redaction.created_at)}
              </time>{" "}
              · <strong>{styleFor(redaction.redaction_type.name).label}</strong>{" "}
              · {redaction.source} · {redaction.user.first_name}{" "}
              {redaction.user.last_name} · “{redaction.redaction_text}”{" "}
              {!readOnly && (
                <button disabled={busy} onClick={() => remove(redaction)}>
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
      {!readOnly && (
        <aside className="redaction-panel">
          <h4>Redactions Panel</h4>
          <small>Unsaved suggestions — verify and accept individually.</small>
          <button disabled={busy || generating} onClick={generate}>
            {generating ? "Generating…" : "Generate AI recommendations"}
          </button>
          {recommendations.length === 0 && !generating && (
            <small>No pending AI recommendations</small>
          )}
          {recommendations.map((recommendation) => (
            <div
              className="recommendation"
              key={
                recommendation.redaction_type +
                recommendation.redaction_text +
                recommendation.starting_position
              }
            >
              <strong>{recommendation.redaction_type}</strong>: “
              {recommendation.redaction_text}”<p>{recommendation.reason}</p>
              <div className="supporting-rule">
                <strong>
                  Supporting rule: {recommendation.supporting_policy.section}
                </strong>
                <p>{recommendation.supporting_policy.excerpt}</p>
                <small>Draft synthetic policy — verify before accepting.</small>
              </div>
              <button disabled={busy} onClick={() => accept(recommendation)}>
                Accept
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  setRecommendations((current) =>
                    current.filter((item) => item !== recommendation),
                  )
                }
              >
                Reject
              </button>
            </div>
          ))}
          <div className="redaction-form">
            <label>
              Selected text
              <input
                readOnly
                value={form?.text ?? ""}
                placeholder="Select text in the description"
              />
            </label>
            <label>
              Type
              <select
                value={selectedTypeId}
                onChange={(event) =>
                  setSelectedTypeId(Number(event.target.value))
                }
              >
                <option value={0}>Choose a type</option>
                {types.map((redactionType) => (
                  <option key={redactionType.id} value={redactionType.id}>
                    {redactionType.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              disabled={busy || !form?.text || !selectedTypeId}
              onClick={save}
            >
              Apply Redaction
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
        </aside>
      )}
    </article>
  );
}
