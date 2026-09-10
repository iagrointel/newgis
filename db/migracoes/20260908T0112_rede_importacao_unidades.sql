-- 20260908T0112_rede_importacao_unidades: a auditoria da importação BDGD passa a guardar a unidade
-- DECLARADA pelo dicionário e a unidade DETECTADA no arquivo, campo numérico por campo numérico, com o
-- fator que leva o valor à unidade da base (metro, quilowatt-hora). O `comp` da migração anterior
-- continua onde está (é a medida do COMP por camada, do item L4-01-c); `unidades` é o dicionário de
-- unidades da importação inteira, e é dele que o sumário por subrede e os exportadores leem o fator.
-- Coluna nova, jsonb e opcional: importação antiga segue válida com NULL, e quem lê cai na unidade
-- declarada dizendo que é declarada.
ALTER TABLE plat.rede_importacao
  ADD COLUMN IF NOT EXISTS unidades jsonb;  -- {campo: {familia, declarada, detectada, fator_para_base, base, origem, ...}}

COMMENT ON COLUMN plat.rede_importacao.unidades IS
  'unidade declarada x detectada por campo numérico do arquivo, com fator para a unidade da base; item L4-01-e';

-- O sumário por subrede (item L4-04-c) passa a gravar, ao lado dos números, a unidade com que eles foram
-- somados e de onde ela veio (medida no arquivo pela importação, ou não medida). Número somado sem dizer
-- em que unidade o arquivo estava é o defeito que este item conserta.
ALTER TABLE plat.rede_subrede_resumo
  ADD COLUMN IF NOT EXISTS unidades jsonb;  -- {comp: {...}, ene: {unidade_do_arquivo, base, fator_para_base, origem, declarada_no_dicionario}}

COMMENT ON COLUMN plat.rede_subrede_resumo.unidades IS
  'unidade do comprimento e da energia usada nas somas desta linha, com a origem (medida na importação x não medida); item L4-01-e';
