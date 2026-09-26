# -*- coding: utf-8 -*-
"""
crypto.py — AES-128-CBC encryption/decryption for Garena payloads.

Keys are read from config (which reads from ENV), so rotating keys after
a Garena update requires only changing AES_KEY / AES_IV env vars — no
code deploy.
"""

import binascii

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from src.core.config import config
from src.core.logger import get_logger

log = get_logger(__name__)


def encrypt_payload(hex_data: str) -> bytes:
    """
    Encrypt a hex-encoded protobuf payload using AES-128-CBC.

    Args:
        hex_data: Hex-encoded bytes of the serialized protobuf message.

    Returns:
        Raw encrypted bytes ready to POST to Garena.
    """
    raw = bytes.fromhex(hex_data)
    cipher = AES.new(config.aes_key, AES.MODE_CBC, config.aes_iv)
    padded = pad(raw, AES.block_size)
    encrypted = cipher.encrypt(padded)
    return encrypted


def encrypt_payload_hex(hex_data: str) -> str:
    """Convenience wrapper — returns hex string of encrypted bytes."""
    return binascii.hexlify(encrypt_payload(hex_data)).decode()


def decrypt_payload(encrypted_bytes: bytes) -> bytes:
    """
    Decrypt a raw AES-128-CBC response from Garena.

    Note: Garena's /GetPlayerPersonalShow endpoint does NOT encrypt the
    response — it returns raw protobuf.  This function is provided for
    future compatibility with endpoints that do encrypt responses.

    Args:
        encrypted_bytes: Raw bytes from Garena response body.

    Returns:
        Decrypted raw bytes (protobuf).
    """
    cipher = AES.new(config.aes_key, AES.MODE_CBC, config.aes_iv)
    decrypted = cipher.decrypt(encrypted_bytes)
    return unpad(decrypted, AES.block_size)


def serialize_uid_request(uid: int) -> str:
    """
    Build and serialize a uid_generator protobuf message, returning hex.

    Keeps protobuf import isolated here so crypto.py is the single
    entry-point for building Garena request payloads.
    """
    import sys
    import os

    # Ensure protobuf path is available
    proto_dir = os.path.join(os.path.dirname(__file__), "protobuf")
    if proto_dir not in sys.path:
        sys.path.insert(0, proto_dir)

    from src.ff.protobuf import uid_generator_pb2  # noqa: PLC0415

    msg = uid_generator_pb2.uid_generator()
    msg.saturn_ = uid
    msg.garena = 1
    return binascii.hexlify(msg.SerializeToString()).decode()
