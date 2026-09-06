-- 20260906T1640_multiescala: grades aninhadas do motor multicritério (item L3-19-multiescala, linha L3).
--
-- Hipótese do item: triagem regional numa grade MACRO (ex.: 1 km) e estudo fino numa grade MICRO (ex.: 100 m)
-- gerada SÓ dentro das regiões aprovadas no macro; camada de escala quilométrica não custa por célula de 100 m
-- (regra do motor de LT, `camadas.py` marca cada camada como micro ou macro); o resultado macro é a máscara de
-- estudo do micro.
--
-- Decisões de modelo (ADR 20260906T1640-grades-aninhadas-multiescala):
--  * CRS de trabalho = UTM SIRGAS 2000 da zona do centróide da área de estudo (decisão A7 de
--    laco/decomposicao/L3L6_CONCEITO.md), gravado em `escala_conjunto.srid_trabalho`. As duas grades do mesmo
--    conjunto compartilham origem e CRS: é isso que faz o aninhamento ser aritmético (sem teste geométrico).
--  * A resolução macro é múltiplo inteiro k da micro; a célula macro (col, lin) contém exatamente as micro
--    (col*k + dx, lin*k + dy), 0 <= dx,dy < k. Célula micro fora de região macro aprovada nunca é GERADA.
--  * Fator bruto e resultado são LINHAS por (execução, célula, fator), nunca coluna por fator (decisão A1/A2).
--  * `escala_fator.resolucao_fonte_m` é OBRIGATÓRIA: é a escala nativa declarada da fonte. O motor compara essa
--    escala com a resolução da grade e grava `escala_grosseira` em `escala_execucao_fator` — o cliente NUNCA
--    envia esse campo (é a refutação do item: fator de 1 km na grade de 100 m tem de sair marcado).
--  * `escala_bloco` é o valor do fator agregado na resolução NATIVA dele; é o recurso PARTILHADO deste item e
--    por isso a chave primária começa por `tenant_id` (dois inquilinos com o mesmo nome de fator e a mesma
--    área NÃO compartilham bloco) e a tabela está sob RLS como todas as outras.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres. Depende de PostGIS (public.geometry), já exigido pela
-- 011_catalogo e pela 045_geocodificador.

-- ------------------------------------------------------------------ área de estudo (conjunto de grades)
CREATE TABLE IF NOT EXISTS plat.escala_conjunto (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       int NOT NULL REFERENCES plat.tenant(id),
  nome            text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  srid_trabalho   int NOT NULL CHECK (srid_trabalho BETWEEN 31965 AND 31985),
  area            geometry(Polygon, 4326) NOT NULL,
  origem_x_m      double precision NOT NULL,   -- canto inferior-esquerdo da grade no CRS de trabalho
  origem_y_m      double precision NOT NULL,
  largura_m       double precision NOT NULL CHECK (largura_m > 0),
  altura_m        double precision NOT NULL CHECK (altura_m > 0),
  dono_id         int NOT NULL REFERENCES plat.usuario(id),
  criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_escala_conjunto_nome ON plat.escala_conjunto (tenant_id, lower(nome));

-- ------------------------------------------------------------------ grade (macro ou micro) de um conjunto
CREATE TABLE IF NOT EXISTS plat.escala_grade (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  conjunto_id        uuid NOT NULL REFERENCES plat.escala_conjunto(id) ON DELETE CASCADE,
  nivel              text NOT NULL CHECK (nivel IN ('macro', 'micro')),
  resolucao_m        numeric NOT NULL CHECK (resolucao_m > 0),
  grade_pai_id       uuid REFERENCES plat.escala_grade(id) ON DELETE CASCADE,
  fator_aninhamento  int CHECK (fator_aninhamento IS NULL OR fator_aninhamento >= 2),  -- k = res_pai / res
  colunas            int NOT NULL CHECK (colunas > 0),   -- nx da área inteira, no CRS de trabalho
  linhas             int NOT NULL CHECK (linhas > 0),
  celulas_possiveis  bigint NOT NULL CHECK (celulas_possiveis >= 0),  -- se a grade cobrisse tudo que o pai cobre
  celulas            bigint NOT NULL DEFAULT 0 CHECK (celulas >= 0),  -- as que existem de fato
  criado_em          timestamptz NOT NULL DEFAULT now(),
  CHECK ((nivel = 'macro') = (grade_pai_id IS NULL)),
  CHECK ((grade_pai_id IS NULL) = (fator_aninhamento IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_escala_grade_conjunto ON plat.escala_grade (tenant_id, conjunto_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_escala_grade_nivel ON plat.escala_grade (tenant_id, conjunto_id, nivel);

-- ------------------------------------------------------------------ célula
CREATE TABLE IF NOT EXISTS plat.escala_celula (
  id         bigserial PRIMARY KEY,
  tenant_id  int NOT NULL REFERENCES plat.tenant(id),
  grade_id   uuid NOT NULL REFERENCES plat.escala_grade(id) ON DELETE CASCADE,
  col        int NOT NULL,
  lin        int NOT NULL,
  centro_x_m double precision NOT NULL,
  centro_y_m double precision NOT NULL,
  geom       geometry(Polygon, 4326) NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_escala_celula ON plat.escala_celula (tenant_id, grade_id, col, lin);
CREATE INDEX IF NOT EXISTS ix_escala_celula_grade ON plat.escala_celula (grade_id);

-- ------------------------------------------------------------------ fator, com a escala nativa DECLARADA
CREATE TABLE IF NOT EXISTS plat.escala_fator (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  nome               text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  resolucao_fonte_m  numeric NOT NULL CHECK (resolucao_fonte_m > 0),  -- escala nativa: obrigatória, sem padrão
  papel              text NOT NULL CHECK (papel IN ('atrai', 'custo')),
  unidade            text NOT NULL DEFAULT '' CHECK (length(unidade) <= 40),
  fonte              text NOT NULL DEFAULT '' CHECK (length(fonte) <= 500),
  dono_id            int NOT NULL REFERENCES plat.usuario(id),
  criado_em          timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_escala_fator_nome ON plat.escala_fator (tenant_id, lower(nome));

-- observação bruta da fonte do fator (ponto + valor); o motor agrega isto em blocos na escala nativa
CREATE TABLE IF NOT EXISTS plat.escala_amostra (
  id         bigserial PRIMARY KEY,
  tenant_id  int NOT NULL REFERENCES plat.tenant(id),
  fator_id   uuid NOT NULL REFERENCES plat.escala_fator(id) ON DELETE CASCADE,
  geom       geometry(Point, 4326) NOT NULL,
  valor      double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_escala_amostra_fator ON plat.escala_amostra (tenant_id, fator_id);

-- valor do fator agregado no bloco da escala NATIVA dele. Recurso partilhado -> chave começa por tenant_id.
CREATE TABLE IF NOT EXISTS plat.escala_bloco (
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  fator_id     uuid NOT NULL REFERENCES plat.escala_fator(id) ON DELETE CASCADE,
  srid         int NOT NULL,
  resolucao_m  numeric NOT NULL CHECK (resolucao_m > 0),
  bloco_x      int NOT NULL,
  bloco_y      int NOT NULL,
  valor        double precision NOT NULL,
  amostras     int NOT NULL CHECK (amostras > 0),
  calculado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, fator_id, srid, resolucao_m, bloco_x, bloco_y)
);

-- ------------------------------------------------------------------ execução (macro, e a micro ligada a ela)
CREATE TABLE IF NOT EXISTS plat.escala_execucao (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  conjunto_id        uuid NOT NULL REFERENCES plat.escala_conjunto(id) ON DELETE CASCADE,
  grade_id           uuid NOT NULL REFERENCES plat.escala_grade(id) ON DELETE CASCADE,
  nivel              text NOT NULL CHECK (nivel IN ('macro', 'micro')),
  execucao_pai_id    uuid REFERENCES plat.escala_execucao(id) ON DELETE CASCADE,
  aprovacao_tipo     text NOT NULL CHECK (aprovacao_tipo IN ('limiar', 'top_pct')),
  aprovacao_valor    numeric NOT NULL CHECK (aprovacao_valor >= 0),
  celulas            bigint NOT NULL DEFAULT 0,
  celulas_possiveis  bigint NOT NULL DEFAULT 0,
  celulas_com_nota   bigint NOT NULL DEFAULT 0,
  celulas_aprovadas  bigint NOT NULL DEFAULT 0,
  duracao_ms         int NOT NULL DEFAULT 0,
  dono_id            int NOT NULL REFERENCES plat.usuario(id),
  criado_em          timestamptz NOT NULL DEFAULT now(),
  CHECK ((nivel = 'macro') = (execucao_pai_id IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_escala_execucao_conjunto ON plat.escala_execucao (tenant_id, conjunto_id);
CREATE INDEX IF NOT EXISTS ix_escala_execucao_pai ON plat.escala_execucao (execucao_pai_id);

-- o relatório por fator: peso, escala declarada da fonte, escala da grade e o veredito escala_grosseira
CREATE TABLE IF NOT EXISTS plat.escala_execucao_fator (
  execucao_id        uuid NOT NULL REFERENCES plat.escala_execucao(id) ON DELETE CASCADE,
  fator_id           uuid NOT NULL REFERENCES plat.escala_fator(id) ON DELETE CASCADE,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  peso               numeric NOT NULL CHECK (peso > 0),
  resolucao_fonte_m  numeric NOT NULL,
  resolucao_grade_m  numeric NOT NULL,
  razao_escala       numeric NOT NULL,          -- resolucao_fonte_m / resolucao_grade_m
  escala             text NOT NULL CHECK (escala IN ('propria', 'grosseira')),
  escala_grosseira   boolean NOT NULL,
  blocos_usados      int NOT NULL DEFAULT 0,    -- avaliações da fonte: por BLOCO, não por célula
  blocos_calculados  int NOT NULL DEFAULT 0,    -- os que esta execução teve de agregar (o resto veio do cache)
  celulas_com_dado   bigint NOT NULL DEFAULT 0,
  valor_min          double precision,
  valor_max          double precision,
  PRIMARY KEY (execucao_id, fator_id),
  CHECK (escala_grosseira = (escala = 'grosseira'))
);
CREATE INDEX IF NOT EXISTS ix_escala_execucao_fator_tenant ON plat.escala_execucao_fator (tenant_id);

-- fator bruto por célula (uma LINHA por execução × célula × fator)
CREATE TABLE IF NOT EXISTS plat.escala_fator_celula (
  execucao_id    uuid NOT NULL REFERENCES plat.escala_execucao(id) ON DELETE CASCADE,
  celula_id      bigint NOT NULL REFERENCES plat.escala_celula(id) ON DELETE CASCADE,
  fator_id       uuid NOT NULL REFERENCES plat.escala_fator(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  bloco_x        int NOT NULL,
  bloco_y        int NOT NULL,
  valor          double precision,
  favorabilidade double precision CHECK (favorabilidade IS NULL OR (favorabilidade >= 0 AND favorabilidade <= 100)),
  PRIMARY KEY (execucao_id, celula_id, fator_id)
);
CREATE INDEX IF NOT EXISTS ix_escala_fator_celula_tenant ON plat.escala_fator_celula (tenant_id);

CREATE TABLE IF NOT EXISTS plat.escala_resultado (
  execucao_id  uuid NOT NULL REFERENCES plat.escala_execucao(id) ON DELETE CASCADE,
  celula_id    bigint NOT NULL REFERENCES plat.escala_celula(id) ON DELETE CASCADE,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  nota         double precision CHECK (nota IS NULL OR (nota >= 0 AND nota <= 100)),
  cobertura    numeric NOT NULL DEFAULT 0,   -- fração do peso total com dado nesta célula
  aprovada     boolean NOT NULL DEFAULT false,
  PRIMARY KEY (execucao_id, celula_id)
);
CREATE INDEX IF NOT EXISTS ix_escala_resultado_tenant ON plat.escala_resultado (tenant_id);
CREATE INDEX IF NOT EXISTS ix_escala_resultado_aprovada ON plat.escala_resultado (execucao_id, aprovada);

-- ------------------------------------------------------------------ RLS por inquilino em TODAS as tabelas
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['escala_conjunto', 'escala_grade', 'escala_celula', 'escala_fator', 'escala_amostra',
                           'escala_bloco', 'escala_execucao', 'escala_execucao_fator', 'escala_fator_celula',
                           'escala_resultado'] LOOP
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

GRANT USAGE, SELECT ON SEQUENCE plat.escala_celula_id_seq TO plat_app;
GRANT USAGE, SELECT ON SEQUENCE plat.escala_amostra_id_seq TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('multiescala/conjunto', 'área de estudo multiescala criada (nome, CRS de trabalho, extensão)'),
  ('multiescala/fator', 'fator multiescala criado (nome, escala nativa declarada, papel)'),
  ('multiescala/amostras', 'amostras de fator carregadas (fator, quantidade)'),
  ('multiescala/macro', 'execução macro de triagem (grade, resolução, células, aprovadas)'),
  ('multiescala/micro', 'execução micro ligada à macro (grade, resolução, células, economia)')
ON CONFLICT (nome) DO NOTHING;
