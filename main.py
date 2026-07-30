"""
Arquivo Principal - JenneStoreBot
Gerenciamento do Bot do Telegram e Servidor Web Flask (Anti-Sleep)
"""
import os
import logging
import threading
from flask import Flask
import telebot
from telebot import types

import config
import database as db

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("JenneBot")

# Inicialização do Bot e Banco
bot = telebot.TeleBot(config.TOKEN)
db.criar_tabelas()

# Servidor Flask para manter o bot acordado (Anti-Sleep)
app = Flask(__name__)

@app.route('/')
def home():
    return "JenneStoreBot está rodando e acordado!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# --- Funções de Menu ---
def main_menu(user_id):
    db.garantir_usuario(user_id, "", "")
    saldo = db.obter_saldo(user_id)
    
    text = (
        f"🌟 **Bem-vindo à JenneStore** 🌟\n\n"
        f"💳 **Seu ID:** `{user_id}`\n"
        f"💰 **Seu Saldo:** `R$ {saldo:.2f}`\n\n"
        f"Escolha uma das opções abaixo no menu:"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 Comprar Streaming", callback_data="cat_streaming"),
        types.InlineKeyboardButton("📱 Comprar eSIM", callback_data="cat_esim"),
        types.InlineKeyboardButton("💳 Comprar GG", callback_data="cat_gg"),
        types.InlineKeyboardButton("👤 Meu Perfil / Saldo", callback_data="perfil"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="gift"),
        types.InlineKeyboardButton("📞 Suporte", callback_data="suporte")
    )
    return text, markup


# --- Handlers de Mensagem e Comandos ---
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    nome = message.from_user.first_name or "Cliente"
    username = message.from_user.username or ""
    
    db.garantir_usuario(user_id, nome, username)
    text, markup = main_menu(user_id)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")


# --- COMANDOS EXCLUSIVOS DO ADMINISTRADOR (DONO) ---
@bot.message_handler(commands=['admin', 'painel'])
def cmd_admin(message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "❌ Você não tem permissão para acessar o painel administrativo.")
        return
    
    total_vendas, faturamento, clientes = db.obter_dados_relatorio()
    
    texto = (
        f"👑 **Painel do Dono - JenneStore**\n\n"
        f"📊 **Estatísticas:**\n"
        f"👥 Clientes: `{clientes}`\n"
        f"🛒 Vendas: `{total_vendas}`\n"
        f"💰 Faturamento: `R$ {faturamento:.2f}`\n\n"
        f"⚙️ **Comandos de Gestão:**\n"
        f"• `/add_estoque [categoria] [conteudo]`\n"
        f"• `/add_gg [nome] [cpf_criptografado]`\n"
        f"• `/add_gift [codigo] [valor]`\n"
        f"• `/dar_saldo [user_id] [valor]`"
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")


@bot.message_handler(commands=['add_estoque'])
def cmd_add_estoque(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split(maxsplit=2)
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/add_estoque [categoria] [conteudo]`", parse_mode="Markdown")
            return
        
        categoria = partes[1].lower()
        conteudo = partes[2]
        db.adicionar_estoque(categoria=categoria, conteudo=conteudo)
        bot.reply_to(message, f"✅ Item adicionado com sucesso em `{categoria}`!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao adicionar estoque: {e}")


@bot.message_handler(commands=['add_gg'])
def cmd_add_gg(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split(maxsplit=2)
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/add_gg [nome] [cpf]`", parse_mode="Markdown")
            return
        
        nome = partes[1]
        cpf = partes[2]
        db.adicionar_dados_gg(nome=nome, cpf_encrypted=cpf)
        bot.reply_to(message, f"✅ Dados GG de `{nome}` adicionados com sucesso!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao adicionar GG: {e}")


@bot.message_handler(commands=['add_gift'])
def cmd_add_gift(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split()
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/add_gift [codigo] [valor]`", parse_mode="Markdown")
            return
        
        codigo = partes[1]
        valor = float(partes[2])
        
        session = db.SessionLocal()
        novo_gift = db.GiftCard(codigo=codigo, valor=valor, usado=0)
        session.add(novo_gift)
        session.commit()
        session.close()
        
        bot.reply_to(message, f"🎁 Gift Card `{codigo}` de `R$ {valor:.2f}` criado!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao criar gift card: {e}")


@bot.message_handler(commands=['dar_saldo'])
def cmd_dar_saldo(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    try:
        partes = message.text.split()
        if len(partes) < 3:
            bot.reply_to(message, "⚠️ Uso: `/dar_saldo [user_id] [valor]`", parse_mode="Markdown")
            return
        
        target_id = int(partes[1])
        valor = float(partes[2])
        
        session = db.SessionLocal()
        user = session.query(db.Usuario).filter_by(user_id=target_id).first()
        if user:
            user.saldo += valor
            session.commit()
            bot.reply_to(message, f"💰 Adicionado `R$ {valor:.2f}` para o usuário `{target_id}`. Novo saldo: `R$ {user.saldo:.2f}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"❌ Usuário `{target_id}` não encontrado no banco.", parse_mode="Markdown")
        session.close()
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao dar saldo: {e}")


# --- Callbacks do Menu ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "perfil":
        saldo = db.obter_saldo(user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"👤 **Seu Perfil**\nID: `{user_id}`\nSaldo: `R$ {saldo:.2f}`", parse_mode="Markdown")
    elif data == "suporte":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📞 Para suporte, entre em contato com o administrador.", parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, text="Seção em desenvolvimento ou indisponível.")


# --- Execução Principal ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Iniciando bot em modo polling direto...")
    bot.remove_webhook()
    bot.polling(none_stop=True, interval=0, timeout=20)
