CREATE DATABASE IF NOT EXISTS if0_42835117_banco;
USE if0_42835117_banco;

-- Tabela de Administradores
CREATE TABLE IF NOT EXISTS administradores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    senha VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Inserir admin padrão (usuário: admin | senha: 123)
INSERT INTO administradores (id, usuario, senha) VALUES
(1, 'admin', '123')
ON DUPLICATE KEY UPDATE usuario=usuario;

-- Tabela de Produtos / Itens
CREATE TABLE IF NOT EXISTS produtos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    descricao TEXT,
    preco DECIMAL(10,2) NOT NULL,
    imagem VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
