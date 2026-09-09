# ADR 20260909T0142 — ajuste por mínimos quadrados e camada de qualidade da malha de parcelas (item L4-parcelas-03-ajuste-e-qualidade)

Contexto: o modelo de parcelas (item 01) e os fluxos com fachada REST (item 02) já existem. Faltava o
que o parcel fabric do ArcGIS Pro chama de least squares adjustment (analyzeByLSA/applyLSA) e a
qualidade da malha (Find Gaps and Overlaps + regras de atributo). O portão do item exige a prova
FORTE: malha sintética de 20 parcelas com 3 pontos de controle cuja solução analítica é conhecida —
o ajuste tem de reproduzir as coordenadas verdadeiras, não apenas "convergir".

## Decisão

`app/parcelas/ajuste.py` resolve a rede por Gauss-Newton ponderado, em metros e segundos de arco,
com mínimos quadrados de norma mínima (`numpy.linalg.lstsq`). A rede é coletada das LINHAS com
`tipo_cogo='reta'` e rumo e distância declarados (observação); arco e linha sem medida não entram.
Ponto de controle é `categoria='controle'` ou `fixo=true`; os demais pontos são incógnitas. Peso por
categoria de ponto (`controle` 0,005 m; `apoio` 0,05 m) e de linha (`medido` 2 cm/10"; `escritura`
10 cm/60"; `derivado` 50 cm/300"), sempre superável por coluna explícita
(`precisao_dist_cm`/`precisao_rumo_s`/`precisao_xy_m`).

**Analisar vs aplicar**: `analisar` resolve e devolve o relatório SEM escrever nada (prova por
checksum da malha no teste); `aplicar` move os pontos com deslocamento ESTRITAMENTE maior que
`movementTolerance`, recompõe a geometria de linha (sempre os dois pontos) e de parcela
(`ST_Polygonize` das linhas dela; anel aberto não tem face e fica declarado no relatório), atualiza
`precisao_xy_m` quando `updateAttributes` e GRAVA a versão em `plat.parcela_ajuste` (append-only,
relatório integral).

## D1. A solução analítica como portão, e os três bugs que ela pegou

A malha de teste é uma grade 4x5 de células 100x20 m com desvio inicial determinístico (fórmula
fechada, nenhum aleatório); 30 nós, 3 controles, 49 linhas, 98 observações, 54 incógnitas, 44
redundâncias. As coordenadas verdadeiras são a SOLUÇÃO ANALÍTICA da rede — o teste exige reproduzi-la
a 1 mm com resíduo dentro do sigma. Esta cláusula pegou TRÊS bugs que uma suíte de fumaça deixaria
passar: sinal trocado na derivada da distância (o solver divergia), colunas da matriz de design
indexadas por ponto em vez de por incógnita (posto 28/54 — espaço nulo de 26 dimensões, achado por
SVD) e linhas de distância sem divisão pelo sigma (o sistema explodia para 1e18 — as linhas de rumo
já dividiam, o que escondia o defeito). Lição registrada: ajuste de rede sem solução conhecida é
teste que não testa.

## D2. Semântica do `convergenceTolerance`: UM passo, declarado

A doc do Esri define `convergenceTolerance` como "maximum coordinate shift expected after
iterating" (padrão 0,05 m). A casa para quando o MAIOR passo da iteração fica abaixo da tolerância.
Consequência medida e declarada no teste: com a tolerância padrão, o ajuste para em 1 iteração e o
resíduo normalizado fica ~1,5 sigma (erro de partida de centímetros); com tolerância fina (0,001 m)
segue mais uma iteração e sigma_zero cai abaixo de 0,01 com coordenadas a 1e-4 m da verdade. O
relatório expõe `sigma_zero` e `iteracoes` para o leitor julgar — a casa não esconde a parada.

## D3. CONSISTENCY_CHECK resolve a MESMA rede ponderada — divergência declarada

Na doc do Esri, CONSISTENCY_CHECK é ajuste de REDE LIVRE (sem controle; rede mínima). Na casa,
CONSISTENCY_CHECK e WEIGHTED_LEAST_SQUARES resolvem a mesma rede com controles fixos; a diferença é
de INTENÇÃO (consistência não move ponto, nunca; a prova é o checksum) e de recusa: rede SEM
controle nenhum é recusada com `rede_sem_redundancia` (sem datum, coordenada não é determinada).
Rede livre (constraints internos) fica fora deste item; se um dia entrar, é um terceiro modo
explícito, não um default silencioso.

## D4. `semLinhas`: medida excluída da RODADA, nunca apagada

Extra declarado da casa (não existe na doc): excluir uma medida grosseira da rodada para conferir
que o resto da rede converge limpo. A medida fica no banco intacta; a exclusão vale só para aquela
resolução e volta no relatório como `linhas_excluidas`. A refutação do portão usa isso: 1 m de erro
em linha de 100 m vira a SUSPEITA nº 1 (residuo normalizado > 3 e DOMINANTE — numa malha rígida o
erro se espalha por vizinhos acima de 3 sigma, o que destaca é a dominância, não a exclusividade) e,
excluída, a rede reconverge com todo resíduo dentro do sigma.

## D5. Qualidade: relatório vivo, não tabela; sobreposição DENTRO do tipo

`POST /api/parcelas/quality`-equivalente (`/api/parcelas/qualidade`) devolve relatório computado na
hora (as camadas de qualidade do Pro também "do not alter the original data"). SOBREPOSIÇÃO é par do
MESMO tipo (`a.tipo = b.tipo`): quadra sobre lote não é par — a comparação é dentro da família, e o
teste tem o par de quadras para provar que o filtro de tipo filtra. LACUNA é face do polygonize das
próprias bordas que nenhuma parcela DO MESMO REGISTRO cobre. As duas contagens são conferidas no
teste com PREDICADOS DIFERENTES dos da implementação (ST_Overlaps no par; ST_Difference contra a
união do registro na face) — conferência independente de verdade, não repetição do mesmo SQL.

## D6. Memória é recurso alheio: lacuna POR REGISTRO, uma passada de polygonize, e o `&&` na conferência

Na primeira rodada do corpo real (11.473 lotes de exemplo), a conferência independente SEM
pré-filtro de bbox varreu 65,8 milhões de pares e um backend do Postgres passou de 3 GB e foi morto
pelo kernel — o servidor de produção reiniciou (dmesg 09/09, OOM). Consertado no teste: `a.geom &&
b.geom` como pré-filtro de candidatos (o predicado que decide continua sendo o ST_Overlaps, logo a
conferência segue independente). E o polygonize do corpus INTEIRO de uma vez não termina de forma
alguma: uma sessão da rodada morta ficou 20 MINUTOS de GEOS a 100 % antes de ser terminada à mão.
Décisão de escopo: a LACUNA é calculada DENTRO de cada registro (cada registro é um levantamento;
espaço entre dois registros não é lacuna de malha nenhuma) — a malha é agrupada por
`criada_por_registro` e o polygonize roda por grupo. No corpus, a maior malha tem 968 lotes e o
mesmo cálculo é trivial. O polygonize roda UMA vez por registro em tabela temporária (conta, soma e
lista a partir dela — eram duas passadas iguais). Regra para o laço: consulta de corpo inteiro em
máquina dividida com produção tem de ter custo declarado e pré-filtro indexável; e sessão de teste
que estoura relógio deixa ZUMBI — matar o backend antes de medir qualquer coisa de novo.

A conferência independente do corpus pegou um segundo erro de escopo, depois do primeiro conserto:
com o polygonize por registro mas a COBERTURA ainda global no inquilino, a camada dizia 234 lacunas
e o conferente (ST_Difference contra a união do PRÓPRIO registro) dizia 250 — 16 faces eram
cobertas por parcelas de OUTRO registro (importações duplicadas no corpus de exemplo). Lacuna de
malha não desaparece porque outra malha cobre a área por cima: esse transpasse ENTRE registros é
exatamente o que a seção de sobreposições aponta. A cobertura passou a ser da própria malha
(`criada_por_registro = f.rid`), e as duas contagens bateram.

E a conferência pegou um TERCEIRO defeito, este latente no SQL: `ST_Polygonize(g)` com geometria
solta resolve para a forma AGREGADA do PostGIS — agregava as bordas dos 25 registros NUMA polygonize
só, misturando coleções de levantamentos diferentes (faces que fecham com borda de um registro e
borda de outro). Passou a admitir `rid` ao lado e o Postgres recusou ("must appear in the GROUP BY")
— a forma correta é `ST_Polygonize(ARRAY[g])`, uma linha por registro. Regra: função do PostGIS com
forma agregada e forma de valor tem de ser chamada com ARRAY explícito quando a intenção é por
linha.
