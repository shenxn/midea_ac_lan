"""Midea BLE secure-session frames."""

# BLE state and catalog mappings contain heterogeneous protocol values.
# ruff: file-ignore[any-type, docstring-missing-returns, docstring-missing-exception, magic-value-comparison]
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SERVICE = "0000ffa0-0000-1000-8000-00805f9b34fb"
WRITE = SERVICE.replace("ffa0", "ffa1")
NOTIFY = SERVICE.replace("ffa0", "ffa2")


def checksum(data: bytes | bytearray) -> int:
    """Return the additive wire checksum."""
    return (-sum(data)) & 255


def signed(data: bytes | bytearray) -> bytes:
    """Append the additive checksum to a frame."""
    return bytes(data) + bytes([checksum(data)])


def encrypt(key: bytes, data: bytes) -> bytes:
    """Encrypt a session payload with a fresh nonce."""
    nonce = os.urandom(8)
    return nonce + AESCCM(key, tag_length=8).encrypt(nonce, data, None)


class Session:
    """Session interface for exact-model Bluetooth appliances."""

    def __init__(self, kind: int, model: bytes, address: str) -> None:
        """Initialize the model-specific Bluetooth state."""
        self.identity = bytes([kind]) + model + bytes.fromhex(address.replace(":", ""))
        self.root = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=None,
            info=b"midea_bleapp",
        ).derive(self.identity)
        self.key: bytes | None = None
        self.link_seq, self.sec_seq = os.urandom(2)
        self.open_id = os.urandom(6)

    def packet(self, cmd: int, body: bytes) -> bytes:
        """Encode a sequenced authenticated session packet."""
        self.sec_seq = self.sec_seq % 255 + 1
        self.link_seq = self.link_seq % 255 + 1
        key = self.key if cmd == 4 else self.root
        if key is None:
            raise ValueError("Missing session key")
        encrypted = encrypt(
            key,
            bytes([cmd, self.sec_seq, len(body)]) + body,
        )
        return b"\xaa\x55" + signed(
            bytes([len(encrypted) + 4, self.link_seq, 3 if cmd == 4 else 2])
            + encrypted,
        )

    def confirm(self, peer: bytes) -> bytes:
        """Derive the peer session key and confirm our identity."""
        priv = ec.generate_private_key(ec.SECP256R1())
        pub = priv.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )[1:]
        point = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(),
            b"\x04" + peer,
        )
        self.key = hashlib.sha256(priv.exchange(ec.ECDH(), point)).digest()[:16]
        return self.packet(3, pub + encrypt(self.key, self.identity))

    def request(self, msg: bytes) -> bytes:
        """Wrap an appliance command in the authenticated session."""
        return self.packet(4, signed(bytes([32, len(msg) + 4, 0]) + msg))

    def decode(self, raw: bytes) -> Any:
        """Validate and decrypt a received session packet."""
        if (
            len(raw) < 6
            or raw[:2] != b"\xaa\x55"
            or len(raw) != raw[2] + 2
            or sum(raw[2:]) % 256
            or raw[4] not in {2, 3}
        ):
            raise ValueError("Invalid BLE envelope")
        data = raw[5:-1]
        if len(data) < 19:
            raise ValueError("BLE security error")
        key = self.root if raw[4] == 2 else self.key
        if key is None:
            raise ValueError("Missing session key")
        plain = AESCCM(key, tag_length=8).decrypt(data[:8], data[8:], None)
        if len(plain) < 3 or len(plain) != 3 + plain[2]:
            raise ValueError("Invalid security frame")
        cmd, body = plain[0], plain[3:]
        if cmd == 4:
            # The 7600002B reply checksum excludes its business type byte.
            if (
                len(body) < 4
                or body[0] != 32
                or body[1] != len(body)
                or sum(body[1:]) % 256
                and sum(body) % 256
            ):
                raise ValueError("Invalid appliance envelope")
            body = body[3:-1]
        return cmd, body
