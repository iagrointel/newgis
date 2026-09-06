-- 20260906T2108_acervo_remoto_fdw: camadas do acervo da casa que vivem nos OUTROS servidores
-- (item L6-01-j-multi-servidor; ADR docs/adr/20260906T2108-acervo-remoto-via-fdw.md; hipótese do item:
-- 412 tabelas do acervo vivem em mais de uma máquina e muitas só existem no segundo servidor ou no
-- terceiro — medido 06/09/2026 em acervo.objeto: vultr 1.546 objetos canônicos, hetzner 454, gpu 677).
--
-- Desenho (nunca copiar dado sem decisão — regra D21, disco a 98 %):
--   1. `plat.acervo_servidor`: REGISTRO dos servidores remotos da casa (host/porta/banco + nome do
--      papel de LEITURA remoto + `segredo_ref`, que é o NOME do arquivo de senha no diretório de
--      segredos da instalação — a senha nunca mora em tabela). Global, sem tenant: metadado do acervo
--      da casa, igual para todo inquilino (mesmo padrão de plat.acervo_camada, 027). Escrita só por
--      scripts como postgres (D16); a API só LÊ.
--   2. `plat.acervo_servidor_tabela`: candidatas declaradas manualmente (servidor, schema, tabela,
--      fonte_id) — complemento de `acervo.objeto` (que é a fonte primária de candidatas, origem
--      'registro_acervo'): tabela remota que ainda não entrou no registro da casa pode ser espelhada
--      por declaração explícita, e é assim que a base de teste monta a fixture sem poluir acervo.objeto.
--   3. `plat.acervo_camada` ganha `modo_acesso` ('local' = tabela neste servidor, padrão das 027+;
--      'fdw' = espelho postgres_fdw só-leitura ativo; 'indisponivel' = o servidor remoto não respondeu
--      na última verificação), `fdw_tabela` (nome qualificado da foreign table no schema espelho),
--      `aviso` (texto da indisponibilidade — a camada NUNCA some e NUNCA vira "0 feições" por falha de
--      rede: `linhas_exatas` conserva a última contagem conhecida e o aviso explica o estado),
--      `fdw_verificado_em` e `fdw_latencia_ms` (tempo medido da leitura via FDW — o portão pede tempo
--      medido, número nunca digitado).
--   4. `plat.acervo_fdw_execucao`: registro de cada rodada do sincronizador (mesmo padrão de
--      plat.acervo_camada_execucao, 027).
--
-- `CREATE EXTENSION postgres_fdw` é por BANCO, não por schema (não aceita SCHEMA nem é afetado pela
-- reescrita de trilha); IF NOT EXISTS torna idempotente. A extensão já existe na base da casa
-- (verificado 06/09/2026), mas a migração não depende disso.
--
-- Carimbo 20260906T2108 (ADR 0014). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- ---------------------------------------------------------------- servidores remotos da casa
CREATE TABLE IF NOT EXISTS plat.acervo_servidor (
  servidor      text PRIMARY KEY,                  -- casa com acervo.objeto.servidor ('gpu', 'hetzner', ...)
  host          text NOT NULL CHECK (btrim(host) <> '' AND length(host) <= 253),
  porta         int NOT NULL DEFAULT 5432 CHECK (porta BETWEEN 1 AND 65535),
  banco         text NOT NULL CHECK (btrim(banco) <> '' AND length(banco) <= 63),
  fdw_usuario   text NOT NULL CHECK (btrim(fdw_usuario) <> '' AND length(fdw_usuario) <= 63),
  segredo_ref   text NOT NULL CHECK (btrim(segredo_ref) <> '' AND length(segredo_ref) <= 200
                                   AND segredo_ref NOT LIKE '%/%' AND segredo_ref NOT LIKE '..%'),
  ativo         boolean NOT NULL DEFAULT true,
  notas         text,
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
-- segredo_ref é SÓ o nome do arquivo dentro do diretório de segredos da instalação
-- (/etc/plat/segredos por padrão, PLAT_FDW_SEGREDOS_DIR em teste): sem '/' e sem '..' é o que impede
-- que uma linha aponte para fora do cofre. O conteúdo do arquivo é a senha do papel de leitura e ele
-- nunca é gravado aqui.

-- ---------------------------------------------------------------- candidatas declaradas manualmente
CREATE TABLE IF NOT EXISTS plat.acervo_servidor_tabela (
  servidor    text NOT NULL REFERENCES plat.acervo_servidor(servidor) ON DELETE CASCADE,
  schema_nome text NOT NULL CHECK (btrim(schema_nome) <> '' AND length(schema_nome) <= 63),
  tabela      text NOT NULL CHECK (btrim(tabela) <> '' AND length(tabela) <= 63),
  fonte_id    text NOT NULL CHECK (btrim(fonte_id) <> ''),
  registrado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (servidor, schema_nome, tabela)
);

-- ---------------------------------------------------------------- acervo_camada: acesso remoto
ALTER TABLE plat.acervo_camada
  ADD COLUMN IF NOT EXISTS modo_acesso text NOT NULL DEFAULT 'local';
ALTER TABLE plat.acervo_camada
  ADD COLUMN IF NOT EXISTS fdw_tabela text;
ALTER TABLE plat.acervo_camada
  ADD COLUMN IF NOT EXISTS aviso text;
ALTER TABLE plat.acervo_camada
  ADD COLUMN IF NOT EXISTS fdw_verificado_em timestamptz;
ALTER TABLE plat.acervo_camada
  ADD COLUMN IF NOT EXISTS fdw_latencia_ms int;
-- CHECK em DO-block para ser idempotente (ADD CONSTRAINT não tem IF NOT EXISTS); o filtro por
-- connamespace impede que uma constraint homônima de OUTRO schema (outra trilha, nesta mesma base)
-- faça esta migração pular a criação no SEU schema:
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ck_acervo_camada_modo_acesso' AND connamespace = 'plat'::regnamespace
  ) THEN
    ALTER TABLE plat.acervo_camada
      ADD CONSTRAINT ck_acervo_camada_modo_acesso
      CHECK (modo_acesso IN ('local', 'fdw', 'indisponivel'));
  END IF;
END $$;

-- ---------------------------------------------------------------- execuções do sincronizador FDW
CREATE TABLE IF NOT EXISTS plat.acervo_fdw_execucao (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  iniciado_em     timestamptz NOT NULL,
  concluido_em    timestamptz NOT NULL,
  duracao_ms      int NOT NULL,
  servidores_ok   int NOT NULL,
  servidores_fora int NOT NULL,
  tabelas_fdw     int NOT NULL,
  indisponiveis   int NOT NULL
);

-- só leitura para a aplicação (mesmo padrão de plat.acervo_camada em 027): quem escreve é
-- scripts/acervo_fdw_sync.py, como postgres.
GRANT SELECT ON plat.acervo_servidor, plat.acervo_servidor_tabela, plat.acervo_fdw_execucao TO plat_app;
REVOKE INSERT, UPDATE, DELETE ON plat.acervo_servidor, plat.acervo_servidor_tabela, plat.acervo_fdw_execucao
  FROM plat_app;
