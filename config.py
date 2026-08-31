import os
from dotenv import load_dotenv

load_dotenv()

# Bot Token
TOKEN = os.getenv("TELEGRAM_TOKEN", "8645582951:AAGKtbHS3qF8VOFC4onst-8sf4ussasX5_I")

# ID do Administrador
ADMIN_ID = int(os.getenv("ADMIN_ID", "8776521959"))

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Preços Padrão por Categoria
PRECOS = {
    "gg": 4.0,
    "streaming": 12.0,
    "esim": 20.0
}

# Configurações de Deploy (Render)
PORT = int(os.getenv("PORT", 8080))
