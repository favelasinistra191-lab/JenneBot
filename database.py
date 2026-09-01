import os
import json
import socket
import psycopg2
import psycopg2.extras
import config
from datetime import datetime

def obter_conexao():
    # Força a resolução estrita para IPv4 para contornar o bloqueio de rede do Render
    host = "db.ibwndysxzqczxcyyfqwt.supabase.co"
    ip_v4 = host
    try:
        infos = socket.getaddrinfo(host, 5432, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            ip_v4 = infos[0][4][0]
    except Exception:
        pass

    url = f"postgresql://postgres:8Dedezembro@{ip_v4}:5432/postgres"
    return psycopg2.connect(url, sslmode='require')

def criar_tabelas():
    conn = obter_conexao()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_dados (
            chave TEXT PRIMARY KEY,
            conteudo JSONB
        );
    """)
    conn.commit()
    
    cur.execute("SELECT conteudo FROM bot_dados WHERE chave = 'dados_gerais'")
    if not cur.fetchone():
        dados_iniciais = {
            "usuarios": [],
            "estoque": [],
            "dados_titular": [],
            "compras": [],
            "gifts": [],
            "precos_bin": {},
            "configuracoes": {}
        }
        cur.execute(
            "INSERT INTO bot_dados (chave, conteudo) VALUES ('dados_gerais', %s)",
            (json.dumps(dados_iniciais),)
        )
        conn.commit()
    cur.close()
    conn.close()

def carregar_dados(forcar_atualizacao=False):
    conn = obter_conexao()
    cur = conn.cursor()
    cur.execute("SELECT conteudo FROM bot_dados WHERE chave = 'dados_gerais'")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0]:
        return row[0]
    return {
        "usuarios": [],
        "estoque": [],
        "dados_titular": [],
        "compras": [],
        "gifts": [],
        "precos_bin": {},
        "configuracoes": {}
    }

def salvar_dados(dados):
    conn = obter_conexao()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bot_dados (chave, conteudo) VALUES ('dados_gerais', %s) ON CONFLICT (chave) DO UPDATE SET conteudo = %s",
        (json.dumps(dados), json.dumps(dados))
    )
    conn.commit()
    cur.close()
    conn.close()

def garantir_usuario(user_id, primeiro_nome, username):
    dados = carregar_dados()
    usuarios = dados.get("usuarios", [])
    
    encontrado = False
    for u in usuarios:
        if u["user_id"] == user_id:
            encontrado = True
            break
            
    if not encontrado:
        novo_usuario = {
            "user_id": user_id,
            "primeiro_nome": primeiro_nome,
            "username": username,
            "saldo": 0.0
        }
        usuarios.append(novo_usuario)
        dados["usuarios"] = usuarios
        salvar_dados(dados)

def obter_saldo(user_id):
    dados = carregar_dados()
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            return float(u.get("saldo", 0.0))
    return 0.0

def alterar_saldo(user_id, valor):
    dados = carregar_dados()
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            u["saldo"] = float(u.get("saldo", 0.0)) + valor
            salvar_dados(dados)
            return u["saldo"]
    return 0.0

def obter_preco_bin(bin_code):
    dados = carregar_dados()
    precos = dados.get("precos_bin", {})
    if bin_code in precos:
        return float(precos[bin_code])
    return config.PRECOS["gg"]

def definir_preco_bin(bin_code, valor):
    dados = carregar_dados()
    if "precos_bin" not in dados:
        dados["precos_bin"] = {}
    dados["precos_bin"][bin_code] = valor
    salvar_dados(dados)

def adicionar_gift(codigo, valor):
    dados = carregar_dados()
    if "gifts" not in dados:
        dados["gifts"] = []
    dados["gifts"].append({"codigo": codigo, "valor": valor, "usado": 0})
    salvar_dados(dados)

def resgatar_gift(user_id, codigo):
    dados = carregar_dados()
    gifts = dados.get("gifts", [])
    for g in gifts:
        if g["codigo"].upper() == codigo.upper():
            if g.get("usado", 0) == 1:
                return "usado", 0.0
            g["usado"] = 1
            valor = float(g["valor"])
            alterar_saldo(user_id, valor)
            salvar_dados(dados)
            return "ok", valor
    return "invalido", 0.0

def adicionar_lote_estoque(linhas, categoria="gg", bin="GERAL"):
    dados = carregar_dados()
    if "estoque" not in dados:
        dados["estoque"] = []
    if "dados_titular" not in dados:
        dados["dados_titular"] = []
        
    for linha in linhas:
        if "|" in linha and len(linha.split("|")) >= 4:
            dados["estoque"].append({
                "categoria": categoria,
                "bin": bin,
                "conteudo": linha.strip(),
                "vendido": 0
            })
        else:
            dados["dados_titular"].append({
                "conteudo": linha.strip(),
                "usado": 0
            })
    salvar_dados(dados)

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    dados = carregar_dados()
    saldo_atual = obter_saldo(user_id)
    
    if saldo_atual < preco:
        return "saldo_insuficiente", None, None, None, None, None
        
    estoque = dados.get("estoque", [])
    dados_titular = dados.get("dados_titular", [])
    
    item_escolhido = None
    for item in estoque:
        if int(item.get("vendido", 0)) == 0 and str(item.get("categoria", "")).lower() == str(categoria).lower():
            if bin_v and str(item.get("bin")) != str(bin_v):
                continue
            item_escolhido = item
            break
            
    if not item_escolhido:
        return "esgotado", None, None, None, None, None
        
    dado_escolhido = None
    for d in dados_titular:
        if int(d.get("usado", 0)) == 0:
            dado_escolhido = d
            break
            
    if not dado_escolhido:
        return "falta_dados", None, None, None, None, None
        
    item_escolhido["vendido"] = 1
    dado_escolhido["usado"] = 1
    
    alterar_saldo(user_id, -preco)
    
    res_gg = item_escolhido["conteudo"]
    res_dados = dado_escolhido["conteudo"]
    bin_item = item_escolhido.get("bin", "GERAL")
    
    if "compras" not in dados:
        dados["compras"] = []
        
    dados["compras"].append({
        "user_id": user_id,
        "categoria": categoria,
        "conteudo": res_gg,
        "dados": res_dados,
        "banco": "BANCO DO BRASIL",
        "bandeira": "VISA",
        "data": str(datetime.now())
    })
    
    salvar_dados(dados)
    return "ok", res_gg, res_dados, "BANCO DO BRASIL", "VISA", bin_item

def obter_historico_compras(user_id):
    dados = carregar_dados()
    compras = dados.get("compras", [])
    return [c for c in compras if c.get("user_id") == user_id]
