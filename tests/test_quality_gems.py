import dataclasses

import pytest

from novel_editorial.quality.gems import (
    SENSORY_DETAIL_WORDS,
    SIGNAL_DIALOGUE,
    SIGNAL_NUMBER_DETAIL,
    SIGNAL_SENSORY,
    GoodSentence,
    find_good_sentences,
)


def test_dialogue_signal_hits_each_quote_style() -> None:
    quote_styles = ["「」", "『』", "“”", "‘’"]
    for open_quote, close_quote in quote_styles:
        gems = find_good_sentences(f"{open_quote}明天来{close_quote}他说。")
        assert gems == [
            GoodSentence(
                index=1,
                snippet=f"{open_quote}明天来{close_quote}他说",
                signals=[SIGNAL_DIALOGUE],
            )
        ]


def test_ascii_quotes_do_not_count_as_dialogue() -> None:
    assert find_good_sentences("'明天来'他说。") == []


def test_number_detail_signal_hits_units() -> None:
    hit_texts = [
        "下午三点，他准时到了车站。",
        "火车3点出发。",
        "三时整，哨声响起。",
        "他约了五号见面。",
        "2026年夏天，他回了老家。",
        "三月开花。",
        "三日之后再来。",
        "她五岁就会游泳。",
        "三号开会。",
        "三秒后出发。",
        "三米长的绳子。",
        "他走了三里路。",
        "二两白酒。",
        "他买了两块钱的菜。",
        "三钱银子。",
        "三块糖。",
        "三元钱。",
    ]
    for text in hit_texts:
        gems = find_good_sentences(text)
        assert gems, f"expected a hit for {text!r}"
        assert SIGNAL_NUMBER_DETAIL in gems[0].signals


def test_number_detail_requires_digit_unit_combo() -> None:
    no_hit_texts = [
        "明天就走。",
        "三更天。",
        "他数到三。",
        "说到点就走。",
        "三碗饭。",
        "两个苹果。",
    ]
    for text in no_hit_texts:
        assert find_good_sentences(text) == [], f"expected no hit for {text!r}"


def test_sensory_signal_hits_detail_words() -> None:
    gems = find_good_sentences("她把钥匙放进铁盒，锈声在雨里很轻。")
    assert gems == [
        GoodSentence(
            index=1,
            snippet="她把钥匙放进铁盒，锈声在雨里很轻",
            signals=[SIGNAL_SENSORY],
        )
    ]


def test_sensory_detail_words_matches_spec() -> None:
    assert SENSORY_DETAIL_WORDS == frozenset("光影声味汗血锈霜雪雨风烟尘灰铁灯钟门窗锁刀火水石")
    assert len(SENSORY_DETAIL_WORDS) == 24


def test_multiple_signals_merge_deduplicated_in_order() -> None:
    gems = find_good_sentences("三点，“灯”亮着，“雨”落在铁皮上。")
    assert len(gems) == 1
    assert gems[0].signals == [
        SIGNAL_DIALOGUE,
        SIGNAL_NUMBER_DETAIL,
        SIGNAL_SENSORY,
    ]


def test_ai_flavor_sentences_coexist_with_good_sentences() -> None:
    text = (
        "他静静地站着，仿佛在想着什么，不禁轻轻叹息。"
        "月光宛如薄纱，悄然洒落在三点。"
        "“明天来”他说。"
        "她把钥匙放进铁盒，锈声在雨里很轻。"
    )
    gems = find_good_sentences(text)
    assert [(gem.index, gem.snippet, gem.signals) for gem in gems] == [
        (2, "月光宛如薄纱，悄然洒落在三点", [SIGNAL_NUMBER_DETAIL, SIGNAL_SENSORY]),
        (3, "“明天来”他说", [SIGNAL_DIALOGUE]),
        (4, "她把钥匙放进铁盒，锈声在雨里很轻", [SIGNAL_SENSORY]),
    ]


def test_no_signal_text_returns_empty() -> None:
    text = "他坐在桌前，打开电脑，开始写报告。老师说作业明天交，大家记得带课本。"
    assert find_good_sentences(text) == []


def test_empty_and_whitespace_text_return_empty() -> None:
    assert find_good_sentences("") == []
    assert find_good_sentences("   \n  ") == []


def test_find_good_sentences_is_deterministic() -> None:
    text = "三点，他说“把灯关上”，雨水敲着铁皮。她推门进来。"
    assert find_good_sentences(text) == find_good_sentences(text)


def test_indexes_are_1_based_in_sentence_order() -> None:
    text = "下午三点，他到了。她把钥匙放进铁盒。他坐在桌前写报告。"
    gems = find_good_sentences(text)
    assert [gem.index for gem in gems] == [1, 2]


def test_good_sentence_is_frozen_dataclass() -> None:
    assert dataclasses.is_dataclass(GoodSentence)
    gem = GoodSentence(index=1, snippet="句", signals=[SIGNAL_SENSORY])
    with pytest.raises(dataclasses.FrozenInstanceError):
        gem.index = 2  # pyright: ignore[reportAttributeAccessIssue]


def test_quote_fragments_merge_curly_quotes() -> None:
    gems = find_good_sentences("「别开灯。」他说。")
    assert gems == [
        GoodSentence(
            index=1,
            snippet="「别开灯」他说",
            signals=[SIGNAL_DIALOGUE, SIGNAL_SENSORY],
        )
    ]


def test_quote_fragments_merge_after_speech_verb() -> None:
    gems = find_good_sentences("她说：“别开灯。”然后走了。")
    assert gems == [
        GoodSentence(
            index=1,
            snippet="她说：“别开灯”然后走了",
            signals=[SIGNAL_DIALOGUE, SIGNAL_SENSORY],
        )
    ]


def test_quote_fragments_do_not_merge_when_next_has_open_quote() -> None:
    text = "“别开灯。”他喊“快走。”她又说。"
    gems = find_good_sentences(text)
    assert [gem.snippet for gem in gems] == ["“别开灯", "”他喊“快走", "”她又说"]


def test_quote_fragments_do_not_merge_when_next_lacks_close_start() -> None:
    text = "“灯亮着。水开了。”"
    gems = find_good_sentences(text)
    assert [gem.snippet for gem in gems] == ["“灯亮着", "水开了", "”"]


def test_quote_fragments_merge_keeps_original_indexes() -> None:
    text = "她推门进来。“别开灯。”他说。"
    gems = find_good_sentences(text)
    assert [(gem.index, gem.snippet) for gem in gems] == [
        (1, "她推门进来"),
        (2, "“别开灯”他说"),
    ]


def test_quote_fragments_merge_combines_signals_deduplicated() -> None:
    text = "“别开灯。”他在三点说。"
    gems = find_good_sentences(text)
    assert gems == [
        GoodSentence(
            index=1,
            snippet="“别开灯”他在三点说",
            signals=[
                SIGNAL_DIALOGUE,
                SIGNAL_NUMBER_DETAIL,
                SIGNAL_SENSORY,
            ],
        )
    ]
