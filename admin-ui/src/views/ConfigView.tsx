import { useEffect, useState } from "react";
import { config, ApiError } from "../api/client";
import type { FullConfig } from "../api/types";

// Read/write the application-level configuration sections. The UI
// edits each section as raw JSON inside a textarea — same shape the
// backend stores in the DB, so what the operator pastes is what the
// next pipeline run reads.

type SectionKey =
  | "embedding"
  | "reranker"
  | "generation"
  | "chunking"
  | "rag_prompt_template"
  | "default_collection";

const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: "embedding", label: "Embedding" },
  { key: "reranker", label: "Reranker" },
  { key: "generation", label: "Generation" },
  { key: "chunking", label: "Chunking" },
  { key: "rag_prompt_template", label: "RAG prompt template" },
  { key: "default_collection", label: "Default collection" },
];

export function ConfigView(): JSX.Element {
  const [current, setCurrent] = useState<FullConfig | null>(null);
  const [drafts, setDrafts] = useState<Record<SectionKey, string>>(
    () => emptyDrafts(),
  );
  const [error, setError] = useState<string | null>(null);
  const [savedSection, setSavedSection] = useState<SectionKey | null>(null);

  const load = async () => {
    setError(null);
    try {
      const c = await config.getAll();
      setCurrent(c);
      setDrafts({
        embedding: JSON.stringify(c.embedding, null, 2),
        reranker: JSON.stringify(c.reranker, null, 2),
        generation: JSON.stringify(c.generation, null, 2),
        chunking: JSON.stringify(c.chunking, null, 2),
        rag_prompt_template: c.rag_prompt_template,
        default_collection: c.default_collection,
      });
    } catch (e) {
      setError(formatError(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const save = async (key: SectionKey) => {
    setError(null);
    setSavedSection(null);
    const draft = drafts[key];
    try {
      if (key === "rag_prompt_template") {
        await config.setPromptTemplate(draft);
      } else if (key === "default_collection") {
        await config.setDefaultCollection(draft);
      } else {
        const parsed = JSON.parse(draft);
        if (key === "embedding") await config.setEmbedding(parsed);
        else if (key === "reranker") await config.setReranker(parsed);
        else if (key === "generation") await config.setGeneration(parsed);
        else if (key === "chunking") await config.setChunking(parsed);
      }
      setSavedSection(key);
      await load();
    } catch (e) {
      setError(formatError(e));
    }
  };

  if (!current) {
    return (
      <section>
        <h2>Configuration</h2>
        {error ? <div className="error">{error}</div> : <p>Loading…</p>}
      </section>
    );
  }

  return (
    <section>
      <h2>Configuration</h2>
      {error && <div className="error">{error}</div>}
      {savedSection && (
        <div className="success">Saved {savedSection.replace("_", " ")}.</div>
      )}

      {SECTIONS.map(({ key, label }) => (
        <div key={key} style={{ marginBottom: "1.5rem" }}>
          <label htmlFor={`config-${key}`}>{label}</label>
          {key === "default_collection" ? (
            <input
              id={`config-${key}`}
              type="text"
              value={drafts[key]}
              onChange={(e) =>
                setDrafts((prev) => ({ ...prev, [key]: e.target.value }))
              }
            />
          ) : (
            <textarea
              id={`config-${key}`}
              value={drafts[key]}
              onChange={(e) =>
                setDrafts((prev) => ({ ...prev, [key]: e.target.value }))
              }
            />
          )}
          <div style={{ marginTop: "0.5rem" }}>
            <button onClick={() => void save(key)}>Save {label}</button>
          </div>
        </div>
      ))}
    </section>
  );
}

function emptyDrafts(): Record<SectionKey, string> {
  return {
    embedding: "",
    reranker: "",
    generation: "",
    chunking: "",
    rag_prompt_template: "",
    default_collection: "",
  };
}

function formatError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) {
      return "Admin key missing or rejected. Set it in the bar above.";
    }
    if (e.status === 400) {
      return `Validation failed: ${JSON.stringify(e.detail)}`;
    }
    return `${e.message}: ${JSON.stringify(e.detail)}`;
  }
  if (e instanceof SyntaxError) {
    return `Invalid JSON: ${e.message}`;
  }
  return String(e);
}
