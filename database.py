import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("A variável de ambiente DATABASE_URL não foi configurada!")

engine = None
tentativas = 10
tempo_espera = 5

for tentativa in range(1, tentativas + 1):
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        print("Conexão com o banco de dados estabelecida com sucesso!")
        break
    except Exception as e:
        print(f"Tentativa {tentativa}/{tentativas} falhou ao conectar ao banco: {e}")
        if tentativa < tentativas:
            time.sleep(tempo_espera)
        else:
            raise Exception("Não foi possível conectar ao banco de dados após várias tentativas.")

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
