import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { Activity, AIRecommendation, Case, RedactionType } from "./types";
import { redactionConfig } from "./redactionConfig";
import { ActivityCard } from "./ActivityCard";

function Status({ value }: { value: string }) {
  return <span className={`status ${value.toLowerCase()}`}>{value}</span>;
}
function Message({ children }: { children: React.ReactNode }) {
  return <p className="message">{children}</p>;
}
function Cases() {
  const [cases, setCases] = useState<Case[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    api
      .listCases()
      .then(setCases)
      .catch(() => setError(true));
  }, []);
  if (error) return <Message>Unable to load cases.</Message>;
  if (!cases) return <Message>Loading cases…</Message>;
  return (
    <>
      <h1>Cases</h1>
      {cases.length === 0 ? (
        <Message>No cases found.</Message>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Case number</th>
                <th>Status</th>
                <th>Summary</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td>{c.case_number}</td>
                  <td>
                    <Status value={c.status} />
                  </td>
                  <td>{c.ai_summary ?? "No saved summary"}</td>
                  <td>
                    <Link to={`/cases/${c.id}`}>Open case</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
function CaseDetail({ caseId }: { caseId: string }) {
  const [item, setItem] = useState<Case | null>(null);
  const [activities, setActivities] = useState<Activity[] | null>(null);
  const [types, setTypes] = useState<RedactionType[]>([]);
  const [loadError, setLoadError] = useState<number | boolean>(false);
  const [error, setError] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [drafts, setDrafts] = useState<Record<
    number,
    AIRecommendation[]
  > | null>(null);
  const [summaryDraft, setSummaryDraft] = useState<string | null>(null);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const showError = (e: unknown) =>
    setError(
      e instanceof ApiError ? e.message : "Request failed. Please retry.",
    );
  const reload = async () => {
    try {
      const [c, a] = await Promise.all([
        api.getCase(caseId),
        api.listActivities(caseId),
      ]);
      setItem(c);
      setActivities(a);
    } catch (e) {
      showError(e);
    }
  };
  useEffect(() => {
    let ignore = false;
    Promise.all([
      api.getCase(caseId),
      api.listActivities(caseId),
      api.listTypes(),
    ])
      .then(([c, a, t]) => {
        if (!ignore) {
          setItem(c);
          setActivities(a);
          setTypes(t);
        }
      })
      .catch((e: { status?: number }) => {
        if (!ignore) setLoadError(e.status === 404 ? 404 : true);
      });
    return () => {
      ignore = true;
    };
  }, [caseId]);
  const analyze = async () => {
    if (!item) return;
    setAnalyzing(true);
    setError("");
    setAnalysisComplete(false);
    setDrafts(null);
    setSummaryDraft(null);
    try {
      const result = await api.analyzeCase(item.id);
      setDrafts(
        Object.fromEntries(
          result.activities.map((a) => [a.activity_id, a.recommendations]),
        ),
      );
      setSummaryDraft(result.summary_draft);
      setAnalysisComplete(true);
    } catch (e) {
      showError(e);
    } finally {
      setAnalyzing(false);
    }
  };
  const approve = async () => {
    if (!item || summaryDraft === null) return;
    setApproving(true);
    setError("");
    try {
      setItem(await api.approveSummary(item.id, summaryDraft, item.ai_summary));
      setSummaryDraft(null);
    } catch (e) {
      showError(e);
    } finally {
      setApproving(false);
    }
  };
  const toggleCase = async () => {
    if (
      !item ||
      !window.confirm(
        item.status === "CLOSED" ? "Reopen this case?" : "Close this case?",
      )
    )
      return;
    try {
      setItem(
        item.status === "CLOSED"
          ? await api.reopenCase(item.id)
          : await api.closeCase(item.id),
      );
    } catch (e) {
      showError(e);
    }
  };
  if (loadError === 404)
    return (
      <Message>
        Case not found. <Link to="/cases">Return to cases</Link>
      </Message>
    );
  if (loadError) return <Message>Unable to load this case.</Message>;
  if (!item || !activities) return <Message>Loading case…</Message>;
  return (
    <>
      <Link to="/cases">← Back to cases</Link>
      <h1>{item.case_number}</h1>
      <p>
        <Status value={item.status} />
      </p>
      <h2>Saved summary</h2>
      <p>{item.ai_summary ?? "No saved summary"}</p>
      <button
        disabled={analyzing || approving || item.status === "CLOSED"}
        onClick={analyze}
      >
        {analyzing ? "Analyzing…" : "Analyze case"}
      </button>
      <p>
        Analysis returns unsaved drafts. Verify the summary and each redaction
        separately.
      </p>
      {analysisComplete && activities.length === 0 && (
        <Message>No activities to analyze.</Message>
      )}
      {summaryDraft !== null && (
        <section className="card" aria-label="Summary draft review">
          <h2>Unsaved summary draft</h2>
          <p>
            Verify facts and remove internal or privileged details before
            approval.
          </p>
          {item.ai_summary && (
            <p>Approving will replace the saved summary shown above.</p>
          )}
          <label>
            Summary draft
            <textarea
              value={summaryDraft}
              maxLength={4000}
              rows={6}
              disabled={approving || item.status === "CLOSED"}
              onChange={(e) => setSummaryDraft(e.target.value)}
            />
          </label>
          <button
            disabled={
              approving || item.status === "CLOSED" || !summaryDraft.trim()
            }
            onClick={approve}
          >
            Approve summary
          </button>
          <button disabled={approving} onClick={() => setSummaryDraft(null)}>
            Discard summary draft
          </button>
        </section>
      )}
      {error && <p role="alert">{error}</p>}
      <h2>Activities</h2>
      {activities.length === 0 ? (
        <Message>No activities found.</Message>
      ) : (
        activities.map((a) => (
          <ActivityCard
            key={a.id}
            activity={a}
            types={types}
            onChanged={reload}
            readOnly={item.status === "CLOSED" || analyzing}
            draftRecommendations={drafts?.[a.id]}
            onDraftsChanged={(next) =>
              setDrafts((current) => ({ ...current, [a.id]: next }))
            }
          />
        ))
      )}
      <aside>
        <strong>Legend</strong>
        {Object.entries(redactionConfig).map(([key, value]) => (
          <span key={key} className="legend-item">
            <i
              style={{
                background: value.background,
                borderColor: value.border,
              }}
            />
            {value.label}
          </span>
        ))}
      </aside>
      <button
        className="case-toggle"
        disabled={analyzing || approving}
        onClick={toggleCase}
      >
        {item.status === "CLOSED" ? "Reopen Case" : "Close Case"}
      </button>
    </>
  );
}
function Detail() {
  const { caseId = "" } = useParams();
  return <CaseDetail key={caseId} caseId={caseId} />;
}
export default function App() {
  return (
    <main>
      <Routes>
        <Route path="/" element={<Navigate to="/cases" replace />} />
        <Route path="/cases" element={<Cases />} />
        <Route path="/cases/:caseId" element={<Detail />} />
      </Routes>
    </main>
  );
}
