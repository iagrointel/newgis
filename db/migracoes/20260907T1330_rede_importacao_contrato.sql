-- 20260907T1330_rede_importacao_contrato: a auditoria da importação BDGD passa a guardar, na
-- mesma linha, o relatório do contrato de dado (avaliado ANTES da carga), a unidade detectada do
-- COMP por camada e os três órfãos que o portão do item L4-01-c manda contar e listar.
-- Colunas novas, todas jsonb e opcionais: uma importação antiga continua válida com NULL.
ALTER TABLE plat.rede_importacao
  ADD COLUMN IF NOT EXISTS contrato jsonb,   -- {versao_contrato, avaliadas, total, bloqueia_falhas, resumo, expectativas[]}
  ADD COLUMN IF NOT EXISTS comp     jsonb,   -- {camada: {unidade, fator, razao_comp_sobre_geodesico, soma_*}}
  ADD COLUMN IF NOT EXISTS orfaos   jsonb;   -- {uc_sem_trafo, trafo_sem_ctmt, pac_sem_trecho: {quantidade, exemplos, explicacao}}

COMMENT ON COLUMN plat.rede_importacao.contrato IS
  'relatório do contrato de dado da BDGD (app/rede_utilidades/contrato.py sobre contrato_bdgd.yaml), avaliado antes da carga; item L4-01-c';
COMMENT ON COLUMN plat.rede_importacao.comp IS
  'unidade do COMP detectada pela razão Σ COMP / Σ geodésico por camada de trecho (metros ≈ 1, quilômetros ≈ 0,001); item L4-01-c';
COMMENT ON COLUMN plat.rede_importacao.orfaos IS
  'UC sem transformador, transformador sem alimentador e ponto de acoplamento sem trecho: quantidade, exemplos e explicação; item L4-01-c';
