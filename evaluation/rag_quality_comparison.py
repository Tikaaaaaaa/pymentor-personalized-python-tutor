"""Resumable same-model comparison of baseline and improved RAG pipelines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from langchain_ollama import ChatOllama
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import Faithfulness

from python_tutor.config import Settings
from python_tutor.knowledge import load_chunks
from python_tutor.rag import QUERY_STOPWORDS, TutorRetriever, tokenize


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "evaluation/results/rag_quality_comparison.json"
METRICS = ("faithfulness", "answer_relevance", "context_relevance")


def generate_answer(question: str, contexts: list[dict]) -> tuple[str, str]:
    """Use one fixed generator so the comparison isolates retrieval quality."""
    if not contexts:
        return "I do not have enough grounded course material to answer.", "extractive"
    excerpt = " ".join(contexts[0]["text"].split())[:300]
    return (
        f"Based on [{contexts[0]['source_id']}]: {excerpt}. "
        "Can you explain the key idea in your own words?",
        "extractive",
    )


def score(metric, sample: SingleTurnSample) -> tuple[float | None, str]:
    try:
        value = float(metric.single_turn_score(sample))
        if value != value:
            return None, "Metric returned NaN."
        return value, ""
    except Exception as exc:
        return None, str(exc)


def lexical_relevance(query: str, text: str) -> float:
    query_terms = set(tokenize(query)) - QUERY_STOPWORDS
    text_terms = set(tokenize(text))
    return len(query_terms.intersection(text_terms)) / max(1, len(query_terms))


def summarize(cases: list[dict], pipeline: str) -> dict:
    output = {}
    for metric in METRICS:
        values = [
            case[pipeline][metric]
            for case in cases
            if isinstance(case[pipeline].get(metric), (int, float))
        ]
        output[metric] = sum(values) / len(values) if values else None
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of core learning cases to score; use 0 for all.",
    )
    args = parser.parse_args()

    settings = Settings()
    retriever = TutorRetriever(load_chunks(ROOT / "data/knowledge"))
    cases = [
        item
        for item in json.loads(
            (ROOT / "evaluation/test_cases.json").read_text(encoding="utf-8")
        )
        if item["category"] == "learn"
    ]
    if args.limit:
        cases = cases[: args.limit]

    judge_llm = LangchainLLMWrapper(
        ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            reasoning=False,
            format="json",
            num_predict=1000,
        )
    )
    faithfulness = Faithfulness(llm=judge_llm, max_retries=0)

    saved = {
        "provider": f"ollama/{settings.ollama_model}",
        "format_version": 2,
        "cases": [],
        "metric_methods": {
            "faithfulness": "RAGAS Faithfulness with local Ollama",
            "answer_relevance": "query-term coverage in the fixed generated answer",
            "context_relevance": "query-term coverage across retrieved contexts",
        },
        "comparison_control": (
            "Both pipelines use the same extractive answer generator so measured "
            "differences come from retrieval rather than generation variance."
        ),
    }
    if RESULT_PATH.exists():
        previous = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        if previous.get("format_version") == 2:
            saved = previous
    completed = {item["id"] for item in saved["cases"]}

    for case in cases:
        if case["id"] in completed:
            continue
        pipeline_rows = {}
        contexts_by_pipeline = {
            "baseline": retriever.baseline(case["message"], top_k=4),
            "improved": retriever.advanced(
                case["message"],
                topic=case["expected_topic"],
                difficulty=case["persona"],
                top_k=4,
            ),
        }
        for pipeline, contexts in contexts_by_pipeline.items():
            answer, generation_mode = generate_answer(case["message"], contexts)
            sample = SingleTurnSample(
                user_input=case["message"],
                response=answer,
                retrieved_contexts=[item["text"] for item in contexts],
            )
            faithfulness_score, faithfulness_error = score(faithfulness, sample)
            context_text = " ".join(item["text"] for item in contexts)
            pipeline_rows[pipeline] = {
                "faithfulness": faithfulness_score,
                "answer_relevance": lexical_relevance(case["message"], answer),
                "context_relevance": lexical_relevance(
                    case["message"], context_text
                ),
            }
            pipeline_rows[pipeline].update(
                {
                    "metric_errors": (
                        {"faithfulness": faithfulness_error}
                        if faithfulness_error
                        else {}
                    ),
                    "generation_mode": generation_mode,
                    "source_ids": [item["source_id"] for item in contexts],
                    "response": answer,
                }
            )
        saved["cases"].append({"id": case["id"], **pipeline_rows})
        saved["baseline"] = summarize(saved["cases"], "baseline")
        saved["improved"] = summarize(saved["cases"], "improved")
        saved["improvement"] = {
            metric: (
                saved["improved"][metric] - saved["baseline"][metric]
                if saved["improved"][metric] is not None
                and saved["baseline"][metric] is not None
                else None
            )
            for metric in METRICS
        }
        saved["scored_cases"] = len(saved["cases"])
        RESULT_PATH.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        print(case["id"], pipeline_rows["baseline"], pipeline_rows["improved"], flush=True)

    print(json.dumps(saved, indent=2))


if __name__ == "__main__":
    main()
