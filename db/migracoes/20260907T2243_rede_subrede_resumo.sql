-- Item L4-04-c-sumarios-por-subrede: o sumário calculado de cada subrede, como TABELA.
-- depende: 20260907T2031_rede_controlador_de_subrede.sql
--
-- O item irmão L4-04-a gravava um resumo de traçado dentro de `plat.rede_subrede.resumo` (jsonb com
-- contagem de elementos e duração). Aquilo responde "a atualização rodou"; não responde "quantos
-- quilômetros, quantos clientes, quanta energia tem este alimentador". Este item cria a tabela do
-- SUMÁRIO — uma linha por subrede, com coluna para cada grandeza — porque é o que um painel liga:
-- painel lê tabela com coluna tipada, não jsonb livre (subnetworks-table.htm: a tabela de subredes é
-- um objeto de primeira classe, consultável).
--
-- Por que uma tabela nova e não mais colunas em `plat.rede_subrede`: o registro da subrede é
-- ciclo de vida (nome, tier, limpa/suja) e muda a cada edição; o sumário é dado calculado, refeito
-- inteiro a cada cálculo e descartável sem perder nada. Separar deixa apagar e recalcular sem tocar
-- no registro, e deixa o painel ler só o que é número.
--
-- `km_por_nivel`, `ucs_por_classe` e `dispositivos_por_categoria` ficam em jsonb porque a chave vem do
-- PACOTE de ativos (grupo, classe da unidade consumidora, categoria de rede) e muda de pacote para
-- pacote: coluna fixa aqui obrigaria migração a cada pacote novo. O total correspondente é coluna.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.rede_subrede_resumo (
  subrede_id       uuid PRIMARY KEY,
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  rede_id          uuid NOT NULL,
  tier_id          uuid NOT NULL,
  subrede_nome     text NOT NULL CHECK (btrim(subrede_nome) <> '' AND length(subrede_nome) <= 200),
  -- de onde saiu a filiação de cada elemento a esta subrede (o atributo do arquivo que carrega o nome
  -- da subrede naquele tier; ver o ADR 20260907T2243)
  atributo_de_subrede text NOT NULL CHECK (btrim(atributo_de_subrede) <> ''),
  elementos        int NOT NULL DEFAULT 0 CHECK (elementos >= 0),
  -- comprimento por nível de tensão: {grupo do pacote -> km}. Declarado = soma do comprimento que o
  -- arquivo declara em cada trecho; geometria = soma do comprimento geodésico da linha carregada.
  km_por_nivel     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(km_por_nivel) = 'object'),
  km_por_nivel_geometria jsonb NOT NULL DEFAULT '{}'::jsonb
                   CHECK (jsonb_typeof(km_por_nivel_geometria) = 'object'),
  km_declarado     double precision CHECK (km_declarado IS NULL OR km_declarado >= 0),
  km_geometria     double precision CHECK (km_geometria IS NULL OR km_geometria >= 0),
  divergencia_pct  double precision,
  trafos           int NOT NULL DEFAULT 0 CHECK (trafos >= 0),
  kva_instalado    double precision CHECK (kva_instalado IS NULL OR kva_instalado >= 0),
  ucs              int NOT NULL DEFAULT 0 CHECK (ucs >= 0),
  ucs_por_classe   jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(ucs_por_classe) = 'object'),
  energia_anual_kwh double precision CHECK (energia_anual_kwh IS NULL OR energia_anual_kwh >= 0),
  dispositivos_por_categoria jsonb NOT NULL DEFAULT '{}'::jsonb
                   CHECK (jsonb_typeof(dispositivos_por_categoria) = 'object'),
  gd_unidades      int NOT NULL DEFAULT 0 CHECK (gd_unidades >= 0),
  gd_potencia_kw   double precision CHECK (gd_potencia_kw IS NULL OR gd_potencia_kw >= 0),
  tronco_max_m     double precision CHECK (tronco_max_m IS NULL OR tronco_max_m >= 0),
  tronco_origem    text NOT NULL CHECK (tronco_origem IN ('topologia', 'sem_topologia', 'sem_controlador')),
  duracao_ms       int NOT NULL DEFAULT 0 CHECK (duracao_ms >= 0),
  calculado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, subrede_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_resumo_rede ON plat.rede_subrede_resumo (rede_id, subrede_nome);
CREATE INDEX IF NOT EXISTS ix_rede_subrede_resumo_tenant ON plat.rede_subrede_resumo (tenant_id);
ALTER TABLE plat.rede_subrede_resumo DROP CONSTRAINT IF EXISTS rede_subrede_resumo_tenant_subrede_fkey;
ALTER TABLE plat.rede_subrede_resumo ADD CONSTRAINT rede_subrede_resumo_tenant_subrede_fkey
  FOREIGN KEY (tenant_id, subrede_id) REFERENCES plat.rede_subrede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_subrede_resumo DROP CONSTRAINT IF EXISTS rede_subrede_resumo_tenant_rede_fkey;
ALTER TABLE plat.rede_subrede_resumo ADD CONSTRAINT rede_subrede_resumo_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;
ALTER TABLE plat.rede_subrede_resumo DROP CONSTRAINT IF EXISTS rede_subrede_resumo_tenant_tier_fkey;
ALTER TABLE plat.rede_subrede_resumo ADD CONSTRAINT rede_subrede_resumo_tenant_tier_fkey
  FOREIGN KEY (tenant_id, tier_id) REFERENCES plat.rede_tier (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260907T2031.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_subrede_resumo'] LOOP
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
  ('redes/subrede_resumo', 'sumário das subredes recalculado (quantas subredes, em que tier)')
ON CONFLICT (nome) DO NOTHING;
