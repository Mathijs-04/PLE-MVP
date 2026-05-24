from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_rules_qa import (
    AskResponse,
    _clean_answer_text,
    _format_source,
    _parse_answer,
    app,
)
from fastapi.testclient import TestClient


class FormatSourceTest(unittest.TestCase):
    def test_aos_core_rules_and_faction(self) -> None:
        result = _format_source("aos", True, ["Skaven"])

        self.assertEqual(
            result,
            "WH Age of Sigmar Core Rules (4th ed.) & Skaven Battletome",
        )

    def test_wh40k_core_rules_and_faction(self) -> None:
        result = _format_source("wh40k", True, ["Space Marines"])

        self.assertEqual(
            result,
            "WH 40.000 Core Rules (10th ed.) & Space Marines Codex",
        )

    def test_faction_only(self) -> None:
        result = _format_source("wh40k", False, ["Necrons"])

        self.assertEqual(result, "Necrons Codex")


class ParseAnswerTest(unittest.TestCase):
    def test_parses_valid_json(self) -> None:
        raw = """{
            "short_answer": "Yes.",
            "detailed_answer": "You may move.",
            "source": {"has_core_rules": true, "factions": ["Skaven"]},
            "certainty": 2
        }"""

        result = _parse_answer(raw, "aos")

        self.assertEqual(result.short_answer, "Yes.")
        self.assertEqual(result.detailed_answer, "You may move.")
        self.assertEqual(
            result.source,
            "WH Age of Sigmar Core Rules (4th ed.) & Skaven Battletome",
        )
        self.assertEqual(result.certainty, 2)

    def test_strips_markdown_code_fences(self) -> None:
        raw = """```json
{
    "short_answer": "No.",
    "detailed_answer": "Not allowed.",
    "source": {"has_core_rules": false, "factions": []},
    "certainty": 1
}
```"""

        result = _parse_answer(raw, "wh40k")

        self.assertEqual(result.short_answer, "No.")
        self.assertEqual(result.detailed_answer, "Not allowed.")

    def test_clamps_certainty_to_valid_range(self) -> None:
        raw_high = '{"short_answer": "Yes.", "certainty": 9}'
        raw_low = '{"short_answer": "Yes.", "certainty": 0}'

        self.assertEqual(_parse_answer(raw_high, "aos").certainty, 4)
        self.assertEqual(_parse_answer(raw_low, "aos").certainty, 1)

    def test_falls_back_on_invalid_json(self) -> None:
        result = _parse_answer("Plain text answer.", "aos")

        self.assertEqual(result.short_answer, "Plain text answer.")
        self.assertEqual(result.detailed_answer, "")
        self.assertEqual(result.source, "")

    def test_unescapes_quotes_in_answer_text(self) -> None:
        raw = '{"short_answer": "Use \\"Run\\".", "detailed_answer": ""}'

        result = _parse_answer(raw, "aos")

        self.assertEqual(result.short_answer, 'Use "Run".')


class CleanAnswerTextTest(unittest.TestCase):
    def test_unescapes_quotes(self) -> None:
        self.assertEqual(_clean_answer_text('Use \\"Run\\".'), 'Use "Run".')


class AskEndpointTest(unittest.TestCase):
    def test_empty_question_returns_422(self) -> None:
        with patch("web_rules_qa._VECTORSTORES", {"aos": MagicMock()}), patch(
            "web_rules_qa._SOURCES", {"aos": []}
        ), patch("web_rules_qa._HEADING_VOCABS", {"aos": []}):
            client = TestClient(app)
            response = client.post("/ask", json={"question": "   ", "game": "aos"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Question is required.")

    def test_valid_question_returns_parsed_response(self) -> None:
        mock_response = AskResponse(
            short_answer="Yes.",
            detailed_answer="You may reinforce.",
            source="WH Age of Sigmar Core Rules (4th ed.)",
            certainty=1,
        )

        with patch("web_rules_qa._VECTORSTORES", {"aos": MagicMock()}), patch(
            "web_rules_qa._SOURCES", {"aos": []}
        ), patch("web_rules_qa._HEADING_VOCABS", {"aos": []}), patch(
            "web_rules_qa.answer_question",
            return_value='{"short_answer": "Yes.", "detailed_answer": "You may reinforce.", "source": {"has_core_rules": true, "factions": []}, "certainty": 1}',
        ):
            client = TestClient(app)
            response = client.post(
                "/ask",
                json={"question": "Can I reinforce?", "game": "aos"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["short_answer"], mock_response.short_answer)
        self.assertEqual(response.json()["detailed_answer"], mock_response.detailed_answer)
        self.assertEqual(response.json()["source"], mock_response.source)
        self.assertEqual(response.json()["certainty"], mock_response.certainty)


if __name__ == "__main__":
    unittest.main()
