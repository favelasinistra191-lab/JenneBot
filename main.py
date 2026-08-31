"""
Arquivo Principal - Don Ghost Bot (Versão Mercado Pago)
Versão Profissional Completa e Inteira • Roteamento Isolado + Banner Dinâmico no Start + Comandos Admin
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

import mercadopago

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
if not MP_ACCESS_TOKEN:
    MP_ACCESS_TOKEN = "APP_USR-249848378901175-080605-e67c3c2b3575d5a687864a126913a7ae-3171236437"

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("DonGhostBot")

bot = telebot.TeleBot(config.TOKEN, threaded=True)
db.criar_tabelas()

app = Flask(__name__)
CANAL_OBRIGATORIO = "https://t.me/+VNkIZojSrHs4NDJh"

@app.route('/')
def home():
    return "DonGhostBot rodando perfeitamente!"

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
                return
            except Exception as e:
                LOG.error(f"Erro ao enviar foto do banner no start: {e}")
        
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
                return
            except Exception:
                pass
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

@bot.message_handler(commands=['abastecer'])
def cmd_abastecer(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/abastecer [BIN]` e envie as linhas na mensagem seguinte.", parse_mode="Markdown")
        return
    bin_alvo = ''.join(filter(str.isdigit, args[1]))[:6]
    bot.reply_to(message, f"📥 Envie agora o arquivo ou texto com as GGs para a BIN `{bin_alvo}`.", parse_mode="Markdown")

@bot.message_handler(commands=['set_preco'])
def cmd_set_preco(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/set_preco [bin] [valor]`", parse_mode="Markdown")
        return
    try:
        bin_code = ''.join(filter(str.isdigit, args[1]))[:6]
        valor = float(args[2].replace(",", "."))
        db.definir_preco_bin(bin_code, valor)
        bot.reply_to(message, f"✅ Preço da BIN `{bin_code}` atualizado para `R$ {valor:.2f}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao definir preço: {e}")

@bot.message_handler(commands=['set_bonus'])
def cmd_set_bonus(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/set_bonus [porcentagem] [dias (opcional)]`", parse_mode="Markdown")
        return
    try:
        porcentagem = float(args[1].replace(",", "."))
        dias = int(args[2]) if len(args) > 2 else 1
        expira_em = time.time() + (dias * 86400) if dias > 0 else None
        
        dados = db.carregar_dados(forcar_atualizacao=True)
        if "configuracoes" not in dados:
            dados["configuracoes"] = {}
        dados["configuracoes"]["bonus_porcentagem"] = porcentagem
        dados["configuracoes"]["bonus_expira_em"] = expira_em
        db.salvar_dados(dados)
        
        bot.reply_to(message, f"✅ Bônus configurado para `{porcentagem:.0f}%` (válido por {dias} dias).", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

@bot.message_handler(commands=['gerar_gift'])
def cmd_gerar_gift(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Use: `/gerar_gift [quantidade] [valor]`", parse_mode="Markdown")
        return
    try:
        quantidade = int(args[1])
        valor = float(args[2].replace(",", "."))
        gifts_criados = []
        
        for _ in range(quantidade):
            codigo = f"GIFT-{uuid.uuid4().hex[:8].upper()}"
            db.adicionar_gift(codigo, valor)
            gifts_criados.append(codigo)
            
        texto_resp = f"🎁 **{quantidade} Gifts de R$ {valor:.2f} gerados com sucesso!**\n\n"
        for g in gifts_criados:
            texto_resp += f"`{g}`\n"
        bot.reply_to(message, texto_resp, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

@bot.message_handler(commands=['resgatar'])
def cmd_resgatar(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use: `/resgatar [codigo_gift]`", parse_mode="Markdown")
        return
    codigo = args[1].strip()
    status, valor = db.resgatar_gift(user_id, codigo)
    if status == "ok":
        saldo_novo = db.obter_saldo(user_id)
        bot.reply_to(message, f"✅ **Gift resgatado com sucesso!**\n\n💵 Adicionado: `R$ {valor:.2f}`\n💰 Seu Saldo Atual: `R$ {saldo_novo:.2f}`", parse_mode="Markdown")
    elif status == "usado":
        bot.reply_to(message, "❌ Este Gift já foi resgatado por alguém.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Código de Gift inválido ou inexistente.", parse_mode="Markdown")

@bot.message_handler(commands=['pix'])
def cmd_pix(message):
    try:
        user_id = message.from_user.id
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Informe o valor da recarga.\nExemplo: `/pix 20`", parse_mode="Markdown")
            return
        
        valor = float(args[1].replace(",", "."))
        if valor < 10.0:
            bot.reply_to(message, "⚠️ O valor mínimo para recarga via Pix é R$ 10,00.", parse_mode="Markdown")
            return
            
        preference_data = {
            "items": [{
                "title": f"Recarga de Saldo - ID {user_id}",
                "quantity": 1,
                "unit_price": float(valor),
                "currency_id": "BRL"
            }],
            "external_reference": f"recarga_{user_id}_{int(time.time())}",
            "payment_methods": {
                "excluded_payment_types": [{"id": "credit_card"}, {"id": "ticket"}],
                "installments": 1
            }
        }
        
        preference_response = sdk.preference().create(preference_data)
        payment_link = preference_response["response"].get("init_point")
        
        if not payment_link:
            bot.reply_to(message, "❌ Erro ao gerar link de pagamento no Mercado Pago. Tente novamente mais tarde.", parse_mode="Markdown")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🔗 Pagar com Pix (Mercado Pago)", url=payment_link),
            types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu")
        )
        
        bot.reply_to(
            message,
            f"💳 **LINK DE PAGAMENTO PIX GERADO!**\n\n"
            f"💵 Valor: `R$ {valor:.2f}`\n\n"
            f"Clique no botão abaixo para abrir o checkout seguro do Mercado Pago. O saldo cai automaticamente após a aprovação!",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        LOG.error(f"Erro ao gerar pix: {e}")
        bot.reply_to(message, f"❌ Erro ao processar recarga Pix: {e}")

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
        markup_rec = types.InlineKeyboardMarkup(row_width=1)
        markup_rec.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        texto_rec = (
            f"💳 **FAZER RECARGA VIA PIX**\n\n"
            f"Para adicionar saldo na sua conta de forma automática, envie o comando seguido do valor desejado.\n\n"
            f"💡 **Exemplo:**\n`/pix 20` (Valor mínimo: R$ 10,00)\n\n"
            f"⚡ O link de pagamento Pix do Mercado Pago será gerado instantaneamente na hora!"
        )
        try:
            bot.edit_message_text(text=texto_rec, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup_rec, parse_mode="Markdown")
        except Exception:
            bot.send_message(call.message.chat.id, text=texto_rec, reply_markup=markup_rec, parse_mode="Markdown")

    elif data == "menu_gg":
        dados_db = db.carregar_dados()
        estoque = dados_db.get("estoque", [])
        bins_disponiveis = {}

        for item in estoque:
            if item.get("categoria") == "gg" and item.get("vendido", 0) == 0:
                bin_code = item.get("bin")
                if bin_code:
                    if bin_code not in bins_disponiveis:
                        bins_disponiveis[bin_code] = {
                            "banco": item.get("banco", "GERAL"),
                            "bandeira": item.get("bandeira", "OUTRA"),
                            "quantidade": 0
                        }
                    bins_disponiveis[bin_code]["quantidade"] += 1

        if not bins_disponiveis:
            bot.answer_callback_query(call.id, "⚠️ No momento não há nenhuma GG disponível em estoque!", show_alert=True)
            return

        markup_gg = types.InlineKeyboardMarkup(row_width=1)
        for bin_code, info in bins_disponiveis.items():
            preco_bin = db.obter_preco_bin(bin_code)
            texto_botao = f"💳 {info['bandeira']} - {info['banco']} ({bin_code[:4]}**) | Qtd: {info['quantidade']} | R$ {preco_bin:.2f}"
            markup_gg.add(types.InlineKeyboardButton(texto_botao, callback_data=f"comprar_gg_{bin_code}"))

        markup_gg.add(types.InlineKeyboardButton("🔙 Menu Principal", callback_data="voltar_menu"))
        
        try:
            bot.edit_message_text(
                text="💳 **ESCOLHA A BIN / CARTÃO DESEJADO:**",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup_gg,
                parse_mode="Markdown"
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                text="💳 **ESCOLHA A BIN / CARTÃO DESEJADO:**",
                reply_markup=markup_gg,
                parse_mode="Markdown"
            )

    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        dados_db = db.carregar_dados()
        estoque_atual = [e for e in dados_db.get("estoque", []) if e.get("categoria") == "gg" and e.get("bin") == bin_escolhida and e.get("vendido", 0) == 0]
        
        if not estoque_atual:
            bot.answer_callback_query(call.id, "⚠️ Estoque esgotado para esta BIN!", show_alert=True)
            return

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
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.answer_callback_query(call.id, "❌ Saldo insuficiente.", show_alert=True)
        elif status == "falta_dados":
            bot.answer_callback_query(call.id, "⚠️ Estoque sem dados de titular suficientes.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Estoque esgotado para esta BIN.", show_alert=True)
            
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
                return
            except Exception: 
                pass
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
