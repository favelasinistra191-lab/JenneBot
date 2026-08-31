"""
Módulo de Banco de Dados • Don Ghost Bot
Gerenciamento de Cache, GitHub, Usuários, Indicação Automática, Promoções, Histórico e Preços por BIN
"""
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
CACHE_TTL = 10  # Segundos para revalidar cache

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
        "admin_pendente": {},
        "precos_bin": {}, 
        "configuracoes": {
            "bonus_porcentagem": 100.0, 
            "bonus_expira_em": None,
            "banner_file_id": None
        }
    }
    
    if not GITHUB_TOKEN:
        if os.path.exists(FILE_PATH):
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if "admin_pendente" not in dados: dados["admin_pendente"] = {}
                if "precos_bin" not in dados: dados["precos_bin"] = {}
                if "configuracoes" not in dados:
                    dados["configuracoes"] = {"bonus_porcentagem": 100.0, "bonus_expira_em": None, "banner_file_id": None}
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
            if "admin_pendente" not in dados: dados["admin_pendente"] = {}
            if "precos_bin" not in dados: dados["precos_bin"] = {}
            if "configuracoes" not in dados:
                dados["configuracoes"] = {"bonus_porcentagem": 100.0, "bonus_expira_em": None, "banner_file_id": None}
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
    print("Banco de dados configurado com sucesso!")

def garantir_usuario(user_id, nome, username, indicado_por=None):
    dados = carregar_dados(forcar_atualizacao=True)
    usuarios = dados.get("usuarios", [])
    
    for u in usuarios:
        if u["user_id"] == user_id:
            if not u.get("indicado_por") and indicado_por and indicado_por != user_id:
                u["indicado_por"] = indicado_por
                salvar_dados(dados)
            return
            
    novo_usuario = {
        "user_id": user_id,
        "nome": nome,
        "username": username,
        "saldo": 0.0,
        "indicado_por": indicado_por if (indicado_por and indicado_por != user_id) else None,
        "indicacao_paga": False
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

def obter_preco_bin(bin_code):
    dados = carregar_dados()
    precos = dados.get("precos_bin", {})
    return float(precos.get(bin_code, 4.0))

def definir_preco_bin(bin_code, preco):
    dados = carregar_dados(forcar_atualizacao=True)
    if "precos_bin" not in dados:
        dados["precos_bin"] = {}
    dados["precos_bin"][bin_code] = preco
    salvar_dados(dados)

def obter_dados_relatorio():
    dados = carregar_dados()
    clientes = len(dados.get("usuarios", []))
    vendas = len([e for e in dados.get("estoque", []) if e.get("vendido") == 1])
    
    faturamento = 0.0
    precos = dados.get("precos_bin", {})
    for e in dados.get("estoque", []):
        if e.get("vendido") == 1:
            b_code = e.get("bin", "000000")
            faturamento += float(precos.get(b_code, 4.0))
            
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
    precos = dados.get("precos_bin", {})
    
    agrupado = {}
    for item in estoque:
        if item.get("categoria") == "gg" and item.get("vendido") == 0:
            b = item.get("bin")
            band = item.get("bandeira")
            key = (b, band)
            agrupado[key] = agrupado.get(key, 0) + 1
            
    resultado = []
    for (b, band), qtd in agrupado.items():
        preco = float(precos.get(b, 4.0))
        resultado.append((b, band, qtd, preco))
    return resultado

def obter_historico_compras(user_id):
    dados = carregar_dados()
    estoque = dados.get("estoque", [])
    return [e for e in estoque if e.get("vendido") == 1 and e.get("comprado_por") == user_id]

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    dados = carregar_dados(forcar_atualizacao=True)
    usuarios = dados.get("usuarios", [])
    estoque = dados.get("estoque", [])
    titulares = dados.get("dados_titular", [])
    
    user = next((u for u in usuarios if u["user_id"] == user_id), None)
    if not user or user.get("saldo", 0.0) < preco:
        return "saldo_insuficiente", None, None, None, None, None
        
    item_escolhido = next((item for item in estoque if item.get("categoria") == categoria and item.get("vendido") == 0 and (not bin_v or item.get("bin") == bin_v)), None)
    if not item_escolhido:
        return "esgotado", None, None, None, None, None
        
    titular_escolhido = next((t for t in titulares if t.get("usado", 0) == 0), None)
    if not titular_escolhido:
        return "falta_dados", None, None, None, None, None

    user["saldo"] -= preco
    item_escolhido["vendido"] = 1
    item_escolhido["comprado_por"] = user_id
    titular_escolhido["usado"] = 1

    salvar_dados(dados)
    return "ok", item_escolhido["conteudo"], titular_escolhido["conteudo"], item_escolhido["banco"], item_escolhido["bandeira"], item_escolhido["bin"]
