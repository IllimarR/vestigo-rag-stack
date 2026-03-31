import { useEffect, useState } from "react";
import { config, ApiError } from "../api/client";
import type { FullConfig } from "../api/types";

// Read/write the application-level configuration sections. Each section
// renders as its own card with its own Save button — operators editing
// one section don't have their unsaved drafts on another section
// clobbered by a save.

type SectionKey =
  | "embedding"
  | "reranker"
  | "generation"
  | "chunking"
  | "rag_prompt_template"
  | "default_collection";

type SectionMeta = { key: SectionKey; label: string; hint: string };

const SECTIONS: SectionMeta[] = [
  {
    key: "embedding",
    label: "Embedding",
    hint:
      "Vector embedder endpoint, api_type, and model. Dispatched on api_type.",
  },
  {
    key: "reranker",
    label: "Reranker",
    hint:
      "Cross-encoder or LLM-as-reranker. Dispatched on type.",
  },
  {
    key: "generation",
    label: "Generation",
    hint:
      "Answer model — OpenAI-compatible or Anthropic. Dispatched on api_type.",
  },
  {
    key: "chunking",
    label: "Chunking",
    hint: "method, size, overlap. Dispatched on method.",
  },
  {
    key: "rag_prompt_template",
    label: "RAG prompt template",
    hint:
      "Rendered with {context} and {question} placeholders before generation.",
  },
  {
    key: "default_collection",
    label: "Default collection",
    hint: "Collection used when a query doesn't specify one.",
  },
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
        <header className="view-header">
          <h2>Configuration</h2>
        </header>
        {error ? (
          <div className="error" style={{ marginTop: "0.75rem" }}>{error}</div>
        ) : (
          <p className="muted">Loading…</p>
        )}
      </section>
    );
  }

  return (
    <section>
      <header className="view-header">
        <h2>Configuration</h2>
        <p className="view-subtitle">
          Application-level settings backed by{" "}
          <code className="mono">ConfigProvider</code> — picked up by the
          pipeline on the next request without a restart.
        </p>
      </header>

      {error && <div className="error" style={{ marginTop: "0.75rem" }}>{error}</div>}
      {savedSection && (
        <div className="success" style={{ marginTop: "0.75rem" }}>
          Saved {SECTIONS.find((s) => s.key === savedSection)?.label.toLowerCase()}.
        </div>
      )}

      <div style={{ marginTop: "1rem" }}>
        {SECTIONS.map((section) => (
          <div key={section.key} className="config-section">
            <div className="config-section__header">
              <h3 className="config-section__title">{section.label}</h3>
              <span className="config-section__hint">{section.hint}</span>
            </div>
            <div className="config-section__body">
              {section.key === "default_collection" ? (
                <input
                  id={`config-${section.key}`}
                  aria-label={section.label}
                  type="text"
                  value={drafts[section.key]}
                  onChange={(e) =>
                    setDrafts((prev) => ({
                      ...prev,
                      [section.key]: e.target.value,
                    }))
                  }
                />
              ) : (
                <textarea
                  id={`config-${section.key}`}
                  aria-label={section.label}
                  value={drafts[section.key]}
                  onChange={(e) =>
                    setDrafts((prev) => ({
                      ...prev,
                      [section.key]: e.target.value,
                    }))
                  }
                />
              )}
            </div>
            <div className="config-section__actions">
              <button onClick={() => void save(section.key)}>
                Save {section.label.toLowerCase()}
              </button>
            </div>
          </div>
        ))}
      </div>
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
