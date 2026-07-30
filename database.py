import os
import json
import base64
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "favelasinistra191-lab/JenneBot"
FILE_PATH = "dados.json"

def carregar_dados():
    if not GITHUB_TOKEN:
        if os.path.exists(FILE_PATH):
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"usuarios": [], "estoque": [], "gift_cards": [], "dados_titular": []}

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        file_content = response.json().get("content")
        decoded_bytes = base64.b64decode(file_content)
        return json.loads(decoded_bytes.decode("utf-8"))
    else:
        return {"usuarios": [], "estoque": [], "gift_cards": [], "dados_titular": []}

def salvar_dados(dados):
    if not GITHUB_TOKEN:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=4)
        return

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    r_get = requests.get(url, headers=headers)
    sha = r_get.json().get("sha") if r_get.status_code == 200 else None

    json_str = json.dumps(dados, ensure_ascii=False, indent=4)
    content_encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    payload = {
        "message": "Atualizando dados da loja via bot",
        "content": content_encoded,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    requests.put(url, headers=headers, json=payload)

def criar_tabelas():
    dados = carregar_dados()
    if not dados.get("usuarios"):
        salvar_dados(dados)
    print("Banco de dados via GitHub configurado com sucesso!")

# --- FUNÇÕES DE COMPATIBILIDADE COM O BOT ---
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

def obter_dados_relatorio():
    dados = carregar_dados()
    clientes = len(dados.get("usuarios", []))
    vendas = len([e for e in dados.get("estoque", []) if e.get("vendido") == 1])
    faturamento = sum([12.0 for e in dados.get("estoque", []) if e.get("vendido") == 1]) # Exemplo estimado
    return vendas, faturamento, clientes

def adicionar_estoque_item(categoria, conteudo, bin="000000", banco="GERAL", bandeira="GERAL"):
    dados = carregar_dados()
    estoque = dados.get("estoque", [])
    
    novo_id = max([e.get("id", 0) for e in estoque], default=0) + 1
    estoque.append({
        "id": novo_id,
        "categoria": categoria,
        "conteudo": conteudo,
        "bin": bin,
        "banco": banco,
        "bandeira": bandeira,
        "vendido": 0
    })
    dados["estoque"] = estoque
    salvar_dados(dados)

def adicionar_dado_titular(conteudo):
    dados = carregar_dados()
    titulares = dados.get("dados_titular", [])
    
    novo_id = max([t.get("id", 0) for t in titulares], default=0) + 1
    titulares.append({
        "id": novo_id,
        "conteudo": conteudo,
        "usado": 0
    })
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
    dados = carregar_dados()
    usuarios = dados.get("usuarios", [])
    estoque = dados.get("estoque", [])
    titulares = dados.get("dados_titular", [])
    
    # Achar usuário
    user = None
    for u in usuarios:
        if u["user_id"] == user_id:
            user = u
            break
            
    if not user:
        return "saldo_insuficiente", None, None, None, None
        
    if user.get("saldo", 0.0) < preco:
        return "saldo_insuficiente", None, None, None, None
        
    # Achar item no estoque
    item_escolhido = None
    for item in estoque:
        if item.get("categoria") == categoria and item.get("vendido") == 0:
            if bin_v and item.get("bin") != bin_v:
                continue
            item_escolhido = item
            break
            
    if not item_escolhido:
        return "esgotado", None, None, None, None
        
    # Achar titular livre (se for GG)
    titular_escolhido = None
    if categoria == "gg":
        for t in titulares:
            if t.get("usado", 0) == 0:
                titular_escolhido = t
                break
        if not titular_escolhido:
            return "falta_dados", None, None, None, None

    # Efetivar a compra
    user["saldo"] -= preco
    item_escolhido["vendido"] = 1
    
    res_dados = "N/A"
    if titular_escolhido:
        titular_escolhido["usado"] = 1
        res_dados = titular_escolhido["conteudo"]

    salvar_dados(dados)
    return "ok", item_escolhido["conteudo"], res_dados, item_escolhido["banco"], item_escolhido["bandeira"]
