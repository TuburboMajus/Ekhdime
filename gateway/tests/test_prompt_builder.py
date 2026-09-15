from app.prompts.builder import build_prompt, format_history
from app.sessions.models import Message
from tests.conftest import make_settings


def test_build_prompt_includes_query():
    settings = make_settings()
    prompt = build_prompt(settings, "list my projects")
    assert "Query: list my projects" in prompt


def test_build_prompt_omits_optional_blocks_when_absent():
    settings = make_settings(plane_user_email="", plane_user_id="")
    prompt = build_prompt(settings, "hi")
    assert "User:" not in prompt
    assert "History:" not in prompt


def test_build_prompt_includes_user_identity_when_configured():
    settings = make_settings(plane_user_email="alice@example.com")
    prompt = build_prompt(settings, "hi")
    assert "User: alice@example.com" in prompt


def test_build_prompt_includes_history():
    settings = make_settings()
    history = [
        Message(role="user", content="What should I work on?"),
        Message(role="assistant", content="ABC-42."),
    ]
    prompt = build_prompt(settings, "why?", history=history)
    assert "History:" in prompt
    assert "User: What should I work on?" in prompt
    assert "Assistant: ABC-42." in prompt


def test_format_history_labels_roles():
    history = [Message(role="user", content="hi"), Message(role="assistant", content="hello")]
    formatted = format_history(history)
    assert formatted == "User: hi\nAssistant: hello"
