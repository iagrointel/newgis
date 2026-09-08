-- 046_upload_retomavel (renomeada de 044_uploads: OUTRA sessão desta mesma árvore aplicou um "044_uploads.sql"
-- próprio ao banco compartilhado às 14:40 de 06/09 antes desta migração rodar — mesmo item, mesmo ADR, schema
-- IDÊNTICO campo a campo em plat.upload/plat.upload_parte e a mesma plat.upload_reservado_bytes já vivas no
-- banco quando isto foi conferido com \d; o arquivo original daquela sessão não ficou nesta árvore de trabalho
-- para comparar linha a linha, só o efeito no banco. Por isso esta migração é ESCRITA PARA SER SEGURA CONTRA
-- JÁ EXISTIR: TABLE/POLICY/FUNCTION usam sempre IF NOT EXISTS/OR REPLACE/DROP...IF EXISTS, e o que ela
-- acrescenta de fato ao que já estava aplicado é só `plat.uploads_expirar_candidatos` (função do periódico de
-- expurgo, que a outra sessão ainda não tinha criado). Upload retomável pelo navegador (item
-- L0-04-a-upload-arquivo; ADR 0005 seção 3). plat.upload é a
-- sessão de envio vista pelo navegador (nome, tamanho declarado, tipo declarado, sha256 declarado opcional,
-- estado); plat.upload_parte é o recibo de cada parte recebida (upload_id, n) — permite responder "quais partes
-- faltam" sem perguntar ao Garage, e permite reenvio idempotente da MESMA parte (upsert por (upload_id, n)).
-- O multipart real no Garage já existe (plat.arquivo_upload, 022_arquivos.sql/objetos.parte_iniciar): esta
-- migração NÃO duplica aquela tabela, só guarda o upload_s3_id (o upload_id que plat.arquivo_upload usa como
-- chave) e os campos que só fazem sentido do lado do navegador (nome original, tamanho/tipo/sha256 declarados,
-- contagem de partes esperada). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
--
-- Cota (D-upload-reserva, decisão desta trilha): a hipótese do ADR de reaproveitar tenant.uso_reservado_bytes
-- foi DESCARTADA por colisão de significado — a 029_ingestao_vetor.sql já usa aquela coluna para "armazenamento
-- de TABELA carregada" (comentário da própria 029: "independente da cota do bucket Garage"), e a cota deste item
-- é a do bucket Garage (tenant.cota_bytes, ADR 0006). Em vez de uma 2ª coluna de reserva concorrente, a reserva
-- É a soma de plat.upload.bytes_declarado com estado='iniciado' do inquilino: plat.upload_reservado_bytes(tenant)
-- abaixo faz essa soma sob o mesmo SELECT ... FOR UPDATE da linha do tenant, serializando duas reservas
-- concorrentes sem inventar um contador que possa dessincronizar (a reserva morre sozinha quando o upload
-- expira/aborta/conclui — não há reconciliação para esquecer de rodar).

CREATE TABLE IF NOT EXISTS plat.upload (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         int NOT NULL REFERENCES plat.tenant(id),
  usuario_id        int NOT NULL REFERENCES plat.usuario(id),
  nome              text NOT NULL CHECK (length(nome) BETWEEN 1 AND 255),
  bytes_declarado   bigint NOT NULL CHECK (bytes_declarado > 0),
  tipo_declarado    text NOT NULL,
  sha256_declarado  text CHECK (sha256_declarado IS NULL OR sha256_declarado ~ '^[0-9a-f]{64}$'),
  upload_s3_id      text NOT NULL UNIQUE,        -- FK lógica p/ plat.arquivo_upload.upload_id (022_arquivos.sql)
  chave_temp        text NOT NULL,
  parte_bytes       bigint NOT NULL,
  partes_total      int NOT NULL CHECK (partes_total >= 1),
  estado            text NOT NULL DEFAULT 'iniciado'
                    CHECK (estado IN ('iniciado', 'concluido', 'abortado', 'expirado')),
  arquivo_id        uuid REFERENCES plat.item(id),   -- preenchido em 'concluido'
  criado_em         timestamptz NOT NULL DEFAULT now(),
  atualizado_em     timestamptz NOT NULL DEFAULT now(),  -- toda parte recebida atualiza (é o relógio do expurgo 24h)
  expira_em         timestamptz NOT NULL,
  concluido_em      timestamptz
);
CREATE INDEX IF NOT EXISTS ix_upload_tenant_estado ON plat.upload (tenant_id, estado);
CREATE INDEX IF NOT EXISTS ix_upload_expurgo ON plat.upload (estado, atualizado_em) WHERE estado = 'iniciado';

CREATE TABLE IF NOT EXISTS plat.upload_parte (
  upload_id    uuid NOT NULL REFERENCES plat.upload(id) ON DELETE CASCADE,
  n            int NOT NULL CHECK (n >= 1),
  bytes        bigint NOT NULL CHECK (bytes >= 0),
  etag         text NOT NULL,
  sha256       text,
  recebida_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (upload_id, n)
);

ALTER TABLE plat.upload ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_upload ON plat.upload;
CREATE POLICY p_upload ON plat.upload FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.upload_parte ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_upload_parte ON plat.upload_parte;
CREATE POLICY p_upload_parte ON plat.upload_parte FOR ALL TO plat_app
  USING (EXISTS (SELECT 1 FROM plat.upload u WHERE u.id = upload_parte.upload_id AND u.tenant_id = plat.tenant_atual()))
  WITH CHECK (EXISTS (SELECT 1 FROM plat.upload u WHERE u.id = upload_parte.upload_id AND u.tenant_id = plat.tenant_atual()));

-- ---------------------------------------------------------------- reserva de cota (ver nota acima)
CREATE OR REPLACE FUNCTION plat.upload_reservado_bytes(p_tenant_id int) RETURNS bigint
LANGUAGE sql STABLE AS $$
  SELECT coalesce(sum(bytes_declarado), 0)::bigint FROM plat.upload
  WHERE tenant_id = p_tenant_id AND estado = 'iniciado';
$$;

-- ---------------------------------------------------------------- expurgo de uploads esquecidos (item L0-04-a,
-- periódico app.uploads.periodicos.uploads_expirar): SECURITY DEFINER, mesmo mecanismo de plat.sessoes_expurgar
-- (roda como o dono postgres, que não sofre a RLS de plat.upload) -- só assim o job periódico, que roda sob o
-- inquilino técnico `plataforma`, enxerga upload esquecido de QUALQUER inquilino. Só LÊ e devolve candidatos; o
-- abortamento em si (multipart no Garage) é feito pelo Python no contexto do inquilino de cada linha.
CREATE OR REPLACE FUNCTION plat.uploads_expirar_candidatos(p_horas int)
RETURNS TABLE (id uuid, tenant_id int, usuario_id int, upload_s3_id text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT u.id, u.tenant_id, u.usuario_id, u.upload_s3_id
  FROM plat.upload u
  WHERE u.estado = 'iniciado' AND u.atualizado_em < now() - (p_horas || ' hours')::interval
  ORDER BY u.atualizado_em;
$$;
GRANT EXECUTE ON FUNCTION plat.uploads_expirar_candidatos(int) TO plat_app;

-- ---------------------------------------------------------------- eventos novos
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('uploads/iniciar', 'upload retomável iniciado (item L0-04-a)'),
  ('uploads/concluir', 'upload retomável concluído: arquivo gravado no armazenamento'),
  ('uploads/abortar', 'upload retomável abortado ou expirado pelo periódico')
ON CONFLICT (nome) DO NOTHING;

GRANT EXECUTE ON FUNCTION plat.upload_reservado_bytes(int) TO plat_app;
