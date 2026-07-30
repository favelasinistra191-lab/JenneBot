"""PostgreSQL (Supabase): FIFO, vendas e estatísticas de usuários."""

from __future__ import annotations
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator
from sqlalchemy import create_engine, text, Row
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

# --- LINK DE CONEXÃO DO SUPABASE ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.ibwndysxzqczxcyyfqwt:8Dedezembro@aws-0-ca-central-1.pooler.supabase.com:6543/postgres")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)

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
        f"CREATE TABLE IF NOT EXISTS estoque(id {id_type}, categoria TEXT NOT NULL, conteudo TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', bin TEXT, banco TEXT, vendido_para BIGINT, vendido_em TIMESTAMP, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS vendas(id {id_type}, categoria TEXT NOT NULL, valor REAL NOT NULL, user_id BIGINT, estoque_id INTEGER, invoice_id TEXT UNIQUE, data TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS usuarios(user_id BIGINT PRIMARY KEY, saldo REAL NOT NULL DEFAULT 0, nome TEXT, username TEXT, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS gg_dados(id {id_type}, estoque_id INTEGER UNIQUE, nome TEXT NOT NULL, cpf_ciphertext TEXT NOT NULL, cpf_fingerprint TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, pareado_em TIMESTAMP, status TEXT NOT NULL DEFAULT 'pendente')",
        f"CREATE TABLE IF NOT EXISTS depositos(id {id_type}, invoice_id TEXT NOT NULL UNIQUE, user_id BIGINT NOT NULL, valor_recebido REAL NOT NULL, bonus_percentual REAL NOT NULL DEFAULT 0, valor_bonus REAL NOT NULL DEFAULT 0, valor_creditado REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pendente', criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, confirmado_em TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS configuracoes(chave TEXT PRIMARY KEY, valor TEXT NOT NULL, atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS gifts(id {id_type}, codigo TEXT NOT NULL UNIQUE, valor REAL NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resgatado_por BIGINT, resgatado_em TIMESTAMP)",
        f"CREATE TABLE IF NOT EXISTS auditoria(id {id_type}, evento TEXT NOT NULL, detalhes TEXT, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ]
    try:
        with get_db() as session:
            for table_cmd in tables:
                session.execute(text(table_cmd))
            
            # Migração legada
            session.execute(text("UPDATE estoque SET categoria = 'gg', status = 'aguardando_dados' WHERE categoria = 'chave'"))
    except Exception as e:
        # Ignora erro de transação somente-leitura (comum no pooler do Supabase port 6543)
        # Se as tabelas já existirem, o bot funcionará normalmente.
        if "read-only transaction" in str(e):
            print("Aviso: Banco de dados em modo somente-leitura para DDL. Pulando criação de tabelas.")
        else:
            raise e

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

def contar_usuarios_unicos() -> int:
    with get_db() as session:
        res = session.execute(text("SELECT COUNT(*) FROM usuarios"))
        return int(res.fetchone()[0])

def obter_saldo(user_id: int) -> float:
    with get_db() as session:
        res = session.execute(text("SELECT saldo FROM usuarios WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        return float(res[0]) if res else 0.0

def adicionar_gg_pendente(bin_gg: str, banco: str, conteudo: str, actor: int):
    now = datetime.now()
    with get_db() as session:
        res = session.execute(text("INSERT INTO estoque (categoria, conteudo, status, bin, banco, criado_em) VALUES ('gg', :cont, 'aguardando_dados', :bin, :bank, :now) RETURNING id"), {"cont": conteudo.strip(), "bin": bin_gg.strip(), "bank": banco.strip(), "now": now})
        gid = res.fetchone()[0]
        paired_data_id = _pair_fifo(session)
        return gid, paired_data_id

def adicionar_dados_pendentes(nome: str, cipher: str, fingerprint: str, actor: int):
    now = datetime.now()
    with get_db() as session:
        res = session.execute(text("INSERT INTO gg_dados (nome, cpf_ciphertext, cpf_fingerprint, criado_em, status) VALUES (:nome, :cipher, :finger, :now, 'pendente') RETURNING id"), {"nome": nome.strip(), "cipher": cipher, "finger": fingerprint, "now": now})
        did = res.fetchone()[0]
        paired_gg_id = _pair_fifo(session)
        return did, paired_gg_id

def _pair_fifo(session: Session):
    paired_id = None
    while True:
        gg = session.execute(text("SELECT id FROM estoque WHERE categoria='gg' AND status='aguardando_dados' ORDER BY id LIMIT 1")).fetchone()
        data = session.execute(text("SELECT id FROM gg_dados WHERE estoque_id IS NULL AND status='pendente' ORDER BY id LIMIT 1")).fetchone()
        if not gg or not data: break
        gid, did = gg[0], data[0]
        session.execute(text("UPDATE gg_dados SET estoque_id = :gid, status = 'pareado', pareado_em = :now WHERE id = :did"), {"gid": gid, "did": did, "now": datetime.now()})
        session.execute(text("UPDATE estoque SET status = 'disponivel' WHERE id = :gid"), {"gid": gid})
        paired_id = gid # Para o caso de adicionar dados, retorna o ID da GG pareada
    return paired_id

def adicionar_estoque(categoria: str, conteudo: str):
    with get_db() as session:
        res = session.execute(text("INSERT INTO estoque (categoria, conteudo, criado_em) VALUES (:cat, :cont, :now) RETURNING id"), {"cat": categoria, "cont": conteudo.strip(), "now": datetime.now()})
        return res.fetchone()[0]

def contar_estoque_categoria(categoria: str) -> int:
    with get_db() as session:
        if categoria == "gg":
            res = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria = 'gg' AND status = 'disponivel'"))
        else:
            res = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria = :cat AND status = 'disponivel'"), {"cat": categoria})
        return int(res.fetchone()[0])

def listar_estoque_gg():
    with get_db() as session:
        # Pega apenas os 6 primeiros dígitos da BIN (extrai do numero no conteudo)
        # Sem JOIN obrigatório com gg_dados - mostra mesmo se não tiver dados pareados
        res = session.execute(text("""
            SELECT 
                LEFT(regexp_replace(split_part(conteudo, '|', 1), '[^0-9]', '', 'g'), 6) as bin_v,
                TRIM(COALESCE(banco, 'Não identificado')) as bank_v,
                COUNT(*) 
            FROM estoque 
            WHERE categoria = 'gg' 
            AND status = 'disponivel' 
            GROUP BY bin_v, bank_v 
            ORDER BY bin_v
        """)).fetchall()
        return [(r[0], r[1], r[2]) for r in res]

def criar_gift(codigo: str, valor: float, actor: int):
    with get_db() as session:
        session.execute(text("INSERT INTO gifts (codigo, valor, criado_em) VALUES (:code, :val, :now)"), {"code": codigo.strip(), "val": _money(valor), "now": datetime.now()})

def resgatar_gift(codigo: str, user_id: int) -> float | None:
    garantir_usuario(user_id)
    now = datetime.now()
    with get_db() as session:
        is_sqlite = engine.url.drivername == 'sqlite'
        q = "SELECT id, valor FROM gifts WHERE codigo = :code AND status = 'disponivel'"
        if not is_sqlite: q += " FOR UPDATE"
        row = session.execute(text(q), {"code": codigo.strip()}).fetchone()
        if not row: return None
        gid, valor = row[0], float(row[1])
        session.execute(text("UPDATE gifts SET status = 'resgatado', resgatado_por = :uid, resgatado_em = :now WHERE id = :gid"), {"uid": user_id, "gid": gid, "now": now})
        session.execute(text("UPDATE usuarios SET saldo = saldo + :val, atualizado_em = :now WHERE user_id = :uid"), {"val": valor, "uid": user_id, "now": now})
        return valor

def obter_status_filas():
    with get_db() as session:
        gg = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria='gg' AND status='aguardando_dados'")).fetchone()[0]
        data = session.execute(text("SELECT COUNT(*) FROM gg_dados WHERE estoque_id IS NULL AND status='pendente'")).fetchone()[0]
        ready = session.execute(text("SELECT COUNT(*) FROM estoque WHERE categoria='gg' AND status='disponivel'")).fetchone()[0]
        return int(gg), int(data), int(ready)

def obter_dados_relatorio():
    with get_db() as session:
        row = session.execute(text("SELECT COUNT(*), COALESCE(SUM(valor), 0) FROM vendas")).fetchone()
        grouped = session.execute(text("SELECT categoria, COUNT(*) FROM vendas GROUP BY categoria")).fetchall()
        return int(row[0]), float(row[1]), {r[0]: int(r[1]) for r in grouped}

def concluir_compra_fatura(inv_id, uid, cat, val, bn=None, bk=None):
    now = datetime.now()
    with get_db() as session:
        if session.execute(text("SELECT 1 FROM vendas WHERE invoice_id = :inv"), {"inv": inv_id}).fetchone(): return "ja_processado", None, None
        
        is_sqlite = engine.url.drivername == 'sqlite'
        if is_sqlite:
            # SQLite não tem split_part, usamos uma abordagem mais simples para o filtro de BIN
            q = "SELECT e.id, e.conteudo FROM estoque e WHERE e.categoria = :cat AND e.status = 'disponivel'"
            p = {"cat": cat}
            if bn: 
                q += " AND (e.bin = :bn OR e.conteudo LIKE :bn_like)"
                p["bn"] = bn.strip()
                p["bn_like"] = f"{bn.strip()}%"
        else:
            q = "SELECT e.id, e.conteudo FROM estoque e WHERE e.categoria = :cat AND e.status = 'disponivel'"
            p = {"cat": cat}
            if bn: q += " AND (TRIM(split_part(e.conteudo, '|', 1)) = :bn OR TRIM(COALESCE(e.bin, '')) = :bn)"; p["bn"] = bn.strip()
            
        row = session.execute(text(q + " ORDER BY e.id LIMIT 1"), p).fetchone()
        if not row: return "sem_estoque", None, None
        sid, cont = row[0], row[1]
        session.execute(text("UPDATE estoque SET status = 'vendido', vendido_para = :uid, vendido_em = :now WHERE id = :sid"), {"uid": uid, "sid": sid, "now": now})
        if cat == "gg": session.execute(text("UPDATE gg_dados SET status = 'vendido' WHERE estoque_id = :sid"), {"sid": sid})
        session.execute(text("INSERT INTO vendas (categoria, valor, user_id, estoque_id, invoice_id) VALUES (:cat, :val, :uid, :sid, :inv)"), {"cat": cat, "val": _money(val), "uid": uid, "sid": sid, "inv": inv_id})
        session.execute(text("UPDATE usuarios SET saldo = saldo - :val, atualizado_em = :now WHERE user_id = :uid"), {"val": _money(val), "uid": uid, "now": now})
        return "ok", sid, cont

def obter_dados_gg_para_entrega(sid, uid):
    with get_db() as session:
        res = session.execute(text("SELECT e.bin, e.banco, COALESCE(d.nome, 'N/A'), COALESCE(d.cpf_ciphertext, '') FROM estoque e LEFT JOIN gg_dados d ON d.estoque_id = e.id WHERE e.id = :sid AND e.vendido_para = :uid"), {"sid": sid, "uid": uid})
        return res.fetchone()

def log_auditoria(evento: str, detalhes: str = None):
    with get_db() as session:
        session.execute(text("INSERT INTO auditoria (evento, detalhes) VALUES (:ev, :det)"), {"ev": evento, "det": detalhes})

def definir_promocao(valor: float, bonus: float):
    now = datetime.now()
    with get_db() as session:
        session.execute(text("INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES ('promo_min', :v, :now) ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = EXCLUDED.atualizado_em"), {"v": str(valor), "now": now})
        session.execute(text("INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES ('promo_bonus', :b, :now) ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = EXCLUDED.atualizado_em"), {"b": str(bonus), "now": now})

def criar_deposito(inv_id: str, user_id: int, valor: float):
    with get_db() as session:
        session.execute(text("INSERT INTO depositos (invoice_id, user_id, valor_recebido, status) VALUES (:inv, :uid, :val, 'pendente')"), {"inv": inv_id, "uid": user_id, "val": valor})

def confirmar_deposito(inv_id: str, user_id: int):
    now = datetime.now()
    with get_db() as session:
        is_sqlite = engine.url.drivername == 'sqlite'
        q = "SELECT id, valor_recebido, status FROM depositos WHERE invoice_id = :inv AND user_id = :uid"
        if not is_sqlite: q += " FOR UPDATE"
        row = session.execute(text(q), {"inv": inv_id, "uid": user_id}).fetchone()
        if not row: return "nao_encontrado", 0, 0, 0
        if row[2] == 'confirmado': return "ja_processado", 0, 0, 0
        
        val = float(row[1])
        # Lógica de bônus simplificada
        bonus = 0
        total = val + bonus
        
        session.execute(text("UPDATE depositos SET status = 'confirmado', confirmado_em = :now, valor_creditado = :tot WHERE id = :did"), {"tot": total, "did": row[0], "now": now})
        session.execute(text("UPDATE usuarios SET saldo = saldo + :tot, atualizado_em = :now WHERE user_id = :uid"), {"tot": total, "uid": user_id, "now": now})
        log_auditoria("deposito_confirmado", f"user={user_id} valor={val} total={total} moeda=BRL")
        return "ok", val, bonus, total

def corrigir_bins_estoque() -> dict:
    """Reprocessa TODOS os GGs: extrai a BIN correta do conteudo, identifica banco, e atualiza tudo."""
    import requests as req
    
    # Cache de BINs para não repetir consultas à API
    bin_cache = {}
    
    def lookup_bin(bin6: str) -> str:
        if bin6 in bin_cache:
            return bin_cache[bin6]
        try:
            resp = req.get(
                f"https://lookup.binlist.net/{bin6}",
                headers={"Accept-Version": "3"},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                bank_name = data.get("bank", {}).get("name", "Não identificado")
            else:
                bank_name = "Não identificado"
        except Exception:
            bank_name = "Erro na consulta"
        bin_cache[bin6] = bank_name
        return bank_name
    
    with get_db() as session:
        # Buscar TODOS os GGs (inclusive vendidos para referência, mas só atualiza os não vendidos)
        rows = session.execute(text(
            "SELECT id, conteudo, bin, banco, status FROM estoque WHERE categoria = 'gg'"
        )).fetchall()
        
        total = len(rows)
        corrigidos = 0
        erros = 0
        bin_details = {}  # {bin6: banco}
        bin_counts = {}   # {bin6: quantidade}
        
        for row_id, conteudo, bin_atual, banco_atual, status in rows:
            try:
                # Extrair o número do cartão do conteudo
                parts = conteudo.split("|")
                if len(parts) < 2:
                    erros += 1
                    continue
                
                # Extrair apenas dígitos do primeiro campo
                raw_number = parts[0]
                card_number = ""
                for ch in raw_number:
                    if ch.isdigit():
                        card_number += ch
                
                if len(card_number) >= 6:
                    bin6 = card_number[:6]
                    
                    # Identificar banco
                    banco = lookup_bin(bin6)
                    
                    # Rebuild o conteudo com o número limpo (apenas dígitos)
                    if len(parts) >= 3:
                        novo_conteudo = f"{card_number}|{parts[1].strip()}|{parts[2].strip()}"
                    else:
                        novo_conteudo = f"{card_number}|{parts[1].strip()}"
                    
                    # SEMPRE atualiza, sem exceção
                    session.execute(text(
                        "UPDATE estoque SET bin = :bin6, banco = :banco, conteudo = :conteudo WHERE id = :row_id"
                    ), {"bin6": bin6, "banco": banco, "conteudo": novo_conteudo, "row_id": row_id})
                    corrigidos += 1
                    bin_details[bin6] = banco
                    bin_counts[bin6] = bin_counts.get(bin6, 0) + 1
                else:
                    erros += 1
            except Exception:
                erros += 1
    
    # Gerar detalhes de cada BIN corrigida com quantidade
    detalhes = [f"💳 BIN `{b}` → 🏦 `{banco}` ({bin_counts[b]} un)" for b, banco in bin_details.items()]
    
    return {
        "total": total,
        "corrigidos": corrigidos,
        "erros": erros,
        "detalhes": detalhes
    }
