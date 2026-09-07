-- 20260906T2109_modo_manutencao: modo somente-leitura/manutenção global e por inquilino (item
-- L7-33-modo-somente-leitura; paridade com o `mode` do Portal e o site mode READ_ONLY do Server).
-- plat.sistema = bandeira chave/valor com quem/quando/motivo (infraestrutura: plat_app nunca escreve,
-- lê só pela função); plat.sistema_trilha = histórico append-only de cada ligar/desligar.
-- plat.job_pegar ganha a cláusula de pausa: inquilino sob modo não tem job pendente retirado; o job
-- em execução no momento de ligar NÃO é tocado (termina normal) e a fila retoma ao desligar.
-- Idempotente. Aplicada como postgres pelo db/migrar.sh. Sem BEGIN/COMMIT: o aplicador abre a transação.

CREATE TABLE IF NOT EXISTS plat.sistema (
  chave          text PRIMARY KEY,
  valor          jsonb NOT NULL DEFAULT '{}'::jsonb,
  motivo         text NOT NULL,
  atualizado_por text NOT NULL,
  atualizado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plat.sistema_trilha (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  chave         text NOT NULL,
  acao          text NOT NULL,
  valor         jsonb NOT NULL,
  quem          text NOT NULL,
  motivo        text NOT NULL,
  registrado_em timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- chave canônica do modo
CREATE OR REPLACE FUNCTION plat.modo_chave(p_escopo text, p_tenant_id int) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = plat, public AS $$
BEGIN
  IF p_escopo = 'global' THEN RETURN 'modo_manutencao'; END IF;
  IF p_escopo = 'inquilino' AND p_tenant_id IS NOT NULL THEN
    RETURN 'modo_manutencao:tenant:' || p_tenant_id;
  END IF;
  RAISE EXCEPTION 'escopo de modo inválido: % (tenant %)', p_escopo, p_tenant_id;
END $$;

-- ---------------------------------------------------------------- leitura efetiva: global vence; depois o inquilino
CREATE OR REPLACE FUNCTION plat.modo_ler(p_tenant_id int DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE g plat.sistema; t plat.sistema;
BEGIN
  SELECT * INTO g FROM plat.sistema WHERE chave = 'modo_manutencao';
  IF g.chave IS NOT NULL AND coalesce((g.valor ->> 'ativo')::boolean, false) THEN
    RETURN jsonb_build_object(
      'ativo', true, 'escopo', 'global', 'motivo', g.motivo, 'quem', g.atualizado_por,
      'desde', g.atualizado_em, 'retry_after_s', coalesce((g.valor ->> 'retry_after_s')::int, 300));
  END IF;
  IF p_tenant_id IS NOT NULL THEN
    SELECT * INTO t FROM plat.sistema WHERE chave = plat.modo_chave('inquilino', p_tenant_id);
    IF t.chave IS NOT NULL AND coalesce((t.valor ->> 'ativo')::boolean, false) THEN
      RETURN jsonb_build_object(
        'ativo', true, 'escopo', 'inquilino', 'tenant_id', p_tenant_id, 'motivo', t.motivo,
        'quem', t.atualizado_por, 'desde', t.atualizado_em,
        'retry_after_s', coalesce((t.valor ->> 'retry_after_s')::int, 300));
    END IF;
  END IF;
  RETURN jsonb_build_object('ativo', false);
END $$;

CREATE OR REPLACE FUNCTION plat.modo_bloqueia(p_tenant_id int) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS
  $$ SELECT coalesce((plat.modo_ler(p_tenant_id) ->> 'ativo')::boolean, false) $$;

-- ---------------------------------------------------------------- escrita (só pela CLI/worker; motivo SEMPRE obrigatório)
CREATE OR REPLACE FUNCTION plat.modo_ligar(p_escopo text, p_tenant_id int, p_motivo text, p_quem text,
                                           p_retry_after_s int DEFAULT 300) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE c text; v jsonb;
BEGIN
  IF p_motivo IS NULL OR btrim(p_motivo) = '' THEN
    RAISE EXCEPTION 'motivo obrigatório para ligar o modo de manutenção';
  END IF;
  IF p_quem IS NULL OR btrim(p_quem) = '' THEN
    RAISE EXCEPTION 'quem obrigatório para ligar o modo de manutenção';
  END IF;
  c := plat.modo_chave(p_escopo, p_tenant_id);
  IF p_escopo = 'inquilino' AND NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant_id) THEN
    RAISE EXCEPTION 'inquilino inexistente: %', p_tenant_id;
  END IF;
  v := jsonb_build_object('ativo', true, 'escopo', p_escopo, 'retry_after_s', greatest(p_retry_after_s, 1));
  IF p_escopo = 'inquilino' THEN v := v || jsonb_build_object('tenant_id', p_tenant_id); END IF;
  INSERT INTO plat.sistema(chave, valor, motivo, atualizado_por, atualizado_em)
  VALUES (c, v, btrim(p_motivo), p_quem, now())
  ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, motivo = EXCLUDED.motivo,
                                    atualizado_por = EXCLUDED.atualizado_por, atualizado_em = EXCLUDED.atualizado_em;
  INSERT INTO plat.sistema_trilha(chave, acao, valor, quem, motivo)
  VALUES (c, 'ligar', v, p_quem, btrim(p_motivo));
  RETURN plat.modo_ler(p_tenant_id);
END $$;

CREATE OR REPLACE FUNCTION plat.modo_desligar(p_escopo text, p_tenant_id int, p_motivo text, p_quem text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE c text; v jsonb;
BEGIN
  IF p_motivo IS NULL OR btrim(p_motivo) = '' THEN
    RAISE EXCEPTION 'motivo obrigatório para desligar o modo de manutenção (a trilha registra o porquê da volta)';
  END IF;
  IF p_quem IS NULL OR btrim(p_quem) = '' THEN
    RAISE EXCEPTION 'quem obrigatório para desligar o modo de manutenção';
  END IF;
  c := plat.modo_chave(p_escopo, p_tenant_id);
  v := jsonb_build_object('ativo', false, 'escopo', p_escopo);
  IF p_escopo = 'inquilino' THEN v := v || jsonb_build_object('tenant_id', p_tenant_id); END IF;
  -- a linha fica gravada com ativo=false: último estado conhecido, sem apagar histórico do motivo
  INSERT INTO plat.sistema(chave, valor, motivo, atualizado_por, atualizado_em)
  VALUES (c, v, btrim(p_motivo), p_quem, now())
  ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, motivo = EXCLUDED.motivo,
                                    atualizado_por = EXCLUDED.atualizado_por, atualizado_em = EXCLUDED.atualizado_em;
  INSERT INTO plat.sistema_trilha(chave, acao, valor, quem, motivo)
  VALUES (c, 'desligar', v, p_quem, btrim(p_motivo));
  RETURN plat.modo_ler(p_tenant_id);
END $$;

-- ---------------------------------------------------------------- job somente-leitura (exportação):
-- tipo declarado `somente_leitura` no registro Python (hoje catalogo.exportar_lista) não altera dado do
-- inquilino — só lê e materializa artefato — então atravessa o modo: a hipótese do item manda a exportação
-- continuar. A coluna congela a marca no momento da criação (mudança futura no registro não reabre fila).
ALTER TABLE plat.job ADD COLUMN IF NOT EXISTS somente_leitura boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------- pausa da fila: inquilino sob modo não tem pendente retirado
-- (o job em execução não é tocado: "termina ou pausa sem se perder", portão do L7-33); EXCETO o job
-- somente_leitura, que continua saindo da fila durante a manutenção.
CREATE OR REPLACE FUNCTION plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pego plat.job;
BEGIN
  PERFORM plat.via_worker_ligar();
  WITH c AS (
    SELECT j.id FROM plat.job j
    WHERE j.estado = 'pendente' AND j.agendado_para <= now()
      AND (p_pesado_ok OR NOT j.pesado)
      AND (j.somente_leitura OR NOT plat.modo_bloqueia(j.tenant_id))
      AND (j.chave IS NULL OR NOT EXISTS (SELECT 1 FROM plat.job r WHERE r.chave = j.chave AND r.estado = 'rodando'))
      AND (SELECT count(*) FROM plat.job r WHERE r.tenant_id = j.tenant_id AND r.estado = 'rodando')
          < plat.cota_jobs_simultaneos(j.tenant_id)
    ORDER BY j.prioridade, j.agendado_para, j.criado_em
    FOR UPDATE OF j SKIP LOCKED LIMIT 1)
  UPDATE plat.job SET estado = 'rodando', worker = p_worker, iniciado_em = now(), heartbeat_em = now(),
                      tentativa = tentativa + 1, progresso = 0, mensagem = NULL
  FROM c WHERE plat.job.id = c.id RETURNING plat.job.* INTO pego;
  PERFORM plat.via_worker_desligar();
  RETURN pego;
END $$;

-- ---------------------------------------------------------------- privilégios (mesmo padrão de plat.worker, migração 004):
-- tabelas de infraestrutura, acesso só por função; a 001 dá tudo a plat_app por privilégio padrão, então o
-- REVOKE tem de ser explícito. Ligar/desligar é operação de infra (CLI com a role do worker, nunca a API).
REVOKE ALL ON plat.sistema FROM PUBLIC, plat_app;
REVOKE ALL ON plat.sistema_trilha FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.modo_ligar(text, int, text, text, int) FROM PUBLIC, plat_app;
REVOKE EXECUTE ON FUNCTION plat.modo_desligar(text, int, text, text) FROM PUBLIC, plat_app;
GRANT EXECUTE ON FUNCTION plat.modo_ligar(text, int, text, text, int) TO plat_worker;
GRANT EXECUTE ON FUNCTION plat.modo_desligar(text, int, text, text) TO plat_worker;
GRANT EXECUTE ON FUNCTION plat.modo_ler(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.modo_bloqueia(int) TO plat_worker;
-- a CLI `plat modo --inquilino <slug>` resolve o slug pela mesma função pública da tela de login (003)
GRANT EXECUTE ON FUNCTION plat.tenant_publico(text) TO plat_worker;
