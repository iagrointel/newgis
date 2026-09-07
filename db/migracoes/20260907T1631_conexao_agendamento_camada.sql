-- 20260907T1631_conexao_agendamento_camada: item L6-02-k-agendamento — atualização agendada de camadas
-- copiadas (`plat.conexao.modo = 'copiada'`). NÃO cria outro relógio: reusa `plat.agenda`/`app/jobs/agenda.py`
-- (tick a cada 30 s, intervalo mínimo de 15 min já em INTERVALO_MINIMO_S) e o mecanismo de "5 falhas seguidas
-- pausam" já gravado em `plat.agenda_registrar_fim` (004, achado B9) — aqui só se ACRESCENTA o aviso por
-- e-mail quando isso acontece (throttle de 6 h) e o teto de tarefas ATIVAS por USUÁRIO (a referência Esri
-- publica 10 por usuário; 50 por organização já existe em `plat.cota_agendas`, default da 004).
--
-- Guarda de dado: a cópia em si (`plat.camada_copia_versao.bytes`) é o corpo bruto que o conector devolveu
-- (`app.conexao.seguranca.buscar_seguro(..., guardar_corpo=True)`, já existente, já defendido contra SSRF) —
-- este item entrega o AGENDAMENTO e a TROCA ATÔMICA, genéricos para qualquer conector futuro que precise
-- copiar; o parser específico de cada formato (CSV/GeoJSON/WMS/...) é de outros itens da família L6-02-*.
-- Troca atômica por VERSIONAMENTO + PONTEIRO (Postgres nativo, ADR: nenhuma tabela nova por conector): a nova
-- versão é inserida e COMMITADA por inteiro numa transação; só depois um UPDATE de UMA linha em
-- `plat.camada_copia_atual` aponta para ela — se o worker morrer entre as duas, o ponteiro continua na
-- versão antiga, íntegra; nenhuma consulta concorrente vê a camada vazia (MVCC do Postgres: um SELECT sempre
-- lê a linha do ponteiro inteira, antes OU depois do UPDATE, nunca no meio).
--
-- Numeração por carimbo de tempo (ADR 0014). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres (dono das
-- funções SECURITY DEFINER).

-- ---------------------------------------------------------------- versões da cópia (uma linha por fetch bem-sucedido)
CREATE TABLE IF NOT EXISTS plat.camada_copia_versao (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conexao_id     uuid NOT NULL REFERENCES plat.conexao(id) ON DELETE CASCADE,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  conteudo_tipo  text,
  tamanho_bytes  int NOT NULL CHECK (tamanho_bytes >= 0),
  bytes          bytea NOT NULL,
  criada_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_camada_copia_versao_conexao ON plat.camada_copia_versao (conexao_id, criada_em DESC);
CREATE INDEX IF NOT EXISTS ix_camada_copia_versao_tenant  ON plat.camada_copia_versao (tenant_id);

-- ponteiro: 1 linha por conexão copiada, a versão CORRENTE (a "camada" que o resto da casa lê)
CREATE TABLE IF NOT EXISTS plat.camada_copia_atual (
  conexao_id     uuid PRIMARY KEY REFERENCES plat.conexao(id) ON DELETE CASCADE,
  versao_id      uuid NOT NULL REFERENCES plat.camada_copia_versao(id),
  atualizado_em  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE plat.camada_copia_versao ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.camada_copia_atual  ENABLE ROW LEVEL SECURITY;

-- só leitura direta para o inquilino dono; toda escrita passa pelas funções SECURITY DEFINER abaixo (o worker
-- da agenda roda no inquilino da conexão, então plat.tenant_atual() já é o dono no INSERT da versão nova —
-- mas a TROCA e a PODA precisam ver a tabela de ponteiro por FORA da RLS por um instante só, mesmo padrão de
-- plat.conexao_saude_registrar).
DROP POLICY IF EXISTS p_camada_copia_versao_ler ON plat.camada_copia_versao;
CREATE POLICY p_camada_copia_versao_ler ON plat.camada_copia_versao FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_camada_copia_atual_ler ON plat.camada_copia_atual;
CREATE POLICY p_camada_copia_atual_ler ON plat.camada_copia_atual FOR SELECT TO plat_app
  USING (EXISTS (SELECT 1 FROM plat.conexao c WHERE c.id = camada_copia_atual.conexao_id AND c.tenant_id = plat.tenant_atual()));

REVOKE ALL ON plat.camada_copia_versao FROM PUBLIC;
REVOKE ALL ON plat.camada_copia_atual  FROM PUBLIC;
GRANT SELECT ON plat.camada_copia_versao TO plat_app;
GRANT SELECT ON plat.camada_copia_atual  TO plat_app;

-- ---------------------------------------------------------------- grava 1 versão nova (chamada pelo job, no inquilino da conexão)
CREATE OR REPLACE FUNCTION plat.camada_copia_versao_inserir(
  p_conexao uuid, p_conteudo_tipo text, p_bytes bytea
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_tenant int; v_id uuid;
BEGIN
  SELECT tenant_id INTO v_tenant FROM plat.conexao WHERE id = p_conexao AND modo = 'copiada';
  IF v_tenant IS NULL THEN
    RAISE EXCEPTION 'conexao % inexistente ou modo != copiada' , p_conexao USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF v_tenant IS DISTINCT FROM plat.tenant_atual() THEN
    RAISE EXCEPTION 'gravacao de versao fora do inquilino da conexao' USING ERRCODE = 'insufficient_privilege';
  END IF;
  INSERT INTO plat.camada_copia_versao(conexao_id, tenant_id, conteudo_tipo, tamanho_bytes, bytes)
  VALUES (p_conexao, v_tenant, p_conteudo_tipo, length(p_bytes), p_bytes)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;

-- troca atômica: UMA linha, UM UPDATE (ou INSERT na 1ª vez). Devolve a versão ANTERIOR (NULL na 1ª troca) para
-- quem chama decidir se apaga (poda) — nunca apaga aqui dentro, para o UPDATE do ponteiro ficar o mais curto
-- possível (o item pede a troca atômica; a poda é operação à parte, best-effort).
CREATE OR REPLACE FUNCTION plat.camada_copia_trocar(p_conexao uuid, p_versao uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_anterior uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.camada_copia_versao WHERE id = p_versao AND conexao_id = p_conexao) THEN
    RAISE EXCEPTION 'versao % nao pertence a conexao %', p_versao, p_conexao USING ERRCODE = 'invalid_parameter_value';
  END IF;
  -- lê a versão ANTERIOR antes de qualquer escrita (FOR UPDATE: serializa trocas concorrentes da MESMA
  -- conexão, nunca de conexões diferentes — o lock é por linha)
  SELECT versao_id INTO v_anterior FROM plat.camada_copia_atual WHERE conexao_id = p_conexao FOR UPDATE;
  INSERT INTO plat.camada_copia_atual(conexao_id, versao_id, atualizado_em)
  VALUES (p_conexao, p_versao, now())
  ON CONFLICT (conexao_id) DO UPDATE SET versao_id = EXCLUDED.versao_id, atualizado_em = EXCLUDED.atualizado_em;
  RETURN v_anterior;
END $$;

-- ---------------------------------------------------------------- poda: mantém só a versão corrente (D21: disco)
CREATE OR REPLACE FUNCTION plat.camada_copia_podar(p_conexao uuid, p_manter uuid) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  DELETE FROM plat.camada_copia_versao WHERE conexao_id = p_conexao AND id <> p_manter;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- ---------------------------------------------------------------- teto de tarefas ATIVAS por usuário (Esri: 10/usuário, 50/org)
CREATE OR REPLACE FUNCTION plat.cota_agendas_usuario(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->>'cota_agendas_usuario')::int, 10) FROM plat.tenant WHERE id = p_tenant
$$;

CREATE OR REPLACE FUNCTION plat.agendas_ativas_usuario(p_usuario int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*)::int FROM plat.agenda WHERE usuario_id = p_usuario AND ativa
$$;

-- ---------------------------------------------------------------- aviso ao dono quando a agenda pausa por falha
-- Fila simples (nunca envia direto daqui: e-mail é I/O, e SECURITY DEFINER síncrono dentro do relógio do
-- worker não pode bloquear o tick de outras agendas). `app/conexao/tarefas_agendamento.py::agenda_avisos_enviar`
-- (periódico, mesmo padrão de conexoes.saude_verificar) consome as pendentes.
CREATE TABLE IF NOT EXISTS plat.agenda_aviso (
  id          bigserial PRIMARY KEY,
  agenda_id   uuid NOT NULL REFERENCES plat.agenda(id) ON DELETE CASCADE,
  tenant_id   int NOT NULL REFERENCES plat.tenant(id),
  usuario_id  int REFERENCES plat.usuario(id),
  motivo      text NOT NULL,
  criado_em   timestamptz NOT NULL DEFAULT now(),
  enviado_em  timestamptz
);
CREATE INDEX IF NOT EXISTS ix_agenda_aviso_pendente ON plat.agenda_aviso (criado_em) WHERE enviado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_agenda_aviso_agenda    ON plat.agenda_aviso (agenda_id, criado_em DESC);

ALTER TABLE plat.agenda_aviso ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_agenda_aviso_ler ON plat.agenda_aviso;
CREATE POLICY p_agenda_aviso_ler ON plat.agenda_aviso FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());
REVOKE ALL ON plat.agenda_aviso FROM PUBLIC;
GRANT SELECT ON plat.agenda_aviso TO plat_app;

-- 1 aviso pendente/enviado a cada 6h por agenda (throttle na ENTRADA, não no envio): se já existe um aviso
-- desta agenda criado nas últimas 6h (pendente ou já enviado), não insere outro.
CREATE OR REPLACE FUNCTION plat.agenda_aviso_registrar(p_agenda uuid, p_motivo text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE a plat.agenda; v_id bigint;
BEGIN
  SELECT * INTO a FROM plat.agenda WHERE id = p_agenda;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF EXISTS (SELECT 1 FROM plat.agenda_aviso WHERE agenda_id = p_agenda AND criado_em > now() - interval '6 hours') THEN
    RETURN NULL;
  END IF;
  INSERT INTO plat.agenda_aviso(agenda_id, tenant_id, usuario_id, motivo)
  VALUES (p_agenda, a.tenant_id, a.usuario_id, p_motivo) RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION plat.agenda_avisos_pendentes(p_limite int DEFAULT 50)
RETURNS TABLE (id bigint, agenda_id uuid, tenant_id int, usuario_id int, motivo text, nome text, email text)
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT v.id, v.agenda_id, v.tenant_id, v.usuario_id, v.motivo, a.nome, u.email
  FROM plat.agenda_aviso v
  JOIN plat.agenda a ON a.id = v.agenda_id
  LEFT JOIN plat.usuario u ON u.id = v.usuario_id
  WHERE v.enviado_em IS NULL
  ORDER BY v.criado_em
  LIMIT p_limite
$$;

CREATE OR REPLACE FUNCTION plat.agenda_aviso_marcar_enviado(p_id bigint) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = plat, public AS $$
  UPDATE plat.agenda_aviso SET enviado_em = now() WHERE id = p_id
$$;

-- estende agenda_registrar_fim (004): ao pausar por 5 falhas seguidas, registra o aviso (throttle embutido
-- em agenda_aviso_registrar). Mesma assinatura — CREATE OR REPLACE não muda quem chama.
CREATE OR REPLACE FUNCTION plat.agenda_registrar_fim(p_job uuid, p_agenda uuid, p_estado text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_falhas_antes int; v_pausou boolean;
BEGIN
  SELECT falhas_seguidas INTO v_falhas_antes FROM plat.agenda WHERE id = p_agenda;
  v_pausou := (p_estado = 'falhou' AND coalesce(v_falhas_antes, 0) + 1 >= 5);
  UPDATE plat.agenda SET ultimo_estado = p_estado, ultimo_job_id = p_job,
    falhas_seguidas = CASE WHEN p_estado = 'falhou' THEN falhas_seguidas + 1 WHEN p_estado = 'concluido' THEN 0 ELSE falhas_seguidas END,
    ativa = CASE WHEN v_pausou THEN false ELSE ativa END,
    proxima_em = CASE WHEN v_pausou THEN NULL ELSE proxima_em END
  WHERE id = p_agenda;
  IF v_pausou THEN
    PERFORM plat.agenda_aviso_registrar(p_agenda, format('agenda pausada apos 5 falhas seguidas (job %s)', p_job));
  END IF;
END $$;

-- ---------------------------------------------------------------- EXECUTE só plat_app/plat_worker (achado do adversário do T1, 004)
DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.camada_copia_versao_inserir(uuid, text, bytea)', 'plat.camada_copia_trocar(uuid, uuid)',
    'plat.camada_copia_podar(uuid, uuid)', 'plat.cota_agendas_usuario(int)', 'plat.agendas_ativas_usuario(int)',
    'plat.agenda_aviso_registrar(uuid, text)', 'plat.agenda_avisos_pendentes(int)',
    'plat.agenda_aviso_marcar_enviado(bigint)', 'plat.agenda_registrar_fim(uuid, uuid, text)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/atualizar_copia', 'execução agendada de atualização de camada copiada (conexao_id, ok, tamanho_bytes)'),
  ('agendas/aviso_pausada', 'e-mail enviado ao dono avisando que a agenda pausou por 5 falhas seguidas')
ON CONFLICT (nome) DO NOTHING;
