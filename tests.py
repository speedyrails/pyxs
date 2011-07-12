# -*- coding: utf-8 -*-

import string

import pytest

from pyxs import Op, Packet
from pyxs.exceptions import InvalidOperation, InvalidPayload, InvalidPath
from pyxs.helpers import compile, validate_path


def test_packet():
    # a) invalid operation.
    with pytest.raises(InvalidOperation):
        Packet(-1, "", 0)

    # b) invalid payload -- maximum size exceeded.
    with pytest.raises(InvalidPayload):
        Packet(Op.DEBUG, "hello" * 4096, 0)


def test_packet_from_string():
    d = b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00OK\x00"
    p = Packet.from_string(d)

    assert p.op == Op.DEBUG
    assert p.req_id == 0
    assert p.tx_id == 0
    assert p.len == 3
    assert p.payload == b"OK\x00"
    assert len(p.payload) == p.len
    assert str(p) == d


# Helpers.

def test_compile():
    # a) <foo> -- non-empty string with no NULL bytes.
    patterns = compile("<foo>")
    assert "foo" in patterns

    regex = patterns["foo"]
    assert regex.match("foo")
    assert not regex.match("foo\x00")
    assert not regex.match("f\x00oo")
    assert not regex.match("")

    # b) <foo|> -- non-empty string with zero or more NULL bytes.
    patterns = compile("<foo|>")
    assert "foo" in patterns

    regex = patterns["foo"]
    assert regex.match("foo")
    assert regex.match("foo\x00")
    assert regex.match("f\x00\x00oo")
    assert not regex.match("")

    # c) <foo>| -- non-empty string with no NULL bytes, followed by a
    #    trailing NULL.
    patterns = compile("<foo>|")
    assert "foo" in patterns

    regex = patterns["foo"]
    assert regex.match("foo\x00")
    assert not regex.match("\x00")
    assert not regex.match("f\x00oo\x00")
    assert not regex.match("")

    # d) <foo>|* -- zero or more non-empty strings with no NULL bytes,
    #    followed by a trailing NULL.
    patterns = compile("<foo>|*")
    assert "foo" in patterns

    regex = patterns["foo"]
    assert regex.match("")
    assert regex.match("foo\x00")
    assert regex.match("foo\x00bar\x00")
    assert not regex.match("foo\x00bar\x00\x00")
    assert not regex.match("\x00")

    # e) <foo>|+ -- one or more non-empty strings with no NULL bytes,
    #    followed by a trailing NULL.
    patterns = compile("<foo>|+")
    assert "foo" in patterns

    regex = patterns["foo"]
    assert regex.match("foo\x00")
    assert regex.match("foo\x00bar\x00")
    assert not regex.match("foo\x00bar\x00\x00")
    assert not regex.match("\x00")
    assert not regex.match("")


def test_validate_path():
    # a) max length is bounded by 3072 for absolute path and 2048 for
    #    relative ones.
    with pytest.raises(InvalidPath):
        validate_path("/foo/bar" * 3072)

    with pytest.raises(InvalidPath):
        validate_path("foo/bar" * 2048)

    # b) ASCII alphanumerics and -/_@ only!
    for char in string.punctuation:
        if char in "-/_@": continue

        with pytest.raises(InvalidPath):
            validate_path("/foo" + char)

    with pytest.raises(InvalidPath):
        validate_path("/foo\x00")

    # c) no trailing / -- except for root path.
    with pytest.raises(InvalidPath):
        validate_path("/foo/")

    try:
        validate_path("/")
    except InvalidPath:
        pytest.fail("/ is prefectly valid, baby :)")
