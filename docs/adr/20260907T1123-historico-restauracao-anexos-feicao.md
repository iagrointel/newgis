# ADR 20260907T1123 — Histórico, restauração e anexos por feição (item L2-03-edicao)

Data: 07/09/2026. Constrói sobre o L2-03-a-api-edicao-transacional (API única de escrita,
`POST /api/camadas/{id}/edicoes`) e o L2-01-mapa-web (visualizador `/mapa`).

## 1. Histórico por gatilho, não por chamada de API

Decisão (C5/C12 do `L2_CONCEITO.md`): o histórico é gravado por um gatilho `AFTER INSERT OR UPDATE
OR DELETE` em `plat.feicao_historico_registrar()`, ligado a TODA tabela `d_<slug>.c_<uuid16>` por
`plat.camada_preparar` (a mesma função que já liga `tg_versao`/`tg_tenant`), e retroativamente a toda
camada já publicada. Isso cobre qualquer escrita — pela API, por SQL direto de manutenção, por uma
futura réplica ou importação em lote — não só o que passa por `app.edicao.servico`. Alternativa
descartada: gravar o histórico dentro de `aplicar_edicoes()` (só cobriria a API).

Descoberta em bancada: `to_jsonb(registro)` converte a coluna `geometry` usando o CAST explícito que o
PostGIS registra (`geometry -> json`, produz GeoJSON com um bloco `crs`), não a saída de texto
(EWKB hex) como se presumiu na primeira versão do gatilho. Confirmado com
`SELECT json(ST_GeomFromText(...))`. O gatilho usa isso diretamente (`(antes -> 'geom') - 'crs'`),
sem reconstruir geometria a partir de hex — mais simples e correto. Achado registrado aqui para quem
mexer de novo num gatilho parecido não reintroduzir a suposição errada.

Geometria não fica em coluna tipada no `plat.feicao_historico` (é `text`, GeoJSON serializado): o
gatilho é genérico para qualquer tabela de camada, com ou sem coluna `geom`, e o SRID de exibição é o
mesmo da camada (nunca transformado aqui).

## 2. Restauração pela MESMA porta de escrita

`historico.restaurar()` não escreve a tabela de camada por conta própria: monta o `UPDATE`/`INSERT`
reaproveitando `validar_atributos`/`_preparar_geometria`/`_exigir_dono_ou_admin` de
`app.edicao.servico` (C5 do conceito: uma porta, gatilhos e regras valem para qualquer caminho).
Consequência deliberada: uma regra de domínio pode ter mudado depois que o histórico foi gravado —
restaurar não pula a validação atual (`test_restaurar_domino_atual_ainda_e_aplicado`).

Duas formas de restauração:
- feição ainda existe → `UPDATE` para o estado gravado em `atributos_depois`/`geom_depois` da entrada
  escolhida (a versão otimista da linha atual continua valendo).
- feição foi apagada → `INSERT` com o MESMO `globalid` (não um novo), para que qualquer referência
  externa (anexo, seleção salva, link direto) continue válida depois da restauração.

A restauração em si grava DUAS entradas novas no histórico: a mecânica (`'atualizar'`/`'inserir'`,
gravada pelo MESMO gatilho genérico que qualquer escrita dispara) e um marcador explícito
(`'restaurar'`), para quem consulta o histórico distinguir uma restauração de uma edição comum sem
ambiguidade. O histórico nunca é reescrito, só cresce.

Restaurar a entrada de uma EXCLUSÃO (`operacao='apagar'`) é recusado (409 `nada_a_restaurar`): essa
entrada só tem `atributos_antes` (o estado ANTES de apagar), não um "depois" — a entrada certa para
recriar a feição é a anterior a ela (`'inserir'` ou o último `'atualizar'`).

## 3. Anexos: reuso do adaptador de objetos (L0-11), tabela de ligação nova

Limite de tamanho e de tipo aplicados no servidor, em duas etapas: teto no comprimento da string
base64 (barato, antes de decodificar) e teto no tamanho decodificado real
(`limites.ANEXO_TAMANHO_MAX`); tipo contra uma lista fechada (`limites.ANEXO_TIPOS_PERMITIDOS`) e
contra o conteúdo de fato (`app.varredura_conteudo.escanear_cabecalho`, item L7-03-b — um PDF
disfarçado de PNG é recusado mesmo com `content_type` mentindo).

O objeto em si vive no Garage por trás de `app.objetos.guardar` (bucket por inquilino, cota,
deduplicação por sha256 — nada novo). `plat.feicao_anexo` só liga `(schema, tabela, globalid)` ao
objeto guardado, porque `plat.arquivo` não conhece feição.

`ANEXO_TIPOS_PERMITIDOS` é uma TUPLA ordenada, não um `frozenset`: `docs/gerar_limites.py` grava o
`repr()` literal do valor em `docs/LIMITES.md`, e a ordem de iteração de um `set`/`frozenset` do
Python não é determinística entre execuções — um frozenset faria o documento gerado variar a cada
`make limites` sem nada ter mudado de verdade (achado nesta rodada, corrigido antes de commitar).

## 4. Rotas novas (todas sob `/api/camadas/{id}/feicoes/{globalid}/...`)

| rota | privilégio | o que faz |
|---|---|---|
| `GET .../historico` | leitura da camada | lista quem/quando/o quê, mais recente primeiro |
| `POST .../historico/{historico_id}/restaurar` | `feicoes.editar\|feicoes.editar_total` | restaura |
| `GET .../anexos` | leitura da camada | lista anexos da feição |
| `POST .../anexos` | `feicoes.editar\|feicoes.editar_total` | envia anexo (JSON base64, sob cookie) |
| `GET .../anexos/{anexo_id}` | leitura da camada | baixa o anexo |
| `DELETE .../anexos/{anexo_id}` | `feicoes.editar\|feicoes.editar_total` | apaga (soft-delete) |

Entrada de anexo por JSON base64 sob cookie de sessão, não corpo cru: o mesmo motivo do
`app/catalogo/rotas_miniatura.py` (CSRF sob cookie exige `application/json` em todo verbo de escrita;
corpo cru exigiria token de serviço, ver `app/rotas_arquivos.py`).

`app/mapa/rotas.py::_ficha()` ganhou 4 chaves aditivas (`editavel`, `regras_campo`,
`somente_proprias`, `geometria_travada`) para a tela de edição saber o que pode fazer sem abrir outra
rota — nunca expõe schema/tabela do banco.

## 5. Fronteira honesta

- Concorrência otimista, domínio/obrigatório no servidor e isolamento entre inquilinos são
  responsabilidade do L2-03-a (não reimplementados aqui) — este item reconfere as duas primeiras
  cláusulas a partir do caminho de restauração e de um novo teste "direto na API" para provar que a
  refutação do item-pai também vale por aqui.
- Split/união de feição, aderência (snapping) visual e edição em lote ficam na camada de FRONTEND
  (ver handoff): o backend já aceita lote heterogêneo (`adicionar`/`atualizar`/`apagar` na mesma
  chamada), então "editar em lote" e "unir duas linhas num único polígono" são composições no
  navegador sobre a MESMA API, não rotas novas.
