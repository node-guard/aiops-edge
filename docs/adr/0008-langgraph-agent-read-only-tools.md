# ADR-0008: One LangGraph agent with read-only tools; RAG is P1

- Status: Accepted
- Date: 2026-11-02
- Owner: Student A

## Decision
A single investigation agent with fixed typed read-only tools, bounded steps/time/tokens, arguments validated outside the model, and structured RCA output. pgvector RAG over curated runbooks and operator-validated incidents is P1 (S8 if time allows). LLM access goes through a provider interface; local LLM is deferred.

## Consequences
The offline scenario has no AI investigation by design; local decisions come from the autonomy matrix.
