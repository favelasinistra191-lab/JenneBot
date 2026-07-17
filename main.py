"""Bot Telegram de GG, streaming, eSIM e saldo em reais (BRL)."""

from __future__ import annotations
import logging
import os
import time
import threading
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

# Configuração de Logs
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

# Variáveis de Ambiente
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
API_URL = os.getenv("CRYPTO_PAY_API_URL", "https://pay.crypt.bot/api").rstrip("/")
MIN_DEPOSITO = Decimal("10.00")
PRECOS = {
    "gg": Decimal("4.00"),
    "streaming": Decimal("12.00"),
    "esim": Decimal("20.00"),
}

# Banco de Dados
BASE = os.path.dirname(os.path.abspath(__file__))
db.DB_PATH = os.path.join(BASE, "bot_database.db")
db.criar_tabelas()

# Proxy e Bot
if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}
bot = telebot.TeleBot(TOKEN) if TOKEN else None
HEADERS = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
state: dict[int, dict[str, str]] = {}

# --- Servidor Web para o Render ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Classes e Funções Auxiliares ---

@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    url: str

def protect() -> CPFProtector:
    key = os.getenv("CPF_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("Configure CPF_ENCRYPTION_KEY no .env.")
    return CPFProtector.from_string(key)

def require_bot() -> telebot.TeleBot:
    if bot is None:
        raise RuntimeError("Configure TELEGRAM_BOT_TOKEN no .env.")
    return bot

def is_admin(message: Any) -> bool:
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

def register(obj: Any) -> None:
    user = obj.from_user
    name = (
        " ".join(
            x
            for x in [
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            ]
            if x
        )
        or "Cliente"
    )
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

def invoice(description: str, value: Decimal) -> Invoice | None:
    if not CRYPTO_TOKEN: return None
    payload = {
        "currency_type": "fiat", "fiat": "BRL", "amount": f"{value:.2f}",
        "description": description[:1024], "allow_comments": False, "allow_anonymous": False,
    }
    try:
        response = requests.post(f"{API_URL}/createInvoice", json=payload, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            result = data["result"]
            return Invoice(str(result["invoice_id"]), str(result.get("bot_invoice_url") or result.get("pay_url")))
    except Exception as exc:
        LOG.warning("Erro ao criar fatura: %s", exc)
    return None

def paid(invoice_id: str) -> bool:
    try:
        response = requests.get(f"{API_URL}/getInvoices", params={"invoice_ids": invoice_id}, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        items = data.get("result", {}).get("items", [])
        return bool(data.get("ok") and items and items[0].get("status") == "paid")
    except Exception as exc:
        LOG.warning("Erro ao consultar fatura: %s", exc)
        return False

def back() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Início", callback_data="inicio"))
    return markup

def home(chat: int, uid: int) -> None:
    saldo = db.obter_saldo(uid)
    gg = db.contar_estoque_categoria("gg")
    stream = db.contar_estoque_categoria("streaming")
    esim = db.contar_estoque_categoria("esim")
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"💳 GG • R$ 4,00 • {gg} unidades", callback_data="menu_gg"),
        types.InlineKeyboardButton(f"📺 Streaming • R$ 12,00 • {stream} unidades", callback_data="buy_streaming"),
        types.InlineKeyboardButton(f"📶 eSIM • R$ 20,00 • {esim} unidades", callback_data="buy_esim"),
        types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
        types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
    )
    require_bot().send_message(chat, f"🏪 *LOJA DIGITAL*\n\n💰 Saldo: `R$ {saldo:.2f}`\nEscolha uma opção:", reply_markup=markup, parse_mode="Markdown")

# --- Handlers do Bot ---

if bot:
    @bot.message_handler(commands=["start"])
    def start(message: Any) -> None:
        register(message)
        home(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["menu"])
    def admin_menu(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        menu_text = (
            "🛠️ *MENU DO ADMINISTRADOR*\n\n"
            "📦 *Gerenciamento de Estoque:*\n"
            "• `/add gg` - Inicia adição em massa de GGs\n"
            "• `/add dados` - Adiciona dados (Nome/CPF)\n"
            "• `/add streaming LOGIN|SENHA|OBS` - Adiciona streaming\n"
            "• `/add_esim` - Adiciona eSIM\n\n"
            "📊 *Relatórios e Status:*\n"
            "• `/relatorio` - Vendas e faturamento total\n"
            "• `/filas` - Status das filas\n"
            "• `/ver_gg ID` - Detalhes de uma GG\n\n"
            "⚙️ *Configurações:*\n"
            "• `/promocao VALOR` - Define bônus de depósito"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["add"])
    def add(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        parts = (message.text or "").split(maxsplit=2)
        option = parts[1].lower() if len(parts) > 1 else ""
        if option == "gg":
            state[message.from_user.id] = {"flow": "gg_mass"}
            msg = bot.reply_to(message, "💳 *ADIÇÃO EM MASSA DE GG*\n\nPasso 1/3: informe a BIN (6 a 8 dígitos):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, gg_mass_bin)
        elif option == "dados":
            state[message.from_user.id] = {"flow": "dados"}
            msg = bot.reply_to(message, "👤 /add dados — passo 1/2: informe o nome completo:")
            bot.register_next_step_handler(msg, data_name)
        elif option == "streaming" and len(parts) == 3:
            db.adicionar_estoque("streaming", parts[2])
            bot.reply_to(message, "✅ Streaming cadastrado por R$ 12,00.")
        else:
            bot.reply_to(message, "Uso:\n`/add gg` (em massa)\n`/add dados`\n`/add streaming LOGIN|SENHA|OBS`", parse_mode="Markdown")

    def gg_mass_bin(message: Any) -> None:
        value = (message.text or "").strip()
        if not is_admin(message) or not value.isdigit() or not 6 <= len(value) <= 8:
            bot.reply_to(message, "❌ BIN inválida. Recomece com /add gg.")
            return
        state[message.from_user.id]["bin"] = value
        msg = bot.reply_to(message, "🏦 Passo 2/3: informe o Banco:")
        bot.register_next_step_handler(msg, gg_mass_bank)

    def gg_mass_bank(message: Any) -> None:
        value = (message.text or "").strip()
        if not is_admin(message) or not value: return
        state[message.from_user.id]["bank"] = value
        msg = bot.reply_to(message, f"✅ *Configuração salva!*\nBIN: `{state[message.from_user.id]['bin']}`\nBanco: `{value}`\n\n📥 Passo 3/3: Agora envie a lista `NUMERO|VALIDADE|CVV`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, gg_mass_process)

    def gg_mass_process(message: Any) -> None:
        current = state.pop(message.from_user.id, None)
        if not is_admin(message) or not current: return
        lines = (message.text or "").strip().split("\n")
        success, errors = 0, 0
        for line in lines:
            parts = line.strip().split("|")
            if len(parts) == 3:
                try:
                    db.adicionar_gg_pendente(current["bin"], current["bank"], line.strip(), message.from_user.id)
                    success += 1
                except: errors += 1
            else: errors += 1
        bot.reply_to(message, f"📊 *RESULTADO*\n✅ Sucesso: {success}\n❌ Erros: {errors}\n📦 Total: {db.contar_estoque_categoria('gg')}", parse_mode="Markdown")

    def data_name(message: Any) -> None:
        value = (message.text or "").strip()
        if not is_admin(message) or len(value) < 3:
            bot.reply_to(message, "❌ Nome inválido.")
            return
        state[message.from_user.id]["name"] = value
        msg = bot.reply_to(message, "🪪 Passo 2/2: informe o CPF completo:")
        bot.register_next_step_handler(msg, data_cpf)

    def data_cpf(message: Any) -> None:
        current = state.pop(message.from_user.id, None)
        if not is_admin(message) or not current: return
        try:
            p = protect()
            did, gid = db.adicionar_dados_pendentes(current["name"], p.encrypt(message.text or ""), p.fingerprint(message.text or ""), message.from_user.id)
            suffix = f" Pareado com GG #{gid}" if gid else " Aguardando GG"
            bot.reply_to(message, f"✅ Dados #{did} cadastrados.{suffix}")
        except Exception as exc:
            bot.reply_to(message, f"❌ {exc}")

    @bot.message_handler(commands=["add_esim"])
    def add_esim(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        msg = bot.reply_to(message, "Informe código|file_id_da_imagem do eSIM:")
        bot.register_next_step_handler(msg, save_esim)

    def save_esim(message: Any) -> None:
        if is_admin(message) and message.text:
            db.adicionar_estoque("esim", message.text)
            bot.reply_to(message, "✅ eSIM cadastrado.")

    @bot.message_handler(commands=["promocao"])
    def promotion(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        try:
            value = float((message.text or "").split(maxsplit=1)[1].replace(",", "."))
            db.definir_promocao(value, message.from_user.id)
            bot.reply_to(message, f"✅ Promoção de {value:g}% ativa.")
        except: bot.reply_to(message, "Uso: /promocao 10 (0 desativa).")

    @bot.message_handler(commands=["filas"])
    def queues(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        gg, data, ready = db.obter_status_filas()
        bot.reply_to(message, f"📦 GG aguardando: {gg}\n👤 Dados aguardando: {data}\n✅ Pares prontos: {ready}")

    @bot.message_handler(commands=["ver_gg"])
    def view_gg(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        try:
            sid = int((message.text or "").split()[1])
            row = db.obter_gg_admin(sid, message.from_user.id)
            cpf = protect().decrypt(str(row["cpf_ciphertext"])) if row and row["cpf_ciphertext"] else "Não pareado"
            bot.reply_to(message, f"GG #{sid}\nBIN: {row['bin']}\nBanco: {row['banco']}\nConteúdo: `{row['conteudo']}`\nCPF: `{cpf}`", parse_mode="Markdown")
        except: bot.reply_to(message, "Uso: /ver_gg ID")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any) -> None:
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        total, revenue, cats = db.obter_dados_relatorio()
        bot.reply_to(message, f"📈 Vendas: {total}\n💰 Faturamento: R$ {revenue:.2f}\n{cats}")

    @bot.message_handler(func=lambda message: message.text and message.text.startswith("/"))
    def unknown_command(message: Any) -> None:
        bot.reply_to(message, "❌ Código não encontrado, código não existente.")

    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: Any) -> None:
        register(call)
        bot.answer_callback_query(call.id)
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        if data == "inicio": home(chat, uid)
        elif data == "conta":
            history = db.ultimos_depositos(uid)
            lines = "\n".join(f"• R$ {r['valor_recebido']:.2f} — {r['status']}" for r in history) or "Nenhum depósito."
            bot.send_message(chat, f"👤 *MINHA CONTA*\n🆔 `{uid}`\n💰 Saldo: `R$ {db.obter_saldo(uid):.2f}`\n\n{lines}", reply_markup=back(), parse_mode="Markdown")
        elif data == "saldo":
            msg = bot.send_message(chat, f"➕ *ADICIONAR SALDO*\nMínimo: `R$ 10,00`\nDigite o valor:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, deposit_value)
        elif data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ Sem estoque.", reply_markup=back())
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, bk, c in groups:
                markup.add(types.InlineKeyboardButton(f"BIN {b} • {bk} • {c} • R$ 4,00", callback_data=f"sg|{quote(b)}|{quote(bk)}"))
            bot.send_message(chat, "Escolha:", reply_markup=markup)
        elif data.startswith("sg|"):
            _, b, bk = data.split("|", 2)
            inv = invoice(f"GG {unquote(b)}", PRECOS["gg"])
            if not inv: return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Pagar", url=inv.url), types.InlineKeyboardButton("Confirmar", callback_data=f"vg|{inv.invoice_id}|{b}|{bk}"))
            bot.send_message(chat, "Fatura: `R$ 4,00`", reply_markup=markup, parse_mode="Markdown")
        elif data.startswith("buy_"):
            cat = data[4:]
            inv = invoice(cat.title(), PRECOS[cat])
            if not inv: return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Pagar", url=inv.url), types.InlineKeyboardButton("Confirmar", callback_data=f"vp|{cat}|{inv.invoice_id}"))
            bot.send_message(chat, f"Fatura: `R$ {PRECOS[cat]:.2f}`", reply_markup=markup, parse_mode="Markdown")
        elif data.startswith("vg|"):
            _, inv_id, bn, bk = data.split("|", 3)
            if not paid(inv_id): return
            finish(chat, uid, "gg", *db.concluir_compra_fatura(inv_id, uid, "gg", 4, unquote(bn), unquote(bk)))
        elif data.startswith("vp|"):
            _, cat, inv_id = data.split("|", 2)
            if not paid(inv_id): return
            finish(chat, uid, cat, *db.concluir_compra_fatura(inv_id, uid, cat, float(PRECOS[cat])))
        elif data.startswith("vd|"):
            inv_id = data.split("|", 1)[1]
            if not paid(inv_id): return
            res, rec, bon, cre = db.confirmar_deposito(inv_id, uid)
            if res == "ok": bot.send_message(chat, f"✅ Crédito: `R$ {cre:.2f}`", reply_markup=back(), parse_mode="Markdown")

    def deposit_value(message: Any) -> None:
        try:
            val = Decimal(message.text.replace(",", ".")).quantize(Decimal("0.01"))
            if val < MIN_DEPOSITO: return
            inv = invoice("Depósito", val)
            if not inv: return
            db.criar_deposito(inv.invoice_id, message.from_user.id, float(val))
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Pagar", url=inv.url), types.InlineKeyboardButton("Confirmar", callback_data=f"vd|{inv.invoice_id}"))
            bot.reply_to(message, f"Valor: `R$ {val:.2f}`", reply_markup=markup, parse_mode="Markdown")
        except: pass

    def finish(chat, uid, cat, status, sid, content):
        if status != "ok" or not sid: return
        if cat == "gg":
            d = db.obter_dados_gg_para_entrega(sid, uid)
            cpf = protect().decrypt(str(d["cpf_ciphertext"]))
            bot.send_message(chat, f"⚡ *GG*\nBanco: {d['banco']}\nBIN: `{d['bin']}`\nGG: `{content}`\nNome: {d['nome']}\nCPF: `{cpf}`", parse_mode="Markdown")
        elif cat == "esim":
            f_id, s, c = content.partition("|")
            bot.send_photo(chat, f_id, caption=f"eSIM: `{c}`") if s else bot.send_message(chat, content)
        else: bot.send_message(chat, f"⚡ Streaming: `{content}`", parse_mode="Markdown")

if __name__ == "__main__":
    # Inicia Flask em uma thread separada
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Inicia Bot
    while True:
        try:
            LOG.info("Iniciando Bot...")
            bot.remove_webhook() # Limpa webhooks antigos
            time.sleep(2) # Delay para evitar conflito 409
            bot.infinity_polling(timeout=20, long_polling_timeout=20, skip_pending=True)
        except Exception as exc:
            LOG.error(f"Erro no polling: {exc}")
            time.sleep(10)
