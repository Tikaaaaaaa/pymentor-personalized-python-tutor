from pathlib import Path

from python_tutor.memory import TutorMemory


def test_memory_persists_profile_messages_and_misconceptions(tmp_path: Path):
    memory = TutorMemory(tmp_path / "memory.db")
    profile = memory.profile("student-1")
    assert profile["ability"] == "beginner"

    memory.add_message("student-1", "session-1", "user", "Explain loops")
    memory.record_misconception(
        "student-1",
        "loops",
        "range includes stop",
        evidence="Quiz answer included the stop value.",
        severity="high",
        recommended_fix="Practice exclusive range stops.",
    )
    memory.record_misconception("student-1", "loops", "range includes stop")
    memory.record_quiz("student-1", "loops", 0.5, {"correct": False})
    memory.update_session(
        "student-1",
        "session-1",
        topic="loops",
        current_question="Explain loops",
        confusion="range includes stop",
        goal="Understand range",
    )
    memory.update_profile(
        "student-1",
        strengths=["variables"],
        weaknesses=["range includes stop"],
        completed_topics=["variables"],
        learning_progress={"loops": 0.5},
    )

    assert memory.history("student-1", "session-1")[0]["content"] == "Explain loops"
    updated = memory.profile("student-1")
    assert updated["misconceptions"][0]["occurrences"] == 2
    assert updated["misconceptions"][0]["severity"] == "high"
    assert updated["misconceptions"][0]["recommended_fix"]
    assert updated["quiz_history"][0]["score"] == 0.5
    assert updated["strengths"] == ["variables"]
    assert updated["learning_progress"]["loops"] == 0.5
    assert memory.session("student-1", "session-1")["goal"] == "Understand range"
