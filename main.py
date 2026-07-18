"""Bot Telegram de Loja Digital - Versão Final com Entrega Automática Supabase."""

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

PRECOS = {
    "gg": 4.0,
    "streaming": 12.0,
    "esim": 20.0,
}

db.criar_tabelas()

if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}

bot = telebot.TeleBot(TOKEN) if TOKEN else None

# --- Servidor Web ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot Online", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Auxiliares ---

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

# --- Handlers ---

if bot:
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
            "• `/add streaming` - Lista (Email|Senha|Tela|Senha)\n\n"
            "🎁 *Gifts:* `/gerar_gift VALOR`\n"
            "📊 *Status:* `/estoque` | `/relatorio` | `/filas`"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["gerar_gift"])
    def create_gift(message: Any):
        if not is_admin(message): return
        try:
            val = float(message.text.split()[1])
            code = "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
            db.criar_gift(code, val, message.from_user.id)
            bot.reply_to(message, f"🎁 *GIFT CARD GERADO*\n\nCódigo: `{code}`\nValor: R$ {val:.2f}", parse_mode="Markdown")
        except: bot.reply_to(message, "Uso: `/gerar_gift 50`")

    @bot.message_handler(commands=["start"])
    def start(message: Any):
        register(message)
        home(message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: Any):
        register(call)
        bot.answer_callback_query(call.id)
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        
        if data == "inicio": home(chat, uid)
        elif data == "resgatar_btn":
            msg = bot.send_message(chat, "📥 Digite ou cole o código do seu Gift Card:")
            bot.register_next_step_handler(msg, process_gift_step)
        elif data == "saldo":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🏦 PIX Manual", callback_data="pix_manual"))
            bot.send_message(chat, "Escolha o método de depósito:", reply_markup=markup)
        elif data == "pix_manual":
            bot.send_message(chat, f"🏦 *PIX MANUAL*\n\nChave:\n`{PIX_ESTATICO}`", parse_mode="Markdown")
        
        # --- FLUXO DE COMPRA ---
        elif data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ Sem estoque de GG no momento.")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, bk, c in groups:
                markup.add(types.InlineKeyboardButton(f"BIN {b} • {bk} • {c} un • R$ 4,00", callback_data=f"buy|gg|{b}|{bk}"))
            bot.send_message(chat, "Escolha a BIN da GG:", reply_markup=markup)
            
        elif data == "buy_streaming":
            count = db.contar_estoque_categoria("streaming")
            if count == 0:
                bot.send_message(chat, "❌ Sem estoque de Streaming no momento.")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 12,00)", callback_data="confirm_buy|streaming"))
            bot.send_message(chat, f"📺 *COMPRAR STREAMING*\n\nEstoque: `{count}` un\nValor: `R$ 12,00`", reply_markup=markup, parse_mode="Markdown")

        elif data.startswith("confirm_buy|") or data.startswith("buy|gg|"):
            process_purchase(call)

    def process_purchase(call: Any):
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        saldo = db.obter_saldo(uid)
        
        # Identifica categoria e preço
        if data.startswith("buy|gg|"):
            cat, price = "gg", PRECOS["gg"]
            parts = data.split("|")
            bin_v, bank_v = parts[2], parts[3]
        else:
            cat = data.split("|")[1]
            price = PRECOS[cat]
            bin_v, bank_v = None, None

        if saldo < price:
            bot.send_message(chat, f"❌ Saldo insuficiente! Você tem R$ {saldo:.2f} e precisa de R$ {price:.2f}.")
            return

        # Tenta concluir a compra
        inv_id = f"BUY-{int(time.time())}-{uid}"
        status, sid, conteudo = db.concluir_compra_fatura(inv_id, uid, cat, price, bin_v, bank_v)

        if status == "ok":
            bot.send_message(chat, "✅ *COMPRA REALIZADA COM SUCESSO!*", parse_mode="Markdown")
            if cat == "gg":
                dados_entrega = db.obter_dados_gg_para_entrega(sid, uid)
                p = protect()
                cpf = p.decrypt(dados_entrega[3])
                msg = (
                    f"💳 *DADOS DA GG*\n\n"
                    f"BIN: `{dados_entrega[0]}`\n"
                    f"Banco: `{dados_entrega[1]}`\n"
                    f"Conteúdo: `{conteudo}`\n\n"
                    f"👤 *DADOS DO TITULAR*\n"
                    f"Nome: `{dados_entrega[2]}`\n"
                    f"CPF: `{cpf}`"
                )
            elif cat == "streaming":
                parts = conteudo.split("|")
                msg = (
                    f"📺 *DADOS DO STREAMING*\n\n"
                    f"Email: `{parts[0]}`\n"
                    f"Senha: `{parts[1]}`\n"
                    f"Tela: `{parts[2]}`\n"
                    f"Senha da Tela: `{parts[3]}`"
                )
            else:
                msg = f"📦 *CONTEÚDO:* `{conteudo}`"
            
            bot.send_message(chat, msg, parse_mode="Markdown")
        else:
            bot.send_message(chat, "❌ Erro ao processar compra. Verifique o estoque.")

    def process_gift_step(message: Any):
        code = message.text.strip()
        valor = db.resgatar_gift(code, message.from_user.id)
        if valor:
            bot.send_message(message.chat.id, f"✅ *GIFT RESGATADO!*\n\nForam creditados *R$ {valor:.2f}* na sua conta.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Código inválido ou já usado.")

    def home(chat: int, uid: int):
        saldo = db.obter_saldo(uid)
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"💳 GG • R$ 4,00 • {gg} un", callback_data="menu_gg"),
            types.InlineKeyboardButton(f"📺 Streaming • R$ 12,00 • {stream} un", callback_data="buy_streaming"),
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
            LOG.error(f"Erro: {exc}")
            time.sleep(5)
