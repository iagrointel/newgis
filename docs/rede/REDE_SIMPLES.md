# Rede simples (item L4-18-rede-simples-trace-network)

Rede sem pacote de ativos, sem regra de negócio e sem terminal de dispositivo: só junções e trechos, com a
direção de fluxo declarada por ATRIBUTO do trecho e os atributos de rede que o inquilino escolher. É o que a
Esri chama de *Trace Network*, e serve às disciplinas em que a rede é um grafo de linhas com sentido, sem
catálogo de equipamento: hidrografia, drenagem, ferrovia.

## 1. Como se cria

`POST /api/rede/simples`, uma chamada, duas camadas do inquilino:

```json
{"nome": "Bacia do rio X", "disciplina": "agua",
 "camada_linha_id": "<item camada_vetorial de linhas>",
 "camada_ponto_id": "<item camada_vetorial de pontos>",
 "campo_direcao": "sentido",
 "mapa_direcao": {"jusante": "digitalizada", "invertido": "contra", "desconhecido": "indeterminada"},
 "atributos_rede": [{"nome": "regime", "tipo_dado": "texto", "de": "linha"}]}
```

A chamada faz, numa transação só: cria a rede em modo `simples`; instala o catálogo mínimo interno; copia as
feições das duas camadas (multiparte explodida por `ST_Dump`, geometria reprojetada para 4326); traduz o
campo de direção para o vocabulário fechado; grava a configuração; e constrói a topologia derivada. Na tela
`/redes/simples` isso são três interações: escolher a camada de linhas, escolher a de pontos, clicar em criar.

A camada de pontos é opcional — uma rede simples pode ser só de trechos.

## 2. Direção de fluxo

Vocabulário fechado, três valores, gravados na chave `direcao_fluxo` dos atributos de cada trecho:

| valor | significado |
|---|---|
| `digitalizada` | o fluxo segue a ordem dos vértices, do primeiro para o último |
| `contra` | o fluxo segue ao contrário da ordem dos vértices |
| `indeterminada` | não se sabe; o trecho não conduz em sentido nenhum |

Regras que valem sempre:

* sem `campo_direcao` declarado, toda a rede é lida como `digitalizada`;
* valor do campo de origem que não está no `mapa_direcao` vira `indeterminada`;
* valor fora do vocabulário gravado depois por `applyEdits` (alguém pôs "talvez") é lido como
  `indeterminada` — nunca se adivinha um sentido;
* a direção é atributo DA FEIÇÃO, não do índice: mudá-la por `applyEdits` muda o traçado na hora, sem
  reconstruir a topologia.

## 3. Traçados

`POST /api/rede/{rede_id}/tracar` com `tipo`:

* `montante` / `jusante` — andam pela direção de fluxo (item L4-18);
* `conectado` — conectividade pura, ignora a direção (item L4-02-a);
* `caminho_curto` — menor caminho por comprimento geodésico ou por atributo de rede (item L4-02-d).

Toda parada num trecho indeterminado sai no resultado: `parou_em_indeterminada` e uma lista `avisos` com
`aresta_id`, `feicao_id` e `no_id` de cada trecho indeterminado que encosta no resultado. Encostar dos DOIS
lados conta: a aresta não conduz em sentido nenhum, então tanto faz por qual ponta o traçado chegou nela.

## 4. Promover a rede de utilidades

`POST /api/rede/{rede_id}/promover` carimba o PACOTE MÍNIMO: exporta o catálogo real da rede, põe na forma
canônica, passa pelo mesmo validador de qualquer pacote de ativos, grava `sha256`/`bytes` e muda o modo para
`utilidades`. Antes disso `GET /api/rede/{id}/pacote` devolve 404; depois devolve o pacote, e o inquilino
pode importar por cima dele um pacote de ativos de verdade.

Promover NÃO reimporta o documento: `deposito.importar` apaga o catálogo antes de gravar, e as feições têm
chave estrangeira para `rede_tipo` com `ON DELETE CASCADE` — reimportar levaria junto todas as feições e a
topologia (medido durante a construção do item). O catálogo já é exatamente o que o pacote descreve.

O catálogo mínimo é: 1 domínio (`rede`), 1 tier (`unico`), 0 categorias, 1 configuração de terminal
(`juncao-simples`, um terminal, nenhum caminho válido), 2 grupos (`juncao` ponto, `trecho` linha), 2 tipos,
1 atributo (`direcao_fluxo`) e 1 regra de conectividade junção-trecho.

## 5. Paridade com o Trace Network da Esri

Fontes: `pro.arcgis.com/.../trace-network/what-is-a-trace-network-.htm`,
`.../network-attributes.htm`, `.../dirty-areas-in-a-trace-network.htm`,
`developers.arcgis.com/rest/services-reference/enterprise/trace-network-service/` (lidas em setembro de 2026).

| capacidade | Trace Network (Esri) | rede simples (aqui) | estado |
|---|---|---|---|
| rede sem pacote de ativos | sem asset package, sem regra, sem terminal | modo `simples`: catálogo mínimo interno, colunas de pacote nulas, `GET /pacote` = 404 | feito |
| origem em feature classes existentes | junções e arestas em feature classes do usuário | duas camadas `camada_vetorial` do inquilino, copiadas para as camadas de rede | feito |
| direção de fluxo por atributo | digitized / against digitized / indeterminate | `digitalizada` / `contra` / `indeterminada`, com mapa de valores declarado pelo inquilino | feito |
| atributos de rede | network attributes atribuídos a campos, usados por condição e função no traçado | declarados em `atributos_rede` e usáveis como custo em `caminho_curto` | parcial: condição e função de traçado por atributo ficam com o item de traçado avançado |
| traçado conectado | connected trace | `tipo=conectado` (item L4-02-a) | feito |
| traçado a montante / a jusante | upstream / downstream trace | `tipo=montante` / `tipo=jusante` | feito |
| caminho mais curto | shortest path trace | `tipo=caminho_curto` (item L4-02-d) | feito |
| barreiras | starting points e barriers | `pontos_partida` e `barreiras`, por feição+terminal ou por coordenada com tolerância | feito |
| áreas sujas | dirty areas marcam onde a topologia gravada ficou velha e o traçado avisa | `rede_topo_area_suja` e o aviso do alcance (item L4-01-b) | feito |
| validar topologia | validate network topology consolida as áreas sujas | `POST /topologia/habilitar` reconstrói tudo; validação incremental por área é fronteira aberta | parcial |
| promover a utility network | não existe: a Esri não converte Trace Network em Utility Network | `POST /promover` carimba o pacote mínimo e muda o modo | além (não tem equivalente) |
| subrede e controlador | Trace Network não tem subrede nem subnetwork controller | `subrede`/`isolados` existem no motor, mas o catálogo mínimo não tem as categorias `transformacao`/`fonte`, então não separam nada numa rede simples | fora (é de rede de utilidades) |

## 6. Fronteira honesta desta passagem

1. Montante e jusante andam pelos TRECHOS. Atravessar um dispositivo multi-terminal pela direção de fluxo
   (usar o campo `montante` de cada terminal do pacote) não está feito — numa rede simples não existe
   dispositivo, e numa rede de utilidades esse traçado é do item de traçado avançado.
2. As feições são COPIADAS das camadas do inquilino na criação. Editar a camada de origem depois não
   atualiza a rede; editar a rede não atualiza a camada de origem. Sincronizar as duas é outro item.
3. `atributos_rede` é declaração e vocabulário: o produto valida os nomes e os publica, e `caminho_curto`
   sabe usar um deles como custo. Condição de traçado por atributo (parar quando `regime = 'intermitente'`)
   não existe ainda.
4. O teto de uma chamada de criação é 200 mil feições por camada. Acima disso a carga precisa virar tarefa
   de importação, não uma chamada de API.
