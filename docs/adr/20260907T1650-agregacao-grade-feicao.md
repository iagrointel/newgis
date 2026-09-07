# ADR 20260907T1650 — agregação de grade para feição (item L3-07-agregacao)

## Contexto

O motor multicritério calcula favorabilidade por CÉLULA de grade (`plat.amc_unidade` +
`plat.amc_resultado`, itens L3-01-b/e). Este item leva esse resultado a uma FEIÇÃO qualquer
(imóvel, lote, município, setor censitário — qualquer polígono do usuário) por interseção
geométrica ponderada por área, e o caminho inverso (feição -> células) para exibir a composição.
O portão exige reproduzir `cbre.imoveis_fav` (piloto real, 4.346 feições) com |Δ| ≤ 0,5 em
≥ 99,5 % dos casos, contra `cbre.hex_fav`/`cbre.hex` calculados por `cbre/pipeline/85_fatores.sql`.

## Decisão 1 — o núcleo é uma consulta SQL parametrizada por DUAS sub-consultas, não uma função Python sobre geometria

`app/amc/agregacao.py::agregar()` recebe `feicoes_sql`/`celulas_sql` já prontas (cada uma
devolvendo linhas num formato fixo: id, geometria no CRS de trabalho, e para célula também
veto/motivo/fatores em jsonb) e faz UMA consulta com `ST_Intersects`/`ST_Area`/`ST_Intersection`
no PostGIS — nunca reimplementando geometria em shapely/Python. Isso deixa o MESMO motor servir
três fontes diferentes sem duplicar a conta: a execução real do produto
(`celulas_de_execucao_sql`), casos sintéticos de teste (`feicoes_de_geojson`/`celulas_de_geojson`,
via `unnest`) e a comparação com `cbre.hex_fav`/`cbre.imoveis_candidatos` que prova o portão (SQL
literal, direto nas tabelas do piloto, só leitura). Escala medida: 4.346 feições × 73.115 células
em ≈ 4,5-22 s dependendo da carga da máquina (`tests/medidas/L3-07-agregacao.json`).

## Decisão 2 — a "média por fator" opera sobre valores JÁ TRANSFORMADOS (nota 0-100), nunca sobre o valor bruto

O esquema do modelo (`docs/esquemas/amc_modelo.v1.json`) separa valor bruto (`amc_fator_bruto`,
metros/booleano/categoria) de nota (0-100, produto da transformação declarada) — a mesma fronteira
que `app/amc/combinacao.py` já assume ("matriz de fatores JÁ transformados"). Uma média de área
ponderada só comuta com a transformação quando ela é afim e nenhuma célula bate no limite (`abaixo`/
`acima`); como isso não é garantido em geral, `agregar()` exige a nota já pronta por célula, nunca
o bruto. É por isso que a prova do portão usa `cbre.hex_fav` (fatores já 0-100) em vez de tentar
reconstituir a transformação aqui.

## Decisão 3 — a integração com a execução real do motor entra com UM fator sintético (limite honesto, documentado)

`celulas_de_execucao_sql()` não tem, hoje, a nota por fator por célula persistida — só o valor bruto
(`amc_fator_bruto.valor`) e a favorabilidade JÁ combinada da célula (`amc_resultado.favorabilidade`).
Recompor a transformação de cada fator aqui duplicaria o item L3-01-d-transformacoes (pendente,
`app/amc/executor.py` já documenta o mesmo limite: só resolve `linear`, as outras erram alto e claro)
sem a verificação cruzada que aquele item exige. A saída escolhida: a célula entra na agregação com
um fator sintético `favorabilidade` = o que o motor já combinou; a agregação por feição vira
`Σ área·favorabilidade / Σ área` sobre as não vetadas — mesma conta de qualquer `f_*` do cbre, com
N = 1. `agregar()` continua aceitando `modelo_definicao`/`pesos` para recombinar N > 1 fatores
(testado com dados sintéticos, `test_pesos_do_modelo_recombinam_varios_fatores`) para quando a nota
por fator por célula existir.

## Decisão 4 — desempate determinístico do veto principal

`veto_principal` é o motivo da célula vetada de maior área de interseção; em empate de área,
`ORDER BY area_m2 DESC, cell_id` desempata sempre pelo mesmo critério. Sem isso, duas consultas
matematicamente equivalentes mas com plano de execução diferente podem devolver motivos diferentes
para a mesma feição — achado rodando a refutação do item (`tests/unit/test_amc_agregacao_adversario.py`,
a consulta escrita à mão no psql discordava da de `agregacao.py` só nesse critério até o ajuste).

## Decisão 5 — três colunas de `cbre.imoveis_fav` ficam fora da comparação do portão, por não serem geometria

`f_roubo`, `f_trib`, `f_renda`, `f_rlapp`, `f_polos`, `f_se`, `f_cluster` e `f_varzea` são
SOBRESCRITOS por `cbre/pipeline/85_fatores.sql` depois da agregação de grade, com uma consulta
direta por imóvel (`cbre.imovel_fatores_extra`/`cbre.imovel_inundacao` — roubo pelo trajeto real do
imóvel, inundação oficial por imóvel, mais precisos que a média das células que ele toca).
Comparar essas colunas testaria o gancho por imóvel do cbre, não o mecanismo geométrico deste item;
ficam fora de `FATORES_HEX` em `tests/unit/test_amc_agregacao_cbre.py`, com a evidência (linha do
SQL do cbre) no docstring do teste. Os dez fatores comparados (`f_decl`, `f_zon`, `f_gru`, `f_rod`,
`f_disp`, `f_ener`, `f_agua`, `f_restr`, `f_press`, `f_dens`) são exatamente os que o próprio SQL do
cbre lista no `SELECT` de resumo do fim do arquivo — nenhum `UPDATE` os toca depois da agregação.

## Consequências

- `celulas_de_uma_feicao()` cobre o caminho inverso da hipótese (feição -> células, para exibir),
  mas ainda sem rota HTTP dedicada — este item entrega o mecanismo (papéis dados/backend/
  adversário do prompt), a exposição via API/tela fica para um item de frontend futuro.
- `limiar_fracao_vetada` ("sai do ranking") é parâmetro de quem chama, nunca calculado — mesma
  regra do resto do motor (pesos e limiares são escolha do usuário, nunca medição).
