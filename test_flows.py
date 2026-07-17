from __future__ import annotations
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
import database as db
from security_utils import CPFProtector


@pytest.fixture
def env(tmp_path: Path) -> tuple[Path, CPFProtector]:
    path = tmp_path / "bot.db"
    db.DB_PATH = str(path)
    db.criar_tabelas()
    return path, CPFProtector.from_string(Fernet.generate_key().decode())


def data(p: CPFProtector, name: str, cpf: str = "52998224725") -> tuple[str, str, str]:
    return name, p.encrypt(cpf), p.fingerprint(cpf)


def test_gg_then_data_and_only_complete_is_sellable(env):
    _, p = env
    gid, did = db.adicionar_gg_pendente("123456", "Banco A", "GG1", 1)
    assert did is None
    assert db.contar_estoque_categoria("gg") == 0
    name, cipher, fingerprint = data(p, "Ana")
    data_id, paired = db.adicionar_dados_pendentes(name, cipher, fingerprint, 1)
    assert paired == gid
    assert data_id > 0
    assert db.contar_estoque_categoria("gg") == 1


def test_data_then_gg_out_of_order(env):
    _, p = env
    name, cipher, fingerprint = data(p, "Bia")
    did, gid = db.adicionar_dados_pendentes(name, cipher, fingerprint, 1)
    assert gid is None
    assert db.obter_status_filas() == (0, 1, 0)
    stock, paired_data = db.adicionar_gg_pendente("654321", "Banco B", "GG2", 1)
    assert paired_data == did
    assert stock > 0
    assert db.obter_status_filas() == (0, 0, 1)


def test_fifo_exact_order(env):
    path, p = env
    g1, _ = db.adicionar_gg_pendente("111111", "A", "GG-A", 1)
    g2, _ = db.adicionar_gg_pendente("222222", "B", "GG-B", 1)
    for name in ("Primeiro", "Segundo"):
        n, c, f = data(p, name)
        db.adicionar_dados_pendentes(n, c, f, 1)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT estoque_id,nome FROM gg_dados ORDER BY id"
        ).fetchall()
    assert rows == [(g1, "Primeiro"), (g2, "Segundo")]


def test_atomic_sale_and_no_duplicate_delivery(env):
    _, p = env
    n, c, f = data(p, "Cliente")
    db.adicionar_dados_pendentes(n, c, f, 1)
    gid, _ = db.adicionar_gg_pendente("333333", "C", "GG-C", 1)
    result = db.concluir_compra_fatura("invoice-1", 9, "gg", 4, "333333", "C")
    assert result == ("ok", gid, "GG-C")
    assert db.obter_dados_gg_para_entrega(gid, 8) is None
    assert db.obter_dados_gg_para_entrega(gid, 9)["nome"] == "Cliente"
    assert db.concluir_compra_fatura("invoice-1", 9, "gg", 4)[0] == "ja_processado"


def test_concurrent_fifo_no_duplicate(env):
    path, p = env
    for i in range(8):
        db.adicionar_gg_pendente(f"44444{i}", "D", f"GG{i}", 1)

    def insert(i: int):
        n, c, f = data(p, f"N{i}")
        return db.adicionar_dados_pendentes(n, c, f, 1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(insert, range(8)))
    assert db.obter_status_filas() == (0, 0, 8)
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(DISTINCT estoque_id),COUNT(*) FROM gg_dados"
        ).fetchone() == (8, 8)


def test_deposit_bonus_brl_and_once(env):
    path, _ = env
    db.garantir_usuario(5)
    db.definir_promocao(100, 1)
    db.criar_deposito("dep", 5, 10)
    assert db.confirmar_deposito("dep", 5) == ("ok", 10, 10, 20)
    assert db.confirmar_deposito("dep", 5)[0] == "ja_processado"
    assert db.obter_saldo(5) == 20
    with sqlite3.connect(path) as conn:
        assert (
            "moeda=BRL"
            in conn.execute(
                "SELECT detalhes FROM auditoria WHERE evento='deposito_confirmado'"
            ).fetchone()[0]
        )


def test_original_migration_marks_legacy_gg_pending(tmp_path: Path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE estoque(id INTEGER PRIMARY KEY AUTOINCREMENT,categoria TEXT,conteudo TEXT,status TEXT DEFAULT 'disponivel');CREATE TABLE vendas(id INTEGER PRIMARY KEY AUTOINCREMENT,categoria TEXT,valor REAL,data TIMESTAMP DEFAULT CURRENT_TIMESTAMP);CREATE TABLE usuarios(user_id INTEGER PRIMARY KEY,saldo REAL DEFAULT 0);INSERT INTO estoque(categoria,conteudo) VALUES('chave','123456|LEGADO');"
        )
    db.DB_PATH = str(path)
    db.criar_tabelas()
    db.criar_tabelas()
    assert db.contar_estoque_categoria("gg") == 0
    assert db.obter_status_filas()[0] == 1


def test_currency_constants_and_crypto_payload(monkeypatch, env):
    import main

    assert main.PRECOS == {"gg": 4, "streaming": 12, "esim": 20}
    assert main.MIN_DEPOSITO == 10
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "ok": True,
                "result": {"invoice_id": 1, "bot_invoice_url": "https://pay"},
            }

    def fake_post(url, **kwargs):
        captured.update(kwargs["json"])
        return Response()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "CRYPTO_TOKEN", "x")
    assert main.invoice("Teste", main.PRECOS["gg"])
    assert captured["currency_type"] == "fiat"
    assert captured["fiat"] == "BRL"
    assert captured["amount"] == "4.00"
    assert "asset" not in captured
