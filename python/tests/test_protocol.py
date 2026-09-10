from bmis_desktop.bmis.protocol import decode_response


def test_decode_simple_string():
    assert decode_response(b"+OK\r\n") == "OK"

def test_decode_integer():
    assert decode_response(b":123\r\n") == 123

def test_decode_bulk_string():
    assert decode_response(b"$5\r\nhello\r\n") == "hello"


def test_decode_null_bulk_string():
    assert decode_response(b"$-1\r\n") is None


def test_decode_array():
    response = b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n"

    assert decode_response(response) == ["foo", "bar"]


def test_decode_error():
    assert decode_response(b"-ERR something went wrong\r\n") == (
        "ERR something went wrong"
    )


def test_decode_wrong_type_error():
    assert decode_response(b"-WRONGTYPE wrong type\r\n") == (
        "WRONGTYPE wrong type"
    )