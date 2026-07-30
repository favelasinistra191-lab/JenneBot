"""
Módulo de Banco de Dados - JenneStoreBot
Gerenciamento via SQLAlchemy (PostgreSQL / SQLite)
"""
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import text

# URL do Banco de Dados (Pega do ambiente do Render ou usa SQLite local)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///jenne_store.db")

# Correção para o Render/PostgreSQL se necessário
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Definição das Tabelas ---
class Usuario(Base):
    __tablename__ = 'usuarios'
    user_id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    username = Column(String)
    saldo = Column(Float, default=0.0)

class Estoque(Base):
    __tablename__ = 'estoque'
    id = Column(Integer, primary_key=True, autoincrement=True)
    categoria = Column(String, index=True)      # 'streaming', 'esim', 'gg'
    sub_tipo = Column(String, nullable=True)     # 'NETFLIX', 'CLARO', etc.
    conteudo = Column(Text)                      # Login:Senha, QR Code ou GG
    bin = Column(String, nullable=True)          # BIN do cartão (6 dígitos)
    banco = Column(String, nullable=True)        # Nome do Banco
    bandeira = Column(String, nullable=True)     # VISA, MASTERCARD, etc.
    vendido = Column(Integer, default=0)         # 0 = Disponível, 1 = Vendido

class DadoTitular(Base):
    __tablename__ = 'dados_titular'
    id = Column(Integer, primary_key=True, autoincrement=True)
    conteudo = Column(Text)                      # Nome, CPF, Endereço, etc.
    usado = Column(Integer, default=0)           # 0 = Disponível, 1 = Usado

class GiftCard(Base):
    __tablename__ = 'gift_cards'
    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String, unique=True, index=True)
    valor = Column(Float)
    usado = Column(Integer, default=0)

class Venda(Base):
    __tablename__ = 'vendas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    produto = Column(String)
    valor = Column(Float)


# --- Funções Auxiliares do Banco ---
def criar_tabelas():
    Base.metadata.create_all(bind=engine)

def garantir_usuario(user_id, nome, username):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        if not user:
            novo_user = Usuario(user_id=user_id, nome=nome, username=username, saldo=0.0)
            session.add(novo_user)
            session.commit()
    finally:
        session.close()

def obter_saldo(user_id):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        return user.saldo if user else 0.0
    finally:
        session.close()

def adicionar_estoque_item(categoria, conteudo, sub_tipo=None, bin=None, banco=None, bandeira=None):
    session = SessionLocal()
    try:
        item = Estoque(
            categoria=categoria, 
            sub_tipo=sub_tipo, 
            conteudo=conteudo, 
            bin=bin, 
            banco=banco, 
            bandeira=bandeira, 
            vendido=0
        )
        session.add(item)
        session.commit()
    finally:
        session.close()

def adicionar_dado_titular(conteudo):
    session = SessionLocal()
    try:
        dado = DadoTitular(conteudo=conteudo, usado=0)
        session.add(dado)
        session.commit()
    finally:
        session.close()

def listar_estoque_gg_agrupado():
    session = SessionLocal()
    try:
        # Pega apenas itens que NÃO foram vendidos e que possuem BIN válida
        resultados = session.execute(text(
            "SELECT bin, banco, bandeira, COUNT(*) FROM estoque "
            "WHERE categoria='gg' AND vendido=0 AND bin IS NOT NULL "
            "GROUP BY bin, banco, bandeira"
        )).fetchall()
        return resultados
    finally:
        session.close()

def realizar_compra_item_casado(user_id, categoria, preco, bin_v=None):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        if not user or user.saldo < preco:
            return "saldo_insuficiente", None, None, None, None

        # Busca 1 item de GG disponível na BIN escolhida
        query = session.query(Estoque).filter_by(categoria=categoria, vendido=0)
        if bin_v:
            query = query.filter_by(bin=bin_v)
        
        item_gg = query.first()
        if not item_gg:
            return "sem_estoque", None, None, None, None

        # Busca 1 dado de titular disponível em massa
        dado_titular = session.query(DadoTitular).filter_by(usado=0).first()
        if not dado_titular:
            return "falta_dados", None, None, None, None

        # Desconta saldo e marca como vendidos/usados
        user.saldo -= preco
        item_gg.vendido = 1
        dado_titular.usado = 1

        # Registra a venda
        nova_venda = Venda(user_id=user_id, produto=f"GG {item_gg.bin} + Titular", valor=preco)
        session.add(nova_venda)
        
        session.commit()

        return "ok", item_gg.conteudo, dado_titular.conteudo, item_gg.banco, item_gg.bandeira
    except Exception as e:
        session.rollback()
        print(f"Erro na compra casada: {e}")
        return "erro", None, None, None, None
    finally:
        session.close()

def obter_dados_relatorio():
    session = SessionLocal()
    try:
        total_vendas = session.query(Venda).count()
        faturamento = session.query(db_func_sum(Venda.valor)).scalar() or 0.0
        clientes = session.query(Usuario).count()
        return total_vendas, faturamento, clientes
    except Exception:
        return 0, 0.0, 0
    finally:
        session.close()

def db_func_sum(coluna):
    from sqlalchemy import func
    return func.sum(coluna)
