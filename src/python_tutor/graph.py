from __future__ import annotations

import json
import re
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .guardrails import (
    asks_for_direct_solution,
    input_guardrail,
    likely_in_scope,
    output_guardrail,
)
from .llm import LLMClient, LLMError
from .memory import TutorMemory
from .prompts import (
    CURRICULUM_SYSTEM,
    EXPLAINER_SYSTEM,
    FEEDBACK_SYSTEM,
    QUIZ_SYSTEM,
)
from .rag import TutorRetriever, canonical_topic
from .schemas import TutorState


class TutorGraph:
    def __init__(self, llm: LLMClient, retriever: TutorRetriever, memory: TutorMemory):
        self.llm = llm
        self.retriever = retriever
        self.memory = memory
        self.app = self._build()

    def _build(self):
        graph = StateGraph(TutorState)
        graph.add_node("load_memory", self.load_memory)
        graph.add_node("input_guardrails", self.apply_input_guardrails)
        graph.add_node("supervisor", self.supervisor)
        graph.add_node("query_analysis", self.query_analysis)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("context_validation", self.context_validation)
        graph.add_node("explainer", self.explainer)
        graph.add_node("curriculum_planner", self.curriculum_planner)
        graph.add_node("quiz_agent", self.quiz_agent)
        graph.add_node("feedback_synthesizer", self.feedback_synthesizer)
        graph.add_node("scope_response", self.scope_response)
        graph.add_node("output_guardrails", self.apply_output_guardrails)
        graph.add_node("memory_update", self.memory_update)
        graph.add_node("persist", self.persist)

        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "input_guardrails")
        graph.add_edge("input_guardrails", "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self.route,
            {
                "query_analysis": "query_analysis",
                "curriculum_planner": "curriculum_planner",
                "quiz_agent": "quiz_agent",
                "feedback_synthesizer": "feedback_synthesizer",
                "scope_response": "scope_response",
            },
        )
        graph.add_edge("query_analysis", "retrieve")
        graph.add_edge("retrieve", "context_validation")
        graph.add_edge("context_validation", "explainer")
        for node in (
            "explainer",
            "curriculum_planner",
            "quiz_agent",
            "feedback_synthesizer",
            "scope_response",
        ):
            graph.add_edge(node, "output_guardrails")
        graph.add_edge("output_guardrails", "memory_update")
        graph.add_edge("memory_update", "persist")
        graph.add_edge("persist", END)
        return graph.compile()

    def load_memory(self, state: TutorState) -> dict:
        """Load session, profile, and conversation memory before any routing."""
        return {
            "student_profile": self.memory.profile(state["student_id"]),
            "session_memory": self.memory.session(
                state["student_id"], state["session_id"]
            ),
            "session_history": self.memory.history(
                state["student_id"], state["session_id"]
            ),
            "guardrail_flags": [],
        }

    def apply_input_guardrails(self, state: TutorState) -> dict:
        """Sanitize learner input and flag injection or direct-solution requests."""
        result = input_guardrail(state["message"])
        flags = list(state.get("guardrail_flags", [])) + result.flags
        if result.blocked:
            return {
                "message": result.safe_text,
                "intent": "out_of_scope",
                "guardrail_flags": flags,
            }
        if asks_for_direct_solution(result.safe_text):
            flags.append("answer_withholding")
        return {"message": result.safe_text, "guardrail_flags": flags}

    def supervisor(self, state: TutorState) -> dict:
        """Classify one bounded intent so exactly one specialist branch runs."""
        if "prompt_injection" in state.get("guardrail_flags", []):
            return {"intent": "out_of_scope", "topic": "security"}
        message = state["message"]
        lowered = message.lower()
        if any(
            word in lowered
            for word in (
                "progress",
                "summary",
                "how am i doing",
                "mastered topics",
                "my gaps",
                "and gaps",
            )
        ):
            return {"intent": "progress", "topic": "progress"}
        if any(word in lowered for word in ("quiz", "test me", "question me")):
            return {"intent": "quiz", "topic": canonical_topic(message)}
        if any(word in lowered for word in ("learning plan", "study plan", "what next")):
            return {"intent": "answer", "topic": "curriculum"}
        if not likely_in_scope(message):
            return {"intent": "out_of_scope", "topic": "outside_python"}
        return {"intent": "learn", "topic": canonical_topic(message)}

    @staticmethod
    def route(state: TutorState) -> Literal[
        "query_analysis",
        "curriculum_planner",
        "quiz_agent",
        "feedback_synthesizer",
        "scope_response",
    ]:
        """Map the supervisor decision to one registered graph branch."""
        if "answer_withholding" in state.get("guardrail_flags", []):
            return "query_analysis"
        if state.get("topic") == "curriculum":
            return "curriculum_planner"
        return {
            "learn": "query_analysis",
            "answer": "query_analysis",
            "quiz": "quiz_agent",
            "progress": "feedback_synthesizer",
            "out_of_scope": "scope_response",
        }.get(state.get("intent", "learn"), "curriculum_planner")

    def query_analysis(self, state: TutorState) -> dict:
        """Normalize the query and select relevant long-term learner evidence."""
        topic = canonical_topic(state.get("topic") or state["message"])
        misconceptions = [
            item
            for item in state["student_profile"].get("misconceptions", [])
            if item.get("topic") == topic
        ]
        return {
            "topic": topic,
            "query_analysis": {
                "original_query": state["message"],
                "topic": topic,
                "difficulty": state["student_profile"].get("ability", "beginner"),
            },
            "personalization_notes": _personalization_notes(
                state["student_profile"], topic, misconceptions
            ),
        }

    def retrieve(self, state: TutorState) -> dict:
        """Run hybrid retrieval and expose its confidence and validation reason."""
        profile = state["student_profile"]
        decision = self.retriever.retrieve(
            state["message"],
            topic=state.get("topic", ""),
            difficulty=profile.get("ability", "beginner"),
            top_k=4,
        )
        return {
            "retrieved_contexts": decision.contexts,
            "confidence": decision.confidence,
            "context_sufficient": decision.sufficient,
            "retrieval_reason": decision.reason,
            "query_analysis": {
                **state.get("query_analysis", {}),
                "normalized_query": decision.normalized_query,
            },
        }

    def context_validation(self, state: TutorState) -> dict:
        """Fail closed when evidence is too weak for a supported response."""
        if state.get("context_sufficient") and state.get("retrieved_contexts"):
            return {}
        return {
            "retrieved_contexts": [],
            "context_sufficient": False,
            "next_action": "Ask about a topic covered by the indexed Python curriculum.",
        }

    def explainer(self, state: TutorState) -> dict:
        """Generate a grounded explanation that explicitly uses relevant memory."""
        contexts = state.get("retrieved_contexts", [])
        if not contexts or not state.get("context_sufficient", False):
            return {
                "draft_response": (
                    "I do not have enough grounded course material to answer that confidently. "
                    "Please ask about a CSAI 106 Python topic such as variables, loops, functions, "
                    "collections, exceptions, or classes."
                ),
                "next_action": "Ask a question within the indexed Python syllabus.",
            }
        context_text = "\n\n".join(
            f"[{item['source_id']}] {item['text']}" for item in contexts
        )
        personalization_notes = state.get("personalization_notes", [])
        personalization_instruction = (
            "Use this learner history explicitly but naturally:\n- "
            + "\n- ".join(personalization_notes)
            if personalization_notes
            else "No topic-specific learner history is available yet."
        )
        withholding = "answer_withholding" in state.get("guardrail_flags", [])
        instruction = (
            "The learner requested a direct assignment solution. Do not provide finished code. "
            "Give one conceptual hint, one smaller analogous example, and one Socratic question."
            if withholding
            else "Teach the requested concept and ask one check-for-understanding question."
        )
        prompt = f"""Student profile:
{json.dumps(state['student_profile'], ensure_ascii=True)}

Recent session:
{json.dumps(state.get('session_history', [])[-6:], ensure_ascii=True)}

Structured session memory:
{json.dumps(state.get('session_memory', {}), ensure_ascii=True)}

Personalization requirement:
{personalization_instruction}

Course context:
{context_text}

Student message:
<student_message>{state['message']}</student_message>

Special instruction:
{instruction}
"""
        try:
            answer = self.llm.chat(
                [
                    {"role": "system", "content": EXPLAINER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.15,
            )
        except LLMError:
            answer = _grounded_fallback(contexts, withholding)
        answer = _apply_personalized_opening(answer, personalization_notes)
        return {
            "draft_response": answer,
            "next_action": "Answer the check-for-understanding question.",
        }

    def curriculum_planner(self, state: TutorState) -> dict:
        """Recommend prerequisite-aware next steps from persistent evidence."""
        try:
            answer = self.llm.chat(
                [
                    {"role": "system", "content": CURRICULUM_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(state["student_profile"], ensure_ascii=True),
                    },
                ],
                temperature=0.1,
            )
        except LLMError:
            answer = "1. Variables and types\n2. Conditionals and loops\n3. Functions and testing"
        return {"draft_response": answer, "next_action": "Start the first recommended topic."}

    def quiz_agent(self, state: TutorState) -> dict:
        """Create one level-calibrated, source-grounded quiz without its solution."""
        topic = state.get("topic") or "python fundamentals"
        profile = state["student_profile"]
        decision = self.retriever.retrieve(
            state["message"],
            topic=topic,
            difficulty=profile.get("ability", "beginner"),
            top_k=2,
        )
        contexts = decision.contexts
        if not decision.sufficient:
            return {
                "draft_response": (
                    "I do not have enough indexed course material to create a reliable quiz "
                    "for that topic. Choose variables, loops, functions, collections, "
                    "exceptions, files, or classes."
                ),
                "retrieved_contexts": [],
                "confidence": decision.confidence,
                "context_sufficient": False,
                "retrieval_reason": decision.reason,
                "next_action": "Choose an indexed Python quiz topic.",
            }
        context_text = "\n\n".join(
            f"[{item['source_id']}] {item['text']}" for item in contexts
        )
        try:
            answer = self.llm.chat(
                [
                    {"role": "system", "content": QUIZ_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Create one {profile.get('ability', 'beginner')} question about {topic}. "
                            "Use the course context below, include its source ID, and reveal no solution. "
                            "End with: Reply with your reasoning and answer.\n\n"
                            f"Course context:\n{context_text}"
                        ),
                    },
                ],
                temperature=0.2,
            )
        except LLMError:
            if contexts:
                answer = (
                    f"Python quiz on {topic}, grounded in [{contexts[0]['source_id']}]: "
                    f"Explain the key rule described in this source and give one small Python "
                    "example that follows it. Reply with your reasoning and answer."
                )
            else:
                answer = (
                    f"Python quiz on {topic}: What value does `len([10, 20, 30])` return, "
                    "and why? Reply with your reasoning and answer."
                )
        return {
            "draft_response": answer,
            "retrieved_contexts": contexts,
            "confidence": decision.confidence,
            "context_sufficient": decision.sufficient,
            "retrieval_reason": decision.reason,
            "next_action": "Submit your quiz answer.",
        }

    def feedback_synthesizer(self, state: TutorState) -> dict:
        """Summarize only persisted evidence of progress, strengths, and gaps."""
        try:
            answer = self.llm.chat(
                [
                    {"role": "system", "content": FEEDBACK_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(state["student_profile"], ensure_ascii=True),
                    },
                ],
                temperature=0.1,
            )
        except LLMError:
            profile = state["student_profile"]
            answer = (
                f"Current level: {profile['ability']}. "
                f"Mastered topics: {', '.join(profile['mastered_topics']) or 'none recorded yet'}. "
                f"Topics needing practice: {', '.join(profile['struggling_topics']) or 'not enough evidence yet'}."
            )
        return {"draft_response": answer, "next_action": "Continue with the recommended topic."}

    def scope_response(self, state: TutorState) -> dict:
        """Return a deterministic refusal for injection or out-of-scope input."""
        if "prompt_injection" in state.get("guardrail_flags", []):
            response = (
                "I cannot follow instructions that try to override the tutor's rules or reveal "
                "private prompts. I can help with a Python programming concept instead."
            )
        else:
            response = (
                "This tutor is limited to the indexed CSAI 106 Python curriculum. "
                "Ask me about Python fundamentals, control flow, functions, collections, "
                "exceptions, files, or object-oriented programming."
            )
        return {"draft_response": response, "confidence": 1.0, "next_action": "Ask a Python question."}

    def apply_output_guardrails(self, state: TutorState) -> dict:
        """Redact secrets and block prompt leakage on every specialist path."""
        clean, flags = output_guardrail(state.get("draft_response", ""))
        return {
            "final_response": clean,
            "guardrail_flags": state.get("guardrail_flags", []) + flags,
        }

    def memory_update(self, state: TutorState) -> dict:
        """Update session state and structured misconceptions after a safe response."""
        detected = _detect_misconception(state["message"])
        confusion = ""
        if detected:
            self.memory.record_misconception(
                state["student_id"],
                detected["topic"],
                detected["misconception"],
                evidence=state["message"],
                severity=detected["severity"],
                recommended_fix=detected["recommended_fix"],
            )
            confusion = detected["misconception"]
            profile = self.memory.profile(state["student_id"])
            struggling = list(profile.get("struggling_topics", []))
            if detected["topic"] not in struggling:
                struggling.append(detected["topic"])
            weaknesses = list(profile.get("weaknesses", []))
            if detected["misconception"] not in weaknesses:
                weaknesses.append(detected["misconception"])
            self.memory.update_profile(
                state["student_id"],
                weaknesses=weaknesses,
                struggling_topics=struggling,
            )
        self.memory.update_session(
            state["student_id"],
            state["session_id"],
            topic=state.get("topic", ""),
            current_question=state["message"],
            confusion=confusion,
            goal=state.get("next_action", ""),
        )
        return {}

    def persist(self, state: TutorState) -> dict:
        """Persist the sanitized interaction after safety and memory updates."""
        self.memory.add_message(
            state["student_id"], state["session_id"], "user", state["message"]
        )
        self.memory.add_message(
            state["student_id"],
            state["session_id"],
            "assistant",
            state["final_response"],
        )
        return {}


def _grounded_fallback(contexts: list[dict], withholding: bool) -> str:
    excerpt = re.sub(r"\s+", " ", contexts[0]["text"]).strip()
    if withholding:
        return (
            f"Hint from [{contexts[0]['source_id']}]: {excerpt[:350]}... "
            "Which smaller input could you test first to verify your understanding?"
        )
    return (
        f"Based on [{contexts[0]['source_id']}]: {excerpt[:500]}... "
        "Can you explain the main idea back in your own words?"
    )


def _personalization_notes(
    profile: dict, topic: str, misconceptions: list[dict]
) -> list[str]:
    notes = []
    if misconceptions:
        item = misconceptions[0]
        fix = item.get("recommended_fix") or "review it with a small example"
        notes.append(f"you previously struggled with {item['misconception']}; {fix}")
    if topic in profile.get("strengths", []):
        notes.append(
            f"{topic} is one of your recorded strengths, so include a deeper challenge"
        )
    if topic in profile.get("weaknesses", []) or topic in profile.get(
        "struggling_topics", []
    ):
        notes.append(f"{topic} is a recorded weak area, so use slower scaffolding")
    return notes


def _apply_personalized_opening(answer: str, notes: list[str]) -> str:
    if not notes:
        return answer
    return f"I remember that {notes[0]}. Let's focus there first.\n\n{answer}"


def _detect_misconception(message: str) -> dict | None:
    lowered = message.lower()
    patterns = [
        (
            ("range includes", "range has the stop"),
            "loops",
            "range includes the stop value",
            "practice exclusive stop values with small ranges",
        ),
        (
            ("print and return are the same", "print gives the value back"),
            "functions",
            "print and return have the same purpose",
            "trace where a returned value goes in the caller",
        ),
        (
            ("= and == are the same", "both compare values"),
            "variables",
            "assignment and equality are interchangeable",
            "contrast state change with Boolean comparison",
        ),
        (
            ("recursion does not need a base case", "no base case"),
            "recursion",
            "recursion does not require a base case",
            "practice stopping conditions before recursive steps",
        ),
    ]
    for signals, topic, misconception, recommended_fix in patterns:
        if any(signal in lowered for signal in signals):
            return {
                "topic": topic,
                "misconception": misconception,
                "severity": "high",
                "recommended_fix": recommended_fix,
            }
    return None
