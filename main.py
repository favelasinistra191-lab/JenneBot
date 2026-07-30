"""Bot Telegram de Loja Digital - Versão Ultra-Compatível para Render."""

import logging
import os
import time
import threading
import random
import re
import string
import requests
from datetime import datetime
from decimal import Decimal
from typing import Any
import telebot
from telebot import apihelper, types
import database as db
from security_utils import CPFProtector
from flask import Flask

# --- Configurações Iniciais ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

# TOKEN E CONFIGURAÇÕES
TOKEN = os.getenv("TELEGRAM_TOKEN", "8645582951:AAGKtbHS3qF8VOFC4onst-8sf4ussasX5_I")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PIX_ESTATICO = os.getenv("PIX_ESTATICO", "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607181421TUV2VAB162WC66304B341")
PRECOS = {"gg": 4.0, "streaming": 12.0, "esim": 20.0}
MIN_DEPOSITO = 10.0

# Inicialização do Banco
db.criar_tabelas()

# Inicialização do Bot
bot = telebot.TeleBot(TOKEN)
state = {}

# --- Servidor Web (Keep-Alive para o Render) ---
app = Flask(__name__)

@app.route('/')
def health(): 
    return "JenneStore Online!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    LOG.info(f"Servidor de Keep-Alive iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)

# --- Funções Auxiliares ---
def protect():
    key = os.getenv("CPF_ENCRYPTION_KEY", "jennebot_secret_key_123").strip()
    return CPFProtector.from_string(key)

def register(obj):
    user = obj.from_user
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or "Cliente"
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

def is_admin(message):
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

# --- Handlers de Usuário ---
@bot.message_handler(commands=["start"])
def start(message):
    LOG.info(f"Comando /start recebido de {message.from_user.id}")
    register(message)
    home(message.chat.id, message.from_user.id)

def home(chat, uid):
    saldo = db.obter_saldo(uid)
    gg = db.contar_estoque_categoria("gg")
    st = db.contar_estoque_categoria("streaming")
    es = db.contar_estoque_categoria("esim")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"💳 GG | R$ 4,00 | {gg} un", callback_data="menu_gg"),
        types.InlineKeyboardButton(f"📺 Streaming | R$ 12,00 | {st} un", callback_data="menu_streaming"),
        types.InlineKeyboardButton(f"📶 eSIM | R$ 20,00 | {es} un", callback_data="menu_esim"),
        types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
        types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
    )
    
    msg_home = (
        "🏪 *BEM-VINDO À JENNE STORE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Escolha uma das opções abaixo para navegar no nosso catálogo.\n\n"
        f"💰 Seu Saldo: `R$ {saldo:.2f}`"
    )
    bot.send_message(chat, msg_home, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    register(call)
    bot.answer_callback_query(call.id)
    chat, uid, data = call.message.chat.id, call.from_user.id, call.data
    
    if data == "inicio": home(chat, uid)
    elif data == "conta":
        saldo = db.obter_saldo(uid)
        bot.send_message(chat, f"👤 *MINHA CONTA*\n━━━━━━━━━━━━━━━━━━━━\n🆔 Seu ID: `{uid}`\n💰 Saldo Atual: `R$ {saldo:.2f}`\n━━━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")
    elif data == "saldo":
        bot.send_message(chat, f"💰 *ADICIONAR SALDO*\n━━━━━━━━━━━━━━━━━━━━\nEnvie o valor via PIX Copia e Cola:\n\n`{PIX_ESTATICO}`\n\nApós o pagamento, envie o comprovante para o suporte.", parse_mode="Markdown")
    elif data == "resgatar_btn":
        msg = bot.send_message(chat, "🎁 Digite o código do seu Gift Card:")
        bot.register_next_step_handler(msg, process_gift)
    elif data == "menu_gg":
        groups = db.listar_estoque_gg()
        if not groups:
            bot.send_message(chat, "❌ Sem estoque de GG no momento.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for b, banco, c in groups:
            markup.add(types.InlineKeyboardButton(f"{b} | {c} un", callback_data=f"buy|gg|{b}"))
        markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, "💳 *ESCOLHA SUA BIN*", reply_markup=markup, parse_mode="Markdown")
    elif data == "menu_streaming":
        count = db.contar_estoque_categoria("streaming")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Comprar R$ 12,00", callback_data="buy|streaming"), types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, f"📺 *STREAMING*\n📦 Estoque: {count} un", reply_markup=markup, parse_mode="Markdown")
    elif data == "menu_esim":
        count = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Comprar R$ 20,00", callback_data="buy|esim"), types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, f"📶 *eSIM*\n📦 Estoque: {count} un", reply_markup=markup, parse_mode="Markdown")
    elif data.startswith("buy|"):
        process_purchase(call)

def process_purchase(call):
    chat, uid, data = call.message.chat.id, call.from_user.id, call.data
    parts = data.split("|")
    cat = parts[1]
    price = PRECOS[cat]
    if db.obter_saldo(uid) < price:
        bot.send_message(chat, "❌ Saldo insuficiente.")
        return
    
    bn = parts[2] if len(parts) > 2 else None
    res, sid, cont = db.concluir_compra_fatura(f"BUY-{int(time.time())}", uid, cat, price, bn)
    if res == "ok":
        if cat == "gg":
            d = db.obter_dados_gg_para_entrega(sid, uid)
            bot.send_message(chat, f"✅ *COMPRA REALIZADA!*\n\n💳 Cartão: `{cont}`\n👤 Titular: {d[2]}\n🆔 CPF: {protect().decrypt(d[3])}", parse_mode="Markdown")
        else:
            bot.send_message(chat, f"✅ *COMPRA REALIZADA!*\n\n📦 Conteúdo: `{cont}`", parse_mode="Markdown")
    else:
        bot.send_message(chat, "❌ Erro no estoque ou produto indisponível.")

def process_gift(message):
    val = db.resgatar_gift(message.text.strip(), message.from_user.id)
    if val: bot.send_message(message.chat.id, f"✅ Gift resgatado: R$ {val:.2f}")
    else: bot.send_message(message.chat.id, "❌ Código inválido.")

# --- Handlers Admin ---
@bot.message_handler(commands=["menu"])
def admin_menu(message):
    if not is_admin(message): return
    bot.reply_to(message, "💎 *PAINEL ADMIN*\n\nUse `/add gg`, `/add dados`, `/relatorio`, `/estoque`.", parse_mode="Markdown")

@bot.message_handler(commands=["relatorio"])
def admin_relatorio(message):
    if not is_admin(message): return
    total_v, fat, cats = db.obter_dados_relatorio()
    bot.reply_to(message, f"📊 Vendas: {total_v}\n💰 Faturamento: R$ {fat:.2f}")

@bot.message_handler(commands=["add"])
def admin_add(message):
    if not is_admin(message): return
    parts = message.text.split()
    if len(parts) < 2: return
    opt = parts[1].lower()
    msg = bot.reply_to(message, f"Envie a lista de {opt}:")
    if opt == "gg": bot.register_next_step_handler(msg, gg_mass_process)
    elif opt == "dados": bot.register_next_step_handler(msg, data_mass_process)
    elif opt == "streaming": bot.register_next_step_handler(msg, stream_mass_process)
    elif opt == "esim": bot.register_next_step_handler(msg, esim_mass_process)

def gg_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        if "|" in line:
            try:
                card = re.sub(r"\D", "", line.split("|")[0])
                db.adicionar_gg_pendente(card[:6], "Auto", line.strip(), message.from_user.id)
                s += 1
            except: pass
    bot.reply_to(message, f"✅ {s} GGs adicionadas.")

def data_mass_process(message):
    lines = message.text.strip().split("\n")
    s, p = 0, protect()
    for line in lines:
        parts = line.split("|")
        if len(parts) == 2:
            db.adicionar_dados_pendentes(parts[0].strip(), p.encrypt(parts[1].strip()), p.fingerprint(parts[1].strip()), message.from_user.id)
            s += 1
    bot.reply_to(message, f"✅ {s} Dados adicionados.")

def stream_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        if "|" in line:
            db.adicionar_estoque("streaming", line.strip())
            s += 1
    bot.reply_to(message, f"✅ {s} Streamings adicionados.")

def esim_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        db.adicionar_estoque("esim", line.strip())
        s += 1
    bot.reply_to(message, f"✅ {s} eSIMs adicionados.")

# --- Inicialização ---
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    
    LOG.info("Aguardando 15 segundos...")
    time.sleep(15)
    
    LOG.info("Iniciando bot...")
    while True:
        try:
            # REMOVIDO drop_pending_updates para compatibilidade total
            bot.remove_webhook()
            time.sleep(1)
            
            LOG.info("Bot online!")
            # USANDO polling básico para evitar erros de argumento
            bot.polling(none_stop=True)
            
        except Exception as e:
            LOG.error(f"Erro no loop: {e}")
            time.sleep(10)

# --- Servidor Web (Keep-Alive para o Render) ---
app = Flask(__name__)

@app.route('/')
def health(): 
    return "JenneStore Online!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    LOG.info(f"Servidor de Keep-Alive iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)

# --- Funções Auxiliares ---
def protect():
    key = os.getenv("CPF_ENCRYPTION_KEY", "jennebot_secret_key_123").strip()
    return CPFProtector.from_string(key)

def register(obj):
    user = obj.from_user
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or "Cliente"
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

def is_admin(message):
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

# --- Handlers de Usuário ---
@bot.message_handler(commands=["start"])
def start(message):
    LOG.info(f"Comando /start recebido de {message.from_user.id}")
    register(message)
    home(message.chat.id, message.from_user.id)

def home(chat, uid):
    saldo = db.obter_saldo(uid)
    gg = db.contar_estoque_categoria("gg")
    st = db.contar_estoque_categoria("streaming")
    es = db.contar_estoque_categoria("esim")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"💳 GG | R$ 4,00 | {gg} un", callback_data="menu_gg"),
        types.InlineKeyboardButton(f"📺 Streaming | R$ 12,00 | {st} un", callback_data="menu_streaming"),
        types.InlineKeyboardButton(f"📶 eSIM | R$ 20,00 | {es} un", callback_data="menu_esim"),
        types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
        types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
    )
    
    msg_home = (
        "🏪 *BEM-VINDO À JENNE STORE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Escolha uma das opções abaixo para navegar no nosso catálogo.\n\n"
        f"💰 Seu Saldo: `R$ {saldo:.2f}`"
    )
    bot.send_message(chat, msg_home, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    register(call)
    bot.answer_callback_query(call.id)
    chat, uid, data = call.message.chat.id, call.from_user.id, call.data
    
    if data == "inicio": home(chat, uid)
    elif data == "conta":
        saldo = db.obter_saldo(uid)
        bot.send_message(chat, f"👤 *MINHA CONTA*\n━━━━━━━━━━━━━━━━━━━━\n🆔 Seu ID: `{uid}`\n💰 Saldo Atual: `R$ {saldo:.2f}`\n━━━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")
    elif data == "saldo":
        bot.send_message(chat, f"💰 *ADICIONAR SALDO*\n━━━━━━━━━━━━━━━━━━━━\nEnvie o valor via PIX Copia e Cola:\n\n`{PIX_ESTATICO}`\n\nApós o pagamento, envie o comprovante para o suporte.", parse_mode="Markdown")
    elif data == "resgatar_btn":
        msg = bot.send_message(chat, "🎁 Digite o código do seu Gift Card:")
        bot.register_next_step_handler(msg, process_gift)
    elif data == "menu_gg":
        groups = db.listar_estoque_gg()
        if not groups:
            bot.send_message(chat, "❌ Sem estoque de GG no momento.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for b, banco, c in groups:
            markup.add(types.InlineKeyboardButton(f"{b} | {c} un", callback_data=f"buy|gg|{b}"))
        markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, "💳 *ESCOLHA SUA BIN*", reply_markup=markup, parse_mode="Markdown")
    elif data == "menu_streaming":
        count = db.contar_estoque_categoria("streaming")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Comprar R$ 12,00", callback_data="buy|streaming"), types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, f"📺 *STREAMING*\n📦 Estoque: {count} un", reply_markup=markup, parse_mode="Markdown")
    elif data == "menu_esim":
        count = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Comprar R$ 20,00", callback_data="buy|esim"), types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, f"📶 *eSIM*\n📦 Estoque: {count} un", reply_markup=markup, parse_mode="Markdown")
    elif data.startswith("buy|"):
        process_purchase(call)

def process_purchase(call):
    chat, uid, data = call.message.chat.id, call.from_user.id, call.data
    parts = data.split("|")
    cat = parts[1]
    price = PRECOS[cat]
    if db.obter_saldo(uid) < price:
        bot.send_message(chat, "❌ Saldo insuficiente.")
        return
    
    bn = parts[2] if len(parts) > 2 else None
    res, sid, cont = db.concluir_compra_fatura(f"BUY-{int(time.time())}", uid, cat, price, bn)
    if res == "ok":
        if cat == "gg":
            d = db.obter_dados_gg_para_entrega(sid, uid)
            bot.send_message(chat, f"✅ *COMPRA REALIZADA!*\n\n💳 Cartão: `{cont}`\n👤 Titular: {d[2]}\n🆔 CPF: {protect().decrypt(d[3])}", parse_mode="Markdown")
        else:
            bot.send_message(chat, f"✅ *COMPRA REALIZADA!*\n\n📦 Conteúdo: `{cont}`", parse_mode="Markdown")
    else:
        bot.send_message(chat, "❌ Erro no estoque ou produto indisponível.")

def process_gift(message):
    val = db.resgatar_gift(message.text.strip(), message.from_user.id)
    if val: bot.send_message(message.chat.id, f"✅ Gift resgatado: R$ {val:.2f}")
    else: bot.send_message(message.chat.id, "❌ Código inválido.")

# --- Handlers Admin ---
@bot.message_handler(commands=["menu"])
def admin_menu(message):
    if not is_admin(message): return
    bot.reply_to(message, "💎 *PAINEL ADMIN*\n\nUse `/add gg`, `/add dados`, `/relatorio`, `/estoque`.", parse_mode="Markdown")

@bot.message_handler(commands=["relatorio"])
def admin_relatorio(message):
    if not is_admin(message): return
    total_v, fat, cats = db.obter_dados_relatorio()
    bot.reply_to(message, f"📊 Vendas: {total_v}\n💰 Faturamento: R$ {fat:.2f}")

@bot.message_handler(commands=["add"])
def admin_add(message):
    if not is_admin(message): return
    parts = message.text.split()
    if len(parts) < 2: return
    opt = parts[1].lower()
    msg = bot.reply_to(message, f"Envie a lista de {opt}:")
    if opt == "gg": bot.register_next_step_handler(msg, gg_mass_process)
    elif opt == "dados": bot.register_next_step_handler(msg, data_mass_process)
    elif opt == "streaming": bot.register_next_step_handler(msg, stream_mass_process)
    elif opt == "esim": bot.register_next_step_handler(msg, esim_mass_process)

def gg_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        if "|" in line:
            try:
                card = re.sub(r"\D", "", line.split("|")[0])
                db.adicionar_gg_pendente(card[:6], "Auto", line.strip(), message.from_user.id)
                s += 1
            except: pass
    bot.reply_to(message, f"✅ {s} GGs adicionadas.")

def data_mass_process(message):
    lines = message.text.strip().split("\n")
    s, p = 0, protect()
    for line in lines:
        parts = line.split("|")
        if len(parts) == 2:
            db.adicionar_dados_pendentes(parts[0].strip(), p.encrypt(parts[1].strip()), p.fingerprint(parts[1].strip()), message.from_user.id)
            s += 1
    bot.reply_to(message, f"✅ {s} Dados adicionados.")

def stream_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        if "|" in line:
            db.adicionar_estoque("streaming", line.strip())
            s += 1
    bot.reply_to(message, f"✅ {s} Streamings adicionados.")

def esim_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        db.adicionar_estoque("esim", line.strip())
        s += 1
    bot.reply_to(message, f"✅ {s} eSIMs adicionados.")

# --- Inicialização ---
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    
    LOG.info("Aguardando 15 segundos...")
    time.sleep(15)
    
    LOG.info("Iniciando bot...")
    while True:
        try:
            # REMOVIDO drop_pending_updates para compatibilidade total
            bot.remove_webhook()
            time.sleep(1)
            
            LOG.info("Bot online!")
            # USANDO polling básico para evitar erros de argumento
            bot.polling(none_stop=True)
            
        except Exception as e:
            LOG.error(f"Erro no loop: {e}")
            time.sleep(10)

# --- Servidor Web (Keep-Alive para o Render) ---
app = Flask(__name__)

@app.route('/')
def health(): 
    return "JenneStore Online e Atenta!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    LOG.info(f"Servidor de Keep-Alive iniciado na porta {port}")
    app.run(host='0.0.0.0', port=port)

# --- Funções Auxiliares (Preservadas) ---
def protect():
    key = os.getenv("CPF_ENCRYPTION_KEY", "jennebot_secret_key_123").strip()
    return CPFProtector.from_string(key)

def register(obj):
    user = obj.from_user
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or "Cliente"
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

def is_admin(message):
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

# --- Handlers de Usuário (Interface Original) ---
@bot.message_handler(commands=["start"])
def start(message):
    LOG.info(f"Comando /start recebido de {message.from_user.id}")
    register(message)
    home(message.chat.id, message.from_user.id)

def home(chat, uid):
    saldo = db.obter_saldo(uid)
    gg = db.contar_estoque_categoria("gg")
    st = db.contar_estoque_categoria("streaming")
    es = db.contar_estoque_categoria("esim")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"💳 GG | R$ 4,00 | {gg} un", callback_data="menu_gg"),
        types.InlineKeyboardButton(f"📺 Streaming | R$ 12,00 | {st} un", callback_data="menu_streaming"),
        types.InlineKeyboardButton(f"📶 eSIM | R$ 20,00 | {es} un", callback_data="menu_esim"),
        types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
        types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
    )
    
    msg_home = (
        "🏪 *BEM-VINDO À JENNE STORE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Escolha uma das opções abaixo para navegar no nosso catálogo.\n\n"
        f"💰 Seu Saldo: `R$ {saldo:.2f}`"
    )
    bot.send_message(chat, msg_home, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    register(call)
    bot.answer_callback_query(call.id)
    chat, uid, data = call.message.chat.id, call.from_user.id, call.data
    
    if data == "inicio": home(chat, uid)
    elif data == "conta":
        saldo = db.obter_saldo(uid)
        bot.send_message(chat, f"👤 *MINHA CONTA*\n━━━━━━━━━━━━━━━━━━━━\n🆔 Seu ID: `{uid}`\n💰 Saldo Atual: `R$ {saldo:.2f}`\n━━━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")
    elif data == "saldo":
        bot.send_message(chat, f"💰 *ADICIONAR SALDO*\n━━━━━━━━━━━━━━━━━━━━\nEnvie o valor via PIX Copia e Cola:\n\n`{PIX_ESTATICO}`\n\nApós o pagamento, envie o comprovante para o suporte.", parse_mode="Markdown")
    elif data == "resgatar_btn":
        msg = bot.send_message(chat, "🎁 Digite o código do seu Gift Card:")
        bot.register_next_step_handler(msg, process_gift)
    elif data == "menu_gg":
        groups = db.listar_estoque_gg()
        if not groups:
            bot.send_message(chat, "❌ Sem estoque de GG no momento.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for b, banco, c in groups:
            markup.add(types.InlineKeyboardButton(f"{b} | {c} un", callback_data=f"buy|gg|{b}"))
        markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, "💳 *ESCOLHA SUA BIN*", reply_markup=markup, parse_mode="Markdown")
    elif data == "menu_streaming":
        count = db.contar_estoque_categoria("streaming")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Comprar R$ 12,00", callback_data="buy|streaming"), types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, f"📺 *STREAMING*\n📦 Estoque: {count} un", reply_markup=markup, parse_mode="Markdown")
    elif data == "menu_esim":
        count = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Comprar R$ 20,00", callback_data="buy|esim"), types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
        bot.send_message(chat, f"📶 *eSIM*\n📦 Estoque: {count} un", reply_markup=markup, parse_mode="Markdown")
    elif data.startswith("buy|"):
        process_purchase(call)

def process_purchase(call):
    chat, uid, data = call.message.chat.id, call.from_user.id, call.data
    parts = data.split("|")
    cat = parts[1]
    price = PRECOS[cat]
    if db.obter_saldo(uid) < price:
        bot.send_message(chat, "❌ Saldo insuficiente.")
        return
    
    bn = parts[2] if len(parts) > 2 else None
    res, sid, cont = db.concluir_compra_fatura(f"BUY-{int(time.time())}", uid, cat, price, bn)
    if res == "ok":
        if cat == "gg":
            d = db.obter_dados_gg_para_entrega(sid, uid)
            bot.send_message(chat, f"✅ *COMPRA REALIZADA!*\n\n💳 Cartão: `{cont}`\n👤 Titular: {d[2]}\n🆔 CPF: {protect().decrypt(d[3])}", parse_mode="Markdown")
        else:
            bot.send_message(chat, f"✅ *COMPRA REALIZADA!*\n\n📦 Conteúdo: `{cont}`", parse_mode="Markdown")
    else:
        bot.send_message(chat, "❌ Erro no estoque ou produto indisponível.")

def process_gift(message):
    val = db.resgatar_gift(message.text.strip(), message.from_user.id)
    if val: bot.send_message(message.chat.id, f"✅ Gift resgatado: R$ {val:.2f}")
    else: bot.send_message(message.chat.id, "❌ Código inválido.")

# --- Handlers Admin (Preservados) ---
@bot.message_handler(commands=["menu"])
def admin_menu(message):
    if not is_admin(message): return
    bot.reply_to(message, "💎 *PAINEL ADMIN*\n\nUse `/add gg`, `/add dados`, `/relatorio`, `/estoque`.", parse_mode="Markdown")

@bot.message_handler(commands=["relatorio"])
def admin_relatorio(message):
    if not is_admin(message): return
    total_v, fat, cats = db.obter_dados_relatorio()
    bot.reply_to(message, f"📊 Vendas: {total_v}\n💰 Faturamento: R$ {fat:.2f}")

@bot.message_handler(commands=["add"])
def admin_add(message):
    if not is_admin(message): return
    parts = message.text.split()
    if len(parts) < 2: return
    opt = parts[1].lower()
    msg = bot.reply_to(message, f"Envie a lista de {opt}:")
    if opt == "gg": bot.register_next_step_handler(msg, gg_mass_process)
    elif opt == "dados": bot.register_next_step_handler(msg, data_mass_process)
    elif opt == "streaming": bot.register_next_step_handler(msg, stream_mass_process)
    elif opt == "esim": bot.register_next_step_handler(msg, esim_mass_process)

def gg_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        if "|" in line:
            try:
                card = re.sub(r"\D", "", line.split("|")[0])
                db.adicionar_gg_pendente(card[:6], "Auto", line.strip(), message.from_user.id)
                s += 1
            except: pass
    bot.reply_to(message, f"✅ {s} GGs adicionadas.")

def data_mass_process(message):
    lines = message.text.strip().split("\n")
    s, p = 0, protect()
    for line in lines:
        parts = line.split("|")
        if len(parts) == 2:
            db.adicionar_dados_pendentes(parts[0].strip(), p.encrypt(parts[1].strip()), p.fingerprint(parts[1].strip()), message.from_user.id)
            s += 1
    bot.reply_to(message, f"✅ {s} Dados adicionados.")

def stream_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        if "|" in line:
            db.adicionar_estoque("streaming", line.strip())
            s += 1
    bot.reply_to(message, f"✅ {s} Streamings adicionados.")

def esim_mass_process(message):
    lines = message.text.strip().split("\n")
    s = 0
    for line in lines:
        db.adicionar_estoque("esim", line.strip())
        s += 1
    bot.reply_to(message, f"✅ {s} eSIMs adicionados.")

# --- Inicialização com Delay Anti-Conflito ---
if __name__ == "__main__":
    # Inicia o servidor Flask imediatamente para o Render não dar timeout
    threading.Thread(target=run_flask, daemon=True).start()
    
    LOG.info("Aguardando 15 segundos para evitar conflito com instâncias antigas...")
    time.sleep(15)
    
    LOG.info("Iniciando bot...")
    while True:
        try:
            # Forma simples e compatível de iniciar o bot
            bot.remove_webhook()
            time.sleep(1)
            
            LOG.info("Bot online e aguardando comandos!")
            bot.polling(none_stop=True, interval=0, timeout=20)
            
        except Exception as e:
            if "Conflict" in str(e):
                LOG.warning("Conflito detectado. Aguardando 20 segundos para tentar novamente...")
                time.sleep(20)
            else:
                LOG.error(f"Erro no loop: {e}")
                time.sleep(10)
