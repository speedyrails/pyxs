# -*- coding: utf-8 -*-
"""
    pyxs
    ~~~~

    Pure Python bindings for communicating with XenStore over Unix socket.

    :copyright: (c) 2011 by Selectel, see AUTHORS for more details.
"""

from __future__ import absolute_import, print_function, unicode_literals

import re
import socket
import struct
from collections import namedtuple

from .exceptions import InvalidOperation, InvalidPayload
from .helpers import spec


#: Operations supported by XenStore.
Op = namedtuple("Operation", [
    "DEBUG",
    "DIRECTORY",
    "READ",
    "GET_PERMS",
    "WATCH",
    "UNWATCH",
    "TRANSACTION_START",
    "TRANSACTION_END",
    "INTRODUCE",
    "RELEASE",
    "GET_DOMAIN_PATH",
    "WRITE",
    "MKDIR",
    "RM",
    "SET_PERMS",
    "WATCH_EVENT",
    "ERROR",
    "IS_DOMAIN_INTRODUCED",
    "RESUME",
    "SET_TARGET",
    "RESTRICT"
])(*(range(20) + [128]))


class Packet(namedtuple("_Packet", "op req_id tx_id len payload")):
    """A single message to or from XenStore.

    :param int op: an item from :data:`~pyxs.Op`, representing
                   operation, performed by this packet.
    :param bytes payload: packet payload, should be a valid ASCII-string
                          with characters between ``[0x20;0x7f]``.
    :param int req_id: request id -- hopefuly a **unique** identifier
                       for this packet.
    :param int tx_id: transaction id, defaults to ``0`` -- which means
                      no transaction is running.
    """
    #: ``xsd_sockmsg`` struct format see ``xen/include/public/io/xs_wire.h``
    #: for details.
    _fmt = b"IIII"

    def __new__(cls, op, payload, req_id, tx_id=None):
        if isinstance(payload, unicode):
            payload = payload.encode("utf-8")

        # Checking restrictions:
        # a) payload is limited to 4096 bytes.
        if len(payload) > 4096:
            raise InvalidPayload(payload)
        # b) operation requested is present in ``xsd_sockmsg_type``.
        if op not in Op:
            raise InvalidOperation(op)

        if tx_id is None: tx_id = 0

        return super(Packet, cls).__new__(cls,
            op, req_id or 0, tx_id, len(payload), payload)

    @classmethod
    def from_string(cls, s):
        if isinstance(s, unicode):
            s = s.encode("utf-8")

        type, req_id, tx_id, l = map(int,
            struct.unpack(cls._fmt, s[:struct.calcsize(cls._fmt)]))
        return cls(type, s[-l:], req_id, tx_id)

    def __str__(self):
        # Note the ``[:-1]`` slice -- the actual payload is excluded.
        return struct.pack(self._fmt, *self[:-1]) + self.payload


class Connection(object):
    """XenStore connection object."""

    def __init__(self, addr):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(addr)

    # Private API.
    # ............

    def send(self, type, payload):
        # .. note:: `req_id` is allways 0 for now.
        self.socket.send(str(Packet(type, payload, 0)))

        chunks, done = [], False
        while not done:
            try:
                data = self.socket.recv(1024)
            except socket.error:
                done = True
            else:
                chunks.append(data)
                done = len(data) <= 1024
        else:
            return Packet.from_string("".join(chunks))

    def command(self, type, *args):
        packet = self.send(type, "\x00".join(args))

        # According to ``xenstore.txt`` erroneous responses start with
        # a capital E and end with ``NULL``-byte.
        if re.match(r"^E[A-Z]+\x00$", packet.payload):
            raise RuntimeError(packet.payload[:-1])

        return packet

    # Public API.
    # ...........

    @spec("<path>|")
    def read(self, path):
        """Reads the octet string value at a given path."""
        return self.command(Op.READ, path + "\x00")

    @spec("<path>|", "<value|>")
    def write(self, path, value):
        """Write a value to a given path."""
        return self.command(Op.WRITE, path, value)

    @spec("<path>|")
    def mkdir(self, path):
        """Ensures that a given path exists, by creating it and any
        missing parents with empty values. If `path` or any parent
        already exist, its value is left unchanged.
        """
        return self.command(Op.MKDIR, path + "\x00")

    @spec("<path>|")
    def rm(self, path):
        """Ensures that a given does not exist, by deleting it and all
        of its children. It is not an error if `path` doesn't exist, but
        it **is** an error if `path`'s immediate parent does not exist
        either.
        """
        return self.command(Op.RM, path + "\x00")

    def debug(self, *args):
        """A simple echo call.

        **Syntax**::

          "print"|<string>|??           sends <string> to debug log
          "print"|<thing-with-no-null>  EINVAL
          "check"|??                    check xenstored internals
          <anything-else|>              no-op (future extension)
        """
        return self.command(Op.DEBUG, *args)
