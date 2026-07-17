from __future__ import annotations
from keep_alive import keep_alive

keep_alive()

import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote
import requests
import telebot
from telebot import apihelper, types
import database as db
from security_utils import CPFError, CPFProtector

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)
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
BASE = os.path.dirname(os.path.abspath(__file__))
db.DB_PATH = os.path.join(BASE, "bot_database.db")
db.criar_tabelas()
if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}
bot = telebot.TeleBot(TOKEN) if TOKEN else None
HEADERS = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
state: dict[int, dict[str, str]] = {}

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
    if not CRYPTO_TOKEN:
        return None
    payload = {
        "currency_type": "fiat",
        "fiat": "BRL",
        "amount": f"{value:.2f}",
        "description": description[:1024],
        "allow_comments": False,
        "allow_anonymous": False,
    }
    try:
        response = requests.post(
            f"{API_URL}/createInvoice", json=payload, headers=HEADERS, timeout=20
        )
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            result = data["result"]
            return Invoice(
                str(result["invoice_id"]),
                str(result.get("bot_invoice_url") or result.get("pay_url")),
            )
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        LOG.warning("Erro ao criar fatura: %s", exc)
    return None

def paid(invoice_id: str) -> bool:
    try:
        response = requests.get(
            f"{API_URL}/getInvoices",
            params={"invoice_ids": invoice_id},
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("result", {}).get("items", [])
        return bool(
            data.get("ok")
            and items
            and items[0].get("status") == "paid"
            and items[0].get("currency_type") == "fiat"
            and items[0].get("fiat") == "BRL"
        )
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
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
        types.InlineKeyboardButton(f"💳 GG • R$ 4,00 • {gg} disponíveis", callback_data="menu_gg"),
        types.InlineKeyboardButton(f"📺 Streaming • R$ 12,00 • {stream} disponíveis", callback_data="buy_streaming"),
        types.InlineKeyboardButton(f"📶 eSIM • R$ 20,00 • {esim} disponíveis", callback_data="buy_esim"),
        types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
        types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
    )
    require_bot().send_message(
        chat,
        f"🏪 *LOJA DIGITAL*\n\n💰 Saldo: `R$ {saldo:.2f}`\nEscolha uma opção:",
        reply_markup=markup,
        parse_mode="Markdown",
    )

if bot:
    @bot.message_handler(commands=["start"])
    def start(message: Any) -> None:
        register(message)
        home(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["add"])
    def add(message: Any) -> None:
        if not is_admin(message):
            return
        parts = (message.text or "").split(maxsplit=2)
        option = parts[1].lower() if len(parts) > 1 else ""
        if option == "dados":
            msg = bot.reply_to(message, "👤 /add dados — passo 1/2: informe o nome completo:")
            bot.register_next_step_handler(msg, data_name)
        elif option == "streaming" and len(parts) == 3:
            db.adicionar_estoque("streaming", parts[2])
            bot.reply_to(message, "✅ Streaming cadastrado por R$ 12,00.")
        else:
            bot.reply_to(
                message,
                "Uso:\n`/add dados`\n`/add streaming LOGIN|SENHA|OBS`",
                parse_mode="Markdown",
            )

    @bot.message_handler(commands=["add_gg_massa"])
    def add_gg_massa_inicio(message):
        if not is_admin(message): return
        msg = bot.reply_to(message, "Informe o nome do banco")
        bot.register_next_step_handler(msg, add_gg_massa_dados)

    def add_gg_massa_dados(message: Any) -> None:
        if not is_admin(message): return
        banco = message.text.strip()
        msg = bot.reply_to(message, f"✅ Banco '{banco}' definido.\nAgora envie a lista (um por linha):\nFormato: NÚMERO|VALIDADE|CVV")
        state[message.from_user.id] = {"banco": banco}
        bot.register_next_step_handler(msg, processar_gg_massa)

    def processar_gg_massa(message: Any) -> None:
        current = state.pop(message.from_user.id, None)
        if not is_admin(message) or not current: return
        linhas = message.text.split('\n')
        sucesso = 0
        for linha in linhas:
            if '|' not in linha: continue
            try:
                dados = linha.strip()
                bin_v = dados.split('|')[0][:6]
                db.adicionar_gg_pendente(bin_v, current["banco"], dados, message.from_user.id)
                sucesso += 1
            except: continue
        bot.reply_to(message, f"✅ {sucesso} GGs do banco {current['banco']} adicionadas!")

    @bot.message_handler(commands=["add_dados_massa"])
    def add_dados_massa(message: Any) -> None:
        if not is_admin(message): return
        texto = message.text.replace("/add_dados_massa", "").strip()
        linhas = texto.split('\n')
        sucesso = 0
        for linha in linhas:
            if '|' not in linha: continue
            try:
                nome, cpf = linha.split('|', 1)
                p = protect()
                cipher = p.encrypt(cpf.strip())
                db.adicionar_dados_pendentes(nome.strip(), cipher, p.fingerprint(cpf.strip()), message.from_user.id)
                sucesso += 1
            except: continue
        bot.reply_to(message, f"✅ {sucesso} registros de Dados adicionados com sucesso!")

    def data_name(message: Any) -> None:
        value = (message.text or "").strip()
        if not is_admin(message) or len(value) < 3:
            bot.reply_to(message, "❌ Nome inválido. Recomece com /add dados.")
            return
        state[message.from_user.id] = {"name": value}
        msg = bot.reply_to(message, "🪪 Passo 2/2: informe o CPF completo:")
        bot.register_next_step_handler(msg, data_cpf)

    def data_cpf(message: Any) -> None:
        current = state.pop(message.from_user.id, None)
        if not is_admin(message) or not current: return
        try:
            p = protect()
            cipher = p.encrypt(message.text or "")
            did, gid = db.adicionar_dados_pendentes(current["name"], cipher, p.fingerprint(message.text or ""), message.from_user.id)
        except (CPFError, RuntimeError) as exc:
            bot.reply_to(message, f"❌ {exc} Recomece com /add dados.")
            return
        suffix = (" Pareado com GG #" + str(gid) if gid else " Aguardando próxima GG")
        bot.reply_to(message, f"✅ Dados #{did} cadastrados.{suffix}")

    @bot.message_handler(commands=["add_esim"])
    def add_esim(message: Any) -> None:
        if not is_admin(message): return
        msg = bot.reply_to(message, "Informe código|file_id_da_imagem do eSIM:")
        bot.register_next_step_handler(msg, save_esim)

    def save_esim(message: Any) -> None:
        if is_admin(message) and message.text:
            db.adicionar_estoque("esim", message.text)
            bot.reply_to(message, "✅ eSIM cadastrado por R$ 20,00.")

    @bot.message_handler(commands=["promocao"])
    def promotion(message: Any) -> None:
        if not is_admin(message): return
        try:
            value = float((message.text or "").split(maxsplit=1)[1].replace(",", "."))
            db.definir_promocao(value, message.from_user.id)
            bot.reply_to(message, f"✅ Promoção de {value:g}% ativa.")
        except (IndexError, ValueError):
            bot.reply_to(message, "Uso: /promocao 100 (0 desativa).")

    @bot.message_handler(commands=["filas"])
    def queues(message: Any) -> None:
        if is_admin(message):
            gg, data, ready = db.obter_status_filas()
            bot.reply_to(message, f"📦 GG: {gg}\n👤 Dados: {data}\n✅ Pares: {ready}")

    @bot.message_handler(commands=["ver_gg"])
    def view_gg(message: Any) -> None:
        if not is_admin(message): return
        try:
            sid = int((message.text or "").split()[1])
            row = db.obter_gg_admin(sid, message.from_user.id)
            if not row: raise ValueError
            cpf = protect().decrypt(str(row["cpf_ciphertext"])) if row["cpf_ciphertext"] else "Não pareado"
            bot.reply_to(message, f"GG #{sid}\nStatus: {row['status']}\nBIN: {row['bin']}\nConteúdo: `{row['conteudo']}`\nCPF: `{cpf}`", parse_mode="Markdown")
        except (IndexError, ValueError, CPFError, RuntimeError):
            bot.reply_to(message, "Uso: /ver_gg ID.")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any) -> None:
        if is_admin(message):
            total, revenue, cats = db.obter_dados_relatorio()
            bot.reply_to(message, f"📈 Vendas: {total}\n💰 R$ {revenue:.2f}\n{cats}")

    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: Any) -> None:
        register(call)
        bot.answer_callback_query(call.id)
        chat = call.message.chat.id
        uid = call.from_user.id
        if call.data == "inicio": home(chat, uid)
        elif call.data == "conta":
            history = db.ultimos_depositos(uid)
            lines = "\n".join(f"• R$ {r['valor_recebido']:.2f} — {r['status']}" for r in history) or "Nenhum depósito."
            bot.send_message(chat, f"👤 *MINHA CONTA*\n🆔 `{uid}`\n💰 Saldo: `R$ {db.obter_saldo(uid):.2f}`\n\n{lines}", reply_markup=back(), parse_mode="Markdown")
        elif call.data == "saldo":
            promo = db.obter_promocao()
            msg = bot.send_message(chat, f"➕ Digite o valor em reais (Mín: R$ 10,00):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, deposit_value)
        elif call.data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ Sem estoque.", reply_markup=back())
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for bin_v, bank, count in groups:
                markup.add(types.InlineKeyboardButton(f"BIN {bin_v} • {bank} • {count} un", callback_data=f"sg|{quote(bin_v)}|{quote(bank)}"))
            bot.send_message(chat, "Escolha:", reply_markup=markup)
        elif call.data.startswith("sg|"):
            _, bin_v, bank = call.data.split("|", 2)
            inv = invoice(f"GG {unquote(bin_v)}", PRECOS["gg"])
            if not inv: return
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Pagar", url=inv.url), types.InlineKeyboardButton("Confirmar", callback_data=f"vg|{inv.invoice_id}|{bin_v}|{bank}"))
            bot.send_message(chat, "Fatura: R$ 4,00", reply_markup=markup)
        elif call.data.startswith("buy_"):
            cat = call.data[4:]
            inv = invoice(cat.title(), PRECOS[cat])
            if not inv: return
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Pagar", url=inv.url), types.InlineKeyboardButton("Confirmar", callback_data=f"vp|{cat}|{inv.invoice_id}"))
            bot.send_message(chat, f"Fatura: R$ {PRECOS[cat]:.2f}", reply_markup=markup)
        elif call.data.startswith("vg|"):
            _, inv_id, bn, bk = call.data.split("|", 3)
            if not paid(inv_id): bot.send_message(chat, "⚠️ Pendente."); return
            finish(chat, uid, "gg", *db.concluir_compra_fatura(inv_id, uid, "gg", 4, unquote(bn), unquote(bk)))
        elif call.data.startswith("vp|"):
            _, cat, inv_id = call.data.split("|", 2)
            if not paid(inv_id): bot.send_message(chat, "⚠️ Pendente."); return
            finish(chat, uid, cat, *db.concluir_compra_fatura(inv_id, uid, cat, float(PRECOS[cat])))
        elif call.data.startswith("vd|"):
            inv_id = call.data.split("|", 1)[1]
            if not paid(inv_id): bot.send_message(chat, "⚠️ Pendente."); return
            res, r, b, c = db.confirmar_deposito(inv_id, uid)
            if res == "ok": bot.send_message(chat, f"✅ Crédito de R$ {c:.2f} aplicado.")
            else: bot.send_message(chat, "ℹ️ Já processado.")

    def deposit_value(message: Any) -> None:
        try:
            val = Decimal((message.text or "").replace(",", ".")).quantize(Decimal("0.01"))
            if val < MIN_DEPOSITO: raise ValueError
        except: bot.reply_to(message, "❌ Valor inválido."); return
        inv = invoice("Saldo", val)
        if not inv: return
        db.criar_deposito(inv.invoice_id, message.from_user.id, float(val))
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Pagar", url=inv.url), types.InlineKeyboardButton("Confirmar", callback_data=f"vd|{inv.invoice_id}"))
        bot.reply_to(message, f"Fatura: R$ {val:.2f}", reply_markup=markup)

    def finish(chat, uid, cat, status, sid, content):
        if status != "ok": bot.send_message(chat, "❌ Erro ou sem estoque."); return
        if cat == "gg":
            d = db.obter_dados_gg_para_entrega(sid, uid)
            try: cpf = protect().decrypt(str(d["cpf_ciphertext"]))
            except: cpf = "Erro decriptação"
            bot.send_message(chat, f"⚡ *ENTREGUE*\nGG: `{content}`\nNome: {d['nome']}\nCPF: `{cpf}`", parse_mode="Markdown")
        else: bot.send_message(chat, f"⚡ Entregue: `{content}`", parse_mode="Markdown")

@bot.message_handler(commands=['comandos'])
def listar_comandos(message):
    if not is_admin(message): return
    bot.reply_to(message, "🛠 **Admin:**\n/add_gg_massa\n/add_dados_massa\n/status", parse_mode="Markdown")

if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(skip_pending=True)
        except Exception as exc:
            LOG.exception("Erro: %s", exc)
            time.sleep(15)

```
