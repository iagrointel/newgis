-- 20260915T2252_vulnerabilidade (item L7-03-f-dependencias-cve-log-correcoes; docs/SEGURANCA.md seção 7.6):
-- fecha a parte "sem plat.vulnerabilidade" do bloqueio registrado em laco/estado.json. Duas tabelas:
--
--   plat.varredura_cve    — uma linha por EXECUÇÃO do job `seguranca.varrer_cve` (app/jobs/seguranca.py) ou
--                           do script standalone (scripts/varredura_cve.py, chamado por
--                           deploy/plat-varredura-cve.timer): quando, rc (0 = todas as fontes tentadas
--                           rodaram; 2 = alguma fonte não rodou — sem rede, binário ausente etc.), duração e
--                           um resumo textual por fonte (nunca "0 CVE" fingido quando a fonte não rodou).
--   plat.vulnerabilidade  — uma linha por achado (pip-audit ou npm-audit); NUNCA apagada: quando o mesmo
--                           pacote/id some de uma varredura para a próxima (corrigido), `resolvida_em` é
--                           preenchido — é esse campo que faz `docs/gerar_correcoes.py` renderizar o "log de
--                           correções" que a spec promete. Um índice único parcial garante no máximo UMA
--                           linha ABERTA (resolvida_em IS NULL) por (fonte, pacote, id_cve); se o mesmo
--                           achado voltar depois de resolvido (regressão), a linha só é reaberta pela
--                           função abaixo (nunca duas linhas abertas ao mesmo tempo para o mesmo achado).
--
-- Sem tenant_id de propósito (como plat.status_amostra, 20260907T2233): dependência de requirements.txt e
-- de web/vendor/VERSOES.txt é da INSTALAÇÃO, não de um inquilino. plat_app só LÊ (GRANT SELECT); toda
-- escrita passa por plat.varredura_cve_registrar(), SECURITY DEFINER — mesmo desenho de
-- plat.status_amostrar. Idempotente; sem BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS plat.varredura_cve (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  quando      timestamptz NOT NULL DEFAULT now(),
  fonte       text NOT NULL DEFAULT 'pip-audit+npm-audit',
  rc          int NOT NULL,
  duracao_ms  int NOT NULL CHECK (duracao_ms >= 0),
  resumo      text NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_varredura_cve_quando ON plat.varredura_cve (quando DESC);
REVOKE ALL ON TABLE plat.varredura_cve FROM PUBLIC;
GRANT SELECT ON plat.varredura_cve TO plat_app;

CREATE TABLE IF NOT EXISTS plat.vulnerabilidade (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fonte                text NOT NULL CHECK (fonte IN ('pip-audit', 'npm-audit')),
  pacote               text NOT NULL,
  versao               text NOT NULL,
  id_cve               text NOT NULL,
  gravidade            text NOT NULL CHECK (gravidade IN ('critica', 'alta', 'media', 'baixa', 'desconhecida')),
  corrigido_em_versao  text,
  detectada_em         timestamptz NOT NULL DEFAULT now(),
  resolvida_em         timestamptz,
  varredura_id         bigint NOT NULL REFERENCES plat.varredura_cve(id),
  CONSTRAINT ck_vulnerabilidade_resolvida_apos_detectada CHECK (resolvida_em IS NULL OR resolvida_em >= detectada_em)
);
-- só uma linha ABERTA por achado; uma linha resolvida fica de fora do índice e vira histórico
CREATE UNIQUE INDEX IF NOT EXISTS ux_vulnerabilidade_aberta ON plat.vulnerabilidade (fonte, pacote, id_cve)
  WHERE resolvida_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_vulnerabilidade_resolvida_em ON plat.vulnerabilidade (resolvida_em);
CREATE INDEX IF NOT EXISTS ix_vulnerabilidade_detectada_em ON plat.vulnerabilidade (detectada_em DESC);
REVOKE ALL ON TABLE plat.vulnerabilidade FROM PUBLIC;
GRANT SELECT ON plat.vulnerabilidade TO plat_app;

-- Grava uma execução e faz o upsert dos achados: abre linha nova (ou atualiza a aberta que já existia para
-- o mesmo fonte/pacote/id_cve), e fecha (resolvida_em = now()) toda linha aberta de uma fonte que RODOU
-- nesta execução (p_fontes_ok) e cujo achado não apareceu mais — nunca fecha achado de uma fonte que não
-- rodou (sem rede não pode "corrigir" nada por ausência de dado). Devolve o id da varredura.
CREATE OR REPLACE FUNCTION plat.varredura_cve_registrar(
  p_rc int, p_duracao_ms int, p_resumo text, p_achados jsonb, p_fontes_ok text[] DEFAULT '{}'::text[],
  p_fonte text DEFAULT 'pip-audit+npm-audit'
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE v_id bigint; a jsonb;
BEGIN
  INSERT INTO plat.varredura_cve (fonte, rc, duracao_ms, resumo)
    VALUES (p_fonte, p_rc, p_duracao_ms, p_resumo)
    RETURNING id INTO v_id;

  FOR a IN SELECT * FROM jsonb_array_elements(coalesce(p_achados, '[]'::jsonb)) LOOP
    INSERT INTO plat.vulnerabilidade (fonte, pacote, versao, id_cve, gravidade, corrigido_em_versao, varredura_id)
    VALUES (a->>'fonte', a->>'pacote', a->>'versao', a->>'id_cve', a->>'gravidade', a->>'corrigido_em_versao', v_id)
    ON CONFLICT (fonte, pacote, id_cve) WHERE resolvida_em IS NULL
    DO UPDATE SET versao = EXCLUDED.versao, gravidade = EXCLUDED.gravidade,
                  corrigido_em_versao = EXCLUDED.corrigido_em_versao, varredura_id = EXCLUDED.varredura_id;
  END LOOP;

  IF array_length(p_fontes_ok, 1) > 0 THEN
    UPDATE plat.vulnerabilidade v
       SET resolvida_em = now()
     WHERE v.resolvida_em IS NULL
       AND v.fonte = ANY (p_fontes_ok)
       AND NOT EXISTS (
         SELECT 1 FROM jsonb_array_elements(coalesce(p_achados, '[]'::jsonb)) a2
          WHERE a2->>'fonte' = v.fonte AND a2->>'pacote' = v.pacote AND a2->>'id_cve' = v.id_cve
       );
  END IF;

  RETURN v_id;
END $$;
REVOKE EXECUTE ON FUNCTION plat.varredura_cve_registrar(int, int, text, jsonb, text[], text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.varredura_cve_registrar(int, int, text, jsonb, text[], text) TO plat_app;

-- Resumo agregado para a página /status (item L0-06-e-status): só contagem e o retrato da última execução —
-- nunca pacote, versão nem CVE individual numa rota sem sessão. Sempre 1 linha (as duas primeiras colunas são
-- subconsultas escalares: NULL/0 quando ainda não rodou nenhuma varredura, nunca "sem linha").
CREATE OR REPLACE FUNCTION plat.status_vulnerabilidades()
RETURNS TABLE (abertas int, ultima_em timestamptz, ultimo_rc int, fonte text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT (SELECT count(*)::int FROM plat.vulnerabilidade WHERE resolvida_em IS NULL),
         (SELECT quando FROM plat.varredura_cve ORDER BY quando DESC LIMIT 1),
         (SELECT rc FROM plat.varredura_cve ORDER BY quando DESC LIMIT 1),
         (SELECT fonte FROM plat.varredura_cve ORDER BY quando DESC LIMIT 1)
$$;
REVOKE EXECUTE ON FUNCTION plat.status_vulnerabilidades() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.status_vulnerabilidades() TO plat_app;
