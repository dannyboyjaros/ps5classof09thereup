#!/usr/bin/env python3
"""Send a raw payload ELF to ps5-payload-elfldr and stream its stdio."""
import socket
import sys

host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.197"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 9021
path = sys.argv[3] if len(sys.argv) > 3 else "c09diag.elf"

with open(path, "rb") as stream:
    payload = stream.read()

sock = socket.create_connection((host, port), timeout=20)
sock.sendall(payload)
sock.shutdown(socket.SHUT_WR)
sock.settimeout(20)
chunks = []
while True:
    try:
        data = sock.recv(65536)
    except socket.timeout:
        break
    if not data:
        break
    chunks.append(data)
sock.close()
sys.stdout.buffer.write(b"".join(chunks))
