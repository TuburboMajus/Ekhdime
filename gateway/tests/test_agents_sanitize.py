import pytest

from app.agents.sanitize import looks_like_leaked_tool_syntax


@pytest.mark.parametrize(
    "text",
    [
        '<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name="plane-workspace">',
        "some text ｜｜DSML｜｜ more text",
        "prefix ｜｜calls> suffix",
        "prefix ｜｜invoke suffix",
    ],
)
def test_detects_leaked_markers(text):
    assert looks_like_leaked_tool_syntax(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "You have 3 projects: Alpha, Beta, Gamma.",
        "Here's a pipe | in a table | like markdown.",
        "The project's status is 'In Progress'.",
    ],
)
def test_leaves_normal_answers_alone(text):
    assert looks_like_leaked_tool_syntax(text) is False
