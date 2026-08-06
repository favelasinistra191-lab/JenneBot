import os
import json
import base64
import requests
import time

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "favelasinistra191-lab/JenneBot"
FILE_PATH = "dados.json"

_cache_dados = None
_ultimo_carregamento = 0
CACHE_TTL = 10  # Tempo em segundos para revalidar com o GitHub

def carregar_dados(forcar_atualizacao=False):
    global _cache_dados, _ultimo_carregamento
    agora = time.time()
    
    if not forcar_atualizacao and _cache_dados and (agora - _ultimo_carregamento < CACHE_TTL):
        return _cache_dados

    estrutura_padrao = {
        "usuarios": [], 
        "estoque": [], 
        "gift_cards": [], 
        "dados_titular": [],
        "admin_pendente": {}
    }
    
    if not GITHUB_TOKEN:
        if os.path.exists(FILE_PATH):
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if "admin_pendente" not in dados:
                    dados["admin_pendente"] = {}
                _cache_dados = dados
                _ultimo_carregamento = agora
                return dados
        return estrutura_padrao

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            file_content = response.json().get("content")
            decoded_bytes = base64.b64decode(file_content)
            dados = json.loads(decoded_bytes.decode("utf-8"))
            if "admin_pendente" not in dados:
                dados["admin_pendente"] = {}
            _cache_dados = dados
            _ultimo_carregamento = agora
            return dados
    except Exception:
        if _cache_dados:
            return _cache_dados

    return estrutura_padrao

def salvar_dados(dados):
    global _cache_dados, _ultimo_carregamento
    _cache_dados = dados
    _ultimo_carregamento = time.time()

    if not GITHUB_TOKEN:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=4)
        return

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    try:
        r_get = requests.get(url, headers=headers, timeout=5)
        sha = r_get.json().get("sha") if r_get.status_code == 200 else None

        json_str = json.dumps(dados, ensure_ascii=False, indent=4)
        content_encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "Atualização rápida via cache",
            "content": content_encoded,
            "branch": "main"
        }
        if sha:
            payload["sha"] = sha

        requests.put(url, headers=headers, json=payload, timeout=5)
    except Exception:
        pass

def criar_tabelas():
    dados = carregar_dados(forcar_atualizacao=True)
    if not dados.get("usuarios"):
        salvar_dados(dados)
    print("Banco de dados via GitHub e Cache configurados com sucesso!")

def garantir_usuario(user_id, nome, username):
    dados = carregar_dados()
    usuarios = dados.get("usuarios", [])
    
    for u in usuarios:
        if u["user_id"] == user_id:
            return
            
    usuarios.append({
        "user_id": user_id,
        "nome": nome,
        "username": username,
        "saldo": 0.0
    })
    dados["usuarios"] = usuarios
    salvar_dados(dados)

def obter_saldo(user_id):
    dados = carregar_dados()
    for u in dados.get("usuarios", []):
        if u["user_id"] == user_id:
            return float(u.get("saldo", 0.0))
    return 0.0

def adicionar_saldo_usuario(user_id, valor_adicional):
    """Adiciona saldo ao usuário (já considerando o bônus em dobro calculado no main)"""
    dados = carregar_dados(forcar_atualizacao=True)
    usuarios = dados.get("usuarios", [])
    
    usuario_encontrado = None
    for u in usuarios:
        if u["user_id"] == user_id:
            usuario_encontrado = u
            break
            
    if not usuario_encontrado:
        # Se por acaso não achar, cria o usuário na hora
        usuarios.append({
            "user_id": user_id,
            "nome": "Cliente",
            "username": "",
            "saldo": float(valor_adicional)
        })
    else:
        usuario_encontrado["saldo"] = float(usuario_encontrado.get("saldo", 0.0)) + float(valor_adicional)
        
    dados["usuarios"] = usuarios
    salvar_dados(dados)
    return obter_saldo(user_id)

def obter_dados_relatorio():
    dados = carregar_dados()
    clientes = len(dados.get("usuarios", []))
    vendas = len([e for e in dados.get("estoque", []) if e.get("vendido") == 1])
    faturamento = sum([12.0 for e in dados.get("estoque", []) if e.get("vendido") == 1])
    return vendas, faturamento, clientes

def adicionar_lote_estoque(lista_itens, categoria, bin="000000", banco="GERAL", bandeira="GERAL"):
    dados = carregar_dados(forcar_atualizacao=True)
    estoque = dados.get("estoque", [])
    
    novo_id = max([e.get("id", 0) for e in estoque], default=0) + 1
    
    for conteudo in lista_itens:
        estoque.append({
            "id": novo_id,
            "categoria": categoria,
            "conteudo": conteudo,
            "bin": bin,
            "banco": banco,
            "bandeira": bandeira,
            "vendido": 0
        })
        novo_id += 1
        
    dados["estoque"] = estoque
    salvar_dados(dados)

def adicionar_lote_dados_titular(lista_titulares):
    dados = carregar_dados(forcar_atualizacao=True)
    titulares = dados.get("dados_titular", [])
    
    novo_id = max([t.get("id", 0) for t in titulares], default=0) + 1
    
    for conteudo in lista_titulares:
        titulares.append({
            "id": novo_id,
            "conteudo": conteudo,
            "usado": 0
        })
        novo_id += 1
        
    dados["dados_titular"] = titulares
    salvar_dados(dados)

def listar_estoque_gg_agrupado():
    dados = carregar_dados()
    estoque = dados.get("estoque", [])
    
    agrupado = {}
    for item in estoque:
        if item.get("categoria") == "gg" and item.get("vendido") == 0:
            b = item.get("bin")
            band = item.get("bandeira")
            key = (b, band)
            agrupado[key] = agrupado.get(key, 0) + 1
            
    return [(b, band, qtd) for (b, band), qtd in agrupado.items()]

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    dados = carregar_dados(forcar_atualizacao=True)
    usuarios = dados.get("usuarios", [])
    estoque = dados.get("estoque", [])
    titulares = dados.get("dados_titular", [])
    
    user = None
    for u in usuarios:
        if u["user_id"] == user_id:
            user = u
            break
            
    if not user or user.get("saldo", 0.0) < preco:
        return "saldo_insuficiente", None, None, None, None
        
    item_escolhido = None
    for item in estoque:
        if item.get("categoria") == categoria and item.get("vendido") == 0:
            if bin_v and item.get("bin") != bin_v:
                continue
            item_escolhido = item
            break
            
    if not item_escolhido:
        return "esgotado", None, None, None, None
        
    titular_escolhido = None
    if categoria == "gg":
        for t in titulares:
            if t.get("usado", 0) == 0:
                titular_escolhido = t
                break
        if not titular_escolhido:
            return "falta_dados", None, None, None, None

    user["saldo"] -= preco
    item_escolhido["vendido"] = 1
    
    res_dados = "N/A"
    if titular_escolhido:
        titular_escolhido["usado"] = 1
        res_dados = titular_escolhido["conteudo"]

    salvar_dados(dados)
    return "ok", item_escolhido["conteudo"], res_dados, item_escolhido["banco"], item_escolhido["bandeira"]
