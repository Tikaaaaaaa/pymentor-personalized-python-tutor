# Oral Exam Guide

Both members must be able to trace one request through every graph node and justify each
design trade-off.

## Core questions

1. **Why LangGraph?**
   It makes shared state, node responsibilities, conditional edges, and stopping behavior
   explicit. That is easier to inspect and test than an opaque agent loop.

2. **What makes the RAG strategy advanced?**
   It adds query analysis, alias expansion, inverse-frequency weighting, metadata
   personalization, title coverage, reranking, relative-score filtering, and context
   validation. Results are measured against the unchanged naive baseline.

3. **Why 130-word chunks with overlap?**
   Introductory Python sections are short. This size usually keeps one concept intact while
   avoiding large mixed-topic contexts. The overlap protects definitions near boundaries.

4. **How is short-term memory different from long-term memory?**
   Session memory stores the active topic, question, confusion, goal, and dialogue. The
   long-term profile stores level, goals, strengths, weaknesses, completed topics, and
   progress. Misconception memory separately stores evidence, frequency, severity, and a
   recommended fix. All three affect future teaching.

5. **How is answer withholding guaranteed?**
   A deterministic pre-model guardrail marks direct-solution requests. The Explainer then
   receives a hint-only instruction. This does not rely solely on the learner-facing prompt.

6. **What happens on low retrieval confidence?**
   Context Validation removes weak evidence before generation. The Explainer then states
   that indexed material is insufficient and asks for a covered topic.

7. **How do you prove memory changes an answer?**
   Seed the misconception "range includes the stop value", start a new session with the
   same student, and ask about loops. The response explicitly revisits exclusive range
   stops. `evaluation/personalization_evaluation.py` reproduces this for three personas.

8. **How do you stop prompt injection?**
   Pattern detection, input delimiters, fixed graph capabilities, no arbitrary tool access,
   scoped retrieval, output leakage checks, and secret redaction.

9. **Why SQLite?**
   It is persistent, transactional, inspectable, and appropriate for a small capstone. A
   production system could move the same logical schema to PostgreSQL.

10. **How do Groq and Ollama coexist?**
   `LLMClient` exposes one interface. `auto` selects Groq when a key exists and otherwise
   uses Ollama. Graph code does not know which provider executes a request.

11. **What metric matters most for a tutor?**
    Learning improvement, measured by pre/post quiz delta, is more meaningful than fluency.
    It is paired with groundedness and pedagogical compliance so improvement is trustworthy.

## Live-demo sequence

1. Ask for a simple explanation and open its grounding sources.
2. Ask a follow-up in the same session to show context continuity.
3. Record or show a known loops misconception, start a new session with the same student,
   and ask about `range` to show cross-session personalization.
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
