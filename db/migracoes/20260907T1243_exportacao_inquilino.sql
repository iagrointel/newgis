-- 20260907T1243_exportacao_inquilino: botão "Exportar meu inquilino" (item L0-06-d-exportar-inquilino).
-- Carimbo de tempo, não número sequencial (ADR 0014). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Uma linha por pedido de exportação COMPLETA do inquilino (não de uma camada só, como plat.exportacao do
-- L0-04-h): o pacote final tem um GeoPackage com todas as camadas hospedadas, um catálogo em JSON (itens,
-- pastas, grupos, compartilhamentos, relações, usuários SEM hash de senha), os arquivos do bucket zipados por
-- item e um manifesto com sha256 de cada componente — a spec 17.4 chama isso de "escrow prático": o cliente
-- sai com um formato aberto, sem depender de nós. O privilégio já existe (`org.exportar`, migração 003) —
-- este arquivo não cria privilégio novo.

CREATE TABLE IF NOT EXISTS plat.exportacao_inquilino (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  usuario_id        int NOT NULL REFERENCES plat.usuario(id),
  estado            text NOT NULL DEFAULT 'pendente'
                    CHECK (estado IN ('pendente','gerando','pronta','falhou','cancelada','expirada')),
  job_id            uuid,
  estimativa_bytes  bigint NOT NULL DEFAULT 0,
  n_itens           int,
  n_camadas         int,
  n_arquivos        int,
  arquivo_item_id   uuid REFERENCES plat.item(id) ON DELETE SET NULL,  -- item na pasta do admin que pediu
  chave             text,                                 -- chave do objeto no Garage (app/objetos.py)
  sha256            text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  bytes             bigint,
  duracao_ms        int,
  erro              text,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  concluido_em      timestamptz,
  expira_em         timestamptz NOT NULL DEFAULT now() + interval '7 days'
);
CREATE INDEX IF NOT EXISTS ix_exportacao_inquilino_tenant ON plat.exportacao_inquilino (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_exportacao_inquilino_expira ON plat.exportacao_inquilino (expira_em)
  WHERE estado = 'pronta';

ALTER TABLE plat.exportacao_inquilino ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.exportacao_inquilino FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_exportacao_inquilino ON plat.exportacao_inquilino;
CREATE POLICY p_exportacao_inquilino ON plat.exportacao_inquilino FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- estado final é imutável (mesmo padrão de plat.exportacao_estado_final_imutavel, 20260907T0141)
CREATE OR REPLACE FUNCTION plat.exportacao_inquilino_estado_final_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IN ('falhou','cancelada','expirada') AND NEW.estado IS DISTINCT FROM OLD.estado THEN
    RAISE EXCEPTION 'exportacao_inquilino_em_estado_final' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS exportacao_inquilino_estado_final_imutavel ON plat.exportacao_inquilino;
CREATE TRIGGER exportacao_inquilino_estado_final_imutavel BEFORE UPDATE ON plat.exportacao_inquilino
  FOR EACH ROW EXECUTE FUNCTION plat.exportacao_inquilino_estado_final_imutavel();

-- ---------------------------------------------------------------- limite de 1 execução por dia (refutação:
-- pedir a segunda no mesmo dia UTC tem de devolver 429). Conta pendente/gerando/pronta — uma que falhou ou foi
-- cancelada não consome a cota do dia, senão um erro transitório (disco cheio, ogr2ogr indisponível) trancaria
-- o admin até o dia seguinte por um problema que não é dele.
CREATE OR REPLACE FUNCTION plat.exportacao_inquilino_hoje(p_tenant int) RETURNS int
LANGUAGE sql STABLE AS $$
  SELECT count(*)::int FROM plat.exportacao_inquilino
  WHERE tenant_id = p_tenant AND criado_em >= date_trunc('day', now())
    AND estado NOT IN ('falhou','cancelada');
$$;
GRANT EXECUTE ON FUNCTION plat.exportacao_inquilino_hoje(int) TO plat_app;

-- ---------------------------------------------------------------- expurgo das vencidas (periódico
-- inquilino.expirar; mesmo mecanismo de plat.exportacoes_expirar_candidatos)
CREATE OR REPLACE FUNCTION plat.exportacoes_inquilino_expirar_candidatos()
RETURNS TABLE (id uuid, tenant_id int, usuario_id int, chave text, arquivo_item_id uuid)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT e.id, e.tenant_id, e.usuario_id, e.chave, e.arquivo_item_id
  FROM plat.exportacao_inquilino e
  WHERE e.estado = 'pronta' AND e.expira_em < now()
  ORDER BY e.expira_em;
$$;
GRANT EXECUTE ON FUNCTION plat.exportacoes_inquilino_expirar_candidatos() TO plat_app;

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('inquilino/exportar', 'exportação completa do inquilino pedida (item L0-06-d)'),
  ('inquilino/exportar_baixar', 'pacote de exportação do inquilino baixado')
ON CONFLICT (nome) DO NOTHING;
