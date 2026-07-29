"""Bot Telegram de Loja Digital - Versão com Estatísticas e Visual Moderno."""

from __future__ import annotations
import logging
import os
import time
import threading
import random
import re
import string
import requests
from datetime import datetime
from decimal import Decimal
from typing import Any
import telebot
from telebot import apihelper, types
import database as db
from security_utils import CPFProtector
from flask import Flask

# --- Configurações Iniciais ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8645582951:AAGKtbHS3qF8VOFC4onst-8sf4ussasX5_I").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PIX_ESTATICO = "00020126580014br.gov.bcb.pix0136ca6bbdfb-a4ed-4ca3-b88e-53cccd4b43635204000053039865802BR5924Carlos Gabriel Candido d6006Brasil62290525202607181421TUV2VAB162WC66304B341"
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

PRECOS = {"gg": 4.0, "streaming": 12.0, "esim": 20.0}
MIN_DEPOSITO = 10.0
CRYPTO_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "")

db.criar_tabelas()

if os.getenv("HTTPS_PROXY_URL"):
    apihelper.proxy = {"https": os.environ["HTTPS_PROXY_URL"]}

bot = telebot.TeleBot(TOKEN) if TOKEN else None
state: dict[int, dict[str, Any]] = {}

# --- Servidor Web Keep-Alive ---
app = Flask(__name__)
@app.route('/')
def health(): return "Bot Online e Moderno!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive_ping():
    if not RENDER_URL: return
    while True:
        try: requests.get(RENDER_URL)
        except: pass
        time.sleep(600)

# --- Auxiliares ---

def protect() -> CPFProtector:
    key = os.getenv("CPF_ENCRYPTION_KEY", "").strip()
    return CPFProtector.from_string(key)

# Cache de BINs já consultadas (persiste durante a sessão)
_BIN_CACHE: dict[str, dict] = {}

def identificar_banco_por_bin(bin_digits: str) -> dict:
    """Identifica o banco/instituição pelos 6 primeiros dígitos via binlist.net com cache."""
    bin6 = bin_digits.strip()[:6]
    # Verifica cache primeiro
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]
    try:
        resp = requests.get(
            f"https://lookup.binlist.net/{bin6}",
            headers={"Accept-Version": "3"},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            bank_name = data.get("bank", {}).get("name", "Não identificado")
            scheme = data.get("scheme", "").upper()
            card_type = data.get("type", "").capitalize()
            country = data.get("country", {}).get("name", "")
            result = {
                "banco": bank_name,
                "bandeira": scheme,
                "tipo": card_type,
                "pais": country
            }
            _BIN_CACHE[bin6] = result
            return result
        elif resp.status_code == 429:
            result = {"banco": "Rate limit atingido", "bandeira": "", "tipo": "", "pais": ""}
            _BIN_CACHE[bin6] = result
            return result
        else:
            result = {"banco": "Não identificado", "bandeira": "", "tipo": "", "pais": ""}
            _BIN_CACHE[bin6] = result
            return result
    except Exception:
        result = {"banco": "Erro na consulta", "bandeira": "", "tipo": "", "pais": ""}
        _BIN_CACHE[bin6] = result
        return result

def is_admin(message: Any) -> bool:
    return bool(ADMIN_ID and message.from_user.id == ADMIN_ID)

def register(obj: Any) -> None:
    user = obj.from_user
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or "Cliente"
    db.garantir_usuario(user.id, name, getattr(user, "username", None))

# --- Handlers Administrativos ---

if bot:
    @bot.message_handler(commands=["menu"])
    def admin_menu(message: Any):
        if not is_admin(message):
            bot.reply_to(message, "❌ Código não encontrado, código não existente.")
            return
        menu_text = (
            "💎 *PAINEL ADMINISTRATIVO*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📦 *ADIÇÃO EM MASSA*\n"
            "• `/add gg` - Cartões\n"
            "• `/add dados` - Nome|CPF\n"
            "• `/add streaming` - Contas\n"
            "• `/add esim` - eSIMs\n\n"
            "📊 *GESTÃO DE LOJA*\n"
            "• `/estoque` - Ver itens\n"
            "• `/relatorio` - Vendas e Estatísticas\n"
            "• `/filas` - Status Pareamento\n\n"
            "🎁 *GIFT CARDS*\n"
            "• `/gerar_gift VALOR`"
        )
        bot.reply_to(message, menu_text, parse_mode="Markdown")

    @bot.message_handler(commands=["relatorio"])
    def report(message: Any):
        if not is_admin(message): return
        total_vendas, faturamento, categorias = db.obter_dados_relatorio()
        total_clientes = db.contar_usuarios_unicos()
        cat_str = "\n".join([f"• {k.title()}: {v}" for k, v in categorias.items()])
        
        rel_text = (
            "📈 *RELATÓRIO GERAL DA LOJA*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Total de Clientes:* `{total_clientes}`\n"
            f"🛒 *Total de Vendas:* `{total_vendas}`\n"
            f"💰 *Faturamento:* `R$ {faturamento:.2f}`\n\n"
            f"📦 *Vendas por Categoria:*\n{cat_str}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        bot.reply_to(message, rel_text, parse_mode="Markdown")

    @bot.message_handler(commands=["estoque"])
    def view_stock(message: Any):
        if not is_admin(message): return
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        bot.reply_to(message, f"📋 *ESTOQUE DETALHADO*\n━━━━━━━━━━━━━━━━━━━━\n💳 GG: `{gg}` unidades\n📺 Streaming: `{stream}` unidades\n📶 eSIM: `{esim}` unidades", parse_mode="Markdown")

    @bot.message_handler(commands=["listar_bin"])
    def listar_bin_cmd(message: Any):
        """Lista todas as BINs disponíveis no estoque com quantidade e banco."""
        if not is_admin(message): return
        groups = db.listar_estoque_gg()
        if not groups:
            bot.reply_to(message, "❌ *SEM ESTOQUE!*\nNenhuma GG disponível no momento.", parse_mode="Markdown")
            return
        total = 0
        linhas = []
        for b, banco, c in groups:
            linhas.append(f"💳 BIN `{b}` - {banco} → `{c}` un")
            total += c
        info = "\n".join(linhas)
        bot.reply_to(message,
            f"📦 *ESTOQUE GG POR BIN*\n━━━━━━━━━━━━━━━━━━━━\n{info}\n━━━━━━━━━━━━━━━━━━━━\n📦 Total: `{total}` unidades em `{len(groups)}` BINs diferentes",
            parse_mode="Markdown"
        )

    @bot.message_handler(commands=["add"])
    def add_cmd(message: Any):
        if not is_admin(message): return
        parts = message.text.split()
        if len(parts) < 2: return
        option = parts[1].lower()
        if option == "gg":
            msg = bot.reply_to(message, "💳 *ADD GG EM MASSA*\n\nEnvie a lista no formato:\n`NUMERO|VALIDADE|CVV`\n\nA *BIN* e o *Banco* serão identificados automaticamente.")
            bot.register_next_step_handler(msg, gg_mass_auto_process)
        elif option == "dados":
            msg = bot.reply_to(message, "👤 *ADD DADOS EM MASSA*\n\nEnvie a lista no formato:\n`NOME|CPF`")
            bot.register_next_step_handler(msg, data_mass_process)
        elif option == "streaming":
            msg = bot.reply_to(message, "📺 *ADD STREAMING EM MASSA*\n\nEnvie a lista no formato:\n`EMAIL|SENHA|TELA|SENHA`")
            bot.register_next_step_handler(msg, stream_mass_process)
        elif option == "esim":
            msg = bot.reply_to(message, "📶 *ADD ESIM EM MASSA*\n\nEnvie a lista de conteúdos (um por linha):")
            bot.register_next_step_handler(msg, esim_mass_process)

    def gg_mass_auto_process(message: Any):
        """Processa a lista de GGs automaticamente, extraindo BIN de cada linha individualmente."""
        lines = message.text.strip().split("\n")
        
        # Primeira passada: agrupar por BIN (consulta API apenas 1x por BIN)
        bin_groups = {}
        for line in lines:
            if "|" not in line:
                continue
            parts = line.strip().split("|")
            if len(parts) < 2:
                continue
            # Extrai apenas dígitos do primeiro campo (número do cartão)
            card_number = re.sub(r"\D", "", parts[0].strip())
            if len(card_number) >= 6:
                bin6 = card_number[:6]
                if bin6 not in bin_groups:
                    bin_groups[bin6] = []
                # Guarda a linha completa com o número do cartão normalizado
                # Reconstrói: numero|validade|cvv
                if len(parts) >= 3:
                    clean_line = f"{card_number}|{parts[1].strip()}|{parts[2].strip()}"
                else:
                    clean_line = f"{card_number}|{parts[1].strip()}"
                bin_groups[bin6].append(clean_line)
        
        if not bin_groups:
            bot.reply_to(message, "❌ Nenhuma GG válida encontrada. Verifique o formato: `NUMERO|VALIDADE|CVV`")
            return
        
        # Segunda passada: identificar banco para cada BIN e adicionar ao DB
        total_s = 0
        total_e = 0
        info_msgs = []
        
        for bin6, card_lines in bin_groups.items():
            info_banco = identificar_banco_por_bin(bin6)
            bank_name = info_banco["banco"]
            info_msgs.append(f"💳 BIN `{bin6}` → 🏦 `{bank_name}` ({len(card_lines)} un)")
            
            for card_line in card_lines:
                try:
                    db.adicionar_gg_pendente(bin6, bank_name, card_line, message.from_user.id)
                    total_s += 1
                except:
                    total_e += 1
        
        info_text = "\n".join(info_msgs)
        bot.reply_to(message, 
            f"✅ *PROCESSO CONCLUÍDO*\n━━━━━━━━━━━━━━━━━━━━\n{info_text}\n━━━━━━━━━━━━━━━━━━━━\nSucesso: `{total_s}`\nErros: `{total_e}`\n📦 Estoque Total GG: `{db.contar_estoque_categoria('gg')}`",
            parse_mode="Markdown"
        )

    @bot.message_handler(commands=["corrigir_bin"])
    def corrigir_bin_cmd(message: Any):
        """Reprocessa todas as BINs do banco de dados, extraindo corretamente e identificando o banco."""
        if not is_admin(message): return
        try:
            bot.send_message(message.chat.id, "⏳ *CORRIGINDO BINs*\nLendo todos os GGs do banco de dados...")
            bin_results = db.corrigir_bins_estoque()
            total = bin_results.get("total", 0)
            corrigidos = bin_results.get("corrigidos", 0)
            erros = bin_results.get("erros", 0)
            detalhes = bin_results.get("detalhes", [])
            
            if total == 0:
                bot.reply_to(message, "✅ Nenhum GG encontrado no banco de dados.")
                return
            
            info_text = "\n".join(detalhes[:20])  # Mostra até 20 BINs
            bot.reply_to(message,
                f"✅ *CORREÇÃO CONCLUÍDA*\n━━━━━━━━━━━━━━━━━━━━\n📦 Total: `{total}` GGs\n✔️ Corrigidos: `{corrigidos}`\n❌ Erros: `{erros}`\n━━━━━━━━━━━━━━━━━━━━\n{info_text}",
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.reply_to(message, f"❌ Erro ao corrigir BINs: {str(e)}")

    def data_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e, p = 0, 0, protect()
        for line in lines:
            parts = line.split("|")
            if len(parts) == 2:
                try:
                    db.adicionar_dados_pendentes(parts[0].strip(), p.encrypt(parts[1].strip()), p.fingerprint(parts[1].strip()), message.from_user.id)
                    s += 1
                except: e += 1
            else: e += 1
        bot.reply_to(message, f"✅ *DADOS ADICIONADOS*\n\nSucesso: `{s}`\nErros: `{e}`", parse_mode="Markdown")

    def stream_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            if "|" in line:
                try:
                    db.adicionar_estoque("streaming", line.strip())
                    s += 1
                except: e += 1
            else: e += 1
        bot.reply_to(message, f"✅ *STREAMINGS ADICIONADOS*\n\nSucesso: `{s}`\nErros: `{e}`", parse_mode="Markdown")

    def esim_mass_process(message: Any):
        lines = message.text.strip().split("\n")
        s, e = 0, 0
        for line in lines:
            try:
                db.adicionar_estoque("esim", line.strip())
                s += 1
            except: e += 1
        bot.reply_to(message, f"✅ *eSIMs ADICIONADOS*\n\nSucesso: `{s}`\nErros: `{e}`", parse_mode="Markdown")

    @bot.message_handler(commands=["gerar_gift"])
    def create_gift(message: Any):
        if not is_admin(message): return
        try:
            val = float(message.text.split()[1])
            code = "GIFT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
            db.criar_gift(code, val, message.from_user.id)
            bot.reply_to(message, f"🎁 *GIFT CARD GERADO*\n━━━━━━━━━━━━━━━━━━━━\nCódigo: `{code}`\nValor: `R$ {val:.2f}`\n━━━━━━━━━━━━━━━━━━━━\n_Mande para o cliente resgatar._", parse_mode="Markdown")
        except: bot.reply_to(message, "Uso: `/gerar_gift 50`")

    # --- Handlers de Usuário ---

    @bot.message_handler(commands=["start"])
    def start(message: Any):
        LOG.info(f"Comando /start recebido do usuário {message.from_user.id}")
        register(message)
        home(message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: True)
    def callbacks(call: Any):
        register(call)
        bot.answer_callback_query(call.id)
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        
        if data == "inicio": home(chat, uid)
        elif data == "saldo":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🏦 PIX Manual", callback_data="pix_manual"))
            bot.send_message(chat, "💰 *ADICIONAR SALDO*\n━━━━━━━━━━━━━━━━━━━━\nNo momento, apenas o *PIX Manual* está funcionando.\n\nApós realizar o pagamento, envie o comprovante no privado para que eu possa liberar seu saldo imediatamente.", reply_markup=markup, parse_mode="Markdown")
        elif data == "pix_manual":
            bot.send_message(chat, f"🏦 *PIX MANUAL (COPIA E COLA)*\n━━━━━━━━━━━━━━━━━━━━\nClique no código abaixo para copiar:\n\n`{PIX_ESTATICO}`\n\n━━━━━━━━━━━━━━━━━━━━\n⚠️ *AVISO:* Envie o comprovante no privado para liberação.", parse_mode="Markdown")
        elif data == "resgatar_btn":
            msg = bot.send_message(chat, "🎁 *RESGATE DE GIFT*\n\nDigite ou cole o código do seu Gift Card abaixo:")
            bot.register_next_step_handler(msg, process_gift_step)
        elif data == "menu_gg":
            groups = db.listar_estoque_gg()
            if not groups:
                bot.send_message(chat, "❌ *DESCULPE!*\nEstamos sem estoque de GG no momento. Volte mais tarde!", parse_mode="Markdown")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for b, banco, c in groups:
                markup.add(types.InlineKeyboardButton(f"{b} | {c} un", callback_data=f"buy|gg|{b}"))
            markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
            bot.send_message(chat, "💳 *ESCOLHA SUA BIN*\n━━━━━━━━━━━━━━━━━━━━\nTodas as GGs acompanham dados do titular.", reply_markup=markup, parse_mode="Markdown")
        elif data == "menu_streaming":
            count = db.contar_estoque_categoria("streaming")
            if count == 0:
                bot.send_message(chat, "❌ *SEM ESTOQUE!*\nStreaming indisponível no momento.", parse_mode="Markdown")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 12,00)", callback_data="buy|streaming"))
            markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
            bot.send_message(chat, f"📺 *STREAMING DISPONÍVEL*\n━━━━━━━━━━━━━━━━━━━━\n📦 Estoque: `{count}` unidades\n💰 Valor: `R$ 12,00`", reply_markup=markup, parse_mode="Markdown")
        elif data == "menu_esim":
            count = db.contar_estoque_categoria("esim")
            if count == 0:
                bot.send_message(chat, "❌ *SEM ESTOQUE!*\neSIM indisponível no momento.", parse_mode="Markdown")
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirmar Compra (R$ 20,00)", callback_data="buy|esim"))
            markup.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="inicio"))
            bot.send_message(chat, f"📶 *eSIM DISPONÍVEL*\n━━━━━━━━━━━━━━━━━━━━\n📦 Estoque: `{count}` unidades\n💰 Valor: `R$ 20,00`", reply_markup=markup, parse_mode="Markdown")
        elif data.startswith("buy|"):
            process_purchase(call)
        elif data == "conta":
            saldo = db.obter_saldo(uid)
            bot.send_message(chat, f"👤 *MINHA CONTA*\n━━━━━━━━━━━━━━━━━━━━\n🆔 Seu ID: `{uid}`\n💰 Saldo Atual: `R$ {saldo:.2f}`\n━━━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")

    def process_purchase(call: Any):
        chat, uid, data = call.message.chat.id, call.from_user.id, call.data
        saldo = db.obter_saldo(uid)
        parts = data.split("|")
        cat = parts[1]
        price = PRECOS[cat]
        if cat == "gg":
            bn = parts[2] if len(parts) > 2 else None
            bk = None  # Não precisa filtrar por banco, só por BIN
        else:
            bn, bk = None, None

        if saldo < price:
            bot.send_message(chat, f"❌ *SALDO INSUFICIENTE!*\n\nVocê possui `R$ {saldo:.2f}`\nValor necessário: `R$ {price:.2f}`\n\nAdicione saldo para continuar.", parse_mode="Markdown")
            return

        inv_id = f"BUY-{int(time.time())}-{uid}"
        status, sid, conteudo = db.concluir_compra_fatura(inv_id, uid, cat, price, bn, bk)

        if status == "ok":
            agora = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
            if cat == "gg":
                d = db.obter_dados_gg_para_entrega(sid, uid)
                cpf = protect().decrypt(d[3])
                nums = conteudo.split("|")
                msg = (
                    f"✅ *COMPRA REALIZADA!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💳 *DADOS DO CARTÃO:*\n"
                    f"• Número: `{nums[0]}`\n"
                    f"• Validade: `{nums[1]}`\n"
                    f"• CVV: `{nums[2]}`\n\n"
                    f"🏦 *BANCO:* `{d[1]}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *DADOS DO TITULAR:*\n"
                    f"• Nome: `{d[2]}`\n"
                    f"• CPF: `{cpf}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 *ENTREGA:* `{agora}`\n\n"
                    f"⚠️ *AVISO:* Você tem 10 minutos para realizar a troca em caso de erro. Após esse tempo, não nos responsabilizamos."
                )
            elif cat == "streaming":
                s = conteudo.split("|")
                msg = (
                    f"✅ *COMPRA REALIZADA!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📺 *DADOS DO STREAMING:*\n"
                    f"• Email: `{s[0]}`\n"
                    f"• Senha: `{s[1]}`\n"
                    f"• Tela: `{s[2]}`\n"
                    f"• PIN: `{s[3]}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 *ENTREGA:* `{agora}`"
                )
            else:
                msg = f"✅ *COMPRA REALIZADA!*\n━━━━━━━━━━━━━━━━━━━━\n📦 *CONTEÚDO:* `{conteudo}`\n━━━━━━━━━━━━━━━━━━━━\n🕒 *ENTREGA:* `{agora}`"
            
            bot.send_message(chat, msg, parse_mode="Markdown")
        else:
            bot.send_message(chat, "❌ *ERRO NO SISTEMA!*\nOcorreu uma falha ao processar sua compra. O saldo não foi debitado.")

    def process_gift_step(message: Any):
        valor = db.resgatar_gift(message.text.strip(), message.from_user.id)
        if valor:
            bot.send_message(message.chat.id, f"✅ *SUCESSO!*\n\nO Gift Card foi resgatado e *R$ {valor:.2f}* foram adicionados ao seu saldo.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ *ERRO:* Código inválido, já utilizado ou inexistente.", parse_mode="Markdown")

    def home(chat: int, uid: int):
        saldo = db.obter_saldo(uid)
        gg = db.contar_estoque_categoria("gg")
        stream = db.contar_estoque_categoria("streaming")
        esim = db.contar_estoque_categoria("esim")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"💳 GG | R$ 4,00 | {gg} un", callback_data="menu_gg"),
            types.InlineKeyboardButton(f"📺 Streaming | R$ 12,00 | {stream} un", callback_data="menu_streaming"),
            types.InlineKeyboardButton(f"📶 eSIM | R$ 20,00 | {esim} un", callback_data="menu_esim"),
            types.InlineKeyboardButton("👤 Minha Conta", callback_data="conta"),
            types.InlineKeyboardButton("➕ Adicionar saldo", callback_data="saldo"),
            types.InlineKeyboardButton("🎁 Resgatar Gift", callback_data="resgatar_btn")
        )
        msg_home = (
            "🏪 *BEM-VINDO À LOJA DIGITAL*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Escolha uma das opções abaixo para navegar no nosso catálogo.\n\n"
            f"💰 Seu Saldo: `R$ {saldo:.2f}`"
        )
        bot.send_message(chat, msg_home, reply_markup=markup, parse_mode="Markdown")

    @bot.message_handler(func=lambda m: m.text and m.text.startswith("/"))
    def unknown(message: Any):
        bot.reply_to(message, "❌ Código não encontrado, código não existente.")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()
    while True:
        try:
            if not TOKEN:
                LOG.error("TELEGRAM_BOT_TOKEN não configurado!")
                time.sleep(30)
                continue
            LOG.info("Iniciando bot em modo polling...")
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=20, skip_pending=True)
        except Exception as exc:
            LOG.error(f"Erro no loop principal: {exc}")
            time.sleep(10)
