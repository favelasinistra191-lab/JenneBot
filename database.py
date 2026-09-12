import sqlite3
import os
from datetime import datetime

DB_NAME = "bot_telegram.db"


def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # ------------------------- USUÁRIOS -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY,
            username       TEXT,
            first_name     TEXT,
            saldo          REAL    DEFAULT 0,
            pontos         INTEGER DEFAULT 0,
            vip            INTEGER DEFAULT 0,
            indicados      INTEGER DEFAULT 0,
            registrado_em  TEXT,
            ultimo_acesso  TEXT
        )
    """)

    # ------------------------- CONFIGURAÇÕES DO BOT -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave  TEXT PRIMARY KEY,
            valor  TEXT
        )
    """)

    # ------------------------- PRODUTOS -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            nome           TEXT    NOT NULL,
            descricao      TEXT,
            preco          REAL    NOT NULL DEFAULT 0,
            estoque        INTEGER NOT NULL DEFAULT 0,
            imagem         TEXT,
            ativo          INTEGER NOT NULL DEFAULT 1,
            criado_em      TEXT
        )
    """)

    # ------------------------- ESTOQUE DE GGS (BINS) -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS estoque_ggs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id     INTEGER,
            bin            TEXT    NOT NULL,
            bandeira       TEXT    NOT NULL,
            conteudo       TEXT    UNIQUE NOT NULL,
            vendido        INTEGER NOT NULL DEFAULT 0,
            comprador_id   INTEGER,
            comprado_em    TEXT,
            criado_em      TEXT,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
        )
    """)

    # ------------------------- ESTOQUE DE DADOS (NOMES/CPFS) -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS estoque_dados (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id     INTEGER,
            conteudo       TEXT    UNIQUE NOT NULL,
            vendido        INTEGER NOT NULL DEFAULT 0,
            comprador_id   INTEGER,
            comprado_em    TEXT,
            criado_em      TEXT,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE CASCADE
        )
    """)

    # ------------------------- VENDAS -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            comprador_id   INTEGER NOT NULL,
            produto_id     INTEGER,
            nome_produto   TEXT,
            quantidade     INTEGER NOT NULL DEFAULT 1,
            valor_total    REAL    NOT NULL DEFAULT 0,
            metodo         TEXT,
            cards          TEXT,
            criado_em      TEXT,
            FOREIGN KEY (comprador_id) REFERENCES users (user_id) ON DELETE CASCADE,
            FOREIGN KEY (produto_id)   REFERENCES produtos (id)  ON DELETE SET NULL
        )
    """)

    # ------------------------- DEPOSITOS -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS depositos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            valor          REAL    NOT NULL,
            comprovante    TEXT,
            status         TEXT    NOT NULL DEFAULT 'pendente',
            criado_em      TEXT,
            aprovado_em    TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
    """)

    # ------------------------- ADMIN LOG -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER,
            acao       TEXT,
            detalhe    TEXT,
            criado_em  TEXT
        )
    """)

    conn.commit()
    conn.close()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =====================================================================
# CONFIGURAÇÕES (FOTO / TEXTO START)
# =====================================================================
def set_config(chave, valor):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO config (chave, valor) VALUES (?, ?)
        ON CONFLICT(chave) DO UPDATE SET valor = ?
    """, (chave, valor, valor))
    conn.commit()
    conn.close()


def get_config(chave):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    conn.close()
    return row["valor"] if row else None


# =====================================================================
# USUARIOS
# =====================================================================
def registrar_usuario(user_id, username=None, first_name=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existe = cur.fetchone()

    if not existe:
        cur.execute(
            """INSERT INTO users
               (user_id, username, first_name, saldo, pontos, vip,
                indicados, registrado_em, ultimo_acesso)
               VALUES (?, ?, ?, 0, 0, 0, 0, ?, ?)""",
            (user_id, username, first_name, _now(), _now()),
        )
        conn.commit()
        conn.close()
        return True
    else:
        cur.execute(
            "UPDATE users SET username = ?, first_name = ?, ultimo_acesso = ? WHERE user_id = ?",
            (username, first_name, _now(), user_id),
        )
        conn.commit()
        conn.close()
        return False


def garantir_usuario(user_id, first_name=None, username=None):
    return registrar_usuario(user_id, username=username, first_name=first_name)


def get_usuario(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def atualizar_saldo(user_id, valor):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (valor, user_id))
    conn.commit()
    saldo = cur.execute("SELECT saldo FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return saldo["saldo"] if saldo else 0


def set_saldo(user_id, valor):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET saldo = ? WHERE user_id = ?", (valor, user_id))
    conn.commit()
    conn.close()


def add_pontos(user_id, qtd):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET pontos = pontos + ? WHERE user_id = ?", (qtd, user_id))
    conn.commit()
    conn.close()


def set_vip(user_id, dias):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET vip = ? WHERE user_id = ?", (dias, user_id))
    conn.commit()
    conn.close()


def add_indicado(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET indicados = indicados + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def listar_usuarios(limite=100):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY saldo DESC LIMIT ?", (limite,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def total_usuarios():
    conn = get_conn()
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    conn.close()
    return total


# =====================================================================
# PRODUTOS
# =====================================================================
def adicionar_produto(nome, preco, descricao="", estoque=0, imagem=None, produto_id=None):
    conn = get_conn()
    cur = conn.cursor()

    if produto_id:
        cur.execute(
            """UPDATE produtos
               SET nome = ?, preco = ?, descricao = ?, estoque = ?, imagem = ?
               WHERE id = ?""",
            (nome, preco, descricao, estoque, imagem, produto_id),
        )
    else:
        cur.execute(
            """INSERT INTO produtos (nome, descricao, preco, estoque, imagem, ativo, criado_em)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (nome, descricao, preco, estoque, imagem, _now()),
        )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid if not produto_id else produto_id


def get_produto(produto_id):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_produtos(apenas_ativos=True):
    conn = get_conn()
    cur = conn.cursor()
    if apenas_ativos:
        rows = cur.execute(
            "SELECT * FROM produtos WHERE ativo = 1 AND estoque > 0 ORDER BY preco ASC"
        ).fetchall()
    else:
        rows = cur.execute("SELECT * FROM produtos ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remover_produto(produto_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (produto_id,))
    conn.commit()
    conn.close()


def deletar_produto(produto_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
    conn.commit()
    conn.close()


def sincronizar_estoque(produto_id):
    """Estoque do produto é o menor valor entre GGs disponíveis e Dados disponíveis."""
    conn = get_conn()
    cur = conn.cursor()
    ggs_livres = cur.execute("SELECT COUNT(*) AS c FROM estoque_ggs WHERE produto_id = ? AND vendido = 0", (produto_id,)).fetchone()["c"]
    dados_livres = cur.execute("SELECT COUNT(*) AS c FROM estoque_dados WHERE produto_id = ? AND vendido = 0", (produto_id,)).fetchone()["c"]
    
    menor_estoque = min(ggs_livres, dados_livres)
    cur.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (menor_estoque, produto_id))
    conn.commit()
    conn.close()
    return menor_estoque


# =====================================================================
# ESTOQUE SEPARADO (GGS / BINS E DADOS)
# =====================================================================
def identificar_bandeira(bin_str):
    b = str(bin_str).strip()
    if b.startswith("4"):
        return "Visa"
    elif b.startswith(("51", "52", "53", "54", "55")) or (2221 <= int(b[:4]) <= 2720 if b[:4].isdigit() else False):
        return "Mastercard"
    elif b.startswith(("34", "37")):
        return "Amex"
    elif b.startswith("6011") or b.startswith("65") or (644 <= int(b[:3]) <= 649 if b[:3].isdigit() else False):
        return "Discover"
    elif b.startswith("36") or b.startswith("38") or b.startswith("30"):
        return "Diners"
    elif b.startswith("35"):
        return "JCB"
    else:
        return "Desconhecida"


def adicionar_ggs_lote(produto_id, bin_informada, texto_linhas):
    """Adiciona GGs validando se cada linha corresponde à Bin informada (6 primeiros dígitos)."""
    linhas = [l.strip() for l in (texto_linhas or "").splitlines() if l.strip()]
    adicionados = 0
    duplicados = 0
    invalidos = 0

    bin_limpa = "".join(filter(str.isdigit, str(bin_informada)))[:6]
    bandeira = identificar_bandeira(bin_limpa)

    conn = get_conn()
    cur = conn.cursor()

    for linha in linhas:
        numeros_linha = "".join(filter(str.isdigit, linha))
        if not numeros_linha.startswith(bin_limpa):
            invalidos += 1
            continue

        try:
            cur.execute("""
                INSERT INTO estoque_ggs (produto_id, bin, bandeira, conteudo, vendido, criado_em)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (produto_id, bin_limpa, bandeira, linha, _now()))
            adicionados += 1
        except sqlite3.IntegrityError:
            duplicados += 1

    conn.commit()
    conn.close()
    sincronizar_estoque(produto_id)
    return adicionados, duplicados, invalidos


def adicionar_dados_lote(produto_id, texto_linhas):
    """Adiciona CPFs/Nomes/Dados separadamente."""
    linhas = [l.strip() for l in (texto_linhas or "").splitlines() if l.strip()]
    adicionados = 0
    duplicados = 0

    conn = get_conn()
    cur = conn.cursor()

    for linha in linhas:
        if not linha:
            continue
        try:
            cur.execute("""
                INSERT INTO estoque_dados (produto_id, conteudo, vendido, criado_em)
                VALUES (?, ?, 0, ?)
            """, (produto_id, linha, _now()))
            adicionados += 1
        except sqlite3.IntegrityError:
            duplicados += 1

    conn.commit()
    conn.close()
    sincronizar_estoque(produto_id)
    return adicionados, duplicados


def contar_estoque_separado(produto_id):
    conn = get_conn()
    cur = conn.cursor()
    ggs = cur.execute("SELECT COUNT(*) AS c FROM estoque_ggs WHERE produto_id = ? AND vendido = 0", (produto_id,)).fetchone()["c"]
    dados = cur.execute("SELECT COUNT(*) AS c FROM estoque_dados WHERE produto_id = ? AND vendido = 0", (produto_id,)).fetchone()["c"]
    conn.close()
    return ggs, dados


# =====================================================================
# VENDAS / COMPRA DE ITENS CASADOS
# =====================================================================
def realizar_compra_item_casado(user_id, produto_id, quantidade=1, metodo="saldo"):
    produto = get_produto(produto_id)
    if not produto:
        return {"status": "erro", "msg": "Produto não encontrado."}

    usuario = get_usuario(user_id)
    if not usuario:
        return {"status": "erro", "msg": "Usuário não encontrado."}

    total = round(float(produto["preco"]) * int(quantidade), 2)

    ggs_livres, dados_livres = contar_estoque_separado(produto_id)
    if ggs_livres < quantidade or dados_livres < quantidade:
        return {"status": "sem_estoque", "ggs": ggs_livres, "dados": dados_livres}

    if metodo == "saldo" and float(usuario["saldo"]) < total:
        return {
            "status": "sem_saldo",
            "saldo": float(usuario["saldo"]),
            "faltam": round(total - float(usuario["saldo"]), 2),
        }

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Pega N GGs livres
        ggs_selecionadas = cur.execute(
            "SELECT * FROM estoque_ggs WHERE produto_id = ? AND vendido = 0 ORDER BY id ASC LIMIT ?",
            (produto_id, quantidade)
        ).fetchall()

        # Pega N Dados livres
        dados_selecionados = cur.execute(
            "SELECT * FROM estoque_dados WHERE produto_id = ? AND vendido = 0 ORDER BY id ASC LIMIT ?",
            (produto_id, quantidade)
        ).fetchall()

        if len(ggs_selecionadas) < quantidade or len(dados_selecionados) < quantidade:
            conn.rollback()
            conn.close()
            return {"status": "sem_estoque"}

        itens_entregues = []
        for i in range(quantidade):
            gg = ggs_selecionadas[i]
            dado = dados_selecionados[i]

            # Marca GG como vendida e remove
            cur.execute(
                "UPDATE estoque_ggs SET vendido = 1, comprador_id = ?, comprado_em = ? WHERE id = ?",
                (user_id, _now(), gg["id"])
            )
            # Marca Dado como vendido e remove
            cur.execute(
                "UPDATE estoque_dados SET vendido = 1, comprador_id = ?, comprado_em = ? WHERE id = ?",
                (user_id, _now(), dado["id"])
            )

            casado_texto = f"💳 GG: {gg['conteudo']} (Bin: {gg['bin']} - {gg['bandeira']})\n👤 Dados: {dado['conteudo']}"
            itens_entregues.append(casado_texto)

        if metodo == "saldo":
            cur.execute(
                "UPDATE users SET saldo = saldo - ? WHERE user_id = ?",
                (total, user_id),
            )

        texto_venda_final = "\n\n--------------------\n\n".join(itens_entregues)

        cur.execute(
            """INSERT INTO vendas
               (comprador_id, produto_id, nome_produto, quantidade,
                valor_total, metodo, cards, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                produto_id,
                produto["nome"],
                quantidade,
                total,
                metodo,
                texto_venda_final,
                _now(),
            ),
        )
        conn.commit()

        sincronizar_estoque(produto_id)

        saldo = cur.execute("SELECT saldo FROM users WHERE user_id = ?", (user_id,)).fetchone()["saldo"]
        conn.close()

        return {"status": "ok", "saldo": float(saldo), "cards_entregues": itens_entregues, "total": total}

    except Exception as e:
        conn.rollback()
        conn.close()
        return {"status": "erro", "msg": str(e)}


def historico_vendas(user_id=None, limite=50):
    conn = get_conn()
    cur = conn.cursor()
    if user_id:
        rows = cur.execute(
            "SELECT * FROM vendas WHERE comprador_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limite),
        ).fetchall()
    else:
        rows = cur.execute("SELECT * FROM vendas ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def total_vendas():
    conn = get_conn()
    cur = conn.cursor()
    r = cur.execute("SELECT COUNT(*) AS c, COALESCE(SUM(valor_total),0) AS v FROM vendas").fetchone()
    conn.close()
    return r["c"], r["v"]


# =====================================================================
# DEPOSITOS
# =====================================================================
def criar_deposito(user_id, valor, comprovante=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO depositos (user_id, valor, comprovante, status, criado_em)
           VALUES (?, ?, ?, 'pendente', ?)""",
        (user_id, valor, comprovante, _now()),
    )
    conn.commit()
    dep_id = cur.lastrowid
    conn.close()
    return dep_id


def listar_depositos(status="pendente"):
    conn = get_conn()
    cur = conn.cursor()
    if status:
        rows = cur.execute(
            "SELECT * FROM depositos WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
    else:
        rows = cur.execute("SELECT * FROM depositos ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def aprovar_deposito(deposito_id):
    conn = get_conn()
    cur = conn.cursor()
    dep = cur.execute("SELECT * FROM depositos WHERE id = ?", (deposito_id,)).fetchone()
    if not dep or dep["status"] != "pendente":
        conn.close()
        return None

    cur.execute(
        "UPDATE depositos SET status = 'aprovado', aprovado_em = ? WHERE id = ?",
        (_now(), deposito_id),
    )
    cur.execute("UPDATE users SET saldo = saldo + ? WHERE user_id = ?", (dep["valor"], dep["user_id"]))
    conn.commit()
    saldo = cur.execute("SELECT saldo FROM users WHERE user_id = ?", (dep["user_id"],)).fetchone()["saldo"]
    conn.close()
    return saldo


def recusar_deposito(deposito_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE depositos SET status = 'recusado' WHERE id = ?", (deposito_id,))
    conn.commit()
    conn.close()


# =====================================================================
# ESTATISTICAS / LOG
# =====================================================================
def estatisticas():
    conn = get_conn()
    cur = conn.cursor()
    stats = {
        "usuarios": cur.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "produtos": cur.execute("SELECT COUNT(*) c FROM produtos WHERE ativo = 1").fetchone()["c"],
        "ggs_livres": cur.execute("SELECT COUNT(*) c FROM estoque_ggs WHERE vendido = 0").fetchone()["c"],
        "dados_livres": cur.execute("SELECT COUNT(*) c FROM estoque_dados WHERE vendido = 0").fetchone()["c"],
        "vendas": cur.execute("SELECT COUNT(*) c FROM vendas").fetchone()["c"],
        "faturamento": cur.execute("SELECT COALESCE(SUM(valor_total),0) v FROM vendas").fetchone()["v"],
    }
    conn.close()
    return stats


def log_admin(admin_id, acao, detalhe=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO admin_log (admin_id, acao, detalhe, criado_em) VALUES (?, ?, ?, ?)",
        (admin_id, acao, detalhe, _now()),
    )
    conn.commit()
    conn.close()


# --- apelidos de compatibilidade ---
criar_tabelas = init_db

init_db()

