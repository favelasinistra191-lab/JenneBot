"""
Arquivo Principal - JenneStoreBot
Gerenciamento completo do Bot do Telegram, Servidor Web Flask, Painel Admin,
Adição de GGs em massa com BIN fixa, Limpeza de Estoque, Streaming, eSIM, Gifts e Entrega Casada.
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


# --- Função para Identificar Bandeira e Banco pela BIN ---
def consultar_bin(bin6):
    bin6 = ''.join(filter(str.isdigit, str(bin6)))[:6]
    if len(bin6) < 6:
        return "DESCONHECIDO", "BANCO DESCONHECIDO"
    
    # Identifica a Bandeira automaticamente pelos primeiros dígitos
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

    # Consulta o Banco na API (Apenas 1 vez para o lote)
    banco = "BANCO NÃO IDENTIFICADO"
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=3, headers={'Accept-Version': '3'})
        if response.status_code == 200:
            data = response.json()
            b = data.get("bank", {}).get("name")
            if b:
                banco = b.upper()
    except Exception:
        try:
            response = requests.get(f"https://data.binlist.net/{bin6}", timeout=3)
            if response.status_code == 200:
                data = response.json()
                b = data.get("bank", {}).get("name")
                if b:
                    banco = b.upper()
        except Exception:
            pass

    return bandeira, banco


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
        f"• `/add_streaming [Empresa] [Login:Senha]`\n"
        f"• `/add_esim [Operadora] [QR_Code]`\n"
        f"• `/add_gg [BIN]` (Cole a lista na mesma mensagem)\n"
        f"• `/add_dados` (Cole a lista de dados dos titulares em massa)\n"
        f"• `/limpar_estoque` (Zera GGs e Dados de Teste)\n"
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


# --- COMANDO /ADD_GG OTIMIZADO COM BIN FIXA ---
@bot.message_handler(commands=['add_gg'])
def cmd_add_gg(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    texto_original = message.text.replace('/add_gg', '').strip()
    if not texto_original:
        bot.reply_to(message, "⚠️ Uso correto:\n`/add_gg [BIN]`\nCole a lista de GGs logo abaixo na mesma mensagem.\nExemplo:\n`/add_gg 422061`\n`num|mes|ano|cvv`", parse_mode="Markdown")
        return
    
    linhas = texto_original.split('\n')
    primeira_linha_args = linhas[0].strip().split()
    bin_informada = "".join(filter(str.isdigit, primeira_linha_args[0])) if primeira_linha_args else ""
    
    if len(bin_informada) < 6:
        bot.reply_to(message, "❌ Informe uma BIN válida de 6 dígitos logo após o comando (Ex: `/add_gg 422061`).", parse_mode="Markdown")
        return
    
    bin6 = bin_informada[:6]
    
    if len(primeira_linha_args) == 1 and len(linhas) > 1:
        linhas_cartoes = linhas[1:]
    else:
        linhas_cartoes = linhas

    status_msg = bot.reply_to(message, f"⏳ Consultando bandeira e banco da BIN `{bin6}`...", parse_mode="Markdown")
    bandeira, banco = consultar_bin(bin6)

    adicionados = 0
    for linha in linhas_cartoes:
        linha = linha.strip()
        if not linha or linha == bin6 or (len(linha) == 6 and linha.isdigit()):
            continue
            
        db.adicionar_estoque_item(categoria='gg', conteudo=linha, bin=bin6, banco=banco, bandeira=bandeira)
        adicionados += 1

    if adicionados == 0:
        bot.edit_message_text("❌ Nenhum cartão válido encontrado na lista.", chat_id=message.chat.id, message_id=status_msg.message_id)
        return

    relatorio = (
        f"✅ **Lote de GGs Adicionado com Sucesso!**\n\n"
        f"💳 **BIN:** `{bin6}`\n"
        f"🏷️ **Bandeira:** `{bandeira}`\n"
        f"🏦 **Banco:** `{banco}`\n"
        f"📦 **Quantidade:** `+{adicionados} Uni.`"
    )

    try:
        bot.edit_message_text(relatorio, chat_id=message.chat.id, message_id=status_msg.message_id, parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, relatorio, parse_mode="Markdown")


@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares em massa logo abaixo do comando.", parse_mode="Markdown")
        return
    
    linhas = texto_completo.split('\n')
    adicionados = 0

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        db.adicionar_dado_titular(linha)
        adicionados += 1

    bot.reply_to(message, f"✅ Sucesso! Cadastrados **{adicionados}** blocos de dados de titular em massa.", parse_mode="Markdown")


# --- NOVO: COMANDO PARA LIMPAR ESTOQUE DE TESTE ---
@bot.message_handler(commands=['limpar_estoque'])
def cmd_limpar_estoque(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    session = db.SessionLocal()
    try:
        # Apaga todos os itens de estoque não vendidos (GGs, Streaming, eSIM) e Dados de Titular
        session.execute(db.text("DELETE FROM estoque WHERE vendido = 0"))
        session.execute(db.text("DELETE FROM dados_titular WHERE usado = 0"))
        session.commit()
        bot.reply_to(message, "🧹 **Estoque limpo com sucesso!** Todos os cartões e dados de teste não vendidos foram removidos da base.", parse_mode="Markdown")
    except Exception as e:
        session.rollback()
        bot.reply_to(message, f"❌ Erro ao limpar o estoque: {e}")
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
        bot.reply_to(message, f"🎉 **Resgate com sucesso!** Adicionado R$ {gift.valor:.2f} ao seu saldo.", parse_mode="Markdown")
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


# --- Callbacks e Compra com Entrega Casada Profissional ---
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
        bot.send_message(call.message.chat.id, "🎁 Para resgatar, envie: `/resgatar [codigo]`", parse_mode="Markdown")
        
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
            texto_btn = f"💳 {bandeira} | {banco} ({bin_code}) - Estoque: {total_qtd}"
            markup.add(types.InlineKeyboardButton(texto_btn, callback_data=f"comprar_gg_{bin_code}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Voltar ao Menu", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "💳 **Escolha a BIN / Banco desejado abaixo:**", reply_markup=markup, parse_mode="Markdown")
        
    elif data.startswith("comprar_gg_"):
        bin_escolhida = data.split("_")[2]
        preco_gg = 20.0
        bot.answer_callback_query(call.id)
        
        status, resultado_gg, resultado_dados, banco_item, bandeira_item = db.realizar_compra_item_casado(user_id, 'gg', preco_gg, bin_v=bin_escolhida)
        
        if status == "ok":
            mensagem_entrega = (
                f"✅ **COMPRA APROVADA COM SUCESSO!**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 **DADOS DO CARTÃO (GG)**\n"
                f"• **Número / Val / CVV:** `{resultado_gg}`\n"
                f"• **Bandeira:** `{bandeira_item}`\n"
                f"• **Banco:** `{banco_item}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **DADOS DO TITULAR**\n"
                f"`{resultado_dados}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 *Guarde seus dados com segurança. Bom proveito!*"
            )
            bot.send_message(call.message.chat.id, mensagem_entrega, parse_mode="Markdown")
        elif status == "saldo_insuficiente":
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente para realizar esta compra.")
        elif status == "falta_dados":
            bot.send_message(call.message.chat.id, "⚠️ Compra aprovada para a GG, mas os dados do titular em massa acabaram. Avise o admin para abastecer o `/add_dados`!")
        else:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta BIN no momento.")
            
    elif data == "voltar_menu":
        bot.answer_callback_query(call.id)
        text, markup = main_menu(user_id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        
    else:
        bot.answer_callback_query(call.id, text="Seção indisponível.")


# --- Execução Principal ---
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    LOG.info("Iniciando bot em modo polling direto...")
    bot.remove_webhook()
    bot.polling(none_stop=True, interval=0, timeout=20)
