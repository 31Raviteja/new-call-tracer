from app.services.parser import EventParser


def test_parser_counts_malformed_event():
    parser = EventParser()
    result = parser.parse("2026-08-07T06:31:43#:EVENT[bad-format]: {")
    assert result is None
    assert parser.parse_errors == 1


def test_parser_ignores_non_event_line():
    parser = EventParser()
    assert parser.parse("normal log line") is None
    assert parser.parse_errors == 0
