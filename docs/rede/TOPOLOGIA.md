# Topologia derivada da rede de utilidades (item L4-01-b-topologia-derivada)

Contrato do item, o modelo de dado, o algoritmo e a paridade contra o *Enable Network Topology* do ArcGIS.
Ver também `docs/PACOTE_REDE.md` (o esquema, item anterior) e ADR 0020.

## 1. O que "habilitar topologia" faz

`POST /api/rede/{rede_id}/topologia/habilitar` lê as feições da rede (`plat.rede_feicao_ponto` = dispositivo,
`plat.rede_feicao_linha` = trecho) e RECONSTRÓI do zero dois índices derivados:

- `plat.rede_topo_no` — um nó por vértice de conexão e por terminal de dispositivo;
- `plat.rede_topo_aresta` — uma aresta por trecho, com nó de origem/destino, comprimento geodésico
  (`ST_Length(geom::geography)`), bitmask de fase e os atributos do trecho desnormalizados.

`GET /api/rede/{rede_id}/topologia` devolve o resumo da última construção (`plat.rede_topo_resumo`);
`GET .../topologia/nos` e `.../arestas` listam o resultado. As feições continuam camadas normais e
editáveis — a topologia nunca é editada diretamente, só reconstruída por `habilitar`.

**Reconstrução total, não incremental.** Toda chamada apaga a topologia anterior da rede e regrava tudo numa
transação. Não existe "área suja" (marcar só o trecho que mudou) nesta passagem — ver ADR 0020 §2.

## 2. Tolerância é parâmetro da rede

`plat.rede.tolerancia_m` (padrão `0,05`, checado `0 < x <= 10`), definida na criação da rede
(`POST /api/rede {"tolerancia_m": ...}`) e visível na ficha (`GET /api/rede/{id}`). Duas coordenadas coincidem
quando `ST_DWithin(a::geography, b::geography, tolerancia_m)` é verdadeiro — distância GEODÉSICA, não
planar, medida em metros reais.

Medido (`tests/api/test_rede_topologia.py`): um ponto a 0,04 m de um vértice conecta na tolerância padrão; a
0,06 m não conecta; a MESMA distância de 0,06 m conecta numa rede que declarou tolerância de 0,1 m — a régua é
da rede, nunca uma constante global.

## 3. Coincidência geométrica + associação explícita

Cruzar não é conectar: só os vértices DECLARADOS (as duas pontas de um trecho, o ponto de um dispositivo)
entram como candidato a nó. Um cruzamento no meio de duas linhas nunca gera candidato — as duas seguem
desconectadas, mesmo se as linhas se cruzam geometricamente (`test_cruzamento_sem_no_nao_conecta`).

A fusão de dois candidatos dentro da tolerância segue esta ordem:

1. **trecho ↔ trecho, mesmo grupo** — sempre funde (continuação natural do mesmo tipo de ativo: dois
   segmentos de trecho de média tensão que se tocam).
2. **trecho ↔ trecho ou trecho ↔ dispositivo, grupos diferentes** — funde só se existir uma linha em
   `plat.rede_regra` (`conectividade_no_trecho` ou `conectividade_entre_nos`) ligando os dois TIPOS
   envolvidos. Sem essa regra, a coincidência geométrica sozinha NÃO conecta — impede, por exemplo, que um
   poste (estrutura) "vaze" conectividade elétrica só por estar perto de um trecho.
3. **dispositivo com 2+ terminais** (ex.: transformador `alta`/`baixa`, ambos no MESMO ponto físico) — cada
   terminal é resolvido em separado, por dispositivo, usando a ORDEM do `tier` do trecho vizinho
   (`rede_tier.ordem`, já declarada no pacote de ativos): o terminal `montante=true` liga ao tier de ordem
   MENOR (mais a montante), o(s) `montante=false` ao(s) de ordem maior. Quando os candidatos tocam só UM
   tier (ex.: uma chave em série no meio do mesmo trecho de MT), a ordem de chegada decide — determinística,
   mas sem como saber o lado real sem um traçado completo da rede (fronteira honesta, §6).

## 4. Um nó por terminal, não por dispositivo

Um transformador com 2 terminais gera (até) 2 linhas em `rede_topo_no`: uma funde com o trecho de MT, outra
com o de BT — nunca uma linha só. Um dispositivo `sem_terminal` (ex.: poste) não gera nó NENHUM: é decorativo
para a topologia elétrica, mesmo que apareça aos milhares na camada (medido: 60.549 postes → 0 nós).

`nos_orfaos` conta nós de papel `terminal` com grau (nº de arestas que o tocam) igual a zero — um dispositivo
cadastrado cujo terminal não encontrou nenhum trecho compatível dentro da tolerância. `arestas_sem_no` conta
trechos degenerados (origem == destino, comprimento zero) — não entram na candidatura de nó de propósito
(um trecho de comprimento zero não tem "lado A" e "lado B" para decidir).

## 5. Escala e a medida de tempo — dois caminhos, dois arquivos de medida

**Rápido, todo turno**: `tests/dados/gerar_rede.py` gera uma rede FICTÍCIA nas mesmas ordens de grandeza da
cooperativa de teste, com semente determinística (a mesma semente sempre produz os mesmos dados) — uma árvore
de MT com passos aleatórios, transformadores nascendo em vértices da árvore com sub-árvore de BT, ramais
saindo de vértices de BT existentes, postes decorativos em qualquer lugar da caixa, mais um punhado de casos
de fronteira DELIBERADOS (transformador deslocado 1 m — prova de nó órfão; trecho degenerado — prova de
aresta sem nó). Usada nos testes rápidos de `tests/api/test_rede_topologia*.py` (segundos, não minutos).

**Escala real, marcado `lento`**: a rede real da cooperativa de teste (ativo de rede de referência da
casa, num schema próprio do banco compartilhado, SOMENTE LEITURA — 44.268 trechos de MT, 29.244 de BT, 26.581 ramais, 5.481 trafos, 60.549 postes) NÃO
está no repositório como arquivo (é acesso vivo ao Postgres compartilhado, exige `GRANT USAGE/SELECT` — ver
docstring de `tests/dados/carga_bdgd.py`), mas EXISTE e é medida em `tests/api/test_rede_topologia_medida.py`
(`pytest -m lento`), com conferência por um contador Python independente que nunca reconsulta as tabelas que
o construtor gravou. Medido 2026-09-07 (`tests/medidas/L4-01-b-topologia-derivada.json`): 73.512 arestas reais
(MT+BT), 80.456 nós, 3.948 órfãos, 0 arestas sem nó, 21 alimentadores com componente conexa idêntica arquivo ×
topologia, 1.554 terminais de alta órfãos batendo exato com o arquivo. **Fronteira medida, não fabricada**:
a tabela `ramlig` do ativo de referência tem 0 dos 26.581 registros com `wkt` preenchido — o ramal de ligação entra como atributo, não
como aresta geométrica (§6 abaixo detalha a conferência). Tempo de `habilitar` variou de ~21 s (máquina sem
outra carga) a ~600 s (máquina com 4-8 agentes de outras trilhas disputando CPU/RAM ao mesmo tempo — swap
100% cheio) na mesma rede de 73.512 arestas: o código processa em lotes de 4.000 linhas (§ADR 0020) e escala
linear; a variação é do ambiente compartilhado, não do algoritmo — os dois tempos estão no arquivo de medida.

Achado de performance registrado no ADR 0020 §5: `ST_DWithin` sobre `geom::geography` não usa o índice GIST;
corrigido com um pré-filtro por `ST_DWithin(geom, geom, graus)` (geometria pura, usa o índice) seguido da
conferência exata em `geography`. Números do gerador sintético só no próprio teste (`tests/api/test_rede_topologia.py`,
não escritos em arquivo); números da escala real em `tests/medidas/L4-01-b-topologia-derivada.json` (comando
incluso no próprio arquivo JSON).

## 6. Fronteira honesta

- **Sem manutenção incremental por área suja.** Toda chamada de `habilitar` reconstrói a topologia inteira.
- **Sem unificação com o catálogo geral de camadas.** `plat.rede_feicao_ponto`/`rede_feicao_linha` são
  tabelas PRÓPRIAS desta linha, não o `camada_vetorial` genérico (tabela dinâmica `d_<slug>.c_<uuid>` da
  ingestão, item L0-04). As duas são "camadas normais e editáveis" no sentido em que a hipótese do item pede
  (linhas de tabela real, com RLS, inseridas/consultadas por rota própria), mas ainda não a MESMA infraestrutura
  de upload/miniatura/exportação do catálogo geral — decisão de escopo, não lacuna descoberta depois.
- **Sem traçado.** A topologia é o grafo; percorrê-lo respeitando `caminhos_validos` e estado aberto/fechado
  de uma chave é o item seguinte da linha L4.
- **Desambiguação de terminal por ordem de chegada** quando um dispositivo multi-terminal só toca UM tier
  (§3.3) é uma convenção, não uma dedução dos dados — sem traçado de rede não há como fazer melhor.
- **Ramal de ligação sem geometria no ativo real.** A tabela `ramlig` do ativo de rede de referência (BDGD
  da cooperativa de teste) tem os 26.581 registros do arquivo mas 0 com a coluna `wkt` preenchida — medido, não suposto
  (`count(wkt)` direto na tabela). A carga (`tests/dados/carga_bdgd.py`) filtra `WHERE wkt IS NOT NULL`, o
  ramal entra como atributo (contagem do arquivo) mas não como aresta geométrica — fabricar uma linha que o
  arquivo não tem violaria a metodologia da casa. A topologia geométrica medida em escala real cobre MT + BT
  + transformador + poste (139.542 elementos reais, com trafo/poste como pontos e MT/BT como arestas).

## 7. Paridade com o ArcGIS (*Enable Network Topology*)

| capacidade | Esri (*ArcGIS Pro 3.4, Utility Network*) | aqui | estado |
|---|---|---|---|
| habilitar topologia (construir o grafo a partir das feições) | *Enable Network Topology*: lê as classes de feição da rede, aplica regras de conectividade e escreve a malha de rede | `POST /api/rede/{id}/topologia/habilitar`: lê `rede_feicao_ponto`/`rede_feicao_linha`, escreve `rede_topo_no`/`rede_topo_aresta` | feito |
| coincidência geométrica com tolerância | tolerância de *snapping* configurável na malha de rede | `tolerancia_m` por rede, `ST_DWithin` geodésico | feito |
| terminal de dispositivo como nó próprio | *device feature* com *terminal configuration*; a malha trata cada terminal como ponto de conexão distinto | um `rede_topo_no` por terminal, resolvido por tier quando há 2+ | feito |
| regra de conectividade entre tipos | *Junction-Edge Connectivity Rules* / *Junction-Junction Connectivity Rules* | `plat.rede_regra` (já do item anterior), consultada na fusão de nó | feito |
| resumo/validação da malha (contagem, erros) | *Validate Network Topology* devolve erros de conectividade | `plat.rede_topo_resumo` (nós, arestas, órfãos, arestas sem nó) — sem catálogo de ERROS de regra ainda, só contagem estrutural | parcial |
| manutenção incremental (*dirty areas*) | edição marca a área suja; só ela é reconstruída | reconstrução total a cada `habilitar` | fora (próximo item, ADR 0020 §2) |
| traçado (*Trace*) | percorre a malha respeitando regras/estado | não existe ainda | fora (item seguinte da linha L4) |
| subrede (*Subnetwork*) | agrupamento e atualização de subrede a partir de uma fonte | não existe ainda | fora (item seguinte da linha L4) |

Coluna "Pro/AGOL real" omitida (mesma decisão D20 do ADR 0019: pendente até o parceiro testar com credencial
própria) — a comparação acima é leitura da documentação pública da Esri, não medição contra o produto real.
