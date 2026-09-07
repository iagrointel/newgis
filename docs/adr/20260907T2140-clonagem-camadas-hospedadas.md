# ADR 20260907T2140 — Clonagem de camadas hospedadas e tabelas de um FeatureServer da Esri (item L2-08-b)

Estado: aceito (07/09/2026). Linha L2, sobre o leitor de portal (L2-08-a), a criação de camada (L0-04-c), os
domínios/subtipos (L2-10-a) e os relacionamentos (L2-10-b).

## D1. Um só caminho de dados nesta rodada: `query` paginada por `resultOffset` (ou por `objectIds`)

O portão lista dois caminhos (exportação de File Geodatabase por `createReplica`/`exportItem` e `query`
paginada). Só o segundo foi construído: não exige permissão de exportação do dono, funciona em serviço
público e em Portal, e o OpenFileGDB entraria num job pesado com arquivo temporário (disco a 93 %). Quando o
serviço não pagina por `resultOffset`, o motor lê os `objectIds` e busca em fatias. O caminho por FGDB fica
registrado como não feito.

## D2. Dados antes dos domínios; valor fora do domínio vem como está

O Portal da Esri não valida o dado gravado contra o domínio declarado (a amostra pública gravada tem
`Unassigned-spike` num campo cujo domínio não o contém). O gatilho de domínio da casa (L2-10-a) valida em
INSERT/UPDATE, então a cópia fiel carrega as linhas primeiro e liga os domínios depois; o gatilho passa a valer
para edições novas. Os `types` da Esri só viram subtipos quando o `typeIdField` é inteiro (o modelo da casa é
`subtipo_codigo int`); tipos de feição com id texto ficam de fora com aviso no relatório.

## D3. Relacionamento 1:N com chave de origem repetida vira N:M por junção

A classe 1:N/1:1 da casa cria chave estrangeira e índice único sobre a chave de origem
(`plat.relacionamento_fk_aplicar`). Quando o dado clonado repete a chave (a amostra pública tem 20 feições e
14 `requestid` distintos), a relação é recriada como N:M na tabela de junção `plat.relacionamento_junc`,
preenchida com os pares presentes no dado — `queryRelatedRecords` devolve o mesmo resultado, e o relatório
diz por quê.

## D4. Nome de campo, tipo e rastreio

Nomes passam pela mesma regra da ingestão (`app/ingestao/nomes.normalizar`); `OBJECTID`/`GlobalID` viram
`oid_origem`/`globalid_origem` (o `fid`/`globalid` da casa são novos); `Shape__Area`/`Shape__Length` são
descartados com aviso; campos de rastreio da Esri (`editFieldsInfo`) viram atributos `origem_*`; datas em
milissegundos (inclusive negativas) viram `timestamptz`; `102100` vira `3857`, e a referência do serviço
(`extent.spatialReference`) prevalece sobre a de origem.

## D5. Anexos no armazém de objetos; re-execução por assinatura

Anexos vão para o Garage por `app/objetos.guardar` (classe `feicao_anexo`, sha256, item = globalid da feição)
e, quando a tabela de vínculo do L2-03-e existir na base, ganham a linha em `plat.feicao_anexo`. A segunda
execução compara a assinatura da camada (`editingInfo.lastEditDate`; sem ele, a contagem de feições da origem)
com a gravada e não escreve nada quando é igual (`escritas = 0`).

## D6. A plataforma pode ser fonte de si mesma

`X-Esri-Authorization: Bearer` (o cabeçalho dos clientes Esri e do nosso leitor de portal) passou a valer como
`Authorization` na resolução de sessão: o FeatureServer da própria plataforma serve de fonte de teste sem
credencial de parceiro (D20 continua aberta).
