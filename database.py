"""
Módulo de Banco de Dados - JenneStoreBot
"""
import os
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, func, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import config

LOG = logging.getLogger("JenneDatabase")

DATABASE_URL = os.getenv("DATABASE_URL", getattr(config, "DATABASE_URL", ""))
if not DATABASE_URL:
    LOG.error("DATABASE_URL não configurada!")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Usuario(Base):
    __tablename__ = 'usuarios'
    user_id = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=True)
    username = Column(String(100), nullable=True)
    saldo = Column(Float, default=0.0)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=True)


class EstoqueGeral(Base):
    __tablename__ = 'estoque_geral'
    id = Column(Integer, primary_key=True, autoincrement=True)
    categoria = Column(String(50))
    sub_tipo = Column(String(100), nullable=True)
    conteudo = Column(Text)
    bin = Column(String(20), nullable=True)
    banco = Column(String(100), nullable=True)
    vendido = Column(Integer, default=0)


class DadosTitularGG(Base):
    __tablename__ = 'dados_titular_gg'
    id = Column(Integer, primary_key=True, autoincrement=True)
    dado = Column(Text)
    usado = Column(Integer, default=0)


class Venda(Base):
    __tablename__ = 'vendas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer)
    categoria = Column(String(50))
    valor = Column(Float)
    detalhes_entrega = Column(Text)
    data = Column(DateTime, default=datetime.utcnow)


class GiftCard(Base):
    __tablename__ = 'gift_cards'
    codigo = Column(String(100), primary_key=True)
    valor = Column(Float)
    usado = Column(Integer, default=0)


def criar_tabelas():
    try:
        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS criado_em TIMESTAMP;'))
            conn.commit()
        LOG.info("Tabelas verificadas/criadas com sucesso.")
    except Exception as e:
        LOG.error(f"Erro ao criar tabelas: {e}")


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


# FUNÇÃO CORRIGIDA COM O PARÂMETRO 'bin' ADICIONADO:
def adicionar_estoque_item(categoria, conteudo, sub_tipo=None, bin=None, banco=None):
    session = SessionLocal()
    try:
        item = EstoqueGeral(
            categoria=categoria,
            sub_tipo=sub_tipo,
            conteudo=conteudo,
            bin=bin,
            banco=banco,
            vendido=0
        )
        session.add(item)
        session.commit()
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em adicionar_estoque_item: {e}")
    finally:
        session.close()


def adicionar_dado_titular(dado):
    session = SessionLocal()
    try:
        item = DadosTitularGG(dado=dado, usado=0)
        session.add(item)
        session.commit()
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em adicionar_dado_titular: {e}")
    finally:
        session.close()


def listar_estoque_gg_agrupado():
    session = SessionLocal()
    try:
        results = (
            session.query(EstoqueGeral.bin, EstoqueGeral.banco, func.count(EstoqueGeral.id))
            .filter_by(categoria='gg', vendido=0)
            .group_by(EstoqueGeral.bin, EstoqueGeral.banco)
            .all()
        )
        return results
    except Exception as e:
        LOG.error(f"Erro em listar_estoque_gg_agrupado: {e}")
        return []
    finally:
        session.close()


def contar_estoque(categoria, sub_tipo=None):
    session = SessionLocal()
    try:
        query = session.query(EstoqueGeral).filter_by(categoria=categoria, vendido=0)
        if sub_tipo:
            query = query.filter_by(sub_tipo=sub_tipo)
        return query.count()
    except Exception as e:
        LOG.error(f"Erro em contar_estoque: {e}")
        return 0
    finally:
        session.close()


def realizar_compra_item(user_id, categoria, preco, sub_tipo=None, bin_v=None):
    session = SessionLocal()
    try:
        user = session.query(Usuario).filter_by(user_id=user_id).first()
        if not user or user.saldo < preco:
            return "saldo_insuficiente", None

        query = session.query(EstoqueGeral).filter_by(categoria=categoria, vendido=0)
        if sub_tipo:
            query = query.filter_by(sub_tipo=sub_tipo)
        if bin_v:
            query = query.filter_by(bin=bin_v)

        item = query.first()
        if not item:
            return "sem_estoque", None

        user.saldo -= preco
        item.vendido = 1
        conteudo_final = item.conteudo

        if categoria == 'gg':
            dado_titular = session.query(DadosTitularGG).filter_by(usado=0).first()
            if dado_titular:
                dado_titular.usado = 1
                conteudo_final += f"\n\n📋 **Dados do Titular:**\n{dado_titular.dado}"
            else:
                conteudo_final += f"\n\n📋 **Dados do Titular:** Não disponível no momento."

        venda = Venda(user_id=user_id, categoria=categoria, valor=preco, detalhes_entrega=conteudo_final)
        session.add(venda)
        session.commit()

        return "ok", conteudo_final
    except Exception as e:
        session.rollback()
        LOG.error(f"Erro em realizar_compra_item: {e}")
        return "erro_interno", None
    finally:
        session.close()


def obter_dados_relatorio():
    session = SessionLocal()
    try:
        total_vendas = session.query(Venda).count()
        faturamento = session.query(func.sum(Venda.valor)).scalar() or 0.0
        clientes = session.query(Usuario).count()
        return total_vendas, faturamento, clientes
    except Exception as e:
        LOG.error(f"Erro em obter_dados_relatorio: {e}")
        return 0, 0.0, 0
    finally:
        session.close()
