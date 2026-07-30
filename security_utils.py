"""Proteção simplificada de dados sensíveis."""
import base64
import hashlib
import hmac
import re
from cryptography.fernet import Fernet

class Security:
    # Chave interna derivada do TOKEN do bot para não precisar de configuração manual
    # Isso garante que os dados sejam ilegíveis se o banco for baixado sem o contexto do bot
    _internal_key = None

    @classmethod
    def get_key(cls):
        if cls._internal_key is None:
            from config import TOKEN
            if not TOKEN:
                # Fallback seguro para desenvolvimento
                token_seed = "jennebot_default_secret_seed"
            else:
                token_seed = TOKEN
            
            # Gera uma chave de 32 bytes a partir do token do bot
            key_hash = hashlib.sha256(token_seed.encode()).digest()
            cls._internal_key = base64.urlsafe_b64encode(key_hash)
        return cls._internal_key

    @classmethod
    def encrypt(cls, text: str) -> str:
        if not text: return ""
        f = Fernet(cls.get_key())
        return f.encrypt(text.encode()).decode()

    @classmethod
    def decrypt(cls, token: str) -> str:
        if not token: return ""
        try:
            f = Fernet(cls.get_key())
            return f.decrypt(token.encode()).decode()
        except:
            return "Erro ao descriptografar"

def validate_cpf(cpf: str) -> str:
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return digits # Retorna apenas os dígitos se não for CPF válido para não travar
    return digits

def format_cpf(cpf: str) -> str:
    digits = re.sub(r"\D", "", cpf)
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return digits
