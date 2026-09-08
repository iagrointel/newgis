# O resultado do traçado: fotografia com procedência, e um GeoPackage escrito com a biblioteca padrão

Item `L4-02-f-resultados-e-exportacao`. Setembro de 2026.

## Contexto

O traçado já devolve a lista de elementos, a geometria agregada e a contagem. Falta o que se faz com esse
resultado depois: vê-lo como tabela com as somas ao lado, marcá-lo como seleção, guardá-lo como camada,
levá-lo para fora em arquivo e voltar a um traçado feito ontem. É o que a Esri organiza na página de
resultados da rede de utilidades (`results.htm`).

## Decisão

**1. Uma porta por saída, e todas sobre o mesmo motor.** O despacho ao motor certo saiu da rota
`POST /api/rede/{id}/tracar` para `app/rede_utilidades/despacho.py`, e as quatro portas do item o chamam:
exportar, salvar como camada, repetir do histórico e a própria rota de traçar. Quatro cópias do despacho
seriam quatro motores com um nome só.

**2. O histórico guarda o PEDIDO, nunca o resultado.** `plat.rede_tracado_execucao` grava o corpo enviado, a
contagem, o tempo e a data da rodada de topologia que valia. Repetir é reenviar o pedido à rede como ela
está hoje, e a resposta traz `contagem_anterior` ao lado da contagem nova: quando a rede mudou, os dois
números divergem, e é isso que se quer ver. Um resultado guardado envelheceria em silêncio junto com a rede.

**3. A camada salva é um tipo de item PRÓPRIO (`camada_tracado`), não `camada_vetorial`.** O tipo vetorial
exige schema e tabela PostGIS; a camada de traçado não tem tabela — é uma fotografia dos elementos, da
geometria e das agregações, com a procedência do traçado que a produziu (rede, configuração, pontos de
partida, versão da topologia e data). Sem dado físico, portanto sem cota. Chamá-la de `camada_vetorial`
obrigaria a inventar um schema e uma tabela que não existem.

**4. Nível de tensão é o TIER declarado no pacote de ativos.** A agregação "por nível" lê
`plat.rede_tier` (subtransmissão, média tensão, baixa tensão, com a ordem), nunca deduz o nível do nome do
grupo. Elemento cujo tipo não tem tier sai numa linha própria, com o nível nulo: a agregação diz o que não
sabe em vez de escolher uma faixa por ele.

**5. O GeoPackage é escrito com `sqlite3` da biblioteca padrão** (`app/rede_utilidades/geopacote.py`), não
com `ogr2ogr`. Um GeoPackage é um SQLite com três tabelas de catálogo e a geometria em WKB — que o PostGIS
devolve pronto em `ST_AsBinary` — atrás de um cabeçalho de oito bytes. Chamar `ogr2ogr` exigiria subprocesso
e arquivo temporário dentro da requisição (o repositório só o chama de dentro de um job) numa máquina com
98 % de disco. Com `sqlite3` o arquivo nasce em memória e sai como bytes. Quem confere o formato no teste é
o `ogrinfo`, que é o leitor de verdade, e não o nosso próprio código.

## Consequências

- Toda exportação e toda camada passam por `limites.TRACADO_EXPORTACAO_MAX` (50 mil elementos): acima disso
  a resposta é 413 dizendo o número medido e como estreitar o traçado, nunca um arquivo pela metade.
- O histórico é por pessoa e por rede, e para em `limites.TRACADO_HISTORICO_MAX` (20). Quem traça por token
  de serviço de outro inquilino (superadmin em leitura) não entra no histórico: a política de escrita da
  tabela exige o vínculo com o inquilino.
- Salvar como camada é a única rota de escrita sob `/api/rede` que não pede `rede.editar`: ela não escreve
  na rede, escreve no catálogo, e por isso pede `conteudo.criar`.
