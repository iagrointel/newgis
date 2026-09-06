-- 027_acervo_camada: registro de camadas do acervo da casa (item L6-01-a-registro; ADR ver
-- laco/decomposicao/L3L6_CONCEITO.md B1/B2/B5). Diferença explícita do L6-01-a-procedencia-acervo (migração 021,
-- ENTREGUE): aquele é a FICHA de FONTE (`plat.acervo_ficha`, 376 linhas de metadado, sem geometria); este é o
-- REGISTRO de CAMADA — uma linha por TABELA canônica com geometria no servidor principal (medido 06/09/2026:
-- 475 candidatas via geometry_columns × acervo.objeto, 270 em `public`; o número muda a cada varredura da casa,
-- por isso nunca é digitado aqui, só medido de novo a cada `acervo_sync.py`).
--
-- Tabela GLOBAL (sem tenant_id): é o mesmo tipo de referência que `plat.acervo_ficha` — metadado do acervo da
-- casa, igual para todo inquilino; RLS por inquilino entra só no L6-01-b (view sobre a tabela ORIGINAL, essa
-- sim com predicado de assinatura). `acervo.*` continua sendo escrito só pelos scripts da casa
-- (registro.py/contagem2.py/frescor.py); esta tabela é escrita só por `scripts/acervo_sync.py`, que roda como
-- `postgres` (mesmo padrão de identidade de `db/migrar.sh`) — a API do plat (`plat_app`) só LÊ.
--
-- Numeração 027 (026 = jobs_manutencao_analyze). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.acervo_camada (
  acervo_camada_id   text PRIMARY KEY,                 -- slug '<fonte_id>/<schema>.<tabela>' (decisão B2)
  fonte_id           text NOT NULL,                     -- acervo.fonte é só-leitura; sem FK física entre schemas
  servidor           text NOT NULL,
  banco              text NOT NULL,
  schema_nome        text NOT NULL,
  tabela             text NOT NULL,
  coluna_geom        text NOT NULL,
  srid               int NOT NULL,
  tipo_geom          text NOT NULL,
  colunas_expostas   text[] NOT NULL DEFAULT '{}',      -- lista branca (coarse, nome-only; L6-01-f endurece por conteúdo)
  colunas_bloqueadas text[] NOT NULL DEFAULT '{}',       -- o que foi retirado da lista branca e por quê (auditoria)
  linhas_exatas      bigint,                             -- NULL = contagem não concluída em 25 s (nunca 0 por omissão)
  linhas_contadas_em date,
  linhas_estimadas   bigint,                             -- reltuples, só para comparar; nunca vai a documento
  sha256             text,                               -- da FONTE (acervo.fonte.sha256), quando existir
  comando_reexecucao text,
  estado             text NOT NULL CHECK (estado IN ('exposta', 'bloqueada', 'pendente_de_licenca')),
  motivo_bloqueio    text,
  sincronizado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_acervo_camada_fonte  ON plat.acervo_camada (fonte_id);
CREATE INDEX IF NOT EXISTS ix_acervo_camada_estado ON plat.acervo_camada (estado);

-- registro de execução do sincronizador (histórico + prova de que roda em ≤ 5 min)
CREATE TABLE IF NOT EXISTS plat.acervo_camada_execucao (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  iniciado_em     timestamptz NOT NULL,
  concluido_em    timestamptz NOT NULL,
  duracao_ms      int NOT NULL,
  candidatas      int NOT NULL,
  expostas        int NOT NULL,
  bloqueadas      int NOT NULL,
  pendentes       int NOT NULL,
  fantasmas       int NOT NULL,          -- estimativa > 0 e COUNT(*) = 0 (subconjunto de bloqueadas)
  nao_concluidas  int NOT NULL           -- COUNT(*) estourou o timeout de 25 s (subconjunto de bloqueadas)
);

-- só leitura para a aplicação: quem escreve é scripts/acervo_sync.py, como postgres (mesmo padrão de
-- plat.versao_migracao em 001_fundacao.sql)
GRANT SELECT ON plat.acervo_camada, plat.acervo_camada_execucao TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.acervo_camada, plat.acervo_camada_execucao FROM plat_app;
