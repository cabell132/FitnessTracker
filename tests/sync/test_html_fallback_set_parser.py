"""Unit tests for the HtmlFallbackSetParser wrapper."""

from __future__ import annotations

from fitness_tracker.sync._true_coach_html import HtmlFallbackSetParser


class TestHtmlFallbackSetParser:
    """Tests for the SetParser-compatible wrapper."""

    def test_returns_non_empty_sets(self) -> None:
        parser = HtmlFallbackSetParser()
        result = parser.parse_the_sets("3 x 10 reps")
        assert len(result.sets) >= 1

    def test_default_set_is_normal_type(self) -> None:
        parser = HtmlFallbackSetParser()
        result = parser.parse_the_sets("")
        assert result.sets[0].type == "normal"

    def test_default_set_has_duration(self) -> None:
        parser = HtmlFallbackSetParser()
        result = parser.parse_the_sets("")
        assert result.sets[0].duration_seconds == 60

    def test_satisfies_set_parser_protocol(self) -> None:
        """HtmlFallbackSetParser should satisfy the SetParser protocol."""
        from fitness_tracker.sync.ports.set_parser import SetParser

        parser = HtmlFallbackSetParser()
        assert isinstance(parser, SetParser)
