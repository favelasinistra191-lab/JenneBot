"""PostgreSQL (Supabase): FIFO, vendas e depósitos idempotentes."""

from __future__ import annotations
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator
from sqlalchemy import create_url, create_engine, text, Row
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

# --- LINK DE CONEXÃO DO SUPABASE ---
DATABASE_URL = "postgresql://postgres.ibwndysxzqczxcyyfqwt:8Dedezembro@aws-0-ca-central-1.pooler.supabase.com:6543/postgres"

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_CENTS = Decimal("0.01")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _money(value: float | Decimal | str) -> float:
    return float(Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP))

@contextmanager
def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def criar_tabelas() -> None:
    with get_db() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS estoque(id SERIAL PRIMARY KEY, categoria TEXT NOT NULL, conteudo TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', bin TEXT, banco TEXT, vendido_para BIGINT, vendido_em TIMESTAMP, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS vendas(id SERIAL PRIMARY KEY, categoria TEXT NOT NULL, valor REAL NOT NULL, user_id BIGINT, estoque_id INTEGER, invoice_id TEXT UNIQUE, data TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS usuarios(user_id BIGINT PRIMARY KEY, saldo REAL NOT NULL DEFAULT 0, nome TEXT, username TEXT, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS gg_dados(id SERIAL PRIMARY KEY, estoque_id INTEGER UNIQUE, nome TEXT NOT NULL, cpf_ciphertext TEXT NOT NULL, cpf_fingerprint TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, pareado_em TIMESTAMP, status TEXT NOT NULL DEFAULT 'pendente');
            CREATE TABLE IF NOT EXISTS depositos(id SERIAL PRIMARY KEY, invoice_id TEXT NOT NULL UNIQUE, user_id BIGINT NOT NULL, valor_recebido REAL NOT NULL, bonus_percentual REAL NOT NULL DEFAULT 0, valor_bonus REAL NOT NULL DEFAULT 0, valor_creditado REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pendente', criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, confirmado_em TIMESTAMP);
            CREATE TABLE IF NOT EXISTS configuracoes(chave TEXT PRIMARY KEY, valor TEXT NOT NULL, atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS gifts(id SERIAL PRIMARY KEY, codigo TEXT NOT NULL UNIQUE, valor REAL NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resgatado_por BIGINT, resgatado_em TIMESTAMP);
        """))
        session.execute(text("INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES ('promocao_percentual', '0', NOW()) ON CONFLICT (chave) DO NOTHING"))

def garantir_usuario(user_id: int, nome: str = None, username: str = None):
    with get_db() as session:
        session.execute(text("""
            INSERT INTO usuarios (user_id, saldo, nome, username, atualizado_em) 
            VALUES (:uid, 0, :nome, :user, NOW()) 
            ON CONFLICT (user_id) DO UPDATE SET 
            nome = COALESCE(EXCLUDED.nome, usuarios.nome), 
            username = COALESCE(EXCLUDED.username, usuarios.username), 
            atualizado_em = NOW()
        """), {"uid": user_id, "nome": nome, "user": username})

def obter_saldo(user_id: int) -> float:
    with get_db() as session:
        res = session.execute(text("SELECT saldo FROM usuarios WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        return float(res[0]) if res else 0.0

def adicionar_gg_pendente(bin_gg: str, banco: str, conteudo: str, actor: int):
    with get_db() as session:
        res = session.execute(text("""
            INSERT INTO estoque (categoria, conteudo, status, bin, banco, criado_em) 
            VALUES ('gg', :cont, 'aguardando_dados', :bin, :bank, NOW()) RETURNING id
        """), {"cont": conteudo.strip(), "bin": bin_gg.strip(), "bank": banco.strip()})
        gid = res.fetchone()[0]
        _pair_fifo(session)
        return gid

def adicionar_dados_pendentes(nome: str, cipher: str, fingerprint: str, actor: int):
    with get_db() as session:
        res = session.execute(text("""
            INSERT INTO gg_dados (nome, cpf_ciphertext, cpf_fingerprint, criado_em, status) 
            VALUES (:nome, :cipher, :finger, NOW(), 'pendente') RETURNING id
        """), {"nome": nome.strip(), "cipher": cipher, "finger": fingerprint})
        did = res.fetchone()[0]
        _pair_fifo(session)
        return did

def _pair_fifo(session: Session):
    while True:
        gg = session.execute(text("SELECT id FROM estoque WHERE categoria='gg' AND status='aguardando_dados' ORDER BY id LIMIT 1")).fetchone()
        data = session.execute(text("SELECT id FROM gg_dados WHERE estoque_id IS NULL AND status='pendente' ORDER BY id LIMIT 1")).fetchone()
        if not gg or not data: break
        gid, did = gg[0], data[0]
        session.execute(text("UPDATE gg_dados SET estoque_id = :gid, status = 'pareado', pareado_em = NOW() WHERE id = :did"), {"gid": gid, "did": did})
        session.execute(text("UPDATE estoque SET status = 'disponivel' WHERE id = :gid"), {"gid": gid})

def adicionar_estoque(categoria: str, conteudo: str):
    with get_db() as session:
        res = session.execute(text("INSERT INTO estoque (categoria, conteudo, criado_em) VALUES (:cat, :cont, NOW()) RETURNING id"), {"cat": categoria, "cont": conteudo.strip()})
        return res.fetchone()[0]

def contar_estoque_categoria(categoria: str) -> int:
    with get_db() as session:
        if categoria == "gg":
            res = session.execute(text("SELECT COUNT(*) FROM estoque e JOIN gg_dados d ON d.estoque_id = e.id WHERE e.categoria = 'gg' AND e.status = 'disponivel' AND d.status = 'pareado'"))
        else:
            res = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria = :cat AND status = 'disponivel'"), {"cat": categoria})
        return int(res.fetchone()[0])

def listar_estoque_gg():
    with get_db() as session:
        res = session.execute(text("""
            SELECT COALESCE(bin, split_part(conteudo, '|', 1)) as bin_v, COALESCE(banco, 'Não informado') as bank_v, COUNT(*) 
            FROM estoque e JOIN gg_dados d ON d.estoque_id = e.id 
            WHERE e.categoria = 'gg' AND e.status = 'disponivel' AND d.status = 'pareado' 
            GROUP BY bin_v, bank_v
        """)).fetchall()
        return [(r[0], r[1], r[2]) for r in res]

def criar_gift(codigo: str, valor: float, actor: int):
    with get_db() as session:
        session.execute(text("INSERT INTO gifts (codigo, valor, criado_em) VALUES (:code, :val, NOW())"), {"code": codigo.strip(), "val": _money(valor)})

def resgatar_gift(codigo: str, user_id: int) -> float | None:
    garantir_usuario(user_id)
    with get_db() as session:
        row = session.execute(text("SELECT id, valor FROM gifts WHERE codigo = :code AND status = 'disponivel'"), {"code": codigo.strip()}).fetchone()
        if not row: return None
        gid, valor = row[0], float(row[1])
        session.execute(text("UPDATE gifts SET status = 'resgatado', resgatado_por = :uid, resgatado_em = NOW() WHERE id = :gid"), {"uid": user_id, "gid": gid})
        session.execute(text("UPDATE usuarios SET saldo = saldo + :val, atualizado_em = NOW() WHERE user_id = :uid"), {"val": valor, "uid": user_id})
        return valor

def obter_status_filas():
    with get_db() as session:
        gg = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria='gg' AND status='aguardando_dados'")).fetchone()[0]
        data = session.execute(text("SELECT COUNT(*) FROM gg_dados WHERE estoque_id IS NULL AND status='pendente'")).fetchone()[0]
        ready = session.execute(text("SELECT COUNT(*) FROM estoque e JOIN gg_dados d ON d.estoque_id = e.id WHERE e.categoria='gg' AND e.status='disponivel' AND d.status='pareado'")).fetchone()[0]
        return int(gg), int(data), int(ready)

def obter_dados_relatorio():
    with get_db() as session:
        row = session.execute(text("SELECT COUNT(*), COALESCE(SUM(valor), 0) FROM vendas")).fetchone()
        grouped = session.execute(text("SELECT categoria, COUNT(*) FROM vendas GROUP BY categoria")).fetchall()
        return int(row[0]), float(row[1]), {r[0]: int(r[1]) for r in grouped}

def concluir_compra_fatura(inv_id, uid, cat, val, bn=None, bk=None):
    with get_db() as session:
        if session.execute(text("SELECT 1 FROM vendas WHERE invoice_id = :inv"), {"inv": inv_id}).fetchone(): return "ja_processado", None, None
        q = "SELECT e.id, e.conteudo FROM estoque e WHERE e.categoria = :cat AND e.status = 'disponivel'"
        p = {"cat": cat}
        if cat == "gg": q += " AND EXISTS(SELECT 1 FROM gg_dados d WHERE d.estoque_id = e.id AND d.status = 'pareado')"
        if bn: q += " AND (e.bin = :bn OR (e.bin IS NULL AND e.conteudo LIKE :bn_like))"; p["bn"] = bn; p["bn_like"] = f"{bn}|%"
        if bk: q += " AND COALESCE(e.banco, 'Não informado') = :bk"; p["bk"] = bk
        row = session.execute(text(q + " ORDER BY e.id LIMIT 1"), p).fetchone()
        if not row: return "sem_estoque", None, None
        sid, cont = row[0], row[1]
        session.execute(text("UPDATE estoque SET status = 'vendido', vendido_para = :uid, vendido_em = NOW() WHERE id = :sid"), {"uid": uid, "sid": sid})
        if cat == "gg": session.execute(text("UPDATE gg_dados SET status = 'vendido' WHERE estoque_id = :sid"), {"sid": sid})
        session.execute(text("INSERT INTO vendas (categoria, valor, user_id, estoque_id, invoice_id) VALUES (:cat, :val, :uid, :sid, :inv)"), {"cat": cat, "val": _money(val), "uid": uid, "sid": sid, "inv": inv_id})
        return "ok", sid, cont

def obter_dados_gg_para_entrega(sid, uid):
    with get_db() as session:
        res = session.execute(text("SELECT e.bin, e.banco, d.nome, d.cpf_ciphertext FROM estoque e JOIN gg_dados d ON d.estoque_id = e.id WHERE e.id = :sid AND e.vendido_para = :uid"), {"sid": sid, "uid": uid})
        return res.fetchone()

def obter_gg_admin(sid, actor):
    with get_db() as session:
        res = session.execute(text("SELECT e.id, e.status, e.bin, e.banco, e.conteudo, d.nome, d.cpf_ciphertext FROM estoque e LEFT JOIN gg_dados d ON d.estoque_id = e.id WHERE e.id = :sid"), {"sid": sid})
        return res.fetchone()
