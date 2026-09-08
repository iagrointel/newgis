"""Motor multicritério (AMC) — linha L3. Itens L3-01-a (modelo de dado: `plat.amc_modelo`, `amc_modelo_versao`,
`amc_conjunto_unidade`, `amc_unidade`, `amc_execucao`, `amc_fator_bruto`, `amc_resultado`; migração 045) e L3-01-b
(conjunto de unidades: grade hexagonal/quadrada em UTM SIRGAS 2000 da zona do centróide, ou feições do usuário).
Decisões de conceito: laco/decomposicao/L3L6_CONCEITO.md parte A; ADR 0016. Linguagem do produto: fator → critério →
favorabilidade 0-100 → pesos escolhidos pelo usuário (não medidos); veto zera com motivo; NULL = sem dado, nunca 0."""

# versão do MOTOR gravada em toda execução (A10): muda quando extrator/transformação/combinador mudam de resultado
MOTOR_VERSAO = "amc/0.1"
