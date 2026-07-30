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
        return {"usuarios": [], "produtos": [], "vendas": []}

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        file_content = response.json().get("content")
        decoded_bytes = base64.b64decode(file_content)
        return json.loads(decoded_bytes.decode("utf-8"))
    else:
        return {"usuarios": [], "produtos": [], "vendas": []}

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
