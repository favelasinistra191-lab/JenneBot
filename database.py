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
DATABASE_URL = "postgresql://postgres.ibwndysxzqczxcyyfqwt:8Dedezembro@aws-0-ca-central-1.pooler.supabase.com:6543/postgres"

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

def contar_usuarios_unicos() -> int:
    with get_db() as session:
        res = session.execute(text("SELECT COUNT(*) FROM usuarios"))
        return int(res.fetchone()[0])

def obter_saldo(user_id: int) -> float:
    with get_db() as session:
        res = session.execute(text("SELECT saldo FROM usuarios WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        return float(res[0]) if res else 0.0

def adicionar_gg_pendente(bin_gg: str, banco: str, conteudo: str, actor: int):
    with get_db() as db:
        res = db.execute(text("INSERT INTO estoque (categoria, conteudo, status, bin, banco, criado_em) VALUES ('gg', :cont, 'aguardando_dados', :bin, :bank, NOW()) RETURNING id"), {"cont": conteudo.strip(), "bin": bin_gg.strip(), "bank": banco.strip()})
        gid = res.fetchone()[0]
    _pair_fifo_independent()
    return gid

def adicionar_dados_pendentes(nome: str, cipher: str, fingerprint: str, actor: int):
    with get_db() as db:
        res = db.execute(text("INSERT INTO gg_dados (nome, cpf_ciphertext, cpf_fingerprint, criado_em, status) VALUES (:nome, :cipher, :finger, NOW(), 'pendente') RETURNING id"), {"nome": nome.strip(), "cipher": cipher, "finger": fingerprint})
        did = res.fetchone()[0]
    _pair_fifo_independent()
    return did

def _pair_fifo_independent():
    """Pareamento FIFO usando sessao independente (sem depender de sessao externa)."""
    with get_db() as session:
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
        session.execute(text("INSERT INTO gifts (codigo, valor, criado_em) VALUES (:code, :val, NOW())"), {"code": codigo.strip(), "val": _money(valor)})

def resgatar_gift(codigo: str, user_id: int) -> float | None:
    garantir_usuario(user_id)
    with get_db() as session:
        row = session.execute(text("SELECT id, valor FROM gifts WHERE codigo = :code AND status = 'disponivel' FOR UPDATE"), {"code": codigo.strip()}).fetchone()
        if not row: return None
        gid, valor = row[0], float(row[1])
        session.execute(text("UPDATE gifts SET status = 'resgatado', resgatado_por = :uid, resgatado_em = NOW() WHERE id = :gid"), {"uid": user_id, "gid": gid})
        session.execute(text("UPDATE usuarios SET saldo = saldo + :val, atualizado_em = NOW() WHERE user_id = :uid"), {"val": valor, "uid": user_id})
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
    with get_db() as session:
        if session.execute(text("SELECT 1 FROM vendas WHERE invoice_id = :inv"), {"inv": inv_id}).fetchone(): return "ja_processado", None, None
        q = "SELECT e.id, e.conteudo FROM estoque e WHERE e.categoria = :cat AND e.status = 'disponivel'"
        p = {"cat": cat}
        if bn: q += " AND (TRIM(split_part(e.conteudo, '|', 1)) = :bn OR TRIM(COALESCE(e.bin, '')) = :bn)"; p["bn"] = bn.strip()
        row = session.execute(text(q + " ORDER BY e.id LIMIT 1"), p).fetchone()
        if not row: return "sem_estoque", None, None
        sid, cont = row[0], row[1]
        session.execute(text("UPDATE estoque SET status = 'vendido', vendido_para = :uid, vendido_em = NOW() WHERE id = :sid"), {"uid": uid, "sid": sid})
        if cat == "gg": session.execute(text("UPDATE gg_dados SET status = 'vendido' WHERE estoque_id = :sid"), {"sid": sid})
        session.execute(text("INSERT INTO vendas (categoria, valor, user_id, estoque_id, invoice_id) VALUES (:cat, :val, :uid, :sid, :inv)"), {"cat": cat, "val": _money(val), "uid": uid, "sid": sid, "inv": inv_id})
        session.execute(text("UPDATE usuarios SET saldo = saldo - :val, atualizado_em = NOW() WHERE user_id = :uid"), {"val": _money(val), "uid": uid})
        return "ok", sid, cont

def obter_dados_gg_para_entrega(sid, uid):
    with get_db() as session:
        res = session.execute(text("SELECT e.bin, e.banco, COALESCE(d.nome, 'N/A'), COALESCE(d.cpf_ciphertext, '') FROM estoque e LEFT JOIN gg_dados d ON d.estoque_id = e.id WHERE e.id = :sid AND e.vendido_para = :uid"), {"sid": sid, "uid": uid})
        return res.fetchone()

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
