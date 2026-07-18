"""Bot Telegram de Loja Digital - Versão Completa Supabase."""

from __future__ import annotations
import logging
import os
import time
import threading
import random
import string
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import quote
import telebot
from telebot import apihelper, types
import database as db
from security_utils import CPFProtector
from flask import Flask

# --- Configurações ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PIX_ESTATICO = "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607181421TUV2VAB162WC66304B341"

# Inicializa o banco (Supabase)
db.criar_tabelas()

if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}

bot = telebot.TeleBot(TOKEN) if TOKEN else None
state: dict[int, dict[str, Any]] = {}

# --- Servidor Web Keep-Alive ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot Online e Seguro no Supabase", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Funções Auxiliares ---

def protect() -> CPFProtector:
    key = os.getenv("CPF_ENCRYPTION_KEY", "").strip()
    if not key: raise RuntimeError("Erro: CPF_ENCRYPTION_KEY ausente.")
    return CPFProtector.from_string(key)

def is_admin(message: Any) -> bool:
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

def register(obj: Any) -> None:
    user = obj.from_user
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or "Cliente"
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

def generate_gift_code():
    return "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))

# --- Comandos do Bot ---

if bot:
    # 1. Comandos Administrativos (Prioridade)
    
    @bot.message_handler(commands=["menu"])
    def admin_menu(message: Any):
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
            "📊 *Status:* `/estoque` | `/relatorio` | `/filas`"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["estoque"])
    def view_stock(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        bot.reply_to(message, f"📦 *ESTOQUE ATUAL*\n\n💳 GG: `{gg}`\n📺 Streaming: `{stream}`\n📶 eSIM: `{esim}`", parse_mode="Markdown")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        total, revenue, cats = db.obter_dados_relatorio()
        cat_str = "\n".join([f"• {k.title()}: {v}" for k, v in cats.items()])
        bot.reply_to(message, f"📈 *RELATÓRIO DE VENDAS*\n\nTotal: {total}\nFaturamento: R$ {revenue:.2f}\n\n*Categorias:*\n{cat_str}", parse_mode="Markdown")

    @bot.message_handler(commands=["filas"])
    def queues(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        gg, data, ready = db.obter_status_filas()
        bot.reply_to(message, f"📦 *STATUS DAS FILAS*\n\nGGs aguardando dados: {gg}\nDados aguardando GGs: {data}\n✅ Prontos: {ready}", parse_mode="Markdown")

    @bot.message_handler(commands=["add"])
    def add_command(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        parts = message.text.split()
        if len(parts) < 2: return
        option = parts[1].lower()
        if option == "gg":
            state[message.from_user.id] = {"flow": "gg_mass"}
            msg = bot.reply_to(message, "💳 *ADD GG EM MASSA*\nInforme a BIN (6-8 dígitos):")
            bot.register_next_step_handler(msg, gg_mass_bin)
        elif option == "dados":
            msg = bot.reply_to(message, "👤 *ADD DADOS EM MASSA*\nEnvie a lista `NOME|CPF`:")
            bot.register_next_step_handler(msg, data_mass_process)
        elif option == "streaming":
            msg = bot.reply_to(message, "📺 *ADD STREAMING EM MASSA*\nEnvie a lista `EMAIL|SENHA|TELA|SENHA`:")
            bot.register_next_step_handler(msg, stream_mass_process)

    def gg_mass_bin(message: Any):
        state[message.from_user.id]["bin"] = message.text.strip()
        msg = bot.reply_to(message, "🏦 Informe o Banco:")
        bot.register_next_step_handler(msg, gg_mass_bank)

    def gg_mass_bank(message: Any):
        state[message.from_user.id]["bank"] = message.text.strip()
        msg = bot.reply_to(message, "📥 Envie a lista `NUMERO|VALIDADE|CVV`:")
        bot.register_next_step_handler(msg, gg_mass_finish)

    def gg_mass_finish(message: Any):
        current = state.pop(message.from_user.id, None)
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            if "|" in line:
                try:
                    db.adicionar_gg_pendente(current["bin"], current["bank"], line.strip(), message.from_user.id)
                    s += 1
                except: e += 1
            else: e += 1
        bot.reply_to(message, f"✅ Sucesso: {s}\n❌ Erros: {e}\n\n📦 Total GG: {db.contar_estoque_categoria('gg')}")

    def data_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        p = protect()
        for line in lines:
            parts = line.split("|")
            if len(parts) == 2:
                try:
                    db.adicionar_dados_pendentes(parts[0].strip(), p.encrypt(parts[1].strip()), p.fingerprint(parts[1].strip()), message.from_user.id)
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

    @bot.message_handler(commands=["gerar_gift"])
    def create_gift(message: Any):
        if not is_admin(message): return
        try:
            val = float(message.text.split()[1])
            code = generate_gift_code()
            db.criar_gift(code, val, message.from_user.id)
            bot.reply_to(message, f"🎁 *GIFT CARD GERADO*\n\nCódigo: `{code}`\nValor: R$ {val:.2f}", parse_mode="Markdown")
        except: bot.reply_to(message, "Uso: `/gerar_gift 50`")

    # 2. Comandos de Usuário
    
    @bot.message_handler(commands=["start"])
    def start(message: Any):
        register(message)
        home(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["resgatar"])
    def redeem_gift_cmd(message: Any):
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Uso: `/resgatar CODIGO`")
            return
        res = db.resgatar_gift(parts[1].strip(), message.from_user.id)
        if res: bot.reply_to(message, f"✅ Sucesso! R$ {res:.2f} creditados.")
        else: bot.reply_to(message, "❌ Código inválido ou já usado.")

    @bot.message_handler(func=lambda m: m.text and m.text.startswith("/"))
    def unknown(message: Any):
        bot.reply_to(message, "❌ Código não encontrado, código não existente.")

    # 3. Callbacks e Menus
    
    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: Any):
        register(call)
        bot.answer_callback_query(call.id)
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        
        if data == "inicio": home(chat, uid)
        elif data == "saldo":
            markup = types.InlineKeyboardMarkup()
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
                bot.send_message(chat, "❌ Sem estoque no momento.")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, bk, c in groups:
                markup.add(types.InlineKeyboardButton(f"BIN {b} • {bk} • {c} un • R$ 4,00", callback_data=f"sg|{b}|{bk}"))
            bot.send_message(chat, "Escolha a BIN:", reply_markup=markup)
        elif data == "buy_streaming":
            # Lógica de compra de streaming aqui...
            bot.send_message(chat, "📺 Opção de Streaming em breve.")
        elif data == "buy_esim":
            bot.send_message(chat, "📶 Opção de eSIM em breve.")
        elif data == "conta":
            saldo = db.obter_saldo(uid)
            bot.send_message(chat, f"👤 *MINHA CONTA*\n\nID: `{uid}`\nSaldo: `R$ {saldo:.2f}`", parse_mode="Markdown")

    def home(chat: int, uid: int):
        saldo = db.obter_saldo(uid)
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"💳 GG • R$ 4,00 • {gg} un", callback_data="menu_gg"),
            types.InlineKeyboardButton(f"📺 Streaming • R$ 12,00 • {stream} un", callback_data="buy_streaming"),
            types.InlineKeyboardButton(f"📶 eSIM • R$ 20,00 • {esim} un", callback_data="buy_esim"),
            types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
            types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
            types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
        )
        bot.send_message(chat, f"🏪 *LOJA DIGITAL*\n\n💰 Saldo: `R$ {saldo:.2f}`", reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=20, skip_pending=True)
        except Exception as exc:
            LOG.error(f"Erro no polling: {exc}")
            time.sleep(5)
