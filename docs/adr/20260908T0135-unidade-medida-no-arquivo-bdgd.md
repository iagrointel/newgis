# ADR 20260908T0135 — a unidade dos campos numéricos da BDGD é medida no arquivo, não lida do dicionário

Item `L4-01-e-dicionario-unidades-bdgd`. Estado: aceita.

## Contexto

O dicionário do pacote `eletrica-br` declarava `COMP` em quilômetro e `ENE_SUM` em megawatt-hora, porque é
o que o Módulo 10 da ANEEL escreve. O extrato de referência da casa traz os dois em metro e em
quilowatt-hora: o item L4-01-c mediu a razão entre o `COMP` somado e o comprimento geodésico do mesmo trecho
(1,024, ou seja, metro) e o item L4-04-c somou energia por unidade consumidora com a ordem de grandeza de
quilowatt-hora. Ou seja, a unidade não é fixada pela BDGD — é escolha de quem extraiu o arquivo.

Enquanto a unidade era assumida do dicionário, dois erros de mil vezes moravam no código: o exportador
OpenDSS multiplicava `ENE_SUM` por mil (assumindo megawatt-hora) e, no mesmo arquivo, usava `ENE_01..12`
como se fosse quilowatt-hora; o sumário por subrede somava `comp` como se fosse metro sem nada que o
dissesse.

## Decisão

1. A unidade é MEDIDA na importação, por campo numérico, contra uma régua que não vem do arquivo:
   comprimento pela razão com o comprimento geodésico da própria geometria; energia pela ordem de grandeza
   contra a potência instalada dos transformadores (Σ POT_NOM × 8.760 h) e contra o número de unidades
   consumidoras. As duas âncoras da energia têm de concordar quando as duas existem.
2. O resultado é GRAVADO na auditoria da importação (`plat.rede_importacao.unidades`), campo a campo, com a
   unidade declarada, a detectada, o fator para a unidade da base e a evidência da medida.
3. Quem soma ou exporta LÊ de lá (`unidades.fatores_da_rede`): sumário por subrede e exportador OpenDSS.
   O dicionário do pacote passa a dizer, nesses campos, "unidade do arquivo, detectada", e a nota de origem
   guarda o que a ANEEL declara.
4. Sem medida (rede sem importação registrada, camada sem a coluna, âncoras em conflito) NADA é convertido:
   fator 1 e `origem: nao_medida` escrito ao lado do número. Aplicar o fator do dicionário nesse caso seria
   o erro que este ADR existe para evitar.

## Consequências

- Um número somado ou exportado sempre vem com a unidade e a origem dela ao lado (coluna `unidades` do
  sumário, bloco `unidades` do `resumo.json` do circuito e da exportação de subrede).
- O carimbo de conclusão da importação passou a ser `clock_timestamp()`: duas importações da mesma rede na
  mesma transação teriam o mesmo `now()` e "a última importação" ficaria indefinida.
- Fronteira honesta: o exportador EPANET ainda não existe na plataforma. O que existe hoje do lado da água é
  a exportação de subrede em JSON, e ela passou a carregar o mesmo bloco `unidades` — quem escrever o
  conversor EPANET lê a unidade de lá, não do dicionário.
