from __future__ import annotations

import html
import uuid

import streamlit as st
from dotenv import load_dotenv

from python_tutor import TutorService


load_dotenv()
st.set_page_config(
    page_title="PyMentor | Personalized Python Tutor",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_service() -> TutorService:
    return TutorService()


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --pm-navy: #102a43;
            --pm-blue: #2563eb;
            --pm-cyan: #06b6d4;
            --pm-mint: #10b981;
            --pm-bg: #f5f8fc;
            --pm-card: rgba(255, 255, 255, 0.92);
            --pm-line: #dce6f2;
            --pm-muted: #60758a;
        }

        .stApp {
            background:
                radial-gradient(circle at 85% 5%, rgba(6, 182, 212, 0.10), transparent 24rem),
                radial-gradient(circle at 25% 0%, rgba(37, 99, 235, 0.08), transparent 30rem),
                var(--pm-bg);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #102a43 0%, #173f67 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.10);
        }

        [data-testid="stSidebar"] * {
            color: #f8fbff;
        }

        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            color: #102a43 !important;
            background: #ffffff !important;
        }

        [data-testid="stSidebar"] input {
            border-radius: 10px;
        }

        [data-testid="stSidebar"] .stAlert * {
            color: #102a43 !important;
        }

        .block-container {
            max-width: 1280px;
            padding-top: 2rem;
            padding-bottom: 6rem;
        }

        .pm-hero {
            position: relative;
            overflow: hidden;
            padding: 1.75rem 2rem;
            margin-bottom: 1rem;
            border: 1px solid rgba(37, 99, 235, 0.15);
            border-radius: 24px;
            background: linear-gradient(125deg, #102a43 0%, #174f86 58%, #087f9c 100%);
            color: white;
            box-shadow: 0 18px 45px rgba(16, 42, 67, 0.16);
        }

        .pm-hero::after {
            content: "";
            position: absolute;
            width: 250px;
            height: 250px;
            right: -70px;
            top: -105px;
            border-radius: 50%;
            border: 42px solid rgba(255, 255, 255, 0.08);
        }

        .pm-brand {
            display: flex;
            align-items: center;
            gap: 0.85rem;
            margin-bottom: 0.65rem;
        }

        .pm-logo {
            display: grid;
            width: 48px;
            height: 48px;
            place-items: center;
            border-radius: 14px;
            background: linear-gradient(145deg, #5eead4, #22d3ee);
            color: #102a43;
            font-size: 1.55rem;
            font-weight: 900;
            box-shadow: 0 8px 22px rgba(34, 211, 238, 0.25);
        }

        .pm-hero h1 {
            margin: 0;
            color: white;
            font-size: 2.1rem;
            letter-spacing: -0.04em;
        }

        .pm-hero p {
            max-width: 720px;
            margin: 0.3rem 0 0;
            color: #dcecff;
            font-size: 1.03rem;
        }

        .pm-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.3rem 0.65rem;
            margin: 0.9rem 0.4rem 0 0;
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.09);
            color: #eef8ff;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .pm-section-title {
            margin: 1.2rem 0 0.55rem;
            color: var(--pm-navy);
            font-size: 1.05rem;
            font-weight: 800;
        }

        .pm-welcome {
            padding: 1.15rem 1.3rem;
            border: 1px solid var(--pm-line);
            border-radius: 18px;
            background: var(--pm-card);
            box-shadow: 0 8px 24px rgba(16, 42, 67, 0.06);
        }

        .pm-welcome strong {
            color: var(--pm-navy);
        }

        .pm-welcome p {
            margin: 0.25rem 0 0;
            color: var(--pm-muted);
        }

        .pm-message-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin: 0.65rem 0;
        }

        .pm-chip {
            display: inline-block;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            background: #e8f1ff;
            color: #174f86;
            font-size: 0.76rem;
            font-weight: 700;
        }

        .pm-chip.success {
            background: #dcfce7;
            color: #166534;
        }

        .pm-chip.warning {
            background: #fef3c7;
            color: #92400e;
        }

        .pm-chip.personal {
            background: #ede9fe;
            color: #6d28d9;
        }

        [data-testid="stMetric"] {
            padding: 0.75rem 0.9rem;
            border: 1px solid var(--pm-line);
            border-radius: 15px;
            background: rgba(255, 255, 255, 0.78);
        }

        [data-testid="stChatMessage"] {
            padding: 1rem 1.15rem;
            border: 1px solid var(--pm-line);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.86);
            box-shadow: 0 7px 20px rgba(16, 42, 67, 0.045);
        }

        [data-testid="stChatInput"] {
            border: 1px solid #b9cbe0;
            border-radius: 16px;
            background: white;
            box-shadow: 0 8px 26px rgba(16, 42, 67, 0.10);
        }

        .stButton > button {
            border: 1px solid #bfd0e4;
            border-radius: 12px;
            font-weight: 700;
            transition: all 0.15s ease;
        }

        .stButton > button:hover {
            border-color: var(--pm-blue);
            color: var(--pm-blue);
            transform: translateY(-1px);
        }

        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            border-color: rgba(255, 255, 255, 0.28);
            background: rgba(255, 255, 255, 0.09);
            color: white;
        }

        .pm-sidebar-brand {
            padding: 0.35rem 0 0.8rem;
            font-size: 1.35rem;
            font-weight: 900;
            letter-spacing: -0.03em;
        }

        .pm-sidebar-brand span {
            color: #67e8f9;
        }

        .pm-footer {
            margin-top: 2rem;
            color: var(--pm-muted);
            font-size: 0.78rem;
            text-align: center;
        }

        @media (max-width: 760px) {
            .block-container {
                padding-top: 1rem;
            }
            .pm-hero {
                padding: 1.3rem;
                border-radius: 18px;
            }
            .pm-hero h1 {
                font-size: 1.7rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = ""


def list_text(items: list | None, empty: str = "None recorded") -> str:
    return ", ".join(str(item) for item in items) if items else empty


def render_response_metadata(message: dict) -> None:
    chips = []
    intent = message.get("intent")
    if intent:
        chips.append(f'<span class="pm-chip">{html.escape(intent.title())}</span>')
    confidence = message.get("confidence")
    if confidence is not None:
        chips.append(
            f'<span class="pm-chip success">Confidence {confidence:.0%}</span>'
        )
    for flag in message.get("guardrails", []):
        chips.append(
            f'<span class="pm-chip warning">{html.escape(flag.replace("_", " ").title())}</span>'
        )
    if message.get("personalization"):
        chips.append('<span class="pm-chip personal">Memory personalized</span>')
    if chips:
        st.markdown(
            '<div class="pm-message-meta">' + "".join(chips) + "</div>",
            unsafe_allow_html=True,
        )

    if message.get("personalization"):
        with st.expander("Why this answer was personalized"):
            for note in message["personalization"]:
                st.write(f"- {note}")
    if message.get("sources"):
        with st.expander(f"Grounding sources ({len(message['sources'])})"):
            for source in message["sources"]:
                st.markdown(
                    f"**{source['section']}**  \n"
                    f"`{source['source_id']}` · relevance score `{source['score']:.2f}`"
                )
    if message.get("retrieval_reason"):
        st.caption(message["retrieval_reason"])
    if message.get("next_action"):
        st.info(f"Next step: {message['next_action']}")


def queue_prompt(prompt: str) -> None:
    st.session_state.pending_prompt = prompt


inject_styles()
initialize_state()
service = get_service()

with st.sidebar:
    st.markdown(
        '<div class="pm-sidebar-brand"><span>Py</span>Mentor</div>',
        unsafe_allow_html=True,
    )
    st.caption("PERSONALIZED LEARNER PROFILE")
    student_id = st.text_input("Student ID", value="demo-student")
    profile = service.profile(student_id)

    ability_options = ["beginner", "intermediate", "advanced"]
    stored_ability = profile.get("ability", "beginner")
    ability = st.selectbox(
        "Current level",
        ability_options,
        index=ability_options.index(
            stored_ability if stored_ability in ability_options else "beginner"
        ),
    )
    goals_text = st.text_input(
        "Learning goals",
        value=", ".join(profile.get("goals", [])),
        placeholder="e.g. master loops, understand functions",
        help="Comma-separated goals stored in long-term memory.",
    )
    if st.button("Save learner profile", use_container_width=True):
        profile = service.update_profile(
            student_id,
            ability=ability,
            goals=[item.strip() for item in goals_text.split(",") if item.strip()],
        )
        st.success("Learner profile saved.")

    st.divider()
    session_left, session_right = st.columns([1.35, 1])
    with session_left:
        st.caption("ACTIVE SESSION")
        st.code(st.session_state.session_id[:8], language=None)
    with session_right:
        if st.button("New session", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.pending_prompt = ""
            st.rerun()

    st.info("Hint-first mode is active. Assignment solutions are never given directly.")

    with st.expander("Persistent learner memory", expanded=False):
        st.markdown(f"**Strengths**  \n{list_text(profile.get('strengths'))}")
        st.markdown(f"**Weaknesses**  \n{list_text(profile.get('weaknesses'))}")
        st.markdown(
            f"**Completed topics**  \n{list_text(profile.get('completed_topics'))}"
        )
        misconceptions = profile.get("misconceptions", [])
        if misconceptions:
            st.markdown("**Misconceptions**")
            for item in misconceptions[:5]:
                st.markdown(
                    f"- **{item.get('topic', 'Python')}**: "
                    f"{item.get('misconception', 'Recorded misconception')}"
                )
        else:
            st.caption("No misconceptions recorded yet.")

    st.caption("Powered by LangGraph · RAG · SQLite memory")

st.markdown(
    """
    <section class="pm-hero">
        <div class="pm-brand">
            <div class="pm-logo">P</div>
            <div>
                <h1>PyMentor</h1>
                <p>Your grounded, memory-aware Python learning companion.</p>
            </div>
        </div>
        <span class="pm-badge">✓ Source-grounded answers</span>
        <span class="pm-badge">✓ Persistent learner memory</span>
        <span class="pm-badge">✓ Safe hint-first teaching</span>
    </section>
    """,
    unsafe_allow_html=True,
)

strength_count = len(profile.get("strengths", []))
weakness_count = len(profile.get("weaknesses", []))
misconception_count = len(profile.get("misconceptions", []))
metric_columns = st.columns(4)
metric_columns[0].metric("Learner level", ability.title())
metric_columns[1].metric("Strengths", strength_count)
metric_columns[2].metric("Focus areas", weakness_count)
metric_columns[3].metric("Memory signals", misconception_count)

st.markdown('<div class="pm-section-title">Start a learning activity</div>', unsafe_allow_html=True)
action_columns = st.columns(4)
quick_actions = [
    ("Explain a concept", "Explain Python loops and range with a simple example."),
    ("Practice quiz", "Give me a Python quiz about functions."),
    ("Learning plan", "Create my next Python learning plan."),
    ("Progress check", "Show my learning progress and what I should practice."),
]
for column, (label, prompt_text) in zip(action_columns, quick_actions):
    with column:
        if st.button(label, use_container_width=True):
            queue_prompt(prompt_text)
            st.rerun()

topic_columns = st.columns(6)
topics = ["Variables", "Conditions", "Loops", "Functions", "Collections", "Classes"]
for column, topic in zip(topic_columns, topics):
    with column:
        if st.button(topic, key=f"topic-{topic}", use_container_width=True):
            queue_prompt(f"Teach me the key ideas of Python {topic.lower()}.")
            st.rerun()

if not st.session_state.messages:
    st.markdown(
        f"""
        <div class="pm-welcome">
            <strong>Welcome, {html.escape(student_id)}.</strong>
            <p>
                Choose an activity above or ask a Python question below. PyMentor will
                ground its answer in the course knowledge base and adapt to your
                {html.escape(ability)} profile.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('<div class="pm-section-title">Tutor workspace</div>', unsafe_allow_html=True)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_response_metadata(message)

typed_prompt = st.chat_input(
    "Ask a Python question, request a quiz, or check your progress..."
)
prompt = typed_prompt or st.session_state.pending_prompt
st.session_state.pending_prompt = ""

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Building a grounded learning response..."):
            try:
                result = service.ask(
                    student_id=student_id,
                    session_id=st.session_state.session_id,
                    message=prompt,
                )
                assistant_message = {
                    "role": "assistant",
                    "content": result.response,
                    "intent": result.intent,
                    "sources": [source.model_dump() for source in result.sources],
                    "guardrails": result.guardrails_triggered,
                    "personalization": result.personalization_applied,
                    "confidence": result.confidence,
                    "retrieval_reason": result.retrieval_reason,
                    "next_action": result.next_action,
                }
                st.markdown(result.response)
                render_response_metadata(assistant_message)
                st.session_state.messages.append(assistant_message)
            except Exception as exc:
                st.error(f"PyMentor could not complete this request: {exc}")

st.markdown(
    '<div class="pm-footer">PyMentor · CSAI 422 Capstone · Grounded learning, not answer generation</div>',
    unsafe_allow_html=True,
)
