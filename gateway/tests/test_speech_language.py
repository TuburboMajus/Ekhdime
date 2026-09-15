from app.speech.language import voice_for_text

DEFAULT = "af_heart"


def test_detects_french():
    text = (
        "Je n'ai trouve aucun projet dans ce workspace Plane. "
        "Si tu penses que des projets devraient exister, dis-moi et je peux verifier."
    )
    assert voice_for_text(text, DEFAULT) == "ff_siwis"


def test_english_falls_back_to_default_voice():
    text = "You have no projects in your workspace right now. Let me know if you'd like to create one."
    assert voice_for_text(text, DEFAULT) == DEFAULT


def test_unsupported_language_falls_back_to_default_voice():
    # German has no distinct Kokoro voice in the current mapping.
    text = "Du hast derzeit keine Projekte in deinem Arbeitsbereich."
    assert voice_for_text(text, DEFAULT) == DEFAULT


def test_empty_text_falls_back_to_default_voice_without_raising():
    assert voice_for_text("", DEFAULT) == DEFAULT


def test_gibberish_falls_back_to_default_voice_without_raising():
    assert voice_for_text("!!! 123 ### ???", DEFAULT) == DEFAULT
