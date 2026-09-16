-- reaplicavel
-- 20260916T1145_rede_associacao_conectividade_nullable: `plat.rede_associacao` tem dois desenhos
-- coexistindo desde a "entrega 10/09" descrita em 20260906T2058_rede_regras_conectividade.sql — o de
-- FEIÇÃO (`de_feicao_id`/`para_feicao_id` NOT NULL, `tipo IN ('contencao','estrutura')`, criado por
-- 2058) e o de NÓ/ARESTA (`de_no_id`/`para_no_id`/`para_aresta_id`/`origem`, ADITADO por
-- 20260906T2126_rede_modelo_elementos.sql, que roda DEPOIS de 2058 na ordem de carimbo — 21:26 > 20:58
-- — e cuja própria `CREATE TABLE IF NOT EXISTS` nunca executa porque a tabela já existe). A união ficou
-- incompleta em dois pontos:
--
-- 1. `de_feicao_id`/`para_feicao_id` continuam NOT NULL: nenhuma associação no desenho de NÓ/ARESTA
--    (importador BDGD — `app/rede_utilidades/bdgd.py::_gravar_associacoes` — e importador OSM —
--    `app/rede_utilidades/osm_power.py`) consegue gravar, porque essas linhas não têm feição, só nó/
--    aresta. Medido ao vivo: `psycopg2.errors.NotNullViolation: null value in column "de_feicao_id"`
--    na primeira associação de qualquer importação BDGD (`tests/api/test_rede_unidades_bdgd.py`,
--    `tests/api/test_rede_bdgd_job.py`, `tests/api/test_rede_modelo.py`).
-- 2. `rede_associacao_tipo_check` só aceita ('contencao', 'estrutura') — o vocabulário do desenho de
--    FEIÇÃO (item L4-03-a). O desenho de NÓ/ARESTA usa 'conectividade' (bdgd.py, osm_power.py) e
--    'fixacao' (osm_power.py, nome do 2126 antes da renomeação para 'estrutura' em 2058) — nenhum dos
--    dois é aceito hoje.
--
-- Ajuste: união estrita dos dois vocabulários (nunca remove valor aceito, só acrescenta); e as duas
-- colunas de feição voltam a nullable, exatamente como as colunas irmãs de nó/aresta já são — a
-- obrigatoriedade de exatamente um par (feição×feição OU nó/aresta×nó) fica para a aplicação (nenhuma
-- linha do importador BDGD/OSM jamais teve `de_feicao_id` para começo de conversa; o desenho de
-- FEIÇÃO, ainda não integrado a bdgd.py, continua preenchendo as duas colunas normalmente).
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

ALTER TABLE plat.rede_associacao ALTER COLUMN de_feicao_id DROP NOT NULL;
ALTER TABLE plat.rede_associacao ALTER COLUMN para_feicao_id DROP NOT NULL;

ALTER TABLE plat.rede_associacao DROP CONSTRAINT IF EXISTS rede_associacao_tipo_check;
ALTER TABLE plat.rede_associacao ADD CONSTRAINT rede_associacao_tipo_check
  CHECK (tipo IN ('conectividade', 'contencao', 'estrutura', 'fixacao'));
