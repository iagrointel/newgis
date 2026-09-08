-- 20260908T0500_funcoes_leitor_sem_public: quatro funções da 20260906T1546_leitor_tiles.sql (JÁ APLICADA nas
-- trilhas da linhagem do mapa — por isso REVOKE aqui, não edição dela) ficaram com EXECUTE para PUBLIC, o padrão
-- do Postgres para função nova: plat.escopo_cobre, plat.ip_permitido, plat.origem_permitida e plat.papel_leitor.
-- A regra da casa (011_catalogo.sql; teste tests/api/catalogo/test_eventos_e_seguranca.py::
-- test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app) é nenhuma função do schema plat executável
-- por PUBLIC. Quem precisa delas: a aplicação (políticas e checagem de token/restrição), o worker e o papel de
-- leitura de tiles (a política de RLS das camadas usa papel_leitor/escopo_cobre sob esse papel).
REVOKE EXECUTE ON FUNCTION plat.escopo_cobre(text[], text, uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.ip_permitido(text, jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.origem_permitida(text, jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.papel_leitor() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.escopo_cobre(text[], text, uuid), plat.ip_permitido(text, jsonb),
  plat.origem_permitida(text, jsonb), plat.papel_leitor() TO plat_app, plat_worker, plat_leitor;
