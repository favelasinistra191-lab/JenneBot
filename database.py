import json
import os
import threading

ARQUIVO_DADOS = "dados.json"
lock = threading.Lock()

def criar_tabelas():
    with lock:
        if not os.path.exists(ARQUIVO_DADOS):
            dados_iniciais = {
                "usuarios": [],
                "estoque": [],
                "dados_titular": [],
                "gifts": [],
                "compras": [],
                "configuracoes": {
                    "bonus_porcentagem": 100.0,
                    "bonus_expira_em": None,
                    "banner_file_id": None
                },
                "precos_bins": {}
            }
            with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
                json.dump(dados_iniciais, f, indent=4, ensure_ascii=False)

def carregar_dados(forcar_atualizacao=False):
    with lock:
        if not os.path.exists(ARQUIVO_DADOS):
            criar_tabelas()
        try:
            with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if "precos_bins" not in dados:
                    dados["precos_bins"] = {}
                if "dados_titular" not in dados:
                    dados["dados_titular"] = []
                return dados
        except Exception:
            return {
                "usuarios": [], "estoque": [], "dados_titular": [],
                "gifts": [], "compras": [], "configuracoes": {}, "precos_bins": {}
            }

def salvar_dados(dados):
    with lock:
        with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)

def garantir_usuario(user_id, nome, username, indicado_por=None):
    dados = carregar_dados()
    usuarios = dados.get("usuarios", [])
    
    for u in usuarios:
        if u["user_id"] == user_id:
            return
            
    novo_usuario = {
        "user_id": user_id,
        "nome": nome,
        "username": username,
        "saldo": 0.0,
        "indicado_por": indicado_por
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
    precos = dados.get("precos_bins", {})
    return float(precos.get(str(bin_code), 10.0))

def definir_preco_bin(bin_code, valor):
    dados = carregar_dados()
    if "precos_bins" not in dados:
        dados["precos_bins"] = {}
    dados["precos_bins"][str(bin_code)] = float(valor)
    salvar_dados(dados)

def adicionar_lote_estoque(linhas, categoria="gg", bin="GERAL"):
    dados = carregar_dados()
    if "estoque" not in dados:
        dados["estoque"] = []
    if "dados_titular" not in dados:
        dados["dados_titular"] = []

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        
        # Se for uma linha completa com dados ou CC pura
        if "|" in linha:
            partes = linha.split("|")
            # Identifica se a linha tem dados de titular junto ou é só CC
            if len(partes) >= 6:
                # Exemplo: CC|MES|ANO|CVV|Nome|CPF
                cartao_puro = f"{partes[0]}|{partes[1]}|{partes[2]}|{partes[3]}"
                titular_puro = f"{partes[4]}|{partes[5]}"
                
                dados["estoque"].append({
                    "categoria": str(categoria).lower(),
                    "bin": str(bin),
                    "conteudo": cartao_puro,
                    "vendido": 0
                })
                dados["dados_titular"].append({
                    "conteudo": titular_puro,
                    "usado": 0
                })
            else:
                dados["estoque"].append({
                    "categoria": str(categoria).lower(),
                    "bin": str(bin),
                    "conteudo": linha,
                    "vendido": 0
                })
        else:
            dados["estoque"].append({
                "categoria": str(categoria).lower(),
                "bin": str(bin),
                "conteudo": linha,
                "vendido": 0
            })
            
    salvar_dados(dados)

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    dados = carregar_dados()
    usuarios = dados.get("usuarios", [])
    estoque = dados.get("estoque", [])
    dados_titular = dados.get("dados_titular", [])

    # Localiza o usuário e valida o saldo
    usuario_obj = None
    for u in usuarios:
        if u["user_id"] == user_id:
            usuario_obj = u
            break
            
    if not usuario_obj or float(usuario_obj.get("saldo", 0.0)) < preco:
        return "saldo_insuficiente", None, None, None, None, None

    # Procura um item GG disponível no estoque
    item_escolhido = None
    index_estoque = -1
    for idx, item in enumerate(estoque):
        if str(item.get("categoria", "")).lower() == str(categoria).lower() and int(item.get("vendido", 0)) == 0:
            if bin_v and str(item.get("bin")) != str(bin_v):
                continue
            item_escolhido = item
            index_estoque = idx
            break

    if not item_escolhido:
        return "estoque_esgotado", None, None, None, None, None

    # Procura dados de titular disponíveis
    titular_escolhido = None
    index_titular = -1
    for idx, t in enumerate(dados_titular):
        if int(t.get("usado", 0)) == 0:
            titular_escolhido = t
            index_titular = idx
            break

    if not titular_escolhido:
        # Se não houver dados separados cadastrados, cria um dado coringa padrão para não travar a venda
        dados_titular_str = "TITULAR NÃO INFORMADO|00000000000"
    else:
        dados_titular_str = titular_escolhido["conteudo"]
        dados_titular[index_titular]["usado"] = 1

    # Marca o cartão como vendido
    estoque[index_estoque]["vendido"] = 1
    
    # Desconta o saldo do usuário
    usuario_obj["saldo"] = float(usuario_obj.get("saldo", 0.0)) - preco

    # Registra no histórico de compras
    if "compras" not in dados:
        dados["compras"] = []
    
    conteudo_cc = item_escolhido["conteudo"]
    banco_str = "BANCO GERAL"
    bandeira_str = "VISA/MASTER"
    
    dados["compras"].append({
        "user_id": user_id,
        "conteudo": conteudo_cc,
        "banco": banco_str,
        "bandeira": bandeira_str
    })

    salvar_dados(dados)
    return "ok", conteudo_cc, dados_titular_str, banco_str, bandeira_str, item_escolhido.get("bin")

def obter_historico_compras(user_id):
    dados = carregar_dados()
    compras = dados.get("compras", [])
    return [c for c in compras if c.get("user_id") == user_id]

def adicionar_gift(codigo, valor):
    dados = carregar_dados()
    if "gifts" not in dados:
        dados["gifts"] = []
    dados["gifts"].append({
        "codigo": codigo,
        "valor": float(valor),
        "usado": 0
    })
    salvar_dados(dados)

def resgatar_gift(user_id, codigo):
    dados = carregar_dados()
    gifts = dados.get("gifts", [])
    
    for g in gifts:
        if g["codigo"].upper() == codigo.upper():
            if int(g.get("usado", 0)) == 1:
                return "usado", 0.0
            
            g["usado"] = 1
            valor = float(g.get("valor", 0.0))
            
            for u in dados.get("usuarios", []):
                if u["user_id"] == user_id:
                    u["saldo"] = float(u.get("saldo", 0.0)) + valor
                    break
            
            salvar_dados(dados)
            return "ok", valor
            
    return "invalido", 0.0
