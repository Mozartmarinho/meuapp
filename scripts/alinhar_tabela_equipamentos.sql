-- Alinha a tabela equipamentos ao model Python.
-- Idempotente: só adiciona a coluna se ela ainda não existir.
-- Rode no banco meuappdb (MySQL Workbench ou mysql.exe).
-- Depois: UPDATE copia nome_equipamento → equipamento nos cadastros antigos.

USE meuappdb;

-- DESCRIBE equipamentos;

SET @db := DATABASE();

DROP PROCEDURE IF EXISTS meuapp_add_col_equipamentos;
DELIMITER $$
CREATE PROCEDURE meuapp_add_col_equipamentos(IN p_col VARCHAR(64), IN p_ddl VARCHAR(255))
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = @db
          AND LOWER(TABLE_NAME) = 'equipamentos'
          AND LOWER(COLUMN_NAME) = LOWER(p_col)
    ) THEN
        SET @sql := CONCAT('ALTER TABLE equipamentos ADD COLUMN `', p_col, '` ', p_ddl);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL meuapp_add_col_equipamentos('equipamento', 'VARCHAR(100) NULL DEFAULT ''''');
CALL meuapp_add_col_equipamentos('nome_equipamento', 'VARCHAR(100) NULL');
CALL meuapp_add_col_equipamentos('marca', 'VARCHAR(100) NULL');
CALL meuapp_add_col_equipamentos('modelo', 'VARCHAR(100) NULL');
CALL meuapp_add_col_equipamentos('numero_serie', 'VARCHAR(50) NULL');
CALL meuapp_add_col_equipamentos('patrimonio', 'VARCHAR(50) NULL');
CALL meuapp_add_col_equipamentos('localizacao', 'VARCHAR(100) NULL');
CALL meuapp_add_col_equipamentos('setor', 'VARCHAR(100) NULL');
CALL meuapp_add_col_equipamentos('local', 'VARCHAR(200) NULL');
CALL meuapp_add_col_equipamentos('ativo', 'TINYINT(1) NOT NULL DEFAULT 1');
CALL meuapp_add_col_equipamentos('data_compra', 'DATE NULL');
CALL meuapp_add_col_equipamentos('data_manutencao', 'DATE NULL');
CALL meuapp_add_col_equipamentos('data_criacao', 'DATETIME NULL');
CALL meuapp_add_col_equipamentos('atualizado_em', 'DATETIME NULL');
CALL meuapp_add_col_equipamentos('cliente_id', 'INT NULL');
CALL meuapp_add_col_equipamentos('tipo_recurso', 'VARCHAR(40) NULL DEFAULT ''Estação''');
CALL meuapp_add_col_equipamentos('grupo_id', 'INT NULL');
CALL meuapp_add_col_equipamentos('usuario_equipamento', 'VARCHAR(120) NULL');
CALL meuapp_add_col_equipamentos('ip', 'VARCHAR(45) NULL');
CALL meuapp_add_col_equipamentos('is_agente', 'TINYINT(1) NOT NULL DEFAULT 0');

DROP PROCEDURE IF EXISTS meuapp_add_col_equipamentos;

UPDATE equipamentos
   SET equipamento = nome_equipamento
 WHERE (equipamento IS NULL OR equipamento = '')
   AND nome_equipamento IS NOT NULL
   AND nome_equipamento != '';

UPDATE equipamentos
   SET nome_equipamento = equipamento
 WHERE (nome_equipamento IS NULL OR nome_equipamento = '')
   AND equipamento IS NOT NULL
   AND equipamento != '';
