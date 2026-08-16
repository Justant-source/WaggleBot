"""Again Spring story line split + 3-line screens."""
from ai_worker.scene.again_spring_text import pack_story_screens, split_story_lines


def test_user_reported_mid_sentence_wrap_is_gone():
    s1 = "아이를 낳자고 꺼냈더니 아내가 조건을 내밀었다. 임신 기간 생활비를 내가 다 내야 한다는 것."
    s2 = "지금은 반반씩 내고 있는데 그게 한쪽으로 다 넘어온다. 아이는 둘이 낳는 건데"
    assert split_story_lines(s1) == [
        "아이를 낳자고 꺼냈더니 아내가",
        "조건을 내밀었다.",
        "임신 기간 생활비를",
        "내가 다 내야 한다는 것.",
    ]
    assert split_story_lines(s2) == [
        "지금은 반반씩 내고 있는데",
        "그게 한쪽으로 다 넘어온다.",
        "아이는 둘이 낳는 건데",
    ]
    packed = pack_story_screens(split_story_lines(s1))
    assert packed == [
        split_story_lines(s1)[:3],
        split_story_lines(s1)[3:],
    ]
    assert all(len(screen) <= 3 for screen in packed)
    assert pack_story_screens(split_story_lines(s2)) == [split_story_lines(s2)]


if __name__ == "__main__":
    test_user_reported_mid_sentence_wrap_is_gone()
    print("PASS")
