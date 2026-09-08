-- 20260906T1553_rede_pacote_de_ativos: catálogo da REDE DE UTILIDADES (item L4-01-a-pacote-de-ativos; ADR 0019).
-- Primeiro item da linha L4. O esquema da rede é DADO: um pacote JSON versionado descreve redes de domínio,
-- tiers, grupos e tipos de ativo, categorias, atributos e configurações de terminal; estas tabelas são a
-- projeção normalizada desse pacote, e a exportação é reconstruída DELAS (nunca do arquivo recebido).
--
-- Tudo é dado do INQUILINO (tenant_id + RLS), como plat.conexao (030) e ao contrário do acervo (021/027), que
-- é registro global da casa. O pacote entra e sai inteiro: a importação substitui o catálogo daquela rede numa
-- só transação, por isso as chaves estrangeiras internas são ON DELETE CASCADE a partir de plat.rede.
--
-- Nomes de código (`codigo`) são o vocabulário do pacote e ficam únicos por rede; os identificadores internos
-- são uuid para que a exportação nunca dependa de sequência e o mesmo pacote possa ser reimportado em outro
-- inquilino sem colidir. Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.rede (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             int NOT NULL REFERENCES plat.tenant(id),
  nome                  text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  disciplina            text NOT NULL CHECK (disciplina IN ('eletrica','agua','gas','esgoto','telecom','estrutura')),
  descricao             text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  pacote_codigo         text,
  pacote_nome           text,
  pacote_descricao      text,
  pacote_versao         text,
  pacote_esquema_versao int,
  pacote_fonte          text,
  pacote_sha256         text,
  pacote_bytes          int,
  importado_em          timestamptz,
  importado_por         int REFERENCES plat.usuario(id),
  dono_id               int NOT NULL REFERENCES plat.usuario(id),
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rede_tenant ON plat.rede (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_nome ON plat.rede (tenant_id, lower(nome));

CREATE OR REPLACE FUNCTION plat.tg_rede_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS rede_atualizado_em ON plat.rede;
CREATE TRIGGER rede_atualizado_em BEFORE UPDATE ON plat.rede
  FOR EACH ROW EXECUTE FUNCTION plat.tg_rede_atualizado_em();

-- rede de domínio: elétrica de distribuição, água, gás, esgoto, telecom, e a rede de ESTRUTURA (o que sustenta)
CREATE TABLE IF NOT EXISTS plat.rede_dominio (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  rede_id     uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  codigo      text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome        text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  tipo        text NOT NULL CHECK (tipo IN ('dominio','estrutura')),
  disciplina  text NOT NULL CHECK (disciplina IN ('eletrica','agua','gas','esgoto','telecom','estrutura')),
  ordem       int NOT NULL CHECK (ordem BETWEEN 1 AND 999),
  descricao   text CHECK (descricao IS NULL OR length(descricao) <= 2000)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_dominio ON plat.rede_dominio (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_dominio_tenant ON plat.rede_dominio (tenant_id);

-- tier: nível dentro do domínio, com ORDEM e TIPO (hierárquico = há montante e jusante; particionado = não há)
CREATE TABLE IF NOT EXISTS plat.rede_tier (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  rede_id     uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  dominio_id  uuid NOT NULL REFERENCES plat.rede_dominio(id) ON DELETE CASCADE,
  codigo      text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome        text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  ordem       int NOT NULL CHECK (ordem BETWEEN 1 AND 999),
  tipo        text NOT NULL CHECK (tipo IN ('hierarquico','particionado')),
  descricao   text CHECK (descricao IS NULL OR length(descricao) <= 2000)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_tier ON plat.rede_tier (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_tier_tenant ON plat.rede_tier (tenant_id);

-- categoria de rede: papel do ativo no traçado (fonte, proteção, seccionamento, controlador, ...)
CREATE TABLE IF NOT EXISTS plat.rede_categoria (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  rede_id     uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  codigo      text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome        text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  descricao   text CHECK (descricao IS NULL OR length(descricao) <= 2000)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_categoria ON plat.rede_categoria (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_categoria_tenant ON plat.rede_categoria (tenant_id);

-- configuração de terminal: quantos terminais o ativo tem e por quais caminhos a energia (ou a água) passa
CREATE TABLE IF NOT EXISTS plat.rede_terminal_config (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  rede_id          uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  codigo           text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome             text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  terminais        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(terminais) = 'array'),
  caminhos_validos jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(caminhos_validos) = 'array')
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_terminal ON plat.rede_terminal_config (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_terminal_tenant ON plat.rede_terminal_config (tenant_id);

-- grupo de ativo: a classe de feição (o que vira uma camada), com a geometria e a camada de origem
CREATE TABLE IF NOT EXISTS plat.rede_grupo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  dominio_id     uuid NOT NULL REFERENCES plat.rede_dominio(id) ON DELETE CASCADE,
  codigo         text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome           text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  geometria      text NOT NULL CHECK (geometria IN ('ponto','linha','poligono','sem_geometria')),
  descricao      text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  camadas_fonte  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(camadas_fonte) = 'array')
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_grupo ON plat.rede_grupo (rede_id, codigo);
CREATE INDEX IF NOT EXISTS ix_rede_grupo_tenant ON plat.rede_grupo (tenant_id);

-- tipo de ativo: o SUBTIPO codificado dentro do grupo (código inteiro + chave estável), preso a um tier
CREATE TABLE IF NOT EXISTS plat.rede_tipo (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  rede_id        uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  grupo_id       uuid NOT NULL REFERENCES plat.rede_grupo(id) ON DELETE CASCADE,
  tier_id        uuid NOT NULL REFERENCES plat.rede_tier(id) ON DELETE CASCADE,
  terminal_id    uuid REFERENCES plat.rede_terminal_config(id) ON DELETE SET NULL,
  codigo         int NOT NULL CHECK (codigo BETWEEN 1 AND 32767),
  chave          text NOT NULL CHECK (chave ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome           text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  descricao      text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  codigos_fonte  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(codigos_fonte) = 'array')
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_tipo_codigo ON plat.rede_tipo (grupo_id, codigo);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_tipo_chave ON plat.rede_tipo (grupo_id, chave);
CREATE INDEX IF NOT EXISTS ix_rede_tipo_tenant ON plat.rede_tipo (tenant_id);

CREATE TABLE IF NOT EXISTS plat.rede_tipo_categoria (
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  rede_id       uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  tipo_id       uuid NOT NULL REFERENCES plat.rede_tipo(id) ON DELETE CASCADE,
  categoria_id  uuid NOT NULL REFERENCES plat.rede_categoria(id) ON DELETE CASCADE,
  PRIMARY KEY (tipo_id, categoria_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_tipo_categoria_tenant ON plat.rede_tipo_categoria (tenant_id);

-- atributo de rede: o campo do ativo, com a coluna de ORIGEM e se essa origem foi conferida em dado real
CREATE TABLE IF NOT EXISTS plat.rede_atributo (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  rede_id      uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  grupo_id     uuid NOT NULL REFERENCES plat.rede_grupo(id) ON DELETE CASCADE,
  tipo_id      uuid REFERENCES plat.rede_tipo(id) ON DELETE CASCADE,
  codigo       text NOT NULL CHECK (codigo ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
  nome         text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  tipo_dado    text NOT NULL CHECK (tipo_dado IN ('texto','inteiro','real','data','booleano','geometria')),
  unidade      text CHECK (unidade IS NULL OR length(unidade) <= 30),
  obrigatorio  boolean NOT NULL DEFAULT false,
  origem       jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_atributo
  ON plat.rede_atributo (grupo_id, coalesce(tipo_id, '00000000-0000-0000-0000-000000000000'::uuid), codigo);
CREATE INDEX IF NOT EXISTS ix_rede_atributo_tenant ON plat.rede_atributo (tenant_id);

-- regra: o que pode se ligar a quê (conectividade, fixação estrutural, contenção)
CREATE TABLE IF NOT EXISTS plat.rede_regra (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  rede_id      uuid NOT NULL REFERENCES plat.rede(id) ON DELETE CASCADE,
  tipo         text NOT NULL CHECK (tipo IN ('conectividade_no_trecho','conectividade_entre_nos',
                                             'fixacao_estrutural','contencao')),
  de_tipo_id   uuid NOT NULL REFERENCES plat.rede_tipo(id) ON DELETE CASCADE,
  para_tipo_id uuid NOT NULL REFERENCES plat.rede_tipo(id) ON DELETE CASCADE,
  descricao    text CHECK (descricao IS NULL OR length(descricao) <= 2000)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rede_regra ON plat.rede_regra (rede_id, tipo, de_tipo_id, para_tipo_id);
CREATE INDEX IF NOT EXISTS ix_rede_regra_tenant ON plat.rede_regra (tenant_id);

-- RLS: o mesmo padrão de plat.conexao (030). Leitura pelo inquilino; escrita exige `rede.editar` (privilégio já
-- semeado na migração 003, "editar rede de utilidades"), avaliado na aplicação; a política de linha garante que
-- nada de outro inquilino entra nem sai, mesmo com a rota errada.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede','rede_dominio','rede_tier','rede_categoria','rede_terminal_config',
                           'rede_grupo','rede_tipo','rede_tipo_categoria','rede_atributo','rede_regra'] LOOP
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
  ('redes/criar', 'rede de utilidades criada (nome, disciplina)'),
  ('redes/apagar', 'rede de utilidades apagada (nome)'),
  ('redes/importar_pacote', 'pacote de ativos importado (código, versão, sha256, contagens)')
ON CONFLICT (nome) DO NOTHING;
