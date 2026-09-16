-- depende: 20260906T2124_cotas_uso.sql
--
-- Conserto (achado em tests/api/jobs/test_jobs_periodicos.py::test_cada_periodico_registrado_dispara_uma_vez_com_dois_relogios[3],
-- periódico "medição de uso diária" / jobs.uso_medir): `plat.uso_medir(p_tenant, p_dia, p_bytes_bucket)` foi
-- desenhada para NULL em `p_bytes_bucket` significar "preserva a medição anterior" quando o Garage está fora
-- do ar ou o inquilino não tem bucket (app/jobs/periodicos.py::jobs_uso_medir, docstring). O ramo `ON CONFLICT
-- DO UPDATE` já faz isso (`coalesce(EXCLUDED.bytes_bucket, u.bytes_bucket)`), mas o `INSERT` inicial usava
-- `p_bytes_bucket` cru — na PRIMEIRA medição de um inquilino (sem linha anterior para preservar) isso grava
-- NULL numa coluna NOT NULL e o job falha com NotNullViolation. Medido: reproduz sempre que o periódico mede
-- um inquilino pela primeira vez sem bucket (qualquer inquilino de teste novo, e todo inquilino sem Garage
-- configurado).
--
-- Conserto: `coalesce(p_bytes_bucket, 0)` só no INSERT (sem linha anterior, 0 é o piso honesto); o
-- comportamento de UPDATE (preservar o valor anterior quando NULL) não muda.

CREATE OR REPLACE FUNCTION plat.uso_medir(p_tenant int, p_dia date, p_bytes_bucket bigint DEFAULT NULL)
RETURNS SETOF plat.uso_inquilino LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE
  v_banco bigint; v_itens int; v_lixeira int; v_ativos int; v_jobs int; v_tempo bigint; v_req bigint; v_bytes bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM plat.tenant WHERE id = p_tenant) THEN
    RAISE EXCEPTION 'inquilino_inexistente';
  END IF;
  v_banco := plat.uso_bytes_banco(p_tenant);
  SELECT count(*) FILTER (WHERE apagado_em IS NULL), count(*) FILTER (WHERE apagado_em IS NOT NULL)
    INTO v_itens, v_lixeira FROM plat.item WHERE tenant_id = p_tenant;
  SELECT count(DISTINCT usuario_id) INTO v_ativos
  FROM plat.log_acesso
  WHERE tenant_id = p_tenant AND usuario_id IS NOT NULL
    AND em >= (p_dia - 29)::timestamptz AND em < (p_dia + 1)::timestamptz;
  SELECT count(*) INTO v_jobs
  FROM plat.job
  WHERE tenant_id = p_tenant AND criado_em >= p_dia::timestamptz AND criado_em < (p_dia + 1)::timestamptz;
  SELECT coalesce(sum(EXTRACT(EPOCH FROM (terminado_em - iniciado_em)) * 1000), 0)::bigint INTO v_tempo
  FROM plat.job
  WHERE tenant_id = p_tenant AND terminado_em IS NOT NULL AND iniciado_em IS NOT NULL
    AND terminado_em >= p_dia::timestamptz AND terminado_em < (p_dia + 1)::timestamptz;
  SELECT count(*), coalesce(sum(bytes), 0)::bigint INTO v_req, v_bytes
  FROM plat.log_acesso
  WHERE tenant_id = p_tenant AND em >= p_dia::timestamptz AND em < (p_dia + 1)::timestamptz;
  INSERT INTO plat.uso_inquilino AS u
    (tenant_id, dia, bytes_banco, bytes_bucket, itens, itens_lixeira, usuarios_ativos_30d, jobs, job_tempo_ms,
     requisicoes, bytes_servidos, medido_em)
  VALUES
    (p_tenant, p_dia, v_banco, coalesce(p_bytes_bucket, 0), v_itens, v_lixeira, v_ativos, v_jobs, v_tempo, v_req, v_bytes, now())
  ON CONFLICT (tenant_id, dia) DO UPDATE SET
    bytes_banco = EXCLUDED.bytes_banco,
    bytes_bucket = coalesce(EXCLUDED.bytes_bucket, u.bytes_bucket),
    itens = EXCLUDED.itens, itens_lixeira = EXCLUDED.itens_lixeira,
    usuarios_ativos_30d = EXCLUDED.usuarios_ativos_30d,
    jobs = EXCLUDED.jobs, job_tempo_ms = EXCLUDED.job_tempo_ms,
    requisicoes = EXCLUDED.requisicoes, bytes_servidos = EXCLUDED.bytes_servidos,
    medido_em = EXCLUDED.medido_em;
  -- reconciliação do contador transacional de tabelas com o tamanho físico medido; nunca durante uma carga
  -- (a 029 reserva em uso_reservado_bytes e acerta uso_bytes no fim — mexer no meio cobraria duas vezes)
  UPDATE plat.tenant SET uso_bytes = v_banco
  WHERE id = p_tenant AND uso_bytes IS DISTINCT FROM v_banco
    AND NOT EXISTS (SELECT 1 FROM plat.importacao WHERE tenant_id = p_tenant
                    AND estado IN ('confirmada', 'carregando'));
  RETURN QUERY SELECT * FROM plat.uso_inquilino WHERE tenant_id = p_tenant AND dia = p_dia;
END $$;
