import socket
import threading

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