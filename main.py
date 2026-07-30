"""
JenneStoreBot - Bot de Vendas Moderno para Telegram
Focado em performance, segurança e facilidade de uso no Render.
"""
import logging
import os
import time
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot import types

import database as db
import config
from security_utils import Security, format_cpf


# --- Configuração de Logs ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger("JenneStoreBot")


# --- Inicialização ---
bot = telebot.TeleBot(config.TOKEN)
# db.criar_tabelas()


# --- Servidor Web para Health Check e Keep-Alive ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return {"status": "online", "timestamp": datetime.now().isoformat()}, 200


@app.route('/ping')
def ping():
    return "ok", 200


def run_web_server():
    app.run(host='0.0.0.0', port=config.PORT)


# --- Auxiliares ---
def register_user(user):
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Usuário"
    db.garantir_usuario(user.id, name, user.username)


def is_admin(user_id):
    return user_id == config.ADMIN_ID


# --- Menus ---
def main_menu(user_id):
    saldo = db.obter_saldo(user_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        types.InlineKeyboardButton("💳 GGs", callback_data="cat_gg"),
        types.InlineKeyboardButton("📺 Streaming", callback_data="cat_streaming"),
        types.InlineKeyboardButton("📶 eSIM", callback_data="cat_esim"),
        types.InlineKeyboardButton("👤 Minha Conta", callback_data="menu_conta"),
        types.InlineKeyboardButton("💰 Adicionar Saldo", callback_data="menu_saldo"),
        types.InlineKeyboardButton("🎁 Gift Card", callback_data="menu_gift"),
        types.InlineKeyboardButton("🛠 Suporte", url="https://t.me/seu_suporte")
    ]
    markup.add(*btns)
    text = (
        "👋 *Bem-vindo à Jenne Store!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Seu Saldo:* `R$ {saldo:.2f}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Escolha uma categoria abaixo:"
    )
    return text, markup


# --- Handlers de Comandos ---
@bot.message_handler(commands=['start'])
def cmd_start(message):
    register_user(message.from_user)
    text, markup = main_menu(message.from_user.id)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")


@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if not is_admin(message.from_user.id): return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📊 Relatório", callback_data="admin_relatorio"))
    markup.add(types.InlineKeyboardButton("📥 Add Estoque (Stream/eSIM)", callback_data="admin_add_estoque"))
    markup.add(types.InlineKeyboardButton("💳 Add GG (Cartão)", callback_data="admin_add_gg"))
    markup.add(types.InlineKeyboardButton("👤 Add Dados (Titular)", callback_data="admin_add_dados"))
    markup.add(types.InlineKeyboardButton("🎁 Gerar Gift Card", callback_data="admin_gen_gift"))
    bot.send_message(message.chat.id, "🛠 *PAINEL ADMINISTRATIVO*", reply_markup=markup, parse_mode="Markdown")


# --- Handlers de Callback ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    register_user(call.from_user)

    if call.data == "main_menu":
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "menu_conta":
        saldo = db.obter_saldo(user_id)
        text = f"👤 *SUA CONTA*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* `{user_id}`\n💰 *Saldo:* `R$ {saldo:.2f}`\n━━━━━━━━━━━━━━━━━━━━"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "menu_saldo":
        text = f"💰 *ADICIONAR SALDO*\n━━━━━━━━━━━━━━━━━━━━\n🔑 *Chave PIX:* `{config.PIX_ESTATICO}`\n\n⚠️ Envie o comprovante para o suporte."
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "menu_gift":
        msg = bot.send_message(chat_id, "🎁 Digite o código do seu Gift Card:")
        bot.register_next_step_handler(msg, process_gift_redemption)

    elif call.data == "cat_gg":
        groups = db.listar_estoque_gg()
        if not groups:
            bot.answer_callback_query(call.id, "❌ Sem estoque de GG.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for bin_v, bank, count in groups:
            markup.add(types.InlineKeyboardButton(f"💳 {bin_v} | {bank} | {count} un", callback_data=f"buy_gg_{bin_v}"))
        markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="main_menu"))
        bot.edit_message_text("💳 *ESCOLHA UMA BIN*", chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("buy_gg_"):
        bin_v = call.data.replace("buy_gg_", "")
        price = config.PRECOS["gg"]
        res, item_id, _ = db.realizar_venda(user_id, "gg", price, bin_v)
        if res == "ok":
            d = db.obter_dados_venda_gg(item_id)
            info_cartao = d[0]
            titular = d[3] or "Não informado"
            cpf = format_cpf(Security.decrypt(d[4])) if d[4] else "Não informado"
            entrega = (
                "✅ *COMPRA REALIZADA!*\n\n"
                f"💳 *Cartão:* `{info_cartao}`\n"
                f"🏦 *Banco:* `{d[2]}`\n"
                f"👤 *Titular:* `{titular}`\n"
                f"🆔 *CPF:* `{cpf}`\n\n"
                "💰 Valor debitado: R$ {:.2f}".format(price)
            )
            bot.send_message(chat_id, entrega, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, f"❌ {res.replace('_', ' ')}", show_alert=True)

    elif call.data.startswith("cat_") and ("streaming" in call.data or "esim" in call.data):
        cat = "streaming" if "streaming" in call.data else "esim"
        count = db.contar_estoque_categoria(cat)
        price = config.PRECOS[cat]
        text = f"📦 *{cat.upper()}*\n━━━━━━━━━━━━━━━━━━━━\n💰 *Preço:* `R$ {price:.2f}`\n📦 *Disponível:* `{count}`\n━━━━━━━━━━━━━━━━━━━━"
        markup = types.InlineKeyboardMarkup()
        if count > 0: markup.add(types.InlineKeyboardButton("✅ Comprar", callback_data=f"buy_simple_{cat}"))
        markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("buy_simple_"):
        cat = call.data.replace("buy_simple_", "")
        price = config.PRECOS[cat]
        res, _, content = db.realizar_venda(user_id, cat, price)
        if res == "ok":
            bot.send_message(chat_id, f"✅ *COMPRA REALIZADA!*\n\n📦 *Conteúdo:* `{content}`", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, f"❌ {res.replace('_', ' ')}", show_alert=True)

    # --- Admin ---
    elif call.data == "admin_relatorio" and is_admin(user_id):
        t, f, c = db.obter_dados_relatorio()
        bot.send_message(chat_id, f"📊 *RELATÓRIO*\n🛒 Vendas: {t}\n💰 Faturamento: R$ {f:.2f}")

    elif call.data == "admin_add_estoque" and is_admin(user_id):
        msg = bot.send_message(chat_id, "📥 Envie no formato: `categoria|conteudo` (Ex: `streaming|login:senha`)")
        bot.register_next_step_handler(msg, process_admin_add_simple)

    elif call.data == "admin_add_gg" and is_admin(user_id):
        msg = bot.send_message(chat_id, "💳 Envie no formato: `bin|banco|numero|validade|cvv` (Ex: `455188|Nubank|455188...|12/28|123`)")
        bot.register_next_step_handler(msg, process_admin_add_gg)

    elif call.data == "admin_add_dados" and is_admin(user_id):
        msg = bot.send_message(chat_id, "👤 Envie no formato: `Nome Completo|CPF` (Ex: `Joao Silva|12345678901`)")
        bot.register_next_step_handler(msg, process_admin_add_dados)


# --- Processadores Admin ---
def process_admin_add_simple(message):
    lines = message.text.strip().split("\n")
    for line in lines:
        if "|" in line:
            cat, cont = line.split("|", 1)
            db.adicionar_estoque(cat.lower().strip(), cont.strip())
    bot.send_message(message.chat.id, "✅ Itens adicionados.")


def process_admin_add_gg(message):
    lines = message.text.strip().split("\n")
    for line in lines:
        p = line.split("|")
        if len(p) >= 5:
            db.adicionar_estoque("gg", f"{p[2]}|{p[3]}|{p[4]}", p[0], p[1])
    bot.send_message(message.chat.id, "✅ GGs adicionadas.")


def process_admin_add_dados(message):
    lines = message.text.strip().split("\n")
    for line in lines:
        if "|" in line:
            nome, cpf = line.split("|")
            db.adicionar_dados_gg(nome.strip(), Security.encrypt(cpf.strip()))
    bot.send_message(message.chat.id, "✅ Dados adicionados e protegidos.")


def process_gift_redemption(message):
    val = db.resgatar_gift(message.text.strip(), message.from_user.id)
    bot.send_message(message.chat.id, f"✅ Resgatado: R$ {val:.2f}" if val else "❌ Código inválido.")


# --- Execução Principal ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
