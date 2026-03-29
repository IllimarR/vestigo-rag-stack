// Typed fetch wrapper for the Vestigo Admin API.
//
// The base URL is read from `VITE_ADMIN_API_URL` (default `http://localhost:8001`).
// The bearer token is held in `localStorage` so a page reload doesn't kick the
// operator back to the login form; clearing it from the auth bar wipes both.

import type {
  ApiKeysResponse,
  AuditQueryParams,
  AuditResponse,
  ChunkConfig,
  CreatedApiKey,
  EmbeddingConfig,
  FullConfig,
  GenerationConfig,
  RerankerConfig,
} from "./types";

const BASE_URL =
  import.meta.env.VITE_ADMIN_API_URL ?? "http://localhost:8001";
const TOKEN_KEY = "vestigo.admin.token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(value: string): void {
  if (typeof window === "undefined") return;
  if (value) window.localStorage.setItem(TOKEN_KEY, value);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    throw new ApiError(
      response.status,
      `HTTP ${response.status} ${response.statusText}`,
      detail,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --- Config ----------------------------------------------------------------

export const config = {
  getAll(): Promise<FullConfig> {
    return request("/v1/config");
  },
  setEmbedding(value: EmbeddingConfig): Promise<{ status: string }> {
    return request("/v1/config/embedding", {
      method: "PUT",
      body: JSON.stringify(value),
    });
  },
  setReranker(value: RerankerConfig): Promise<{ status: string }> {
    return request("/v1/config/reranker", {
      method: "PUT",
      body: JSON.stringify(value),
    });
  },
  setGeneration(value: GenerationConfig): Promise<{ status: string }> {
    return request("/v1/config/generation", {
      method: "PUT",
      body: JSON.stringify(value),
    });
  },
  setChunking(value: ChunkConfig): Promise<{ status: string }> {
    return request("/v1/config/chunking", {
      method: "PUT",
      body: JSON.stringify(value),
    });
  },
  setPromptTemplate(template: string): Promise<{ status: string }> {
    return request("/v1/config/rag-prompt-template", {
      method: "PUT",
      body: JSON.stringify({ template }),
    });
  },
  setDefaultCollection(collection: string): Promise<{ status: string }> {
    return request("/v1/config/default-collection", {
      method: "PUT",
      body: JSON.stringify({ collection }),
    });
  },
};

// --- API keys --------------------------------------------------------------

export const apiKeys = {
  list(): Promise<ApiKeysResponse> {
    return request("/v1/api-keys");
  },
  create(name: string): Promise<CreatedApiKey> {
    return request("/v1/api-keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },
  revoke(auditId: string): Promise<{ status: string }> {
    return request(`/v1/api-keys/${encodeURIComponent(auditId)}`, {
      method: "DELETE",
    });
  },
};

// --- Audit -----------------------------------------------------------------

export const audit = {
  query(params: AuditQueryParams = {}): Promise<AuditResponse> {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      search.set(key, String(value));
    }
    const qs = search.toString();
    return request(`/v1/audit${qs ? `?${qs}` : ""}`);
  },
};
