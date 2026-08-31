"""
Arquivo Principal - Don Ghost Bot (Versão Mercado Pago)
Versão Profissional Completa • Banner Dinâmico + GGs Casados + Pix Mercado Pago + Lote Gifts + Gestão de Preço por BIN
"""
import os
import logging
import threading
import uuid
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot import types
import requests

import config
import database as db

# Configurações Mercado Pago (Token Oficial)
MP_ACCESS_TOKEN = "APP_USR-249848378901175-080605-e67c3c2b3575d5a687864a126913a7ae-3171236437"

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("DonGhostBot")

bot = telebot.TeleBot(config.TOKEN, threaded=True)
db.criar_tabelas()

app = Flask(__name__)

CANAL_OBRIGATORIO = "https://t.me/+VNkIZojSrHs4NDJh"

@app.route('/')
def home():
    return "DonGhostBot com Mercado Pago está rodando perfeitamente!"

@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    try:
        dados_notificacao = request.json or request.args
        if not dados_notificacao:
            return jsonify({"status": "error"}), 400

        tipo_evento = dados_notificacao.get("type") or dados_notificacao.get("topic")
        
        payment_id = None
        if tipo_evento == "payment":
            payment_id = dados_notificacao.get("data", {}).get("id")
        elif "id" in dados_notificacao:
            payment_id = dados_notificacao.get("id")

        if payment_id:
            headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
            resp = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers, timeout=10)
            
            if resp.status_code == 200:
                p_data = resp.json()
                status_pagamento = p_data.get("status")
                external_ref = p_data.get("external_reference")
                valor_pago = float(p_data.get("transaction_amount", 0.0))

                if status_pagamento == "approved":
                    if external_ref and "recarga_" in str(external_ref):
                        partes = str(external_ref).split("_")
                        if len(partes) >= 2:
                            user_id = int(partes[1])
                            
                            if valor_pago > 0:
                                dados = db.carregar_dados(forcar_atualizacao=True)
                                config_promocao = dados.get("configuracoes", {})
                                
                                porcentagem_bonus = float(config_promocao.get("bonus_porcentagem", 100.0))
                                expira_em = config_promocao.get("bonus_expira_em")
                                
                                if expira_em and time.time() > expira_em:
                                    porcentagem_bonus = 0.0

                                valor_bonus = valor_pago * (porcentagem_bonus / 100.0)
                                valor_total = valor_pago + valor_bonus
                                
                                usuarios = dados.get("usuarios", [])
                                usuario_encontrado = None
                                for u in usuarios:
                                    if u["user_id"] == user_id:
                                        usuario_encontrado = u
                                        break

                                if usuario_encontrado:
                                    usuario_encontrado["saldo"] = float(usuario_encontrado.get("saldo", 0.0)) + valor_total
                                    
                                    indicado_por = usuario_encontrado.get("indicado_por")
                                    if indicado_por and not usuario_encontrado.get("indicacao_paga", False):
                                        usuario_encontrado["indicacao_paga"] = True
                                        for u_ind in usuarios:
                                            if u_ind["user_id"] == indicado_por:
                                                u_ind["saldo"] = float(u_ind.get("saldo", 0.0)) + 20.0
                                                break

                                    db.salvar_dados(dados)
                                    novo_saldo = usuario_encontrado["saldo"]
                                    
                                    markup = types.InlineKeyboardMarkup()
                                    markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
                                    
                                    try:
                                        msg_bonus_texto = f" (+ {porcentagem_bonus:.0f}% de Bônus)" if porcentagem_bonus > 0 else ""
                                        bot.send_message(
                                            user_id,
                                            f"✅ **Pagamento Aprovado via Mercado Pago!**\n\n"
                                            f"💵 Recarga de R$ {valor_pago:.2f}{msg_bonus_texto} adicionada com sucesso!\n"
                                            f"💰 **Saldo Atual:** `R$ {novo_saldo:.2f}`",
                                            reply_markup=markup,
                                            parse_mode="Markdown"
                                        )
                                    except Exception as e:
                                        LOG.error(f"Erro Pix MP: {e}")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def verificar_inscricao_canal(user_id):
    try:
        chat_member = bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        return True 
    return False

def consultar_bin(bin6):
    bin6 = ''.join(filter(str.isdigit, str(bin6)))[:6]
    if len(bin6) < 6:
        return "OUTRA", "BANCO DESCONHECIDO"
    
    primeiro_digito = bin6[0]
    if primeiro_digito == '4':
        bandeira = "VISA"
    elif bin6.startswith(('51','52','53','54','55')) or (2221 <= int(bin6[:4]) <= 2720):
        bandeira = "MASTERCARD"
    elif bin6.startswith(('34', '37')):
        bandeira = "AMERICAN EXPRESS"
    elif bin6.startswith('6011') or bin6.startswith('65'):
        bandeira = "DISCOVER"
    else:
        bandeira = "OUTRA"

    banco = "BANCO DO BRASIL / GERAL"
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=2, headers={'Accept-Version': '3'})
        if response.status_code == 200:
            data = response.json()
            b = data.get("bank", {}).get("name")
            if b:
                banco = b.upper()
    except Exception:
        pass
    return bandeira, banco

def main_menu(user_id):
    db.garantir_usuario(user_id, "", "")
    saldo = db.obter_saldo(user_id)
    bot_username = bot.get_me().username
    link_indicacao = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = (
        f"💎 **BEM-VINDO AO BOT DON GHOST • PREMIUM SHOP** 💎\n"
        f"───────────────────────────────\n"
        f"👤 **ID de Acesso:** `{user_id}`\n"
        f"💰 **Saldo em Conta:** `R$ {saldo:.2f}`\n"
        f"───────────────────────────────\n"
        f"🔥 *As melhores notícias do mercado, GGs de alta qualidade e aprovação expressa.*\n\n"
        f"🔗 **Seu Link de Indicação:**\n`{link_indicacao}`\n"
        f"💡 *Indique amigos: Você ganha R$ 20,00 de bônus assim que o amigo convidado fizer o primeiro depósito!*"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💳 Comprar GGs", callback_data="menu_gg"),
        types.InlineKeyboardButton("💳 Fazer Recarga Pix", callback_data="menu_recarga"),
        types.InlineKeyboardButton("👤 Meu Perfil", callback_data="perfil"),
        types.InlineKeyboardButton("📦 Minhas Compras", callback_data="historico_compras"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="info_gift"),
        types.InlineKeyboardButton("🤝 Indique e Ganhe", callback_data="info_indicar"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte")
    )
    return text, markup

@bot.message_handler(content_types=['photo'])
def capturar_novo_banner(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    if not message.caption or "/mudar_banner" not in message.caption:
        return

    file_id = message.photo[-1].file_id
    dados = db.carregar_dados(forcar_atualizacao=True)
    if "configuracoes" not in dados:
        dados["configuracoes"] = {}
    dados["configuracoes"]["banner_file_id"] = file_id
    db.salvar_dados(dados)
    
    bot.reply_to(message, "✅ **Banner atualizado com sucesso!**", parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        user_id = message.from_user.id
        primeiro_nome = message.from_user.first_name or "Cliente"
        username = message.from_user.username or ""
        
        if not verificar_inscricao_canal(user_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📢 Entrar no Canal Oficial", url=CANAL_OBRIGATORIO),
                types.InlineKeyboardButton("🔄 Já Entrei / Verificar", callback_data="verificar_inscricao")
            )
            bot.send_message(message.chat.id, "⚠️ **Acesso Restrito!**\n\nPara utilizar o bot, entre no canal oficial primeiro.", reply_markup=markup, parse_mode="Markdown")
            return

        args = message.text.split()
        indicado_por = None
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                indicado_por = int(args[1].replace("ref_", ""))
            except ValueError:
                pass

        db.garantir_usuario(user_id, primeiro_nome, username, indicado_por=indicado_por)
        text, markup = main_menu(user_id)
        
        dados = db.carregar_dados()
        banner_file_id = dados.get("configuracoes", {}).get("banner_file_id")
        
        if banner_file_id:
            try:
                bot.send_photo(message.chat.id, photo=banner_file_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        LOG.error(f"Erro no start: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "verificar_inscricao")
def callback_verificar_inscricao(call):
    user_id = call.from_user.id
    if verificar_inscricao_canal(user_id):
        bot.answer_callback_query(call.id, "✅ Verificado com sucesso!", show_alert=True)
        text, markup = main_menu(user_id)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
            
        dados = db.carregar_dados()
        banner_file_id = dados.get("configuracoes", {}).get("banner_file_id")
        if banner_file_id:
            try:
                bot.send_photo(call.message.chat.id, photo=banner_file_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "⚠️ Você ainda não entrou no canal!", show_alert=True)

@bot.message_handler(commands=['admin', 'painel'])
def cmd_admin(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    total_vendas, faturamento, clientes = db.obter_dados_relatorio()
    dados = db.carregar_dados()
    cfg = dados.get("configuracoes", {})
    p_bonus = cfg.get("bonus_porcentagem", 100.0)
    
    texto = (
        f"👑 **Painel Administrativo • Don Ghost**\n\n"
        f"📊 Clientes: `{clientes}` | Vendas: `{total_vendas}` | Faturamento: `R$ {faturamento:.2f}`\n"
        f"⚡ Bônus Atual Ativo: `{p_bonus:.0f}%`\n\n"
        f"⚙️ **Comandos úteis de Admin:**\n"
        f"• `/abastecer [bin]` - Adicionar GGs em lote\n"
        f"• `/set_preco [bin] [valor]` - Definir preço de uma BIN\n"
        f"• `/set_bonus [porcentagem] [dias]` - Configurar bônus\n"
        f"• `/add_dados` - Adicionar dados do titular\n"
        f"• `/gerar_gift [qtd] [valor]` - Gerar gifts\n"
        f"• `/limpar_estoque` - Limpar vendidos"
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")

@bot.message_handler(commands=['set_bonus'])
def cmd_set_bonus(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Uso correto: `/set_bonus [porcentagem] [dias]`", parse_mode="Markdown")
        return
    try:
        porcentagem = float(args[1].replace(',', '.'))
        dias = float(args[2].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Valores inválidos.", parse_mode="Markdown")
        return
    
    expira_em = time.time() + (dias * 86400)
    dados = db.carregar_dados(forcar_atualizacao=True)
    if "configuracoes" not in dados:
        dados["configuracoes"] = {}
    dados["configuracoes"]["bonus_porcentagem"] = porcentagem
    dados["configuracoes"]["bonus_expira_em"] = expira_em
    db.salvar_dados(dados)
    bot.reply_to(message, f"✅ **Promoção Configurada!** Bônus: `{porcentagem:.0f}%` por `{dias} dia(s)`", parse_mode="Markdown")

@bot.message_handler(commands=['set_preco'])
def cmd_set_preco(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Uso correto: `/set_preco [bin] [valor]`\n*Ex:* `/set_preco 422061 3.0`", parse_mode="Markdown")
        return
    try:
        bin_code = "".join(filter(str.isdigit, args[1]))[:6]
        preco = float(args[2].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Valores inválidos.", parse_mode="Markdown")
        return
    
    db.definir_preco_bin(bin_code, preco)
    bot.reply_to(message, f"✅ **Preço atualizado!** BIN `{bin_code}` agora custa `R$ {preco:.2f}`.", parse_mode="Markdown")

@bot.message_handler(commands=['abastecer'])
def cmd_abastecer_etapa1(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.replace('/abastecer', '').strip()
    bin6 = "".join(filter(str.isdigit, args))[:6]
    if len(bin6) < 6:
        bot.reply_to(message, "⚠️ Use o formato: `/abastecer 422061`", parse_mode="Markdown")
        return
    bandeira, banco = consultar_bin(bin6)
    dados = db.carregar_dados()
    dados["admin_pendente"] = {"admin_id": message.from_user.id, "tipo": "gg", "bin": bin6, "banco": banco, "bandeira": bandeira}
    db.salvar_dados(dados)
    bot.reply_to(message, f"🔍 **BIN Registrada!**\n💳 **BIN:** `{bin6}` | **Bandeira:** `{bandeira}`\n👇 **Mande a lista completa das GGs.**", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.from_user.id == config.ADMIN_ID and not message.text.startswith('/'))
def processar_etapa2(message):
    dados = db.carregar_dados()
    pendente = dados.get("admin_pendente")
    if not pendente or pendente.get("admin_id") != message.from_user.id:
        return

    dados["admin_pendente"] = {}
    db.salvar_dados(dados)
    tipo = pendente.get("tipo")
    texto_bruto = message.text.strip()
    linhas = texto_bruto.replace('\r\n', '\n').split('\n')
    
    if tipo == "gg":
        bin6 = pendente["bin"]
        banco = pendente["banco"]
        bandeira = pendente["bandeira"]
        cartoes = []
        for linha in linhas:
            linha = linha.strip()
            if not linha: continue
            for parte in linha.split():
                if '|' in parte: cartoes.append(parte.strip())
        if not cartoes:
            for linha in linhas:
                if len(linha.strip()) > 10: cartoes.append(linha.strip())
        if not cartoes:
            bot.reply_to(message, "❌ Nenhum cartão encontrado.")
            return

        db.adicionar_lote_estoque(cartoes, categoria='gg', bin=bin6, banco=banco, bandeira=bandeira)
        msg_sucesso = f"✅ **Estoque Atualizado!** Adicionadas `{len(cartoes)} GGs` para a BIN `{bin6}`!"
        bot.reply_to(message, msg_sucesso, parse_mode="Markdown")

@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID: return
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo: return
    linhas = [l.strip() for l in texto_completo.replace('\r\n', '\n').split('\n') if l.strip()]
    if not linhas: return
    db.adicionar_lote_dados_titular(linhas)
    bot.reply_to(message, f"✅ Cadastrados `{len(linhas)}` titulares.", parse_mode="Markdown")

@bot.message_handler(commands=['limpar_estoque'])
def cmd_limpar_estoque(message):
    if message.from_user.id != config.ADMIN_ID: return
    try:
        dados = db.carregar_dados(forcar_atualizacao=True)
        dados["estoque"] = [e for e in dados.get("estoque", []) if e.get("vendido") == 1]
        dados["dados_titular"] = [t for t in dados.get("dados_titular", []) if t.get("usado") == 1]
        db.salvar_dados(dados)
        bot.reply_to(message, "🧹 **Estoque limpo com sucesso!**", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

@bot.message_handler(commands=['gerar_gift'])
def cmd_gerar_gift(message):
    if message.from_user.id != config.ADMIN_ID: return
    args = message.text.split()
    if len(args) < 3: return
    try:
        quantidade = int(args[1])
        valor = float(args[2].replace(',', '.'))
    except ValueError:
        return
    
    dados = db.carregar_dados(forcar_atualizacao=True)
    if "gift_cards" not in dados: dados["gift_cards"] = []
    lista_gerados = f"🎁 **Gifts Gerados ({quantidade}x - R$ {valor:.2f})**\n\n"
    for _ in range(quantidade):
        codigo_gift = f"GIFT-{uuid.uuid4().hex[:8].upper()}"
        dados["gift_cards"].append({"codigo": codigo_gift, "valor": valor, "usado": 0})
        lista_gerados += f"🔑 `R$ {valor:.2f}`: `{codigo_gift}`\n"
    db.salvar_dados(dados)
    bot.reply_to(message, lista_gerados, parse_mode="Markdown")

@bot.message_handler(commands=['resgatar'])
def cmd_resgatar(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2: return
    codigo = args[1].strip()
    try:
        dados = db.carregar_dados(forcar_atualizacao=True)
        gift_encontrado = next((g for g in dados.get("gift_cards", []) if g.get("codigo") == codigo), None)
        if not gift_encontrado or gift_encontrado.get("usado") == 1:
            bot.reply_to(message, "❌ Gift inválido ou já utilizado.")
            return
        valor = gift_encontrado.get("valor")
        gift_encontrado["usado"] = 1
        
        usuario_encontrado = next((u for u in dados.get("usuarios", []) if u["user_id"] == user_id), None)
        if usuario_encontrado:
            usuario_encontrado["saldo"] = usuario_encontrado.get("saldo", 0.0) + valor
        else:
            dados["usuarios"].append({"user_id": user_id, "nome": message.from_user.first_name, "username": message.from_user.username, "saldo": valor})
        db.salvar_dados(dados)
        bot.reply_to(message, f"🎉 **Resgate Efetuado!** Adicionado R$ {valor:.2f} ao seu saldo.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

@bot.message_handler(commands=['pix'])
def cmd_pix_customizado(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o valor. Exemplo: `/pix 15` (Mínimo R$ 10,00)", parse_mode="Markdown")
        return
    try:
        valor = float(args[1].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Valor inválido.", parse_mode="Markdown")
        return
    if valor < 10.0:
        bot.reply_to(message, "⚠️ O valor mínimo para recarga via Pix é de **R$ 10,00**.", parse_mode="Markdown")
        return

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    external_ref = f"recarga_{user_id}_{uuid.uuid4().hex[:6]}"
    payload = {
        "transaction_amount": valor,
        "description": f"Recarga Saldo Bot #{user_id}",
        "payment_method_id": "pix",
        "payer": {
            "email": f"cliente_{user_id}@donghost.com",
            "first_name": message.from_user.first_name or "Cliente",
            "last_name": "Telegram"
        },
        "external_reference": external_ref
    }

    try:
        response = requests.post("https://api.mercadopago.com/v1/payments", json=payload, headers=headers, timeout=15)
        if response.status_code in [200, 201]:
            dados_resposta = response.json()
            point_of_interaction = dados_resposta.get("point_of_interaction", {})
            qr_data = point_of_interaction.get("transaction_data", {}).get("qr_code")
            
            if qr_data:
                mensagem_pix = f"💳 **PAGAMENTO PIX (MERCADO PAGO)**\n\n💵 **Valor:** `R$ {valor:.2f}`\n\n📋 **PIX COPIA E COLA:**\n`{qr_data}`\n\n*Pague no aplicativo do seu banco. Assim que o pagamento for aprovado, o saldo cairá automaticamente.*"
                bot.send_message(message.chat.id, mensagem_pix, parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ Erro ao gerar o código QR do Pix.")
        else:
            LOG.error(f"Erro MP API: {response.text}")
            bot.send_message(message.chat.id, "❌ Erro ao se conectar com o Mercado Pago.")
    except Exception as e:
        LOG.error(f"Exceção Pix MP: {e}")
        bot.send_message(message.chat.id, "❌ Erro de conexão ao gerar pagamento.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data
    
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    
    if data == "perfil":
        saldo = db.obter_saldo(user_id)
        bot.send_message(call.message.chat.id, f"👤 **Painel de Perfil**\n\n• ID: `{user_id}`\n• Saldo: `R$ {saldo:.2f}`", parse_mode="Markdown")
        
    elif data == "suporte":
        markup_sup = types.InlineKeyboardMarkup(row_width=1)
        markup_sup.add(
            types.InlineKeyboardButton("💬 Suporte Telegram", url="https://t.me/JENNE_BOT_SUPORTE"),
            types.InlineKeyboardButton("💬 Suporte WhatsApp", url="https://wa.me/639272951705"),
            types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")
        )
        try:
            bot.edit_message_text(text="📞 **CENTRAL DE SUPORTE OFICIAL**", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup_sup, parse_mode="Markdown")
        except:
            bot.send_message(call.message.chat.id, "📞 **CENTRAL DE SUPORTE OFICIAL**", reply_markup=markup_sup, parse_mode="Markdown")
        
    elif data == "info_gift":
        bot.send_message(call.message.chat.id, "🎁 Para resgatar saldo, envie:\n`/resgatar [codigo]`", parse_mode="Markdown")

    elif data == "info_indicar":
        bot_username = bot.get_me().username
        link_indicacao = f"https://t.me/{bot_username}?start=ref_{user_id}"
        bot.send_message(call.message.chat.id, f"🤝 **INDICAÇÃO E GANHE • R$ 20,00**\n\nConvide amigos usando seu link:\n`{link_indicacao}`", parse_mode="Markdown")

    elif data == "historico_compras":
        historico = db.obter_historico_compras(user_id)
        if not historico:
            bot.send_message(call.message.chat.id, "📦 Você ainda não realizou compras.", parse_mode="Markdown")
            return
        texto_hist = "📦 **HISTÓRICO DE COMPRAS (GGs)**\n───────────────────────────────\n"
        for item in historico[-10:]:
            texto_hist += f"💳 `{item['conteudo']}`\n🏦 `{item['banco']} / {item['bandeira']}`\n───────────────────────────────\n"
        bot.send_message(call.message.chat.id, texto_hist, parse_mode="Markdown")
        
    elif data == "menu_recarga":
        msg_recarga = f"💳 **RECARGA PIX**\n\n⚡ Pagamento automatizado via Mercado Pago.\n\n✍️ **Envie no chat:**\n`/pix [valor]`\n💡 *Ex:* `/pix 15`"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        try:
            bot.edit_message_text(text=msg_recarga, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(call.message.chat.id, msg_recarga, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_gg":
        ggs = db.listar_estoque_gg_agrupado()
        if not ggs:
            bot.send_message(call.message.chat.id, "❌ Sem GGs disponíveis no momento.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for bin_code, bandeira, total_qtd, preco_bin in ggs:
            markup.add(types.InlineKeyboardButton(f"💳 {bandeira} ({bin_code}) • Estoque: {total_qtd} (R$ {preco_bin:.2f})", callback_data=f"comprar_gg_{bin_code}"))
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **SELECIONE A BIN:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        preco_bin = db.obter_preco_bin(bin_escolhida)
        
        status, res_gg, res_dados, banco_item, bandeira_item, bin_item = db.realizar_compra_item_casado(user_id, 'gg', preco_bin, bin_v=bin_escolhida)
        
        if status == "ok":
            partes_cartao = res_gg.split('|')
            num_cc = partes_cartao[0] if len(partes_cartao) > 0 else "N/A"
            mes_cc = partes_cartao[1] if len(partes_cartao) > 1 else "12"
            ano_cc = partes_cartao[2] if len(partes_cartao) > 2 else "2032"
            cvv_cc = partes_cartao[3] if len(partes_cartao) > 3 else "209"

            partes_dados = res_dados.split('|')
            nome_titular = partes_dados[0] if len(partes_dados) > 0 else res_dados
            cpf_titular = partes_dados[1] if len(partes_dados) > 1 else "N/A"

            tempo_reembolso = (datetime.now() + timedelta(minutes=10)).strftime("%d/%m/%Y %H:%M:%S")
            saldo_atual = db.obter_saldo(user_id)

            msg = (
                f"✅ Compra Efetuada! ✅\n\n"
                f"💳 Cartão: {num_cc}\n"
                f"📆 DATA: {mes_cc}/{ano_cc}\n"
                f"🔐 CVV: {cvv_cc}\n"
                f"🛍️ Cartão Formatado: {res_gg}\n\n"
                f"👤 DADOS:\nNome: {nome_titular}\nCPF: {cpf_titular}\n\n"
                f"💰 Seu Saldo Restante: R$ {saldo_atual:.2f}\n\n"
                f"⏰ TEMPO MAXIMO PARA REEMBOLSO: {tempo_reembolso} (10 minutos)"
            )
            bot.send_message(call.message.chat.id, msg, parse_message="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente! Faça uma recarga Pix.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Estoque sem dados de titular suficientes.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN.")
            
    elif data == "voltar_menu":
        text, markup = main_menu(user_id)
        try: 
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: 
            pass
        
        dados = db.carregar_dados()
        banner_file_id = dados.get("configuracoes", {}).get("banner_file_id")
        
        if banner_file_id:
            try: 
                bot.send_photo(call.message.chat.id, photo=banner_file_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except Exception: 
                bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Bot rodando com Mercado Pago...")
    try: 
        bot.remove_webhook()
    except Exception: 
        pass

    while True:
        try: 
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error(f"Erro: {e}")
            time.sleep(5)
