"""Validação e proteção de CPF em repouso."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


class CPFError(ValueError):
    """Erro de CPF ou de chave criptográfica."""


@dataclass(frozen=True)
class CPFProtector:
    """Criptografa CPF e produz uma impressão HMAC para auditoria."""

    key: bytes

    @classmethod
    def from_string(cls, key: str) -> "CPFProtector":
        raw = key.strip().encode("ascii")
        try:
            decoded = base64.urlsafe_b64decode(raw)
        except Exception as exc:  # noqa: BLE001
            raise CPFError("CPF_ENCRYPTION_KEY inválida.") from exc
        if len(decoded) != 32:
            raise CPFError("CPF_ENCRYPTION_KEY deve ser uma chave Fernet válida.")
        Fernet(raw)
        return cls(raw)

    def encrypt(self, cpf: str) -> str:
        normalized = validate_cpf(cpf)
        return Fernet(self.key).encrypt(normalized.encode("ascii")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            normalized = Fernet(self.key).decrypt(token.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError) as exc:
            raise CPFError("Não foi possível descriptografar o CPF.") from exc
        return format_cpf(validate_cpf(normalized))

    def fingerprint(self, cpf: str) -> str:
        normalized = validate_cpf(cpf).encode("ascii")
        signing_key = base64.urlsafe_b64decode(self.key)
        return hmac.new(signing_key, normalized, hashlib.sha256).hexdigest()


def validate_cpf(cpf: str) -> str:
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11 or digits == digits[0] * 11:
        raise CPFError("CPF inválido.")

    def digit(base: str, weights: range) -> int:
        result = (
            sum(int(value) * weight for value, weight in zip(base, weights)) * 10
        ) % 11
        return 0 if result == 10 else result

    if (
        digits[-2:]
        != f"{digit(digits[:9], range(10, 1, -1))}{digit(digits[:10], range(11, 1, -1))}"
    ):
        raise CPFError("CPF inválido.")
    return digits


def format_cpf(cpf: str) -> str:
    digits = validate_cpf(cpf)
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
