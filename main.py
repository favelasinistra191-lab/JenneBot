"""
Arquivo Principal - JenneStoreBot
Versão Profissional Completa • GGs com Dados Casados + ElitePay
"""
import os
import logging
import threading
import uuid
from datetime import datetime, timedelta
from flask import Flask
import telebot
from telebot import types
import requests

import config
import database as db

# Configurações ElitePay
ELITE_URL = "https://api.elitepaybr.com"
ELITE_KEY = "eps_e5989dd11dc840f3967a1bf517277d8a0c729ffb39ec519652d125a25ad42d53"

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("JenneBot")

bot = telebot.TeleBot(config.TOKEN, threaded=True)
db.criar_tabelas()

app = Flask(__name__)

CANAL_OBRIGATORIO = "https://t.me/+VNkIZojSrHs4NDJh"

@app.route('/')
def home():
    return "JenneStoreBot está rodando e acordado perfeitamente!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def verificar_inscricao_canal(user_id):
    try:
        chat_member = bot.get_chat_member(CANAL_OBRIGATORIO, user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        LOG.warning(f"Erro ao verificar inscrição no canal: {e}")
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
        f"💎 **BEM-VINDO À JENNSTORE • PREMIUM SHOP** 💎\n"
        f"───────────────────────────────\n"
        f"👤 **ID de Acesso:** `{user_id}`\n"
        f"💰 **Saldo em Conta:** `R$ {saldo:.2f}`\n"
        f"───────────────────────────────\n"
        f"🔥 *Sua central automatizada de GGs com dados casados de alta qualidade e aprovação expressa.*\n\n"
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
            bot.send_message(
                message.chat.id,
                "⚠️ **Acesso Restrito!**\n\nPara utilizar o bot, você precisa entrar no nosso canal oficial primeiro.",
                reply_markup=markup,
                parse_mode="Markdown"
            )
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
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        LOG.error(f"Erro no start: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "verificar_inscricao")
def callback_verificar_inscricao(call):
    user_id = call.from_user.id
    if verificar_inscricao_canal(user_id):
        bot.answer_callback_query(call.id, "✅ Verificado com sucesso!", show_alert=True)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "⚠️ Você ainda não entrou no canal!", show_alert=True)


@bot.message_handler(commands=['admin', 'painel'])
def cmd_admin(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    total_vendas, faturamento, clientes = db.obter_dados_relatorio()
    texto = (
        f"👑 **Painel Administrativo • JenneStore**\n\n"
        f"📊 Clientes: `{clientes}` | Vendas: `{total_vendas}` | Faturamento: `R$ {faturamento:.2f}`\n\n"
        f"⚙️ **Comandos de Abastecimento:**\n"
        f"• `/abastecer [BIN]` (Abastecer GGs unificado)\n"
        f"• `/add_dados [lista]` (Abastecer titulares em lote)\n"
        f"• `/limpar_estoque` (Limpar não vendidos)\n"
        f"• `/gerar_gift [valor]` (Criar gift card)"
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")


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
    dados["admin_pendente"] = {
        "admin_id": message.from_user.id,
        "tipo": "gg",
        "bin": bin6,
        "banco": banco,
        "bandeira": bandeira
    }
    db.salvar_dados(dados)

    bot.reply_to(
        message, 
        f"🔍 **BIN Registrada!**\n\n"
        f"💳 **BIN:** `{bin6}` | **Bandeira:** `{bandeira}` | **Banco:** `{banco}`\n\n"
        f"👇 **AGORA MANDE A LISTA COMPLETA DOS CARTÕES (GGs)**.", 
        parse_mode="Markdown"
    )


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
            if not linha:
                continue
            for parte in linha.split():
                if '|' in parte:
                    cartoes.append(parte.strip())
        if not cartoes:
            for linha in linhas:
                if len(linha.strip()) > 10:
                    cartoes.append(linha.strip())

        if not cartoes:
            bot.reply_to(message, "❌ Nenhum cartão válido encontrado.")
            return

        db.adicionar_lote_estoque(cartoes, categoria='gg', bin=bin6, banco=banco, bandeira=bandeira)
        
        qtd_adicionada = len(cartoes)
        msg_sucesso = (
            f"✅ **Estoque Atualizado com Sucesso!**\n\n"
            f"📦 Adicionadas `{qtd_adicionada} novas GGs` ao bot!\n"
            f"💳 **BIN:** `{bin6}` | **Bandeira:** `{bandeira}`"
        )
        bot.reply_to(message, msg_sucesso, parse_mode="Markdown")

        try:
            bot.send_message(CANAL_OBRIGATORIO, msg_sucesso, parse_mode="Markdown")
        except Exception:
            pass


@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
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
    if message.from_user.id != config.ADMIN_ID:
        return
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
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Uso: `/gerar_gift [valor]`", parse_mode="Markdown")
        return
    try:
        valor = float(args[1].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Valor inválido.", parse_mode="Markdown")
        return
    
    codigo_gift = f"GIFT-{uuid.uuid4().hex[:8].upper()}"
    try:
        dados = db.carregar_dados(forcar_atualizacao=True)
        if "gift_cards" not in dados:
            dados["gift_cards"] = []
            
        dados["gift_cards"].append({
            "codigo": codigo_gift,
            "valor": valor,
            "usado": 0
        })
        db.salvar_dados(dados)
        
        bot_username = bot.get_me().username
        mensagem_formatada = (
            f"🎁 **Gift Card Gerado!**\n\n"
            f"💵 **Valor:** `R$ {valor:.2f}`\n"
            f"🔑 **Código:** `{codigo_gift}`\n\n"
            f"👉 https://t.me/{bot_username}\n"
            f"Comando: `/resgatar {codigo_gift}`"
        )
        bot.reply_to(message, mensagem_formatada, parse_mode="Markdown")
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
        gift_encontrado = None
        for g in dados.get("gift_cards", []):
            if g.get("codigo") == codigo:
                gift_encontrado = g
                break
                
        if not gift_encontrado or gift_encontrado.get("usado") == 1:
            bot.reply_to(message, "❌ Gift inválido ou já utilizado.")
            return
            
        valor = gift_encontrado.get("valor")
        gift_encontrado["usado"] = 1
        
        usuario_encontrado = None
        for u in dados.get("usuarios", []):
            if u["user_id"] == user_id:
                usuario_encontrado = u
                break
                
        if usuario_encontrado:
            usuario_encontrado["saldo"] = usuario_encontrado.get("saldo", 0.0) + valor
        else:
            dados["usuarios"].append({
                "user_id": user_id,
                "nome": message.from_user.first_name or "Cliente",
                "username": message.from_user.username or "",
                "saldo": valor
            })
            
        db.salvar_dados(dados)
        bot.reply_to(message, f"🎉 **Resgate Efetuado!** Adicionado R$ {valor:.2f} ao seu saldo.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


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
        bot.edit_message_text(
            text="📞 **CENTRAL DE SUPORTE OFICIAL**\n\nEscolha abaixo o canal de atendimento desejado:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup_sup,
            parse_mode="Markdown"
        )
        
    elif data == "info_gift":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🎁 Para resgatar saldo, envie:\n`/resgatar [codigo]`", parse_mode="Markdown")

    elif data == "info_indicar":
        bot.answer_callback_query(call.id)
        bot_username = bot.get_me().username
        link_indicacao = f"https://t.me/{bot_username}?start=ref_{user_id}"
        bot.send_message(
            call.message.chat.id,
            f"🤝 **INDICAÇÃO E GANHE • R$ 20,00**\n\n"
            f"Convide amigos usando seu link:\n`{link_indicacao}`\n\n"
            f"💰 *Você ganha R$ 20,00 de saldo automaticamente assim que o seu amigo convidado fizer o **primeiro depósito/recarga** no bot!*",
            parse_mode="Markdown"
        )

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
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💎 Recarregar R$ 10,00 (Dobro)", callback_data="pix_10"),
            types.InlineKeyboardButton("💎 Recarregar R$ 20,00 (Dobro)", callback_data="pix_20"),
            types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu")
        )
        bot.edit_message_text(
            text="💳 **RECARGA PIX • ELITEPAY**\n\n⚡ Pagamento instantâneo automatizado.\n🔥 *Promoção de saldo em dobro ativa!*",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )

    elif data in ["pix_10", "pix_20"]:
        bot.answer_callback_query(call.id)
        valor = 10.0 if data == "pix_10" else 20.0
        
        headers = {
            "Authorization": f"Bearer {ELITE_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "valor": valor,
            "external_reference": f"recarga_{user_id}_{uuid.uuid4().hex[:6]}"
        }

        try:
            response = requests.post(f"{ELITE_URL}/pix/create", json=payload, headers=headers, timeout=10)
            dados_resposta = response.json()
            
            if response.status_code in [200, 201] and "qr_code" in dados_resposta:
                qr_code = dados_resposta["qr_code"]
                txid = dados_resposta.get("txid") or dados_resposta.get("id")
                
                mensagem_pix = (
                    f"✅ **PIX ELITEPAY GERADO!**\n\n"
                    f"💵 **Valor:** `R$ {valor:.2f}` (Bônus Dobro Aplicado)\n\n"
                    f"📋 **PIX COPIA E COLA:**\n`{qr_code}`\n\n"
                    f"📲 *Pague no seu banco e clique em '🔄 Verificar Pagamento' abaixo.*"
                )
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton("🔄 Verificar Pagamento", callback_data=f"verificar_elite_{txid}_{valor}"),
                    types.InlineKeyboardButton("🔙 Voltar", callback_data="menu_recarga")
                )
                bot.edit_message_text(text=mensagem_pix, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            else:
                erro_msg = dados_resposta.get("message", "Erro ao gerar Pix na ElitePay")
                bot.send_message(call.message.chat.id, f"❌ Erro: {erro_msg}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Erro de conexão: {e}")

    elif data.startswith("verificar_elite_"):
        bot.answer_callback_query(call.id, "Consultando pagamento na ElitePay...")
        partes = data.split("_")
        txid = partes[2]
        valor = float(partes[3])
        
        url_check = f"{ELITE_URL}/pix/check/{txid}"
        headers = {"Authorization": f"Bearer {ELITE_KEY}"}
        
        try:
            resp = requests.get(url_check, headers=headers, timeout=10)
            if resp.status_code == 200:
                pag_dados = resp.json()
                status_pagamento = pag_dados.get("status")
                
                if status_pagamento in ["approved", "pago", "CONCLUIDA"]:
                    valor_total = valor * 2
                    
                    dados = db.carregar_dados(forcar_atualizacao=True)
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
                    else:
                        novo_saldo = valor_total

                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
                    
                    bot.edit_message_text(
                        text=f"🎉 **PAGAMENTO CONFIRMADO PELA ELITEPAY!**\n\nCrédito de R$ {valor:.2f} + Bônus adicionados.\n💰 **Novo Saldo:** `R$ {novo_saldo:.2f}`",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                else:
                    bot.answer_callback_query(call.id, "⚠️ Pagamento ainda não identificado. Pague o Pix e tente novamente.", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Erro ao consultar o pagamento na ElitePay.", show_alert=True)
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Erro de conexão: {e}", show_alert=True)

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
                f"💳Cartão: {num_cc}\n"
                f"📆DATA: {mes_cc}/{ano_cc}\n"
                f"🔐CVV: {cvv_cc}\n"
                f"🛍️ Cartão Formatado: {res_gg}\n\n"
                f"👤 DADOS PARA TE AUXILIAR:\n"
                f"Nome: {nome_titular}\n"
                f"CPF: {cpf_titular}\n\n"
                f"Nível: {bin_item}\n"
                f"Bandeira: {bandeira_item}\n"
                f"Banco: {banco_item}\n\n"
                f"- Seu Saldo Restante: R$ {saldo_atual:.0f}\n\n"
                f"⏰ TEMPO MAXIMO PARA O REEMBOLSO: {tempo_reembolso}. (10 minutos)\n\n"
                f"TESTAR LIVE DOS CARD NA COBASI\n\n"
                f"RETORNO\n\n"
                f"N7\n"
                f"00, 01, 05, 13, 17, 41, 43, 51, 54, 57, 62, 63, 65, 75. (Todos esses retornos são lives!)\n\n"
                f"SUPORTE TELEGRAM: @JENNE_BOT_SUPORTE\n"
                f"SUPORTE WHATSAPP: +63 927 295 1705"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

            try:
                nome_cliente = call.from_user.first_name or "Cliente"
                msg_canal = f"🛒 **Nova Compra Efetuada!**\n👤 Cliente: `{nome_cliente}`\n💳 BIN comprada: `{bin_item}` ({bandeira_item})"
                bot.send_message(CANAL_OBRIGATORIO, msg_canal, parse_mode="Markdown")
            except Exception:
                pass

        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente! Faça uma recarga Pix.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Estoque sem dados de titular suficientes para este cartão.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Bot rodando perfeitamente com todas as funções e ElitePay integrada...")
    
    try:
        bot.remove_webhook()
    except Exception:
        pass

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error(f"Erro: {e}")
            import time
            time.sleep(5)
