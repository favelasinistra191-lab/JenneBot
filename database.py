"""Módulo de banco de dados para JenneBot - PostgreSQL."""
from __future__ import annotations
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator, List, Tuple, Optional, Dict
from sqlalchemy import create_engine, text, Row
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from config import DATABASE_URL

LOG = logging.getLogger(__name__)

if not DATABASE_URL:
    engine = create_engine("sqlite:///database.db", connect_args={"check_same_thread": False})
else:
    # Ajuste para URLs do Render/Supabase
    db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
    engine = create_engine(db_url, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_CENTS = Decimal("0.01")

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
    is_sqlite = engine.url.drivername == 'sqlite'
    id_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
    
    tables = [
        f"CREATE TABLE IF NOT EXISTS usuarios(user_id BIGINT PRIMARY KEY, saldo REAL NOT NULL DEFAULT 0, nome TEXT, username TEXT, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS estoque(id {id_type}, categoria TEXT NOT NULL, conteudo TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', bin TEXT, banco TEXT, vendido_para BIGINT, vendido_em TIMESTAMP, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS vendas(id {id_type}, categoria TEXT NOT NULL, valor REAL NOT NULL, user_id BIGINT, estoque_id INTEGER, invoice_id TEXT UNIQUE, data TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS gg_dados(id {id_type}, estoque_id INTEGER UNIQUE, nome TEXT NOT NULL, cpf_encrypted TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, pareado_em TIMESTAMP, status TEXT NOT NULL DEFAULT 'pendente')",
        f"CREATE TABLE IF NOT EXISTS gifts(id {id_type}, codigo TEXT NOT NULL UNIQUE, valor REAL NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resgatado_por BIGINT, resgatado_em TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS auditoria(id {id_type}, evento TEXT NOT NULL, detalhes TEXT, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ]
    
    try:
        with get_db() as session:
            for table_cmd in tables:
                session.execute(text(table_cmd))
    except Exception as e:
        LOG.error(f"Erro ao criar tabelas: {e}")

# --- Usuários ---
def garantir_usuario(user_id: int, nome: str = None, username: str = None):
    now = datetime.now()
    with get_db() as session:
        session.execute(text("""
            INSERT INTO usuarios (user_id, saldo, nome, username, atualizado_em) 
            VALUES (:uid, 0, :nome, :user, :now) 
            ON CONFLICT (user_id) DO UPDATE SET 
            nome = COALESCE(EXCLUDED.nome, usuarios.nome), 
            username = COALESCE(EXCLUDED.username, usuarios.username), 
            atualizado_em = EXCLUDED.atualizado_em
        """), {"uid": user_id, "nome": nome, "user": username, "now": now})

def obter_saldo(user_id: int) -> float:
    with get_db() as session:
        res = session.execute(text("SELECT saldo FROM usuarios WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        return float(res[0]) if res else 0.0

# --- Estoque ---
def adicionar_estoque(categoria: str, conteudo: str, bin_v: str = None, banco: str = None):
    with get_db() as session:
        res = session.execute(text("""
            INSERT INTO estoque (categoria, conteudo, bin, banco, status, criado_em) 
            VALUES (:cat, :cont, :bin, :bank, 'disponivel', :now) RETURNING id
        """), {"cat": categoria, "cont": conteudo.strip(), "bin": bin_v, "bank": banco, "now": datetime.now()})
        item_id = res.fetchone()[0]
        if categoria == "gg":
            _tentar_pareamento(session)
        return item_id

def adicionar_dados_gg(nome: str, cpf_encrypted: str):
    with get_db() as session:
        session.execute(text("""
            INSERT INTO gg_dados (nome, cpf_encrypted, status, criado_em) 
            VALUES (:nome, :cpf, 'pendente', :now)
        """), {"nome": nome, "cpf": cpf_encrypted, "now": datetime.now()})
        _tentar_pareamento(session)

def _tentar_pareamento(session: Session):
    # Pega uma GG sem dados e um Dado sem GG
    gg = session.execute(text("SELECT id FROM estoque WHERE categoria='gg' AND status='disponivel' AND id NOT IN (SELECT estoque_id FROM gg_dados WHERE estoque_id IS NOT NULL) ORDER BY id LIMIT 1")).fetchone()
    dado = session.execute(text("SELECT id FROM gg_dados WHERE estoque_id IS NULL AND status='pendente' ORDER BY id LIMIT 1")).fetchone()
    
    if gg and dado:
        session.execute(text("UPDATE gg_dados SET estoque_id = :eid, status = 'pareado', pareado_em = :now WHERE id = :did"), 
                        {"eid": gg[0], "did": dado[0], "now": datetime.now()})

def contar_estoque_categoria(categoria: str) -> int:
    with get_db() as session:
        res = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria = :cat AND status = 'disponivel'"), {"cat": categoria})
        return int(res.fetchone()[0])

def listar_estoque_gg() -> List[Tuple[str, str, int]]:
    with get_db() as session:
        res = session.execute(text("""
            SELECT bin, COALESCE(banco, 'Não identificado'), COUNT(*) 
            FROM estoque 
            WHERE categoria = 'gg' AND status = 'disponivel' 
            GROUP BY bin, banco ORDER BY bin
        """)).fetchall()
        return [(r[0], r[1], r[2]) for r in res]

# --- Vendas ---
def realizar_venda(user_id: int, categoria: str, valor: float, bin_v: str = None) -> Tuple[str, Optional[int], Optional[str]]:
    now = datetime.now()
    inv_id = f"SALE-{user_id}-{int(now.timestamp())}"
    
    with get_db() as session:
        user = session.execute(text("SELECT saldo FROM usuarios WHERE user_id = :uid FOR UPDATE"), {"uid": user_id}).fetchone()
        if not user or user.saldo < valor:
            return "saldo_insuficiente", None, None
            
        query = "SELECT id, conteudo FROM estoque WHERE categoria = :cat AND status = 'disponivel'"
        params = {"cat": categoria}
        if bin_v:
            query += " AND bin = :bin"
            params["bin"] = bin_v
        query += " ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        
        item = session.execute(text(query), params).fetchone()
        if not item:
            return "sem_estoque", None, None
            
        item_id, conteudo = item[0], item[1]
        session.execute(text("UPDATE estoque SET status = 'vendido', vendido_para = :uid, vendido_em = :now WHERE id = :iid"), 
                        {"uid": user_id, "iid": item_id, "now": now})
        session.execute(text("UPDATE usuarios SET saldo = saldo - :val, atualizado_em = :now WHERE user_id = :uid"), 
                        {"val": _money(valor), "uid": user_id, "now": now})
        session.execute(text("INSERT INTO vendas (categoria, valor, user_id, estoque_id, invoice_id, data) VALUES (:cat, :val, :uid, :iid, :inv, :now)"), 
                        {"cat": categoria, "val": _money(valor), "uid": user_id, "iid": item_id, "inv": inv_id, "now": now})
        
        return "ok", item_id, conteudo

def obter_dados_venda_gg(item_id: int):
    with get_db() as session:
        return session.execute(text("""
            SELECT e.conteudo, e.bin, e.banco, d.nome, d.cpf_encrypted 
            FROM estoque e 
            LEFT JOIN gg_dados d ON d.estoque_id = e.id 
            WHERE e.id = :iid
        """), {"iid": item_id}).fetchone()

# --- Gifts ---
def criar_gift(codigo: str, valor: float):
    with get_db() as session:
        session.execute(text("INSERT INTO gifts (codigo, valor, status, criado_em) VALUES (:code, :val, 'disponivel', :now)"), 
                        {"code": codigo.strip(), "val": _money(valor), "now": datetime.now()})

def resgatar_gift(codigo: str, user_id: int) -> Optional[float]:
    now = datetime.now()
    with get_db() as session:
        gift = session.execute(text("SELECT id, valor FROM gifts WHERE codigo = :code AND status = 'disponivel' FOR UPDATE"), 
                               {"code": codigo.strip()}).fetchone()
        if not gift: return None
        gift_id, valor = gift[0], float(gift[1])
        session.execute(text("UPDATE gifts SET status = 'resgatado', resgatado_por = :uid, resgatado_em = :now WHERE id = :gid"), {"uid": user_id, "gid": gift_id, "now": now})
        session.execute(text("UPDATE usuarios SET saldo = saldo + :val, atualizado_em = :now WHERE user_id = :uid"), {"val": valor, "uid": user_id, "now": now})
        return valor

# --- Relatórios ---
def obter_dados_relatorio():
    with get_db() as session:
        res = session.execute(text("SELECT COUNT(*), COALESCE(SUM(valor), 0) FROM vendas")).fetchone()
        grouped = session.execute(text("SELECT categoria, COUNT(*) FROM vendas GROUP BY categoria")).fetchall()
        return int(res[0]), float(res[1]), {r[0]: int(r[1]) for r in grouped}
