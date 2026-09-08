-- Atualização viva de painéis e mapas (item L2-06-d-atualizacao-viva-sse). Quando a tabela física de uma
-- camada muda, o Postgres avisa a aplicação por NOTIFY e a aplicação repassa aos navegadores assinados por
-- Server-Sent Events (`GET /api/eventos/camadas`, app/vivo/). Nada de um segundo mecanismo de empurrão: é o
-- MESMO desenho do progresso de job (migração 004 + app/jobs/eventos.py) — gatilho → pg_notify → um LISTEN
-- por processo → fan-out para as filas asyncio dos clientes.
--
-- Três peças:
--  1. `plat.camada_versao` — contador monotônico por camada (o painel só refaz a consulta quando a versão sobe).
--  2. `plat.camada_evento` — os eventos recentes, para o cliente que reconecta recuperar o que perdeu pelo
--     cabeçalho `Last-Event-ID` (o `id` do evento SSE é a chave desta tabela). Janela curta (poda por tempo).
--  3. `plat.camada_notificar()` + `plat.camada_observar(uuid)` — gatilho POR COMANDO (não por linha: uma
--     edição em lote de 10 mil linhas gera UM evento, não 10 mil) instalado sob demanda na tabela física.
--
-- O canal é `plat_camada` em produção e `plat_t<trilha>_camada` numa trilha isolada: a concatenação
-- `'plat' || '_camada'` existe para que o reescritor de schema (laco/trilha_reescrever.py, que troca o token
-- `plat` isolado) alcance o nome do canal — escrito de uma vez só, `'plat_camada'` seria um token único e
-- duas trilhas escutariam o canal uma da outra.
-- Idempotente; sem BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS plat.camada_versao (
  camada_id      uuid PRIMARY KEY REFERENCES plat.item(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  versao         bigint NOT NULL DEFAULT 0,
  atualizado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plat.camada_evento (
  id         bigserial PRIMARY KEY,
  tenant_id  int NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  camada_id  uuid NOT NULL,
  versao     bigint NOT NULL,
  operacao   text NOT NULL,
  em         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS camada_evento_em_idx ON plat.camada_evento (em);
CREATE INDEX IF NOT EXISTS camada_evento_tenant_idx ON plat.camada_evento (tenant_id, id);

ALTER TABLE plat.camada_versao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.camada_evento ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS camada_versao_tenant ON plat.camada_versao;
CREATE POLICY camada_versao_tenant ON plat.camada_versao FOR ALL TO PUBLIC
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS camada_evento_tenant ON plat.camada_evento;
CREATE POLICY camada_evento_tenant ON plat.camada_evento FOR ALL TO PUBLIC
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT ON plat.camada_versao, plat.camada_evento TO plat_app;

-- ---------------------------------------------------------------- gatilho por comando
CREATE OR REPLACE FUNCTION plat.camada_notificar() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'plat', 'public' AS $func$
DECLARE
  v_camada uuid   := TG_ARGV[0]::uuid;
  v_tenant int    := TG_ARGV[1]::int;
  v_versao bigint;
  v_id     bigint;
  v_em     timestamptz;
BEGIN
  INSERT INTO plat.camada_versao AS cv (camada_id, tenant_id, versao, atualizado_em)
       VALUES (v_camada, v_tenant, 1, now())
  ON CONFLICT (camada_id) DO UPDATE SET versao = cv.versao + 1, atualizado_em = now()
    RETURNING cv.versao INTO v_versao;
  INSERT INTO plat.camada_evento (tenant_id, camada_id, versao, operacao)
       VALUES (v_tenant, v_camada, v_versao, lower(TG_OP))
    RETURNING id, em INTO v_id, v_em;
  PERFORM pg_notify('plat' || '_camada', json_build_object(
    'id', v_id, 'tenant_id', v_tenant, 'camada', v_camada, 'versao', v_versao,
    'operacao', lower(TG_OP), 'em', v_em)::text);
  RETURN NULL;
END $func$;
REVOKE EXECUTE ON FUNCTION plat.camada_notificar() FROM PUBLIC;

-- Instala o gatilho na tabela física da camada. Idempotente e BARATA quando já existe: só faz DDL (que pede
-- lock na tabela) se `pg_trigger` ainda não tem o gatilho — é por isso que a rota de assinatura pode chamar
-- esta função a cada conexão nova sem travar a edição de quem está trabalhando na camada.
CREATE OR REPLACE FUNCTION plat.camada_observar(p_camada uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'plat', 'public' AS $func$
DECLARE
  r_item   record;
  v_schema text;
  v_tabela text;
  v_nome   text := 'plat_camada_notificar';
BEGIN
  SELECT i.id, i.tenant_id, i.tipo, i.dados INTO r_item
    FROM plat.item i WHERE i.id = p_camada AND i.apagado_em IS NULL;
  IF r_item.id IS NULL THEN
    RAISE EXCEPTION 'camada inexistente' USING ERRCODE = 'no_data_found';
  END IF;
  IF plat.tenant_atual() IS NOT NULL AND r_item.tenant_id <> plat.tenant_atual() THEN
    RAISE EXCEPTION 'camada de outro inquilino' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF r_item.tipo <> 'camada_vetorial' THEN
    RETURN false;
  END IF;
  v_schema := r_item.dados->>'schema';
  v_tabela := r_item.dados->>'tabela';
  IF v_schema IS NULL OR v_tabela IS NULL THEN
    RETURN false;
  END IF;
  IF to_regclass(format('%I.%I', v_schema, v_tabela)) IS NULL THEN
    RETURN false;
  END IF;
  INSERT INTO plat.camada_versao (camada_id, tenant_id, versao)
       VALUES (p_camada, r_item.tenant_id, 0)
  ON CONFLICT (camada_id) DO NOTHING;
  IF EXISTS (SELECT 1 FROM pg_trigger t
              WHERE t.tgrelid = to_regclass(format('%I.%I', v_schema, v_tabela))
                AND t.tgname = v_nome AND NOT t.tgisinternal) THEN
    RETURN true;
  END IF;
  EXECUTE format(
    'CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I.%I '
    'FOR EACH STATEMENT EXECUTE FUNCTION plat.camada_notificar(%L, %L)',
    v_nome, v_schema, v_tabela, p_camada::text, r_item.tenant_id::text);
  RETURN true;
END $func$;
REVOKE EXECUTE ON FUNCTION plat.camada_observar(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_observar(uuid) TO plat_app;

-- ---------------------------------------------------------------- reconexão e poda
-- Eventos perdidos entre a queda e a reconexão do cliente (cabeçalho Last-Event-ID). Sempre do inquilino
-- do contexto e só das camadas que o cliente assinou — id de camada vindo do navegador nunca amplia o que
-- ele enxerga.
CREATE OR REPLACE FUNCTION plat.camada_eventos_desde(p_desde bigint, p_camadas uuid[], p_limite int DEFAULT 500)
RETURNS TABLE(id bigint, camada_id uuid, versao bigint, operacao text, em timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'plat', 'public' AS $func$
  SELECT e.id, e.camada_id, e.versao, e.operacao, e.em
    FROM plat.camada_evento e
   WHERE e.tenant_id = plat.tenant_atual()
     AND e.id > p_desde
     AND e.camada_id = ANY (p_camadas)
   ORDER BY e.id
   LIMIT greatest(1, least(p_limite, 500))
$func$;
REVOKE EXECUTE ON FUNCTION plat.camada_eventos_desde(bigint, uuid[], int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_eventos_desde(bigint, uuid[], int) TO plat_app;

-- A janela de recuperação é curta de propósito: quem some por mais que isso recarrega a tela inteira, que é
-- mais barato do que guardar histórico de edição aqui (o histórico de verdade é o versionamento da camada).
CREATE OR REPLACE FUNCTION plat.camada_eventos_podar(p_minutos int DEFAULT 15) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'plat', 'public' AS $func$
DECLARE n bigint;
BEGIN
  DELETE FROM plat.camada_evento WHERE em < now() - make_interval(mins => greatest(1, p_minutos));
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $func$;
REVOKE EXECUTE ON FUNCTION plat.camada_eventos_podar(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.camada_eventos_podar(int) TO plat_app;
