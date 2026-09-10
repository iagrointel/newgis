-- 20260910T2315_campo_capturado_em_texto (item L2-07-campo): `campo_visita.capturado_em` nasceu `timestamptz`
-- na migração 20260910T2245_campo.sql — errado pelo próprio desenho documentado no código (`app/campo/
-- servico.py`/`rotas.py`): é o relógio do APARELHO, mostrado ao usuário "tal qual veio", NUNCA usado para
-- ordenar ou decidir no servidor (quem manda é `recebido_em`, esse sim timestamptz do relógio do servidor).
-- Guardar como timestamptz reescreve o valor (fuso, formatação) e quebra exatamente a garantia que o item
-- pede: um aparelho com o relógio errado não pode alterar NADA além do que é exibido no próprio campo.
-- Achado pelo teste `tests/api/test_campo.py::test_visita_relogio_do_aparelho_nao_e_usado_para_decidir` (a
-- serialização da rota nem convertia o datetime de volta — 500 antes deste fix). Idempotente. Sem BEGIN/COMMIT.
ALTER TABLE plat.campo_visita ALTER COLUMN capturado_em TYPE text USING capturado_em::text;
ALTER TABLE plat.campo_visita DROP CONSTRAINT IF EXISTS campo_visita_capturado_em_check;
ALTER TABLE plat.campo_visita ADD CONSTRAINT campo_visita_capturado_em_check
  CHECK (btrim(capturado_em) <> '' AND length(capturado_em) <= 40);
