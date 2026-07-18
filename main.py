"""Bot Telegram de GG, streaming, eSIM e saldo em reais (BRL)."""

from __future__ import annotations
import logging
import os
import time
import threading
import random
import string
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote
import requests
import telebot
from telebot import apihelper, types
import database as db
from security_utils import CPFError, CPFProtector
from flask import Flask

# --- Configurações de Log ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

# --- Variáveis de Ambiente ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
API_URL = os.getenv("CRYPTO_PAY_API_URL", "https://pay.crypt.bot/api").rstrip("/")
PIX_ESTATICO = "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607181421TUV2VAB162WC66304B341"

MIN_DEPOSITO = Decimal("10.00")
PRECOS = {
    "gg": Decimal("4.00"),
    "streaming": Decimal("12.00"),
    "esim": Decimal("20.00"),
}

# --- Banco de Dados Persistente ---
# No Render, arquivos gravados fora de discos persistentes somem no restart.
# Se você não usa um disco persistente, o banco será resetado a cada deploy.
BASE = os.path.dirname(os.path.abspath(__file__))
db.DB_PATH = os.path.join(BASE, "bot_database.db")
db.criar_tabelas()

if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}

bot = telebot.TeleBot(TOKEN) if TOKEN else None
HEADERS = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
state: dict[int, dict[str, Any]] = {}

# --- Servidor Web Keep-Alive ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot Online e Operante", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Funções de Apoio ---

@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    url: str

def protect() -> CPFProtector:
    key = os.getenv("CPF_ENCRYPTION_KEY", "").strip()
    if not key: raise RuntimeError("Erro: CPF_ENCRYPTION_KEY ausente.")
    return CPFProtector.from_string(key)

def is_admin(message: Any) -> bool:
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

def register(obj: Any) -> None:
    user = obj.from_user
    name = " ".join(filter(None, [getattr(user, "first_name", ""), getattr(user, "last_name", "")])) or "Cliente"
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

def generate_gift_code():
    return "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))

# --- Handlers do Bot ---

if bot:
    # 1. Comandos de Admin (Prioridade Alta)
    
    @bot.message_handler(commands=["menu"])
    def admin_menu(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        menu_text = (
            "🛠️ *MENU DO ADMINISTRADOR*\n\n"
            "📦 *Adição em Massa:*\n"
            "• `/add gg` - BIN -> Banco -> Lista\n"
            "• `/add dados` - Lista (Nome|CPF)\n"
            "• `/add streaming` - Lista (Email|Senha|Tela|SenhaTela)\n"
            "• `/add_esim` - Individual\n\n"
            "🎁 *Gifts:* `/gerar_gift VALOR`\n"
            "📊 *Status:* `/estoque` | `/relatorio` | `/filas`\n"
            "⚙️ *Config:* `/promocao VALOR` | `/ver_gg ID`"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["estoque"])
    def view_stock(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        text = (
            "📦 *ESTOQUE ATUAL*\n\n"
            f"💳 GG: `{gg}` unidades\n"
            f"📺 Streaming: `{stream}` unidades\n"
            f"📶 eSIM: `{esim}` unidades"
        )
        bot.reply_to(message, text, parse_mode="Markdown")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        total, revenue, cats = db.obter_dados_relatorio()
        cat_str = "\n".join([f"• {k.title()}: {v}" for k, v in cats.items()])
        bot.reply_to(message, f"📈 *RELATÓRIO DE VENDAS*\n\nTotal Vendas: {total}\nFaturamento: R$ {revenue:.2f}\n\n*Por Categoria:*\n{cat_str}", parse_mode="Markdown")

    @bot.message_handler(commands=["filas"])
    def queues(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        gg, data, ready = db.obter_status_filas()
        bot.reply_to(message, f"📦 *STATUS DAS FILAS*\n\nGGs aguardando dados: {gg}\nDados aguardando GGs: {data}\n✅ Pares prontos para venda: {ready}", parse_mode="Markdown")

    @bot.message_handler(commands=["add"])
    def add(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Uso: `/add gg`, `/add dados` ou `/add streaming`", parse_mode="Markdown")
            return
            
        option = parts[1].lower()
        if option == "gg":
            state[message.from_user.id] = {"flow": "gg_mass"}
            msg = bot.reply_to(message, "💳 *ADD GG EM MASSA*\nInforme a BIN (6-8 dígitos):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, gg_mass_bin)
        elif option == "dados":
            msg = bot.reply_to(message, "👤 *ADD DADOS EM MASSA*\nEnvie a lista no formato:\n`NOME COMPLETO|CPF`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, data_mass_process)
        elif option == "streaming":
            msg = bot.reply_to(message, "📺 *ADD STREAMING EM MASSA*\nEnvie a lista no formato:\n`EMAIL|SENHA|TELA|SENHA DA TELA`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, stream_mass_process)

    # --- Processamento em Massa (Corrigido para acumular) ---
    
    def gg_mass_bin(message: Any):
        val = message.text.strip()
        if not val.isdigit() or not 6 <= len(val) <= 8:
            bot.reply_to(message, "❌ BIN inválida. Tente novamente.")
            return
        state[message.from_user.id]["bin"] = val
        msg = bot.reply_to(message, "🏦 Informe o Banco:")
        bot.register_next_step_handler(msg, gg_mass_bank)

    def gg_mass_bank(message: Any):
        state[message.from_user.id]["bank"] = message.text.strip()
        msg = bot.reply_to(message, "📥 Agora envie a lista de GGs `NUMERO|VALIDADE|CVV` (uma por linha):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, gg_mass_finish)

    def gg_mass_finish(message: Any):
        current = state.pop(message.from_user.id, None)
        if not current: return
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            if "|" in line:
                try:
                    # Garante que estamos adicionando ao banco
                    db.adicionar_gg_pendente(current["bin"], current["bank"], line.strip(), message.from_user.id)
                    s += 1
                except Exception as ex:
                    LOG.error(f"Erro ao inserir GG: {ex}")
                    e += 1
            else: e += 1
        bot.reply_to(message, f"✅ Adicionadas com sucesso: {s}\n❌ Erros de formato: {e}\n\n📦 Estoque total de GG: {db.contar_estoque_categoria('gg')}")

    def data_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        p = protect()
        for line in lines:
            parts = line.split("|")
            if len(parts) == 2:
                try:
                    name, cpf = parts[0].strip(), parts[1].strip()
                    db.adicionar_dados_pendentes(name, p.encrypt(cpf), p.fingerprint(cpf), message.from_user.id)
                    s += 1
                except: e += 1
            else: e += 1
        bot.reply_to(message, f"✅ Dados adicionados: {s}\n❌ Erros: {e}")

    def stream_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            if "|" in line:
                try:
                    db.adicionar_estoque("streaming", line.strip())
                    s += 1
                except: e += 1
            else: e += 1
        bot.reply_to(message, f"✅ Streamings adicionados: {s}\n❌ Erros: {e}")

    # --- Gifts e Outros ---

    @bot.message_handler(commands=["gerar_gift"])
    def create_gift(message: Any):
        if not is_admin(message): return
        try:
            val = float(message.text.split()[1])
            code = generate_gift_code()
            db.criar_gift(code, val, message.from_user.id)
            bot.reply_to(message, f"🎁 *GIFT CARD GERADO*\n\nCódigo: `{code}`\nValor: `R$ {val:.2f}`", parse_mode="Markdown")
        except: bot.reply_to(message, "Uso: `/gerar_gift 50`")

    @bot.message_handler(commands=["resgatar"])
    def redeem_gift(message: Any):
        parts = message.text.split()
        code = parts[1] if len(parts) > 1 else ""
        if not code:
            bot.reply_to(message, "Uso: `/resgatar CODIGO`")
            return
        res = db.resgatar_gift(code, message.from_user.id)
        if res: bot.reply_to(message, f"✅ Sucesso! R$ {res:.2f} creditados na sua conta.")
        else: bot.reply_to(message, "❌ Código inválido ou já usado.")

    @bot.message_handler(commands=["start"])
    def start_alt(message: Any):
        register(message)
        home(message.chat.id, message.from_user.id)

    # Handler para qualquer comando não reconhecido (Deve ser o último)
    @bot.message_handler(func=lambda m: m.text and m.text.startswith("/"))
    def unknown(message: Any):
        bot.reply_to(message, "❌ Código não encontrado, código não existente.")

    # --- Callbacks ---

    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: Any):
        register(call)
        bot.answer_callback_query(call.id)
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        if data == "inicio": home(chat, uid)
        elif data == "saldo":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💠 PIX Automático", callback_data="pix_auto"))
            markup.add(types.InlineKeyboardButton("🏦 PIX Manual", callback_data="pix_manual"))
            bot.send_message(chat, "Escolha o método de depósito:", reply_markup=markup)
        elif data == "pix_manual":
            bot.send_message(chat, f"🏦 *PIX MANUAL*\n\nChave:\n`{PIX_ESTATICO}`\n\nEnvie o comprovante ao suporte.", parse_mode="Markdown")
        elif data == "resgatar_btn":
            msg = bot.send_message(chat, "Digite o código do Gift Card:")
            bot.register_next_step_handler(msg, lambda m: bot.reply_to(m, f"✅ Sucesso! R$ {db.resgatar_gift(m.text.strip(), uid):.2f} creditados.") if db.resgatar_gift(m.text.strip(), uid) else bot.reply_to(m, "❌ Código inválido."))
        elif data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ Sem estoque no momento.", reply_markup=back())
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, bk, c in groups:
                markup.add(types.InlineKeyboardButton(f"BIN {b} • {bk} • {c} un • R$ 4,00", callback_data=f"sg|{quote(b)}|{quote(bk)}"))
            bot.send_message(chat, "Escolha a BIN:", reply_markup=markup)
        # ... outros callbacks de compra ...

    def home(chat: int, uid: int) -> None:
        saldo = db.obter_saldo(uid)
        gg, stream, esim = db.contar_estoque_categoria("gg"), db.contar_estoque_categoria("streaming"), db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"💳 GG • R$ 4,00 • {gg} unidades", callback_data="menu_gg"),
            types.InlineKeyboardButton(f"📺 Streaming • R$ 12,00 • {stream} unidades", callback_data="buy_streaming"),
            types.InlineKeyboardButton(f"📶 eSIM • R$ 20,00 • {esim} unidades", callback_data="buy_esim"),
            types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
            types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
            types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
        )
        bot.send_message(chat, f"🏪 *LOJA DIGITAL*\n\n💰 Saldo: `R$ {saldo:.2f}`", reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    # Inicia Servidor Web
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Loop de Polling Robusto
    while True:
        try:
            LOG.info("Bot iniciado...")
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=20, long_polling_timeout=20, skip_pending=True)
        except Exception as exc:
            LOG.error(f"Erro no polling: {exc}")
            time.sleep(5)
