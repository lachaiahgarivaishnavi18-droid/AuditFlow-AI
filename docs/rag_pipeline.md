# Retrieval pipeline

1. Authorize audit membership before any retrieval or indexing.
2. Include only processed active document versions in that audit.
3. Extract page/worksheet text with source locations; split into 1,100-character chunks with 200-character overlap.
4. Persist stable 512-dimensional normalized token-hash vectors with SQL chunk rows.
5. Construct a per-query FAISS `IndexFlatIP` from the authorized active subset. No unscoped global index is searched.
6. Rank using 55% vector inner product and 45% token overlap; require lexical overlap to avoid hash-collision-only results.
7. Apply category/document filters and top-K bounds. Include document ID/name/version, page/worksheet/section, score and source text.
8. Default response returns exact retrieved passages; no unsupported narrative is generated. Missing hits produce an explicit insufficient-evidence response.
9. Optional external quote selection validates JSON and contiguous source membership. A provider failure or invalid citation falls back to local passages and a warning.
10. Save query/response provenance in retrieval history.

Hash vectors provide reproducible local similarity, not learned semantic understanding. The optional Sentence Transformers adapter in `embeddings.py` loads explicitly configured local/cached models by default, with normalized outputs and remote code disabled. Learned vector retrieval can match semantic-only hits above a 0.3 cosine threshold; hash mode requires keyword overlap. Every document records its embedding model; a model change requires reindexing. This adapter was unit-tested with a controlled encoder, not benchmarked with live model weights.

FAISS is reconstructed from stored vectors for correctness and isolation, appropriate to the bounded demonstration dataset. Large deployments should maintain scoped versioned indexes and benchmark recall. Supported duplicate, amount-threshold, discrepancy and requirement questions invoke read-only deterministic tools before passage retrieval. Tool outputs retain row references. Uploaded document instructions never become tool calls or system instructions.
