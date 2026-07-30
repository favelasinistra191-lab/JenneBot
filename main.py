"""
Arquivo Principal - JenneStoreBot
Gerenciamento completo do Bot do Telegram, Servidor Web Flask, Painel Admin,
Adição de GGs em massa, Adição de Dados em Massa, Streaming, eSIM e Gifts.
"""
import os
import logging
import threading
import time
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


# --- Função Multi-API de Consulta de BIN (3 APIs em cascata) ---
def consultar_bin(cartao_ou_bin):
    limpo = ''.join(filter(str.isdigit, str(cartao_ou_bin)))
    if len(limpo) < 6:
        return "DESCONHECIDO", "DESCONHECIDO"
    
    bin6 = limpo[:6]
    
    # 1ª Tentativa: Binlist.net
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=2.5, headers={'Accept-Version': '3'})
        if response.status_code == 200:
            data = response.json()
            banco = data.get("bank", {}).get("name")
            if banco:
                return bin6, banco.upper()
    except Exception:
        pass

    # 2ª Tentativa: Data Binlist Backup
    try:
        response = requests.get(f"https://data.binlist.net/{bin6}", timeout=2.5)
        if response.status_code == 200:
            data = response.json()
            banco = data.get("bank", {}).get("name")
            if banco:
                return bin6, banco.upper()
    except Exception:
        pass

    # 3ª Tentativa: API Alternativa
    try:
        response = requests.get(f"https://lookup.binlist.net/v1/{bin6}", timeout=2.5)
        if response.status_code == 200:
            data = response.json()
            banco = data.get("bank", {}).get("name")
            if banco:
                return bin6, banco.upper()
    except Exception:
        pass

    return bin6, "BANCO NÃO IDENTIFICADO"


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
        types.InlineKeyboardButton("💳 Comprar GG", callback_data="menu_gg"),
        types.InlineKeyboardButton("👤 Meu Perfil / Saldo", callback_data="perfil"),
        types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="info_gift"),
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
        f"⚙️ **Comandos de Gestão (Todos em Massa):**\n"
        f"• `/add_streaming [Empresa] [Login:Senha]`\n"
        f"• `/add_esim [Operadora] [QR_Code]`\n"
        f"• `/add_gg [Lista gigante de GGs]`\n"
        f"• `/add_dados [Lista gigante de Dados do Titular]`\n"
        f"• `/gerar_gift [valor]`\n"
        f"• `/dar_saldo [user_id] [valor]`"
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
        bot.reply_to(message, f"❌ Erro ao adicionar streaming: {e}")


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
        bot.reply_to(message, f"❌ Erro ao adicionar eSIM: {e}")


@bot.message_handler(commands=['add_gg'])
def cmd_add_gg(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    texto_completo = message.text.replace('/add_gg', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de GGs junto com o comando.\nExemplo:\n`/add_gg [sua lista grande aqui]`", parse_mode="Markdown")
        return
    
    linhas = texto_completo.split('\n')
    total_adicionadas = 0
    resumo_bancos = {}
    
    status_msg = bot.reply_to(message, f"⏳ Processando e consultando BINs de {len(linhas)} linhas... Aguarde um momento.")

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        
        bin6, banco = consultar_bin(linha)
        db.adicionar_estoque_item(categoria='gg', conteudo=linha, bin=bin6, banco=banco)
        
        total_adicionadas += 1
        
        if banco not in resumo_bancos:
            resumo_bancos[banco] = {}
        if bin6 not in resumo_bancos[banco]:
            resumo_bancos[banco][bin6] = 0
        resumo_bancos[banco][bin6] += 1
        
        time.sleep(0.7)

    relatorio = f"✅ **Sucesso! Total adicionado: {total_adicionadas} GGs**\n\n📊 **Resumo por Banco/BIN:**\n"
    for banco, bins in resumo_bancos.items():
        for bin_code, qtd in bins.items():
            relatorio += f"• `{bin_code}` | {banco} | **{qtd} Uni.**\n"

    try:
        bot.edit_message_text(relatorio, chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, relatorio, parse_mode="Markdown")


# --- NOVO: ADICIONAR DADOS DO TITULAR EM MASSA ---
@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares em massa.\nExemplo:\n`/add_dados [linha 1]\n[linha 2]`", parse_mode="Markdown")
        return
    
    linhas = texto_completo.split('\n')
    adicionados = 0

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        db.adicionar_dado_titular(linha)
        adicionados += 1

    bot.reply_to(message, f"✅ Sucesso! Foram cadastrados **{adicionados}** blocos de dados de titular em massa.", parse_mode="Markdown")


@bot.message_handler(commands=['gerar_gift'])
def cmd_gerar_gift(message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "❌ Você não tem permissão para usar este comando.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use o formato correto:\n`/gerar_gift [valor]`\nExemplo: `/gerar_gift 50`", parse_mode="Markdown")
        return

    try:
        valor = float(args[1].replace(',', '.'))
    except ValueError:
        bot.reply_to(message, "❌ Valor inválido. Insira apenas números (Ex: `/gerar_gift 100`).", parse_mode="Markdown")
        return

    codigo_gift = f"GIFT-{uuid.uuid4().hex[:8].upper()}"

    session = db.SessionLocal()
    try:
        novo_gift = db.GiftCard(codigo=codigo_gift, valor=valor, usado=0)
        session.add(novo_gift)
        session.commit()
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro ao criar o gift card no banco: {e}")
        return
    finally:
        session.close()

    bot.reply_to(message, 
        f"🎁 **Gift Card Gerado com Sucesso!**\n\n"
        f"💰 **Valor:** R$ {valor:.2f}\n"
        f"🔑 **Código:** `{codigo_gift}`\n\n"
        f"Envie o comando para o cliente resgatar: `/resgatar {codigo_gift}`", 
        parse_mode="Markdown"
    )


@bot.message_handler(commands=['resgatar'])
def cmd_resgatar(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Informe o código do gift card.\nExemplo: `/resgatar GIFT-A1B2C3D4`", parse_mode="Markdown")
        return

    codigo_informado = args[1].strip()

    session = db.SessionLocal()
    try:
        gift = session.query(db.GiftCard).filter_by(codigo=codigo_informado).first()

        if not gift:
            bot.reply_to(message, "❌ Código de Gift Card inválido ou não encontrado.")
            return

        if gift.usado == 1:
            bot.reply_to(message, "❌ Este Gift Card já foi resgatado anteriormente.")
            return

        gift.usado = 1

        user = session.query(db.Usuario).filter_by(user_id=user_id).first()
        if not user:
            db.garantir_usuario(user_id, message.from_user.first_name, message.from_user.username)
            user = session.query(db.Usuario).filter_by(user_id=user_id).first()

        user.saldo += gift.valor
        session.commit()

        bot.reply_to(message, 
            f"🎉 **Resgate realizado com sucesso!**\n\n"
            f"💰 Adicionado ao seu saldo: **R$ {gift.valor:.2f}**\n"
            f"💳 Saldo atualizado com sucesso.", 
            parse_mode="Markdown"
        )
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Ocorreu um erro ao processar o resgate: {e}")
    finally:
        session.close()


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


# --- Callbacks do Menu e Compras (Com Entrega Casada Profissional) ---
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
        
    elif data == "info_gift":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🎁 Para resgatar um Gift Card, digite o comando:\n`/resgatar [seu_codigo]`", parse_mode="Markdown")
        
    elif data == "menu_gg":
        bot.answer_callback_query(call.id)
        ggs = db.listar_estoque_gg_agrupado()
        if not ggs:
            bot.send_message(call.message.chat.id, "❌ Não há GGs disponíveis no momento.")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        bin_contagem = {}
        for bin_code, banco, qtd in ggs:
            bin_contagem[bin_code] = bin_contagem.get(bin_code, 0) + qtd

        for bin_code, total_qtd in bin_contagem.items():
            texto_btn = f"💳 BIN: {bin_code} | Estoque: {total_qtd} Uni."
            markup.add(types.InlineKeyboardButton(texto_btn, callback_data=f"comprar_gg_{bin_code}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **Escolha a BIN desejada abaixo:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        preco_gg = 20.0  # Preço padrão da GG (ajuste se precisar)
        bot.answer_callback_query(call.id)
        
        status, resultado = db.realizar_compra_item(user_id, 'gg', preco_gg, bin_v=bin_escolhida)
        if status == "ok":
            # Formatação Profissional da Entrega Casada
            mensagem_entrega = (
                f"✅ **COMPRA APROVADA COM SUCESSO!**\n\n"
                f"💳 **Dados do Cartão (GG):**\n`{resultado}`\n\n"
                f"🔒 *Guarde seus dados com segurança. Aproveite sua compra!*"
            )
            bot.send_message(call.message.chat.id, mensagem_entrega, parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente para realizar esta compra. Resgate um Gift Card ou adicione saldo.")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN no momento.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        
    else:
        bot.answer_callback_query(call.id, text="Seção em desenvolvimento ou indisponível.")


# --- Execução Principal ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Iniciando bot em modo polling direto...")
    bot.remove_webhook()
    bot.polling(none_stop=True, interval=0, timeout=20)
