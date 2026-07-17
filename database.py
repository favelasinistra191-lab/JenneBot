"""SQLite: migração não destrutiva, FIFO, vendas e depósitos idempotentes."""

from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator

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
    """Migra bancos do ZIP original e da versão intermediária sem apagar registros."""
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
        CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY AUTOINCREMENT,evento TEXT NOT NULL,ator_id INTEGER,entidade_tipo TEXT,entidade_id TEXT,detalhes TEXT,criado_em TEXT NOT NULL);"""
        )
        _migrate_nullable(conn)
        for d in (
            "bin TEXT",
            "banco TEXT",
            "vendido_para INTEGER",
            "vendido_em TEXT",
            "criado_em TEXT",
        ):
            _add_column(conn, "estoque", d)
        for d in (
            "user_id INTEGER",
            "estoque_id INTEGER",
            "invoice_id TEXT",
            "tipo_pagamento TEXT DEFAULT 'fatura'",
        ):
            _add_column(conn, "vendas", d)
        for d in ("nome TEXT", "username TEXT", "criado_em TEXT", "atualizado_em TEXT"):
            _add_column(conn, "usuarios", d)
        _add_column(conn, "gg_dados", "pareado_em TEXT")
        _add_column(conn, "gg_dados", "status TEXT DEFAULT 'pendente'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_estoque_status ON estoque(categoria,status)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_venda_invoice ON vendas(invoice_id) WHERE invoice_id IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_dados_estoque ON gg_dados(estoque_id) WHERE estoque_id IS NOT NULL"
        )
        conn.execute(
            "INSERT OR IGNORE INTO configuracoes VALUES('promocao_percentual','0',?)",
            (_now(),),
        )
        conn.execute("UPDATE estoque SET categoria='gg' WHERE categoria='chave'")
        conn.execute("UPDATE estoque SET criado_em=COALESCE(criado_em,?)", (_now(),))
        conn.execute(
            "UPDATE gg_dados SET status=CASE WHEN estoque_id IS NULL THEN 'pendente' ELSE CASE WHEN status='vendido' THEN 'vendido' ELSE 'pareado' END END,pareado_em=CASE WHEN estoque_id IS NULL THEN NULL ELSE COALESCE(pareado_em,criado_em) END"
        )
        conn.execute(
            "UPDATE estoque SET status='aguardando_dados' WHERE categoria='gg' AND status='disponivel' AND NOT EXISTS(SELECT 1 FROM gg_dados d WHERE d.estoque_id=estoque.id)"
        )
        _pair_fifo(conn, None)


def _audit(
    conn: sqlite3.Connection,
    event: str,
    actor: int | None,
    kind: str,
    entity: str,
    details: str,
) -> None:
    conn.execute(
        "INSERT INTO auditoria(evento,ator_id,entidade_tipo,entidade_id,detalhes,criado_em) VALUES(?,?,?,?,?,?)",
        (event, actor, kind, entity, details, _now()),
    )


def _pair_fifo(conn: sqlite3.Connection, actor: int | None) -> list[tuple[int, int]]:
    pairs = []
    while True:
        gg = conn.execute(
            "SELECT id FROM estoque e WHERE categoria='gg' AND status='aguardando_dados' AND NOT EXISTS(SELECT 1 FROM gg_dados d WHERE d.estoque_id=e.id) ORDER BY id LIMIT 1"
        ).fetchone()
        data = conn.execute(
            "SELECT id FROM gg_dados WHERE estoque_id IS NULL AND status='pendente' ORDER BY id LIMIT 1"
        ).fetchone()
        if not gg or not data:
            break
        gid, did = int(gg["id"]), int(data["id"])
        a = conn.execute(
            "UPDATE gg_dados SET estoque_id=?,status='pareado',pareado_em=? WHERE id=? AND estoque_id IS NULL AND status='pendente'",
            (gid, _now(), did),
        ).rowcount
        b = conn.execute(
            "UPDATE estoque SET status='disponivel' WHERE id=? AND status='aguardando_dados'",
            (gid,),
        ).rowcount
        if a != 1 or b != 1:
            raise RuntimeError("Falha atômica no pareamento FIFO.")
        _audit(
            conn,
            "gg_dados_pareados",
            actor,
            "gg_dados",
            str(did),
            f"estoque_id={gid};ordem=fifo",
        )
        pairs.append((gid, did))
    return pairs


def adicionar_gg_pendente(
    bin_gg: str, banco: str, conteudo: str, actor: int
) -> tuple[int, int | None]:
    with conectar() as conn:
        cur = conn.execute(
            "INSERT INTO estoque(categoria,conteudo,status,bin,banco,criado_em) VALUES('gg',?,'aguardando_dados',?,?,?)",
            (conteudo.strip(), bin_gg.strip(), banco.strip(), _now()),
        )
        if cur.lastrowid is None:
            raise RuntimeError("Sem ID da GG.")
        gid = cur.lastrowid
        _audit(
            conn,
            "gg_cadastrada_pendente",
            actor,
            "estoque",
            str(gid),
            "aguardando dados FIFO",
        )
        pairs = _pair_fifo(conn, actor)
        return gid, next((did for sid, did in pairs if sid == gid), None)


def adicionar_dados_pendentes(
    nome: str, cipher: str, fingerprint: str, actor: int
) -> tuple[int, int | None]:
    with conectar() as conn:
        cur = conn.execute(
            "INSERT INTO gg_dados(estoque_id,nome,cpf_ciphertext,cpf_fingerprint,criado_em,status) VALUES(NULL,?,?,?,?,'pendente')",
            (nome.strip(), cipher, fingerprint, _now()),
        )
        if cur.lastrowid is None:
            raise RuntimeError("Sem ID dos dados.")
        did = cur.lastrowid
        _audit(
            conn,
            "dados_cadastrados_pendentes",
            actor,
            "gg_dados",
            str(did),
            "CPF criptografado; aguardando FIFO",
        )
        pairs = _pair_fifo(conn, actor)
        return did, next((sid for sid, pid in pairs if pid == did), None)


def garantir_usuario(
    user_id: int, nome: str | None = None, username: str | None = None
) -> None:
    with conectar() as conn:
        now = _now()
        conn.execute(
            "INSERT INTO usuarios(user_id,saldo,nome,username,criado_em,atualizado_em) VALUES(?,0,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET nome=COALESCE(excluded.nome,usuarios.nome),username=COALESCE(excluded.username,usuarios.username),atualizado_em=excluded.atualizado_em",
            (user_id, nome, username, now, now),
        )


def adicionar_estoque(categoria: str, conteudo: str) -> int:
    with conectar() as conn:
        cur = conn.execute(
            "INSERT INTO estoque(categoria,conteudo,criado_em) VALUES(?,?,?)",
            (categoria, conteudo.strip(), _now()),
        )
        if cur.lastrowid is None:
            raise RuntimeError("Sem ID do estoque.")
        return cur.lastrowid


def contar_estoque_categoria(categoria: str) -> int:
    with conectar() as conn:
        row = (
            conn.execute(
                "SELECT COUNT(*) n FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='pareado' WHERE e.categoria='gg' AND e.status='disponivel'"
            ).fetchone()
            if categoria == "gg"
            else conn.execute(
                "SELECT COUNT(*) n FROM estoque WHERE categoria=? AND status='disponivel'",
                (categoria,),
            ).fetchone()
        )
        return int(row["n"])


def listar_estoque_gg() -> list[tuple[str, str, int]]:
    with conectar() as conn:
        rows = conn.execute(
            "SELECT COALESCE(NULLIF(e.bin,''),substr(e.conteudo,1,instr(e.conteudo||'|','|')-1)) bin_view,COALESCE(NULLIF(e.banco,''),'Não informado') banco_view,COUNT(*) quantidade FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='pareado' WHERE e.categoria='gg' AND e.status='disponivel' GROUP BY bin_view,banco_view ORDER BY bin_view,banco_view"
        ).fetchall()
        return [
            (str(r["bin_view"]), str(r["banco_view"]), int(r["quantidade"]))
            for r in rows
        ]


def concluir_compra_fatura(
    invoice_id: str,
    user_id: int,
    categoria: str,
    valor: float,
    bin_gg: str | None = None,
    banco: str | None = None,
) -> tuple[str, int | None, str | None]:
    with conectar() as conn:
        if conn.execute(
            "SELECT 1 FROM vendas WHERE invoice_id=?", (invoice_id,)
        ).fetchone():
            return "ja_processado", None, None
        query = "SELECT e.id,e.conteudo FROM estoque e WHERE e.categoria=? AND e.status='disponivel'"
        params: list[object] = [categoria]
        if categoria == "gg":
            query += " AND EXISTS(SELECT 1 FROM gg_dados d WHERE d.estoque_id=e.id AND d.status='pareado')"
        if bin_gg:
            query += " AND (e.bin=? OR (e.bin IS NULL AND e.conteudo LIKE ?))"
            params.extend([bin_gg, f"{bin_gg}|%"])
        if banco:
            query += " AND COALESCE(e.banco,'Não informado')=?"
            params.append(banco)
        row = conn.execute(query + " ORDER BY e.id LIMIT 1", params).fetchone()
        if not row:
            return "sem_estoque", None, None
        sid = int(row["id"])
        if (
            conn.execute(
                "UPDATE estoque SET status='vendido',vendido_para=?,vendido_em=? WHERE id=? AND status='disponivel'",
                (user_id, _now(), sid),
            ).rowcount
            != 1
        ):
            return "sem_estoque", None, None
        if (
            categoria == "gg"
            and conn.execute(
                "UPDATE gg_dados SET status='vendido' WHERE estoque_id=? AND status='pareado'",
                (sid,),
            ).rowcount
            != 1
        ):
            raise RuntimeError("Par inconsistente.")
        conn.execute(
            "INSERT INTO vendas(categoria,valor,user_id,estoque_id,invoice_id,tipo_pagamento) VALUES(?,?,?,?,?,'fatura')",
            (categoria, _money(valor), user_id, sid, invoice_id),
        )
        _audit(
            conn,
            "produto_vendido",
            user_id,
            "estoque",
            str(sid),
            f"categoria={categoria};invoice_id={invoice_id}",
        )
        return "ok", sid, str(row["conteudo"])


def obter_dados_gg_para_entrega(sid: int, user_id: int) -> sqlite3.Row | None:
    with conectar() as conn:
        row: sqlite3.Row | None = conn.execute(
            "SELECT e.bin,e.banco,d.nome,d.cpf_ciphertext FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='vendido' WHERE e.id=? AND e.status='vendido' AND e.vendido_para=?",
            (sid, user_id),
        ).fetchone()
        return row


def obter_gg_admin(sid: int, actor: int) -> sqlite3.Row | None:
    with conectar() as conn:
        row: sqlite3.Row | None = conn.execute(
            "SELECT e.id,e.status,e.bin,e.banco,e.conteudo,d.nome,d.cpf_ciphertext,d.status dados_status FROM estoque e LEFT JOIN gg_dados d ON d.estoque_id=e.id WHERE e.id=? AND e.categoria='gg'",
            (sid,),
        ).fetchone()
        if row:
            _audit(
                conn,
                "cpf_consultado_admin",
                actor,
                "estoque",
                str(sid),
                "consulta autorizada",
            )
        return row


def obter_status_filas() -> tuple[int, int, int]:
    with conectar() as conn:
        return (
            int(
                conn.execute(
                    "SELECT COUNT(*) n FROM estoque WHERE categoria='gg' AND status='aguardando_dados'"
                ).fetchone()["n"]
            ),
            int(
                conn.execute(
                    "SELECT COUNT(*) n FROM gg_dados WHERE estoque_id IS NULL AND status='pendente'"
                ).fetchone()["n"]
            ),
            int(
                conn.execute(
                    "SELECT COUNT(*) n FROM estoque e JOIN gg_dados d ON d.estoque_id=e.id AND d.status='pareado' WHERE e.categoria='gg' AND e.status='disponivel'"
                ).fetchone()["n"]
            ),
        )


def obter_saldo(uid: int) -> float:
    with conectar() as conn:
        row = conn.execute(
            "SELECT saldo FROM usuarios WHERE user_id=?", (uid,)
        ).fetchone()
        return float(row["saldo"]) if row else 0.0


def obter_dados_relatorio() -> tuple[int, float, dict[str, int]]:
    with conectar() as conn:
        row = conn.execute(
            "SELECT COUNT(*) n,COALESCE(SUM(valor),0) total FROM vendas"
        ).fetchone()
        grouped = conn.execute(
            "SELECT categoria,COUNT(*) n FROM vendas GROUP BY categoria"
        ).fetchall()
        return (
            int(row["n"]),
            float(row["total"]),
            {str(r["categoria"]): int(r["n"]) for r in grouped},
        )


def criar_deposito(invoice_id: str, uid: int, value: float) -> None:
    garantir_usuario(uid)
    amount = _money(value)
    with conectar() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO depositos(invoice_id,user_id,valor_recebido,valor_creditado,status,criado_em) VALUES(?,?,?,?,'pendente',?)",
            (invoice_id, uid, amount, amount, _now()),
        )


def confirmar_deposito(invoice_id: str, uid: int) -> tuple[str, float, float, float]:
    with conectar() as conn:
        row = conn.execute(
            "SELECT * FROM depositos WHERE invoice_id=? AND user_id=?",
            (invoice_id, uid),
        ).fetchone()
        if not row:
            return "nao_encontrado", 0, 0, 0
        if row["status"] == "confirmado":
            return (
                "ja_processado",
                float(row["valor_recebido"]),
                float(row["valor_bonus"]),
                float(row["valor_creditado"]),
            )
        promo = conn.execute(
            "SELECT valor FROM configuracoes WHERE chave='promocao_percentual'"
        ).fetchone()
        percent = Decimal(str(promo["valor"] if promo else 0))
        received = Decimal(str(row["valor_recebido"]))
        bonus = (received * percent / 100).quantize(_CENTS, rounding=ROUND_HALF_UP)
        credited = received + bonus
        if (
            conn.execute(
                "UPDATE depositos SET status='confirmado',bonus_percentual=?,valor_bonus=?,valor_creditado=?,confirmado_em=? WHERE id=? AND status='pendente'",
                (float(percent), float(bonus), float(credited), _now(), int(row["id"])),
            ).rowcount
            != 1
        ):
            latest = conn.execute(
                "SELECT * FROM depositos WHERE id=?", (int(row["id"]),)
            ).fetchone()
            return (
                "ja_processado",
                float(latest["valor_recebido"]),
                float(latest["valor_bonus"]),
                float(latest["valor_creditado"]),
            )
        conn.execute(
            "UPDATE usuarios SET saldo=saldo+?,atualizado_em=? WHERE user_id=?",
            (float(credited), _now(), uid),
        )
        _audit(
            conn,
            "deposito_confirmado",
            uid,
            "deposito",
            str(row["id"]),
            f"moeda=BRL;recebido={received:.2f};bonus={bonus:.2f};creditado={credited:.2f}",
        )
        return "ok", float(received), float(bonus), float(credited)


def definir_promocao(percent: float, actor: int) -> None:
    if not 0 <= percent <= 1000:
        raise ValueError("Percentual inválido.")
    with conectar() as conn:
        conn.execute(
            "INSERT INTO configuracoes VALUES('promocao_percentual',?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,atualizado_em=excluded.atualizado_em",
            (str(percent), _now()),
        )
        _audit(
            conn,
            "promocao_alterada",
            actor,
            "configuracao",
            "promocao_percentual",
            f"percentual={percent};moeda=BRL",
        )


def obter_promocao() -> float:
    with conectar() as conn:
        row = conn.execute(
            "SELECT valor FROM configuracoes WHERE chave='promocao_percentual'"
        ).fetchone()
        return float(row["valor"]) if row else 0.0


def ultimos_depositos(uid: int, limit: int = 5) -> list[sqlite3.Row]:
    with conectar() as conn:
        return conn.execute(
            "SELECT * FROM depositos WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (uid, limit),
        ).fetchall()
