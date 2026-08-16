"""Again Spring story line split + 3-line screens."""
from ai_worker.scene.again_spring_text import pack_story_screens, split_story_lines


def test_user_reported_mid_sentence_wrap_is_gone():
    s1 = "아이를 낳자고 꺼냈더니 아내가 조건을 내밀었다. 임신 기간 생활비를 내가 다 내야 한다는 것."
    s2 = "지금은 반반씩 내고 있는데 그게 한쪽으로 다 넘어온다. 아이는 둘이 낳는 건데"
    assert split_story_lines(s1) == [
        "아이를 낳자고 꺼냈더니 아내가 조건을 내밀었다.",
        "임신 기간 생활비를 내가 다 내야 한다는 것.",
    ]
    assert split_story_lines(s2) == [
        "지금은 반반씩 내고 있는데",
        "그게 한쪽으로 다 넘어온다.",
        "아이는 둘이 낳는 건데",
    ]
    assert pack_story_screens(split_story_lines(s1)) == [split_story_lines(s1)]


def test_job668_script_does_not_shatter_phrases():
    script = (
        "아이를 낳자는 얘기를 꺼냈는데 조건이 나왔어요. "
        "지금까지 생활비를 반반씩 내고 있었는데, 임신하는 동안 생활비를 제가 전부 내야 한다는 거였죠. "
        "아이는 둘이 함께 하는 결정이고 함께 낳는 건데 비용 전부가 한 사람에게만 넘어가는 거예요. "
        "아이를 낳는 조건이라기보다는 거래처럼 느껴져서 마음이 복잡했어요. "
        "이게 과한 조건인지, 내가 이기적인 건지 정말 잘 모르겠습니다."
    )
    lines = split_story_lines(script)
    assert "지금까지 생활비를" not in lines
    assert "생활비를 제가" not in lines
    assert any("조건이 나왔어요" in x for x in lines)
    assert any("있었는데" in x for x in lines)
    assert all(len(s) <= 3 for s in pack_story_screens(lines))


if __name__ == "__main__":
    test_user_reported_mid_sentence_wrap_is_gone()
    test_job668_script_does_not_shatter_phrases()
    print("PASS")
