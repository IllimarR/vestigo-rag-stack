"""LLM service — homes EmbeddingProvider, Reranker, GenerationProvider impls.

Each stage is independently configured; grouping them in one module is a
delivery convenience only. Nothing here couples the three contracts together.
"""
