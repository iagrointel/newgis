-- 20260908T0600_funcoes_linhagem_mapa_sem_public: cinco funções da linhagem do mapa (20260907T0141_exportacao_camada,
-- 20260907T1655_anotacao_feicao, 20260907T1922_tabela_atributos — JÁ APLICADAS nas trilhas; por isso REVOKE aqui) ficaram
-- com EXECUTE para PUBLIC, o padrão do Postgres para função nova. Regra da casa (011_catalogo.sql; teste
-- tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app):
-- nenhuma função do schema plat executável por PUBLIC. Mesma classe de conserto da 20260908T0500 (funções de tile).
REVOKE EXECUTE ON FUNCTION plat.exportacao_estado_final_imutavel() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.exportacoes_em_curso(integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.exportacoes_expirar_candidatos() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tg_anotacao_feicao() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION plat.tg_tabela_vista_atualizado_em() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.exportacoes_em_curso(integer), plat.exportacoes_expirar_candidatos() TO plat_app, plat_worker;
