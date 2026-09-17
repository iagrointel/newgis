-- 20260909T0345_webhooks: webhooks de eventos por inquilino (item L7-08-a-webhooks-eventos).
--
-- O que existe antes: plat.evento (particionado por mês, migração 003) é gravado por
-- plat.evento_registrar DENTRO da transação da mudança, com INSERT direto revogado a plat_app —
-- é a fila de fatos de domínio que o item pede ("eventos vindos da tabela de eventos de domínio
-- gravada na mesma transação da mudança").
--
-- Decisões que este DDL sela (ADR em docs/adr/, item L7-08-a):
--   1. O despacho é um GATILHO AFTER INSERT no PAI particionado (plpgsql lê a linha NOVA; nunca
--      depende de GUC de inquilino porque filtra por NEW.tenant_id — o gatilho roda com os
--      privilégios de quem efetivamente insere, e dentro de evento_registrar isso é o dono da
--      função, com RLS contornado). Assim TODA fonte de evento (hoje registrar_evento em
--      app/auth/comum.py e app/catalogo/comum.py) despacha sem que nenhuma rota mude, e a entrega
--      nasce atômica com o fato: ou o inquilino vê os dois (evento + entrega agendada) ou nenhum.
--   2. A entrega é uma linha em plat.webhook_entrega + UM job 'webhooks.entregar' por entrega
--      (plat.job): quem executa é o worker de jobs que já existe (L0-05), com retentativa própria
--      (max_tentativas=5, espera 2**tentativa s em job_devolver) — não se inventa um segundo
--      executador nem um segundo relógio. webhook-id do Standard Webhooks = id da ENTREGA, então
--      reenvio manual repete o mesmo id e o receptor pode deduplicar.
--   3. O segredo nunca dorme em claro: AES-GCM com chave derivada de PLAT_SECRET e prefixo/AAD
--      próprios (app/webhooks/assinatura.py, mesmo padrão de app/conexao/credencial.py).
--   4. Desativação automática por entregas seguidas falhadas é REGRA DE APLICAÇÃO (tarefa), não
--      gatilho: precisa ler a config do inquilino (config.webhooks.desativar_apos) e enfileirar
--      aviso por e-mail — coisas de Python, não de plpgsql.

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('webhooks/criar', 'webhook criado pelo admin (a resposta traz o segredo uma única vez)'),
  ('webhooks/atualizar', 'nome, URL, eventos ou ativo alterados'),
  ('webhooks/rotacionar', 'segredo de assinatura rotacionado'),
  ('webhooks/apagar', 'webhook apagado'),
  ('webhooks/reenvio', 'entrega reenviada manualmente (entrega_id)'),
  ('webhooks/desativar', 'desativado automaticamente por falhas seguidas ou pelo admin (motivo)'),
  ('webhooks/reativar', 'reativado pelo admin (falhas consecutivas zeradas)')
ON CONFLICT (nome) DO NOTHING;

CREATE TABLE IF NOT EXISTS plat.webhook (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  nome                text NOT NULL CHECK (length(btrim(nome)) BETWEEN 3 AND 120),
  url                 text NOT NULL CHECK (length(url) <= 2048),
  eventos             text[] NOT NULL CHECK (array_length(eventos, 1) >= 1),
  ativo               boolean NOT NULL DEFAULT true,
  segredo_cifrado     text NOT NULL,
  falhas_consecutivas int NOT NULL DEFAULT 0,
  desativada_em       timestamptz,
  desativada_motivo   text,
  criado_em           timestamptz NOT NULL DEFAULT now(),
  atualizado_em       timestamptz NOT NULL DEFAULT now(),
  criado_por          int REFERENCES plat.usuario(id)
);
CREATE INDEX IF NOT EXISTS ix_webhook_tenant ON plat.webhook (tenant_id);

ALTER TABLE plat.webhook ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_webhook ON plat.webhook;
CREATE POLICY p_webhook ON plat.webhook FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, UPDATE, DELETE ON plat.webhook TO plat_app;

CREATE TABLE IF NOT EXISTS plat.webhook_entrega (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     int NOT NULL REFERENCES plat.tenant(id),
  webhook_id    uuid NOT NULL REFERENCES plat.webhook(id) ON DELETE CASCADE,
  evento_id     bigint NOT NULL,
  tipo_evento   text NOT NULL,
  payload       jsonb NOT NULL,
  estado        text NOT NULL DEFAULT 'pendente'
                CHECK (estado IN ('pendente', 'entregue', 'falhou', 'desativada')),
  tentativas    int NOT NULL DEFAULT 0,
  reenvios      int NOT NULL DEFAULT 0,
  ultima_status int,
  ultima_erro   text,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  entregue_em   timestamptz
);
CREATE INDEX IF NOT EXISTS ix_webhook_entrega_webhook ON plat.webhook_entrega (webhook_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_webhook_entrega_evento ON plat.webhook_entrega (evento_id);

ALTER TABLE plat.webhook_entrega ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_webhook_entrega ON plat.webhook_entrega;
CREATE POLICY p_webhook_entrega ON plat.webhook_entrega FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
-- sem INSERT: a entrega nasce SÓ pelo gatilho de despacho (que roda com os privilégios do dono de
-- plat.evento_registrar, dentro da transação do fato); a API e a tarefa leem e marcam estado (UPDATE).
GRANT SELECT, UPDATE ON plat.webhook_entrega TO plat_app;

-- Despacho: para cada webhook ativo do inquilino da linha NOVA assinado no tipo do evento, nasce
-- uma entrega (payload congelado no momento do fato) + um job para o worker. Esquema de mapeamento
-- do verbo para os valores de `op` do payload da Esri (FeatureServer): criar/adicionar -> created,
-- atualizar -> updated, apagar -> deleted; fora desses, o verbo do tipo vai verbatim.
CREATE OR REPLACE FUNCTION plat.webhook_despachar_evento() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_webhook record;
  v_entrega uuid;
BEGIN
  FOR v_webhook IN
    SELECT w.id, w.nome FROM plat.webhook w
    WHERE w.tenant_id = NEW.tenant_id AND w.ativo AND NEW.tipo = ANY (w.eventos)
  LOOP
    INSERT INTO plat.webhook_entrega(tenant_id, webhook_id, evento_id, tipo_evento, payload)
    VALUES (NEW.tenant_id, v_webhook.id, NEW.id, NEW.tipo,
      jsonb_build_object(
        'id', NEW.id::text,
        'name', v_webhook.nome,
        'type', NEW.tipo,
        'op', CASE split_part(NEW.tipo, '/', 2)
                WHEN 'criar' THEN 'created' WHEN 'adicionar' THEN 'created'
                WHEN 'atualizar' THEN 'updated'
                WHEN 'apagar' THEN 'deleted'
                ELSE split_part(NEW.tipo, '/', 2) END,
        'when', to_jsonb(NEW.em),
        -- 'plataforma' de propósito: o literal 'plat' NU (sem ponto) casaria com a reescrita de schema
        -- de trilha/homologação (app/schema_ambiente.py, \bplat\b) e corromperia o payload no ambiente isolado
        'source', 'plataforma',
        'alvo', jsonb_build_object('tipo', NEW.alvo_tipo, 'id', NEW.alvo_id),
        'ator_id', NEW.ator_id,
        'properties', NEW.propriedades))
    RETURNING id INTO v_entrega;
    INSERT INTO plat.job(tenant_id, usuario_id, tipo, parametros, prioridade, chave, pesado,
                         memoria_mb, timeout_s, executor, max_tentativas)
    VALUES (NEW.tenant_id, NULL, 'webhooks.entregar',
            jsonb_build_object('entrega_id', v_entrega::text), 2, v_entrega::text,
            false, 256, 60, 'local', 5);
  END LOOP;
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS webhook_evento_despachar ON plat.evento;
CREATE TRIGGER webhook_evento_despachar AFTER INSERT ON plat.evento
  FOR EACH ROW EXECUTE FUNCTION plat.webhook_despachar_evento();

-- Expurgo do log de entregas (periódico webhooks.expurgar no inquilino técnico `plataforma`):
-- atravessa inquilinos de propósito (mesmo contrato de plat.jobs_expurgar, 006), por isso SECURITY
-- DEFINER + a mesma guarda de contexto. EXECUTE: revoked de PUBLIC pelo default privileges da 006 —
-- o periódico roda como plat_app, então o grant vai a plat_app, como no precedente.
CREATE OR REPLACE FUNCTION plat.webhook_entregas_expurgar(p_dias int DEFAULT 30) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  IF plat.tenant_atual() IS DISTINCT FROM (SELECT id FROM plat.tenant WHERE slug = 'plataforma') THEN
    RAISE EXCEPTION 'expurgo só no contexto do inquilino técnico plataforma' USING ERRCODE = 'insufficient_privilege';
  END IF;
  DELETE FROM plat.webhook_entrega
   WHERE criado_em < now() - make_interval(days => greatest(p_dias, 1));
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
REVOKE EXECUTE ON FUNCTION plat.webhook_entregas_expurgar(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.webhook_entregas_expurgar(int) TO plat_app;
