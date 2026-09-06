-- 024_arquivos_revoke_public: as 4 funções de plat.arquivo_bucket_* nasceram (022) com EXECUTE para PUBLIC —
-- achado do testador (tests/api/test_funcoes_seguras.py e
-- tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app):
-- o default privilege de 003/006 ("funções novas no schema plat nascem sem EXECUTE para PUBLIC") não se aplicou
-- (MEDIDO: uma função criada agora mesmo por postgres em plat, do zero, ainda sai com `=X/postgres` no ACL, apesar
-- de `pg_default_acl` não ter PUBLIC para (postgres, plat, function) — o mesmo padrão que 010/012/013/016/019 já
-- tratam com REVOKE explícito por função, redundante ao default privilege). Segue o mesmo padrão; idempotente (REVOKE sem privilégio concedido não erra).
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_resolver(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_por_tenant(int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_registrar(int, text, text, text, text, text, text, bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.arquivo_bucket_cota_atualizar(int, bigint) FROM PUBLIC;
