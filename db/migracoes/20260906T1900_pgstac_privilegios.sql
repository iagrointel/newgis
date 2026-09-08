-- 20260906T1900_pgstac_privilegios: privilégios de plat_app sobre o schema `pgstac` (item L1-01-a).
-- O pgstac é instalado por `pypgstac migrate` (db/pgstac_instalar.sh, chamado por db/migrar.sh), NUNCA por
-- migração SQL desta pasta — pypgstac cria o próprio schema `pgstac` (nome fixo, sem parâmetro) e os papéis
-- pgstac_admin/pgstac_read/pgstac_ingest. Esta migração só concede a plat_app o que ela precisa para ler e
-- gravar STAC (pgstac_read + pgstac_ingest), nunca pgstac_admin (que é dono dos objetos e pode alterar DDL).
-- Idempotente: se os papéis do pgstac ainda não existem, para com uma mensagem que diz o que rodar antes.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgstac_read')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgstac_ingest') THEN
    RAISE EXCEPTION 'papéis pgstac_read/pgstac_ingest inexistentes: rode antes `bash db/pgstac_instalar.sh` '
      '(pypgstac migrate) nesta base';
  END IF;
END $$;

GRANT pgstac_read TO plat_app;
GRANT pgstac_ingest TO plat_app;
-- nunca: GRANT pgstac_admin TO plat_app -- pgstac_admin é dono do schema/DDL do pgstac, fora do alcance da API
-- defesa em profundidade: se algum dia alguém conceder pgstac_admin por engano, a próxima aplicação desta
-- migração (idempotente) não desfaz sozinha, mas o teste de isolamento (tests/api/imagens) reprova a suíte.
