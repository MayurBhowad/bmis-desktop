import pytest

from bmis_desktop.bmis.protocol import ProtocolParser


def test_parser_waits_for_incomplete_simple_string():
    parser = ProtocolParser()

    assert parser.feed(b"+OK\r") is None
    assert parser.feed(b"\n") == "OK"


def test_parser_waits_for_incomplete_bulk_string():
    parser = ProtocolParser()

    assert parser.feed(b"$5\r\nhe") is None
    assert parser.feed(b"llo\r\n") == "hello"


def test_parser_waits_for_incomplete_integer():
    parser = ProtocolParser()

    assert parser.feed(b":12") is None
    assert parser.feed(b"3\r\n") == 123


def test_parser_handles_complete_response_in_one_chunk():
    parser = ProtocolParser()

    assert parser.feed(b"+OK\r\n") == "OK"


def test_parser_handles_multiple_responses():
    parser = ProtocolParser()

    assert parser.feed(b"+OK\r\n:123\r\n") == "OK"
    assert parser.feed(b"") == 123