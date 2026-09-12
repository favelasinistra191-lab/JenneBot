import os
import re
import time
import uuid
import logging
import threading
from datetime import datetime, timedelta

import requests
import telebot
from telebot import types
import mercadopago
from flask import Flask, request, jsonify

import config
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
LOG = logging.getLogger("DonGhostBot")

bot = telebot.TeleBot(config.TOKEN, threaded=True)

MP_ACCESS_TOKEN = os.getenv(
    "MP_ACCESS_TOKEN",
    "APP_USR-249848378901175-080605-e67c3c2b3575d5a687864a126913a7ae-3171236437",
)
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

SUPORTE_TG = "https://t.me/JENNE_BOT_SUPORTE"
SUPORTE_WA = "https://wa.me/639272951705"
PRECO_MINIMO_PIX = float(os.getenv("PRECO_MINIMO_PIX", "10.0"))

ADMIN_ABASTECENDO = {}
app = Flask(__name__)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def eh_admin(user_id):
    return int(user_id) == int(config.ADMIN_ID)


def sanitizar(txt):
    for c in ("*", "_", "`", "["):
        txt = txt.replace(c, "")
    return txt


def responder(call, texto, alerta=True):
    try:
        bot.answer_callback_query(call.id, texto, show_alert=alerta)
    except Exception as e:
        LOG.debug("answer_callback_query ignorado: %s", e)


def editar_ou_enviar(call, texto, markup=None):
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=texto,
            reply_markup=markup,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        bot.send_message(
            call.message.chat.id, texto,
            reply_markup=markup, parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return False


def obter_saldo_usuario(user_id):
    u = db.get_usuario(user_id)
    return float(u["saldo"]) if u else 0.0


def enviar_menu(chat_id, user_id):
    db.garantir_usuario(user_id, "", "")
    saldo = obter_saldo_usuario(user_id)
    texto = (
        "💎 **BEM-VINDO AO BOT DON GG • PREMIUM SHOP** 💎\n"
        "───────────────────────────────\n"
        f"👤 **ID de Acesso:** `{user_id}`\n"
        f"💰 **Saldo em Conta:** `R$ {saldo:.2f}`\n"
        "───────────────────────────────\n"
        "🔥 *As melhores GG'S do mercado, GGs de alta qualidade e aprovação expressa.*"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💳 Comprar GGs", callback_data="menu_gg"),
        types.InlineKeyboardButton("💳 Fazer Recarga Pix", callback_data="menu_recarga"),
        types.InlineKeyboardButton("👤 Meu Perfil", callback_data="perfil"),
        types.InlineKeyboardButton("📦 Minhas Compras", callback_data="historico_compras"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="info_gift"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte"),
    )
    banner = db.get_config("banner_file_id") if hasattr(db, "get_config") else None
    if banner:
        try:
            bot.send_photo(chat_id, photo=banner, caption=texto,
                           reply_markup=markup, parse_mode="Markdown")
            return
        except Exception as e:
            LOG.warning("Banner indisponivel, usando texto: %s", e)
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")


# --------------------------------------------------------------------------
# COMANDOS
# --------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_id = message.from_user.id
    db.garantir_usuario(user_id, message.from_user.first_name or "Cliente",
                        message.from_user.username or "")
    enviar_menu(message.chat.id, user_id)


@bot.message_handler(commands=["ajuda", "help"])
def cmd_ajuda(message):
    bot.reply_to(message,
                 "🤖 **COMANDOS**\n\n"
                 "/start — Menu principal\n"
                 "/pix 20 — Gerar cobrança Pix\n"
                 "/resgatar GIFT-XXXX — Resgatar saldo\n\n"
                 "👑 **Admin**\n"
                 "/abastecer [ID/Nome] — Cadastrar cards\n"
                 "/set_preco [ID] [valor] — Preço do produto\n"
                 "/gerar_gift [qtd] [valor] — Criar gifts\n"
                 "/estoque — Resumo do estoque\n"
                 "/limpar_estoque — Remover vendidos",
                 parse_mode="Markdown")


@bot.message_handler(commands=["estoque"])
def cmd_estoque(message):
    if not eh_admin(message.from_user.id):
        return
    produtos = db.listar_produtos(apenas_ativos=False)
    if not produtos:
        bot.reply_to(message, "📭 Nenhum produto cadastrado.")
        return
    linhas = ["📦 **ESTOQUE ATUAL**\n"]
    total = 0
    for p in produtos:
        q = db.contar_cards_livres(p["id"])
        total += q
        linhas.append(f"• `{p['nome']}` (ID: {p['id']}) → {q} disp. | R$ {p['preco']:.2f}")
    linhas.append(f"\n**TOTAL DE CARDS:** {total}")
    bot.reply_to(message, "\n".join(linhas), parse_mode="Markdown")


@bot.message_handler(commands=["abastecer"])
def cmd_abastecer(message):
    if not eh_admin(message.from_user.id):
        bot.reply_to(message, "🔒 Comando exclusivo do admin.")
        return

    texto = message.text or ""
    partes = [p for p in texto.splitlines()]
    tokens = partes[0].split()

    if len(tokens) < 2:
        bot.reply_to(message,
                     "⚠️ Use assim:\n`/abastecer [ID_PRODUTO]`\ne cole os cards na **próxima** mensagem.",
                     parse_mode="Markdown")
        return

    try:
        produto_id = int(tokens[1])
    except ValueError:
        bot.reply_to(message, "❌ ID do produto inválido. Use um número ex: `/abastecer 1`", parse_mode="Markdown")
        return

    prod = db.get_produto(produto_id)
    if not prod:
        bot.reply_to(message, f"❌ Produto com ID `{produto_id}` não encontrado. Cadastre o produto primeiro.", parse_mode="Markdown")
        return

    restantes = [l.strip() for l in partes[1:] if l.strip()]
    if restantes:
        adicionados, duplicados = db.adicionar_cards_em_lote("\n".join(restantes), produto_id, message.from_user.id)
        bot.reply_to(message,
                     f"✅ Adicionados **{adicionados}** cards ao produto `{prod['nome']}`.\n⚠️ Duplicados: {duplicados}",
                     parse_mode="Markdown")
        return

    ADMIN_ABASTECENDO[message.from_user.id] = produto_id
    bot.reply_to(message,
                 f"📥 Produto `{prod['nome']}` (ID: {produto_id}) selecionado.\n\n"
                 f"Agora cole as linhas dos cards na **próxima mensagem**, uma por linha.",
                 parse_mode="Markdown")


@bot.message_handler(func=lambda m: (
        m.text is not None
        and not m.text.startswith("/")
        and eh_admin(m.from_user.id)
        and m.from_user.id in ADMIN_ABASTECENDO))
def capturar_linhas_abastecimento(message):
    produto_id = ADMIN_ABASTECENDO.pop(message.from_user.id, None)
    if not produto_id:
        return
    linhas = [l.strip() for l in (message.text or "").splitlines() if l.strip()]
    if not linhas:
        bot.reply_to(message, "⚠️ Mensagem vazia. Abastecimento cancelado.")
        return
    adicionados, duplicados = db.adicionar_cards_em_lote("\n".join(linhas), produto_id, message.from_user.id)
    prod = db.get_produto(produto_id)
    nome_prod = prod['nome'] if prod else str(produto_id)
    bot.reply_to(message,
                 f"✅ **{adicionados}** cards salvos no produto `{nome_prod}`.\n"
                 f"⚠️ Ignorados/Duplicados: {duplicados}",
                 parse_mode="Markdown")


@bot.message_handler(commands=["set_preco"])
def cmd_set_preco(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/set_preco [id_produto] [valor]`", parse_mode="Markdown")
        return
    try:
        pid = int(args[1])
        valor = float(args[2].replace(",", "."))
        prod = db.get_produto(pid)
        if not prod:
            bot.reply_to(message, "❌ Produto não encontrado.")
            return
        db.adicionar_produto(prod["nome"], valor, prod["descricao"], prod["estoque"], prod["imagem"], produto_id=pid)
        bot.reply_to(message, f"✅ Produto `{prod['nome']}` atualizado para `R$ {valor:.2f}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["gerar_gift"])
def cmd_gerar_gift(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/gerar_gift [quantidade] [valor]`", parse_mode="Markdown")
        return
    try:
        qtd, valor = int(args[1]), float(args[2].replace(",", "."))
        codigos = []
        for _ in range(qtd):
            codigo = f"GIFT-{uuid.uuid4().hex[:8].upper()}"
            db.adicionar_card(codigo, None, senha=str(valor), admin_id=message.from_user.id)
            codigos.append(codigo)
        bot.reply_to(message,
                     f"🎁 **{qtd} gifts de R$ {valor:.2f} gerados!**\n\n" + "\n".join(f"`{c}`" for c in codigos),
                     parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["resgatar"])
def cmd_resgatar(message):
    args = (message.text or "").split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/resgatar GIFT-XXXXXXXX`", parse_mode="Markdown")
        return
    codigo = args[1].strip().upper()
    conn = db.get_conn()
    cur = conn.cursor()
    card = cur.execute("SELECT * FROM cards WHERE codigo = ? AND produto_id IS NULL AND vendido = 0", (codigo,)).fetchone()
    if not card:
        conn.close()
        bot.reply_to(message, "❌ Código de gift inválido ou já resgatado.")
        return
    valor = float(card["senha"] or 0)
    cur.execute("UPDATE cards SET vendido = 1, comprador_id = ?, comprado_em = ? WHERE id = ?", (message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), card["id"]))
    conn.commit()
    conn.close()

    db.atualizar_saldo(message.from_user.id, valor)
    novo_saldo = obter_saldo_usuario(message.from_user.id)
    bot.reply_to(message,
                 f"✅ **Gift resgatado com sucesso!**\n\n💵 Adicionado: `R$ {valor:.2f}`\n"
                 f"💰 Saldo atual: `R$ {novo_saldo:.2f}`",
                 parse_mode="Markdown")


@bot.message_handler(commands=["pix"])
def cmd_pix(message):
    args = (message.text or "").split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o valor.\nExemplo: `/pix 20`", parse_mode="Markdown")
        return
    try:
        valor = float(args[1].replace(",", "."))
    except ValueError:
        bot.reply_to(message, "❌ Valor inválido. Exemplo: `/pix 20`")
        return
    if valor < PRECO_MINIMO_PIX:
        bot.reply_to(message, f"⚠️ Valor mínimo para Pix: R$ {PRECO_MINIMO_PIX:.2f}")
        return
    link = gerar_link_pix(message.from_user.id, valor)
    if not link:
        bot.reply_to(message, "❌ Falha ao gerar o link no Mercado Pago. Tente novamente.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔗 Pagar com Pix (Mercado Pago)", url=link),
        types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"),
    )
    bot.reply_to(message,
                 f"💳 **LINK PIX GERADO!**\n\n💵 Valor: `R$ {valor:.2f}`\n\n"
                 f"Toque no botão para abrir o checkout. O saldo cai automaticamente após a aprovação.",
                 reply_markup=markup, parse_mode="Markdown")


@bot.message_handler(commands=["limpar_estoque"])
def cmd_limpar_estoque(message):
    if not eh_admin(message.from_user.id):
        return
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM cards WHERE vendido = 1 AND produto_id IS NOT NULL")
    removidos = cur.rowcount
    conn.commit()
    conn.close()
    bot.reply_to(message, f"🧹 {removidos} item(ns) vendido(s) removido(s) do estoque.")


@bot.message_handler(content_types=["photo"])
def capturar_novo_banner(message):
    if not eh_admin(message.from_user.id):
        return
    caption = message.caption or ""
    if "/mudar_banner" not in caption:
        return
    if hasattr(db, "set_config"):
        db.set_config("banner_file_id", message.photo[-1].file_id)
        bot.reply_to(message, "✅ **Banner atualizado!**", parse_mode="Markdown")


# --------------------------------------------------------------------------
# MERCADO PAGO
# --------------------------------------------------------------------------
def gerar_link_pix(user_id, valor):
    try:
        pref = {
            "items": [{
                "title": f"Recarga de Saldo - ID {user_id}",
                "quantity": 1,
                "unit_price": float(valor),
                "currency_id": "BRL",
            }],
            "external_reference": f"recarga_{user_id}_{int(time.time())}",
            "payment_methods": {
                "excluded_payment_types": [{"id": "credit_card"}, {"id": "ticket"}],
                "installments": 1,
            },
        }
        resp = sdk.preference().create(pref)
        return resp["response"].get("init_point")
    except Exception as e:
        LOG.error("Mercado Pago preference: %s", e)
        return None


@app.route("/")
def home():
    return "DonGhostBot rodando perfeitamente!"


@app.route("/webhook/mercadopago", methods=["POST", "GET"])
def webhook_mercadopago():
    try:
        dados = request.json or request.args.to_dict() or {}
        payment_id = (dados.get("data", {}) or {}).get("id") if isinstance(dados.get("data"), dict) \
            else dados.get("data") or dados.get("id")
        if not payment_id:
            return jsonify({"status": "ignored"}), 200

        resp = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return jsonify({"status": "not_found"}), 200

        p = resp.json()
        if p.get("status") != "approved":
            return jsonify({"status": p.get("status")}), 200

        ref = str(p.get("external_reference") or "")
        if "recarga_" not in ref:
            return jsonify({"status": "ignored"}), 200
        try:
            user_id = int(ref.split("_")[1])
        except (IndexError, ValueError):
            return jsonify({"status": "bad_ref"}), 200

        valor_pago = float(p.get("transaction_amount") or 0.0)
        if valor_pago <= 0:
            return jsonify({"status": "zero"}), 200

        db.atualizar_saldo(user_id, valor_pago)
        novo = obter_saldo_usuario(user_id)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
        try:
            bot.send_message(
                user_id,
                f"✅ **Pagamento aprovado via Mercado Pago!**\n\n"
                f"💵 Recarga de R$ {valor_pago:.2f} creditada.\n"
                f"💰 **Saldo atual:** `R$ {novo:.2f}`",
                reply_markup=markup, parse_mode="Markdown",
            )
        except Exception as e:
            LOG.error("Aviso de recarga nao entregue a %s: %s", user_id, e)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        LOG.error("Webhook MP: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


def run_web_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", config.PORT)))


# --------------------------------------------------------------------------
# CALLBACKS
# --------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: c.data == "voltar_menu")
def cb_voltar(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    enviar_menu(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data in ("perfil", "suporte", "info_gift", "historico_compras", "menu_recarga"))
def cb_estatico(call):
    uid, data = call.from_user.id, call.data

    if data == "perfil":
        responder(call, None, alerta=False)
        bot.send_message(call.message.chat.id,
                         f"👤 **Painel de Perfil**\n\n• ID: `{uid}`\n• Saldo: `R$ {obter_saldo_usuario(uid):.2f}`",
                         parse_mode="Markdown")

    elif data == "suporte":
        responder(call, None, alerta=False)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💬 Suporte Telegram", url=SUPORTE_TG),
            types.InlineKeyboardButton("💬 Suporte WhatsApp", url=SUPORTE_WA),
            types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"),
        )
        editar_ou_enviar(call, "📞 **CENTRAL DE SUPORTE OFICIAL**", markup)

    elif data == "menu_recarga":
        responder(call, None, alerta=False)
        editar_ou_enviar(call,
                         "💳 **FAZER RECARGA VIA PIX**\n\nEnvie o comando `/pix [valor]` no chat para gerar sua cobrança.\nExemplo: `/pix 20`",
                         types.InlineKeyboardMarkup(row_width=1).add(
                             types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")))

    elif data == "info_gift":
        responder(call, None, alerta=False)
        editar_ou_enviar(call,
                         "🎁 Para resgatar saldo, envie:\n`/resgatar GIFT-XXXXXXXX`",
                         types.InlineKeyboardMarkup(row_width=1).add(
                             types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")))

    elif data == "historico_compras":
        responder(call, None, alerta=False)
        itens = db.historico_vendas(user_id=uid, limite=10)
        if not itens:
            bot.send_message(call.message.chat.id, "📦 Você ainda não realizou compras.")
            return
        linhas = ["📦 **HISTÓRICO DE COMPRAS**\n"]
        for it in itens:
            linhas.append(f"🏷️ Produto ID: `{it.get('produto_id')}` • R$ {float(it.get('valor_total', 0)):.2f}\n"
                          f"💳 Cards:\n`{sanitizar(str(it.get('cards', '')))}`\n"
                          f"────────────────────")
        bot.send_message(call.message.chat.id, "\n".join(linhas), parse_mode="Markdown")


@bot.callback_query_handler(func=lambda c: c.data == "menu_gg")
def cb_menu_gg(call):
    responder(call, None, alerta=False)
    produtos = db.listar_produtos(apenas_ativos=True)
    if not produtos:
        responder(call, "⚠️ Nenhum produto disponível em estoque no momento!")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in produtos:
        q = db.contar_cards_livres(p["id"])
        if q > 0:
            markup.add(types.InlineKeyboardButton(
                f"🃏 {p['nome']} • {q} disp. • R$ {p['preco']:.2f}",
                callback_data=f"comprar_prod::{p['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
    editar_ou_enviar(call, "💳 **ESCOLHA O PRODUTO DESEJADO:**", markup)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("comprar_prod::"))
def cb_comprar_prod(call):
    try:
        produto_id = int(call.data.split("::", 1)[1])
    except ValueError:
        responder(call, "❌ Produto inválido.")
        return

    res = db.realizar_compra_item_casado(call.from_user.id, produto_id, quantidade=1, metodo="saldo")

    if res["status"] == "sem_saldo":
        responder(call, f"❌ Saldo insuficiente.\nVocê tem R$ {res['saldo']:.2f} e faltam R$ {res['faltam']:.2f}.")
        return
    if res["status"] == "sem_estoque":
        responder(call, "❌ Estoque esgotado para este produto.")
        return
    if res["status"] != "ok":
        responder(call, f"❌ Erro: {res.get('msg', 'Desconhecido')}")
        return

    cards_str = "\n".join([c["codigo"] for c in res["cards"]])
    msg = (
        "✅ **COMPRA EFETUADA!** ✅\n\n"
        f"🛍️ **Item(ns):**\n`{sanitizar(cards_str)}`\n\n"
        f"💰 **Saldo restante:** `R$ {res['saldo']:.2f}`"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🃏 Comprar outro", callback_data="menu_gg"),
        types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"),
    )
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    bot.send_message(call.message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")
    responder(call, "✅ Compra concluída!")


# --------------------------------------------------------------------------
# BOOT
# --------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    try:
        bot.remove_webhook()
    except Exception:
        pass
    LOG.info("DonGhostBot subindo em polling. Admin: %s", config.ADMIN_ID)
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error("Polling caiu: %s — reiniciando em 5s", e)
            time.sleep(5)
