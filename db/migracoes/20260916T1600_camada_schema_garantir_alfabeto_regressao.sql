-- depende: 20260916T1100_recurso_partilhado_por_inquilino_regressao.sql
--
-- Conserto de regressão de fusão (tests/api/ingestao/test_slug_alfabeto.py, achado do adversário do
-- turno 3, itens L0-04-c/L0-04-ingest-vetor). Terceira vez que o alfabeto relaxado se perde: a
-- 20260906T1607_slug_ingestao_reconciliado.sql já tinha igualado `plat.camada_schema_garantir` ao CHECK
-- de `plat.tenant.slug` (migração 002: '^[a-z0-9][a-z0-9-]{1,38}$', hífen e dígito inicial válidos) mais
-- '_' por compatibilidade. A 20260907T0245 (isolamento de schema por instalação, achado F8) reescreveu a
-- função a partir do estado ANTERIOR à reconciliação e voltou ao alfabeto estrito
-- ('^[a-z][a-z0-9_]{0,60}$', sem hífen, sem dígito inicial). A 20260916T1100 (recurso partilhado por
-- inquilino) fundiu o prefixo de instalação com a trava de transação da 20260908T2210, mas também partiu
-- do estado anterior à reconciliação — carregou o alfabeto estrito de novo. Medido: todo slug com hífen
-- ou dígito inicial (ex. 'minha-org', '2024-prefeitura') é aceito na criação do inquilino e recusado com
-- `slug_invalido` na primeira ingestão — o inquilino nunca importa camada nenhuma.
--
-- Conserto: reaplica o alfabeto relaxado por CIMA da versão viva (prefixo de instalação + trava de
-- transação), em vez de reescrever a função do zero — preserva as duas defesas.
--
-- ATENÇÃO A QUEM JUNTAR RAMOS (repetida da 20260906T1607, porque já foi ignorada duas vezes): a
-- criação do inquilino (migração 002) é a AUTORIDADE do alfabeto do slug. Qualquer redefinição futura de
-- `plat.camada_schema_garantir` tem de manter '^[a-z0-9][a-z0-9_-]{1,60}$' (ou mais permissivo), nunca
-- menos. `tests/api/ingestao/test_slug_alfabeto.py` reprova a divergência — rodar antes de fundir.

CREATE OR REPLACE FUNCTION plat.camada_schema_garantir(p_slug text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  -- mesmo alfabeto do CHECK de plat.tenant.slug (migração 002), mais '_' por compatibilidade
  IF p_slug !~ '^[a-z0-9][a-z0-9_-]{1,60}$' THEN
    RAISE EXCEPTION 'slug_invalido';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE slug = p_slug AND id = plat.tenant_atual()) THEN
    RAISE EXCEPTION 'schema_de_outro_inquilino';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('plat:camada_schema_garantir:' || p_slug)::bigint);
  -- prefixo de instalação: sem ele produção, homologação e as trilhas partilhariam o mesmo d_<slug>
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION plat_app', plat.camada_schema_prefixo() || p_slug);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO plat_leitor', plat.camada_schema_prefixo() || p_slug);
END $$;
