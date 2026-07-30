import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("A variável de ambiente DATABASE_URL não foi configurada!")

# Corrige o prefixo de 'postgres://' para 'postgresql://' exigido pelo SQLAlchemy moderno
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Cria o engine com pool_pre_ping para gerenciar reconexões automaticamente
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def criar_tabelas():
    with engine.begin() as conexao:
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id BIGINT PRIMARY KEY,
                saldo NUMERIC(10, 2) DEFAULT 0.00,
                nome TEXT,
                username TEXT,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
    print("Tabelas verificadas/criadas com sucesso.")

def garantir_usuario(user_id: int, nome: str, username: str):
    with SessionLocal() as session:
        try:
            resultado = session.execute(
                text("SELECT user_id FROM usuarios WHERE user_id = :uid"),
                {"uid": user_id}
            ).fetchone()

            if not resultado:
                session.execute(
                    text("""
                        INSERT INTO usuarios (user_id, saldo, nome, username)
                        VALUES (:uid, 0.00, :nome, :username)
                    """),
                    {"uid": user_id, "nome": nome, "username": username}
                )
                session.commit()
        except Exception as e:
            session.rollback()
            print(f"Erro ao garantir usuário: {e}")
            raise e
        try:
            resultado = session.execute(
                text("SELECT user_id FROM usuarios WHERE user_id = :uid"),
                {"uid": user_id}
            ).fetchone()

            if not resultado:
                session.execute(
                    text("""
                        INSERT INTO usuarios (user_id, saldo, nome, username)
                        VALUES (:uid, 0.00, :nome, :username)
                    """),
                    {"uid": user_id, "nome": nome, "username": username}
                )
                session.commit()
        except Exception as e:
            session.rollback()
            print(f"Erro ao garantir usuário: {e}")
            raise e
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def criar_tabelas():
    with engine.begin() as conexao:
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id BIGINT PRIMARY KEY,
                saldo NUMERIC(10, 2) DEFAULT 0.00,
                nome TEXT,
                username TEXT,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
    print("Tabelas verificadas/criadas com sucesso.")

def garantir_usuario(user_id: int, nome: str, username: str):
    with SessionLocal() as session:
        try:
            resultado = session.execute(
                text("SELECT user_id FROM usuarios WHERE user_id = :uid"),
                {"uid": user_id}
            ).fetchone()

            if not resultado:
                session.execute(
                    text("""
                        INSERT INTO usuarios (user_id, saldo, nome, username)
                        VALUES (:uid, 0.00, :nome, :username)
                    """),
                    {"uid": user_id, "nome": nome, "username": username}
                )
                session.commit()
        except Exception as e:
            session.rollback()
            print(f"Erro ao garantir usuário: {e}")
            raise e

def criar_tabelas():
    with engine.begin() as conexao:
        conexao.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id BIGINT PRIMARY KEY,
                saldo NUMERIC(10, 2) DEFAULT 0.00,
                nome TEXT,
                username TEXT,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
    print("Tabelas verificadas/criadas com sucesso.")

def garantir_usuario(user_id: int, nome: str, username: str):
    with SessionLocal() as session:
        try:
            resultado = session.execute(
                text("SELECT user_id FROM usuarios WHERE user_id = :uid"),
                {"uid": user_id}
            ).fetchone()

            if not resultado:
                session.execute(
                    text("""
                        INSERT INTO usuarios (user_id, saldo, nome, username)
                        VALUES (:uid, 0.00, :nome, :username)
                    """),
                    {"uid": user_id, "nome": nome, "username": username}
                )
                session.commit()
        except Exception as e:
            session.rollback()
            print(f"Erro ao garantir usuário: {e}")
            raise e
