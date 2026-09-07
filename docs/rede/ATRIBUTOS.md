# Atributos de rede (item L4-01-d-atributos-de-rede)

Contrato do item, o modelo de dado, o algoritmo e a paridade contra *network attributes*, *attribute
propagation*, *is connected* e *substitution* do ArcGIS Pro. Ver também `docs/rede/TOPOLOGIA.md` (item
anterior, base sobre a qual este item constrói) e ADR 20260907T1315.

## 1. O que é "atributo de rede" aqui

`plat.rede_atributo` (item L4-01-a) já é o catálogo de todo atributo importado do pacote — nome, tipo,
unidade, coluna de origem por tipo de ativo. Este item marca, nesse MESMO catálogo, quais atributos são:

- **propagáveis** (`propagavel`): o traçado pode levá-los do controlador para jusante — hoje só a fase;
- **apoiam traversabilidade** (`apoia_traversabilidade`): definem se um dispositivo conduz ou não — hoje só
  a posição normal de operação da chave.

E semeia três linhas SINTÉTICAS por grupo aplicável — atributos que a plataforma CALCULA, sem coluna de
origem na BDGD: comprimento geodésico (grupos de linha), `is_connected` e `subrede` (todo grupo). Marcadas
`origem = {"calculado": true}`, nunca com câmera/coluna inventada.

## 2. Sincronização: trigger (edição) + lote (reconstrução)

- **Trigger** (`tg_rede_atributo_sincronizar_linha`/`_ponto`, `AFTER UPDATE`): ao editar uma feição já
  refletida na topologia, copia `fase_bitmask`/`atributos`/`tensao_nominal_kv`/`capacidade_kva` (linha) ou
  recalcula `traversavel` a partir de `estado_dispositivo` (ponto) na linha derivada correspondente. Não
  reconstrói estrutura — só copia valor.
- **Lote** (`POST /api/rede/{id}/atributos/sincronizar` → `atributos.sincronizar_topologia_lote`): copia
  tensão/capacidade de TODAS as arestas de uma vez e RECONSTRÓI `plat.rede_topo_dispositivo_aresta` do zero
  para a rede — precisa da contagem de terminais por dispositivo, que não cabe num trigger de linha.

## 3. Aresta interna do dispositivo

`plat.rede_topo_dispositivo_aresta` liga os dois nós-terminal de um dispositivo de 2+ terminais (chave,
religador, disjuntor). Sem ela, a topologia derivada de L4-01-b não tem como o traçado atravessar uma chave
FECHADA — L4-01-b só liga um terminal ao trecho vizinho, nunca terminal a terminal do MESMO dispositivo.
`traversavel` reflete `estado_dispositivo` (`aberto` → `false`; qualquer outra coisa, inclusive nulo →
`true`). Dispositivo de categoria `transformacao` NUNCA ganha esta aresta: ele separa duas subredes (alta ×
baixa tensão), nunca conduz por dentro — decisão de `sincronizar_topologia_lote`, olhando
`rede_tipo_categoria`, não da migração.

## 4. Propagação de fase

`atributos.propagar_fase` faz um BFS a partir de cada raiz declarada (nó de categoria `fonte`, ou
informada explicitamente pelo chamador). A fase corrente é uma propriedade do CAMINHO percorrido nesta
passada — cada nó visitado guarda a fase com que foi alcançado, nunca uma variável global — o que garante
que mudar a fase de um trecho a montante muda toda a jusante alcançada dali e NUNCA um ramo irmão que nasce
do mesmo tronco mas não compartilha nó com o trecho mudado.

Ao atravessar uma aresta de DISPOSITIVO cujo tipo tem regra de SUBSTITUIÇÃO ativa
(`plat.rede_atributo_substituicao`, indexada pelo `tipo_id` do ponto que originou a aresta) para o atributo
corrente, a fase muda de `de_valor` para `para_valor` — nunca aplicada fora de regra explícita.

A fase resultante fica em `rede_topo_aresta.fase_propagada`; onde ela diverge da fase DECLARADA
(`fase_bitmask`, vinda do arquivo/BDGD) nos trechos de MT, uma linha entra em
`plat.rede_atributo_discrepancia` — candidata a erro de cadastro, NUNCA usada para corrigir o valor
declarado em silêncio.

## 5. Conectividade (`is_connected`/`subrede`)

`atributos.recalcular_conectividade` roda o MESMO grafo (linha + dispositivo, respeitando `traversavel`) e
marca `is_connected = true`/`subrede_codigo = <rótulo da raiz>` em todo nó e aresta alcançados a partir de
alguma raiz; o resto fica `is_connected = false`/`subrede_codigo = NULL` — inclusive o lado morto de uma
chave que acabou de abrir. `is_connected` serve de FILTRO direto (`WHERE is_connected`), sem recalcular nada
na consulta.

## 6. Fronteira achada: dispositivo coincidente com trecho-trecho do mesmo grupo

`topologia.habilitar` (L4-01-b) funde diretamente as duas pontas de trecho que se tocam sempre que são do
MESMO grupo — pensado para um trecho partido em vários pedaços sem dispositivo no meio. Quando uma chave de
2 terminais do MESMO tier (o caso normal: MT em série, tronco e jusante ambos `trecho_de_media_tensao`)
senta exatamente sobre esse encontro, a fusão trecho-trecho funde as duas pontas ENTRE SI antes de o
dispositivo entrar no jogo — os dois terminais da chave caem no MESMO grupo de união, viram um nó só, não
dois. `sincronizar_topologia_lote` detecta isto honestamente (conta em `ignorados_sem_dois_nos`, nunca cria
a aresta interna com um único nó). Não é bug deste item: é uma ambiguidade herdada de L4-01-b.

Consequência medida contra a cooperativa de teste (schema `certaja`, BDGD real): o extrato não tem NENHUMA
chave/subestação do pacote `eletrica-br` (só trechos, transformador e poste) — `sincronizar_topologia_lote`
mede 0 aresta de dispositivo nessa base, e a propagação/conectividade usam a raiz ASSUMIDA por alimentador
(extremidade de grau 1 do `ctmt`), nunca uma subestação real. Números exatos em
`tests/medidas/L4-01-d-atributos-de-rede.json`. Os testes de mecânica pura
(`tests/api/test_rede_atributos.py`) contornam a fronteira montando a topologia manualmente (2 nós de
terminal reais) — provam a lógica isolada da ambiguidade, com a refutação exigida pelo item incluída.

## 7. Paridade (resumo; tabela completa em `docs/PARIDADE.md`)

*Network attribute* propagável/traversável, sincronização por edição e por lote, aresta interna do
dispositivo, *attribute propagation*, *substitution*, discrepância e `is_connected` como filtro — todos
`feito` na mecânica; a cláusula de concordância ≥95% do enunciado, que pressupõe um controlador real no
MESMO arquivo, fica sem essa medida específica nesta base (fronteira §6) — a mecânica de propagação em si
está provada e refutada com uma rede sintética.
