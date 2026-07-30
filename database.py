import sqlite3
import os

DB_NAME = "loja.db"

def SessionLocal():
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker
    engine = sa.create_engine(f"sqlite:///{DB_NAME}")
    Session = sessionmaker(bind=engine)
    return Session()

def criar_tabelas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            username TEXT,
            saldo REAL DEFAULT 0.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT,
            conteudo TEXT,
            bin TEXT,
            banco TEXT,
            bandeira TEXT,
            vendido INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dados_titular (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conteudo TEXT,
            usado INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gift_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            valor REAL,
            usado INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def garantir_usuario(user_id, nome, username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM usuarios WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (user_id, nome, username, saldo) VALUES (?, ?, ?, 0.0)", (user_id, nome, username))
        conn.commit()
    conn.close()

def obter_saldo(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT saldo FROM usuarios WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def adicionar_estoque_item(categoria, conteudo, bin, banco, bandeira):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO estoque (categoria, conteudo, bin, banco, bandeira, vendido) VALUES (?, ?, ?, ?, ?, 0)",
        (categoria, conteudo, bin, banco, bandeira)
    )
    conn.commit()
    conn.close()

def adicionar_dado_titular(conteudo):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO dados_titular (conteudo, usado) VALUES (?, 0)", (conteudo,))
    conn.commit()
    conn.close()

def listar_estoque_gg_agrupado():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bin, bandeira, COUNT(*) 
        FROM estoque 
        WHERE categoria = 'gg' AND vendido = 0 
        GROUP BY bin, bandeira
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def realizar_compra_item_casado(user_id, categoria, preco, bin_v):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT saldo FROM usuarios WHERE user_id = ?", (user_id,))
    res_user = cursor.fetchone()
    if not res_user or res_user[0] < preco:
        conn.close()
        return "saldo_insuficiente", None, None, None, None
        
    cursor.execute("SELECT id, conteudo, banco, bandeira FROM estoque WHERE categoria = ? AND bin = ? AND vendido = 0 LIMIT 1", (categoria, bin_v))
    res_item = cursor.fetchone()
    if not res_item:
        conn.close()
        return "esgotado", None, None, None, None
        
    item_id, conteudo_gg, banco_item, bandeira_item = res_item
    
    cursor.execute("SELECT id, conteudo FROM dados_titular WHERE usado = 0 LIMIT 1")
    res_dados = cursor.fetchone()
    if not res_dados:
        conn.close()
        return "falta_dados", None, None, None, None
        
    dados_id, conteudo_dados = res_dados
    
    try:
        cursor.execute("UPDATE usuarios SET saldo = saldo - ? WHERE user_id = ?", (preco, user_id))
        cursor.execute("UPDATE estoque SET vendido = 1 WHERE id = ?", (item_id,))
        cursor.execute("UPDATE dados_titular SET usado = 1 WHERE id = ?", (dados_id,))
        conn.commit()
        conn.close()
        return "ok", conteudo_gg, conteudo_dados, banco_item, bandeira_item
    except Exception as e:
        conn.rollback()
        conn.close()
        return "erro", None, None, None, None

def obter_dados_relatorio():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM estoque WHERE vendido = 1")
    total_vendas = cursor.fetchone()[0]
    # Faturamento baseado na média dos novos preços para estimativa do painel admin
    faturamento = total_vendas * 10.0
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    clientes = cursor.fetchone()[0]
    conn.close()
    return total_vendas, faturamento, clientes
