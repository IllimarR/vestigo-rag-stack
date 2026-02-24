# Internal Service Contracts

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Pipeline](pipeline.md) · [Requirements](requirements.md)

---

Every swappable component is defined by a **contract** — a formal interface specification that declares inputs, outputs, and behavior. Contracts are the modularity backbone of the system. All descriptions below are language-agnostic; implementations may use interfaces, abstract classes, protocols, or any equivalent mechanism.

---

## 1. SourceConnector

Abstracts the origin of documents. Each data source (file system, SharePoint, database, API push) implements this contract. The **Ingest API** is implemented as an `ApiPushSourceConnector` — an implementation that receives documents via HTTP and emits them as standard `ChangeEvent` objects, preserving contract isolation.

| Method | Input | Output | Description |
|---|---|---|---|
| `list_documents` | *(none)* | List of `DocumentReference` | Returns all known documents from this source |
| `detect_changes` | last sync timestamp | List of `ChangeEvent` | Returns documents that were added, modified, or deleted since last sync |
| `fetch_document` | `DocumentReference` | `RawDocument` (bytes + metadata) | Retrieves the actual document content |
| `get_source_id` | *(none)* | string | Unique identifier for this source connector instance |

**Data types:**

- `DocumentReference`: source ID, document ID within source, filename, last modified timestamp, direct link to original
- `ChangeEvent`: document reference + change type (added / modified / deleted)
- `RawDocument`: raw bytes, original filename, file type, metadata dictionary (title, author, date, tags, etc.)

---

## 2. DocumentConverter

Converts a raw document into Markdown as the canonical format.

| Method | Input | Output | Description |
|---|---|---|---|
| `convert` | `RawDocument` | `ConvertedDocument` | Converts document content to Markdown |
| `supported_types` | *(none)* | List of file type strings | Returns which file types this converter handles |

**Data types:**

- `ConvertedDocument`: markdown content (string), original file reference, conversion metadata (converter used, warnings/errors)

---

## 3. Chunker

Splits a Markdown document into chunks suitable for embedding.

| Method | Input | Output | Description |
|---|---|---|---|
| `chunk` | markdown string, `ChunkConfig` | List of `Chunk` | Splits the document into chunks |

**Data types:**

- `ChunkConfig`: chunk size (tokens or characters), overlap size, chunking method identifier (e.g., "recursive", "semantic"), any method-specific parameters
- `Chunk`: chunk text, chunk index within document, start/end position in source, parent document reference, inherited metadata

---

## 4. EmbeddingProvider

Generates vector embeddings for text.

| Method | Input | Output | Description |
|---|---|---|---|
| `embed` | List of strings | List of embedding vectors (float arrays) | Generates embeddings for one or more text inputs |
| `get_dimension` | *(none)* | integer | Returns the dimensionality of the embedding vectors |
| `get_model_id` | *(none)* | string | Returns identifier of the model in use |

---

## 5. VectorStoreRepository

Abstracts all storage and retrieval of embedded chunks. This is the **sole access point** to the vector database — no module may bypass it.

| Method | Input | Output | Description |
|---|---|---|---|
| `store_chunks` | List of (`Chunk`, embedding vector) pairs, collection name | *(none)* | Stores chunks with their embeddings and metadata |
| `query_similar` | query embedding vector, top-k, collection name, optional metadata filters | List of `ScoredChunk` | Returns the most similar chunks by vector distance |
| `delete_by_document` | document ID, collection name | count of deleted chunks | Removes all chunks belonging to a document |
| `delete_by_source` | source ID, collection name | count of deleted chunks | Removes all chunks from a specific source |
| `list_collections` | *(none)* | List of collection names | Returns available collections |
| `create_collection` | collection name, embedding dimension | *(none)* | Creates a new collection |
| `delete_collection` | collection name | *(none)* | Deletes a collection and all its data |
| `health_check` | *(none)* | health status | Reports whether the vector store backend is reachable |

**Data types:**

- `ScoredChunk`: chunk, similarity score, all original metadata
- Metadata filters: dictionary of field name → filter condition (equals, range, contains)

**Note:** The prototype uses a delete-then-store approach for document updates rather than atomic upserts. If deletion succeeds but re-storage fails, the document's chunks are lost until the next successful sync cycle. This tradeoff is acceptable at prototype scale.

---

## 6. Reranker

Re-scores and re-orders retrieved chunks by relevance to the query. The contract hides whether the implementation uses a cross-encoder model, an LLM-as-reranker, or any other method.

| Method | Input | Output | Description |
|---|---|---|---|
| `rerank` | query string, List of `ScoredChunk`, top-k | List of `RerankedChunk` | Returns re-ranked chunks with reranker relevance scores |
| `get_model_id` | *(none)* | string | Returns identifier of the reranking model in use |

**Data types:**

- `RerankedChunk`: chunk, original similarity score (from vector search), rerank score (from reranker), final rank position, all original metadata. The `rerank_score` is semantically distinct from the vector similarity score — it represents the reranker's relevance assessment and may be on a different scale.

---

## 7. GenerationProvider

Generates a natural language response given a prompt, with support for streaming.

| Method | Input | Output | Description |
|---|---|---|---|
| `generate` | `GenerationRequest` | `GenerationResponse` | Generates a complete response |
| `generate_stream` | `GenerationRequest` | Stream/iterator of `GenerationChunk` | Generates a streamed response |
| `get_model_id` | *(none)* | string | Returns identifier of the generation model in use |

**Data types:**

- `GenerationRequest`: system prompt, conversation messages (role + content), model parameters (temperature, top_p, max tokens, etc.)
- `GenerationResponse`: generated text, token usage (prompt tokens, completion tokens), model ID
- `GenerationChunk`: partial text delta, optional token usage (on final chunk)

---

## 8. AuditLogger

Emits structured audit events from any service.

| Method | Input | Output | Description |
|---|---|---|---|
| `log_query` | query text, retrieved chunks, generated response, token usage, timestamp, API key ID, **status** (success / partial / failed), **optional error message** | *(none)* | Records a full RAG query cycle, including failed or partial attempts |
| `log_ingest_event` | document reference, event type (ingested/updated/deleted/skipped), chunk count, timestamp, **optional error message** | *(none)* | Records a document lifecycle event, including skipped unsupported files |
| `log_admin_event` | action description, actor, timestamp | *(none)* | Records an administrative action |
| `query_logs` | filters (date range, event type, API key, status), pagination | List of audit log entries | Retrieves audit logs for the Admin UI |

---

## 9. ConfigProvider

Reads and writes all **application-level** configuration. This is the single source of truth for runtime settings — modules query it, never hardcoded values or direct database access.

**Scope:** `ConfigProvider` manages configuration for the core RAG pipeline contracts: embedding, reranking, generation, and chunking. Infrastructure-level bindings — which `VectorStoreRepository` backend, which `SourceConnector` implementations, which `DocumentConverter` and `AuditLogger` backend to use — are determined at deployment time via `.env` files and Docker Compose configuration. This separation is appropriate for the prototype scope: the pipeline parameters that change frequently (model endpoints, chunking strategies, prompt templates) are admin-managed, while structural component bindings that change rarely are infrastructure-managed.

**Configuration changes take effect on the next pipeline run**, not mid-execution. If an ingest job is running when configuration is updated, the running job completes with the previous configuration. No change notification or versioning mechanism is implemented for the prototype.

| Method | Input | Output | Description |
|---|---|---|---|
| `get_embedding_config` | *(none)* | Embedding model endpoint, API type, model name, parameters | Returns current embedding configuration |
| `get_reranker_config` | *(none)* | Reranker type, model endpoint, parameters | Returns current reranker configuration |
| `get_generation_config` | *(none)* | Generation model endpoint, API type, model name, parameters | Returns current generation configuration |
| `get_chunking_config` | *(none)* | `ChunkConfig` | Returns current chunking configuration |
| `get_rag_prompt_template` | *(none)* | Prompt template string | Returns the RAG prompt template |
| `get_default_collection` | *(none)* | collection name string | Returns the default vector store collection for retrieval |
| `set_embedding_config` | configuration values | *(none)* | Updates embedding configuration |
| `set_reranker_config` | configuration values | *(none)* | Updates reranker configuration |
| `set_generation_config` | configuration values | *(none)* | Updates generation configuration |
| `set_chunking_config` | `ChunkConfig` | *(none)* | Updates chunking configuration |
| `set_rag_prompt_template` | prompt template string | *(none)* | Updates the RAG prompt template |
| `set_default_collection` | collection name string | *(none)* | Updates the default retrieval collection |
