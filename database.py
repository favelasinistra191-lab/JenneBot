"""
Módulo de Banco de Dados - JenneStoreBot
Gerenciamento de usuários, estoque, vendas e criptografia.
"""
import os
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import config

LOG = logging.getLogger("JenneDatabase")

# Configuração do Banco de Dados PostgreSQL (Aiven) - Blindado contra erro de dialeto
DATABASE_URL = os.getenv("DATABASE_URL", getattr(config, "DATABASE_URL", ""))

if not DATABASE_URL:
    LOG.error("DATABASE_URL não configurada!")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- Modelos das Tabelas ---
class Usuario(Base):
    __tablename__ = 'usuarios'
    user_id = Column(Integer, primary_key=True)
    nome = Column(String(150))
    username = Column(String(100), nullable=True)
    saldo = Column(Float, default=0.0)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Estoque(Base):
    __tablename__ = 'estoque'
    id = Column(Integer, primary_key=True, autoincrement=True)
    categoria = Column(String(50))  # 'streaming', 'esim', 'gg'
    conteudo = Column(Text)          # login:senha ou numero|validade|cvv
    bin = Column(String(20), nullable=True)
    banco = Column(String(100), nullable=True)
    vendido = Column(Integer, default=0)  # 0 = Disponível, 1 = Vendido


class DadosGG(Base):
    __tablename__ = 'dados_gg'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(150))
    cpf_encrypted = Column(Text)
    usado = Column(Integer, default=0)


class Venda(Base):
    __tablename__ = 'vendas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    categoria = Column(String(50))
    valor = Column(Float)
    item_id = Column(Integer, nullable=True)
    data = Column(DateTime, default=datetime.utcnow)


class GiftCard(Base):
    __tablename__ = 'gift_cards'
    codigo = Column(String(100), primary_key=True)
    valor = Column(Float)
    usado = Column(Integer, default=0)


# --- Funções de Inicialização ---
def criar_tabelas():
    try:
        Base.metadata.create_all(bind=engine)
        LOG.info("Tabelas verificadas/criadas com sucesso.")
    except Exception as e:
        LOG.error(f"Erro ao criar tabelas: {e}")


# --- Funções de Usuário ---
def garantir_usuario(user_id, nome, username):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        if not user:
            user = Usuario(user_id=user_id, nome=nome, username=username, saldo=0.0)
            session.add(user)
        else:
            user.nome = nome
            user.username = username
        session.commit()
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em garantir_usuario: {e}")
    finally:
        session.close()


def obter_saldo(user_id):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        return user.saldo if user else 0.0
    except Exception as e:
        LOG.error(f"Erro em obter_saldo: {e}")
        return 0.0
    finally:
        session.close()


# --- Funções de Estoque e Vendas ---
def listar_estoque_gg():
    session = SessionLocal()
    try:
        from sqlalchemy import func
        results = (
            session.query(Estoque.bin, Estoque.banco, func.count(Estoque.id))
            .filter_by(categoria='gg', vendido=0)
            .group_by(Estoque.bin, Estoque.banco)
            .all()
        )
        return results
    except Exception as e:
        LOG.error(f"Erro em listar_estoque_gg: {e}")
        return []
    finally:
        session.close()


def contar_estoque_categoria(categoria):
    session = SessionLocal()
    try:
        return session.query(Estoque).filter_by(categoria=categoria, vendido=0).count()
    except Exception as e:
        LOG.error(f"Erro em contar_estoque_categoria: {e}")
        return 0
    finally:
        session.close()


def realizar_venda(user_id, categoria, preco, bin_v=None):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        if not user or user.saldo < preco:
            return "saldo_insuficiente", None, None

        query = session.query(Estoque).filter_by(categoria=categoria, vendido=0)
        if bin_v:
            query = query.filter_by(bin=bin_v)
        
        item = query.first()
        if not item:
            return "sem_estoque", None, None

        user.saldo -= preco
        item.vendido = 1

        venda = Venda(user_id=user_id, categoria=categoria, valor=preco, item_id=item.id)
        session.add(venda)
        session.commit()

        return "ok", item.id, item.conteudo
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em realizar_venda: {e}")
        return "erro_interno", None, None
    finally:
        session.close()


def obter_dados_venda_gg(item_id):
    session = SessionLocal()
    try:
        item = session.query(Estoque).filter_by(id=item_id).first()
        if not item:
            return None
        
        dado = session.query(DadosGG).filter_by(usado=0).first()
        titular = dado.nome if dado else "Não informado"
        cpf_enc = dado.cpf_encrypted if dado else None
        
        if dado:
            dado.usado = 1
            session.commit()

        return (item.conteudo, item.bin, item.banco, titular, cpf_enc)
    except Exception as e:
        LOG.error(f"Erro em obter_dados_venda_gg: {e}")
        return None
    finally:
        session.close()


# --- Funções Admin ---
def adicionar_estoque(categoria, conteudo, bin_v=None, banco=None):
    session = SessionLocal()
    try:
        item = Estoque(categoria=categoria, conteudo=conteudo, bin=bin_v, banco=banco, vendido=0)
        session.add(item)
        session.commit()
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em adicionar_estoque: {e}")
    finally:
        session.close()


def adicionar_dados_gg(nome, cpf_encrypted):
    session = SessionLocal()
    try:
        dado = DadosGG(nome=nome, cpf_encrypted=cpf_encrypted, usado=0)
        session.add(dado)
        session.commit()
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em adicionar_dados_gg: {e}")
    finally:
        session.close()


def obter_dados_relatorio():
    session = SessionLocal()
    try:
        from sqlalchemy import func
        total_vendas = session.query(Venda).count()
        faturamento = session.query(func.sum(Venda.valor)).scalar() or 0.0
        clientes = session.query(Usuario).count()
        return total_vendas, faturamento, clientes
    except Exception as e:
        LOG.error(f"Erro em obter_dados_relatorio: {e}")
        return 0, 0.0, 0
    finally:
        session.close()


def resgatar_gift(codigo, user_id):
    session = SessionLocal()
    try:
        gift = session.query(GiftCard).filter_by(codigo=codigo, usado=0).first()
        if not gift:
            return None
        
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        if not user:
            return None

        user.saldo += gift.valor
        gift.usado = 1
        session.commit()
        return gift.valor
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em resgatar_gift: {e}")
        return None
    finally:
        session.close()
