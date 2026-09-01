import os
import json
from datetime import datetime

ARQUIVO_DADOS = "dados.json"

def carregar_json():
    estrutura_padrao = {
        "usuarios": [],
        "estoque": [],
        "gift_cards": [],
        "dados_titular": [],
        "admin_pendente": {},
        "precos_bin": {},
        "configuracoes": {
            "bonus_porcentagem": 100.0,
            "bonus_expira_em": None,
            "banner_file_id": None
        }
    }
    if not os.path.exists(ARQUIVO_DADOS):
        salvar_json(estrutura_padrao)
        return estrutura_padrao
    try:
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            conteudo = json.load(f)
            if not isinstance(conteudo, dict):
                return estrutura_padrao
            for chave in estrutura_padrao:
                if chave not in conteudo:
                    conteudo[chave] = estrutura_padrao[chave]
            return conteudo
    except Exception:
        return estrutura_padrao

def salvar_json(dados):
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def criar_tabelas():
    carregar_json()

def garantir_usuario(user_id, primeiro_nome, username):
    dados = carregar_json()
    usuarios = dados.get("usuarios", [])
    
    encontrado = False
    for u in usuarios:
        if u["user_id"] == user_id:
            encontrado = True
            break
            
    if not encontrado:
        usuarios.append({
            "user_id": user_id,
            "primeiro_nome": primeiro_nome,
            "username": username,
            "saldo": 0.0
        })
        dados["usuarios"] = usuarios
        salvar_json(dados)

def obter_saldo(user_id):
    dados = carregar_json()
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            return float(u.get("saldo", 0.0))
    return 0.0

def alterar_saldo(user_id, valor):
    dados = carregar_json()
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            u["saldo"] = float(u.get("saldo", 0.0)) + valor
            salvar_json(dados)
            return u["saldo"]
    return 0.0

def obter_preco_bin(bin_code):
    dados = carregar_json()
    precos = dados.get("precos_bin", {})
    if bin_code in precos:
        return float(precos[bin_code])
    import config
    return config.PRECOS["gg"]

def definir_preco_bin(bin_code, valor):
    dados = carregar_json()
    if "precos_bin" not in dados:
        dados["precos_bin"] = {}
    dados["precos_bin"][bin_code] = valor
    salvar_json(dados)

def adicionar_gift(codigo, valor):
    dados = carregar_json()
    if "gift_cards" not in dados:
        dados["gift_cards"] = []
    dados["gift_cards"].append({"codigo": codigo, "valor": valor, "usado": 0})
    salvar_json(dados)

def resgatar_gift(user_id, codigo):
    dados = carregar_json()
    gifts = dados.get("gift_cards", [])
    for g in gifts:
        if g["codigo"].upper() == codigo.upper():
            if g.get("usado", 0) == 1:
                return "usado", 0.0
            g["usado"] = 1
            valor = float(g["valor"])
            salvar_json(dados)
            alterar_saldo(user_id, valor)
            return "ok", valor
    return "invalido", 0.0

def adicionar_lote_estoque(linhas, categoria="gg", bin="GERAL"):
    dados = carregar_json()
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
    salvar_json(dados)

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    dados = carregar_json()
    
    saldo_atual = 0.0
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            saldo_atual = float(u.get("saldo", 0.0))
            break
            
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
    
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            u["saldo"] = float(u.get("saldo", 0.0)) - preco
            
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
    
    salvar_json(dados)
    return "ok", res_gg, res_dados, "BANCO DO BRASIL", "VISA", bin_item

def obter_historico_compras(user_id):
    dados = carregar_json()
    compras = dados.get("compras", [])
    return [c for c in compras if c.get("user_id") == user_id]
