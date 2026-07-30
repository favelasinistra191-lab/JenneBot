"""
Arquivo Principal - JenneStoreBot
Versão Definitiva com comando em texto livre (!add)
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

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("JenneBot")

# Inicialização do Bot e Banco
bot = telebot.TeleBot(config.TOKEN, threaded=True)
db.criar_tabelas()

# Servidor Flask (Anti-Sleep)
app = Flask(__name__)

@app.route('/')
def home():
    return "JenneStoreBot está rodando e acordado!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# --- Função Otimizada: Consulta a BIN APENAS 1 VEZ por Lote ---
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

    banco = "BANCO NÃO IDENTIFICADO"
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


# --- Menu Principal Elegante ---
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
        types.InlineKeyboardButton("🛒 Streaming", callback_data="cat_streaming"),
        types.InlineKeyboardButton("📱 eSIM Global", callback_data="cat_esim"),
        types.InlineKeyboardButton("💳 Comprar GGs", callback_data="menu_gg"),
        types.InlineKeyboardButton("👤 Meu Perfil", callback_data="perfil"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="info_gift"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte")
    )
    return text, markup


@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        user_id = message.from_user.id
        nome = message.from_user.first_name or "Cliente"
        username = message.from_user.username or ""
        
        db.garantir_usuario(user_id, nome, username)
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
        f"📊 **Métricas Atuais:**\n"
        f"👥 Clientes: `{clientes}`\n"
        f"🛒 Vendas Realizadas: `{total_vendas}`\n"
        f"💰 Faturamento Total: `R$ {faturamento:.2f}`\n\n"
        f"⚙️ **Comandos Rápidos:**\n"
        f"• `!add [BIN]` *(Ex: !add 422061 e a lista embaixo)*\n"
        f"• `!dados` *(Lista de titulares)*\n"
        f"• `/limpar_estoque`\n"
        f"• `/gerar_gift [valor]`\n"
        f"• `/dar_saldo [user_id] [valor]`"
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")


# --- NOVO COMANDO EM TEXTO LIVRE (!add) PARA NÃO FALHAR NUNCA ---
@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith('!add'))
def cmd_add_gg_texto(message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "❌ Acesso negado.")
        return
    
    texto_bruto = message.text[4:].strip() # Remove '!add'
    if not texto_bruto:
        bot.reply_to(message, "⚠️ Uso correto:\n`!add 422061`\n*(Cole a lista de cartões logo abaixo)*", parse_mode="Markdown")
        return
    
    linhas = texto_bruto.replace('\r\n', '\n').split('\n')
    primeira_linha_palavras = linhas[0].strip().split()
    if not primeira_linha_palavras:
        bot.reply_to(message, "❌ Formato inválido.", parse_mode="Markdown")
        return

    possivel_bin = "".join(filter(str.isdigit, primeira_linha_palavras[0]))
    if len(possivel_bin) >= 6:
        bin6 = possivel_bin[:6]
    else:
        bot.reply_to(message, "❌ Informe uma BIN válida de 6 dígitos.", parse_mode="Markdown")
        return

    cartoes_para_adicionar = []
    
    if len(primeira_linha_palavras) > 1 and '|' in primeira_linha_palavras[1]:
        cartoes_para_adicionar.append(primeira_linha_palavras[1])
        
    for linha in linhas[1:]:
        linha = linha.strip()
        if not linha:
            continue
        if '|' in linha:
            cartoes_para_adicionar.append(linha)
        else:
            partes = linha.split()
            for p in partes:
                if '|' in p:
                    cartoes_para_adicionar.append(p)

    if not cartoes_para_adicionar:
        for linha in linhas[1:]:
            linha = linha.strip()
            if len(linha) > 10:
                cartoes_para_adicionar.append(linha)

    if not cartoes_para_adicionar:
        bot.reply_to(message, "❌ Nenhum cartão válido encontrado. Use o formato `num|mes|ano|cvv`.", parse_mode="Markdown")
        return

    # Consulta a API APENAS UMA VEZ para o lote inteiro
    bandeira, banco = consultar_bin(bin6)

    adicionados = 0
    for item in cartoes_para_adicionar:
        db.adicionar_estoque_item(categoria='gg', conteudo=item, bin=bin6, banco=banco, bandeira=bandeira)
        adicionados += 1

    relatorio = (
        f"✅ **Lote Adicionado com Sucesso!**\n\n"
        f"💳 **BIN:** `{bin6}`\n"
        f"🏷️ **Bandeira:** `{bandeira}`\n"
        f"🏦 **Banco:** `{banco}`\n"
        f"📦 **Quantidade:** `+{adicionados} Uni.`"
    )
    bot.reply_to(message, relatorio, parse_mode="Markdown")


@bot.message_handler(func=lambda message: message.text and message.text.lower().startswith('!dados'))
def cmd_add_dados_texto(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    texto_completo = message.text[6:].strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares logo abaixo.", parse_mode="Markdown")
        return
    
    linhas = texto_completo.replace('\r\n', '\n').split('\n')
    adicionados = 0
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        db.adicionar_dado_titular(linha)
        adicionados += 1

    bot.reply_to(message, f"✅ Sucesso! Cadastrados **{adicionados}** blocos de dados.", parse_mode="Markdown")


@bot.message_handler(commands=['limpar_estoque'])
def cmd_limpar_estoque(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    session = db.SessionLocal()
    try:
        session.execute(db.text("DELETE FROM estoque WHERE vendido = 0"))
        session.execute(db.text("DELETE FROM dados_titular WHERE usado = 0"))
        session.commit()
        bot.reply_to(message, "🧹 **Estoque limpo com sucesso!**", parse_mode="Markdown")
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro: {e}")
    finally:
        session.close()


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
    session = db.SessionLocal()
    try:
        novo_gift = db.GiftCard(codigo=codigo_gift, valor=valor, usado=0)
        session.add(novo_gift)
        session.commit()
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro: {e}")
        return
    finally:
        session.close()

    bot.reply_to(message, f"🎁 **Gift Gerado!**\nValor: R$ {valor:.2f}\nCódigo: `{codigo_gift}`", parse_mode="Markdown")


@bot.message_handler(commands=['resgatar'])
def cmd_resgatar(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o código. Ex: `/resgatar [codigo]`", parse_mode="Markdown")
        return

    codigo_informado = args[1].strip()
    session = db.SessionLocal()
    try:
        gift = session.query(db.GiftCard).filter_by(codigo=codigo_informado).first()
        if not gift or gift.usado == 1:
            bot.reply_to(message, "❌ Gift inválido ou já utilizado.")
            return

        gift.usado = 1
        user = session.query(db.Usuario).filter_by(user_id=user_id).first()
        if not user:
            db.garantir_usuario(user_id, message.from_user.first_name, message.from_user.username)
            user = session.query(db.Usuario).filter_by(user_id=user_id).first()

        user.saldo += gift.valor
        session.commit()
        bot.reply_to(message, f"🎉 **Resgate efetuado!** Adicionado R$ {gift.valor:.2f} ao seu saldo.", parse_mode="Markdown")
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro: {e}")
    finally:
        session.close()


@bot.message_handler(commands=['dar_saldo'])
def cmd_dar_saldo(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split()
        target_id = int(partes[1])
        valor = float(partes[2])
        
        session = db.SessionLocal()
        user = session.query(db.Usuario).filter_by(user_id=target_id).first()
        if user:
            user.saldo += valor
            session.commit()
            bot.reply_to(message, f"💰 Adicionado R$ {valor:.2f} para `{target_id}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Usuário não encontrado.", parse_mode="Markdown")
        session.close()
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
        bot.send_message(call.message.chat.id, "🎁 Para adicionar saldo, envie:\n`/resgatar [seu_codigo]`", parse_mode="Markdown")
        
    elif data == "menu_gg":
        bot.answer_callback_query(call.id)
        ggs = db.listar_estoque_gg_agrupado()
        if not ggs:
            bot.send_message(call.message.chat.id, "❌ Não há GGs disponíveis no momento.")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        bin_contagem = {}
        for bin_code, banco, bandeira, qtd in ggs:
            chave = (bin_code, banco, bandeira)
            bin_contagem[chave] = bin_contagem.get(chave, 0) + qtd

        for (bin_code, banco, bandeira), total_qtd in bin_contagem.items():
            texto_btn = f"💳 {bandeira} | {banco} ({bin_code}) • Estoque: {total_qtd}"
            markup.add(types.InlineKeyboardButton(texto_btn, callback_data=f"comprar_gg_{bin_code}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **Selecione a BIN Desejada:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        preco_gg = 20.0
        bot.answer_callback_query(call.id)
        
        status, resultado_gg, resultado_dados, banco_item, bandeira_item = db.realizar_compra_item_casado(user_id, 'gg', preco_gg, bin_v=bin_escolhida)
        
        if status == "ok":
            mensagem_entrega = (
                f"✅ **PEDIDO APROVADO COM SUCESSO!**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 **DADOS DO CARTÃO**\n"
                f"• **Info (Num|Val|CVV):** `{resultado_gg}`\n"
                f"• **Bandeira:** `{bandeira_item}`\n"
                f"• **Banco:** `{banco_item}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **DADOS DO TITULAR**\n"
                f"`{resultado_dados}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 *Guarde suas informações com segurança. Obrigado!*"
            )
            bot.send_message(call.message.chat.id, mensagem_entrega, parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Compra aprovada, mas os dados de titular em massa esgotaram.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta opção.")
            
    elif data == "voltar_net" or data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        
    else:
        bot.answer_callback_query(call.id, text="Seção indisponível.")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Iniciando bot em modo polling seguro e multi-thread...")
    bot.remove_webhook()
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error(f"Erro na conexão do bot: {e}")
            import time
            time.sleep(3)
