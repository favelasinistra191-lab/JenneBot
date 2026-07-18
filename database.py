"""SQLite: migração não destrutiva, FIFO, vendas e depósitos idempotentes."""

from __future__ import annotations
import sqlite3
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator

# --- CAMINHO PERSISTENTE PARA O RENDER ---
# O Render usa a pasta /data para discos persistentes.
# Se a pasta não existir (rodando localmente), ele usa o diretório atual.
PERSISTENT_PATH = "/data"
if os.path.exists(PERSISTENT_PATH):
    DB_PATH = os.path.join(PERSISTENT_PATH, "bot_database.db")
else:
    DB_PATH = "bot_database.db"

_CENTS = Decimal("0.01")

def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")

def _money(value: float | Decimal | str) -> float:
    return float(Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP))

@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}

def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    if definition.split()[0] not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

def _migrate_nullable(conn: sqlite3.Connection) -> None:
    info = list(conn.execute("PRAGMA table_info(gg_dados)"))
    stock = next((r for r in info if r[1] == "estoque_id"), None)
    if not stock or int(stock[3]) == 0:
        return
    old = {str(r[1]) for r in info}
    conn.execute("ALTER TABLE gg_dados RENAME TO gg_dados_old")
    conn.execute(
        "CREATE TABLE gg_dados(id INTEGER PRIMARY KEY AUTOINCREMENT,estoque_id INTEGER UNIQUE,nome TEXT NOT NULL,cpf_ciphertext TEXT NOT NULL,cpf_fingerprint TEXT NOT NULL,criado_em TEXT NOT NULL,pareado_em TEXT,status TEXT NOT NULL DEFAULT 'pendente',FOREIGN KEY(estoque_id) REFERENCES estoque(id))"
    )
    paired = "pareado_em" if "pareado_em" in old else "criado_em"
    status = "status" if "status" in old else "'pareado'"
    conn.execute(
        f"INSERT INTO gg_dados(id,estoque_id,nome,cpf_ciphertext,cpf_fingerprint,criado_em,pareado_em,status) SELECT id,estoque_id,nome,cpf_ciphertext,cpf_fingerprint,criado_em,{paired},{status} FROM gg_dados_old"
    )
    conn.execute("DROP TABLE gg_dados_old")

def criar_tabelas() -> None:
    with conectar() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS estoque(id INTEGER PRIMARY KEY AUTOINCREMENT,categoria TEXT NOT NULL,conteudo TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'disponivel');
        CREATE TABLE IF NOT EXISTS vendas(id INTEGER PRIMARY KEY AUTOINCREMENT,categoria TEXT NOT NULL,valor REAL NOT NULL,data TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS usuarios(user_id INTEGER PRIMARY KEY,saldo REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS gg_dados(id INTEGER PRIMARY KEY AUTOINCREMENT,estoque_id INTEGER UNIQUE,nome TEXT NOT NULL,cpf_ciphertext TEXT NOT NULL,cpf_fingerprint TEXT NOT NULL,criado_em TEXT NOT NULL,pareado_em TEXT,status TEXT NOT NULL DEFAULT 'pendente',FOREIGN KEY(estoque_id) REFERENCES estoque(id));
        CREATE TABLE IF NOT EXISTS depositos(id INTEGER PRIMARY KEY AUTOINCREMENT,invoice_id TEXT NOT NULL UNIQUE,user_id INTEGER NOT NULL,valor_recebido REAL NOT NULL,bonus_percentual REAL NOT NULL DEFAULT 0,valor_bonus REAL NOT NULL DEFAULT 0,valor_creditado REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pendente',criado_em TEXT NOT NULL,confirmado_em TEXT,FOREIGN KEY(user_id) REFERENCES usuarios(user_id));
        CREATE TABLE IF NOT EXISTS configuracoes(chave TEXT PRIMARY KEY,valor TEXT NOT NULL,atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY AUTOINCREMENT,evento TEXT NOT NULL,ator_id INTEGER,entidade_tipo TEXT,entidade_id TEXT,detalhes TEXT,criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gifts(id INTEGER PRIMARY KEY AUTOINCREMENT,codigo TEXT NOT NULL UNIQUE,valor REAL NOT NULL,status TEXT NOT NULL DEFAULT 'disponivel',criado_em TEXT NOT NULL,resgatado_por INTEGER,resgatado_em TEXT,FOREIGN KEY(resgatado_por) REFERENCES usuarios(user_id));
        """
        )
        _migrate_nullable(conn)
        for d in ("bin TEXT", "banco TEXT", "vendido_para INTEGER", "vendido_em TEXT", "criado_em TEXT"):
            _add_column(conn, "estoque", d)
        for d in ("user_id INTEGER", "estoque_id INTEGER", "invoice_id TEXT", "tipo_pagamento TEXT DEFAULT 'fatura'"):
            _add_column(conn, "vendas", d)
        for d in ("nome TEXT", "username TEXT", "criado_em TEXT", "atualizado_em TEXT"):
            _add_column(conn, "usuarios", d)
        _add_column(conn, "gg_dados", "pareado_em TEXT")
        _add_column(conn, "gg_dados", "status TEXT DEFAULT 'pendente'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_estoque_status ON estoque(categoria,status)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_venda_invoice ON vendas(invoice_id) WHERE invoice_id IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dados_estoque ON gg_dados(estoque_id) WHERE estoque_id IS NOT NULL")
        conn.execute("INSERT OR IGNORE INTO configuracoes VALUES('promocao_percentual','0',?)", (_now(),))
        _pair_fifo(conn, None)

def _audit(conn: sqlite3.Connection, event: str, actor: int | None, kind: str, entity: str, details: str) -> None:
    conn.execute("INSERT INTO auditoria(evento,ator_id,entidade_tipo,entidade_id,detalhes,criado_em) VALUES(?,?,?,?,?,?)", (event, actor, kind, entity, details, _now()))

def _pair_fifo(conn: sqlite3.Connection, actor: int | None) -> list[tuple[int, int]]:
    pairs = []
    while True:
        gg = conn.execute("SELECT id FROM estoque e WHERE categoria='gg' AND status='aguardando_dados' AND NOT EXISTS(SELECT 1 FROM gg_dados d WHERE d.estoque_id=e.id) ORDER BY id LIMIT 1").fetchone()
        data = conn.execute("SELECT id FROM gg_dados WHERE estoque_id IS NULL AND status='pendente' ORDER BY id LIMIT 1").fetchone()
        if not gg or not data: break
        gid, did = int(gg["id"]), int(data["id"])
        conn.execute("UPDATE gg_dados SET estoque_id=?,status='pareado',pareado_em=? WHERE id=? AND estoque_id IS NULL AND status='pendente'", (gid, _now(), did))
        conn.execute("UPDATE estoque SET status='disponivel' WHERE id=? AND status='aguardando_dados'", (gid,))
        _audit(conn, "gg_dados_pareados", actor, "gg_dados", str(did), f"estoque_id={gid}")
        pairs.append((gid, did))
    return pairs

def adicionar_gg_pendente(bin_gg: str, banco: str, conteudo: str, actor: int) -> tuple[int, int | None]:
    with conectar() as conn:
        cur = conn.execute("INSERT INTO estoque(categoria,conteudo,status,bin,banco,criado_em) VALUES('gg',?,'aguardando_dados',?,?,?)", (conteudo.strip(), bin_gg.strip(), banco.strip(), _now()))
        gid = cur.lastrowid
        pairs = _pair_fifo(conn, actor)
        return gid, next((did for sid, did in pairs if sid == gid), None)

def adicionar_dados_pendentes(nome: str, cipher: str, fingerprint: str, actor: int) -> tuple[int, int | None]:
    with conectar() as conn:
        cur = conn.execute("INSERT INTO gg_dados(estoque_id,nome,cpf_ciphertext,cpf_fingerprint,criado_em,status) VALUES(NULL,?,?,?,?,'pendente')", (nome.strip(), cipher, fingerprint, _now()))
        did = cur.lastrowid
        pairs = _pair_fifo(conn, actor)
        return did, next((sid for sid, pid in pairs if pid == did), None)

def garantir_usuario(user_id: int, nome: str | None = None, username: str | None = None) -> None:
    with conectar() as conn:
        now = _now()
        conn.execute("INSERT INTO usuarios(user_id,saldo,nome,username,criado_em,atualizado_em) VALUES(?,0,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET nome=COALESCE(excluded.nome,usuarios.nome),username=COALESCE(excluded.username,usuarios.username),atualizado_em=excluded.atualizado_em", (user_id, nome, username, now, now))

def adicionar_estoque(categoria: str, conteudo: str) -> int:
    with conectar() as conn:
        cur = conn.execute("INSERT INTO estoque(categoria,conteudo,criado_em) VALUES(?,?,?)", (categoria, conteudo.strip(), _now()))
        return cur.lastrowid

def contar_estoque_categoria(categoria: str) -> int:
    with conectar() as conn:
        row = conn.execute("SELECT COUNT(*) n FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='pareado' WHERE e.categoria='gg' AND e.status='disponivel'") if categoria == "gg" else conn.execute("SELECT COUNT(*) n FROM estoque WHERE categoria=? AND status='disponivel'", (categoria,))
        return int(row.fetchone()["n"])

def listar_estoque_gg() -> list[tuple[str, str, int]]:
    with conectar() as conn:
        rows = conn.execute("SELECT COALESCE(NULLIF(e.bin,''),substr(e.conteudo,1,instr(e.conteudo||'|','|')-1)) bin_view,COALESCE(NULLIF(e.banco,''),'Não informado') banco_view,COUNT(*) quantidade FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='pareado' WHERE e.categoria='gg' AND e.status='disponivel' GROUP BY bin_view,banco_view").fetchall()
        return [(str(r["bin_view"]), str(r["banco_view"]), int(r["quantidade"])) for r in rows]

def obter_saldo(uid: int) -> float:
    with conectar() as conn:
        row = conn.execute("SELECT saldo FROM usuarios WHERE user_id=?", (uid,)).fetchone()
        return float(row["saldo"]) if row else 0.0

def criar_gift(codigo: str, valor: float, actor: int) -> None:
    with conectar() as conn:
        conn.execute("INSERT INTO gifts(codigo,valor,criado_em) VALUES(?,?,?)", (codigo.strip(), _money(valor), _now()))

def resgatar_gift(codigo: str, user_id: int) -> float | None:
    garantir_usuario(user_id)
    with conectar() as conn:
        row = conn.execute("SELECT * FROM gifts WHERE codigo=? AND status='disponivel'", (codigo.strip(),)).fetchone()
        if not row: return None
        valor, gift_id = float(row["valor"]), int(row["id"])
        if conn.execute("UPDATE gifts SET status='resgatado',resgatado_por=?,resgatado_em=? WHERE id=? AND status='disponivel'", (user_id, _now(), gift_id)).rowcount != 1: return None
        conn.execute("UPDATE usuarios SET saldo=saldo+?,atualizado_em=? WHERE user_id=?", (valor, _now(), user_id))
        return valor

def obter_status_filas() -> tuple[int, int, int]:
    with conectar() as conn:
        gg = conn.execute("SELECT COUNT(*) n FROM estoque WHERE categoria='gg' AND status='aguardando_dados'").fetchone()["n"]
        data = conn.execute("SELECT COUNT(*) n FROM gg_dados WHERE estoque_id IS NULL AND status='pendente'").fetchone()["n"]
        ready = conn.execute("SELECT COUNT(*) n FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='pareado' WHERE e.categoria='gg' AND e.status='disponivel'").fetchone()["n"]
        return int(gg), int(data), int(ready)

def obter_dados_relatorio() -> tuple[int, float, dict[str, int]]:
    with conectar() as conn:
        row = conn.execute("SELECT COUNT(*) n,COALESCE(SUM(valor),0) total FROM vendas").fetchone()
        grouped = conn.execute("SELECT categoria,COUNT(*) n FROM vendas GROUP BY categoria").fetchall()
        return int(row["n"]), float(row["total"]), {str(r["categoria"]): int(r["n"]) for r in grouped}

def definir_promocao(percent: float, actor: int) -> None:
    with conectar() as conn:
        conn.execute("INSERT INTO configuracoes VALUES('promocao_percentual',?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,atualizado_em=excluded.atualizado_em", (str(percent), _now()))

def obter_promocao() -> float:
    with conectar() as conn:
        row = conn.execute("SELECT valor FROM configuracoes WHERE chave='promocao_percentual'").fetchone()
        return float(row["valor"]) if row else 0.0

def ultimos_depositos(uid: int, limit: int = 5) -> list[sqlite3.Row]:
    with conectar() as conn:
        return conn.execute("SELECT * FROM depositos WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()

def concluir_compra_fatura(inv_id, uid, cat, val, bn=None, bk=None):
    with conectar() as conn:
        if conn.execute("SELECT 1 FROM vendas WHERE invoice_id=?", (inv_id,)).fetchone(): return "ja_processado", None, None
        q = "SELECT e.id,e.conteudo FROM estoque e WHERE e.categoria=? AND e.status='disponivel'"
        p = [cat]
        if cat == "gg": q += " AND EXISTS(SELECT 1 FROM gg_dados d WHERE d.estoque_id=e.id AND d.status='pareado')"
        if bn: q += " AND (e.bin=? OR (e.bin IS NULL AND e.conteudo LIKE ?))"; p.extend([bn, f"{bn}|%"])
        if bk: q += " AND COALESCE(e.banco,'Não informado')=?"; p.append(bk)
        row = conn.execute(q + " ORDER BY e.id LIMIT 1", p).fetchone()
        if not row: return "sem_estoque", None, None
        sid = int(row["id"])
        conn.execute("UPDATE estoque SET status='vendido',vendido_para=?,vendido_em=? WHERE id=?", (uid, _now(), sid))
        if cat == "gg": conn.execute("UPDATE gg_dados SET status='vendido' WHERE estoque_id=?", (sid,))
        conn.execute("INSERT INTO vendas(categoria,valor,user_id,estoque_id,invoice_id) VALUES(?,?,?,?,?)", (cat, _money(val), uid, sid, inv_id))
        return "ok", sid, str(row["conteudo"])

def obter_dados_gg_para_entrega(sid, uid):
    with conectar() as conn:
        return conn.execute("SELECT e.bin,e.banco,d.nome,d.cpf_ciphertext FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id WHERE e.id=? AND e.vendido_para=?", (sid, uid)).fetchone()

def obter_gg_admin(sid, actor):
    with conectar() as conn:
        return conn.execute("SELECT e.id,e.status,e.bin,e.banco,e.conteudo,d.nome,d.cpf_ciphertext FROM estoque e LEFT JOIN gg_dados d ON d.estoque_id=e.id WHERE e.id=?", (sid,)).fetchone()
