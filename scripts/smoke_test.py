from __future__ import annotations

import uuid

from dotenv import load_dotenv

from python_tutor import TutorService


load_dotenv()
service = TutorService()
result = service.ask(
    student_id="smoke-test",
    session_id=str(uuid.uuid4()),
    message="Explain the difference between print and return in Python.",
)
print("Provider:", service.llm.provider)
print("Intent:", result.intent)
print("Sources:", [source.source_id for source in result.sources])
print("Response:\n", result.response)
