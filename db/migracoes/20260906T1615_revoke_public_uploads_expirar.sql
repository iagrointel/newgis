-- Fecha EXECUTE para PUBLIC em toda função do schema plat (item L0-02-tenant-auth, cláusula herdada do T1:
-- "toda função SECURITY DEFINER ... EXECUTE só para plat_app"; o teste
-- tests/api/test_funcoes_seguras.py::test_nenhuma_funcao_com_execute_para_public cobre TODAS as funções).
--
-- MEDIDO 06/09/2026 no schema plat: 7 funções estavam com EXECUTE para PUBLIC —
-- plat.uploads_expirar_candidatos (SECURITY DEFINER, migração 046), plat.upload_reservado_bytes (046),
-- plat.tg_conexao_atualizado_em (030) e as quatro plat.amc_*_guarda/amc_versao_imutavel. Todas nasceram com
-- `GRANT EXECUTE ... TO plat_app` mas SEM o `REVOKE EXECUTE ... FROM PUBLIC` que é o padrão da casa
-- (010_jobs_gatilhos_execute.sql, 016_catalogo_apagar_usuario.sql, 033_ingestao_funcoes_privilegios.sql):
-- `CREATE FUNCTION` dá EXECUTE a PUBLIC por padrão e o ALTER DEFAULT PRIVILEGES da fundação não alcança isso.
--
-- Correção em arquivo NOVO (046 e 030 já estão aplicadas; editar arquivo aplicado faz migrar.sh parar com
-- código 3). O laço é genérico de propósito: fecha o que existir NESTA base, sem depender de qual trilha já
-- aplicou a sua migração — nenhuma linha some se a função não existir. Só o privilégio de PUBLIC é retirado;
-- os GRANT nominais (plat_app, plat_worker) ficam intactos. Função de gatilho não perde nada com isso: o
-- PostgreSQL cobra EXECUTE da função de gatilho em CREATE TRIGGER, não a cada disparo.
DO $$
DECLARE f record;
BEGIN
  FOR f IN
    SELECT p.oid::regprocedure AS assinatura
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'plat'
      AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%'))
  LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f.assinatura);
  END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION plat.uploads_expirar_candidatos(int) TO plat_app;
GRANT EXECUTE ON FUNCTION plat.upload_reservado_bytes(int) TO plat_app;
