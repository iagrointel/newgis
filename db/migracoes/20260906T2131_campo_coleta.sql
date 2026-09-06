-- 20260906T2131_campo_coleta (item L2-07-a-pwa-instalavel-cache): destino da sincronização da PWA de campo.
-- A fila mora no dispositivo (IndexedDB, por slug de inquilino); o que chega aqui é o RESULTADO de cada
-- operação já aplicada: uma coleta de ponto com nota (o tipo de operação "coleta.criar" deste item;
-- L2-07-b/c acrescentam os tipos de formulário/edição sobre a mesma fila local). Idempotência por
-- (tenant_id, operacao_id): o uuid é gerado no dispositivo e reenvio da mesma operação não duplica linha.
-- mapa_id é referência LÓGICA a plat.item (sem FK): o mapa pode ser apagado depois e a coleta permanece.
-- criado_em é o relógio do dispositivo (declarado, não conferido); recebido_em é o relógio do servidor.
-- RLS/GRANT no padrão da 011/046 (default privileges da 001 cobrem tabela nova do postgres).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.campo_coleta (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id    int  NOT NULL REFERENCES plat.tenant(id),
  usuario_id   int  NOT NULL REFERENCES plat.usuario(id),
  operacao_id  uuid NOT NULL,
  mapa_id      uuid,
  geometria    geometry(Point, 4326) NOT NULL,
  atributos    jsonb NOT NULL DEFAULT '{}'::jsonb,
  criado_em    timestamptz NOT NULL,
  recebido_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, operacao_id)
);
CREATE INDEX IF NOT EXISTS campo_coleta_mapa ON plat.campo_coleta (mapa_id) WHERE mapa_id IS NOT NULL;
COMMENT ON TABLE plat.campo_coleta IS 'Coletas de campo recebidas da PWA (L2-07-a); idempotente por (tenant_id, operacao_id).';

ALTER TABLE plat.campo_coleta ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_campo_coleta ON plat.campo_coleta;
CREATE POLICY p_campo_coleta ON plat.campo_coleta FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
