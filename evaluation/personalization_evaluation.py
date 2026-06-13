from __future__ import annotations

import json
import tempfile
from pathlib import Path

from python_tutor.config import Settings
from python_tutor.llm import LLMError
from python_tutor.memory import TutorMemory
from python_tutor.service import TutorService


ROOT = Path(__file__).resolve().parents[1]


class OfflineLLM:
    """Force the graph's deterministic grounded fallback for reproducible scoring."""

    provider = "offline-fallback"

    def chat(self, *args, **kwargs) -> str:
        raise LLMError("Offline personalization evaluation")


SCENARIOS = [
    {
        "persona": "beginner",
        "ability": "beginner",
        "topic": "loops",
        "message": "Explain Python loops and range.",
        "misconception": "range includes the stop value",
        "recommended_fix": "practice exclusive stop values with small ranges",
    },
    {
        "persona": "intermediate",
        "ability": "intermediate",
        "topic": "functions",
        "message": "Explain return values in Python functions.",
        "misconception": "print and return have the same purpose",
        "recommended_fix": "trace where a returned value goes in the caller",
    },
    {
        "persona": "advanced",
        "ability": "advanced",
        "topic": "classes",
        "message": "Explain composition versus inheritance in Python.",
        "strength": "classes",
    },
]


def evaluate() -> dict:
    rows = []
    with tempfile.TemporaryDirectory() as temp_dir:
        memory = TutorMemory(Path(temp_dir) / "personalization.db")
        service = TutorService(Settings(), llm=OfflineLLM(), memory=memory)
        for scenario in SCENARIOS:
            student_id = f"persona-{scenario['persona']}"
            service.update_profile(
                student_id,
                ability=scenario["ability"],
                strengths=[scenario["strength"]] if scenario.get("strength") else [],
                weaknesses=(
                    [scenario["misconception"]]
                    if scenario.get("misconception")
                    else []
                ),
                struggling_topics=(
                    [scenario["topic"]] if scenario.get("misconception") else []
                ),
            )
            if scenario.get("misconception"):
                service.record_misconception(
                    student_id,
                    scenario["topic"],
                    scenario["misconception"],
                    evidence="Controlled prior-session evidence",
                    severity="high",
                    recommended_fix=scenario["recommended_fix"],
                )
            response = service.ask(
                student_id=student_id,
                session_id=f"session-{scenario['persona']}",
                message=scenario["message"],
            )
            rows.append(
                {
                    "persona": scenario["persona"],
                    "ability": scenario["ability"],
                    "memory_used": bool(response.personalization_applied),
                    "grounded": bool(response.sources),
                    "check_question": "?" in response.response,
                    "confidence": response.confidence,
                    "personalization_evidence": response.personalization_applied,
                    "response": response.response,
                }
            )
    count = max(1, len(rows))
    return {
        "scenario_count": len(rows),
        "memory_usage_rate": sum(row["memory_used"] for row in rows) / count,
        "grounded_response_rate": sum(row["grounded"] for row in rows) / count,
        "teaching_check_rate": sum(row["check_question"] for row in rows) / count,
        "cases": rows,
        "method": (
            "Controlled profiles and prior misconceptions are seeded, then the real graph "
            "runs with deterministic grounded fallback generation."
        ),
    }


if __name__ == "__main__":
    output = evaluate()
    path = ROOT / "evaluation/results/personalization.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
