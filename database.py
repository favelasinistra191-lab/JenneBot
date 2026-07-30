import os
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

# Conexão direta com o seu banco no Supabase
DATABASE_URL = "postgresql://postgres:8Dedezembro@db.ibwndysxzqczxcyyfqwt.supabase.co:5432/postgres"

engine = sa.create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def criar_tabelas():
    metadata = sa.MetaData()
    
    sa.Table(
        'usuarios', metadata,
        sa.Column('user_id', sa.BigInteger, primary_key=True),
        sa.Column('nome', sa.Text),
        sa.Column('username', sa.Text),
        sa.Column('saldo', sa.Float, server_default='0.0')
    )
    
    sa.Table(
        'estoque', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('categoria', sa.Text),
        sa.Column('conteudo', sa.Text),
        sa.Column('bin', sa.Text),
        sa.Column('banco', sa.Text),
        sa.Column('bandeira', sa.Text),
        sa.Column('vendido', sa.Integer, server_default='0')
    )
    
    sa.Table(
        'dados_titular', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('conteudo', sa.Text),
        sa.Column('usado', sa.Integer, server_default='0')
    )
    
    sa.Table(
        'gift_cards', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.Text, unique=True),
        sa.Column('valor', sa.Float),
        sa.Column('usado', sa.Integer, server_default='0')
    )
    
    metadata.create_all(engine)

def garantir_usuario(user_id, nome, username):
    session = SessionLocal()
    try:
        user = session.execute(sa.text("SELECT user_id FROM usuarios WHERE user_id = :u"), {"u": user_id}).fetchone()
        if not user:
            session.execute(
                sa.text("INSERT INTO usuarios (user_id, nome, username, saldo) VALUES (:u, :n, :usr, 0.0)"),
                {"u": user_id, "n": nome, "usr": username}
            )
            session.commit()
    finally:
        session.close()

def obter_saldo(user_id):
    session = SessionLocal()
    try:
        row = session.execute(sa.text("SELECT saldo FROM usuarios WHERE user_id = :u"), {"u": user_id}).fetchone()
        return row[0] if row else 0.0
    finally:
        session.close()

def adicionar_estoque_item(categoria, conteudo, bin, banco, bandeira):
    session = SessionLocal()
    try:
        session.execute(
            sa.text("INSERT INTO estoque (categoria, conteudo, bin, banco, bandeira, vendido) VALUES (:c, :cnt, :b, :bnc, :bnd, 0)"),
            {"c": categoria, "cnt": conteudo, "b": bin, "bnc": banco, "bnd": bandeira}
        )
        session.commit()
    finally:
        session.close()

def adicionar_dado_titular(conteudo):
    session = SessionLocal()
    try:
        session.execute(
            sa.text("INSERT INTO dados_titular (conteudo, usado) VALUES (:c, 0)"),
            {"c": conteudo}
        )
        session.commit()
    finally:
        session.close()

def listar_estoque_gg_agrupado():
    session = SessionLocal()
    try:
        rows = session.execute(sa.text("""
            SELECT bin, bandeira, COUNT(*) 
            FROM estoque 
            WHERE categoria = 'gg' AND vendido = 0 
            GROUP BY bin, bandeira
        """)).fetchall()
        return rows
    finally:
        session.close()

def realizar_compra_item_casado(user_id, categoria, preco, bin_v):
    session = SessionLocal()
    try:
        res_user = session.execute(sa.text("SELECT saldo FROM usuarios WHERE user_id = :u"), {"u": user_id}).fetchone()
        if not res_user or res_user[0] < preco:
            return "saldo_insuficiente", None, None, None, None
            
        res_item = session.execute(
            sa.text("SELECT id, conteudo, banco, bandeira FROM estoque WHERE categoria = :c AND bin = :b AND vendido = 0 LIMIT 1"),
            {"c": categoria, "b": bin_v}
        ).fetchone()
        
        if not res_item:
            return "esgotado", None, None, None, None
            
        item_id, conteudo_gg, banco_item, bandeira_item = res_item
        
        res_dados = session.execute(sa.text("SELECT id, conteudo FROM dados_titular WHERE usado = 0 LIMIT 1")).fetchone()
        if not res_dados:
            return "falta_dados", None, None, None, None
            
        dados_id, conteudo_dados = res_dados
        
        session.execute(sa.text("UPDATE usuarios SET saldo = saldo - :p WHERE user_id = :u"), {"p": preco, "u": user_id})
        session.execute(sa.text("UPDATE estoque SET vendido = 1 WHERE id = :id"), {"id": item_id})
        session.execute(sa.text("UPDATE dados_titular SET usado = 1 WHERE id = :id"), {"id": dados_id})
        session.commit()
        return "ok", conteudo_gg, conteudo_dados, banco_item, bandeira_item
    except Exception as e:
        session.rollback()
        return "erro", None, None, None, None
    finally:
        session.close()

def obter_dados_relatorio():
    session = SessionLocal()
    try:
        total_vendas = session.execute(sa.text("SELECT COUNT(*) FROM estoque WHERE vendido = 1")).scalar() or 0
        faturamento = total_vendas * 10.0
        clientes = session.execute(sa.text("SELECT COUNT(*) FROM usuarios")).scalar() or 0
        return total_vendas, faturamento, clientes
    finally:
        session.close()
