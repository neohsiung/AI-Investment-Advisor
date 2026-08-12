"""
Tests for pulling the scoring object out of a chatty LLM reply.
從夾雜自然語言的 LLM 回覆中取出評分物件的測試。

Context (2026-08-12): the LLM tiers were repointed at free NVIDIA NIM models,
all of which are reasoning models. They routinely restate the prompt before
answering — and the prompt contains the JSON template itself. The old
extractor took everything from the first `{` to the last `}`, which spanned
the restated template and the real answer; `<0-10>` is not valid JSON, so the
parse threw and CompositorService substituted `_fallback_score()`, a
deterministic hash of the ticker. Models that answered correctly were being
recorded as noise.

2026-08-12：LLM tier 改指向免費的 NVIDIA NIM 推理模型後，這些模型常會先複述提示
再作答，而提示本身就含 JSON 模板。舊的擷取邏輯取「第一個 { 到最後一個 }」，會同時
涵蓋模板與答案，其中 `<0-10>` 並非合法 JSON，解析失敗後便退回以 ticker 雜湊產生的
假分數——模型明明答對了卻被記成雜訊。
"""
import json

import pytest

from src.services.confidence_compositor_service import _extract_score_object


class TestPicksTheAnswerNotTheEchoedPrompt:

    def test_reasoning_preamble_that_restates_the_template(self):
        """
        Verbatim shape of the production failure (Sentiment/NVDA, 2026-08-12):
        `Expecting value: line 1 column 11 (char 10)` — column 10 is `<0-10>`.
        """
        raw = (
            'The user asks: "Score NVDA from the Sentiment perspective 0-10. '
            'Return ONLY JSON: {"score": <0-10>, "key_factor": "<12 words max>", '
            '"rationale": "<one sentence>"}"\n\n'
            "We need to provide a JSON object with the score.\n"
            '{"score": 7, "key_factor": "Positive AI sentiment", '
            '"rationale": "Coverage is broadly bullish."}'
        )
        obj = _extract_score_object(raw)
        assert obj["score"] == 7
        assert obj["key_factor"] == "Positive AI sentiment"

    def test_template_alone_is_rejected_rather_than_scored(self):
        """
        A reply containing only the template has no answer in it. Returning
        it would record `<0-10>` as a score.
        只複述模板而沒有作答時必須視為失敗，否則會把 `<0-10>` 當成分數記錄下來。
        """
        with pytest.raises(json.JSONDecodeError):
            _extract_score_object('{"score": "<0-10>", "key_factor": "<12 words max>"}')

    def test_last_valid_object_wins(self):
        """The answer follows the restatement, so later objects are the real one."""
        raw = '{"score": 1, "key_factor": "draft"} then revised: {"score": 9, "key_factor": "final"}'
        assert _extract_score_object(raw)["key_factor"] == "final"


class TestOrdinaryReplies:

    def test_bare_json(self):
        assert _extract_score_object('{"score": 8, "key_factor": "x"}')["score"] == 8

    def test_nested_objects_do_not_break_brace_matching(self):
        raw = '{"score": 6, "key_factor": "x", "details": {"pe": 30, "growth": {"yoy": 0.4}}}'
        obj = _extract_score_object(raw)
        assert obj["score"] == 6
        assert obj["details"]["growth"]["yoy"] == 0.4

    def test_prose_after_the_answer(self):
        raw = '{"score": 5, "key_factor": "neutral"}\n\nHope this helps!'
        assert _extract_score_object(raw)["score"] == 5

    def test_float_scores_are_accepted(self):
        assert _extract_score_object('{"score": 7.5, "key_factor": "x"}')["score"] == 7.5

    def test_string_numeric_score_is_accepted(self):
        """Some models quote the number; that is still a usable score."""
        assert _extract_score_object('{"score": "7", "key_factor": "x"}')["score"] == "7"


class TestFailureModes:

    def test_no_json_at_all_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_score_object("I cannot score this ticker.")

    def test_object_without_a_score_key_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_score_object('{"key_factor": "x", "rationale": "y"}')

    def test_unbalanced_braces_raise_rather_than_hang(self):
        """
        Truncation mid-JSON is what max_tokens=300 was doing to the Risk agent.
        max_tokens=300 對 Risk agent 造成的正是這種 JSON 中途截斷。
        """
        with pytest.raises(json.JSONDecodeError):
            _extract_score_object('{"score": 7, "key_factor": "truncated mid-str')
