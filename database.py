# database.py
import sqlite3
import os
from datetime import datetime, timedelta

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

    # ------------------------- CARDS / KEYS -------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo         TEXT    UNIQUE NOT NULL,
            produto_id     INTEGER,
            senha          TEXT,
            vendido        INTEGER NOT NULL DEFAULT 0,
            comprador_id   INTEGER,
            comprado_em    TEXT,
            adicionado_por INTEGER,
            criado_em      TEXT,
            FOREIGN KEY (produto_id) REFERENCES produtos (id) ON DELETE SET NULL
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


def baixar_estoque(produto_id, qtd=1):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE produtos SET estoque = MAX(0, estoque - ?) WHERE id = ?",
        (qtd, produto_id),
    )
    conn.commit()
    conn.close()


# =====================================================================
# CARDS  (ADICIONAR / CONTAR / BUSCAR)
# =====================================================================
def adicionar_card(codigo, produto_id, senha=None, admin_id=None):
    """Insere UM card. Retorna True se inseriu, False se já existia."""
    codigo = (codigo or "").strip()
    if not codigo:
        return False

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO cards (codigo, produto_id, senha, vendido,
                                  adicionado_por, criado_em)
               VALUES (?, ?, ?, 0, ?, ?)""",
            (codigo, produto_id, senha, admin_id, _now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def adicionar_cards_em_lote(texto, produto_id, admin_id=None):
    """
    Recebe um texto com vários cards, um por linha.
    Formatos aceitos:
        CODE
        CODE:SENHA
        CODE - SENHA
    Retorna (adicionados, duplicados).
    """
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    adicionados = 0
    duplicados = 0

    for linha in linhas:
        if ":" in linha:
            codigo, senha = linha.split(":", 1)
        elif " - " in linha:
            codigo, senha = linha.split(" - ", 1)
        else:
            codigo, senha = linha, None

        codigo = codigo.strip()
        senha = senha.strip() if senha else None
        if not codigo:
            continue

        if adicionar_card(codigo, produto_id, senha, admin_id):
            sincronizar_estoque(produto_id)
            adicionados += 1
        else:
            duplicados += 1

    return adicionados, duplicados


def sincronizar_estoque(produto_id):
    """Estoque = quantidade de cards NÃO vendidos daquele produto."""
    conn = get_conn()
    cur = conn.cursor()
    livres = cur.execute(
        "SELECT COUNT(*) AS c FROM cards WHERE produto_id = ? AND vendido = 0",
        (produto_id,),
    ).fetchone()["c"]
    cur.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (livres, produto_id))
    conn.commit()
    conn.close()
    return livres


def cards_livres(produto_id):
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT * FROM cards WHERE produto_id = ? AND vendido = 0 ORDER BY id ASC LIMIT 50",
        (produto_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def contar_cards_livres(produto_id):
    conn = get_conn()
    cur = conn.cursor()
    c = cur.execute(
        "SELECT COUNT(*) AS c FROM cards WHERE produto_id = ? AND vendido = 0",
        (produto_id,),
    ).fetchone()["c"]
    conn.close()
    return c


def listar_cards(produto_id=None, apenas_livres=True, limite=50):
    conn = get_conn()
    cur = conn.cursor()
    sql = "SELECT * FROM cards WHERE 1=1"
    params = []
    if produto_id is not None:
        sql += " AND produto_id = ?"
        params.append(produto_id)
    if apenas_livres:
        sql += " AND vendido = 0"
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    rows = cur.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deletar_card(card_id):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT produto_id FROM cards WHERE id = ?", (card_id,)).fetchone()
    if row:
        cur.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        conn.commit()
        pid = row["produto_id"]
        conn.close()
        if pid:
            sincronizar_estoque(pid)
        return True
    conn.close()
    return False


# =====================================================================
# VENDAS / COMPRA
# =====================================================================
def realizar_compra_item_casado(user_id, produto_id, quantidade=1, metodo="saldo"):
    """
    Compra 1:N (N cards do MESMO produto).

    IMPORTANTE: esta função agora devolve um DICT:
        {"status": "ok",          "saldo": 12.5, "cards": [...], "total": 5.0}
        {"status": "sem_saldo",   "saldo": 1.0,  "faltam": 4.0}
        {"status": "sem_estoque", "livres": 0}
        {"status": "erro",        "msg": "..."}
    Use sempre res["status"] para decidir.
    """
    produto = get_produto(produto_id)
    if not produto:
        return {"status": "erro", "msg": "Produto não encontrado."}

    usuario = get_usuario(user_id)
    if not usuario:
        return {"status": "erro", "msg": "Usuário não encontrado."}

    total = round(float(produto["preco"]) * int(quantidade), 2)

    livres = cards_livres(produto_id)
    if len(livres) < quantidade:
        return {"status": "sem_estoque", "livres": len(livres)}

    if metodo == "saldo" and float(usuario["saldo"]) < total:
        return {
            "status": "sem_saldo",
            "saldo": float(usuario["saldo"]),
            "faltam": round(total - float(usuario["saldo"]), 2),
        }

    conn = get_conn()
    cur = conn.cursor()
    try:
        codigos = []
        for card in livres[:quantidade]:
            cur.execute(
                "UPDATE cards SET vendido = 1, comprador_id = ?, comprado_em = ? WHERE id = ? AND vendido = 0",
                (user_id, _now(), card["id"]),
            )
            if cur.rowcount:
                codigos.append(card)

        if len(codigos) < quantidade:
            conn.rollback()
            conn.close()
            return {"status": "sem_estoque", "livres": 0}

        if metodo == "saldo":
            cur.execute(
                "UPDATE users SET saldo = saldo - ? WHERE user_id = ?",
                (total, user_id),
            )

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
                "\n".join([c["codigo"] for c in codigos]),
                _now(),
            ),
        )
        conn.commit()

        cur.execute("UPDATE produtos SET estoque = MAX(0, estoque - ?) WHERE id = ?", (quantidade, produto_id))
        conn.commit()

        saldo = cur.execute("SELECT saldo FROM users WHERE user_id = ?", (user_id,)).fetchone()["saldo"]
        conn.close()

        return {"status": "ok", "saldo": float(saldo), "cards": codigos, "total": total}

    except Exception as e:
        conn.rollback()
        conn.close()
        return {"status": "erro", "msg": str(e)}


def registrar_venda(user_id, produto_id, nome_produto, qtd, valor, metodo, cards_txt):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO vendas
           (comprador_id, produto_id, nome_produto, quantidade,
            valor_total, metodo, cards, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, produto_id, nome_produto, qtd, valor, metodo, cards_txt, _now()),
    )
    conn.commit()
    conn.close()


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
        "cards_livres": cur.execute("SELECT COUNT(*) c FROM cards WHERE vendido = 0").fetchone()["c"],
        "cards_vendidos": cur.execute("SELECT COUNT(*) c FROM cards WHERE vendido = 1").fetchone()["c"],
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


# --- apelidos de compatibilidade (não remova) ---
criar_tabelas = init_db

init_db()

