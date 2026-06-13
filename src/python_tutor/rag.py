from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .knowledge import Chunk


TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "does",
    "explain",
    "for",
    "how",
    "in",
    "is",
    "me",
    "of",
    "on",
    "python",
    "the",
    "to",
    "what",
    "when",
    "why",
    "with",
}
TOPIC_ALIASES = {
    "variables": {"variable", "variables", "assignment", "equality", "equals"},
    "types": {"type", "types", "conversion", "input", "string"},
    "conditionals": {"conditional", "conditionals", "condition", "if", "elif", "else"},
    "loops": {"loop", "loops", "range", "for", "while", "iteration"},
    "functions": {
        "function",
        "functions",
        "return",
        "argument",
        "parameter",
        "default",
        "scope",
    },
    "lists": {"list", "lists", "tuple", "comprehension", "mutable", "aliasing", "copy"},
    "dictionaries": {"dictionary", "dictionaries", "dict", "key", "keyerror", "mapping"},
    "exceptions": {"exception", "exceptions", "error", "try", "except", "filenotfounderror"},
    "files": {"file", "files", "open", "read", "write"},
    "classes": {"class", "classes", "object", "inheritance", "composition"},
    "recursion": {"recursion", "recursive", "base", "case"},
}


@dataclass(frozen=True)
class RetrievalDecision:
    query: str
    normalized_query: str
    topic: str
    difficulty: str
    contexts: list[dict]
    confidence: float
    sufficient: bool
    reason: str


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def canonical_topic(text: str, fallback: str = "python fundamentals") -> str:
    lowered = text.lower()
    if ("=" in text and "==" in text) or "assignment versus equality" in lowered:
        return "variables"
    tokens = set(tokenize(text))
    ranked = []
    for topic, aliases in TOPIC_ALIASES.items():
        matches = tokens.intersection(aliases)
        if not matches:
            continue
        first_position = min(
            (
                lowered.find(alias)
                for alias in matches
                if lowered.find(alias) >= 0
            ),
            default=len(lowered),
        )
        ranked.append((len(matches), -first_position, topic))
    return max(ranked)[2] if ranked else fallback


def expand_query(query: str, topic: str = "") -> str:
    canonical = canonical_topic(topic or query, fallback=topic or "python fundamentals")
    aliases = sorted(TOPIC_ALIASES.get(canonical, set()))
    return " ".join(dict.fromkeys([*tokenize(query), *aliases]))


class TutorRetriever:
    """Baseline lexical retrieval plus hybrid retrieval and deterministic reranking."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.doc_tokens = [Counter(tokenize(chunk.text)) for chunk in chunks]
        self.document_frequency = Counter()
        for tokens in self.doc_tokens:
            self.document_frequency.update(tokens.keys())

    def baseline(self, query: str, top_k: int = 4) -> list[dict]:
        query_tokens = set(tokenize(query))
        scored = []
        for chunk, tokens in zip(self.chunks, self.doc_tokens):
            score = len(query_tokens.intersection(tokens))
            scored.append((float(score), chunk))
        return self._format(sorted(scored, reverse=True, key=lambda x: x[0])[:top_k])

    def advanced(
        self,
        query: str,
        *,
        topic: str = "",
        difficulty: str = "",
        top_k: int = 4,
    ) -> list[dict]:
        original_terms = tokenize(query)
        resolved_topic = canonical_topic(topic or query)
        query_counts = Counter(original_terms)
        for alias in TOPIC_ALIASES.get(resolved_topic, set()):
            if alias not in query_counts:
                query_counts[alias] = 0.25
        query_terms = list(query_counts)
        n_docs = max(1, len(self.chunks))
        candidates: list[tuple[float, Chunk]] = []

        for chunk, doc_counts in zip(self.chunks, self.doc_tokens):
            bm25_like = 0.0
            for term, qtf in query_counts.items():
                df = self.document_frequency.get(term, 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                tf = doc_counts.get(term, 0)
                bm25_like += qtf * idf * (tf / (tf + 1.2) if tf else 0)

            searchable_metadata = f"{chunk.topic} {chunk.section}".lower()
            topic_terms = TOPIC_ALIASES.get(resolved_topic, set())
            phrase_bonus = 0.8 if query.lower() in chunk.text.lower() else 0.0
            topic_bonus = (
                1.5
                if topic_terms
                and any(term in searchable_metadata for term in topic_terms)
                else 0.0
            )
            level_bonus = 0.4 if difficulty and difficulty == chunk.difficulty else 0.0
            title_bonus = sum(
                0.35 for term in set(query_terms) if term in tokenize(chunk.section)
            )
            candidates.append(
                (bm25_like + phrase_bonus + topic_bonus + level_bonus + title_bonus, chunk)
            )

        # Reranking rewards concept coverage and concise chunks.
        candidates.sort(reverse=True, key=lambda item: item[0])
        reranked = []
        query_set = set(original_terms) - QUERY_STOPWORDS
        for score, chunk in candidates[: max(top_k * 3, 8)]:
            coverage = len(query_set.intersection(tokenize(chunk.text))) / max(1, len(query_set))
            length_penalty = max(0.0, (len(chunk.text.split()) - 150) / 500)
            reranked.append((score + coverage - length_penalty, chunk))
        reranked.sort(reverse=True, key=lambda item: item[0])
        if not reranked:
            return []
        best_score = reranked[0][0]
        filtered = [
            item
            for item in reranked
            if item[0] >= max(0.35, best_score * 0.50)
        ]
        return self._format(filtered[:top_k])

    def retrieve(
        self,
        query: str,
        *,
        topic: str = "",
        difficulty: str = "",
        top_k: int = 4,
    ) -> RetrievalDecision:
        """Analyze, retrieve, rerank, and validate context through one explicit contract."""
        resolved_topic = canonical_topic(topic or query)
        normalized_query = expand_query(query, resolved_topic)
        contexts = self.advanced(
            query,
            topic=resolved_topic,
            difficulty=difficulty,
            top_k=top_k,
        )
        query_terms = set(tokenize(query)) - QUERY_STOPWORDS
        if ("=" in query and "==" in query) or not query_terms:
            query_terms = set(TOPIC_ALIASES.get(resolved_topic, set()))
        if not contexts:
            return RetrievalDecision(
                query=query,
                normalized_query=normalized_query,
                topic=resolved_topic,
                difficulty=difficulty,
                contexts=[],
                confidence=0.0,
                sufficient=False,
                reason="No indexed context matched the analyzed query.",
            )
        top = contexts[0]
        searchable = set(tokenize(f"{top['topic']} {top['section']} {top['text']}"))
        coverage = len(query_terms.intersection(searchable)) / max(1, len(query_terms))
        score_signal = min(1.0, top["score"] / 5.0)
        confidence = round(0.6 * coverage + 0.4 * score_signal, 4)
        sufficient = confidence >= 0.22 and coverage >= 0.12
        reason = (
            "Top context passed lexical coverage and reranker confidence checks."
            if sufficient
            else "Retrieved context was too weak or indirect for a grounded answer."
        )
        return RetrievalDecision(
            query=query,
            normalized_query=normalized_query,
            topic=resolved_topic,
            difficulty=difficulty,
            contexts=contexts if sufficient else [],
            confidence=confidence,
            sufficient=sufficient,
            reason=reason,
        )

    @staticmethod
    def _format(items: list[tuple[float, Chunk]]) -> list[dict]:
        return [
            {
                "source_id": chunk.chunk_id,
                "title": chunk.title,
                "section": chunk.section,
                "topic": chunk.topic,
                "difficulty": chunk.difficulty,
                "text": chunk.text,
                "score": round(score, 4),
            }
            for score, chunk in items
            if score > 0
        ]
