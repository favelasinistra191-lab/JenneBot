import os
import json
from datetime import datetime

# Nome dos arquivos JSON locais
ARQUIVO_CLIENTES = "clientes_dados.json"
ARQUIVO_ESTOQUE = "estoque_gg.json"

def carregar_json(caminho, estrutura_padrao):
    if not os.path.exists(caminho):
        salvar_json(caminho, estrutura_padrao)
        return estrutura_padrao
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = json.load(f)
            if not isinstance(conteudo, type(estrutura_padrao)):
                return estrutura_padrao
            return conteudo
    except Exception:
        return estrutura_padrao

def salvar_json(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def criar_tabelas():
    # Garante que os arquivos JSON existam com a estrutura completa e correta
    carregar_json(ARQUIVO_CLIENTES, {
        "usuarios": [],
        "compras": [],
        "gifts": []
    })
    carregar_json(ARQUIVO_ESTOQUE, {
        "estoque": [],
        "dados_titular": [],
        "precos_bin": {}
    })

def garantir_usuario(user_id, primeiro_nome, username):
    dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
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
        salvar_json(ARQUIVO_CLIENTES, dados)

def obter_saldo(user_id):
    dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            return float(u.get("saldo", 0.0))
    return 0.0

def alterar_saldo(user_id, valor):
    dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            u["saldo"] = float(u.get("saldo", 0.0)) + valor
            salvar_json(ARQUIVO_CLIENTES, dados)
            return u["saldo"]
    return 0.0

def obter_preco_bin(bin_code):
    dados = carregar_json(ARQUIVO_ESTOQUE, {"estoque": [], "dados_titular": [], "precos_bin": {}})
    precos = dados.get("precos_bin", {})
    if bin_code in precos:
        return float(precos[bin_code])
    import config
    return config.PRECOS["gg"]

def definir_preco_bin(bin_code, valor):
    dados = carregar_json(ARQUIVO_ESTOQUE, {"estoque": [], "dados_titular": [], "precos_bin": {}})
    if "precos_bin" not in dados:
        dados["precos_bin"] = {}
    dados["precos_bin"][bin_code] = valor
    salvar_json(ARQUIVO_ESTOQUE, dados)

def adicionar_gift(codigo, valor):
    dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
    if "gifts" not in dados:
        dados["gifts"] = []
    dados["gifts"].append({"codigo": codigo, "valor": valor, "usado": 0})
    salvar_json(ARQUIVO_CLIENTES, dados)

def resgatar_gift(user_id, codigo):
    dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
    gifts = dados.get("gifts", [])
    for g in gifts:
        if g["codigo"].upper() == codigo.upper():
            if g.get("usado", 0) == 1:
                return "usado", 0.0
            g["usado"] = 1
            valor = float(g["valor"])
            alterar_saldo(user_id, valor)
            salvar_json(ARQUIVO_CLIENTES, dados)
            return "ok", valor
    return "invalido", 0.0

def adicionar_lote_estoque(linhas, categoria="gg", bin="GERAL"):
    dados = carregar_json(ARQUIVO_ESTOQUE, {"estoque": [], "dados_titular": [], "precos_bin": {}})
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
    salvar_json(ARQUIVO_ESTOQUE, dados)

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    cli_dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
    est_dados = carregar_json(ARQUIVO_ESTOQUE, {"estoque": [], "dados_titular": [], "precos_bin": {}})
    
    saldo_atual = 0.0
    for u in cli_dados.get("usuarios", []):
        if u["user_id"] == user_id:
            saldo_atual = float(u.get("saldo", 0.0))
            break
            
    if saldo_atual < preco:
        return "saldo_insuficiente", None, None, None, None, None
        
    estoque = est_dados.get("estoque", [])
    dados_titular = est_dados.get("dados_titular", [])
    
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
    
    # Deduz o saldo do cliente
    for u in cli_dados.get("usuarios", []):
        if u["user_id"] == user_id:
            u["saldo"] = float(u.get("saldo", 0.0)) - preco
            
    res_gg = item_escolhido["conteudo"]
    res_dados = dado_escolhido["conteudo"]
    bin_item = item_escolhido.get("bin", "GERAL")
    
    if "compras" not in cli_dados:
        cli_dados["compras"] = []
        
    cli_dados["compras"].append({
        "user_id": user_id,
        "categoria": categoria,
        "conteudo": res_gg,
        "dados": res_dados,
        "banco": "BANCO DO BRASIL",
        "bandeira": "VISA",
        "data": str(datetime.now())
    })
    
    salvar_json(ARQUIVO_CLIENTES, cli_dados)
    salvar_json(ARQUIVO_ESTOQUE, est_dados)
    return "ok", res_gg, res_dados, "BANCO DO BRASIL", "VISA", bin_item

def obter_historico_compras(user_id):
    dados = carregar_json(ARQUIVO_CLIENTES, {"usuarios": [], "compras": [], "gifts": []})
    compras = dados.get("compras", [])
    return [c for c in compras if c.get("user_id") == user_id]
