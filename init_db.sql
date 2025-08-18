-- Criar o banco de dados
CREATE DATABASE IF NOT EXISTS sao_geraldo_db;
USE sao_geraldo_db;

-- Criar tabela de usuários
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,
    tipo VARCHAR(20) DEFAULT 'operador',
    ativo BOOLEAN DEFAULT TRUE,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tipo CHECK (tipo IN ('admin', 'operador', 'supervisor'))
);

-- Criar tabela de pedidos
CREATE TABLE IF NOT EXISTS pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero_pedido VARCHAR(20) NOT NULL UNIQUE,
    cliente VARCHAR(100) NOT NULL,
    tipo_servico VARCHAR(50) NOT NULL,
    descricao TEXT,
    status VARCHAR(20) DEFAULT 'Pendente',
    prioridade VARCHAR(10) DEFAULT 'Normal',
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_conclusao DATETIME,
    valor DECIMAL(10,2),
    observacoes TEXT,
    CONSTRAINT chk_status CHECK (status IN ('Pendente', 'Em Andamento', 'Concluído')),
    CONSTRAINT chk_prioridade CHECK (prioridade IN ('Normal', 'Média', 'Alta'))
);

-- Inserir usuário admin padrão (senha: admin123)
INSERT INTO usuarios (nome, email, senha, tipo) VALUES 
('Administrador', 'admin@saogeraldo.com', 'pbkdf2:sha256:260000$abc123$789def...', 'admin');

-- Criar índices para melhor performance
CREATE INDEX idx_pedidos_status ON pedidos(status);
CREATE INDEX idx_pedidos_cliente ON pedidos(cliente);
CREATE INDEX idx_pedidos_data_criacao ON pedidos(data_criacao);
