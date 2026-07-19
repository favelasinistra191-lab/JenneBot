"""Bot Telegram de Loja Digital - Versão com Estatísticas e Visual Moderno."""

from __future__ import annotations
import logging
import os
import time
import threading
import random
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
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PIX_ESTATICO = "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607181421TUV2VAB162WC66304B341"
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

PRECOS = {"gg": 4.0, "streaming": 12.0, "esim": 20.0}

db.criar_tabelas()

if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}

bot = telebot.TeleBot(TOKEN) if TOKEN else None
state: dict[int, dict[str, Any]] = {}

# --- Servidor Web Keep-Alive ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot Online e Moderno!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive_ping():
    if not RENDER_URL: return
    while True:
        try: requests.get(RENDER_URL)
        except: pass
        time.sleep(600)

# --- Auxiliares ---

def protect() -> CPFProtector:
    key = os.getenv("CPF_ENCRYPTION_KEY", "").strip()
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
            "💎 *PAINEL ADMINISTRATIVO*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📦 *ADIÇÃO EM MASSA*\n"
            "• `/add gg` - Cartões\n"
            "• `/add dados` - Nome|CPF\n"
            "• `/add streaming` - Contas\n"
            "• `/add esim` - eSIMs\n\n"
            "📊 *GESTÃO DE LOJA*\n"
            "• `/estoque` - Ver itens\n"
            "• `/relatorio` - Vendas e Estatísticas\n"
            "• `/filas` - Status Pareamento\n\n"
            "🎁 *GIFT CARDS*\n"
            "• `/gerar_gift VALOR`"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any):
        if not is_admin(message): return
        total_vendas, faturamento, categorias = db.obter_dados_relatorio()
        total_clientes = db.contar_usuarios_unicos()
        cat_str = "\n".join([f"• {k.title()}: {v}" for k, v in categorias.items()])
        
        rel_text = (
            "📈 *RELATÓRIO GERAL DA LOJA*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Total de Clientes:* `{total_clientes}`\n"
            f"🛒 *Total de Vendas:* `{total_vendas}`\n"
            f"💰 *Faturamento:* `R$ {faturamento:.2f}`\n\n"
            f"📦 *Vendas por Categoria:*\n{cat_str}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        bot.reply_to(message, rel_text, parse_mode="Markdown")

    @bot.message_handler(commands=["estoque"])
    def view_stock(message: Any):
        if not is_admin(message): return
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        bot.reply_to(message, f"📋 *ESTOQUE DETALHADO*\n━━━━━━━━━━━━━━━━━━━━\n💳 GG: `{gg}` unidades\n📺 Streaming: `{stream}` unidades\n📶 eSIM: `{esim}` unidades", parse_mode="Markdown")

    @bot.message_handler(commands=["add"])
    def add_cmd(message: Any):
        if not is_admin(message): return
        parts = message.text.split()
        if len(parts) < 2: return
        option = parts[1].lower()
        if option == "gg":
            state[message.from_user.id] = {"flow": "gg_mass"}
            msg = bot.reply_to(message, "💳 *ADD GG EM MASSA*\n\nInforme a *BIN* (6-8 dígitos):")
            bot.register_next_step_handler(msg, gg_mass_bin)
        elif option == "dados":
            msg = bot.reply_to(message, "👤 *ADD DADOS EM MASSA*\n\nEnvie a lista no formato:\n`NOME|CPF`")
            bot.register_next_step_handler(msg, data_mass_process)
        elif option == "streaming":
            msg = bot.reply_to(message, "📺 *ADD STREAMING EM MASSA*\n\nEnvie a lista no formato:\n`EMAIL|SENHA|TELA|SENHA`")
            bot.register_next_step_handler(msg, stream_mass_process)
        elif option == "esim":
            msg = bot.reply_to(message, "📶 *ADD ESIM EM MASSA*\n\nEnvie a lista de conteúdos (um por linha):")
            bot.register_next_step_handler(msg, esim_mass_process)

    def gg_mass_bin(message: Any):
        state[message.from_user.id]["bin"] = message.text.strip()
        msg = bot.reply_to(message, "🏦 Informe o *Nome do Banco*:")
        bot.register_next_step_handler(msg, gg_mass_bank)

    def gg_mass_bank(message: Any):
        state[message.from_user.id]["bank"] = message.text.strip()
        msg = bot.reply_to(message, "📥 Agora envie a lista:\n`NUMERO|VALIDADE|CVV`")
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
        bot.reply_to(message, f"✅ *PROCESSO CONCLUÍDO*\n\nSucesso: `{s}`\nErros: `{e}`\n📦 Estoque Total GG: `{db.contar_estoque_categoria('gg')}`", parse_mode="Markdown")

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
        bot.reply_to(message, f"✅ *DADOS ADICIONADOS*\n\nSucesso: `{s}`\nErros: `{e}`", parse_mode="Markdown")

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
        bot.reply_to(message, f"✅ *STREAMINGS ADICIONADOS*\n\nSucesso: `{s}`\nErros: `{e}`", parse_mode="Markdown")

    def esim_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            try:
                db.adicionar_estoque("esim", line.strip())
                s += 1
            except: e += 1
        bot.reply_to(message, f"✅ *eSIMs ADICIONADOS*\n\nSucesso: `{s}`\nErros: `{e}`", parse_mode="Markdown")

    @bot.message_handler(commands=["gerar_gift"])
    def create_gift(message: Any):
        if not is_admin(message): return
        try:
            val = float(message.text.split()[1])
            code = "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
            db.criar_gift(code, val, message.from_user.id)
            bot.reply_to(message, f"🎁 *GIFT CARD GERADO*\n━━━━━━━━━━━━━━━━━━━━\nCódigo: `{code}`\nValor: `R$ {val:.2f}`\n━━━━━━━━━━━━━━━━━━━━\n_Mande para o cliente resgatar._", parse_mode="Markdown")
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
            bot.send_message(chat, "💰 *ADICIONAR SALDO*\n━━━━━━━━━━━━━━━━━━━━\nNo momento, apenas o *PIX Manual* está funcionando.\n\nApós realizar o pagamento, envie o comprovante no privado para que eu possa liberar seu saldo imediatamente.", reply_markup=markup, parse_mode="Markdown")
        elif data == "pix_manual":
            bot.send_message(chat, f"🏦 *PIX MANUAL (COPIA E COLA)*\n━━━━━━━━━━━━━━━━━━━━\nClique no código abaixo para copiar:\n\n`{PIX_ESTATICO}`\n\n━━━━━━━━━━━━━━━━━━━━\n⚠️ *AVISO:* Envie o comprovante no privado para liberação.", parse_mode="Markdown")
        elif data == "resgatar_btn":
            msg = bot.send_message(chat, "🎁 *RESGATE DE GIFT*\n\nDigite ou cole o código do seu Gift Card abaixo:")
            bot.register_next_step_handler(msg, process_gift_step)
        elif data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ *DESCULPE!*\nEstamos sem estoque de GG no momento. Volte mais tarde!", parse_mode="Markdown")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, bk, c in groups:
                markup.add(types.InlineKeyboardButton(f"💳 BIN {b} | {bk} | {c} un", callback_data=f"buy|gg|{b}|{bk}"))
            markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
            bot.send_message(chat, "💳 *ESCOLHA SUA BIN*\n━━━━━━━━━━━━━━━━━━━━\nTodas as GGs acompanham dados do titular.", reply_markup=markup, parse_mode="Markdown")
        elif data == "menu_streaming":
            count = db.contar_estoque_categoria("streaming")
            if count == 0:
                bot.send_message(chat, "❌ *SEM ESTOQUE!*\nStreaming indisponível no momento.", parse_mode="Markdown")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 12,00)", callback_data="buy|streaming"))
            markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
            bot.send_message(chat, f"📺 *STREAMING DISPONÍVEL*\n━━━━━━━━━━━━━━━━━━━━\n📦 Estoque: `{count}` unidades\n💰 Valor: `R$ 12,00`", reply_markup=markup, parse_mode="Markdown")
        elif data == "menu_esim":
            count = db.contar_estoque_categoria("esim")
            if count == 0:
                bot.send_message(chat, "❌ *SEM ESTOQUE!*\neSIM indisponível no momento.", parse_mode="Markdown")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 20,00)", callback_data="buy|esim"))
            markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
            bot.send_message(chat, f"📶 *eSIM DISPONÍVEL*\n━━━━━━━━━━━━━━━━━━━━\n📦 Estoque: `{count}` unidades\n💰 Valor: `R$ 20,00`", reply_markup=markup, parse_mode="Markdown")
        elif data.startswith("buy|"):
            process_purchase(call)
        elif data == "conta":
            saldo = db.obter_saldo(uid)
            bot.send_message(chat, f"👤 *MINHA CONTA*\n━━━━━━━━━━━━━━━━━━━━\n🆔 Seu ID: `{uid}`\n💰 Saldo Atual: `R$ {saldo:.2f}`\n━━━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")

    def process_purchase(call: Any):
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        saldo = db.obter_saldo(uid)
        parts = data.split("|")
        cat = parts[1]
        price = PRECOS[cat]
        bn, bk = (parts[2], parts[3]) if cat == "gg" else (None, None)

        if saldo < price:
            bot.send_message(chat, f"❌ *SALDO INSUFICIENTE!*\n\nVocê possui `R$ {saldo:.2f}`\nValor necessário: `R$ {price:.2f}`\n\nAdicione saldo para continuar.", parse_mode="Markdown")
            return

        inv_id = f"BUY-{int(time.time())}-{uid}"
        status, sid, conteudo = db.concluir_compra_fatura(inv_id, uid, cat, price, bn, bk)

        if status == "ok":
            agora = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
            if cat == "gg":
                d = db.obter_dados_gg_para_entrega(sid, uid)
                cpf = protect().decrypt(d[3])
                nums = conteudo.split("|")
                msg = (
                    f"✅ *COMPRA REALIZADA!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💳 *DADOS DO CARTÃO:*\n"
                    f"• Número: `{nums[0]}`\n"
                    f"• Validade: `{nums[1]}`\n"
                    f"• CVV: `{nums[2]}`\n\n"
                    f"🏦 *BANCO:* `{d[1]}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *DADOS DO TITULAR:*\n"
                    f"• Nome: `{d[2]}`\n"
                    f"• CPF: `{cpf}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 *ENTREGA:* `{agora}`\n\n"
                    f"⚠️ *AVISO:* Você tem 10 minutos para realizar a troca em caso de erro. Após esse tempo, não nos responsabilizamos."
                )
            elif cat == "streaming":
                s = conteudo.split("|")
                msg = (
                    f"✅ *COMPRA REALIZADA!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📺 *DADOS DO STREAMING:*\n"
                    f"• Email: `{s[0]}`\n"
                    f"• Senha: `{s[1]}`\n"
                    f"• Tela: `{s[2]}`\n"
                    f"• PIN: `{s[3]}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 *ENTREGA:* `{agora}`"
                )
            else:
                msg = f"✅ *COMPRA REALIZADA!*\n━━━━━━━━━━━━━━━━━━━━\n📦 *CONTEÚDO:* `{conteudo}`\n━━━━━━━━━━━━━━━━━━━━\n🕒 *ENTREGA:* `{agora}`"
            
            bot.send_message(chat, msg, parse_mode="Markdown")
        else:
            bot.send_message(chat, "❌ *ERRO NO SISTEMA!*\nOcorreu uma falha ao processar sua compra. O saldo não foi debitado.")

    def process_gift_step(message: Any):
        valor = db.resgatar_gift(message.text.strip(), message.from_user.id)
        if valor:
            bot.send_message(message.chat.id, f"✅ *SUCESSO!*\n\nO Gift Card foi resgatado e *R$ {valor:.2f}* foram adicionados ao seu saldo.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ *ERRO:* Código inválido, já utilizado ou inexistente.", parse_mode="Markdown")

    def home(chat: int, uid: int):
        saldo = db.obter_saldo(uid)
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"💳 GG | R$ 4,00 | {gg} un", callback_data="menu_gg"),
            types.InlineKeyboardButton(f"📺 Streaming | R$ 12,00 | {stream} un", callback_data="menu_streaming"),
            types.InlineKeyboardButton(f"📶 eSIM | R$ 20,00 | {esim} un", callback_data="menu_esim"),
            types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
            types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
            types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
        )
        msg_home = (
            "🏪 *BEM-VINDO À LOJA DIGITAL*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Escolha uma das opções abaixo para navegar no nosso catálogo.\n\n"
            f"💰 Seu Saldo: `R$ {saldo:.2f}`"
        )
        bot.send_message(chat, msg_home, reply_markup=markup, parse_mode="Markdown")

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
