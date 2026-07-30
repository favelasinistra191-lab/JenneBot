"""
Arquivo Principal - JenneStoreBot
Versão Ultra-Rápida com Adição em Lote (Batch Processing)
"""
import os
import logging
import threading
import uuid
from flask import Flask
import telebot
from telebot import types
import requests

import config
import database as db

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("JenneBot")

bot = telebot.TeleBot(config.TOKEN, threaded=True)
db.criar_tabelas()

app = Flask(__name__)

@app.route('/')
def home():
    return "JenneStoreBot está rodando e acordado!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


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
        response = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=3, headers={'Accept-Version': '3'})
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
    
    text = (
        f"⚡ **JENNSTORE • PAINEL DIGITAL** ⚡\n"
        f"────────────────────────\n"
        f"👤 **ID de Acesso:** `{user_id}`\n"
        f"💰 **Saldo Disponível:** `R$ {saldo:.2f}`\n"
        f"────────────────────────\n"
        f"💡 *Selecione uma das categorias abaixo para iniciar sua compra automatizada:*"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 Streaming (R$ 12.00)", callback_data="cat_streaming"),
        types.InlineKeyboardButton("📱 eSIM Global (R$ 20.00)", callback_data="cat_esim"),
        types.InlineKeyboardButton("💳 Comprar GGs (R$ 4.00)", callback_data="menu_gg"),
        types.InlineKeyboardButton("👤 Meu Perfil", callback_data="perfil"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="info_gift"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte")
    )
    return text, markup


@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        user_id = message.from_user.id
        db.garantir_usuario(user_id, message.from_user.first_name or "Cliente", message.from_user.username or "")
        text, markup = main_menu(user_id)
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        LOG.error(f"Erro no start: {e}")


@bot.message_handler(commands=['admin', 'painel'])
def cmd_admin(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    total_vendas, faturamento, clientes = db.obter_dados_relatorio()
    texto = (
        f"👑 **Painel Administrativo • JenneStore**\n\n"
        f"📊 Clientes: `{clientes}` | Vendas: `{total_vendas}`\n\n"
        f"⚙️ **Abastecimento (2 Etapas):**\n"
        f"• `/add_gg [BIN]` (R$ 4,00)\n"
        f"• `/add_streaming [Nome]` (R$ 12,00)\n\n"
        f"⚙️ **Diretos:**\n"
        f"• `/add_esim [codigo]` (R$ 20,00)\n"
        f"• `/add_dados [lista]` (Titulares)\n"
        f"• `/limpar_estoque`\n"
        f"• `/gerar_gift [valor]`"
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")


@bot.message_handler(commands=['add_gg'])
def cmd_add_gg_etapa1(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    args = message.text.replace('/add_gg', '').strip()
    bin6 = "".join(filter(str.isdigit, args))[:6]
    
    if len(bin6) < 6:
        bot.reply_to(message, "⚠️ Use assim: `/add_gg 422061`", parse_mode="Markdown")
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
        f"👇 **AGORA MANDE A LISTA COMPLETA** (pode colar dezenas de cartões de uma vez).", 
        parse_mode="Markdown"
    )


@bot.message_handler(commands=['add_streaming'])
def cmd_add_streaming_etapa1(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    nome_streaming = message.text.replace('/add_streaming', '').strip().upper()
    if not nome_streaming:
        bot.reply_to(message, "⚠️ Informe o nome. Ex: `/add_streaming NETFLIX`", parse_mode="Markdown")
        return
    
    dados = db.carregar_dados()
    dados["admin_pendente"] = {
        "admin_id": message.from_user.id,
        "tipo": "streaming",
        "nome_streaming": nome_streaming
    }
    db.salvar_dados(dados)

    bot.reply_to(
        message, 
        f"🎬 **Streaming Configurado: `{nome_streaming}`**\n\n"
        f"👇 **AGORA MANDE A LISTA DE CONTAS** (cole direto abaixo).", 
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
            bot.reply_to(message, "❌ Nenhum cartão válido encontrado. Envie novamente.")
            return

        # Adiciona tudo de uma vez num único salvamento rápido
        db.add_lote_estoque_wrapper = lambda c, cat, b, bc, band: None # placeholder
        db.adicionar_lote_estoque(cartoes, categoria='gg', bin=bin6, banco=banco, bandeira=bandeira)

        bot.reply_to(message, f"✅ **Estoque Atualizado com Sucesso!**\n\n💳 **BIN:** `{bin6}`\n📦 **Adicionados:** `+{len(cartoes)} GGs` de uma vez!", parse_mode="Markdown")

    elif tipo == "streaming":
        nome_streaming = pendente["nome_streaming"]
        contas = [l.strip() for l in linhas if l.strip()]
        if not contas:
            bot.reply_to(message, "❌ Nenhuma conta válida encontrada. Envie novamente.")
            return

        db.adicionar_lote_estoque(contas, categoria='streaming', bin='000000', banco='GERAL', bandeira=nome_streaming)
        bot.reply_to(message, f"✅ **Estoque Atualizado!**\n\n🎬 **Streaming:** `{nome_streaming}`\n📦 **Adicionadas:** `+{len(contas)} Contas`", parse_mode="Markdown")


@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares logo após o comando.", parse_mode="Markdown")
        return
    linhas = [l.strip() for l in texto_completo.replace('\r\n', '\n').split('\n') if l.strip()]
    if not linhas:
        bot.reply_to(message, "❌ Nenhum dado válido encontrado.")
        return
    
    db.adicionar_lote_dados_titular(linhas)
    bot.reply_to(message, f"✅ Sucesso! Cadastrados `{len(linhas)}` dados de titulares em lote.", parse_mode="Markdown")


@bot.message_handler(commands=['add_esim'])
def cmd_add_esim(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    conteudo = message.text.replace('/add_esim', '').strip()
    if not conteudo:
        bot.reply_to(message, "⚠️ Informe o eSIM. Ex: `/add_esim LPA:1$SMDP...`", parse_mode="Markdown")
        return
    db.adicionar_lote_estoque([conteudo], categoria='esim', bin='000000', banco='GERAL', bandeira='ESIM')
    bot.reply_to(message, "✅ eSIM adicionado com sucesso!", parse_mode="Markdown")


@bot.message_handler(commands=['limpar_estoque'])
def cmd_limpar_estoque(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        dados = db.carregar_dados()
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
        dados = db.carregar_dados()
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
            f"🎁 **Gift Card Gerado com Sucesso!**\n\n"
            f"💵 **Valor:** `R$ {valor:.2f}`\n"
            f"🔑 **Código:** `{codigo_gift}`\n\n"
            f"📋 **Texto pronto para enviar ao cliente:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎁 Resgate seu Gift Card de **R$ {valor:.2f}** na JenneStore!\n"
            f"Clique no link abaixo para entrar no bot e resgatar:\n"
            f"👉 https://t.me/{bot_username}\n\n"
            f"Basta enviar o comando abaixo:\n"
            f"`/resgatar {codigo_gift}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
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
        dados = db.carregar_dados()
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
        bot.reply_to(message, f"🎉 **Resgate efetuado!** Adicionado R$ {valor:.2f} ao seu saldo.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "perfil":
        saldo = db.obter_saldo(user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"👤 **Painel de Perfil**\n\n• ID: `{user_id}`\n• Saldo Atual: `R$ {saldo:.2f}`", parse_mode="Markdown")
        
    elif data == "suporte":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📞 Suporte e atendimento via administrador.", parse_mode="Markdown")
        
    elif data == "info_gift":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🎁 Para adicionar saldo com um Gift Card, envie:\n`/resgatar [seu_codigo]`", parse_mode="Markdown")
        
    elif data == "cat_streaming":
        bot.answer_callback_query(call.id)
        dados = db.carregar_dados()
        estoque = dados.get("estoque", [])
        
        streamings_disp = {}
        for item in estoque:
            if item.get("categoria") == 'streaming' and item.get("vendido") == 0:
                band = item.get("bandeira")
                streamings_disp[band] = streamings_disp.get(band, 0) + 1
                
        if not streamings_disp:
            bot.send_message(call.message.chat.id, "❌ Nenhuma conta de Streaming disponível no momento.")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for nome_streaming, total_qtd in streamings_disp.items():
            markup.add(types.InlineKeyboardButton(f"🎬 {nome_streaming} • Estoque: {total_qtd} (R$ 12,00)", callback_data=f"comprar_stream_{nome_streaming}"))
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "🛒 **Selecione o Streaming Desejado:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("comprar_stream_"):
        nome_streaming = data.replace("comprar_stream_", "")
        bot.answer_callback_query(call.id)
        
        dados = db.carregar_dados()
        preco = 12.0
        
        user = None
        for u in dados.get("usuarios", []):
            if u["user_id"] == user_id:
                user = u
                break
                
        if not user or user.get("saldo", 0.0) < preco:
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
            return
            
        item_alvo = None
        for item in dados.get("estoque", []):
            if item.get("categoria") == 'streaming' and item.get("bandeira") == nome_streaming and item.get("vendido") == 0:
                item_alvo = item
                break
                
        if not item_alvo:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta conta.")
            return
            
        user["saldo"] -= preco
        item_alvo["vendido"] = 1
        db.salvar_dados(dados)
        
        bot.send_message(call.message.chat.id, f"✅ **COMPRA APROVADA!**\n\n🎬 **Serviço:** `{nome_streaming}`\n🔑 **Conta:** `{item_alvo.get('conteudo')}`\n⏱️ *Você tem 10 minutos para reportar caso haja problemas.*", parse_mode="Markdown")

    elif data == "cat_esim":
        bot.answer_callback_query(call.id)
        dados = db.carregar_dados()
        esims = [e for e in dados.get("estoque", []) if e.get("categoria") == 'esim' and e.get("vendido") == 0][:5]
        
        if not esims:
            bot.send_message(call.message.chat.id, "❌ Nenhum eSIM disponível no momento.")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for item in esims:
            markup.add(types.InlineKeyboardButton(f"📱 Comprar eSIM Global • R$ 20.00", callback_data=f"compras_esim_{item.get('id')}"))
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "📱 **eSIM Globais Disponíveis:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("compras_esim_"):
        item_id = int(data.split("_")[2])
        bot.answer_callback_query(call.id)
        
        dados = db.carregar_dados()
        preco = 20.0
        
        user = None
        for u in dados.get("usuarios", []):
            if u["user_id"] == user_id:
                user = u
                break
                
        if not user or user.get("saldo", 0.0) < preco:
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
            return
            
        item_alvo = None
        for item in dados.get("estoque", []):
            if item.get("id") == item_id and item.get("vendido") == 0:
                item_alvo = item
                break
                
        if not item_alvo:
            bot.send_message(call.message.chat.id, "❌ Item esgotado.")
            return
            
        user["saldo"] -= preco
        item_alvo["vendido"] = 1
        db.salvar_dados(dados)
        
        bot.send_message(call.message.chat.id, f"✅ **eSIM Adquirido com Sucesso!**\n\n📱 **Dados de Ativação:**\n`{item_alvo.get('conteudo')}`\n⏱️ *Você tem 10 minutos para troca em caso de problemas.*", parse_mode="Markdown")

    elif data == "menu_gg":
        bot.answer_callback_query(call.id)
        ggs = db.listar_estoque_gg_agrupado()
        if not ggs:
            bot.send_message(call.message.chat.id, "❌ Não há GGs disponíveis no momento.")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for bin_code, bandeira, total_qtd in ggs:
            texto_btn = f"💳 {bandeira} ({bin_code}) • Estoque: {total_qtd} (R$ 4,00)"
            markup.add(types.InlineKeyboardButton(texto_btn, callback_data=f"comprar_gg_{bin_code}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **Selecione a BIN Desejada:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        bot.answer_callback_query(call.id)
        
        status, res_gg, res_dados, banco_item, bandeira_item = db.realizar_compra_item_casado(user_id, 'gg', 4.0, bin_v=bin_escolhida)
        
        if status == "ok":
            msg = (
                f"✅ **PEDIDO APROVADO COM SUCESSO!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 **DADOS DO CARTÃO:**\n"
                f"• Número/Info: `{res_gg}`\n"
                f"• Bandeira: `{bandeira_item}`\n"
                f"• Banco: `{banco_item}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **DADOS DO TITULAR:**\n"
                f"• Cadastro: `{res_dados}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ **Garantia / Troca:** Você tem **10 minutos** para conferir e solicitar troca caso o item esteja inválido."
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Estoque temporariamente sem dados de titular casados.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Bot rodando com processamento em lote ultra-rápido...")
    
    try:
        bot.remove_webhook()
    except Exception:
        pass

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error(f"Erro na conexão: {e}")
            import time
            time.sleep(5)
