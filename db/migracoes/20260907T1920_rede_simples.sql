-- 20260907T1920_rede_simples: REDE SIMPLES (item L4-18-rede-simples-trace-network; ADR
-- docs/adr/20260907T1920-rede-simples.md). Equivalente de disciplina ao Trace Network da Esri: rede sem
-- pacote de ativos, sem regra de negócio e sem terminal de dispositivo — só junções e trechos, com direção
-- de fluxo declarada POR ATRIBUTO do trecho e atributos de rede escolhidos pelo inquilino.
-- depende: 20260906T1553_rede_pacote_de_ativos.sql
-- depende: 20260906T2000_rede_topologia_derivada.sql
--
-- Decisão que evita duplicar a linha L4 inteira: a rede simples NÃO ganha tabelas de feição próprias. Ela
-- reusa `plat.rede_feicao_ponto`/`rede_feicao_linha` e a topologia derivada de L4-01-b, e para isso recebe,
-- na criação, um CATÁLOGO MÍNIMO interno (1 domínio, 1 tier, 2 grupos, 2 tipos, 1 configuração de terminal
-- com um único terminal e nenhum caminho válido). Esse catálogo mínimo NÃO é um pacote de ativos: as colunas
-- `plat.rede.pacote_*` ficam NULAS enquanto o modo é 'simples', e `GET /api/rede/{id}/pacote` devolve 404.
-- É 'promover a rede de utilidades' (POST .../promover) que carimba o pacote mínimo — o mesmo documento,
-- agora validado pelo esquema do pacote, com sha256 e bytes — e muda o modo para 'utilidades'.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.rede ADD COLUMN IF NOT EXISTS modo text NOT NULL DEFAULT 'utilidades'
  CHECK (modo IN ('simples', 'utilidades'));

-- configuração da rede simples: de quais camadas do inquilino ela nasceu, qual atributo do trecho carrega a
-- direção de fluxo, como os valores desse atributo se traduzem para o vocabulário fechado
-- (digitalizada/contra/indeterminada) e quais atributos foram declarados como ATRIBUTOS DE REDE (os que o
-- traçado pode usar como custo ou filtro). Uma linha por rede simples; some junto com a rede (CASCADE).
CREATE TABLE IF NOT EXISTS plat.rede_simples (
  rede_id          uuid PRIMARY KEY,
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  camada_linha_id  uuid,
  camada_ponto_id  uuid,
  campo_direcao    text,
  mapa_direcao     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(mapa_direcao) = 'object'),
  atributos_rede   jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(atributos_rede) = 'array'),
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, rede_id)
);
CREATE INDEX IF NOT EXISTS ix_rede_simples_tenant ON plat.rede_simples (tenant_id);
ALTER TABLE plat.rede_simples ADD CONSTRAINT rede_simples_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

ALTER TABLE plat.rede_simples ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_rede_simples_ler ON plat.rede_simples;
CREATE POLICY p_rede_simples_ler ON plat.rede_simples FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_rede_simples_inserir ON plat.rede_simples;
CREATE POLICY p_rede_simples_inserir ON plat.rede_simples FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino());
DROP POLICY IF EXISTS p_rede_simples_alterar ON plat.rede_simples;
CREATE POLICY p_rede_simples_alterar ON plat.rede_simples FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_rede_simples_apagar ON plat.rede_simples;
CREATE POLICY p_rede_simples_apagar ON plat.rede_simples FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.rede_simples TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/simples_criar', 'rede simples criada a partir de camadas do inquilino (contagens, camadas de origem)'),
  ('redes/simples_promover', 'rede simples promovida a rede de utilidades (pacote mínimo carimbado)')
ON CONFLICT (nome) DO NOTHING;
