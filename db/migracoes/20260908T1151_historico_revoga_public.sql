-- 20260908T1151_historico_revoga_public: `plat.feicao_historico_registrar()` sem EXECUTE para PUBLIC.
--
-- Achado ao rodar `tests/api/catalogo/test_eventos_e_seguranca.py` neste ramo (item L2-07-e, que juntou o ramo
-- do L2-07-b como dependência): a função de gatilho nasceu em 20260907T1025_historico_feicao.sql e foi
-- RECRIADA por 20260907T2020_historico_geom_nula.sql. `CREATE OR REPLACE FUNCTION` devolve a função ao ACL
-- padrão do Postgres, que é EXECUTE para PUBLIC — a segunda migração desfez, sem querer, o que a primeira
-- deixava certo. Regra da casa (visível em 036 e no gerador de camadas do Martin): nenhuma função de `plat`
-- fica executável por PUBLIC.
--
-- Só REVOKE: é função de GATILHO, disparada pelo dono da tabela, e portanto não precisa de GRANT para plat_app.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- depende: 20260907T2020_historico_geom_nula.sql

REVOKE ALL ON FUNCTION plat.feicao_historico_registrar() FROM PUBLIC;
