"""
Arquivo Principal - JenneStoreBot
Versão Definitiva Completa: Preços Ajustados + Recibo Profissional + Gift com Link
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


# ==========================================
# SISTEMA DE ABASTECIMENTO EM 2 ETAPAS (GG)
# ==========================================
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
        "tipo": "gg",
        "bin": bin6,
        "banco": banco,
        "bandeira": bandeira
    }

    bot.reply_to(
        message, 
        f"🔍 **BIN Registrada!**\n\n"
        f"💳 **BIN:** `{bin6}` | **Bandeira:** `{bandeira}` | **Banco:** `{banco}`\n\n"
        f"👇 **AGORA MANDE APENAS A LISTA DE CARTÕES** (cole direto abaixo sem comandos).", 
        parse_mode="Markdown"
    )


# ==========================================
# SISTEMA DE ABASTECIMENTO EM 2 ETAPAS (STREAMING)
# ==========================================
@bot.message_handler(commands=['add_streaming'])
def cmd_add_streaming_etapa1(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    
    nome_streaming = message.text.replace('/add_streaming', '').strip().upper()
    if not nome_streaming:
        bot.reply_to(message, "⚠️ Informe o nome. Ex: `/add_streaming NETFLIX`", parse_mode="Markdown")
        return
    
    ADMIN_ESTADO[message.from_user.id] = {
        "tipo": "streaming",
        "nome_streaming": nome_streaming
    }

    bot.reply_to(
        message, 
        f"🎬 **Streaming Configurado: `{nome_streaming}`**\n\n"
        f"👇 **AGORA MANDE APENAS A LISTA DE CONTAS** (cole direto abaixo).", 
        parse_mode="Markdown"
    )


# ==========================================
# OUVINTE ÚNICO PARA A ETAPA 2 (GG OU STREAMING)
# ==========================================
@bot.message_handler(func=lambda message: message.from_user.id in ADMIN_ESTADO and not message.text.startswith('/'))
def processar_etapa2(message):
    admin_id = message.from_user.id
    estado = ADMIN_ESTADO.pop(admin_id, None)
    if not estado:
        return

    tipo = estado.get("tipo")
    texto_bruto = message.text.strip()
    linhas = texto_bruto.replace('\r\n', '\n').split('\n')
    
    if tipo == "gg":
        bin6 = estado["bin"]
        banco = estado["banco"]
        bandeira = estado["bandeira"]
        
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

        adicionados = 0
        for item in cartoes:
            db.adicionar_estoque_item(categoria='gg', conteudo=item, bin=bin6, banco=banco, bandeira=bandeira)
            adicionados += 1

        bot.reply_to(message, f"✅ **Estoque Atualizado!**\n\n💳 **BIN:** `{bin6}`\n📦 **Adicionados:** `+{adicionados} GGs`", parse_mode="Markdown")

    elif tipo == "streaming":
        nome_streaming = estado["nome_streaming"]
        
        contas = [l.strip() for l in linhas if l.strip()]
        if not contas:
            bot.reply_to(message, "❌ Nenhuma conta válida encontrada. Envie novamente.")
            return

        adicionados = 0
        for conta in contas:
            db.adicionar_estoque_item(categoria='streaming', conteudo=conta, bin='000000', banco='GERAL', bandeira=nome_streaming)
            adicionados += 1

        bot.reply_to(message, f"✅ **Estoque Atualizado!**\n\n🎬 **Streaming:** `{nome_streaming}`\n📦 **Adicionadas:** `+{adicionados} Contas`", parse_mode="Markdown")


# --- OUTROS COMANDOS DIRETOS ---
@bot.message_handler(commands=['add_dados'])
def cmd_add_dados(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    texto_completo = message.text.replace('/add_dados', '').strip()
    if not texto_completo:
        bot.reply_to(message, "⚠️ Envie a lista de dados dos titulares logo após o comando.", parse_mode="Markdown")
        return
    linhas = texto_completo.replace('\r\n', '\n').split('\n')
    adicionados = 0
    for linha in linhas:
        if linha.strip():
            db.adicionar_dado_titular(linha.strip())
            adicionados += 1
    bot.reply_to(message, f"✅ Sucesso! Cadastrados `{adicionados}` dados de titulares.", parse_mode="Markdown")


@bot.message_handler(commands=['add_esim'])
def cmd_add_esim(message):
    if message.from_user.id != config.ADMIN_ID:
        return
    conteudo = message.text.replace('/add_esim', '').strip()
    if not conteudo:
        bot.reply_to(message, "⚠️ Informe o eSIM. Ex: `/add_esim LPA:1$SMDP...`", parse_mode="Markdown")
        return
    db.adicionar_estoque_item(categoria='esim', conteudo=conteudo, bin='000000', banco='GERAL', bandeira='ESIM')
    bot.reply_to(message, "✅ eSIM adicionado com sucesso!", parse_mode="Markdown")


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


# --- CALLBACKS DO CLIENTE ---
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
        conn = db.sqlite3.connect(db.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT bandeira, COUNT(*) FROM estoque WHERE categoria = 'streaming' AND vendido = 0 GROUP BY bandeira")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            bot.send_message(call.message.chat.id, "❌ Nenhuma conta de Streaming disponível no momento.")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for nome_streaming, total_qtd in rows:
            markup.add(types.InlineKeyboardButton(f"🎬 {nome_streaming} • Estoque: {total_qtd} (R$ 12,00)", callback_data=f"comprar_stream_{nome_streaming}"))
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "🛒 **Selecione o Streaming Desejado:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("comprar_stream_"):
        nome_streaming = data.replace("comprar_stream_", "")
        bot.answer_callback_query(call.id)
        
        preco = 12.0
        conn = db.sqlite3.connect(db.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT saldo FROM usuarios WHERE user_id = ?", (user_id,))
        saldo = cursor.fetchone()[0]
        if saldo < preco:
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
            conn.close()
            return
            
        cursor.execute("SELECT id, conteudo FROM estoque WHERE categoria = 'streaming' AND bandeira = ? AND vendido = 0 LIMIT 1", (nome_streaming,))
        item = cursor.fetchone()
        if not item:
            bot.send_message(call.message.chat.id, "❌ Estoque esgotado para esta conta.")
            conn.close()
            return
            
        item_id, conteudo_conta = item[0], item[1]
        cursor.execute("UPDATE usuarios SET saldo = saldo - ? WHERE user_id = ?", (preco, user_id))
        cursor.execute("UPDATE estoque SET vendido = 1 WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(call.message.chat.id, f"✅ **COMPRA APROVADA!**\n\n🎬 **Serviço:** `{nome_streaming}`\n🔑 **Conta:** `{conteudo_conta}`\n⏱️ *Você tem 10 minutos para reportar caso haja problemas.*", parse_mode="Markdown")

    elif data == "cat_esim":
        bot.answer_callback_query(call.id)
        conn = db.sqlite3.connect(db.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM estoque WHERE categoria = 'esim' AND vendido = 0 LIMIT 5")
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            bot.send_message(call.message.chat.id, "❌ Nenhum eSIM disponível no momento.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for item_id, in rows:
            markup.add(types.InlineKeyboardButton(f"📱 Comprar eSIM Global • R$ 20.00", callback_data=f"compras_esim_{item_id}"))
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data="voltar_menu"))
        bot.send_message(call.message.chat.id, "📱 **eSIM Globais Disponíveis:**", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("compras_esim_"):
        item_id = int(data.split("_")[2])
        bot.answer_callback_query(call.id)
        conn = db.sqlite3.connect(db.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT saldo FROM usuarios WHERE user_id = ?", (user_id,))
        saldo = cursor.fetchone()[0]
        preco = 20.0
        if saldo < preco:
            bot.send_message(call.message.chat.id, "❌ Saldo insuficiente.")
            conn.close()
            return
        cursor.execute("SELECT conteudo FROM estoque WHERE id = ? AND vendido = 0", (item_id,))
        item = cursor.fetchone()
        if not item:
            bot.send_message(call.message.chat.id, "❌ Item esgotado.")
            conn.close()
            return
        cursor.execute("UPDATE usuarios SET saldo = saldo - ? WHERE user_id = ?", (preco, user_id))
        cursor.execute("UPDATE estoque SET vendido = 1 WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        bot.send_message(call.message.chat.id, f"✅ **eSIM Adquirido com Sucesso!**\n\n📱 **Dados de Ativação:**\n`{item[0]}`\n⏱️ *Você tem 10 minutos para troca em caso de problemas.*", parse_mode="Markdown")

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
    LOG.info("Bot rodando com proteção definitiva contra conflito (409)...")
    
    try:
        bot.remove_webhook()
    except Exception:
        pass

    # Utiliza o infinity_polling com skip_pending para limpar requisições travadas anteriores
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            LOG.error(f"Erro na conexão: {e}")
            import time
            time.sleep(5)
