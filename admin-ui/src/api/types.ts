// Response shapes mirroring the Admin API (services/admin/application/routes.py).
// Stay in lock-step with the Python types — they share no compile-time
// boundary, so any drift surfaces at runtime through the typed `client`
// wrapper that lives next to this file.

export interface EmbeddingConfig {
  endpoint: string;
  api_type: string;
  model_name: string;
  parameters: Record<string, unknown>;
}

export interface RerankerConfig {
  type: string;
  endpoint: string | null;
  model_name: string;
  parameters: Record<string, unknown>;
}

export interface GenerationConfig {
  endpoint: string;
  api_type: string;
  model_name: string;
  parameters: Record<string, unknown>;
}

export interface ChunkConfig {
  method: string;
  size: number;
  overlap: number;
  parameters: Record<string, unknown>;
}

export interface FullConfig {
  embedding: EmbeddingConfig;
  reranker: RerankerConfig;
  generation: GenerationConfig;
  chunking: ChunkConfig;
  rag_prompt_template: string;
  default_collection: string;
}

export interface ApiKeyRecord {
  audit_id: string;
  name: string;
  created_at: string;
  revoked: boolean;
}

export interface CreatedApiKey {
  plaintext: string;
  audit_id: string;
  name: string;
  created_at: string;
}

export interface ApiKeysResponse {
  results: ApiKeyRecord[];
}

export interface AuditQueryParams {
  type?: string;
  api_key_id?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  offset?: number;
  limit?: number;
}

export interface AuditResponse {
  results: Array<Record<string, unknown>>;
  offset: number;
  limit: number;
}
