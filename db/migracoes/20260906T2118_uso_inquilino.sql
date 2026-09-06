-- 20260906T2118_uso_inquilino: item L0-07-admin-org (console de administração do inquilino) — a fatia
-- "uso por período" que o portão do item pai exige na tela Administração (o item L0-07-c-cotas-uso, ainda
-- pendente, cobre a medição AMPLA: CPU de jobs, requisições por rota, reconciliação com o bucket; aqui fica
-- a série diária por inquilino que a tela e o relatório CSV consomem).
--
-- Decisões (ADR 20260906T2118-uso-inquilino):
--  * Um ponto por (inquilino, dia UTC): `plat.uso_inquilino` com PK (tenant_id, dia). Re-medir no mesmo dia
--    sobrescreve (UPSERT) — a série nunca acumula duas linhas por dia.
--  * `bytes_bucket` NÃO é medido em SQL: o contador mora no Garage (API admin HTTP), então quem mede
--    (a rota `GET /api/org/uso` sob demanda, ou o periódico `uso.medir_todos`) passa o valor já medido por
--    `app.objetos.uso(slug)`. Tudo o que é de banco a função mede sozinha.
--  * `bytes_banco` = `plat.tenant.uso_bytes` (contador de armazenamento de TABELA mantido pela ingestão
--    vetorial da 029 — o mesmo número que entra na cota), não uma soma nova de pg_total_relation_size:
--    medir relações d_<slug> a cada dia em toda tabela de feição é exatamente o custo que a série existe
--    para evitar na hora da tela.
--  * A função é SECURITY DEFINER (dono postgres, contorna RLS) porque o periódico roda sob o inquilino
--    técnico `plataforma` e mede TODOS os inquilinos ativos; a leitura da série pela tela NÃO usa a função
--    — é SELECT direto na tabela sob RLS (cada inquilino só lê a própria série).
--  * Sem GRANT para PUBLIC (regra P6): REVOKE explícito + GRANT só a plat_app, mesmo padrão da 048.

CREATE TABLE IF NOT EXISTS plat.uso_inquilino (
  tenant_id         int  NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  dia               date NOT NULL,
  bytes_bucket      bigint NOT NULL DEFAULT 0,   -- objetos no bucket Garage (medido em Python, vem no parâmetro)
  bytes_banco       bigint NOT NULL DEFAULT 0,   -- plat.tenant.uso_bytes (armazenamento de tabela, contador da 029)
  itens             int  NOT NULL DEFAULT 0,     -- itens do catálogo fora da lixeira
  itens_lixeira     int  NOT NULL DEFAULT 0,     -- lixeira CONTA na cota (refutação do L0-07-c), então entra na série
  usuarios_total    int  NOT NULL DEFAULT 0,     -- usuários com ativo = true (o número que a cota de usuários limita)
  usuarios_ativos   int  NOT NULL DEFAULT 0,     -- com ultimo_login nos últimos 30 dias (uso de verdade)
  jobs              int  NOT NULL DEFAULT 0,     -- jobs criados no dia
  requisicoes       int  NOT NULL DEFAULT 0,     -- linhas de plat.log_acesso do dia
  bytes_servidos    bigint NOT NULL DEFAULT 0,   -- soma de log_acesso.bytes do dia
  medido_em         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, dia)
);

ALTER TABLE plat.uso_inquilino ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_uso_inquilino ON plat.uso_inquilino;
CREATE POLICY p_uso_inquilino ON plat.uso_inquilino FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());

-- ---------------------------------------------------------------- medição de UM inquilino (hoje, UTC)
CREATE OR REPLACE FUNCTION plat.uso_medir(p_tenant int, p_bytes_bucket bigint)
RETURNS plat.uso_inquilino
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE r plat.uso_inquilino%ROWTYPE;
BEGIN
  INSERT INTO plat.uso_inquilino AS ui
    (tenant_id, dia, bytes_bucket, bytes_banco, itens, itens_lixeira, usuarios_total, usuarios_ativos,
     jobs, requisicoes, bytes_servidos, medido_em)
  SELECT t.id, (now() AT TIME ZONE 'UTC')::date, p_bytes_bucket, t.uso_bytes,
         (SELECT count(*) FROM plat.item i WHERE i.tenant_id = t.id AND i.apagado_em IS NULL),
         (SELECT count(*) FROM plat.item i WHERE i.tenant_id = t.id AND i.apagado_em IS NOT NULL),
         (SELECT count(*) FROM plat.usuario u WHERE u.tenant_id = t.id AND u.ativo),
         (SELECT count(*) FROM plat.usuario u WHERE u.tenant_id = t.id AND u.ativo
            AND u.ultimo_login > now() - interval '30 days'),
         (SELECT count(*) FROM plat.job j WHERE j.tenant_id = t.id
            AND j.criado_em >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),
         (SELECT count(*) FROM plat.log_acesso la WHERE la.tenant_id = t.id
            AND la.em >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),
         (SELECT coalesce(sum(la.bytes), 0) FROM plat.log_acesso la WHERE la.tenant_id = t.id
            AND la.em >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),
         now()
  FROM plat.tenant t WHERE t.id = p_tenant
  ON CONFLICT (tenant_id, dia) DO UPDATE SET
    bytes_bucket = EXCLUDED.bytes_bucket, bytes_banco = EXCLUDED.bytes_banco,
    itens = EXCLUDED.itens, itens_lixeira = EXCLUDED.itens_lixeira,
    usuarios_total = EXCLUDED.usuarios_total, usuarios_ativos = EXCLUDED.usuarios_ativos,
    jobs = EXCLUDED.jobs, requisicoes = EXCLUDED.requisicoes, bytes_servidos = EXCLUDED.bytes_servidos,
    medido_em = EXCLUDED.medido_em
  RETURNING * INTO r;
  RETURN r;
END $$;

-- ---------------------------------------------------------------- inquilinos ativos (para o periódico
-- cross-inquilino; a rota da tela NÃO usa — ela já está dentro do próprio inquilino por RLS)
CREATE OR REPLACE FUNCTION plat.uso_tenants_ativos()
RETURNS TABLE (id int, slug text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.id, t.slug FROM plat.tenant t WHERE t.ativo ORDER BY t.id
$$;

-- vocabulário de evento do relatório exportável (portão: "relatório de uso exportável")
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('org/uso_exportar', 'relatório de uso do inquilino exportado em CSV (série diária de plat.uso_inquilino)')
ON CONFLICT (nome) DO NOTHING;

DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.uso_medir(int, bigint)', 'plat.uso_tenants_ativos()'
  ] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
END $$;
