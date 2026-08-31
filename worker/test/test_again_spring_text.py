"""Unit tests for Again Spring semantic line splitting."""
from ai_worker.scene.again_spring_text import split_story_lines


def test_split_story_lines_youtube_example() -> None:
    text = (
        "집에 와서 아이 재운 후에 남편이랑 유튜브 보며 "
        "안주 집으면서 얘기하다가 취기 살짝 오르니까 말이 좀 더 잘 됐어."
    )
    lines = split_story_lines(text)
    assert lines == [
        "집에 와서 아이 재운 후에 남편이랑 유튜브 보며",
        "안주 집으면서 얘기하다가",
        "취기 살짝 오르니까 말이 좀 더 잘 됐어.",
    ]


def test_split_story_lines_keeps_neunde_clauses() -> None:
    text = "아이를 낳자는 얘기를 꺼냈는데 조건이 나왔어요."
    assert split_story_lines(text) == [
        "아이를 낳자는 얘기를 꺼냈는데",
        "조건이 나왔어요.",
    ]


def test_split_story_lines_sentence_boundaries() -> None:
    text = "첫 문장입니다. 두 번째 문장입니다."
    assert split_story_lines(text) == ["첫 문장입니다.", "두 번째 문장입니다."]
