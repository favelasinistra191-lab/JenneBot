# Implantação rápida

1. Pare o bot e faça backup de `bot_database.db`.
2. Extraia este ZIP na pasta do bot. Para preservar dados, copie o `bot_database.db` existente para a nova pasta antes da primeira execução.
3. Copie `.env.example` para `.env` e preencha os tokens no hospedador. O ZIP não contém tokens.
4. Gere a chave de CPF uma vez: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` e coloque o resultado em `CPF_ENCRYPTION_KEY`. Não perca essa chave.
5. Rode `chmod +x start.sh && ./start.sh`. Alternativa: `pip install -r requirements.txt`, exporte as variáveis do `.env` e rode `python3 main.py`.

## Comandos

- `/add gg`: cadastra somente BIN, banco e conteúdo da GG.
- `/add dados`: cadastra somente nome e CPF.
- `/add streaming LOGIN|SENHA|OBS`
- `/add_esim`
- `/promocao 100` (`0` desativa)
- `/filas`: GG aguardando, dados aguardando e pares prontos.
- `/ver_gg ID`: consulta administrativa auditada.

GG e dados entram em filas separadas e são pareados automaticamente por ordem FIFO. Somente pares completos aparecem ao cliente e podem ser vendidos.

## Moeda e cobrança

Preços e saldos são em BRL: GG R$ 4, streaming R$ 12, eSIM R$ 20 e depósito mínimo R$ 10. As faturas do Crypto Pay usam `currency_type=fiat` e `fiat=BRL`; o cliente pode liquidar com os criptoativos aceitos, mas o preço é denominado em reais. Referência oficial: https://help.send.tg/en/articles/10279948-crypto-pay-api

## Migração

A inicialização é idempotente e não destrutiva para o banco original e para a versão anterior. Categoria legada `chave` vira `gg`. GG legada sem nome/CPF passa a `aguardando_dados` e não é vendável até receber o próximo `/add dados` pelo FIFO. Pares já existentes são preservados. Faça backup antes da primeira execução.
