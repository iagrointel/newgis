-- 20260906T2219_rede_administrar_regras: privilégio rede.administrar (item
-- L4-03-a-regras-de-conectividade; ADR docs/adr/20260906T2058-regras-de-conectividade.md).
--
-- Desligar a avaliação de regras (rede.regras_ativas, a comporta de carga em massa) e substituir o conjunto
-- inteiro de regras por CSV são atos de ADMIN DA REDE, separados do rede.editar do dia a dia: quem edita
-- feição não pode abrir a comporta nem trocar a lei que o protege. Administrativo (só o perfil admin tem por
-- padrão, como conteudo.ver_tudo). Espelho em app/auth/privilegios.py — o teste
-- tests/api/test_privilegios_declarados.py compara os dois, e docs/PRIVILEGIOS.md é regerado do banco.
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

INSERT INTO plat.privilegio(nome, grupo, descricao, administrativo) VALUES
  ('rede.administrar', 'rede',
   'ligar/desligar a avaliação de regras da rede e substituir o conjunto de regras por CSV', true)
ON CONFLICT (nome) DO NOTHING;

INSERT INTO plat.perfil_privilegio(perfil, privilegio) VALUES ('admin', 'rede.administrar')
ON CONFLICT DO NOTHING;
