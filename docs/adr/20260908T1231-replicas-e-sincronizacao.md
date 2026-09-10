# ADR 20260908T1231 — Réplicas para trabalho desconectado e sincronização

Item `L2-13-b-replicas-sincronizacao`. Estado: aceita.

## Contexto

Trabalho de campo acontece sem rede. A plataforma precisa entregar um recorte declarado de camadas num
arquivo que o aparelho abre sozinho, aceitar as edições feitas fora de rede quando o aparelho volta, e
devolver ao aparelho o que o servidor mudou nesse meio-tempo — sem que os dois lados se sobrescrevam em
silêncio. É o `createReplica` / `synchronizeReplica` / `extractChanges` do ArcGIS Enterprise, e é a base do
L2-07-c (PWA de campo), do L2-04-k e do uso com o QField.

## Decisões

### 1. O relógio é `plat.feicao_historico.id`; nenhuma tabela de rastreio nova

O gatilho de histórico do item L2-03-edicao (migração `20260907T1025`) já grava uma linha por INSERT, UPDATE
e DELETE em toda tabela `d_<slug>.c_<uuid16>`. O DELETE é o ponto decisivo: a tabela de camada não guarda a
feição apagada, então sem essa tabela não há como responder "o que mudou" com exclusões. O `id bigserial`
dela é um contador monotônico, e "o que mudou desde a geração G" vira `id > G` sobre o índice
`ix_feicao_historico_desde (tenant_id, schema_dado, tabela_dado, id)` — nunca uma varredura da camada.
É o rastreio (fid, versão, momento) que o L2-03-d prevê, e ele já existe: construir um segundo seria
duplicar a fonte de verdade.

Limitação assumida: o `id` é atribuído no INSERT, não na confirmação da transação. Uma transação concorrente
que confirme depois da nossa leitura pode ter `id` menor que a geração nova e só aparecer na sincronização
seguinte. Isso ATRASA uma mudança, nunca a perde — o ponteiro por camada só avança até o que foi lido. A
alternativa (instantâneo de `txid` ou trava sobre a camada inteira) custa mais do que o problema vale neste
turno; se um dia custar menos, o lugar de mudar é `servico.relogio`.

### 2. A sincronização escreve pela porta única do L2-03-a

`app/replica/servico.py` chama `app.edicao.servico.inserir/atualizar/apagar` — o mesmo código de
`POST /api/camadas/{id}/edicoes`. Mesma validação de tipo, domínio, geometria, RLS e "só as próprias
feições". A réplica acrescenta a POLÍTICA DE CONFLITO em volta; não é uma segunda porta de escrita. Por isso
`app/edicao/servico.py` ganhou três aliases públicos (`inserir`, `atualizar`, `apagar`): a sincronização
precisa decidir feição a feição — conferir a versão, escolher pela política, só então aplicar — o que o
laço de `aplicar_edicoes` não permite.

### 3. Três políticas de conflito, escolhidas na criação da réplica

`servidor_vence` (padrão), `cliente_vence`, `pergunta`. Conflito é sempre RELATADO, mesmo quando resolvido:
a resposta traz `versao_cliente`, `versao_servidor`, a resolução e a feição atual do servidor. Em
`cliente_vence` a atualização é reaplicada sobre a versão ATUAL do servidor (nunca sobre a versão velha que
o cliente leu — isso faria a checagem otimista falhar), e o histórico do L2-03-edicao guarda o que foi
sobrescrito. Apagar uma feição que já não existe é sucesso silencioso: apagar duas vezes é apagar uma.

### 4. Idempotência é do LOTE, não da feição

`plat.replica_sincronizacao` guarda a resposta inteira sob `(replica_id, idempotencia)`. Repetir o mesmo
lote devolve a MESMA resposta, com `repetida: true`, aplica zero e não avança a geração. É a única defesa
possível contra duplicar um `adicionar`: uma feição nova não tem versão anterior com que discordar, então
nenhuma checagem otimista a protege. A chave é gerada pelo cliente e repetida em toda retentativa.

### 5. O pacote é GeoPackage escrito por `ogr2ogr`, e o contexto de inquilino viaja por `PGOPTIONS`

A tabela física de camada tem `FORCE ROW LEVEL SECURITY` por `tenant_id = plat.tenant_atual()`, e
`tenant_atual()` lê o GUC de sessão `plat.tenant_id`. O `ogr2ogr` abre conexão PRÓPRIA, que não herda o
contexto da conexão da aplicação: sem o GUC ele leria **zero linha em silêncio** e entregaria um pacote
vazio, sem erro nenhum. O contexto vai pela variável de ambiente `PGOPTIONS` do subprocesso (`-c
plat.tenant_id=<n>`), que a libpq manda ao servidor no arranque — medido nesta base antes de escrever o
módulo. E porque "medido uma vez" não basta para uma falha que é invisível, `pacote.escrever` compara a
contagem lida pelo ogr com a contagem lida pela conexão da aplicação e levanta `pacote_incompleto` se
divergirem. A senha nunca vai na linha de comando (`ps` é legível por qualquer usuário): vai por
`PGPASSWORD` no mesmo ambiente.

O filtro por camada é escrito na linguagem `where` do FeatureServer e passa pelo analisador AST de
`app/consulta/where_ast.py` (lista branca dos campos daquela camada, SQL com parâmetro). Como o ogr2ogr só
aceita texto, o parâmetro vira literal por `cur.mogrify` — a citação é do psycopg2, nunca concatenação
nossa. O filtro é analisado na CRIAÇÃO da réplica, não no job: filtro inválido reprova a chamada do usuário
com 422, em vez de virar um job que falha meia hora depois.

### 6. O que o pacote leva além das camadas

`plat_sync` (uma linha por feição: camada, fid, globalid, versão — é o que o cliente compara para saber o
que ele mudou), `plat_replica` (uma linha por camada: geração do servidor, filtro, política, validade),
`plat_dominio` (os valores de domínio de `dados.regras_campo`, para o aparelho montar lista fechada) e
`plat_anexo` (metadado dos anexos, quando pedido). As três primeiras entram como tabelas de atributo
registradas em `gpkg_contents` — é o `ogr2ogr` que as registra; escrever direto por sqlite3 as deixaria
invisíveis ao GDAL e ao QGIS. `-lco FID=linha_id` é obrigatório nelas: sem isso o driver GPKG adota a coluna
`fid` do CSV como chave primária e a segunda camada da réplica estoura por chave duplicada (cada camada
numera os seus fid a partir de 1).

O conteúdo binário dos anexos NÃO vai no pacote, só o metadado. Baixar a foto exige rede. Embutir o binário
estouraria o teto declarado do arquivo de campo, e é decisão de produto, não deste item.

### 7. Validade da réplica < retenção do rastreio

`REPLICA_VALIDADE_DIAS = 30`, `REPLICA_RASTREIO_RETENCAO_DIAS = 45`. A ordem importa e é provada em
`tests/unit/test_replica_limites.py`: se a réplica pudesse viver mais do que o rastreio é retido, a
sincronização devolveria um conjunto de mudanças INCOMPLETO **sem erro nenhum** — o pior desfecho possível,
porque quem está no campo não teria como perceber. Réplica vencida recebe 409 `replica_expirada` e a saída é
criar réplica nova. Ainda não existe job que expurgue `plat.feicao_historico`; quando existir, tem de
respeitar essa retenção.

### 8. Privilégio e escopo já existentes

`campo.coletar` (o perfil `campo` já o tem — trabalho desconectado é a mesma permissão da PWA de campo) para
todas as rotas; a sincronização exige ainda `feicoes.editar` ou `feicoes.editar_total`, porque escreve
feição. Escopo de token: `camada:ler` para as leituras, `camada:editar` para a sincronização. Nenhum
privilégio novo, nenhum escopo novo: o vocabulário só cresce quando o que existe não cobre.

Isolamento: a RLS de `plat.replica` decide (réplica de outro inquilino é 404, não 403), o dono é conferido
por `_exigir_dono`, e sincronizar uma camada que não está no recorte declarado da réplica é 404
`camada_fora_da_replica` — mesmo que a camada exista e seja legível pelo usuário. O pacote de campo não pode
virar porta para escrever fora do que foi declarado.

## Alternativa considerada e recusada

**QFieldCloud auto-hospedado** como mecanismo de sincronização, em vez do nosso. Recusada por ora e
registrada como alternativa viva (decisão D35 do dono, PWA própria × QFieldCloud auto-hospedado): o
GeoPackage que este item gera é exatamente o formato que o QField lê, então as duas rotas convivem — quem
quiser o QFieldCloud usa o pacote como origem, e quem quiser a nossa PWA usa a rota de sincronização daqui.
O que a nossa rota dá e o QFieldCloud não daria: a política de conflito ligada ao mesmo motor de versão da
edição on-line, o mesmo histórico, a mesma RLS por inquilino e a mesma auditoria de evento.

## Consequências

Uma migração nova (`20260908T1231`), um tipo de job (`replicas.criar`), seis rotas, nenhum privilégio novo,
nenhuma dependência nova. O item L2-03-a foi lido e reusado, não reescrito. Quem for construir o L2-07-c
(PWA de campo) tem aqui a metade do servidor pronta: falta a tela e o armazenamento local do aparelho.
