-- 20260910T2350_formulario (item L5-03-form-builder, 10/09/2026): construtor de formulário de atributos
-- arrasta-e-solta por camada. Uma camada tem NO MÁXIMO um `plat.formulario` (o "form" da camada), com
-- N versões em `plat.formulario_versao` (rascunho até publicar; só uma publicada por vez). O desenho
-- (jsonb) é grupo -> campo, com condicional/cálculo como expressão da linguagem própria (item
-- L2-10-c-linguagem-expressao, `app/expressao/avaliador_py.py` + `web/js/expressao/avaliador.js`) — os
-- dois avaliadores concordam byte a byte, então o mesmo texto de expressão funciona idêntico no
-- construtor, na edição web e no PWA de campo (portão cláusula 2: "um só motor").
--
-- `publicar` COMPILA o desenho e grava a projeção em `plat.item.dados` da camada
-- (`regras_campo`/`form_condicionais`/`form_calculados` — ver app/formulario/motor.py): a validação de
-- obrigatório/domínio ESTÁTICO reaproveita o mecanismo que `app/edicao/servico.py::validar_atributos`
-- já aplicava (item L2-03-a); condicional e cálculo são os dois acréscimos novos deste item, lidos das
-- duas chaves novas por `validar_atributos` sem mudar sua assinatura.
--
-- Sem BEGIN/COMMIT. Idempotente. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.formulario (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  camada_id           uuid NOT NULL UNIQUE REFERENCES plat.item(id) ON DELETE CASCADE,
  nome                text NOT NULL DEFAULT 'Formulário' CHECK (btrim(nome) <> '' AND length(nome) <= 250),
  publicado_versao_id uuid,  -- FK acrescentada depois de criar formulario_versao (referência cruzada)
  criado_por          int REFERENCES plat.usuario(id),
  criado_em           timestamptz NOT NULL DEFAULT now(),
  atualizado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_formulario_tenant ON plat.formulario (tenant_id);

CREATE TABLE IF NOT EXISTS plat.formulario_versao (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  formulario_id uuid NOT NULL REFERENCES plat.formulario(id) ON DELETE CASCADE,
  versao       int NOT NULL CHECK (versao >= 1),
  desenho      jsonb NOT NULL CHECK (jsonb_typeof(desenho) = 'object'),
  publicado    boolean NOT NULL DEFAULT false,
  criado_por   int REFERENCES plat.usuario(id),
  criado_em    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (formulario_id, versao)
);
CREATE INDEX IF NOT EXISTS ix_formulario_versao_tenant ON plat.formulario_versao (tenant_id);
CREATE INDEX IF NOT EXISTS ix_formulario_versao_formulario ON plat.formulario_versao (formulario_id, versao DESC);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'formulario_publicado_versao_id_fkey' AND table_name = 'formulario'
  ) THEN
    ALTER TABLE plat.formulario
      ADD CONSTRAINT formulario_publicado_versao_id_fkey
      FOREIGN KEY (publicado_versao_id) REFERENCES plat.formulario_versao(id) ON DELETE SET NULL;
  END IF;
END $$;

-- só uma versão publicada por formulário (a coluna `publicado` é sinalização redundante lida por
-- `listar_versoes`; `formulario.publicado_versao_id` é a fonte única usada por `GET .../formulario`)
CREATE UNIQUE INDEX IF NOT EXISTS ux_formulario_versao_publicada
  ON plat.formulario_versao (formulario_id) WHERE publicado;

CREATE OR REPLACE FUNCTION plat.tg_formulario_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS tg_formulario_atualizado_em ON plat.formulario;
CREATE TRIGGER tg_formulario_atualizado_em BEFORE UPDATE ON plat.formulario
  FOR EACH ROW EXECUTE FUNCTION plat.tg_formulario_atualizado_em();

-- ---------------------------------------------------------------- RLS + GRANT (padrão do resto da casa)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['formulario', 'formulario_versao'] LOOP
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
  ('formulario/criar', 'formulario (L5-03): formulário de atributos criado para uma camada'),
  ('formulario/versao_salvar', 'formulario (L5-03): rascunho de desenho salvo'),
  ('formulario/versao_publicar', 'formulario (L5-03): versão publicada (regras compiladas na camada)')
ON CONFLICT (nome) DO NOTHING;
