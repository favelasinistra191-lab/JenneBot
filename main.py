"""Bot Telegram de Loja Digital - Versão Final com Sistema Anti-Sono (Keep-Alive)."""

from __future__ import annotations
import logging
import os
import time
import threading
import random
import string
import requests
from decimal import Decimal
from typing import Any
import telebot
from telebot import apihelper, types
import database as db
from security_utils import CPFProtector
from flask import Flask

# --- Configurações Iniciais ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PIX_ESTATICO = "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607181421TUV2VAB162WC66304B341"
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") # URL do seu bot no Render

PRECOS = {"gg": 4.0, "streaming": 12.0, "esim": 20.0}

db.criar_tabelas()

if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}

bot = telebot.TeleBot(TOKEN) if TOKEN else None
state: dict[int, dict[str, Any]] = {}

# --- Servidor Web Keep-Alive ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot Online e Acordado!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Função para o bot se auto-pingar e não dormir
def keep_alive_ping():
    if not RENDER_URL:
        LOG.warning("RENDER_EXTERNAL_URL não configurada. Auto-ping desativado.")
        return
    while True:
        try:
            requests.get(RENDER_URL)
            LOG.info("Auto-ping realizado com sucesso.")
        except Exception as e:
            LOG.error(f"Erro no auto-ping: {e}")
        time.sleep(600) # Ping a cada 10 minutos

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

# --- Handlers Administrativos ---

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
            "• `/add streaming` - Lista (Email|Senha|Tela|Senha)\n"
            "• `/add esim` - Lista (Conteúdo)\n\n"
            "📊 *Gestão:*\n"
            "• `/estoque` - Ver quantidades\n"
            "• `/relatorio` - Vendas e Faturamento\n"
            "• `/filas` - Status de pareamento GG\n\n"
            "🎁 *Gifts:* `/gerar_gift VALOR`"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["estoque"])
    def view_stock(message: Any):
        if not is_admin(message): return
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        bot.reply_to(message, f"📦 *ESTOQUE ATUAL*\n\n💳 GG: `{gg}`\n📺 Streaming: `{stream}`\n📶 eSIM: `{esim}`", parse_mode="Markdown")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any):
        if not is_admin(message): return
        total, revenue, cats = db.obter_dados_relatorio()
        cat_str = "\n".join([f"• {k.title()}: {v}" for k, v in cats.items()])
        bot.reply_to(message, f"📈 *RELATÓRIO DE VENDAS*\n\nTotal: {total}\nFaturamento: R$ {revenue:.2f}\n\n*Categorias:*\n{cat_str}", parse_mode="Markdown")

    @bot.message_handler(commands=["filas"])
    def queues(message: Any):
        if not is_admin(message): return
        gg, data, ready = db.obter_status_filas()
        bot.reply_to(message, f"📦 *STATUS DAS FILAS*\n\nGGs aguardando dados: {gg}\nDados aguardando GGs: {data}\n✅ Prontos para venda: {ready}", parse_mode="Markdown")

    @bot.message_handler(commands=["add"])
    def add_cmd(message: Any):
        if not is_admin(message): return
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
        elif option == "esim":
            msg = bot.reply_to(message, "📶 *ADD ESIM EM MASSA*\nEnvie a lista de conteúdos (um por linha):")
            bot.register_next_step_handler(msg, esim_mass_process)

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
        bot.reply_to(message, f"✅ Sucesso: {s}\n❌ Erros: {e}\n📦 Estoque GG: {db.contar_estoque_categoria('gg')}")

    def data_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e, p = 0, 0, protect()
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

    def esim_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            try:
                db.adicionar_estoque("esim", line.strip())
                s += 1
            except: e += 1
        bot.reply_to(message, f"✅ eSIMs adicionados: {s}\n❌ Erros: {e}")

    @bot.message_handler(commands=["gerar_gift"])
    def create_gift(message: Any):
        if not is_admin(message): return
        try:
            val = float(message.text.split()[1])
            code = "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
            db.criar_gift(code, val, message.from_user.id)
            bot.reply_to(message, f"🎁 *GIFT GERADO*\n\nCódigo: `{code}`\nValor: R$ {val:.2f}", parse_mode="Markdown")
        except: bot.reply_to(message, "Uso: `/gerar_gift 50`")

    # --- Handlers de Usuário ---

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
        elif data == "saldo":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🏦 PIX Manual", callback_data="pix_manual"))
            bot.send_message(chat, "Escolha o método:", reply_markup=markup)
        elif data == "pix_manual":
            bot.send_message(chat, f"🏦 *PIX MANUAL*\n\nChave:\n`{PIX_ESTATICO}`", parse_mode="Markdown")
        elif data == "resgatar_btn":
            msg = bot.send_message(chat, "📥 Digite o código do Gift Card:")
            bot.register_next_step_handler(msg, process_gift_step)
        elif data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ Sem estoque.")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, bk, c in groups:
                markup.add(types.InlineKeyboardButton(f"BIN {b} • {bk} • {c} un", callback_data=f"buy|gg|{b}|{bk}"))
            bot.send_message(chat, "Escolha a BIN:", reply_markup=markup)
        elif data == "menu_streaming":
            count = db.contar_estoque_categoria("streaming")
            if count == 0:
                bot.send_message(chat, "❌ Sem estoque.")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 12,00)", callback_data="buy|streaming"))
            bot.send_message(chat, f"📺 *STREAMING*\nEstoque: `{count}`\nValor: `R$ 12,00`", reply_markup=markup, parse_mode="Markdown")
        elif data == "menu_esim":
            count = db.contar_estoque_categoria("esim")
            if count == 0:
                bot.send_message(chat, "❌ Sem estoque.")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 20,00)", callback_data="buy|esim"))
            bot.send_message(chat, f"📶 *eSIM*\nEstoque: `{count}`\nValor: `R$ 20,00`", reply_markup=markup, parse_mode="Markdown")
        elif data.startswith("buy|"):
            process_purchase(call)
        elif data == "conta":
            saldo = db.obter_saldo(uid)
            bot.send_message(chat, f"👤 *MINHA CONTA*\n\nID: `{uid}`\nSaldo: `R$ {saldo:.2f}`", parse_mode="Markdown")

    def process_purchase(call: Any):
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        saldo = db.obter_saldo(uid)
        parts = data.split("|")
        cat = parts[1]
        price = PRECOS[cat]
        bn, bk = (parts[2], parts[3]) if cat == "gg" else (None, None)

        if saldo < price:
            bot.send_message(chat, f"❌ Saldo insuficiente! (R$ {saldo:.2f})")
            return

        inv_id = f"BUY-{int(time.time())}-{uid}"
        status, sid, conteudo = db.concluir_compra_fatura(inv_id, uid, cat, price, bn, bk)

        if status == "ok":
            bot.send_message(chat, "✅ *COMPRA REALIZADA!*", parse_mode="Markdown")
            if cat == "gg":
                d = db.obter_dados_gg_para_entrega(sid, uid)
                cpf = protect().decrypt(d[3])
                msg = f"💳 *GG:* `{conteudo}`\n🏦 *Banco:* `{d[1]}`\n👤 *Nome:* `{d[2]}`\n🆔 *CPF:* `{cpf}`"
            elif cat == "streaming":
                s = conteudo.split("|")
                msg = f"📺 *STREAMING*\n📧 Email: `{s[0]}`\n🔑 Senha: `{s[1]}`\n🖥️ Tela: `{s[2]}`\n🔒 PIN: `{s[3]}`"
            else:
                msg = f"📦 *CONTEÚDO:* `{conteudo}`"
            bot.send_message(chat, msg, parse_mode="Markdown")
        else:
            bot.send_message(chat, "❌ Erro: Sem estoque ou falha no sistema.")

    def process_gift_step(message: Any):
        valor = db.resgatar_gift(message.text.strip(), message.from_user.id)
        if valor:
            bot.send_message(message.chat.id, f"✅ *GIFT RESGATADO!*\n\nCreditados: *R$ {valor:.2f}*", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Código inválido ou já usado.")

    def home(chat: int, uid: int):
        saldo = db.obter_saldo(uid)
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"💳 GG • R$ 4,00 • {gg} un", callback_data="menu_gg"),
            types.InlineKeyboardButton(f"📺 Streaming • R$ 12,00 • {stream} un", callback_data="menu_streaming"),
            types.InlineKeyboardButton(f"📶 eSIM • R$ 20,00 • {esim} un", callback_data="menu_esim"),
            types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
            types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
            types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
        )
        bot.send_message(chat, f"🏪 *LOJA DIGITAL*\n\n💰 Saldo: `R$ {saldo:.2f}`", reply_markup=markup, parse_mode="Markdown")

    @bot.message_handler(func=lambda m: m.text and m.text.startswith("/"))
    def unknown(message: Any):
        bot.reply_to(message, "❌ Código não encontrado, código não existente.")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=20, skip_pending=True)
        except Exception as exc:
            LOG.error(f"Erro: {exc}")
            time.sleep(5)
