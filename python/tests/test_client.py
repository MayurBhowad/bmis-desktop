import socket
import threading
import pytest

from bmis_desktop.bmis.client import BMisClient

def test_client_connect_to_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()

    def accept_connection():
        connection, _ = server.accept()
        connection.close()

    thread = threading.Thread(target=accept_connection)
    thread.start()

    client = BMisClient(host, port)
    client.connect()

    assert client.is_connected()

    client.close()

    thread.join()
    server.close()


def test_client_sends_command_and_receives_response():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()

    def server_worker():
        connection, _ = server.accept()
        data = connection.recv(1024)

        assert data == b"PING\n"

        connection.sendall(b"+PONG\r\n")
        connection.close()

    thread = threading.Thread(target=server_worker)
    thread.start()

    client = BMisClient(host, port)
    client.connect()

    response = client.execute("PING")

    assert response == "PONG"

    client.close()

    thread.join()
    server.close()



def test_client_executes_set_and_get_against_real_bmis_server():
    client = BMisClient("127.0.0.1", 6379)

    client.connect()

    set_response = client.execute("SET bmis_desktop_test Mayur")
    get_response = client.execute("GET bmis_desktop_test")

    assert set_response == "OK"
    assert get_response == "Mayur"

    client.close()

def test_client_handles_response_split_across_tcp_chunks():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()
    first_chunk_sent = threading.Event()

    def server_worker():
        connection, _ = server.accept()

        data = connection.recv(1024)
        assert data == b"GET name\n"

        connection.sendall(b"$5\r\nhe")
        first_chunk_sent.set()

        first_chunk_sent.wait()
        connection.sendall(b"llo\r\n")

        connection.close()

    thread = threading.Thread(target=server_worker)
    thread.start()

    client = BMisClient(host, port)
    client.connect()

    response = client.execute("GET name")

    assert response == "hello"

    client.close()

    thread.join()
    server.close()

@pytest.mark.integration
def test_client_executes_set_and_get_against_real_bmis_server():
    client = BMisClient("127.0.0.1", 6379)

    try:
        client.connect()

        set_response = client.execute("SET bmis_desktop_test Mayur")
        get_response = client.execute("GET bmis_desktop_test")

        assert set_response == "OK"
        assert get_response == "Mayur"
    finally:
        client.close()


def test_client_rejects_empty_command():
    client = BMisClient("127.0.0.1", 6379)

    with pytest.raises(ValueError, match="empty"):
        client.execute("")


def test_client_rejects_embedded_newline():
    client = BMisClient("127.0.0.1", 6379)
    client.connect = lambda: None  # This test must not open a real connection.

    with pytest.raises(ValueError, match="newline"):
        client.execute("GET name\nDEL name")


def test_client_is_disconnected_after_close():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()

    def accept_connection():
        connection, _ = server.accept()
        connection.close()

    thread = threading.Thread(target=accept_connection)
    thread.start()

    client = BMisClient(host, port)
    client.connect()
    assert client.is_connected()

    client.close()
    assert not client.is_connected()

    thread.join(timeout=2)
    server.close()


def test_client_times_out_when_server_does_not_respond():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()
    accepted = threading.Event()

    def server_worker():
        connection, _ = server.accept()
        with connection:
            accepted.set()
            # Keep the connection open without sending a response.
            threading.Event().wait(timeout=2)

    thread = threading.Thread(target=server_worker)
    thread.start()

    client = BMisClient(host, port, socket_timeout=0.2)

    try:
        client.connect()
        assert accepted.wait(timeout=2)

        with pytest.raises(socket.timeout):
            client.execute("GET name")
    finally:
        client.close()
        thread.join(timeout=3)
        server.close()


def test_client_close_is_idempotent():
    client = BMisClient("127.0.0.1", 6379)

    client.close()
    client.close()

    assert not client.is_connected()



def test_client_disconnects_after_socket_timeout():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()
    accepted = threading.Event()
    release_server = threading.Event()

    def server_worker():
        connection, _ = server.accept()
        with connection:
            accepted.set()
            release_server.wait(timeout=3)

    thread = threading.Thread(target=server_worker)
    thread.start()

    client = BMisClient(host, port, socket_timeout=0.2)

    try:
        client.connect()
        assert accepted.wait(timeout=2)

        with pytest.raises(socket.timeout):
            client.execute("GET name")

        assert not client.is_connected()

        with pytest.raises(RuntimeError, match="not connected"):
            client.execute("GET name")
    finally:
        client.close()
        release_server.set()
        thread.join(timeout=4)
        server.close()
