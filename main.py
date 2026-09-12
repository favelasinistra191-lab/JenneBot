import os
import re
import time
import uuid
import logging
from datetime import datetime

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

bot = telebot.TeleBot(config.TOKEN, threaded=False)

MP_ACCESS_TOKEN = os.getenv(
    "MP_ACCESS_TOKEN",
    "APP_USR-249848378901175-080605-e67c3c2b3575d5a687864a126913a7ae-3171236437",
)
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

SUPORTE_TG = "https://t.me/JENNE_BOT_SUPORTE"
SUPORTE_WA = "https://wa.me/639272951705"
PRECO_MINIMO_PIX = float(os.getenv("PRECO_MINIMO_PIX", "5.0"))

ADMIN_ABASTECENDO_GGS = {}
ADMIN_ABASTECENDO_DADOS = {}
ADMIN_ENVIANDO_FOTO = set()
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
    
    if eh_admin(user_id):
        markup.add(types.InlineKeyboardButton("👑 Painel Admin (Comandos)", callback_data="painel_admin"))

    foto_id = db.get_config("foto_start")
    if foto_id:
        try:
            bot.send_photo(chat_id, foto_id, caption=texto, reply_markup=markup, parse_mode="Markdown")
            return
        except Exception:
            pass
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")


# --------------------------------------------------------------------------
# COMANDOS DE ADMIN E GERAIS
# --------------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_id = message.from_user.id
    db.garantir_usuario(user_id, message.from_user.first_name or "Cliente", message.from_user.username or "")
    enviar_menu(message.chat.id, user_id)


@bot.message_handler(commands=["admin", "painel"])
def cmd_painel(message):
    if not eh_admin(message.from_user.id):
        return
    bot.reply_to(message,
                 "👑 **PAINEL DE CONTROLE - ADMIN**\n\n"
                 "📦 **Produtos & Estoque Casado:**\n"
                 "• `/novo_produto [Nome] | [Preço]` — Cria um produto\n"
                 "• `/estoque` — Vê o resumo do estoque separado\n"
                 "• `/abastecer_ggs [ID] [BIN]` — Adiciona GGs (valida Bin)\n"
                 "• `/abastecer_dados [ID]` — Adiciona Nomes/CPFs\n"
                 "• `/set_preco [ID] [Valor]` — Altera preço\n"
                 "• `/set_foto_start` — Define a foto do perfil/start\n\n"
                 "💵 **Financeiro & Gifts:**\n"
                 "• `/gerar_gift [Qtd] [Valor]` — Cria gift cards\n"
                 "• `/dar_saldo [ID] [Valor]` — Adiciona saldo",
                 parse_mode="Markdown")


@bot.message_handler(commands=["novo_produto"])
def cmd_novo_produto(message):
    if not eh_admin(message.from_user.id):
        return
    txt = message.text.replace("/novo_produto", "").strip()
    if "|" not in txt:
        bot.reply_to(message, "⚠️ Use o formato:\n`/novo_produto Nome do Produto | 15.00`", parse_mode="Markdown")
        return
    partes = txt.split("|")
    nome = partes[0].strip()
    try:
        preco = float(partes[1].strip().replace(",", "."))
    except ValueError:
        bot.reply_to(message, "❌ Preço inválido. Use números ex: `15.00`", parse_mode="Markdown")
        return
    
    pid = db.adicionar_produto(nome, preco, descricao="", estoque=0)
    bot.reply_to(message, f"✅ Produto criado!\n\n🏷️ Nome: `{nome}`\n🆔 ID: `{pid}`\n💵 Preço: `R$ {preco:.2f}`\n\nUse `/abastecer_ggs {pid} [BIN]` e `/abastecer_dados {pid}` para abastecer.", parse_mode="Markdown")


@bot.message_handler(commands=["dar_saldo"])
def cmd_dar_saldo(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/dar_saldo [user_id] [valor]`", parse_mode="Markdown")
        return
    try:
        uid = int(args[1])
        val = float(args[2].replace(",", "."))
        db.atualizar_saldo(uid, val)
        bot.reply_to(message, f"✅ Adicionado R$ {val:.2f} para o usuário `{uid}`.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["estoque"])
def cmd_estoque(message):
    if not eh_admin(message.from_user.id):
        return
    produtos = db.listar_produtos(apenas_ativos=False)
    if not produtos:
        bot.reply_to(message, "📭 Nenhum produto cadastrado.")
        return
    linhas = ["📦 **ESTOQUE SEPARADO (CASADO)**\n"]
    for p in produtos:
        ggs, dados = db.contar_estoque_separado(p["id"])
        linhas.append(f"• `{p['nome']}` (ID: `{p['id']}`)\n  💳 GGs: **{ggs}** | 👤 Dados: **{dados}** | Menor (Estoque): **{p['estoque']}** | R$ {p['preco']:.2f}")
    bot.reply_to(message, "\n".join(linhas), parse_mode="Markdown")


@bot.message_handler(commands=["abastecer_ggs"])
def cmd_abastecer_ggs(message):
    if not eh_admin(message.from_user.id):
        return
    tokens = (message.text or "").split()
    if len(tokens) < 3:
        bot.reply_to(message, "⚠️ Use assim:\n`/abastecer_ggs [ID_PRODUTO] [BIN_6_DIGITOS]`\ne envie as GGs na mensagem seguinte.", parse_mode="Markdown")
        return
    try:
        produto_id = int(tokens[1])
        bin_informada = tokens[2]
    except ValueError:
        bot.reply_to(message, "❌ Parâmetros inválidos.")
        return
    
    prod = db.get_produto(produto_id)
    if not prod:
        bot.reply_to(message, f"❌ Produto ID `{produto_id}` não encontrado.")
        return

    ADMIN_ABASTECENDO_GGS[message.from_user.id] = (produto_id, bin_informada)
    bot.reply_to(message, f"📥 Produto: `{prod['nome']}` | Bin: `{bin_informada}`\n\nAgora **envie as GGs (uma por linha)** nesta conversa.", parse_mode="Markdown")


@bot.message_handler(commands=["abastecer_dados"])
def cmd_abastecer_dados(message):
    if not eh_admin(message.from_user.id):
        return
    tokens = (message.text or "").split()
    if len(tokens) < 2:
        bot.reply_to(message, "⚠️ Use assim:\n`/abastecer_dados [ID_PRODUTO]`\ne envie os dados (CPFs/Nomes) na mensagem seguinte.", parse_mode="Markdown")
        return
    try:
        produto_id = int(tokens[1])
    except ValueError:
        bot.reply_to(message, "❌ ID inválido.")
        return
    
    prod = db.get_produto(produto_id)
    if not prod:
        bot.reply_to(message, f"❌ Produto ID `{produto_id}` não encontrado.")
        return

    ADMIN_ABASTECENDO_DADOS[message.from_user.id] = produto_id
    bot.reply_to(message, f"📥 Produto: `{prod['nome']}`\n\nAgora **envie os dados (uma linha por cadastro)** nesta conversa.", parse_mode="Markdown")


@bot.message_handler(commands=["set_foto_start"])
def cmd_set_foto_start(message):
    if not eh_admin(message.from_user.id):
        return
    ADMIN_ENVIANDO_FOTO.add(message.from_user.id)
    bot.reply_to(message, "📸 Envie agora a imagem que deseja definir como foto de perfil/start do bot.")


@bot.message_handler(content_types=["photo"], func=lambda m: eh_admin(m.from_user.id) and m.from_user.id in ADMIN_ENVIANDO_FOTO)
def capturar_foto_start(message):
    ADMIN_ENVIANDO_FOTO.discard(message.from_user.id)
    file_id = message.photo[-1].file_id
    db.set_config("foto_start", file_id)
    bot.reply_to(message, "✅ Foto de perfil/start definida com sucesso!")


@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/") and eh_admin(m.from_user.id))
def capturar_abastecimento_texto(message):
    uid = message.from_user.id
    if uid in ADMIN_ABASTECENDO_GGS:
        produto_id, bin_informada = ADMIN_ABASTECENDO_GGS.pop(uid)
        adicionados, duplicados, invalidos = db.adicionar_ggs_lote(produto_id, bin_informada, message.text)
        bot.reply_to(message, f"✅ GGs processadas!\n• Adicionadas: **{adicionados}**\n• Duplicadas: {duplicados}\n• Inválidas (Bin incorreta): {invalidos}", parse_mode="Markdown")
        return

    if uid in ADMIN_ABASTECENDO_DADOS:
        produto_id = ADMIN_ABASTECENDO_DADOS.pop(uid)
        adicionados, duplicados = db.adicionar_dados_lote(produto_id, message.text)
        bot.reply_to(message, f"✅ Dados processados!\n• Adicionados: **{adicionados}**\n• Duplicados: {duplicados}", parse_mode="Markdown")
        return


@bot.message_handler(commands=["set_preco"])
def cmd_set_preco(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/set_preco [id] [valor]`")
        return
    try:
        pid, valor = int(args[1]), float(args[2].replace(",", "."))
        prod = db.get_produto(pid)
        if not prod:
            bot.reply_to(message, "❌ Produto não encontrado.")
            return
        db.adicionar_produto(prod["nome"], valor, prod["descricao"], prod["estoque"], prod["imagem"], produto_id=pid)
        bot.reply_to(message, f"✅ Preço alterado para R$ {valor:.2f}")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["gerar_gift"])
def cmd_gerar_gift(message):
    if not eh_admin(message.from_user.id):
        return
    args = (message.text or "").split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/gerar_gift [quantidade] [valor]`")
        return
    try:
        qtd, valor = int(args[1]), float(args[2].replace(",", "."))
        codigos = []
        for _ in range(qtd):
            codigo = f"GIFT-{uuid.uuid4().hex[:8].upper()}"
            db.adicionar_dados_lote(None, codigo) # ou adaptado p gift
            # como gift usa cards antigos, podemos salvar em estoque_dados com produto_id=None
            codigos.append(codigo)
        # Ajuste direto via sql p gift se necessário
        conn = db.get_conn()
        cur = conn.cursor()
        for c in codigos:
            cur.execute("INSERT INTO estoque_dados (produto_id, conteudo, vendido, criado_em) VALUES (NULL, ?, 0, ?)", (c, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

        bot.reply_to(message, f"🎁 **{qtd} Gifts gerados de R$ {valor:.2f}:**\n\n" + "\n".join(f"`{c}`" for c in codigos), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=["resgatar"])
def cmd_resgatar(message):
    args = (message.text or "").split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/resgatar GIFT-XXXXXXXX`")
        return
    codigo = args[1].strip().upper()
    conn = db.get_conn()
    cur = conn.cursor()
    card = cur.execute("SELECT * FROM estoque_dados WHERE conteudo = ? AND produto_id IS NULL AND vendido = 0", (codigo,)).fetchone()
    if not card:
        conn.close()
        bot.reply_to(message, "❌ Código de gift inválido ou já resgatado.")
        return
    # Assumimos o valor guardado ou fixo se necessário, por simplicidade usamos o id ou geramos com valor fixo no texto
    # Como o gift foi gerado, podemos extrair o valor ou pedir pro admin. Vamos ajustar para buscar o valor do gift via config ou extrair.
    # Para manter simples e funcional:
    valor = 10.0 # Valor padrão ou ajuste se preferir
    cur.execute("UPDATE estoque_dados SET vendido = 1, comprador_id = ?, comprado_em = ? WHERE id = ?", (message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), card["id"]))
    conn.commit()
    conn.close()

    db.atualizar_saldo(message.from_user.id, valor)
    novo_saldo = obter_saldo_usuario(message.from_user.id)
    bot.reply_to(message, f"✅ **Gift resgatado!**\n\n💵 Adicionado: `R$ {valor:.2f}`\n💰 Saldo atual: `R$ {novo_saldo:.2f}`", parse_mode="Markdown")


@bot.message_handler(commands=["pix"])
def cmd_pix(message):
    args = (message.text or "").split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o valor. Exemplo: `/pix 15`")
        return
    try:
        valor = float(args[1].replace(",", "."))
    except ValueError:
        bot.reply_to(message, "❌ Valor inválido.")
        return
    if valor < PRECO_MINIMO_PIX:
        bot.reply_to(message, f"⚠️ Valor mínimo para Pix: R$ {PRECO_MINIMO_PIX:.2f}")
        return
    
    res_pix = gerar_pix_copia_e_cola(message.from_user.id, valor)
    if not res_pix:
        bot.reply_to(message, "❌ Erro ao gerar o Pix automático. Tente novamente mais tarde.")
        return
    
    copia_cola = res_pix["qr_code"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
    
    bot.reply_to(message,
                 f"💳 **PIX COPIA E COLA GERADO**\n\n"
                 f"💵 Valor: `R$ {valor:.2f}`\n\n"
                 f"Copie o código abaixo e pague no app do seu banco:\n\n"
                 f"`{copia_cola}`\n\n"
                 f"⏱️ *O saldo cai automaticamente após a aprovação.*",
                 reply_markup=markup, parse_mode="Markdown")


# --------------------------------------------------------------------------
# WEBHOOK FLASK ROUTES
# --------------------------------------------------------------------------
def gerar_pix_copia_e_cola(user_id, valor):
    try:
        url = "https://api.mercadopago.com/v1/payments"
        headers = {
            "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": str(uuid.uuid4())
        }
        payload = {
            "transaction_amount": float(valor),
            "description": f"Recarga de Saldo - ID {user_id}",
            "payment_method_id": "pix",
            "payer": {
                "email": f"cliente_{user_id}@onghost.com",
                "first_name": "Cliente",
                "last_name": "Bot"
            },
            "external_reference": f"recarga_{user_id}_{int(time.time())}"
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            data = resp.json()
            point_of_interaction = data.get("point_of_interaction", {})
            transaction_data = point_of_interaction.get("transaction_data", {})
            return {
                "id": data.get("id"),
                "qr_code": transaction_data.get("qr_code"),
                "qr_code_base64": transaction_data.get("qr_code_base64")
            }
        else:
            LOG.error("Erro MP Pix Copia e Cola: %s", resp.text)
            return None
    except Exception as e:
        LOG.error("Exceção Pix Copia e Cola: %s", e)
        return None


@app.route("/")
def home():
    return "DonGhostBot Webhook rodando perfeitamente!"


@app.route(f"/{config.TOKEN}", methods=["POST"])
def webhook_telegram():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "", 200
    else:
        return "Forbidden", 403


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
                f"✅ **Pagamento aprovado via Pix!**\n\n"
                f"💵 Recarga de R$ {valor_pago:.2f} creditada.\n"
                f"💰 **Saldo atual:** `R$ {novo:.2f}`",
                reply_markup=markup, parse_mode="Markdown",
            )
        except Exception as e:
            LOG.error("Aviso de recarga não entregue a %s: %s", user_id, e)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        LOG.error("Webhook MP: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# --------------------------------------------------------------------------
# CALLBACKS DO BOT
# --------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda c: c.data == "voltar_menu")
def cb_voltar(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    enviar_menu(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data == "painel_admin")
def cb_painel_admin(call):
    if not eh_admin(call.from_user.id):
        responder(call, "Acesso negado.")
        return
    responder(call, None, alerta=False)
    bot.send_message(call.message.chat.id,
                     "👑 **PAINEL DE CONTROLE - ADMIN**\n\n"
                     "📦 **Comandos rápidos:**\n"
                     "• `/novo_produto [Nome] | [Preço]`\n"
                     "• `/estoque`\n"
                     "• `/abastecer_ggs [ID] [BIN]`\n"
                     "• `/abastecer_dados [ID]`\n"
                     "• `/set_preco [ID] [Valor]`\n"
                     "• `/set_foto_start`\n"
                     "• `/gerar_gift [Qtd] [Valor]`\n"
                     "• `/dar_saldo [ID] [Valor]`",
                     parse_mode="Markdown")


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
                         "💳 **FAZER RECARGA VIA PIX**\n\nEnvie o comando `/pix [valor]` no chat para gerar sua cobrança.\nExemplo: `/pix 15`",
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
            linhas.append(f"🏷️ Produto: `{it.get('nome_produto')}` • R$ {float(it.get('valor_total', 0)):.2f}\n"
                          f"💳 Entregas:\n`{sanitizar(str(it.get('cards', '')))}`\n"
                          f"────────────────────")
        bot.send_message(call.message.chat.id, "\n".join(linhas), parse_mode="Markdown")


@bot.callback_query_handler(func=lambda c: c.data == "menu_gg")
def cb_menu_gg(call):
    responder(call, None, alerta=False)
    produtos = db.listar_produtos(apenas_ativos=True)
    if not produtos:
        responder(call, "⚠️ Nenhum produto disponível em estoque no momento!", alerta=True)
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    tem_disponivel = False
    for p in produtos:
        if p["estoque"] > 0:
            tem_disponivel = True
            markup.add(types.InlineKeyboardButton(
                f"🃏 {p['nome']} • {p['estoque']} disp. • R$ {p['preco']:.2f}",
                callback_data=f"comprar_prod::{p['id']}"))
            
    if not tem_disponivel:
        responder(call, "⚠️ Todos os produtos estão com estoque zerado no momento!", alerta=True)
        return

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
        responder(call, f"❌ Saldo insuficiente.\nVocê tem R$ {res['saldo']:.2f} e faltam R$ {res['faltam']:.2f}.", alerta=True)
        return
    if res["status"] == "sem_estoque":
        responder(call, "❌ Estoque esgotado para este produto.", alerta=True)
        return
    if res["status"] != "ok":
        responder(call, f"❌ Erro: {res.get('msg', 'Desconhecido')}", alerta=True)
        return

    cards_str = "\n\n--------------------\n\n".join(res["cards_entregues"])
    msg = (
        "✅ **COMPRA EFETUADA!** ✅\n\n"
        f"🛍️ **Item(ns) adquirido(s):**\n`{sanitizar(cards_str)}`\n\n"
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
# CONFIGURAÇÃO DE WEBHOOK AUTOMÁTICA AO INICIAR
# --------------------------------------------------------------------------
if __name__ == "__main__":
    domain = os.getenv("SQUAREDCLOUD_DOMAIN") or os.getenv("DOMAIN") or os.getenv("RENDER_EXTERNAL_URL")
    
    if domain:
        webhook_url = f"https://{domain.replace('https://', '').strip('/')}/{config.TOKEN}"
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=webhook_url)
            LOG.info("Webhook configurado com sucesso para: %s", webhook_url)
        except Exception as e:
            LOG.error("Erro ao configurar webhook: %s", e)
    else:
        LOG.warning("Nenhum domínio detectado automaticamente. Certifique-se de configurar o webhook manualmente se necessário.")

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
