# Procedência do item de dado

Item `L0-09-a-procedencia`. Vale para todo item que carrega dado: camada vetorial, raster, arquivo, cena,
vista de camada e conexão externa.

O bloco de procedência responde a uma pergunta só: **de onde veio este dado, quem afirmou o quê, e como se
refaz a conta**. Ele fica em `plat.item.dados.procedencia` (jsonb) e usa o mesmo vocabulário que a casa já
usa em dois lugares: o registro do acervo (`acervo.fonte`, 376 fontes, e a régua `acervo.v_completude`) e o
catálogo de camadas do motor logístico. Quem lê a ficha de uma fonte em `GET /api/acervo/{id}` e o bloco de
um item do catálogo lê os mesmos nomes com o mesmo sentido.

Regra que manda em tudo o que está escrito aqui: **procedência errada é pior que procedência nenhuma**
(decisão D17). Por isso nenhum campo é inferido do nome do arquivo, nenhum campo tem valor padrão, e campo
sem valor é `null` — nunca texto vazio.

## Os campos

`origem` diz, campo a campo, quem afirmou: `declarado` (a pessoa ou o serviço externo afirmou) ou `medido`
(esta máquina calculou). Origem de campo vazio é descartada na gravação.

| campo | o que é | equivalente no acervo | conta na pontuação |
|---|---|---|---|
| `fonte` | nome da fonte ou do arquivo de origem | `acervo.fonte.nome` | não |
| `url` | endereço público da fonte (apelido aceito na entrada: `fonte_url`) | `acervo.fonte.url` | sim |
| `licenca` | licença escrita da fonte, como ela está publicada | `acervo.fonte.licenca` | sim |
| `data_do_dado` | a que data o dado se refere (apelido: `data_dado`) | `acervo.fonte.data_dado` | sim |
| `data_de_acesso` | quando o dado entrou aqui (apelido: `data_acesso`) | `acervo.fonte.data_acesso` | não |
| `gerador` | script ou job que produziu o item (apelido: `script_gerador`) | `acervo.fonte.script_gerador` | sim |
| `sha256` | hash do conteúdo de origem, em hexadecimal | `acervo.fonte.sha256` | sim |
| `comando_reexecucao` | comando que recalcula o hash (apelido: `sha256_cmd`) | `acervo.fonte.sha256_cmd` | não |
| `metodo` | como o dado foi carregado ou transformado | `acervo.fonte.metodo` | sim |
| `confianca` | o quanto se confia no valor, em uma frase | `acervo.fonte.confianca` | sim |
| `limites` | o que o dado não permite concluir; texto ou lista de avisos | `acervo.fonte.limites` | sim |
| `frescor` | com que periodicidade a fonte se atualiza | `acervo.fonte.frescor` | sim |
| `proxima_verificacao` | data da próxima conferência | `acervo.fonte.proxima_verificacao` | sim |
| `responsavel` | quem responde por esta ficha | (não existe no acervo) | não |
| `origem` | objeto `{campo: "declarado"\|"medido"}` | (não existe no acervo) | não |

A ingestão também grava `job_id` e `importacao_id`, que ligam o item ao job que o produziu. Campos fora
desta lista são preservados como vieram; a pontuação não os conta.

## A pontuação 0-10

É a régua da `acervo.v_completude`, sem peso próprio: `round(campos / campos_possiveis * 10, 1)` sobre os
**10 campos** marcados na coluna "conta na pontuação" (`url`, `licenca`, `frescor`, `data_do_dado`,
`gerador`, `sha256`, `metodo`, `confianca`, `limites`, `proxima_verificacao`).

Item sem bloco tem pontuação `null`, nunca `0,0`: ausência de registro não é medida de zero. É a mesma
escolha que a ficha da fonte do acervo faz.

A conta existe em dois lugares, e um teste compara os dois campo a campo:

- Python: `app/catalogo/procedencia.py` (`pontuacao`, `campos_preenchidos`, `completude_texto`);
- SQL: `plat.procedencia_pontuacao(dados)`, `plat.procedencia_campos(dados)`,
  `plat.procedencia_licenca(dados)` — usadas pela busca, pelo filtro e pela exportação, para não trazer o
  jsonb para o Python a cada linha.

## O que é preenchido sozinho

Uma camada importada por arquivo nasce com **quatro campos medidos pela máquina**, sem ninguém digitar:

| campo | valor | origem |
|---|---|---|
| `sha256` | hash do arquivo lido de volta do armazenamento, conferido contra o hash gravado no upload | `medido` |
| `data_de_acesso` | data em que o arquivo entrou na plataforma | `medido` |
| `gerador` | `plat ingestao.carregar <versão>` | `medido` |
| `metodo` | `ogr2ogr + ST_MakeValid` | `medido` |

`fonte` recebe o nome original do arquivo, com origem `declarado` — quem nomeou o arquivo foi o usuário.
`url` e `licenca` ficam `null` de propósito: deduzi-las do nome do arquivo seria inventar procedência.

Uma camada publicada a partir de conexão externa (WMS, WFS, WMTS, ArcGIS REST, STAC, OGC API) recebe o que
o próprio serviço declara no `GetCapabilities`/`?f=json` (com origem `declarado`) e o que a sondagem mediu
— hash do corpo lido, data de acesso, método, limites e frescor (com origem `medido`). Protocolo sem
metadado padronizado não é sondado: o bloco fica vazio, e não com um palpite.

## Onde a procedência aparece

- **Ficha do item** (`GET /api/itens/{id}` e a tela do item, aba Visão geral): o bloco campo a campo, com a
  etiqueta de origem em cada campo, e a pontuação como `4,0/10`.
- **Lista** (`GET /api/itens`): cada item traz `procedencia` com `pontuacao`, `campos`, `campos_possiveis`,
  `completude_texto` e `licenca`, para a lista mostrar o selo sem um pedido por item.
- **Busca**: `licenca:CC` casa por trecho da licença registrada; `licenca:nenhuma` acha o que não tem
  licença escrita; `procedencia:[5 TO 10]` filtra por faixa de pontuação e `procedencia:5` por mínimo.
- **Filtro lateral**: `?licenca=<valor>` (repetível, aceita `nenhuma`) e `?procedencia_min=<0-10>`;
  `GET /api/itens/facetas` devolve a contagem por licença.
- **Exportação da lista** (job `catalogo.exportar_lista`): CSV com as colunas `licenca`,
  `procedencia_pontuacao`, `procedencia_campos`, `procedencia_sha256` e `procedencia_gerador`; JSON com o
  bloco inteiro no campo `procedencia`.
- **Metadado ISO 19139** (`GET /api/itens/{id}/metadado.xml`): o bloco vira `dataQualityInfo`/`lineage`.
  Item sem bloco não ganha um texto genérico no lugar: o elemento simplesmente não sai.

## O que ainda não leva procedência

A exportação do inquilino inteiro em GeoPackage (item `L0-06-d-exportar-inquilino`) ainda não existe. A
frase do portão "exportação leva a procedência" está cumprida na exportação que existe hoje — a lista do
catálogo, nos dois formatos. Quando o `L0-06-d` for construído, o bloco entra na tabela de metadado do
GeoPackage pela mesma função SQL.
