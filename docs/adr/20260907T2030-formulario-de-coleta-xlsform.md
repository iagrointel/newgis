# ADR 20260907T2030 — Formulário de coleta por XLSForm (item L2-07-b)

Estado: aceito (07/09/2026). Linha L2. Construído sobre a linguagem de expressão própria (L2-10-c, C6) e a
API de edição transacional (L2-03-a, C5).

## D1. O documento de formulário é um item de catálogo (`plat.tipo_item` = `formulario`), não tabela nova

O XLSForm importado vira um JSON gravado em `plat.item.dados` (esquema no `tipo_item`), ligado à camada de
destino por `plat.item_relacao` (`formulario_de_camada`). Compartilhamento, lixeira, versões e RLS vêm de graça.
O JSON é o precursor do documento do construtor arrasta-e-solta (L5-03): campos em árvore (grupo/repetição),
rótulos por idioma, e cada regra guardada como `{origem (XPath), texto (linguagem própria), ast}` — quem consome
usa o AST (C6). Custo de mudar: baixo (o L5-03 acrescenta chaves, não troca o formato).

## D2. Tradução por tabela de função com três estados, nunca tradução silenciosa

`app/coleta/xpath.py` tem um analisador do XPath de XLSForm e uma tabela `TABELA_XLSFORM` por função:
`feito`, `parcial` (registrado em aviso) ou `fora`. Uma regra com parte `fora` é descartada inteira e o aviso
fica no documento com campo, papel, função e trecho. Fora de propósito: `regex` (o Arcade também não tem; no
servidor seria vetor de ReDoS e os dialetos de Python e JavaScript divergem), `date`/`format-date`
(conversão de texto em data não é determinística entre os dois motores), `uuid`/`random` (não determinísticos —
o servidor gera o globalid), `position`/`indexed-repeat` (índice de repetição não é exposto). Parcial:
`pulldata` só pela coluna `name`; `max`/`min` só com argumentos escalares. A tabela é publicada em
`GET /api/formularios/equivalencia` e conferida por 102 vetores em `tests/expressoes/vetores_xlsform.json`
avaliados em Python e em JavaScript (`tests/unit/test_coleta_xpath.py`).

## D3. Dois motores, um AST, um contexto

O navegador (`web/js/coleta/motor.js`) e o servidor (`app/coleta/motor.py`) avaliam o mesmo AST com o mesmo
contexto (`$campo`, `$_valor`, `$rep`, `$rep__coluna`, `$_lista_<nome>`, `$_linha`; datas em ms UTC). O
navegador serve para a tela reagir (relevância, cascata, cálculo, erro por campo) e para barrar o envio; o
servidor refaz tudo antes de gravar e nunca confia no cliente: campo não relevante vira NULL, restrição
violada ou obrigatório ausente devolve 422 com a lista de erros e NADA é gravado (refutação do item).
Cálculo com dependência circular é detectado na importação (ordenação topológica) e no navegador, com o
mesmo código `dependencia_circular`. `tests/unit/test_coleta_motor_equivalencia.py` roda os dois motores
sobre as mesmas respostas.

## D4. Repetição = camada filha + `pai_globalid`

`begin repeat` cria uma segunda camada hospedada (`criar_camada`, mesmo preparo da ingestão) com as colunas da
repetição mais `pai_globalid uuid` e `indice`. A resposta grava a feição pai e depois as N linhas na mesma
transação, pela mesma `aplicar_edicoes`. A classe de relacionamento formal (`plat.relacionamento`, L2-10-b)
ainda não está em master; quando estiver, a relação 1:N `globalid -> pai_globalid` é um INSERT por formulário.
Repetição aninhada é recusada (422).

## D5. Camada sem geoponto declara `geometria: nenhuma`

A coluna `geom` física existe sempre (`plat.camada_preparar` cria o índice GiST sem condição), mas o item
declara `nenhuma` para a API de edição não exigir geometria; com geoponto a camada é `Point` (lat lon do
XLSForm vira GeoJSON lon lat). Achado no caminho: o gatilho de histórico (L2-03-d) quebrava em linha com
geometria nula (`to_jsonb(NEW) -> 'geom'` é o jsonb `null`, e `null - 'crs'` é erro); consertado em migração
nova (`20260907T2020_historico_geom_nula.sql`), sem editar a aplicada.

## Fora deste item (brief do 07/09)

Geoponto com GPS/precisão, foto com compressão e EXIF, áudio, assinatura, código de barras e a fila off-line
(L2-07-c) ficam para os itens irmãos; aqui o valor de geoponto é aceito como texto "lat lon" e os demais tipos
são guardados como texto com aviso.
