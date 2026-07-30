import os
from dotenv import load_dotenv

load_dotenv()

# Bot Token (Configurado conforme enviado pelo usuário)
TOKEN = os.getenv("TELEGRAM_TOKEN", "8645582951:AAGKtbHS3qF8VOFC4onst-8sf4ussasX5_I")

# ID do Administrador (ID Real: 8776521959)
ADMIN_ID = int(os.getenv("ADMIN_ID", "8776521959"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# PIX (Configurado conforme enviado pelo usuário)
PIX_ESTATICO = os.getenv("PIX_ESTATICO", "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607091522JQUFQ7JV15AEW6304F5BF")

# Preços Padrão
PRECOS = {
    "gg": 4.0,
    "streaming": 12.0,
    "esim": 20.0
}

# Configurações de Deploy
PORT = int(os.getenv("PORT", 8080))
