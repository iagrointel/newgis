-- Item L4-07-fluxo-de-potencia: fluxo de potência do alimentador como serviço da plataforma.
-- depende: 20260908T1049_rede_curto_circuito.sql
--
-- Duas tabelas, porque são duas coisas com ciclos de vida diferentes:
--
--   `rede_fluxo_execucao`   — UMA linha por análise de um alimentador. Guarda os PARÂMETROS que a
--                             produziram (modo, fator de carga, modelo de carga ZIP, geração distribuída,
--                             tensão da fonte, corrente nominal de referência do trecho), a VERSÃO DA
--                             TOPOLOGIA sobre a qual o modelo foi montado (`topologia_versao`, o instante
--                             em que a topologia derivada foi construída) e o ESTADO DE CONVERGÊNCIA
--                             (`convergiu`, `pontos`, `pontos_sem_convergencia`, `avisos`). A coluna
--                             `convergiu` é NOT NULL de propósito: não existe execução gravada sem o
--                             estado de convergência ao lado, e é ele que a tela usa para a tarja e que a
--                             agregação usa para EXCLUIR o alimentador que não fechou.
--
--   `rede_fluxo_resultado`  — o resultado POR ELEMENTO, uma linha por (execução, tipo, elemento[, fase]).
--                             Três tipos no mesmo lugar, porque são o mesmo fato — o estado elétrico de um
--                             elemento no ponto analisado — e a camada do mapa lê os três da mesma tabela:
--                               `barra`  — tensão em por unidade, uma linha por fase (`fase` = 1, 2 ou 3);
--                               `trecho` — corrente, carregamento sobre a corrente nominal DECLARADA e
--                                          perda no segmento;
--                               `trafo`  — carregamento sobre a potência nominal do arquivo, perda total e
--                                          perda de ferro (que é o que fecha a conferência contra
--                                          PER_FER x horas do ano).
--                             A geometria NÃO é copiada: `no_id` (barra) e `feicao_id` (trecho e
--                             transformador) apontam para a topologia e para a camada editável, e a camada
--                             do mapa lê a geometria na hora. Copiar geometria criaria uma segunda verdade
--                             que envelhece sozinha.
--
-- POR QUE NÃO HÁ UMA LINHA POR PONTO DA CURVA. A varredura anual tem 864 pontos (24 h x 3 tipos de dia x
-- 12 meses). Guardar cada elemento em cada ponto daria, num alimentador de 5 mil barras, mais de 4 milhões
-- de linhas por alimentador, e a máquina está com o disco cheio (D21). O que fica gravado é: o percurso
-- inteiro dos 864 pontos em GRANDEZAS DE CIRCUITO (convergência ponto a ponto, perda, tensão extrema,
-- carga) no resumo da execução, e o estado POR ELEMENTO no ponto de maior carga do ano — o ponto crítico,
-- que é onde a tensão é mínima e o carregamento máximo. O ponto está identificado em `ponto_critico`.
--
-- Análise NOVA do mesmo alimentador APAGA a anterior (uma execução viva por subrede), como no curto: o
-- resultado é derivado e refazê-lo custa segundos. A trilha de auditoria fica no `evento`, append-only.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.rede_fluxo_execucao (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  rede_id          uuid NOT NULL,
  subrede_id       uuid NOT NULL,
  subrede_nome     text NOT NULL CHECK (btrim(subrede_nome) <> '' AND length(subrede_nome) <= 200),
  -- a hipótese do cálculo, campo a campo (ver o cabeçalho de app/rede_utilidades/fluxo_potencia.py)
  parametros       jsonb NOT NULL CHECK (jsonb_typeof(parametros) = 'object'),
  -- instante em que a topologia derivada usada pelo modelo foi construída; nulo só se a rede não guardar
  topologia_versao timestamptz,
  -- estado de convergência: nunca opcional, nunca separado do resultado
  convergiu        boolean NOT NULL,
  pontos           int NOT NULL DEFAULT 0 CHECK (pontos >= 0),
  pontos_sem_convergencia int NOT NULL DEFAULT 0 CHECK (pontos_sem_convergencia >= 0),
  ponto_critico    jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(ponto_critico) = 'object'),
  energia          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(energia) = 'object'),
  resumo           jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(resumo) = 'object'),
  avisos           jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(avisos) = 'array'),
  elementos        int NOT NULL DEFAULT 0 CHECK (elementos >= 0),
  duracao_ms       int NOT NULL DEFAULT 0 CHECK (duracao_ms >= 0),
  pico_ram_mb      int CHECK (pico_ram_mb IS NULL OR pico_ram_mb >= 0),
  onde_rodou       text NOT NULL DEFAULT 'local' CHECK (onde_rodou IN ('local', 'gpu')),
  calculado_em     timestamptz NOT NULL DEFAULT now(),
  CHECK (pontos_sem_convergencia <= pontos),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, subrede_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_fluxo_execucao_rede ON plat.rede_fluxo_execucao (rede_id, subrede_nome);
CREATE INDEX IF NOT EXISTS ix_rede_fluxo_execucao_tenant ON plat.rede_fluxo_execucao (tenant_id);
ALTER TABLE plat.rede_fluxo_execucao DROP CONSTRAINT IF EXISTS rede_fluxo_execucao_tenant_rede_fkey;
ALTER TABLE plat.rede_fluxo_execucao ADD CONSTRAINT rede_fluxo_execucao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_fluxo_execucao DROP CONSTRAINT IF EXISTS rede_fluxo_execucao_tenant_subrede_fkey;
ALTER TABLE plat.rede_fluxo_execucao ADD CONSTRAINT rede_fluxo_execucao_tenant_subrede_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS plat.rede_fluxo_resultado (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  execucao_id    uuid NOT NULL,
  tipo           text NOT NULL CHECK (tipo IN ('barra', 'trecho', 'trafo')),
  -- nome do elemento no circuito exportado (barra `b<uuid do nó>`, `t<n>` do trecho, `x<n>` do trafo)
  elemento       text NOT NULL CHECK (btrim(elemento) <> '' AND length(elemento) <= 64),
  -- fase só existe na barra (1, 2, 3); no trecho e no transformador é nula
  fase           smallint CHECK (fase IS NULL OR fase IN (1, 2, 3)),
  -- código do elemento no cadastro do inquilino (COD_ID da BDGD), quando o arquivo o traz
  codigo         text CHECK (codigo IS NULL OR length(codigo) <= 200),
  no_id          uuid,
  feicao_id      uuid,
  kv             double precision CHECK (kv IS NULL OR kv > 0),
  -- NULO significa "não calculado" (elemento fora da parte energizada). Nunca zero: zero seria medida.
  tensao_pu      double precision CHECK (tensao_pu IS NULL OR tensao_pu >= 0),
  corrente_a     double precision CHECK (corrente_a IS NULL OR corrente_a >= 0),
  carregamento_pc double precision CHECK (carregamento_pc IS NULL OR carregamento_pc >= 0),
  perda_kw       double precision,
  perda_ferro_kw double precision,
  potencia_kva   double precision,
  UNIQUE (tenant_id, id),
  UNIQUE (execucao_id, tipo, elemento, fase)
);
CREATE INDEX IF NOT EXISTS ix_rede_fluxo_resultado_exec ON plat.rede_fluxo_resultado (execucao_id, tipo);
CREATE INDEX IF NOT EXISTS ix_rede_fluxo_resultado_tenant ON plat.rede_fluxo_resultado (tenant_id);
ALTER TABLE plat.rede_fluxo_resultado DROP CONSTRAINT IF EXISTS rede_fluxo_resultado_tenant_exec_fkey;
ALTER TABLE plat.rede_fluxo_resultado ADD CONSTRAINT rede_fluxo_resultado_tenant_exec_fkey
  FOREIGN KEY (tenant_id, execucao_id) REFERENCES plat.rede_fluxo_execucao (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260908T1049.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_fluxo_execucao', 'rede_fluxo_resultado'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/fluxo_potencia', 'fluxo de potência calculado num alimentador (parâmetros, convergência, ponto crítico)')
ON CONFLICT (nome) DO NOTHING;
