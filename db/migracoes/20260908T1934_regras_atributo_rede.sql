-- 20260908T1934_regras_atributo_rede: regras de atributo de rede (item L4-29-regras-de-atributo-de-rede).
-- Duas tabelas por inquilino com RLS: plat.rede_objeto (objeto genérico da rede — trecho, chave,
-- transformador, alimentador — com as colunas de rede que as funções de leitura expõem: nivel,
-- subrede, alimentador; os demais atributos ficam em jsonb) e plat.rede_regra (regra por perfil:
-- calculo preenche um atributo, restricao condiciona uma operação, validacao aponta problemas em
-- lote; a expressão usa a linguagem da plataforma, docs/EXPRESSAO.md, com as funções de rede de
-- L4-29). Nomes genéricos de propósito: o modelo detalhado por classe (trecho/trafo/uc) é outro
-- item (L4-20); estas tabelas são o modelo de regras, não o modelo de ativos. Idempotente.

-- ---------------------------------------------------------------- plat.rede_objeto
CREATE TABLE IF NOT EXISTS plat.rede_objeto (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  tipo         text NOT NULL CHECK (tipo <> ''),   -- vocabulário do inquilino: 'trecho', 'chave',
                                                   -- 'trafo', 'alimentador', ... (nada de pessoa)
  codigo       text NOT NULL CHECK (codigo <> ''),
  nivel        text,                               -- nível de tensão ('mt'/'bt'), quando se aplica
  subrede      text,                               -- nome da subrede (função Subrede())
  alimentador  text,                               -- código do alimentador (função Alimentador())
  atributos    jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(atributos) = 'object'),
  criado_em    timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, tipo, codigo)
);
CREATE INDEX IF NOT EXISTS ix_rede_objeto_tenant_tipo ON plat.rede_objeto (tenant_id, tipo);
CREATE INDEX IF NOT EXISTS ix_rede_objeto_tenant_alim ON plat.rede_objeto (tenant_id, tipo, alimentador)
  WHERE alimentador IS NOT NULL;

ALTER TABLE plat.rede_objeto ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_objeto ON plat.rede_objeto;
CREATE POLICY p_rede_objeto ON plat.rede_objeto FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- plat.rede_regra
CREATE TABLE IF NOT EXISTS plat.rede_regra (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  perfil        text NOT NULL CHECK (perfil IN ('calculo','restricao','validacao')),
  nome          text NOT NULL CHECK (nome <> ''),
  alvo_tipo     text NOT NULL CHECK (alvo_tipo <> ''),
  expressao     text NOT NULL CHECK (expressao <> ''),
  atributo_alvo text,  -- só perfil 'calculo': atributo de rede que a rodada preenche
  mensagem      text,  -- restricao/validacao: texto que a recusa/o item carrega
  prioridade    int NOT NULL DEFAULT 0,
  ativa         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, perfil, nome),
  -- cálculo preenche um atributo; restrição e validação não preenchem nada
  CHECK ((perfil = 'calculo') = (atributo_alvo IS NOT NULL))
);
-- (entrega 10/09) a fusão trouxe dois desenhos de plat.rede_regra; o CREATE acima foi ignorado por já
-- existir. A tabela passa a ser a união dos dois, aditivamente:
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS perfil text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS nome text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS alvo_tipo text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS expressao text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS atributo_alvo text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS mensagem text;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS prioridade int NOT NULL DEFAULT 0;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS ativa boolean NOT NULL DEFAULT true;
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS criado_em timestamptz NOT NULL DEFAULT now();
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS atualizado_em timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS ix_rede_regra_tenant ON plat.rede_regra (tenant_id, perfil, alvo_tipo) WHERE ativa;

ALTER TABLE plat.rede_regra ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_regra ON plat.rede_regra;
CREATE POLICY p_rede_regra ON plat.rede_regra FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- privilégio de leitura para o papel leitor
GRANT SELECT ON plat.rede_objeto, plat.rede_regra TO plat_leitor;
