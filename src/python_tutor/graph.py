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
from .rag import TutorRetriever
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
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("explainer", self.explainer)
        graph.add_node("curriculum_planner", self.curriculum_planner)
        graph.add_node("quiz_agent", self.quiz_agent)
        graph.add_node("feedback_synthesizer", self.feedback_synthesizer)
        graph.add_node("scope_response", self.scope_response)
        graph.add_node("output_guardrails", self.apply_output_guardrails)
        graph.add_node("persist", self.persist)

        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "input_guardrails")
        graph.add_edge("input_guardrails", "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self.route,
            {
                "retrieve": "retrieve",
                "curriculum_planner": "curriculum_planner",
                "quiz_agent": "quiz_agent",
                "feedback_synthesizer": "feedback_synthesizer",
                "scope_response": "scope_response",
            },
        )
        graph.add_edge("retrieve", "explainer")
        for node in (
            "explainer",
            "curriculum_planner",
            "quiz_agent",
            "feedback_synthesizer",
            "scope_response",
        ):
            graph.add_edge(node, "output_guardrails")
        graph.add_edge("output_guardrails", "persist")
        graph.add_edge("persist", END)
        return graph.compile()

    def load_memory(self, state: TutorState) -> dict:
        return {
            "student_profile": self.memory.profile(state["student_id"]),
            "session_history": self.memory.history(
                state["student_id"], state["session_id"]
            ),
            "guardrail_flags": [],
        }

    def apply_input_guardrails(self, state: TutorState) -> dict:
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
            return {"intent": "quiz", "topic": _guess_topic(message)}
        if any(word in lowered for word in ("learning plan", "study plan", "what next")):
            return {"intent": "answer", "topic": "curriculum"}
        if not likely_in_scope(message):
            return {"intent": "out_of_scope", "topic": "outside_python"}
        return {"intent": "learn", "topic": _guess_topic(message)}

    @staticmethod
    def route(state: TutorState) -> Literal[
        "retrieve",
        "curriculum_planner",
        "quiz_agent",
        "feedback_synthesizer",
        "scope_response",
    ]:
        if "answer_withholding" in state.get("guardrail_flags", []):
            return "retrieve"
        if state.get("topic") == "curriculum":
            return "curriculum_planner"
        return {
            "learn": "retrieve",
            "answer": "retrieve",
            "quiz": "quiz_agent",
            "progress": "feedback_synthesizer",
            "out_of_scope": "scope_response",
        }.get(state.get("intent", "learn"), "curriculum_planner")

    def retrieve(self, state: TutorState) -> dict:
        profile = state["student_profile"]
        contexts = self.retriever.advanced(
            state["message"],
            topic=state.get("topic", ""),
            difficulty=profile.get("ability", "beginner"),
            top_k=4,
        )
        confidence = min(1.0, (contexts[0]["score"] / 4.0)) if contexts else 0.0
        return {"retrieved_contexts": contexts, "confidence": confidence}

    def explainer(self, state: TutorState) -> dict:
        contexts = state.get("retrieved_contexts", [])
        if not contexts or state.get("confidence", 0.0) < 0.12:
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
        return {
            "draft_response": answer,
            "next_action": "Answer the check-for-understanding question.",
        }

    def curriculum_planner(self, state: TutorState) -> dict:
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
        topic = state.get("topic") or "python fundamentals"
        profile = state["student_profile"]
        contexts = self.retriever.advanced(
            state["message"],
            topic=topic,
            difficulty=profile.get("ability", "beginner"),
            top_k=2,
        )
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
        confidence = min(1.0, contexts[0]["score"] / 4.0) if contexts else 0.0
        return {
            "draft_response": answer,
            "retrieved_contexts": contexts,
            "confidence": confidence,
            "next_action": "Submit your quiz answer.",
        }

    def feedback_synthesizer(self, state: TutorState) -> dict:
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
        clean, flags = output_guardrail(state.get("draft_response", ""))
        return {
            "final_response": clean,
            "guardrail_flags": state.get("guardrail_flags", []) + flags,
        }

    def persist(self, state: TutorState) -> dict:
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


def _guess_topic(text: str) -> str:
    lowered = text.lower()
    aliases = {
        "variables": ("variable", "assignment", "= versus =="),
        "types": ("type", "input return a string"),
        "conditionals": ("conditional", "if", "elif", "else"),
        "loops": ("loop", "range", "while", "for loop"),
        "functions": ("function", "return", "argument", "parameter", "default"),
        "lists": ("list", "comprehension", "mutable", "copy"),
        "dictionaries": ("dictionary", "dict", "keyerror"),
        "exceptions": ("exception", "error", "try", "except"),
        "files": ("file", "open("),
        "classes": ("class", "object", "inheritance", "composition"),
        "recursion": ("recursion", "recursive"),
    }
    return next(
        (
            topic
            for topic, terms in aliases.items()
            if any(term in lowered for term in terms)
        ),
        "python fundamentals",
    )


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
