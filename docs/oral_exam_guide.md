# Oral Exam Guide

Both members must be able to trace one request through every graph node and justify each
design trade-off.

## Core questions

1. **Why LangGraph?**
   It makes shared state, node responsibilities, conditional edges, and stopping behavior
   explicit. That is easier to inspect and test than an opaque agent loop.

2. **What makes the RAG strategy advanced?**
   It improves the naive overlap baseline with inverse-frequency weighting, metadata
   personalization, title coverage, and a reranking stage. Results are measured before and
   after.

3. **Why 130-word chunks with overlap?**
   Introductory Python sections are short. This size usually keeps one concept intact while
   avoiding large mixed-topic contexts. The overlap protects definitions near boundaries.

4. **How is short-term memory different from long-term memory?**
   Session messages preserve current dialogue. Student profiles, quiz history, and
   misconceptions persist across sessions and affect future routing and teaching.

5. **How is answer withholding guaranteed?**
   A deterministic pre-model guardrail marks direct-solution requests. The Explainer then
   receives a hint-only instruction. This does not rely solely on the learner-facing prompt.

6. **What happens on low retrieval confidence?**
   The Explainer refuses to claim grounded knowledge and asks for an indexed Python topic.

7. **How do you stop prompt injection?**
   Pattern detection, input delimiters, fixed graph capabilities, no arbitrary tool access,
   scoped retrieval, output leakage checks, and secret redaction.

8. **Why SQLite?**
   It is persistent, transactional, inspectable, and appropriate for a small capstone. A
   production system could move the same logical schema to PostgreSQL.

9. **How do Groq and Ollama coexist?**
   `LLMClient` exposes one interface. `auto` selects Groq when a key exists and otherwise
   uses Ollama. Graph code does not know which provider executes a request.

10. **What metric matters most for a tutor?**
    Learning improvement, measured by pre/post quiz delta, is more meaningful than fluency.
    It is paired with groundedness and pedagogical compliance so improvement is trustworthy.

## Live-demo sequence

1. Ask for a simple explanation and open its grounding sources.
2. Ask a follow-up in the same session to show context continuity.
3. Start a new session with the same student to show persistent profile memory.
4. Request a full homework solution and demonstrate hint-first withholding.
5. Submit a prompt-injection attempt.
6. Ask an unrelated question to demonstrate scope enforcement.
7. Request a progress summary.
8. Show the evaluation JSON and explain one system improvement driven by a failed case.

## Ownership suggestion

- **Seif:** LangGraph flow, agents, provider adapter, and live demo.
- **Patrick:** RAG, memory schema, guardrails, evaluation, and reported metrics.

This is only a presentation split. Both members must understand every component because the
oral grade is individual.
