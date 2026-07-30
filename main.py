"""
Arquivo Principal - JenneStoreBot
Gerenciamento completo de comandos, painel admin e fluxo de vendas automatizado.
"""
import os
import logging
import threading
from flask import Flask
import telebot
from telebot import types
import requests

import config
import database as db

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("JenneBot")

bot = telebot.TeleBot(config.TOKEN)
db.criar_tabelas()

app = Flask(__name__)

@app.route('/')
def home():
    return "JenneStoreBot está rodando e acordado!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# Função para consultar BIN automaticamente via API pública
def consultar_bin(cartao_ou_bin):
    limpo = ''.join(filter(str.isdigit, str(cartao_ou_bin)))
    if len(limpo) < 6:
        return "DESCONHECIDO", "DESCONHECIDO"
    
    bin6 = limpo[:6]
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            banco = data.get("bank", {}).get("name", "Banco Desconhecido").upper()
            return bin6, banco
    except Exception:
        pass
    return bin6, "BANCO NÃO IDENTIFICADO"


# --- Menus ---
def main_menu(user_id):
    db.garantir_usuario(user_id, "", "")
    saldo = db.obter_saldo(user_id)
    
    text = (
        f"🌟 **Bem-vindo à JenneStore** 🌟\n\n"
        f"💳 **Seu ID:** `{user_id}`\n"
        f"💰 **Seu Saldo:** `R$ {saldo:.2f}`\n\n"
        f"Escolha abaixo o que deseja adquirir:"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📺 Streaming", callback_data="menu_streaming"),
        types.InlineKeyboardButton("📱 eSIM", callback_data="menu_esim"),
        types.InlineKeyboardButton("💳 GG (Cartões)", callback_data="menu_gg"),
        types.InlineKeyboardButton("👤 Meu Perfil", callback_data="perfil"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="gift"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte")
    )
    return text, markup


@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    nome = message.from_user.first_name or "Cliente"
    username = message.from_user.username or ""
    
    db.garantir_usuario(user_id, nome, username)
    text, markup = main_menu(user_id)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")


# --- COMANDOS DO ADMIN ---
@bot.message_handler(commands=['admin', 'painel'])
def cmd_admin(message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "❌ Acesso negado.")
        return
    
    total_vendas, faturamento, clientes = db.obter_dados_relatorio()
    texto = (
        f"👑 **Painel do Dono - JenneStore**\n\n"
        f"📊 Clientes: `{clientes}` | Vendas: `{total_vendas}` | Faturamento: `R$ {faturamento:.2f}`\n\n"
        f"⚙️ **Comandos de Cadastro:**\n"
        f"• `/add_streaming [Empresa] [Login:Senha]`\n"
        f"• `/add_esim [Operadora] [QR_Code/Info]`\n"
        f"• `/add_gg [Cartao|Val|CVV]` (Detecta BIN e Banco automático!)\n"
        f"• `/add_dados [Nome, CPF, etc]` (Dados cadastrais que saem casados com a GG)\n"
        f"• `/add_gift [Codigo] [Valor]`\n"
        f"• `/dar_saldo [User_ID] [Valor]`"
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")


@bot.message_handler(commands=['add_streaming'])
def cmd_add_streaming(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split(maxsplit=2)
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/add_streaming [Empresa] [Login:Senha]`", parse_mode="Markdown")
            return
        db.adicionar_estoque_item(categoria='streaming', sub_tipo=partes[1].upper(), conteudo=partes[2])
        bot.reply_to(message, f"✅ Streaming `{partes[1].upper()}` adicionado com sucesso!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=['add_esim'])
def cmd_add_esim(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split(maxsplit=2)
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/add_esim [Operadora] [QR_Code_ou_Link]`", parse_mode="Markdown")
            return
        db.adicionar_estoque_item(categoria='esim', sub_tipo=partes[1].upper(), conteudo=partes[2])
        bot.reply_to(message, f"✅ eSIM da operadora `{partes[1].upper()}` adicionado!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=['add_gg'])
def cmd_add_gg(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split(maxsplit=1)
        if len(partes) < 2:
            bot.reply_to(message, "⚠️ Uso: `/add_gg [Cartao|Val|CVV]`", parse_mode="Markdown")
            return
        
        cartao_info = partes[1].strip()
        bin6, banco = consultar_bin(cartao_info)
        
        db.adicionar_estoque_item(categoria='gg', conteudo=cartao_info, bin=bin6, banco=banco)
        bot.reply_to(message, f"✅ GG adicionada!\n🔍 BIN: `{bin6}`\n🏦 Banco: `{banco}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split(maxsplit=1)
        if len(partes) < 2:
            bot.reply_to(message, "⚠️ Uso: `/add_dados [Nome, CPF, Endereço...]`", parse_mode="Markdown")
            return
        db.adicionar_dado_titular(partes[1])
        bot.reply_to(message, "✅ Dados do titular cadastrados! (Vão ser entregues automaticamente junto com a GG).", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=['add_gift'])
def cmd_add_gift(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split()
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/add_gift [codigo] [valor]`", parse_mode="Markdown")
            return
        session = db.SessionLocal()
        session.add(db.GiftCard(codigo=partes[1], valor=float(partes[2]), usado=0))
        session.commit()
        session.close()
        bot.reply_to(message, f"🎁 Gift Card `{partes[1]}` de `R$ {float(partes[2]):.2f}` criado!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


@bot.message_handler(commands=['dar_saldo'])
def cmd_dar_saldo(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split()
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/dar_saldo [user_id] [valor]`", parse_mode="Markdown")
            return
        session = db.SessionLocal()
        user = session.query(db.Usuario).filter_by(user_id=int(partes[1])).first()
        if user:
            user.saldo += float(partes[2])
            session.commit()
            bot.reply_to(message, f"💰 Adicionado R$ {float(partes[2]):.2f} para o usuário `{partes[1]}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Usuário não encontrado.", parse_mode="Markdown")
        session.close()
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")


# --- Callbacks e Navegação ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "perfil":
        saldo = db.obter_saldo(user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"👤 **Seu Perfil**\nID: `{user_id}`\nSaldo: `R$ {saldo:.2f}`", parse_mode="Markdown")
        
    elif data == "suporte":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📞 Entre em contato com o suporte do administrador.", parse_mode="Markdown")
        
    elif data == "menu_gg":
        bot.answer_callback_query(call.id)
        ggs = db.listar_estoque_gg_agrupado()
        if not ggs:
            bot.send_message(call.message.chat.id, "❌ Não há GGs disponíveis no momento.")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for bin_code, banco, qtd in ggs:
            # Formato solicitado: 406669 | 100 Uni. (com banco ao lado)
            texto_btn = f"{bin_code} | {banco} | {qtd} Uni."
            markup.add(types.InlineKeyboardButton(texto_btn, callback_data=f"comprar_gg_{bin_code}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **Escolha a BIN / Banco desejada:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        preco_gg = 20.0  # Defina o preço padrão da GG aqui se quiser ajustar
        bot.answer_callback_query(call.id)
        
        status, resultado = db.realizar_compra_item(user_id, 'gg', preco_gg, bin_v=bin_escolhida)
        if status == "ok":
            bot.send_message(call.message.chat.id, f"✅ **Compra realizada com sucesso!**\n\n{resultado}", parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente para realizar esta compra.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        
    else:
        bot.answer_callback_query(call.id, text="Seção em construção.")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Iniciando bot em modo polling direto...")
    bot.remove_webhook()
    bot.polling(none_stop=True, interval=0, timeout=20)
