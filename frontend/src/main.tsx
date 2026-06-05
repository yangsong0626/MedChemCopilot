import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Ketcher } from "ketcher-core";
import {
  ClipboardList,
  FlaskConical,
  Heart,
  PencilLine,
  RefreshCw,
  Save,
  Shuffle,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const browserGlobal = globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};
browserGlobal.process ??= {};
browserGlobal.process.env ??= {};
const KetcherSketcher = lazy(() => import("./KetcherSketcher"));

type Project = {
  project_id: string;
  project_name: string;
  target: string;
  therapeutic_area: string;
  primary_goal: string;
};

type ProjectSummary = Project & {
  measured_compounds: number;
  design_count: number;
  feedback_count: number;
  active_models: number;
};

type Prediction = {
  property_name: string;
  predicted_value: number;
  confidence: number | null;
  applicability_domain: string | null;
  model_version: string;
};

type Rank = {
  total_score: number;
  rank: number | null;
  contributions: Record<string, number>;
  warnings: string[];
};

type Feedback = {
  user_id: string;
  feedback: string;
  note: string | null;
  created_date: string | null;
};

type Design = {
  design_id: string;
  project_id: string;
  source: string;
  smiles: string;
  canonical_smiles: string;
  series: string | null;
  submitted_by: string | null;
  status: string;
  notes: string | null;
  created_date: string | null;
  predictions: Prediction[];
  rank: Rank | null;
  feedback: Feedback[];
};

type PregeneratedDesign = {
  project_id: string;
  library_id: string;
  source: string;
  smiles: string;
  canonical_smiles: string;
  series: string;
  molecular_weight: string;
  logp: string;
  tpsa: string;
  hbd: string;
  hba: string;
  rotatable_bonds: string;
  predictions: Prediction[];
};

type ErrorBoundaryProps = {
  children: React.ReactNode;
};

type ErrorBoundaryState = {
  error: string | null;
};

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { error: error instanceof Error ? error.message : String(error) };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-panel">
          <strong>Sketcher failed to load</strong>
          <span>{this.state.error}</span>
        </div>
      );
    }
    return this.props.children;
  }
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }
  return response.json() as Promise<T>;
}

function predictionValue(design: Design, property: string): number | null {
  return design.predictions.find((prediction) => prediction.property_name === property)?.predicted_value ?? null;
}

function formatValue(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "-";
  return value.toFixed(value >= 10 ? 1 : 2);
}

function SourcePill({ source }: { source: string }) {
  return <span className={`pill source-${source}`}>{source}</span>;
}

function PropertyCell({ value, target }: { value: number | null; target?: "good-high" | "good-low" }) {
  const className = target && value !== null ? `property ${target}` : "property";
  return <span className={className}>{formatValue(value)}</span>;
}

function PredictionReference({ predictions }: { predictions: Prediction[] }) {
  const potency = predictions.find((prediction) => prediction.property_name === "pIC50");
  const adme = predictions.filter((prediction) => prediction.property_name !== "pIC50");
  return (
    <section className="prediction-panel">
      <h3>Prediction Reference</h3>
      <div className="potency-card">
        <span>pIC50</span>
        <strong>{formatValue(potency?.predicted_value ?? null)}</strong>
      </div>
      <div className="prediction-grid">
        {adme.map((prediction) => (
          <div key={prediction.property_name}>
            <span>{prediction.property_name}</span>
            <strong>{formatValue(prediction.predicted_value)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function structureUrl(smiles: string, width = 220, height = 150): string {
  const params = new URLSearchParams({
    smiles,
    width: String(width),
    height: String(height),
  });
  return `${API_BASE}/structures/svg?${params.toString()}`;
}

function MoleculeImage({
  smiles,
  label,
  size = "small",
}: {
  smiles: string;
  label: string;
  size?: "small" | "large";
}) {
  const width = size === "large" ? 320 : 120;
  const height = size === "large" ? 220 : 82;
  return (
    <img
      className={`molecule molecule-${size}`}
      src={structureUrl(smiles, width, height)}
      alt={`Chemical structure for ${label}`}
      loading="lazy"
    />
  );
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string>("");
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [designs, setDesigns] = useState<Design[]>([]);
  const [selectedDesignId, setSelectedDesignId] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [sortKey, setSortKey] = useState<string>("rank");
  const [activeTab, setActiveTab] = useState<"review" | "design">("review");
  const [randomDesign, setRandomDesign] = useState<PregeneratedDesign | null>(null);
  const [sketchPredictions, setSketchPredictions] = useState<Prediction[]>([]);
  const [sketchStatus, setSketchStatus] = useState("Load a design");
  const ketcherRef = useRef<Ketcher | null>(null);
  const [smiles, setSmiles] = useState("");
  const [editorSmiles, setEditorSmiles] = useState("");
  const [smilesTextDirty, setSmilesTextDirty] = useState(false);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("Loading workspace");
  const [busy, setBusy] = useState(false);

  const selectedDesign = useMemo(
    () => designs.find((design) => design.design_id === selectedDesignId) ?? designs[0] ?? null,
    [designs, selectedDesignId],
  );

  const visibleDesigns = useMemo(() => {
    const filtered = sourceFilter === "all" ? designs : designs.filter((design) => design.source === sourceFilter);
    return [...filtered].sort((a, b) => {
      if (sortKey === "rank") return (a.rank?.rank ?? 999) - (b.rank?.rank ?? 999);
      if (sortKey === "score") return (b.rank?.total_score ?? -1) - (a.rank?.total_score ?? -1);
      if (sortKey === "pIC50") return (predictionValue(b, "pIC50") ?? -1) - (predictionValue(a, "pIC50") ?? -1);
      if (sortKey === "date") return (b.created_date ?? "").localeCompare(a.created_date ?? "");
      return a.design_id.localeCompare(b.design_id);
    });
  }, [designs, sourceFilter, sortKey]);

  async function loadProjects() {
    const loaded = await api<Project[]>("/projects");
    if (loaded.length === 0) {
      setStatus("Loading seed data");
      await api<Record<string, number>>("/admin/load-seed", { method: "POST" });
      const seeded = await api<Project[]>("/projects");
      setProjects(seeded);
      setActiveProjectId(seeded[0]?.project_id ?? "");
      return;
    }
    setProjects(loaded);
    setActiveProjectId((current) => current || loaded[0]?.project_id || "");
  }

  async function loadProject(projectId: string) {
    if (!projectId) return;
    setStatus("Loading project");
    const [loadedSummary, loadedDesigns] = await Promise.all([
      api<ProjectSummary>(`/projects/${projectId}`),
      api<Design[]>(`/projects/${projectId}/designs`),
    ]);
    setSummary(loadedSummary);
    setDesigns(loadedDesigns);
    setSelectedDesignId(loadedDesigns[0]?.design_id ?? null);
    setStatus("Ready");
  }

  async function scoreProject() {
    if (!activeProjectId) return;
    setBusy(true);
    setStatus("Training models and scoring designs");
    try {
      await api(`/projects/${activeProjectId}/score`, { method: "POST" });
      await loadProject(activeProjectId);
      setActiveTab("design");
      setStatus("Scoring complete");
    } finally {
      setBusy(false);
    }
  }

  async function loadRandomDesign() {
    if (!activeProjectId) return;
    setBusy(true);
    setSketchStatus("Sampling design");
    try {
      const candidate = await api<PregeneratedDesign>(`/projects/${activeProjectId}/pregenerated/random`);
      setRandomDesign(candidate);
      setSmiles(candidate.canonical_smiles);
      setEditorSmiles(candidate.canonical_smiles);
      setSmilesTextDirty(false);
      setSketchPredictions(candidate.predictions);
      setSketchStatus(candidate.library_id);
      await ketcherRef.current?.setMolecule(candidate.canonical_smiles);
    } finally {
      setBusy(false);
    }
  }

  async function readSketchSmiles(): Promise<string> {
    if (!ketcherRef.current) {
      return smiles.trim();
    }
    if (smilesTextDirty && smiles.trim()) {
      await ketcherRef.current.setMolecule(smiles);
      setEditorSmiles(smiles);
      setSmilesTextDirty(false);
    }
    const nextSmiles = await ketcherRef.current.getSmiles();
    setSmiles(nextSmiles);
    return nextSmiles;
  }

  async function loadTextIntoSketcher() {
    if (!smiles.trim()) return;
    setBusy(true);
    try {
      await ketcherRef.current?.setMolecule(smiles);
      setEditorSmiles(smiles);
      setSmilesTextDirty(false);
      setSketchStatus("Loaded into sketcher");
    } finally {
      setBusy(false);
    }
  }

  async function predictSketch() {
    if (!activeProjectId || !smiles.trim()) return;
    setBusy(true);
    setSketchStatus("Predicting sketch");
    try {
      const currentSmiles = await readSketchSmiles();
      const result = await api<{ canonical_smiles: string; predictions: Prediction[] }>(
        `/projects/${activeProjectId}/predict-smiles`,
        {
          method: "POST",
          body: JSON.stringify({ smiles: currentSmiles }),
        },
      );
      setSmiles(result.canonical_smiles);
      setEditorSmiles(result.canonical_smiles);
      setSmilesTextDirty(false);
      await ketcherRef.current?.setMolecule(result.canonical_smiles);
      setSketchPredictions(result.predictions);
      setSketchStatus("Sketch prediction");
    } finally {
      setBusy(false);
    }
  }

  async function submitSketchDesign() {
    if (!activeProjectId || !smiles.trim()) return;
    setBusy(true);
    try {
      const currentSmiles = await readSketchSmiles();
      const design = await api<Design>(`/projects/${activeProjectId}/designs`, {
        method: "POST",
        body: JSON.stringify({
          smiles: currentSmiles,
          series: "virtual",
          submitted_by: "chemist",
          notes: randomDesign ? `Seeded from ${randomDesign.library_id}` : "Submitted from design sketcher",
        }),
      });
      await loadProject(activeProjectId);
      setSelectedDesignId(design.design_id);
      setSketchStatus(`${design.design_id} submitted`);
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(design: Design, feedback: string) {
    setBusy(true);
    try {
      await api(`/designs/${design.design_id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ user_id: "chemist", feedback, note: note || null }),
      });
      setNote("");
      await loadProject(activeProjectId);
    } finally {
      setBusy(false);
    }
  }

  async function loadSelectedDesignIntoSketcher() {
    if (!selectedDesign) return;
    setBusy(true);
    try {
      setSmiles(selectedDesign.canonical_smiles);
      setEditorSmiles(selectedDesign.canonical_smiles);
      setSmilesTextDirty(false);
      setSketchPredictions(selectedDesign.predictions);
      setSketchStatus(`Loaded ${selectedDesign.design_id}`);
      await ketcherRef.current?.setMolecule(selectedDesign.canonical_smiles);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadProjects().catch((error) => setStatus(error.message));
  }, []);

  useEffect(() => {
    loadProject(activeProjectId).catch((error) => setStatus(error.message));
  }, [activeProjectId]);

  useEffect(() => {
    if (activeTab === "design" && activeProjectId && !randomDesign) {
      loadRandomDesign().catch((error) => setSketchStatus(error.message));
    }
  }, [activeTab, activeProjectId]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <FlaskConical size={22} />
          <div>
            <h1>MedChemCopilot</h1>
            <p>{status}</p>
          </div>
        </div>
        <label className="field">
          <span>Project</span>
          <select value={activeProjectId} onChange={(event) => setActiveProjectId(event.target.value)}>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.project_id}
              </option>
            ))}
          </select>
        </label>
        {summary && (
          <div className="summary-grid">
            <div>
              <span>Compounds</span>
              <strong>{summary.measured_compounds}</strong>
            </div>
            <div>
              <span>Designs</span>
              <strong>{summary.design_count}</strong>
            </div>
            <div>
              <span>Feedback</span>
              <strong>{summary.feedback_count}</strong>
            </div>
            <div>
              <span>Models</span>
              <strong>{summary.active_models}</strong>
            </div>
          </div>
        )}
      </aside>

      <section className="workspace">
        <header className="project-header">
          <div>
            <h2>{summary?.project_name ?? "Project"}</h2>
            <p>
              {summary?.target} · {summary?.primary_goal}
            </p>
          </div>
          <div className="toolbar">
            <div className="view-tabs">
              <button className={activeTab === "review" ? "active" : ""} onClick={() => setActiveTab("review")}>
                <ClipboardList size={16} />
                Review
              </button>
              <button className={activeTab === "design" ? "active" : ""} onClick={() => setActiveTab("design")}>
                <PencilLine size={16} />
                Design
              </button>
            </div>
            {activeTab === "review" && (
              <>
                <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
                  <option value="all">All sources</option>
                  <option value="ai">AI</option>
                  <option value="human">Human</option>
                  <option value="imported">Imported</option>
                </select>
                <select value={sortKey} onChange={(event) => setSortKey(event.target.value)}>
                  <option value="rank">Rank</option>
                  <option value="score">Score</option>
                  <option value="pIC50">pIC50</option>
                  <option value="date">Date</option>
                </select>
              </>
            )}
          </div>
        </header>

        {activeTab === "review" ? (
          <div className="content-grid">
            <section className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Structure</th>
                    <th>Design</th>
                    <th>Source</th>
                    <th>Series</th>
                    <th>Score</th>
                    <th>pIC50</th>
                    <th>logD</th>
                    <th>Sol</th>
                    <th>CLint</th>
                    <th>hERG</th>
                    <th>Papp</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleDesigns.map((design) => (
                    <tr
                      key={design.design_id}
                      className={selectedDesign?.design_id === design.design_id ? "selected" : ""}
                      onClick={() => setSelectedDesignId(design.design_id)}
                    >
                      <td>{design.rank?.rank ?? "-"}</td>
                      <td className="structure-cell">
                        <MoleculeImage smiles={design.canonical_smiles} label={design.design_id} />
                      </td>
                      <td>
                        <strong>{design.design_id}</strong>
                        <span>{design.status}</span>
                      </td>
                      <td>
                        <SourcePill source={design.source} />
                      </td>
                      <td>{design.series ?? "-"}</td>
                      <td>{formatValue(design.rank?.total_score ?? null)}</td>
                      <td>
                        <PropertyCell value={predictionValue(design, "pIC50")} target="good-high" />
                      </td>
                      <td>
                        <PropertyCell value={predictionValue(design, "logD")} />
                      </td>
                      <td>
                        <PropertyCell value={predictionValue(design, "solubility_uM")} target="good-high" />
                      </td>
                      <td>
                        <PropertyCell value={predictionValue(design, "microsomal_CLint")} target="good-low" />
                      </td>
                      <td>
                        <PropertyCell value={predictionValue(design, "hERG_IC50_uM")} target="good-high" />
                      </td>
                      <td>
                        <PropertyCell value={predictionValue(design, "Caco2_Papp")} target="good-high" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <aside className="detail-panel">
              <h3>Review overview</h3>
              <p className="muted">
                Select a row to inspect it in the Design tab. Molecule feedback and new submissions now live there.
              </p>
              {selectedDesign && (
                <>
                  <div className="detail-title">
                    <div>
                      <h3>{selectedDesign.design_id}</h3>
                      <p>{selectedDesign.canonical_smiles}</p>
                    </div>
                    <SourcePill source={selectedDesign.source} />
                  </div>
                  <div className="molecule-preview">
                    <MoleculeImage
                      smiles={selectedDesign.canonical_smiles}
                      label={selectedDesign.design_id}
                      size="large"
                    />
                  </div>
                  <button className="primary" onClick={() => setActiveTab("design")}>
                    <PencilLine size={16} />
                    Open in Design
                  </button>
                </>
              )}
            </aside>
          </div>
        ) : (
          <div className="design-workspace">
            <section className="sketcher-panel">
              <header className="sketcher-header">
                <div>
                  <h3>{randomDesign?.library_id ?? "Design Sketcher"}</h3>
                  <p>{sketchStatus}</p>
                </div>
                <div className="sketcher-actions">
                  <button disabled={busy || !activeProjectId} onClick={scoreProject}>
                    <RefreshCw size={16} />
                    Score Project
                  </button>
                  <button disabled={busy} onClick={loadRandomDesign}>
                    <Shuffle size={16} />
                    Random
                  </button>
                  <button disabled={busy || !smiles.trim()} onClick={loadTextIntoSketcher}>
                    <PencilLine size={16} />
                    Load
                  </button>
                  <button disabled={busy || !smiles.trim()} onClick={predictSketch}>
                    <RefreshCw size={16} />
                    Predict
                  </button>
                  <button className="primary-inline" disabled={busy || !smiles.trim()} onClick={submitSketchDesign}>
                    <Save size={16} />
                    Submit
                  </button>
                </div>
              </header>
              <div className="sketcher-canvas">
                <ErrorBoundary>
                  <Suspense fallback={<p className="muted">Loading sketcher...</p>}>
                    <KetcherSketcher
                      smiles={editorSmiles}
                      onReady={(ketcher) => {
                        ketcherRef.current = ketcher;
                      }}
                      onError={(message) => setSketchStatus(message)}
                    />
                  </Suspense>
                </ErrorBoundary>
              </div>
              <label className="sketch-field">
                <span>SMILES</span>
                <textarea
                  value={smiles}
                  onChange={(event) => {
                    setSmiles(event.target.value);
                    setSmilesTextDirty(true);
                  }}
                  rows={4}
                />
              </label>
              {randomDesign && (
                <div className="descriptor-strip">
                  <div>
                    <span>MW</span>
                    <strong>{randomDesign.molecular_weight}</strong>
                  </div>
                  <div>
                    <span>logP</span>
                    <strong>{randomDesign.logp}</strong>
                  </div>
                  <div>
                    <span>TPSA</span>
                    <strong>{randomDesign.tpsa}</strong>
                  </div>
                  <div>
                    <span>HBD/HBA</span>
                    <strong>
                      {randomDesign.hbd}/{randomDesign.hba}
                    </strong>
                  </div>
                  <div>
                    <span>RotB</span>
                    <strong>{randomDesign.rotatable_bonds}</strong>
                  </div>
                </div>
              )}
            </section>
            <aside className="design-side-panel">
              <PredictionReference predictions={sketchPredictions} />
              <section className="evaluation-panel">
                <h3>Molecule Evaluation</h3>
                {selectedDesign ? (
                  <>
                    <div className="detail-title">
                      <div>
                        <h3>{selectedDesign.design_id}</h3>
                        <p>{selectedDesign.canonical_smiles}</p>
                      </div>
                      <SourcePill source={selectedDesign.source} />
                    </div>
                    <div className="molecule-preview compact-preview">
                      <MoleculeImage
                        smiles={selectedDesign.canonical_smiles}
                        label={selectedDesign.design_id}
                        size="large"
                      />
                    </div>
                    <div className="actions">
                      <button disabled={busy} onClick={() => sendFeedback(selectedDesign, "like")} title="Like">
                        <ThumbsUp size={16} />
                      </button>
                      <button disabled={busy} onClick={() => sendFeedback(selectedDesign, "dislike")} title="Dislike">
                        <ThumbsDown size={16} />
                      </button>
                      <button disabled={busy} onClick={() => sendFeedback(selectedDesign, "shortlist")} title="Shortlist">
                        <Heart size={16} />
                      </button>
                    </div>
                    <button disabled={busy} onClick={loadSelectedDesignIntoSketcher}>
                      <PencilLine size={16} />
                      Load Selected
                    </button>
                    <textarea
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      placeholder="Evaluation note"
                      rows={3}
                    />
                    <div className="warning-list">
                      {selectedDesign.rank?.warnings.map((warning) => <span key={warning}>{warning}</span>)}
                    </div>
                    <section>
                      <h4>
                        <ClipboardList size={15} />
                        Feedback
                      </h4>
                      {selectedDesign.feedback.length ? (
                        selectedDesign.feedback.map((item, index) => (
                          <p className="feedback" key={`${item.user_id}-${index}`}>
                            <strong>{item.feedback}</strong> {item.note}
                          </p>
                        ))
                      ) : (
                        <p className="muted">No feedback yet.</p>
                      )}
                    </section>
                  </>
                ) : (
                  <p className="muted">No design selected.</p>
                )}
              </section>
            </aside>
          </div>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
