"""Free-meeting @mention parser tests (hermes-style boundaries)."""

import unittest

from tools import meeting_mentions


class MeetingMentionsTests(unittest.TestCase):
    def test_single_mention(self):
        self.assertEqual(
            meeting_mentions.find_mentions("@守正 请复核", ["守正", "墨白"]),
            ["守正"],
        )

    def test_all_mention(self):
        self.assertEqual(
            meeting_mentions.find_mentions("请大家看看 @all", ["守正", "墨白"]),
            ["all"],
        )

    def test_cjk_punctuation_boundary(self):
        self.assertEqual(
            meeting_mentions.find_mentions("@守正，回应墨白的提案", ["守正", "墨白"]),
            ["守正"],
        )

    def test_email_is_not_a_mention(self):
        self.assertEqual(
            meeting_mentions.find_mentions("联系 user@example.com 处理", ["example", "user"]),
            [],
        )

    def test_ascii_identifier_is_not_a_mention(self):
        self.assertEqual(
            meeting_mentions.find_mentions("foo@bar 讨论", ["bar"]),
            [],
        )
        self.assertEqual(
            meeting_mentions.find_mentions("user@example.com 处理", ["example"]),
            [],
        )

    def test_quoted_block_is_masked(self):
        content = (
            "<quoted_message>@守正 之前说过的内容</quoted_message>"
            "现在请 @墨白 补充"
        )
        self.assertEqual(
            meeting_mentions.find_mentions(content, ["守正", "墨白"]),
            ["墨白"],
        )

    def test_strip_tokens_keeps_rest(self):
        stripped = meeting_mentions.strip_mention_tokens(
            "@守正，回应墨白的提案 @墨白 今天推进", ["守正", "墨白"]
        )
        self.assertEqual(stripped, "回应墨白的提案 今天推进")

    def test_resolve_excludes_sender(self):
        targets = meeting_mentions.resolve_mention_targets(
            "@守正 @墨白 都看看", ["守正", "墨白"], "守正"
        )
        self.assertEqual(targets, ["墨白"])

    def test_resolve_all_excludes_sender(self):
        targets = meeting_mentions.resolve_mention_targets(
            "@all 开会", ["守正", "墨白", "阿读"], "墨白"
        )
        self.assertEqual(targets, ["守正", "阿读"])

    def test_normalize_nfkc(self):
        self.assertTrue(
            meeting_mentions.is_mentioned("请 @ＡＢＣ 查看", "ABC")
            or meeting_mentions.is_mentioned("请 @ABC 查看", "ＡＢＣ")
        )


if __name__ == "__main__":
    unittest.main()
