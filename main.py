"""
Arquivo Principal - Don Ghost Bot
Versão Profissional Completa • Banner Dinâmico + GGs Casados + Pix + Lote Gifts
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

# Configurações ElitePay
ELITE_URL = "https://api.elitepaybr.com/api/v1/deposit"
ELITE_CLIENT_ID = "ep_70f82834297cc8f491f7daafd666ee1d"
ELITE_CLIENT_SECRET = "eps_e5989dd11dc840f3967a1bf517277d8a0c729ffb39ec519652d125a25ad42d53"

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("DonGhostBot")

bot = telebot.TeleBot(config.TOKEN, threaded=True)
db.criar_tabelas()

app = Flask(__name__)

CANAL_OBRIGATORIO = "https://t.me/+VNkIZojSrHs4NDJh"

@app.route('/')
def home():
    return "DonGhostBot está rodando e acordado perfeitamente!"

@app.route('/webhook/elitepay', methods=['POST'])
def webhook_elitepay():
    try:
        dados_notificacao = request.json
        if not dados_notificacao:
            return jsonify({"status": "error", "message": "Sem dados"}), 400

        status_pagamento = dados_notificacao.get("status") or dados_notificacao.get("payment_status")
        external_ref = dados_notificacao.get("external_reference") or dados_notificacao.get("txid") or dados_notificacao.get("transactionId")

        if status_pagamento in ["approved", "pago", "CONCLUIDA", "PAID", "APROVADO"]:
            if external_ref and "recarga_" in str(external_ref):
                partes = str(external_ref).split("_")
                if len(partes) >= 2:
                    user_id = int(partes[1])
                    valor_pago = float(dados_notificacao.get("valor") or dados_notificacao.get("amount") or 0.0)
                    
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
                                    f"✅ **Pagamento Aprovado!**\n\n"
                                    f"💵 Recarga de R$ {valor_pago:.2f}{msg_bonus_texto} adicionada com sucesso!\n"
                                    f"💰 **Saldo Atual:** `R$ {novo_saldo:.2f}`",
                                    reply_markup=markup,
                                    parse_mode="Markdown"
                                )
                            except Exception as e:
                                LOG.error(f"Erro Pix: {e}")

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
        types.InlineKeyboardButton("💳 Comprar GGs (R$ 4.00)", callback_data="menu_gg"),
        types.InlineKeyboardButton("💳 Fazer Recarga Pix", callback_data="menu_recarga"),
        types.InlineKeyboardButton("👤 Meu Perfil", callback_data="perfil"),
        types.InlineKeyboardButton("📦 Minhas Compras", callback_data="historico_compras"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="info_gift"),
        types.InlineKeyboardButton("🤝 Indique e Ganhe", callback_data="info_indicar"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte")
    )
    return text, markup

# COMANDO EXCLUSIVO PARA VOCÊ MUDAR O BANNER DO BOT!
@bot.message_handler(content_types=['photo'])
def capturar_novo_banner(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    # Verifica se a pessoa mandou a foto escrevendo "/mudar_banner" na legenda da imagem
    if not message.caption or "/mudar_banner" not in message.caption:
        return

    # Pega o ID oficial da foto salva no servidor do Telegram
    file_id = message.photo[-1].file_id
    
    # Salva no banco de dados
    dados = db.carregar_dados(forcar_atualizacao=True)
    if "configuracoes" not in dados:
        dados["configuracoes"] = {}
    dados["configuracoes"]["banner_file_id"] = file_id
    db.salvar_dados(dados)
    
    bot.reply_to(message, "✅ **Banner atualizado com sucesso!** A partir de agora, a mensagem inicial de todos usará esta foto.", parse_mode="Markdown")

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
            bot.send_message(message.chat.id, "⚠️ **Acesso Restrito!**\n\nPara utilizar o bot, você precisa entrar no nosso canal oficial primeiro.", reply_markup=markup, parse_mode="Markdown")
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
        
        # Puxa o banner do Banco de Dados
        dados = db.carregar_dados()
        banner_file_id = dados.get("configuracoes", {}).get("banner_file_id")
        
        if banner_file_id:
            try:
                bot.send_photo(message.chat.id, photo=banner_file_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        else:
            # Se você ainda não configurou um banner, envia só texto (sem erro)
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
        f"⚙️ **Comandos Disponíveis:**\n"
        f"• `/abastecer [BIN]` (Abastecer GGs)\n"
        f"• `/add_dados [lista]` (Abastecer titulares)\n"
        f"• `/gerar_gift [qtd] [valor]` (Criar gifts em lote)\n"
        f"• `/set_bonus [porcentagem] [dias]` (Configurar promoção)\n"
        f"• `/limpar_estoque` (Limpar não vendidos)\n"
        f"📸 **Para mudar o banner:** Envie uma foto e digite `/mudar_banner` na **legenda** da imagem."
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")

@bot.message_handler(commands=['set_bonus'])
def cmd_set_bonus(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Uso correto: `/set_bonus [porcentagem] [dias]`\nExemplo: `/set_bonus 100 3` (100% de bônus por 3 dias)", parse_mode="Markdown")
        return
    try:
        porcentagem = float(args[1].replace(',', '.'))
        dias = float(args[2].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Valores inválidos. Use números.", parse_mode="Markdown")
        return
    
    expira_em = time.time() + (dias * 86400)
    dados = db.carregar_dados(forcar_atualizacao=True)
    if "configuracoes" not in dados:
        dados["configuracoes"] = {}
        
    dados["configuracoes"]["bonus_porcentagem"] = porcentagem
    dados["configuracoes"]["bonus_expira_em"] = expira_em
    db.salvar_dados(dados)
    
    bot.reply_to(message, f"✅ **Promoção Configurada!**\n\n🔥 Bônus de: `{porcentagem:.0f}%`\n⏳ Duração: `{dias} dia(s)`", parse_mode="Markdown")

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
    bot.reply_to(message, f"🔍 **BIN Registrada!**\n\n💳 **BIN:** `{bin6}` | **Bandeira:** `{bandeira}` | **Banco:** `{banco}`\n\n👇 **AGORA MANDE A LISTA COMPLETA DOS CARTÕES (GGs)**.", parse_mode="Markdown")

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
            bot.reply_to(message, "❌ Nenhum cartão válido encontrado.")
            return

        db.adicionar_lote_estoque(cartoes, categoria='gg', bin=bin6, banco=banco, bandeira=bandeira)
        msg_sucesso = f"✅ **Estoque Atualizado!**\n\n📦 Adicionadas `{len(cartoes)} novas GGs` ao bot!\n💳 **BIN:** `{bin6}` | **Bandeira:** `{bandeira}`"
        bot.reply_to(message, msg_sucesso, parse_mode="Markdown")
        try: bot.send_message(CANAL_OBRIGATORIO, msg_sucesso, parse_mode="Markdown")
        except: pass

@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID: return
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares após o comando.", parse_mode="Markdown")
        return
    linhas = [l.strip() for l in texto_completo.replace('\r\n', '\n').split('\n') if l.strip()]
    if not linhas:
        bot.reply_to(message, "❌ Nenhum dado válido encontrado.")
        return
    db.adicionar_lote_dados_titular(linhas)
    bot.reply_to(message, f"✅ Sucesso! Cadastrados `{len(linhas)}` titulares.", parse_mode="Markdown")

@bot.message_handler(commands=['limpar_estoque'])
def cmd_limpar_estoque(message):
    if message.from_user.id != config.ADMIN_ID: return
    try:
        dados = db.carregar_dados(forcar_atualizacao=True)
        dados["estoque"] = [e for e in dados.get("estoque", []) if e.get("vendido") == 1]
        dados["dados_titular"] = [t for t in dados.get("dados_titular", []) if t.get("usado") == 1]
        db.salvar_dados(dados)
        bot.reply_to(message, "🧹 **Estoque não vendido limpo com sucesso!**", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

@bot.message_handler(commands=['gerar_gift'])
def cmd_gerar_gift(message):
    if message.from_user.id != config.ADMIN_ID: return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Uso correto: `/gerar_gift [quantidade] [valor]`", parse_mode="Markdown")
        return
    try:
        quantidade = int(args[1])
        valor = float(args[2].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Quantidade ou valor inválido.", parse_mode="Markdown")
        return
    
    if quantidade <= 0 or valor <= 0:
        bot.reply_to(message, "❌ Informe valores maiores que zero.", parse_mode="Markdown")
        return

    try:
        dados = db.carregar_dados(forcar_atualizacao=True)
        if "gift_cards" not in dados: dados["gift_cards"] = []
        bot_username = bot.get_me().username
        lista_gerados = f"🎁 **Lote de Gift Cards Gerado ({quantidade}x - R$ {valor:.2f})**\n\n"
        
        for _ in range(quantidade):
            codigo_gift = f"GIFT-{uuid.uuid4().hex[:8].upper()}"
            dados["gift_cards"].append({"codigo": codigo_gift, "valor": valor, "usado": 0})
            lista_gerados += f"🔑 `R$ {valor:.2f}`: `{codigo_gift}`\n"
            
        db.salvar_dados(dados)
        lista_gerados += f"\n👉 **Para resgatar:**\nhttps://t.me/{bot_username}\n💡 **Comando:** `/resgatar [código]`"
        bot.reply_to(message, lista_gerados, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

@bot.message_handler(commands=['resgatar'])
def cmd_resgatar(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o código. Ex: `/resgatar [codigo]`", parse_mode="Markdown")
        return
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
        bot.reply_to(message, "❌ Valor inválido. Use números, ex: `/pix 25`", parse_mode="Markdown")
        return
    if valor < 10.0:
        bot.reply_to(message, "⚠️ O valor mínimo para recarga via Pix é de **R$ 10,00**.", parse_mode="Markdown")
        return

    headers = {"x-client-id": ELITE_CLIENT_ID, "x-client-secret": ELITE_CLIENT_SECRET, "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"amount": valor, "description": f"Recarga Saldo Bot #{user_id}", "payerName": message.from_user.first_name or "Cliente", "payerDocument": "00000000000", "external_reference": f"recarga_{user_id}_{uuid.uuid4().hex[:6]}"}

    try:
        response = requests.post(ELITE_URL, json=payload, headers=headers, timeout=15)
        if response.status_code in [200, 201]:
            try: dados_resposta = response.json()
            except: bot.send_message(message.chat.id, f"❌ Erro ao processar Pix."); return

            qr_code = dados_resposta.get("copyPaste") or dados_resposta.get("qrcodeUrl")
            if qr_code:
                mensagem_pix = f"💳 **PAGAMENTO PIX**\n\n💵 **Valor:** `R$ {valor:.2f}`\n\n📋 **PIX COPIA E COLA:**\n`{qr_code}`\n\n*Basta copiar, pagar no seu banco e o saldo será creditado automaticamente.*"
                bot.send_message(message.chat.id, mensagem_pix, parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, f"❌ Erro ao gerar o código Pix.")
        else:
            bot.send_message(message.chat.id, f"❌ Erro no gateway de pagamento.")
    except Exception:
        bot.send_message(message.chat.id, f"❌ Erro de conexão.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "perfil":
        saldo = db.obter_saldo(user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"👤 **Painel de Perfil**\n\n• ID: `{user_id}`\n• Saldo: `R$ {saldo:.2f}`", parse_mode="Markdown")
        
    elif data == "suporte":
        bot.answer_callback_query(call.id)
        markup_sup = types.InlineKeyboardMarkup(row_width=1)
        markup_sup.add(
            types.InlineKeyboardButton("💬 Suporte Telegram", url="https://t.me/JENNE_BOT_SUPORTE"),
            types.InlineKeyboardButton("💬 Suporte WhatsApp", url="https://wa.me/639272951705"),
            types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")
        )
        bot.edit_message_text(text="📞 **CENTRAL DE SUPORTE OFICIAL**\n\nEscolha abaixo o canal de atendimento:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup_sup, parse_mode="Markdown")
        
    elif data == "info_gift":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🎁 Para resgatar saldo, envie:\n`/resgatar [codigo]`", parse_mode="Markdown")

    elif data == "info_indicar":
        bot.answer_callback_query(call.id)
        bot_username = bot.get_me().username
        link_indicacao = f"https://t.me/{bot_username}?start=ref_{user_id}"
        bot.send_message(call.message.chat.id, f"🤝 **INDICAÇÃO E GANHE • R$ 20,00**\n\nConvide amigos usando seu link:\n`{link_indicacao}`\n\n💰 *Você ganha R$ 20,00 assim que seu amigo fizer o **primeiro depósito**!*", parse_mode="Markdown")

    elif data == "historico_compras":
        bot.answer_callback_query(call.id)
        historico = db.obter_historico_compras(user_id)
        if not historico:
            bot.send_message(call.message.chat.id, "📦 Você ainda não realizou compras de GGs.", parse_mode="Markdown")
            return
        texto_hist = "📦 **HISTÓRICO DE COMPRAS (GGs)**\n───────────────────────────────\n"
        for item in historico[-10:]:
            texto_hist += f"💳 `{item['conteudo']}`\n🏦 `{item['banco']} / {item['bandeira']}`\n───────────────────────────────\n"
        bot.send_message(call.message.chat.id, texto_hist, parse_mode="Markdown")
        
    elif data == "menu_recarga":
        bot.answer_callback_query(call.id)
        msg_recarga = f"💳 **RECARGA PIX**\n\n⚡ Pagamento automatizado.\n🔥 *Promoção ativa!*\n\n✍️ **Envie no chat:**\n`/pix [valor]`\n💡 *Ex:* `/pix 15`\n⚠️ *Mínimo R$ 10,00.*"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.edit_message_text(text=msg_recarga, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == "menu_gg":
        bot.answer_callback_query(call.id)
        ggs = db.listar_estoque_gg_agrupado()
        if not ggs:
            bot.send_message(call.message.chat.id, "❌ Sem GGs disponíveis no momento.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for bin_code, bandeira, total_qtd in ggs:
            markup.add(types.InlineKeyboardButton(f"💳 {bandeira} ({bin_code}) • Estoque: {total_qtd} (R$ 4,00)", callback_data=f"comprar_gg_{bin_code}"))
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **SELECIONE A BIN:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        bot.answer_callback_query(call.id)
        status, res_gg, res_dados, banco_item, bandeira_item, bin_item = db.realizar_compra_item_casado(user_id, 'gg', 4.0, bin_v=bin_escolhida)
        
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
                f"👤 DADOS PARA TE AUXILIAR:\n"
                f"Nome: {nome_titular}\n"
                f"CPF: {cpf_titular}\n\n"
                f"Nível: {bin_item}\n"
                f"Bandeira: {bandeira_item}\n"
                f"Banco: {banco_item}\n\n"
                f"💰 Seu Saldo Restante: R$ {saldo_atual:.2f}\n\n"
                f"⏰ TEMPO MAXIMO PARA O REEMBOLSO: {tempo_reembolso}. (10 minutos)\n\n"
                f"TESTAR LIVE DOS CARDS NA COBASI\n\n"
                f"RETORNO\n\n"
                f"N7\n"
                f"00, 01, 05, 13, 17, 41, 43, 51, 54, 57, 62, 63, 65, 75. (Todos esses retornos são lives!)\n\n"
                f"SUPORTE TELEGRAM: @JENNE_BOT_SUPORTE\n"
                f"SUPORTE WHATSAPP: +63 927 295 1705"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
            try: bot.send_message(CANAL_OBRIGATORIO, f"🛒 **Nova Compra!**\n👤 Cliente: `{call.from_user.first_name}`\n💳 BIN: `{bin_item}` ({bandeira_item})", parse_mode="Markdown")
            except: pass
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente! Faça uma recarga Pix.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Estoque sem dados de titular suficientes para este cartão.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        
        dados = db.carregar_dados()
        banner_file_id = dados.get("configuracoes", {}).get("banner_file_id")
        
        if banner_file_id:
            try: bot.send_photo(call.message.chat.id, photo=banner_file_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Bot rodando com Banner Automático pelo DB...")
    try: bot.remove_webhook()
    except: pass

    while True:
        try: bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error(f"Erro: {e}")
            time.sleep(5)
