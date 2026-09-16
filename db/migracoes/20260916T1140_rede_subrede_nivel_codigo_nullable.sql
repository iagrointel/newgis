-- reaplicavel
-- 20260916T1140_rede_subrede_nivel_codigo_nullable: `plat.rede_subrede.nivel`/`codigo_externo` continuam
-- NOT NULL de antes da unificação (item L4-04-c-unificar-subrede, migração 20260908T0152_rede_subrede_
-- unificada.sql). Aquela migração pressupôs uma base onde essas colunas ainda não existiam
-- (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS nivel smallint` — sem NOT NULL, ou seja, nullable por
-- padrão), mas numa base onde `plat.rede_subrede_bdgd` já tinha sido promovida a `plat.rede_subrede`
-- ANTES da unificação (com `nivel`/`codigo_externo` NOT NULL desde a criação original da tabela pelo
-- item L4-04-c em 80ca4db98, antes de existir a distinção de origem), o `ADD COLUMN IF NOT EXISTS` é
-- NO-OP e a constraint antiga persiste.
--
-- Consequência medida ao vivo: `plat.rede_subrede_forma_da_origem` exige `origem = 'controlador' AND
-- nivel IS NULL` para toda subrede DERIVADA do controlador (a maioria do uso da tabela — controladores.py,
-- item L4-04-a), mas a coluna `nivel` sendo NOT NULL torna essa forma IMPOSSÍVEL DE GRAVAR: toda
-- `INSERT INTO plat.rede_subrede(tenant_id, rede_id, tier_id, nome)` (sem nivel/codigo_externo, como
-- `app/rede_utilidades/controladores.py` sempre fez) falha com `NotNullViolation`, reproduzido em
-- `tests/api/test_rede_subredes.py` (11/11 testes).
--
-- Único ajuste: relaxar as duas colunas para o nullable que a migração 20260908T0152 já pretendia (a
-- CHECK `rede_subrede_forma_da_origem`, inalterada, continua sendo a única regra de obrigatoriedade —
-- nivel/codigo_externo obrigatórios quando origem='bdgd', proibidos quando origem='controlador').
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.rede_subrede ALTER COLUMN nivel DROP NOT NULL;
ALTER TABLE plat.rede_subrede ALTER COLUMN codigo_externo DROP NOT NULL;
