from pathlib import Path

from python_tutor.knowledge import load_chunks
from python_tutor.rag import TutorRetriever, canonical_topic


def test_advanced_retrieval_finds_topic():
    chunks = load_chunks(Path("data/knowledge"))
    retriever = TutorRetriever(chunks)
    results = retriever.advanced(
        "Why is a mutable default list dangerous in a Python function?",
        topic="functions",
        difficulty="intermediate",
    )
    assert results
    assert any("function" in (item["topic"] + item["section"]).lower() for item in results)


def test_baseline_and_advanced_return_structured_sources():
    retriever = TutorRetriever(load_chunks(Path("data/knowledge")))
    for results in (
        retriever.baseline("Python dictionary missing key"),
        retriever.advanced("Python dictionary missing key", topic="dictionaries"),
    ):
        assert results
        assert {"source_id", "title", "section", "text", "score"} <= results[0].keys()


def test_context_validation_rejects_unknown_python_topics():
    retriever = TutorRetriever(load_chunks(Path("data/knowledge")))
    decision = retriever.retrieve(
        "Explain Python decorators, descriptors, and metaclass internals."
    )
    assert not decision.sufficient
    assert not decision.contexts
    assert decision.reason


def test_query_analysis_handles_ambiguous_and_symbolic_topics():
    assert canonical_topic("When should I use a dictionary instead of a list?") == "dictionaries"
    assert canonical_topic("What is = versus == in Python?") == "variables"
