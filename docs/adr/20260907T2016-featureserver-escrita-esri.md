# ADR 20260907T2016 — escrita compatível com o protocolo Esri sobre a porta única (item L2-04-d)

Estado: aceito · turno 4 · complementa o ADR 20260907T0216 (edição transacional) e o ADR 0018 (query do
FeatureServer).

## Contexto

O item L2-04-c deu leitura Esri (`query`). Falta a escrita: é ela que decide se o cliente troca o ArcGIS
Enterprise sem trocar a ferramenta, porque o ArcGIS Pro, o Field Maps e o Map Viewer escrevem por
`applyEdits`, `addFeatures`, `updateFeatures`, `deleteFeatures`, pelos anexos e por `uploads/upload`.

A casa já tem UMA porta de escrita de feição (`POST /api/camadas/{id}/edicoes`, item L2-03-a), com validação
de tipo, domínio, CRS, propriedade e concorrência otimista, e já tem anexos por feição (item L2-03-e).

## Decisões

### 1. O protocolo Esri é tradução, não uma segunda porta de escrita

`app/consulta/rotas_edicao_esri.py` traduz o pedido Esri para `EdicoesEntrada` e chama
`app.edicao.servico.aplicar_edicoes`. Nenhuma rota deste arquivo escreve em tabela de camada por conta
própria. Consequência prática: toda regra escrita para a API da casa vale de graça para o cliente Esri, e o
adversário só tem uma superfície para atacar.

### 2. Código HTTP real E corpo no formato Esri

A Esri responde HTTP 200 com o erro dentro do corpo (`{"error": {"code": 403, "message": ...}}`). Um servidor
que copia isso engana proxy, painel de monitoramento e log: tudo lê 200 onde houve recusa. Decidido: devolver
o **código HTTP real** (403, 404, 400) **e** o corpo no formato Esri, com `code` repetindo o status. O cliente
que lê o corpo (é o que a biblioteca da Esri faz) continua funcionando; o cliente que lê o status passa a
receber a verdade.

Limitação honesta: isto NÃO foi conferido contra o cliente Python `arcgis` nem contra ArcGIS Pro/Field Maps
reais. O pacote `arcgis` não está instalado nesta máquina (disco a 93 %) e não há ambiente gráfico para QGIS.
Fica `pendente` na coluna Pro/AGOL real do `docs/PARIDADE.md`, como manda a decisão D20.

### 3. `rollbackOnFailure` é um SAVEPOINT, e a resposta continua sendo o vetor de resultados

Cada feição roda em modo `parcial` (savepoint por feição, mecanismo que o L2-03-a já tinha). O lote inteiro
corre dentro de um `SAVEPOINT esri_lote`; se houve qualquer falha e `rollbackOnFailure` é verdadeiro (padrão,
como no Enterprise), volta ao ponto e nada é gravado — mas a resposta ainda diz, feição a feição, qual falhou,
com `rolledBack: true`. Isso é o que o cliente precisa para corrigir e reenviar.

### 4. `objectId` é `fid`, `globalId` é `globalid`, anexo tem número

O protocolo Esri identifica anexo por inteiro. O identificador da casa é uuid. Em vez de mudar a chave, a
migração 20260907T1927 acrescenta `numero bigserial` em `plat.feicao_anexo`: uuid continua sendo a chave,
`numero` é o rosto Esri.

### 5. `origem` no histórico, por parâmetro de sessão

O portão pede que a edição vinda do FeatureServer seja distinguível. `plat.feicao_historico` ganha `origem`
(padrão `'api'`), preenchida pelo gatilho a partir de `current_setting('plat.origem')` — mesmo mecanismo de
`plat.tenant_id`/`plat.usuario_id`. Vale para qualquer escrita, inclusive a que não passa pela API.

### 6. `calculate` avalia no motor de expressão da casa, nunca em SQL do cliente

`calcExpression[].sqlExpression` é reescrito para a sintaxe do item L2-03-f (`$campo`) por uma tradução que só
aceita identificador que É campo da camada ou função da `TABELA_FUNCOES` do avaliador; qualquer outro nome é
recusado com 400 antes de qualquer avaliação. O valor calculado volta pela porta única de escrita. Nenhum
texto do cliente vira SQL — `pg_sleep(10)` como expressão é 400, não uma consulta.

### 7. Uma camada por serviço (id 0), como no L2-04-c

O diretório completo do serviço é o item L2-04-b. Enquanto ele não existe, estas rotas moram sob o mesmo
prefixo que a operação `query` já usa, e `camada_id` diferente de `0` é 404.

## O que ficou de fora

- Polígono Esri com vários anéis EXTERNOS (multiparte) entra como um `POLYGON` com anéis internos: o WKT é
  montado por `app/consulta/geometria_esri.py::para_ewkt`, que não separa parte de buraco. Quem precisa de
  multiparte manda uma feição por parte ou usa a API da casa.
- `attachments` dentro de `applyEdits` grava o bloco no depósito de objetos antes do fim da transação: um
  `rollbackOnFailure` desfaz a LINHA do anexo, mas o bloco fica no Garage sem referência (a limpeza de objeto
  órfão é do item de retenção).
- `trueCurveClient`, `gdbVersion`, `sessionID`, `honorSequenceOfEdits`, `usePreviousEditMoment`: aceitos e
  ignorados, sem curva verdadeira e sem versionamento por branch nesta passagem.
