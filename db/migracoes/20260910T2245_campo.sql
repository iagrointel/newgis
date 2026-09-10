-- 20260910T2245_campo (item L2-07-campo, 10/09/2026): módulo de CAMPO — a casa já opera fila de trabalho,
-- roteiro do dia e visita com foto dentro de um SIG de cliente (rs-coop/certaja/sig e o irmão edp_es/sig);
-- este é o mesmo módulo portado para a plataforma, com DUAS mudanças de desenho por causa do multi-inquilino:
--
--   1. no sistema de origem o ALVO é uma tabela própria (`alvo`, com atributos fixos do domínio elétrico:
--      cod_id, kva, absoluta, luz...). Aqui o alvo é uma FEIÇÃO DE CAMADA DO CATÁLOGO — `plat.campo_alvo`
--      não guarda atributo nenhum do objeto do mundo real, só a referência (camada_id, globalid) — a mesma
--      dupla que `GET /api/camadas/{id}/feicoes/{globalid}` (item L2-03-edicao) já usa para achar geometria e
--      atributos. Isso deixa a fila de trabalho genérica: qualquer camada vetorial hospedada do inquilino
--      (poste, imóvel, ponto de coleta) pode virar fila, não só um domínio fixo.
--   2. toda tabela leva `tenant_id` com RLS (padrão do resto da casa; o sistema de origem tinha 1 schema por
--      cooperativa, aqui é 1 banco para todos).
--
-- Sem BEGIN/COMMIT. Idempotente. Aplicada como postgres.

-- ---------------------------------------------------------------- fila de trabalho
CREATE TABLE IF NOT EXISTS plat.campo_fila (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  titulo        text NOT NULL CHECK (btrim(titulo) <> '' AND length(titulo) <= 250),
  camada_id     uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  status        text NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta', 'concluida', 'arquivada')),
  dono_id       int NOT NULL REFERENCES plat.usuario(id),
  criado_por    int REFERENCES plat.usuario(id),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_campo_fila_tenant ON plat.campo_fila (tenant_id);
CREATE INDEX IF NOT EXISTS ix_campo_fila_camada ON plat.campo_fila (camada_id);

-- alvo: 1 feição da camada da fila, com ordem de trabalho e nota; nunca duplica a feição na mesma fila
CREATE TABLE IF NOT EXISTS plat.campo_alvo (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  int NOT NULL REFERENCES plat.tenant(id),
  fila_id    uuid NOT NULL REFERENCES plat.campo_fila(id) ON DELETE CASCADE,
  globalid   uuid NOT NULL,
  ordem      int NOT NULL DEFAULT 0,
  nota       text CHECK (nota IS NULL OR length(nota) <= 2000),
  status     text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'visitado', 'pulado')),
  criado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (fila_id, globalid)
);
CREATE INDEX IF NOT EXISTS ix_campo_alvo_tenant ON plat.campo_alvo (tenant_id);
CREATE INDEX IF NOT EXISTS ix_campo_alvo_fila_ordem ON plat.campo_alvo (fila_id, ordem);

-- ---------------------------------------------------------------- roteiro (ordem de visita do dia + trajeto)
CREATE TABLE IF NOT EXISTS plat.campo_roteiro (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  fila_id      uuid NOT NULL REFERENCES plat.campo_fila(id) ON DELETE CASCADE,
  titulo       text CHECK (titulo IS NULL OR length(titulo) <= 250),
  origem_lon   double precision NOT NULL CHECK (origem_lon BETWEEN -180 AND 180),
  origem_lat   double precision NOT NULL CHECK (origem_lat BETWEEN -90 AND 90),
  motor        text NOT NULL CHECK (motor IN ('osrm', 'linha_reta')),
  distancia_m  double precision,
  duracao_s    double precision,
  geom         geometry(LineString, 4326),
  aviso        text,
  dono_id      int NOT NULL REFERENCES plat.usuario(id),
  criado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_campo_roteiro_tenant ON plat.campo_roteiro (tenant_id);
CREATE INDEX IF NOT EXISTS ix_campo_roteiro_fila ON plat.campo_roteiro (fila_id);

CREATE TABLE IF NOT EXISTS plat.campo_roteiro_parada (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  roteiro_id  uuid NOT NULL REFERENCES plat.campo_roteiro(id) ON DELETE CASCADE,
  alvo_id     uuid NOT NULL REFERENCES plat.campo_alvo(id) ON DELETE CASCADE,
  ordem       int NOT NULL,
  trecho_m    double precision,
  trecho_s    double precision,
  UNIQUE (roteiro_id, alvo_id)
);
CREATE INDEX IF NOT EXISTS ix_campo_roteiro_parada_tenant ON plat.campo_roteiro_parada (tenant_id);
CREATE INDEX IF NOT EXISTS ix_campo_roteiro_parada_roteiro ON plat.campo_roteiro_parada (roteiro_id, ordem);

-- ---------------------------------------------------------------- visita
-- `cliente_uuid` é a chave de idempotência: o navegador/PWA gera um uuid POR REGISTRO no momento da coleta
-- (antes de qualquer sincronização) e reenvia o MESMO valor se precisar tentar de novo — sincronizar duas
-- vezes cai no UNIQUE(tenant_id, cliente_uuid) e devolve a visita já gravada, nunca uma duplicata (portão
-- "refutacao" do item: "sincroniza duas vezes: sem duplicata"). `capturado_em` é o relógio do APARELHO
-- (mostrado na tela, nunca usado para ordenar/decidir no servidor); `recebido_em` é o relógio do SERVIDOR e é
-- a única hora que conta para fila/roteiro/relatório — um aparelho com o relógio errado (refutação: "muda
-- relógio") não SOME visita nem CRIA duplicata, só mostra uma data errada no campo que é dele.
CREATE TABLE IF NOT EXISTS plat.campo_visita (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  cliente_uuid   uuid NOT NULL,
  fila_id        uuid REFERENCES plat.campo_fila(id) ON DELETE SET NULL,
  alvo_id        uuid REFERENCES plat.campo_alvo(id) ON DELETE SET NULL,
  roteiro_id     uuid REFERENCES plat.campo_roteiro(id) ON DELETE SET NULL,
  camada_id      uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  globalid       uuid NOT NULL,
  status         text NOT NULL CHECK (status IN ('visitado', 'confirmado', 'nao_confirmado', 'inconclusivo')),
  texto          text CHECK (texto IS NULL OR length(texto) <= 8000),
  usuario_id     int NOT NULL REFERENCES plat.usuario(id),
  lat            double precision CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
  lon            double precision CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
  gps_acc_m      double precision,
  capturado_em   timestamptz NOT NULL,
  recebido_em    timestamptz NOT NULL DEFAULT now(),
  dados          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(dados) = 'object'),
  UNIQUE (tenant_id, cliente_uuid)
);
CREATE INDEX IF NOT EXISTS ix_campo_visita_tenant ON plat.campo_visita (tenant_id);
CREATE INDEX IF NOT EXISTS ix_campo_visita_alvo ON plat.campo_visita (alvo_id);
CREATE INDEX IF NOT EXISTS ix_campo_visita_globalid ON plat.campo_visita (camada_id, globalid);

CREATE TABLE IF NOT EXISTS plat.campo_visita_foto (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  visita_id     uuid NOT NULL REFERENCES plat.campo_visita(id) ON DELETE CASCADE,
  chave         text NOT NULL,
  sha256        text NOT NULL,
  bytes         int NOT NULL,
  largura       int,
  altura        int,
  criado_por    int REFERENCES plat.usuario(id),
  criado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (visita_id, sha256)
);
CREATE INDEX IF NOT EXISTS ix_campo_visita_foto_tenant ON plat.campo_visita_foto (tenant_id);
CREATE INDEX IF NOT EXISTS ix_campo_visita_foto_visita ON plat.campo_visita_foto (visita_id);

-- ---------------------------------------------------------------- gatilho: visita registrada marca o alvo
CREATE OR REPLACE FUNCTION plat.tg_campo_visita_marca_alvo() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.alvo_id IS NOT NULL THEN
    UPDATE plat.campo_alvo SET status = 'visitado' WHERE id = NEW.alvo_id AND status = 'pendente';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS tg_campo_visita_marca_alvo ON plat.campo_visita;
CREATE TRIGGER tg_campo_visita_marca_alvo AFTER INSERT ON plat.campo_visita
  FOR EACH ROW EXECUTE FUNCTION plat.tg_campo_visita_marca_alvo();

CREATE OR REPLACE FUNCTION plat.tg_campo_fila_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS tg_campo_fila_atualizado_em ON plat.campo_fila;
CREATE TRIGGER tg_campo_fila_atualizado_em BEFORE UPDATE ON plat.campo_fila
  FOR EACH ROW EXECUTE FUNCTION plat.tg_campo_fila_atualizado_em();

-- ---------------------------------------------------------------- RLS + GRANT (padrão do resto da casa)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['campo_fila', 'campo_alvo', 'campo_roteiro', 'campo_roteiro_parada', 'campo_visita',
                            'campo_visita_foto'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_ler ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_ler ON plat.%1$s FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_inserir ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_inserir ON plat.%1$s FOR INSERT TO plat_app '
      'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_alterar ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_alterar ON plat.%1$s FOR UPDATE TO plat_app '
      'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_apagar ON plat.%1$s', t);
    EXECUTE format(
      'CREATE POLICY p_%1$s_apagar ON plat.%1$s FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('campo/fila_criar', 'campo (L2-07): fila de trabalho criada a partir de uma camada do inquilino'),
  ('campo/fila_alvos_adicionar', 'campo (L2-07): alvos (feições) acrescentados a uma fila'),
  ('campo/fila_ordem_atualizar', 'campo (L2-07): ordem dos alvos de uma fila reorganizada'),
  ('campo/roteiro_criar', 'campo (L2-07): roteiro do dia calculado a partir de uma fila'),
  ('campo/visita_registrar', 'campo (L2-07): visita registrada (estado, texto, coordenada, quem, quando)'),
  ('campo/visita_foto_enviar', 'campo (L2-07): foto anexada a uma visita')
ON CONFLICT (nome) DO NOTHING;
