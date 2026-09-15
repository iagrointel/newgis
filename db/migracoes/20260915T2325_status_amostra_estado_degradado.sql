-- reaplicavel
-- 20260915T2325_status_amostra_estado_degradado (achado L7-03-f, item B).
-- depende: 20260907T2233_status_amostra.sql
--
-- Causa medida na trilha `uniao`: `db/migracoes/20260906T2126_backup_status.sql` criou
-- `plat.status_amostra` PRIMEIRO, com `CHECK (estado IN ('ok', 'erro', 'ausente'))` (sem 'degradado').
-- `db/migracoes/20260907T2233_status_amostra.sql`, escrita depois, redefine a MESMA tabela com
-- `CHECK (estado IN ('ok','degradado','erro','ausente'))` — mas usa `CREATE TABLE IF NOT EXISTS`, que é
-- NO-OP quando a tabela já existe. Essa migração soma `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para
-- unir as duas colunas (`em` + `criado_em`), mas não tem o `ALTER ... DROP/ADD CONSTRAINT` equivalente
-- para o CHECK — por isso a trilha `uniao` (onde a 20260906 rodou primeiro) ficou presa na constraint
-- antiga, mesmo com o arquivo em disco já pedindo 'degradado'. Não é migração aplicada editada depois:
-- é uma segunda migração que redeclara a mesma tabela sem reconciliar esta constraint específica.
-- `app/status.py` grava 'degradado' (banco com fila pendente) e `tests/api/test_status.py::
-- test_percentual_do_mes_bate_com_as_amostras` grava a amostra sintética com esse estado — falha com
-- CheckViolation enquanto a trilha carregar a constraint de 20260906.
--
-- Conserto reprodutível: NUNCA editar a migração antiga (regra da casa) — recriar a constraint aqui,
-- idempotente (DROP IF EXISTS + ADD), com os 4 estados que o resto do sistema já usa.

ALTER TABLE plat.status_amostra DROP CONSTRAINT IF EXISTS status_amostra_estado_check;
ALTER TABLE plat.status_amostra
  ADD CONSTRAINT status_amostra_estado_check CHECK (estado IN ('ok', 'degradado', 'erro', 'ausente'));
