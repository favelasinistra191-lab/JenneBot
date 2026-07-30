"""
Arquivo Principal - JenneStoreBot
Versão Corrigida e Blindada para Render
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

ADMIN_ESTADO = {}

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
        f"📊 Clientes: `{clientes}` | Vendas: `{total_vendas}` | Faturamento: `R$ {faturamento:.2f}`\n\n"
        f"⚙️ **Comando de Estoque:**\n"
        f"• Digite `/add_gg 422061` e depois mande só a lista."
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")


# ETAPA 1: DIGITA O COMANDO E A BIN
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
    
    ADMIN_ESTADO[message.from_user.id] = {
        "bin": bin6,
        "banco": banco,
        "bandeira": bandeira
    }

    texto_resposta = (
        f"🔍 **BIN Registrada!**\n\n"
        f"💳 **BIN:** `{bin6}`\n"
        f"🏷️ **Bandeira:** `{bandeira}`\n"
        f"🏦 **Banco:** `{banco}`\n\n"
        f"👇 **AGORA MANDE APENAS A LISTA DE CARTÕES** (Sem digitar comandos, só cole a lista abaixo)."
    )
    bot.reply_to(message, texto_resposta, parse_mode="Markdown")


# ETAPA 2: RECEBE APENAS A LISTA (SEM COMANDOS)
@bot.message_handler(func=lambda message: message.from_user.id in ADMIN_ESTADO and not message.text.startswith('/'))
def cmd_add_gg_etapa2(message):
    admin_id = message.from_user.id
    dados_bin = ADMIN_ESTADO.pop(admin_id, None)
    if not dados_bin:
        return

    bin6 = dados_bin["bin"]
    banco = dados_bin["banco"]
    bandeira = dados_bin["bandeira"]

    texto_bruto = message.text.strip()
    linhas = texto_bruto.replace('\r\n', '\n').split('\n')
    
    cartoes_para_adicionar = []
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        for parte in linha.split():
            if '|' in parte:
                cartoes_para_adicionar.append(parte.strip())

    if not cartoes_para_adicionar:
        for linha in linhas:
            linha = linha.strip()
            if len(linha) > 10:
                cartoes_para_adicionar.append(linha)

    if not cartoes_para_adicionar:
        bot.reply_to(message, "❌ Nenhum cartão válido encontrado com pipe `|`. Envie novamente a lista correta.")
        return

    adicionados = 0
    for item in cartoes_para_adicionar:
        db.adicionar_estoque_item(categoria='gg', conteudo=item, bin=bin6, banco=banco, bandeira=bandeira)
        adicionados += 1

    bot.reply_to(
        message, 
        f"✅ **Estoque Atualizado com Sucesso!**\n\n"
        f"💳 **BIN:** `{bin6}`\n"
        f"📦 **Adicionados:** `+{adicionados} Uni.`\n"
        f"🔄 *Os itens foram somados perfeitamente no menu de vendas!*", 
        parse_mode="Markdown"
    )


@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares logo abaixo.", parse_mode="Markdown")
        return
    linhas = texto_completo.replace('\r\n', '\n').split('\n')
    adicionados = 0
    for linha in linhas:
        if linha.strip():
            db.adicionar_dado_titular(linha.strip())
            adicionados += 1
    bot.reply_to(message, f"✅ Sucesso! Cadastrados {adicionados} dados de titulares.", parse_mode="Markdown")


@bot.message_handler(commands=['limpar_estoque'])
def cmd_limpar_estoque(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    session = db.SessionLocal()
    try:
        from sqlalchemy import text
        session.execute(text("DELETE FROM estoque WHERE vendido = 0"))
        session.execute(text("DELETE FROM dados_titular WHERE usado = 0"))
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
        from sqlalchemy import text
        session.execute(text("INSERT INTO gift_cards (codigo, valor, usado) VALUES (:c, :v, 0)"), {"c": codigo_gift, "v": valor})
        session.commit()
        bot.reply_to(message, f"🎁 **Gift Gerado!**\nValor: R$ {valor:.2f}\nCódigo: `{codigo_gift}`", parse_mode="Markdown")
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro: {e}")
    finally:
        session.close()


@bot.message_handler(commands=['resgatar'])
def cmd_resgatar(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o código. Ex: `/resgatar [codigo]`", parse_mode="Markdown")
        return
    codigo = args[1].strip()
    session = db.SessionLocal()
    try:
        from sqlalchemy import text
        res = session.execute(text("SELECT id, valor, usado FROM gift_cards WHERE codigo = :c"), {"c": codigo}).fetchone()
        if not res or res[2] == 1:
            bot.reply_to(message, "❌ Gift inválido ou já utilizado.")
            return
        gift_id, valor = res[0], res[1]
        session.execute(text("UPDATE gift_cards SET usado = 1 WHERE id = :id"), {"id": gift_id})
        session.execute(text("UPDATE usuarios SET saldo = saldo + :v WHERE user_id = :u"), {"v": valor, "u": user_id})
        session.commit()
        bot.reply_to(message, f"🎉 **Resgate efetuado!** Adicionado R$ {valor:.2f} ao seu saldo.", parse_mode="Markdown")
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro: {e}")
    finally:
        session.close()


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
        for bin_code, banco, bandeira, total_qtd in ggs:
            texto_btn = f"💳 {bandeira} | {banco} ({bin_code}) • Estoque: {total_qtd}"
            markup.add(types.InlineKeyboardButton(texto_btn, callback_data=f"comprar_gg_{bin_code}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **Selecione a BIN Desejada:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        bot.answer_callback_query(call.id)
        
        status, res_gg, res_dados, banco_item, bandeira_item = db.realizar_compra_item_casado(user_id, 'gg', 20.0, bin_v=bin_escolhida)
        
        if status == "ok":
            msg = (
                f"✅ **PEDIDO APROVADO!**\n\n"
                f"💳 **CARTÃO:** `{res_gg}`\n"
                f"🏷️ **Bandeira/Banco:** {bandeira_item} | {banco_item}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **TITULAR:**\n`{res_dados}`"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Estoque de dados de titular esgotado.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Bot rodando...")
    bot.remove_webhook()
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=30)
        except Exception as e:
            LOG.error(f"Erro: {e}")
            import time
            time.sleep(3)
