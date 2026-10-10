"""Active only during package acceptance: forbid non-loopback Python networking."""

import ipaddress
import os
import socket

if os.environ.get("PINUI_OFFLINE_TEST") == "1":
    original_connect = socket.socket.connect
    original_resolve = socket.getaddrinfo

    def local(host):
        if host in {None, "localhost"}:
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def connect(self, address):
        if isinstance(address, tuple) and not local(address[0]):
            raise OSError("External network disabled for offline acceptance")
        return original_connect(self, address)

    def resolve(host, *args, **kwargs):
        if not local(host):
            raise OSError("External network disabled for offline acceptance")
        return original_resolve(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.getaddrinfo = resolve
