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
db.criar_tabelas()

MP_ACCESS_TOKEN = os.getenv(
    "MP_ACCESS_TOKEN",
    "APP_USR-249848378901175-080605-e67c3c2b3575d5a687864a126913a7ae-3171236437",
)
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

CANAL_OBRIGATORIO = os.getenv("CANAL_OBRIGATORIO", "https://t.me/+VNkIZojSrHs4NDJh")
CANAL_PARA_API = CANAL_OBRIGATORIO.replace("https://t.me/+", "@").replace("https://t.me/", "@")
PRECO_MINIMO_PIX = float(os.getenv("PRECO_MINIMO_PIX", "10.0"))
SUPORTE_TG = "https://t.me/JENNE_BOT_SUPORTE"
SUPORTE_WA = "https://wa.me/639272951705"

ADMIN_ABASTECENDO = {}
app = Flask(__name__)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def eh_admin(user_id):
    return int(user_id) == int(config.ADMIN_ID)


def sanitizar(txt):
    """Evita que Markdown quebre com nomes contendo * _ ` [ ]."""
    for c in ("*", "_", "`", "["):
        txt = txt.replace(c, "")
    return txt


def responder(call, texto, alerta=True):
    """answer_callback_query sempre protegido — nunca deixa excecao subir."""
    try:
        bot.answer_callback_query(call.id, texto, show_alert=alerta)
    except Exception as e:
        LOG.debug("answer_callback_query ignorado: %s", e)


def editar_ou_enviar(call, texto, markup=None):
    """Edita a mensagem do botao; se falhar, manda nova. Nunca explode."""
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


def enviar_menu(chat_id, user_id):
    db.garantir_usuario(user_id, "", "")
    saldo = db.obter_saldo(user_id)
    texto = (
        "💎 **BEM-VINDO AO BOT DON GHOST • PREMIUM SHOP** 💎\n"
        "───────────────────────────────\n"
        f"👤 **ID de Acesso:** `{user_id}`\n"
        f"💰 **Saldo em Conta:** `R$ {saldo:.2f}`\n"
        "───────────────────────────────\n"
        "🔥 *As melhores notícias do mercado, GGs de alta qualidade e aprovação expressa.*"
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
    banner = db.get_config("banner_file_id")
    if banner:
        try:
            bot.send_photo(chat_id, photo=banner, caption=texto,
                           reply_markup=markup, parse_mode="Markdown")
            return
        except Exception as e:
            LOG.warning("Banner indisponivel, usando texto: %s", e)
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")


def verificar_inscricao_canal(user_id):
    if not CANAL_PARA_API or CANAL_PARA_API == "@+":
        return True
    try:
        membro = bot.get_chat_member(CANAL_PARA_API, user_id)
        return membro.status in ("member", "administrator", "creator")
    except telebot.apihelper.ApiTelegramException as e:
        # -1007 = usuario bloqueou/nao esta; outros erros nao trancam a loja
        if e.error_code == 400 or "not found" in str(e).lower():
            return False
        LOG.warning("Falha ao consultar canal (%s), liberando acesso.", e)
        return True


# --------------------------------------------------------------------------
# COMANDOS
# --------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_id = message.from_user.id
    db.garantir_usuario(user_id, message.from_user.first_name or "Cliente",
                        message.from_user.username or "")
    if not verificar_inscricao_canal(user_id):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 Entrar no Canal Oficial", url=CANAL_OBRIGATORIO),
            types.InlineKeyboardButton("🔄 Já Entrei / Verificar", callback_data="verificar_inscricao"),
        )
        bot.send_message(message.chat.id,
                         "⚠️ **Acesso Restrito!**\n\nPara utilizar o bot, entre no canal oficial primeiro.",
                         reply_markup=markup, parse_mode="Markdown")
        return
    enviar_menu(message.chat.id, user_id)


@bot.message_handler(commands=["ajuda", "help"])
def cmd_ajuda(message):
    bot.reply_to(message,
                 "🤖 **COMANDOS**\n\n"
                 "/start — Menu principal\n"
                 "/pix 20 — Gerar cobrança Pix\n"
                 "/resgatar GIFT-XXXX — Resgatar saldo\n\n"
                 "👑 **Admin**\n"
                 "/abastecer 515545 — Cadastrar GGs\n"
                 "/set_preco 515545 12.50 — Preço da BIN\n"
                 "/set_bonus 20 3 — Bônus de recarga\n"
                 "/gerar_gift 5 25 — Criar gifts\n"
                 "/estoque — Resumo do estoque\n"
                 "/limpar_estoque — Remover vendidos",
                 parse_mode="Markdown")


@bot.message_handler(commands=["estoque"])
def cmd_estoque(message):
    if not eh_admin(message.from_user.id):
        return
    bins = db.contar_por_bin("gg")
    if not bins:
        bot.reply_to(message, "📭 Estoque de GGs vazio.")
        return
    linhas = ["📦 **ESTOQUE ATUAL**\n"]
    total = 0
    for b, q in sorted(bins.items()):
        total += q
        linhas.append(f"• `{b}` → {q} disp. | R$ {db.obter_preco_bin(b):.2f}")
    linhas.append(f"\n**TOTAL:** {total} GGs")
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
                     "⚠️ Use assim:\n`/abastecer 515545`\ne cole as GGs na **próxima** mensagem.\n\n"
                     "Ou tudo junto:\n`/abastecer 515545`\n`515545xxxxxxxxxxxx|12|2030|209|Nome|CPF`",
                     parse_mode="Markdown")
        return

    digitos = "".join(filter(str.isdigit, tokens[1]))
    bin_alvo = digitos[:6] if len(digitos) >= 6 else tokens[1].upper()

    # Linhas coladas na MESMA mensagem
    restantes = [l.strip() for l in partes[1:] if l.strip() and "|" in l]
    if restantes:
        aceitas, rejeitadas = db.adicionar_lote_estoque(restantes, categoria="gg", bin_code=bin_alvo)
        aviso = f"\n⚠️ {rejeitadas} linha(s) ignorada(s) (formato inválido)." if rejeitadas else ""
        bot.reply_to(message,
                     f"✅ Adicionadas **{aceitas}** GGs na BIN `{bin_alvo}`.{aviso}",
                     parse_mode="Markdown")
        return

    ADMIN_ABASTECENDO[message.from_user.id] = bin_alvo
    bot.reply_to(message,
                 f"📥 BIN `{bin_alvo}` selecionada.\n\nAgora cole as linhas de GGs na **próxima mensagem**, "
                 f"uma por linha, no formato:\n`CC|MES|ANO|CVV|NOME|CPF`",
                 parse_mode="Markdown")


@bot.message_handler(func=lambda m: (
        m.text is not None
        and not m.text.startswith("/")
        and eh_admin(m.from_user.id)
        and m.from_user.id in ADMIN_ABASTECENDO))
def capturar_linhas_abastecimento(message):
    bin_alvo = ADMIN_ABASTECENDO.pop(message.from_user.id, "GERAL")
    linhas = [l.strip() for l in (message.text or "").splitlines() if l.strip()]
    if not linhas:
        bot.reply_to(message, "⚠️ Mensagem vazia. Abastecimento cancelado.")
        return
    aceitas, rejeitadas = db.adicionar_lote_estoque(linhas, categoria="gg", bin_code=bin_alvo)
    if not aceitas:
        bot.reply_to(message,
                     f"⚠️ Nenhuma linha válida. Formato esperado:\n`CC|MES|ANO|CVV|NOME|CPF`",
                     parse_mode="Markdown")
        return
    aviso = f"\n⚠️ {rejeitadas} ignorada(s)." if rejeitadas else ""
    bot.reply_to(message,
                 f"✅ **{aceitas}** GGs salvas na BIN `{bin_alvo}`.{aviso}\n"
                 f"Elas já aparecem no botão *💳 Comprar GGs*.",
                 parse_mode="Markdown")


@bot.message_handler(commands=["set_preco"])
def cmd_set_preco(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/set_preco [bin] [valor]`", parse_mode="Markdown")
        return
    try:
        bin_code = "".join(filter(str.isdigit, args[1]))[:6] or args[1]
        valor = float(args[2].replace(",", "."))
        db.definir_preco_bin(bin_code, valor)
        bot.reply_to(message, f"✅ BIN `{bin_code}` → `R$ {valor:.2f}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["set_bonus"])
def cmd_set_bonus(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/set_bonus [porcentagem] [dias opcional]`", parse_mode="Markdown")
        return
    try:
        pct = float(args[1].replace(",", "."))
        dias = int(args[2]) if len(args) > 2 else 1
        db.set_config("bonus_porcentagem", pct)
        db.set_config("bonus_expira_em", time.time() + dias * 86400 if dias > 0 else None)
        bot.reply_to(message, f"✅ Bônus de `{pct:.0f}%` ativo por {dias} dia(s).", parse_mode="Markdown")
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
            db.adicionar_gift(codigo, valor)
            codigos.append(codigo)
        bot.reply_to(message,
                     f"🎁 **{qtd} gifts de R$ {valor:.2f}**\n\n" + "\n".join(f"`{c}`" for c in codigos),
                     parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["resgatar"])
def cmd_resgatar(message):
    args = (message.text or "").split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/resgatar GIFT-XXXXXXXX`", parse_mode="Markdown")
        return
    status, valor = db.resgatar_gift(message.from_user.id, args[1].strip().upper())
    if status == "ok":
        bot.reply_to(message,
                     f"✅ **Gift resgatado!**\n\n💵 Adicionado: `R$ {valor:.2f}`\n"
                     f"💰 Saldo atual: `R$ {db.obter_saldo(message.from_user.id):.2f}`",
                     parse_mode="Markdown")
    elif status == "usado":
        bot.reply_to(message, "❌ Este gift já foi resgatado.")
    else:
        bot.reply_to(message, "❌ Código de gift inválido.")


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
    removidos = db.limpar_estoque()
    bot.reply_to(message, f"🧹 {removidos} item(ns) vendido(s) removido(s) do estoque.")


@bot.message_handler(content_types=["photo"])
def capturar_novo_banner(message):
    if not eh_admin(message.from_user.id):
        return
    caption = message.caption or ""
    if "/mudar_banner" not in caption:
        return
    db.set_config("banner_file_id", message.photo[-1].file_id)
    bot.reply_to(message, "✅ **Banner atualizado!**", parse_mode="Markdown")


# --------------------------------------------------------------------------
# MERCADO PAGO
# --------------------------------------------------------------------------
def bonus_ativo():
    dados = db.carregar_dados(forcar_atualizacao=True)
    cfg = dados.get("configuracoes", {})
    pct = float(cfg.get("bonus_porcentagem", 0.0) or 0.0)
    expira = cfg.get("bonus_expira_em")
    if expira and time.time() > float(expira):
        return 0.0
    return pct


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
            "notification_url": os.getenv("NOTIFICATION_URL", ""),
        }
        if not pref["notification_url"]:
            pref.pop("notification_url")
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

        chave = f"mp_paid_{payment_id}"
        if db.get_config(chave):
            return jsonify({"status": "duplicate"}), 200
        db.set_config(chave, time.time())

        pct = bonus_ativo()
        total = round(valor_pago + valor_pago * (pct / 100.0), 2)
        db.alterar_saldo(user_id, total)
        novo = db.obter_saldo(user_id)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
        extra = f" (+ {pct:.0f}% de bônus)" if pct > 0 else ""
        try:
            bot.send_message(
                user_id,
                f"✅ **Pagamento aprovado via Mercado Pago!**\n\n"
                f"💵 Recarga de R$ {valor_pago:.2f}{extra} creditada.\n"
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
# CALLBACKS — um handler por grupo, sem func=lambda call: True
# --------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: c.data == "verificar_inscricao")
def cb_verificar(call):
    if verificar_inscricao_canal(call.from_user.id):
        responder(call, "✅ Verificado!")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        enviar_menu(call.message.chat.id, call.from_user.id)
    else:
        responder(call, "⚠️ Você ainda não entrou no canal!")


@bot.callback_query_handler(func=lambda c: c.data == "voltar_menu")
def cb_voltar(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    enviar_menu(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data in ("perfil", "suporte", "info_gift", "historico_compras"))
def cb_estatico(call):
    uid, data = call.from_user.id, call.data

    if data == "perfil":
        responder(call, None, alerta=False)
        bot.send_message(call.message.chat.id,
                         f"👤 **Painel de Perfil**\n\n• ID: `{uid}`\n• Saldo: `R$ {db.obter_saldo(uid):.2f}`",
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

    elif data == "info_gift":
        responder(call, None, alerta=False)
        editar_ou_enviar(call,
                         "🎁 Para resgatar saldo, envie:\n`/resgatar GIFT-XXXXXXXX`",
                         types.InlineKeyboardMarkup(row_width=1).add(
                             types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")))

    elif data == "historico_compras":
        responder(call, None, alerta=False)
        itens = db.obter_historico_compras(uid)
        if not itens:
            bot.send_message(call.message.chat.id, "📦 Você ainda não realizou compras.")
            return
        linhas = ["📦 **HISTÓRICO DE COMPRAS**\n"]
        for it in itens[-10:][::-1]:
            linhas.append(f"💳 `{sanitizar(str(it.get('conteudo')))}`\n"
                          f"👤 `{sanitizar(str(it.get('titular', 'N/A')))}`\n"
                          f"🏷️ BIN `{it.get('bin')}` • R$ {float(it.get('preco', 0)):.2f}\n"
                          f"────────────────────")
        bot.send_message(call.message.chat.id, "\n".join(linhas), parse_mode="Markdown")


@bot.callback_query_handler(func=lambda c: c.data == "menu_gg")
def cb_menu_gg(call):
    responder(call, None, alerta=False)
    bins = db.contar_por_bin("gg")
    if not bins:
        responder(call, "⚠️ Nenhuma GG disponível em estoque no momento!")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in sorted(bins):
        markup.add(types.InlineKeyboardButton(
            f"🃏 BIN {b} • {bins[b]} disp. • R$ {db.obter_preco_bin(b):.2f}",
            callback_data=f"comprar_gg::{b}"))
    markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
    editar_ou_enviar(call, "💳 **ESCOLHA A BIN / CARTÃO DESEJADO:**", markup)


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("comprar_gg::"))
def cb_comprar_gg(call):
    bin_escolhida = call.data.split("::", 1)[1]          # split com maxsplit: nao quebra
    preco = db.obter_preco_bin(bin_escolhida)
    res = db.realizar_compra_item_casado(call.from_user.id, "gg", preco, bin_v=bin_escolhida)

    if res["status"] == "saldo_insuficiente":
        responder(call, f"❌ Saldo insuficiente.\nVocê tem R$ {res['saldo']:.2f} e a BIN custa R$ {preco:.2f}.")
        return
    if res["status"] == "esgotado":
        responder(call, f"❌ Estoque esgotado para a BIN {bin_escolhida}.")
        return

    cc, mes, ano, cvv = (res["conteudo"].split("|") + ["N/A"] * 4)[:4]
    titular = sanitizar(str(res.get("titular", "N/A")))
    prazo = (datetime.now() + timedelta(minutes=10)).strftime("%d/%m/%Y %H:%M:%S")

    msg = (
        "✅ **COMPRA EFETUADA!** ✅\n\n"
        f"💳 Cartão: `{cc}`\n"
        f"📆 Validade: `{mes}/{ano}`\n"
        f"🔐 CVV: `{cvv}`\n\n"
        f"🛍️ Formatado: `{sanitizar(res['conteudo'])}`\n\n"
        f"👤 **DADOS DO TITULAR**\n{titular}\n\n"
        f"💰 Saldo restante: `R$ {res['saldo']:.2f}`\n\n"
        f"⏰ Reembolso até {prazo} (10 min)"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🃏 Comprar outra GG", callback_data="menu_gg"),
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
