from __future__ import annotations

import uuid

import streamlit as st
from dotenv import load_dotenv

from python_tutor import TutorService


load_dotenv()
st.set_page_config(page_title="PyMentor", page_icon="P", layout="wide")


@st.cache_resource
def get_service() -> TutorService:
    return TutorService()


st.title("PyMentor")
st.caption("A memory-aware, grounded Python tutor built with LangGraph")

with st.sidebar:
    st.header("Learner")
    student_id = st.text_input("Student ID", value="demo-student")
    profile = get_service().profile(student_id)
    ability_options = ["beginner", "intermediate", "advanced"]
    ability = st.selectbox(
        "Current level",
        ability_options,
        index=ability_options.index(profile.get("ability", "beginner")),
    )
    goals_text = st.text_input(
        "Learning goals",
        value=", ".join(profile.get("goals", [])),
        help="Comma-separated goals stored in long-term memory.",
    )
    if st.button("Save learner profile"):
        get_service().update_profile(
            student_id,
            ability=ability,
            goals=[item.strip() for item in goals_text.split(",") if item.strip()],
        )
        st.success("Long-term learner profile saved.")
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if st.button("New session"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    st.write("Session:", st.session_state.session_id[:8])
    st.info("The tutor gives hints instead of complete homework solutions.")
    with st.expander("Persistent memory"):
        st.write("Strengths:", profile.get("strengths") or "None recorded")
        st.write("Weaknesses:", profile.get("weaknesses") or "None recorded")
        st.write("Completed topics:", profile.get("completed_topics") or "None recorded")
        st.write("Misconceptions:", profile.get("misconceptions") or "None recorded")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("Grounding sources"):
                for source in message["sources"]:
                    st.write(
                        f"`{source['source_id']}` - {source['section']} "
                        f"(score {source['score']:.2f})"
                    )

prompt = st.chat_input("Ask about Python or request a quiz")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking through the learning path..."):
            try:
                result = get_service().ask(
                    student_id=student_id,
                    session_id=st.session_state.session_id,
                    message=prompt,
                )
                st.markdown(result.response)
                if result.sources:
                    with st.expander("Grounding sources"):
                        for source in result.sources:
                            st.write(
                                f"`{source.source_id}` - {source.section} "
                                f"(score {source.score:.2f})"
                            )
                if result.guardrails_triggered:
                    st.caption("Guardrails: " + ", ".join(result.guardrails_triggered))
                if result.personalization_applied:
                    st.caption(
                        "Personalization: " + " | ".join(result.personalization_applied)
                    )
                if result.retrieval_reason:
                    st.caption(
                        f"Retrieval confidence: {result.confidence:.2f} - "
                        f"{result.retrieval_reason}"
                    )
                st.caption(f"Next: {result.next_action}")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": result.response,
                        "sources": [source.model_dump() for source in result.sources],
                    }
                )
            except Exception as exc:
                st.error(f"Tutor error: {exc}")
