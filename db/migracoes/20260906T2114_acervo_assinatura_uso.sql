-- 20260906T2114_acervo_assinatura_uso: assinatura com aceite GRAVADO da licença, registro de leitura por
-- camada e vocabulário do evento de exportação (item L6-01-e-assinatura-e-uso).
-- depende: 20260906T15521aa_acervo_publicacao.sql
-- (item L6-01-b, dono de plat.acervo_assinatura; usa também plat.acervo_licenca de 043_acervo_licenca.sql,
-- item L6-01-g — os dois já vêm antes na ordem lexicográfica dos carimbos).
--
-- O que este arquivo cria:
--   1. as colunas de aceite em plat.acervo_assinatura (licenca_tipo, licenca_texto, licenca_url,
--      licenca_sha256): toda assinatura nova grava QUEM, QUANDO (já existiam assinado_por/assinado_em) e O
--      TEXTO da licença que estava na tela na hora do clique, byte a byte, com o sha256 que o chamador
--      confirmou. O texto não é referência: é CÓPIA — se a licença da fonte mudar depois, o que vale para
--      aquela assinatura é o que ficou gravado aqui.
--   2. plat.acervo_uso: registro de leitura por camada e por dia (consultas e feições servidas), escrito
--      pelas rotas de leitura no MESMO contexto de inquilino da leitura; RLS por inquilino, sem DELETE —
--      o registro de uso não se apaga pela API (limpeza de inquilino é CASCADE no tenant).
--   3. o tipo de evento 'acervo/exportar' (plat.evento.tipo tem FK para plat.evento_tipo).
--
-- Linhas antigas de acervo_assinatura (criadas pelo item L6-01-b antes deste item existir) não têm texto
-- gravado. Em vez de inventar um texto para elas, recebem o rótulo honesto 'aceite-anterior-a-L6-01-e' em
-- licenca_tipo e a frase que confessa a ausência em licenca_texto — na prática só existem em bases de
-- teste da trilha t601b, mas o UPDATE é barato e deixa a base consistente para o NOT NULL.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- 1. aceite gravado na assinatura ----------------------------------------------------------
ALTER TABLE plat.acervo_assinatura ADD COLUMN IF NOT EXISTS licenca_tipo   text;
ALTER TABLE plat.acervo_assinatura ADD COLUMN IF NOT EXISTS licenca_texto  text;
ALTER TABLE plat.acervo_assinatura ADD COLUMN IF NOT EXISTS licenca_url    text;
ALTER TABLE plat.acervo_assinatura ADD COLUMN IF NOT EXISTS licenca_sha256 text;

UPDATE plat.acervo_assinatura
   SET licenca_tipo   = 'aceite-anterior-a-L6-01-e',
       licenca_texto  = 'assinatura criada antes do item L6-01-e: o texto da licença não era gravado à época',
       licenca_url    = '',
       licenca_sha256 = ''
 WHERE licenca_tipo IS NULL;

ALTER TABLE plat.acervo_assinatura ALTER COLUMN licenca_tipo   SET NOT NULL;
ALTER TABLE plat.acervo_assinatura ALTER COLUMN licenca_texto  SET NOT NULL;
ALTER TABLE plat.acervo_assinatura ALTER COLUMN licenca_url    SET NOT NULL;
ALTER TABLE plat.acervo_assinatura ALTER COLUMN licenca_sha256 SET NOT NULL;

-- sem CHECK extra de formato: o conteúdo é montado pelo servidor (app/acervo/licenca.py), nunca digitado
-- pelo chamador; o NOT NULL já impede assinatura direta por SQL sem texto.

-- 2. registro de leitura por camada e dia ---------------------------------------------------
CREATE TABLE IF NOT EXISTS plat.acervo_uso (
  tenant_id        int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  acervo_camada_id text NOT NULL REFERENCES plat.acervo_camada(acervo_camada_id) ON DELETE CASCADE,
  dia              date NOT NULL,
  consultas        int  NOT NULL DEFAULT 0,   -- quantas leituras (feições, tile, exportação) no dia
  feicoes          bigint NOT NULL DEFAULT 0, -- quantas feições saíram pela porta no dia
  PRIMARY KEY (tenant_id, acervo_camada_id, dia)
);
CREATE INDEX IF NOT EXISTS ix_acervo_uso_dia ON plat.acervo_uso (dia);

ALTER TABLE plat.acervo_uso ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_acervo_uso_ler ON plat.acervo_uso;
CREATE POLICY p_acervo_uso_ler ON plat.acervo_uso FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_acervo_uso_inserir ON plat.acervo_uso;
CREATE POLICY p_acervo_uso_inserir ON plat.acervo_uso FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_acervo_uso_atualizar ON plat.acervo_uso;
CREATE POLICY p_acervo_uso_atualizar ON plat.acervo_uso FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual())
  WITH CHECK (tenant_id = plat.tenant_atual());
-- sem policy de DELETE de propósito: uso registrado não se apaga pela API.
GRANT SELECT, INSERT, UPDATE ON plat.acervo_uso TO plat_app;
REVOKE DELETE ON plat.acervo_uso FROM plat_app;

COMMENT ON TABLE plat.acervo_uso IS
  'Registro de leitura das camadas do acervo por inquilino e dia (item L6-01-e): uma linha por '
  '(inquilino, camada, dia), consultas e feições servidas somadas por UPSERT nas rotas de leitura. '
  'Entrada do relatório mensal GET /api/acervo/uso/mensal, consumido pelo item L7-09.';

-- 3. vocabulário de evento ------------------------------------------------------------------
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('acervo/exportar', 'GET /api/acervo/camadas/{id}/exportar — pacote com os dados e LICENCA.txt')
ON CONFLICT (nome) DO NOTHING;
