# O sistema `plat`, de ponta a ponta

Este documento explica o que o repositório `/home/dev/plataforma/enterprise` constrói, para quem chega sem contexto e
precisa entender o todo antes de abrir o código. Ele resume o que já existe (`ARQUITETURA.md`, `docs/PARIDADE.md`), o
que vai existir (`laco/decomposicao/*_CONCEITO.md`, `laco/estado.json`) e como se constrói
(`laco/SKILL_plataforma-enterprise.md`, `PLANO_DA_CORRIDA.md`). Estado do produto: análise / beta privado. Todo número
citado traz a fonte entre parênteses. Data de referência: setembro de 2026.

## O objetivo final

O ponto de chegada de tudo o que está neste repositório é um único item do backlog, `L7-05-producao-final`. Ele
depende dos outros 505 itens (`laco/estado.json`, 506 itens em 06/09/2026). Só fecha quando todos estiverem
`entregue`, quando um roteiro de demonstração de 30 minutos (`docs/DEMO.md`) for percorrido por teste automatizado,
quando a varredura de placeholder do driver der zero e quando um adversário final não achar nenhuma função que
funcione diferente do manual.

Esse item é o momento de entregar as chaves. Um cliente que hoje paga licença de uma plataforma SIG corporativa
proprietária passa a operar a própria plataforma, em pilha 100 % aberta, com os dados dele, na infraestrutura dele ou
na nossa. O que ele usa hoje continua funcionando: mapa web, edição de feições, serviços que o ArcGIS Pro e o QGIS
consomem, painéis, formulários de campo e imagens. O que ele ganha é o que a plataforma proprietária não oferece no
Brasil: o acervo de dado brasileiro com procedência e licença escrita (376 fontes registradas, 68 com licença escrita
em 06/09/2026, `L3L6_CONCEITO.md` seção 0), o motor multicritério explicável (fator, critério, favorabilidade 0-100,
peso escolhido pelo usuário, `L3L6_CONCEITO.md` A1-A5), a rede de utilidades com traçado e regras (`L4_CONCEITO.md`) e
um custo medido por armazenamento, processamento e tráfego, sem crédito por operação e sem assento por usuário
(`L0_CONCEITO.md` D16; `L1_CONCEITO.md` C20).

No dia da entrega, o cliente vê quatro coisas. Primeiro, a instalação: um pacote assinado (Ed25519, `L7_CONCEITO.md`
C2) que sobe por `install.sh` ou por docker compose, com o mesmo esquema de banco nos dois caminhos (`L7_CONCEITO.md`
C1). Segundo, o conteúdo dele migrado: camadas hospedadas, mapas web, grupos e formulários clonados do portal antigo
por token dele, com um relatório do que entrou e do que não entra (`L2-08-migracao-agol`, item pendente). Terceiro, os
serviços no ar: FeatureServer compatível, OGC API Features, WFS, WMS, WMTS, tiles vetoriais e raster, STAC, todos com
token no caminho da URL e log de leitura (`L2_CONCEITO.md` C9; `L1_CONCEITO.md` C6). Quarto, a operação visível:
página de disponibilidade com 12 meses de histórico, registro do ensaio mensal de restauração de backup e log de
correções de segurança (`L7_CONCEITO.md` C17; `/home/dev/plataforma/DOC.md` seção 8).

O parceiro de canal vende o que ele já vende hoje: a montagem do aplicativo, a configuração das camadas, a migração e
o serviço de acompanhamento. A diferença é que a licença por assento e por crédito vira uma assinatura da plataforma,
sem crédito e sem assento, e o construtor de aplicações (linha L5) é a ferramenta dele, não do cliente final (`DOC.md`
seção 20). O material de canal é agnóstico de fornecedor e nunca cita nome de cliente (regra da casa,
`SKILL_plataforma-enterprise.md` P7).

A casa mantém como receita recorrente o contrato de manutenção e evolução, com prazo, responsável nomeado, acordo de
nível de serviço com crédito quando houver segunda máquina de réplica (`L7_CONCEITO.md` C4) e um humano no laço de
suporte apoiado por agentes que nunca escrevem no ambiente do cliente sem aprovação humana (`L7_CONCEITO.md` C16).
Nunca uma licença: o código é aberto, o dado é do cliente e a exportação do inquilino inteiro em formato aberto é
parte do produto (`L0_CONCEITO.md` D15).

## O que é e para quem

`plat` é o codinome de uma plataforma SIG corporativa em pilha 100 % aberta. O nome público ainda não foi decidido
(decisão D18 do dono, `laco/estado.json`). SIG é sistema de informação geográfica: catálogo de dados com geometria,
mapas, edição, análise e serviços para outros programas. O objetivo declarado do laço de construção é substituir o
ArcGIS Enterprise para o cliente, sem que ele encontre buraco no que usa hoje (`laco/estado.json`, campo `objetivo`).

A plataforma é multi-inquilino: uma instalação atende várias organizações, chamadas inquilinos, isoladas entre si no
banco, no armazenamento de objetos e nos tokens (seção "Como o isolamento entre clientes funciona"). Hoje existem três
inquilinos de demonstração, `demo`, `demo2` e o inquilino técnico `plataforma`, semeados pelo instalador
(`README.md`).

O cliente ganha quatro coisas. Ele ganha o que usa hoje, sem licença por núcleo, assento ou crédito (`L0_CONCEITO.md`
D5 e D16). Ele ganha o dado brasileiro do acervo da casa, servido por referência, sem cópia, com ficha de procedência
de dez campos (`L3L6_CONCEITO.md` B1 e B11). Ele ganha análise explicável: motor multicritério e rede de utilidades
com base legal e cobertura declaradas por fator. Ele ganha a saída: exportação por inquilino em formato aberto e
migração reversa para o formato do portal antigo (`L2_CONCEITO.md` C1, item L2-08-d).

O parceiro de canal ganha um construtor de aplicações sem código para montar e entregar, um mecanismo de migração para
levar a carteira dele e um produto que não briga com a comissão que ele já recebe sobre assentos de desktop (`DOC.md`
seção 20 e 22). Estado de tudo isto: análise / beta privado. A URL interna é `https://plat.iagrointel.com`, com
`noindex` em toda resposta, nunca linkada de lugar público (`README.md`).

## O caminho do dado, de ponta a ponta

O fio condutor do sistema é o caminho que um dado percorre desde a entrada até virar aplicação operada. Cada etapa
corresponde a uma linha de produto, L0 a L7.

```
ENTRADA                                  CATÁLOGO (L0)                        MAPA E SERVIÇOS (L2)
arquivo vetorial (shp, gpkg, geojson,    item com uuid opaco, tipo,           estilo MapLibre + bloco do construtor
csv)  ............ L0-04 ingestão   -->  JSON Schema por tipo, procedência    documento de mapa por uuid
imagem (GeoTIFF, JP2) . L1-01 COG   -->  (10 campos), licença, tags,     -->  tiles vetoriais (Martin, PMTiles)
serviço externo (WMS, WFS, STAC,         busca FTS, grupos, compartilha-      tiles raster (TiTiler)
ArcGIS REST, S3) .... L6-02 conexão -->  mento, lixeira 30 d, versões,        FeatureServer / OGC API / WFS / WMS /
acervo da casa (376 fontes) L6-01   -->  relações, cota, eventos              WMTS / STAC, token no caminho, log
                                              |                                        |
                                              v                                        v
ANÁLISE                                  CONSTRUÇÃO SEM CÓDIGO (L5)           OPERAÇÃO (L7)
motor multicritério (L3): fator ->       documento JSON com nós por ULID,     instalação idempotente, pacote assinado,
critério -> favorabilidade 0-100 ->      app, painel, formulário, fluxo,      backup lógico por inquilino + PITR,
peso do usuário -> explicação            narrativa, relatório; um motor de    métricas com rótulo de inquilino,
rede de utilidades (L4): topologia       widgets, uma linguagem de expressão, medição de uso por dia, modo somente-
derivada, traçado, subrede, BDGD         publicação em /p/<inquilino>/<slug>  leitura, homologação, release
                                                                              com o mesmo sha
FILA DE TRABALHOS (L0-05): tudo que dura mais de 1 s é job em plat.job (SKIP LOCKED + NOTIFY + heartbeat),
executado em processo filho com limite de memória, no contexto do inquilino dono do job.
```

O caminho, em prosa. Um arquivo vetorial entra por upload, passa por inspeção (`ogrinfo`) e vira uma proposta
editável. O usuário confirma o sistema de referência de coordenadas quando ele falta; a plataforma nunca assume
(`L0_CONCEITO.md` D4 e D11). A carga roda como job, por `ogr2ogr`, e cria uma tabela tipada no schema do inquilino,
com `fid`, `globalid`, `versao`, `tenant_id` e política de segurança por linha (`L2_CONCEITO.md` C4;
`docs/PARIDADE.md`, seção "Ingestão vetorial"). Uma imagem entra pelo mesmo padrão e vira COG, o GeoTIFF otimizado
para nuvem, em três perfis declarados, com item STAC no catálogo `pgstac` e objeto nomeado por sha256 no Garage
(`L1_CONCEITO.md` C1-C3). Um serviço externo entra como conexão com credencial cifrada e defesa contra SSRF,
requisição forjada do lado do servidor, e vira camada referenciada ou copiada (`L3L6_CONCEITO.md` B6 e B7;
`ARQUITETURA.md` seção 15).

Tudo isso vira item de catálogo: uma tabela `plat.item` genérica, um registro de tipos com JSON Schema por tipo, um
bloco de procedência em todo item de dado e metadado ISO 19139 gerado (`L0_CONCEITO.md` D2 e D17). O item ganha estilo
no formato MapLibre Style Spec e entra num documento de mapa que referencia camadas só por uuid, nunca por URL
absoluta (`L2_CONCEITO.md` C1 e C2). O mesmo item é servido a programas de fora por três raízes, `/svc/{token}/`,
`/ogc/{token}/` e `/tiles/{token}/`, com o token de serviço no caminho da URL, porque os portais do mercado não
guardam credencial de serviço externo (`L2_CONCEITO.md` C9).

O item é analisado. O motor multicritério extrai o valor bruto por unidade uma vez, como job, e recombina pesos em
milissegundos, no navegador até 50 mil unidades (`L3L6_CONCEITO.md` A2). A rede de utilidades trata as feições como
camadas normais e constrói a topologia como índice derivado, com traçado por pgRouting (`L4_CONCEITO.md` C1 e C2). O
usuário monta aplicação, painel e formulário arrastando widgets; o resultado é um documento JSON com nós identificados
por ULID, versionado e publicado por token de aplicação (`L5_CONCEITO.md` D2, D3 e D10). Tudo é operado com métricas,
medição de uso, backup, release assinado e modo somente-leitura para atualizar sem perder edição (`L7_CONCEITO.md` C2,
C6, C7 e C11).

## As oito linhas de produto

Contagem de itens por linha e estado em `STATUS.md` (06/09/2026 17:51 UTC) e `laco/estado.json` (17:55 UTC).
`STATUS.md` registra 22 provados, 17 parciais, 39 refutados e 428 na fila; o `estado.json` gravado quatro minutos
depois registra 23 entregues. As oito linhas somam 505 itens; o item 506 é um registro de decisão do dono (`D21
(dono)`) que o gerador conta no total.

### L0 fundação

O que entrega: inquilinos, identidade, catálogo, ingestão vetorial, fila de trabalhos, arquivos, cotas, eventos,
backup e administração da organização. Equivalente que substitui: Portal for ArcGIS (Content, Members, Groups,
Organization settings) e a parte de fila do Server. Itens: 72; estado 12/72 provados em `STATUS.md` (13 entregues, 5
parciais, 28 refutados no `estado.json`). O que existe hoje está descrito em `ARQUITETURA.md`: identidade com RLS em
22 de 22 tabelas, TOTP, tokens de serviço, log de acesso particionado, fila com worker próprio, catálogo, ingestão de
4 formatos, LDAP, SMTP e convites, metadado ISO 19139 e OGC API Records.

Decisões de conceito que obrigam a não refazer: D1 (identificador de item é uuid opaco gerado no banco, nunca serial
nem URL), D3 (dado vetorial em schema por inquilino, uma tabela por camada, `tenant_id` e RLS em toda tabela), D12
(fila própria só com Postgres, sem Redis nem Celery), D20 (um portal, N inquilinos, RLS em tudo, superadmin fora de
inquilino, teste cruzado gerado do OpenAPI).

### L1 imagens

O que entrega: ingestão de raster em COG, catálogo pgstac por inquilino, tiles raster com token, mosaico por busca
registrada, máscara de nuvem por pixel, séries temporais, exportação e proveniência. Equivalente que substitui: ArcGIS
Image Server e as imagery layers do portal. Itens: 65; estado 0/65 (2 refutados: `L1-01-b` validação da entrada e
`L1-01-d` Garage por inquilino, este por cota que não segura 32 gravações concorrentes). O serviço `plat-titiler`
(8152) tem porta reservada e não existe (`ARQUITETURA.md` seção 1).

Decisões: C1 (catálogo é pgstac, com espelho `plat.raster_item` sob RLS para autorização), C3 (COG em três perfis,
`visual`, `cientifico` e `categorico`; JPEG só em RGB; WEBP só atrás do próprio servidor), C6 (token longo no caminho
da URL, revogável em até 5 s, chave de cache sem o token), C18 (quatro portas para o ArcGIS: XYZ/WMTS/WMS para ver,
STAC + S3 + WCS para analisar, ImageServer compatível parcial, e PMTiles/COG por URL nunca prometidos).

### L2 plataforma

O que entrega: mapa web, estilo, edição transacional com histórico, serviços compatíveis e OGC, geoprocessamento,
painéis, campo offline, migração do portal antigo, 3D, linguagem de expressão, geocodificador e rota, impressão,
versionamento, tempo real, analítica grande e camada de consulta. Equivalente que substitui: Map Viewer, hosted
feature layers, ArcGIS Server (FeatureServer, MapServer, GeocodeServer, NAServer), Arcade, Field Maps e a ferramenta
de migração de grupo. Itens: 100; estado 4/100 provados (5 parciais). Existem hoje o documento de mapa, o mapa base
local em PMTiles, o parser de `where` e CQL2 por árvore sintática, o geocodificador sobre CNEFE (erro mediano 0,0 m em
50 endereços de Roraima, `docs/PARIDADE.md`), rota e matriz sobre um OSRM de teste e o núcleo da linguagem de
expressão com 18 funções e 41 vetores comparados byte a byte entre Python e JavaScript.

Decisões: C1 (documento de mapa próprio com referências só por uuid; Web Map JSON só por conversão nos dois sentidos),
C6 (linguagem de expressão própria com gramática EBNF fechada, AST em JSON e dupla implementação com vetores
compartilhados), C9 (token no caminho em três raízes, código HTTP real e corpo no vocabulário do cliente), C18 (schema
por inquilino, RLS, role só-leitura `plat_leitor` e contexto por token; nenhum SQL de cliente fora de tradutor com
lista fechada).

### L3 motor multicritério

O que entrega: modelo como documento JSON versionado por hash, extração materializada, transformações declarativas,
combinação com política explícita de dado ausente, veto separado do peso, explicação por unidade, robustez por
sorteio, corredor de custo mínimo e exportação do método em PDF. Equivalente que substitui: Suitability Modeler,
Weighted Overlay, Rescale by Function e Distance Accumulation. Itens: 34; estado 0/34 (`L3-01-a` modelo de dado
refutado por um bug de reescrita de schema em `execute_values`; `L3-01-b` unidades parcial, com 1.000.175 células
geradas em 30,97 s pelo adversário).

Decisões: A2 (extração cara e materializada separada da combinação barata e interativa), A4 (transformações em JSON
declarativo com implementação em SQL e em numpy, equivalência testada com |Δ| ≤ 0,01), A6 (veto e restrição são
objetos separados do peso e nunca entram no sorteio de robustez), A10 (execução grava sha256 e contagem de cada
camada, versão do motor e semente; reexecução dá o mesmo hash).

### L4 rede de utilidades

O que entrega: pacote de ativos como dado versionado, topologia derivada, terminais como nós, atributos propagados,
subredes com controlador, traçados (conectado, montante, jusante, isolamento, laços, caminho mais curto), diagramas
esquemáticos, versionamento por ramo, formatos de troca (BDGD, OpenDSS, CIM, EPANET), análise elétrica com estado de
convergência, telemetria, inspeção orbital e malha de parcelas. Equivalente que substitui: Utility Network, Network
Diagram Server, Parcel Fabric e Version Management Server. Itens: 66; estado 1/66 (`L4-01-a-pacote-de-ativos`
entregue). Dado de trabalho: BDGD 2024 com 101 distribuidoras e a cooperativa de teste com 44.268 segmentos de média
tensão (`L4_CONCEITO.md` seção 0).

Decisões: C1 (feições de rede são camadas normais; a topologia é índice derivado, marcado sujo por edição), C3
(esquema da rede é dado: pacote de ativos JSON versionado por inquilino, o que permite água, gás e esgoto sem código
novo), C17 (contrato próprio primeiro, fachada compatível por cima, e "o ArcGIS Pro editar a nossa rede" declarado
fora). O documento `L4-privado_CONCEITO.md` estende a linha para infraestrutura de empreendimento fechado como
atributo de titularidade da subrede, não como modelo novo (C2), e nomeia quatro peças que ainda não existem (C12). O
`L8_CONCEITO.md` é um esboço para rodovias, ainda sem itens no backlog, e conclui que rodovia é referenciamento
linear, não rede de utilidade (C1 e C13).

### L5 construtores

O que entrega: doze construtores (aplicação, painel, fluxo, formulário, narrativa, site, aplicação instantânea, popup,
simbologia, relatório, camada e gerenciador de trabalho) sobre um motor de widgets, um editor de arrasto, um
barramento de mensagens, uma linguagem de expressão e um esquema de versões. Equivalente que substitui: Experience
Builder, Dashboards, Survey123, Field Maps, StoryMaps, Hub, ModelBuilder, QuickCapture e Workflow Manager. Itens: 61;
estado 1/61 (`L5-05-documento-versoes` entregue: envelope de documento, ULID por nó, migração de esquema na leitura e
verificação de integridade contra edição direta no banco, `docs/PARIDADE.md`).

Decisões: D1 (sem framework: módulos ES e Custom Elements; arrastar e soltar medido em 123 ms no chromium do
playwright), D2 (todo nó tem ULID imutável; referências por id, nunca por posição), D6 (uma linguagem de expressão com
dois avaliadores e vetores compartilhados), D10 (publicação em `/p/<inquilino>/<slug>` com token de aplicação cujo
escopo é a lista exata dos itens citados).

### L6 conectores e acervo

O que entrega: o acervo da casa (376 fontes em 22 domínios) publicado ao inquilino por view só-leitura, ficha de
procedência de dez campos, licença curada em vocabulário fechado, gate de LGPD, registro de camadas com contagem
exata, modelo de conexão externa com credencial cifrada e defesa de SSRF, e conectores concretos por protocolo.
Equivalente que substitui: Living Atlas, "add layer from URL" do Map Viewer e Data Pipelines. Itens: 32; estado 4/32
provados (6 parciais, 1 refutado). Existem hoje o registro `plat.acervo_camada` (462 tabelas candidatas medidas em
06/09/2026), a ficha, a licença curada em 29 de 40 fontes com termo encontrado por HTTP (decisão D39), o gate de LGPD
e o modelo de conexão com 25 testes de SSRF (`docs/PARIDADE.md`).

Decisões: B1 (acervo chega por view `SECURITY INVOKER` em schema próprio, com lista branca de colunas e predicado de
assinatura; nunca cópia, nunca GRANT direto em `public`), B3 (licença em tabela curada com vocabulário fechado; só
fonte com termo escrito e URL testada aparece ao inquilino), B4 (bloqueio de LGPD por fonte e por coluna, com teste no
`make check`), B12 (catálogo de endpoints gerado do registro vivo e retestado, nunca lista digitada).

### L7 operação

O que entrega: instalação em dois empacotamentos, release assinado, backup em duas camadas com ensaio mensal, réplica
e failover manual, observabilidade, medição e cobrança por uso, segurança conforme ASVS 5.0 nível 2, CDN, residência
de dados por instalação, modo somente-leitura, classificação de dado e retenção, licença do appliance, i18n e
acessibilidade, homologação, suporte com laço agêntico e página de SLA. Equivalente que substitui: ArcGIS Monitor,
webgisdr, Portal Administrator Directory, usage reports e o modelo de patch da Esri. Itens: 75; estado 0/75 (7
refutados: release, assinatura de pacote, homologação, dependências, segredos, instalações apt e antivírus, todos com
conserto em curso).

Decisões: C1 (um repositório, dois empacotamentos, migrações como único lugar de esquema, `pg_dump -s` idêntico nos
dois caminhos), C3 (backup lógico por inquilino sempre; PITR com pgBackRest só onde o cluster é dedicado), C5
(`plat.evento` é a única origem de webhook, trilha, medição e laço agêntico), C11 (modo somente-leitura como
primitiva: atualização, failover e licença vencida usam a mesma bandeira).

## Como o isolamento entre clientes funciona

O inquilino é a unidade de isolamento. Cada requisição define o inquilino da transação por
`set_config('plat.tenant_id', ..., true)`, e toda política de segurança por linha (RLS, row-level security do
PostgreSQL) lê esse valor por `plat.tenant_atual()` (`ARQUITETURA.md` seção 3.3). Medido em 05/09/2026: 22 de 22
tabelas e partições com `tenant_id` têm RLS ligada; 0 tabelas com `tenant_id` sem RLS (`ARQUITETURA.md` seção 3.2). As
tabelas de camada nascem com `ENABLE` e `FORCE ROW LEVEL SECURITY` (`docs/PARIDADE.md`, seção "Ingestão vetorial").

As roles do banco não têm privilégio de contorno. `plat_app` e `plat_worker` são `NOBYPASSRLS`, não são donas de
nenhum objeto, e as funções `SECURITY DEFINER` conferem o contexto por `plat.contexto_confere` antes de agir
(`ARQUITETURA.md` seções 3.1 e 4.8). O superadmin é resolvido pelo hash da sessão, nunca por variável de contexto; o
adversário forjou `plat.usuario_id` e recebeu `ERROR so_superadmin` (`ARQUITETURA.md` seção 4.7). O limite escrito nos
ADRs é conhecido: quem tem a senha de `plat_app` escolhe o inquilino, porque o contexto é uma variável que a própria
role define (`ARQUITETURA.md` seção 3.3).

O token de serviço tem escopos fechados, restrição de origem e de IP, validade de 90 dias por padrão e 365 no máximo,
rotação com sobreposição de 24 h e revogação medida em 0,01 s até o 401 (`ARQUITETURA.md` seção 4.5). O contrato das
linhas L1 e L2 leva o token no caminho da URL e valida antes do cache (`L1_CONCEITO.md` C6). No armazenamento, cada
inquilino tem um bucket e duas chaves no Garage; a chave só-leitura tentando escrever recebe 403 do próprio Garage
(`docs/PARIDADE.md`, seção "Arquivos/objetos"). O teste cruzado é gerado do OpenAPI: 74 rotas, 4 vetores por rota,
digest dos dados do inquilino B antes e depois; rota sem caso reprova o teste (`ARQUITETURA.md` seção 9.3).

Base por ambiente: a homologação usa um banco separado, `plat_homolog`, e não um schema, para que migração, backup e
restauração sejam idênticos aos de produção (`L7_CONCEITO.md` C15). Cada trilha de construção recebe uma base de banco
própria por `laco/trilha_ambiente.sh`, com reescrita de schema por `CursorSchemaAmbiente`
(`SKILL_plataforma-enterprise.md`, regras que custaram caro).

O padrão descoberto em 06/09/2026, quando adversários por linha verificaram 8 itens marcados como prontos e derrubaram
7: o que é protegido por linha aguentou todos os ataques; o que é recurso partilhado não tinha dimensão de inquilino
(`STATUS.md`, "Leitura honesta"). Exemplos registrados nos campos `bloqueio` do `estado.json`: as chaves dos
periódicos eram constantes e qualquer inquilino as ocupava (`L0-05-d`); a compactação de versões apagava versões de
item de outro inquilino (`L0-03-l`); o schema `d_<slug>` não tinha prefixo de instalação, então duas instalações no
mesmo banco não se isolavam (`L0-04-c`); o administrador do inquilino elevava as próprias cotas (`L0-07-a`); seis
funções `SECURITY DEFINER` estavam com `EXECUTE` para `PUBLIC` (`L0-02-e`); a cota de bytes do bucket não segurava
gravação concorrente (`L1-01-d`); um `GRANT ... ON ALL FUNCTIONS` da migração 011 devolveu a `plat_app` as funções do
worker (`ARQUITETURA.md` seção 3.1). A regra que saiu disso está em `CONTRIBUIR.md`: recurso partilhado (fila, trinco,
schema de dados, contador de cota, porta, nome de tarefa agendada, permissão de função) sempre com dimensão de
inquilino ou de ambiente.

## A pilha

| componente | software | porta | estado | onde roda |
|---|---|---|---|---|
| API | FastAPI sob uvicorn, 2 workers, unidade `plat-api` (`MemoryMax=1G`) | 127.0.0.1:8150 | existe | servidor principal (Vultr São Paulo, `L7_CONCEITO.md` seção 0) |
| fila | worker próprio em Python, unidade `plat-worker` (`MemoryMax=2G`), um processo filho por job; opcional em contêiner Docker | 8153 (`/saude`); contêiner em 8155 | existe (ADR 0003 e 0010) | mesma máquina |
| proxy | nginx com HTTPS, `noindex`, HSTS, limite por IP no login, cache de tiles | 443 / 80 | existe | mesma máquina |
| banco | PostgreSQL 16.13 + PostGIS 3.6.3; schemas `plat`, `plat_trabalho`, `d_<slug>` por inquilino; roles `plat_app`, `plat_worker`, `plat_leitor` | 5432 | existe; banco `iagro_sat` compartilhado com outros projetos da casa | mesma máquina |
| catálogo de imagens | pgstac + stac-fastapi-pgstac | no banco | planejado (`L1-01-a`) | mesma máquina |
| objetos | Garage 2.3.0, S3 compatível, um bucket e duas chaves por inquilino | 3900 (admin 3903) | existe; serviço `plataforma-garage` reusado (D26) | mesma máquina |
| tiles vetoriais | Martin em modo funções, com contexto por token; PMTiles por tippecanoe para camadas estáticas | 8151 | planejado (`L2-01-b`); porta reservada; `/saude` devolve `"martin": "ausente"` | mesma máquina |
| tiles raster | TiTiler + titiler-pgstac, 4 workers | 8152 | planejado (`L1-02-a`); porta reservada | mesma máquina |
| mapa no navegador | MapLibre GL 4.7.1 e pmtiles 4.5.0 em `web/vendor/`, com sha256 conferido por `make vendor`; mapa base local `guarulhos.pmtiles` (18 MB) | navegador | existe (`L2-01-a`) | cliente |
| renderização no servidor | chromium do playwright com o mesmo MapLibre, serviço `plat-render` | 8154 (`L2_CONCEITO.md` C10) | planejado; medido 350 ms para 2.000 polígonos | mesma máquina |
| tempo real | `plat-fluxo`, partição nativa e BRIN, SSE por `pg_notify` | 8155 (`L2_CONCEITO.md` C14) | planejado | mesma máquina |
| rota | OSRM em contêiner (perfil `carro`, área de teste) e pgRouting 4.0.1 do apt | 50xx (protocolo próprio do `osrm-routed`) | OSRM de teste existe; pgRouting planejado (`L4-02`) | mesma máquina |
| homologação | unidade `plat-homolog`, banco `plat_homolog`, dado sintético | 8154 (`ARQUITETURA.md` seção 5.8; `L7_CONCEITO.md` C15) | refutado, conserto em curso (`L7-31`) | mesma máquina |
| observabilidade | Prometheus 2.54.1 + Grafana 11.2.0 em `/opt/monitoring` | 9090 / 3000 | pilha existe na máquina; integração planejada (`L7-06`) | mesma máquina |
| processamento pesado | executor remoto por SSH no GPU box (RTX 4000, 20 GB) | via túnel | planejado (`L1-05`); só a coluna `executor` existe | GPU box |
| réplica | streaming físico + `pg_promote` manual + Garage `replication_factor 2` | segunda máquina | planejado (`L7-07`) | segunda máquina, ainda não existe |

Faixa de portas reservada ao produto: 8150-8159. Serviços vizinhos que o `plat` nunca toca: 8125, 8126, 8091,
8127-8135, 8141 (`ARQUITETURA.md` seção 1). Recursos medidos em 05/09/2026: 12 vCPU, 23 GB de RAM com cerca de 3 GB
disponíveis, discos a 98 % (`SKILL_plataforma-enterprise.md`). Por isso o laço trabalha com no máximo 3 GB de dado
novo (decisão D21).

## Como se constrói e como se prova

O repositório é construído por um laço de agentes descrito em `laco/SKILL_plataforma-enterprise.md`. O estado vivo é
`laco/estado.json`: 506 itens, cada um com hipótese, portão de pronto e refutação. O portão de pronto é literal: cada
cláusula vira um teste ou uma medida gravada em `tests/medidas/<item>.json`, o único lugar de onde um documento cita
número (`ARQUITETURA.md` seção 12). A refutação é a instrução dada ao adversário para derrubar o item. Nove portões
valem para todo item, P1 a P9: funciona no navegador com captura, sem placeholder, suíte inteira verde, paridade
declarada e testada, reprodutível por `install.sh` e migrações, multi-inquilino com teste cruzado, dado aberto sem
nome de cliente, adversário não refutou, documentado no mesmo turno.

Os papéis são separados por modelo e por contexto (`PLANO_DA_CORRIDA.md`; `STATUS.md`). Fable dirige: elege itens,
junta os ramos e arbitra. Sonnet constrói e conserta, cada item num worktree próprio `wt/<item>` com base de banco
própria. Opus faz adversário e conserto de segurança. O adversário roda em contexto próprio, não lê os handoffs de
quem construiu, recebe só o item, o portão, o repositório e a URL, e escreve `refutacao.json` com veredito PASSA,
REFUTADO ou PARCIAL. O gerente não discute com o adversário: conserta e roda de novo, ou registra o item como
refutado. Ninguém fala por contexto compartilhado; tudo vai por arquivo em `laco/handoffs/T<turno>/`, e handoff sem
comando e saída literal é inválido.

A junção é serial e em lote. `laco/fila_merge.sh` junta 6 a 11 ramos por vez, roda a suíte inteira uma vez por lote e,
quando o lote quebra, faz bisseção para devolver só o ramo culpado com o registro do erro (`CONTRIBUIR.md`). Trabalho
vindo de outra máquina entra pelo mesmo caminho: `laco/puxa_github.sh` cria o worktree e o põe na fila. Migração nova
usa carimbo de tempo no nome (ADR 0014), depois que quatro trilhas concorrentes colidiram em números (`ARQUITETURA.md`
seção 16). Nenhum item vira provado sem laudo: de 60 itens declarados entregues ou parciais no início de 06/09/2026,
só 8 tinham laudo de adversário; dos 8 verificados, 7 caíram, com achados de segurança reais (`STATUS.md`). Cada
achado vira um teste `xfail(strict=True)` que acompanha o conserto. Essa taxa é o portão funcionando: os itens
vermelhos não são trabalho perdido, são itens que estavam marcados como prontos sem prova (`PLANO_DA_CORRIDA.md`, fase
C).

Um driver em cron (`laco/driver.sh`, a cada 30 minutos) mede o repositório, varre placeholders e reprova se achar
algum, e lança um turno automático quando nenhum turno rodou em 90 minutos. A restrição que desenha a corrida é a cota
de API, não a máquina: onze agentes caíram de uma vez às 17:30 de 06/09/2026 no limite da sessão; o supervisor
(`laco/supervisor.py`) detecta a queda, pausa, espera e retoma sem marcar tentativa nem refutar item por queda de cota
(`PLANO_DA_CORRIDA.md`). O trabalho interrompido fica em commits de resgate nos ramos e nunca se perde
(`laco/RETOMADA_20260906.md`).

## Onde está hoje e o que falta

Placar de `STATUS.md` (06/09/2026 17:51 UTC): 22 provados, 17 parciais, 39 refutados, 428 na fila, 506 itens. Por
linha: L0 12/72, L1 0/65, L2 4/100, L3 0/34, L4 1/66, L5 1/61, L6 4/32, L7 0/75. A conta de trabalho restante escrita
no plano é de cerca de 555 horas-agente, com o teto físico de agentes como caminho crítico (`PLANO_DA_CORRIDA.md`).

O que só o dono destrava está em `decisoes_do_dono` do `estado.json`, 23 decisões de D18 a D40. As que travam itens
hoje: D20, credencial do parceiro de canal para testar ArcGIS Pro e ArcGIS Online reais, sem a qual toda linha de
paridade fica `pendente` e 20 itens ficam em quarentena (`PLANO_DA_CORRIDA.md`); D17 e D39, quem assina a licença das
fontes cujo órgão não a declara, com 29 de 40 fontes fechadas; D21, disco a 98 % nos dois servidores; D22, janela para
reiniciar o Postgres compartilhado e ligar `archive_mode`, sem a qual não há PITR; D18, nome público do produto; D40,
o segredo TOTP do superadmin de teste, que hoje bloqueia parte da suíte de API. No total, 36 itens dependem de decisão
do dono e ficam visíveis como quarentena, sem travar os demais (`PLANO_DA_CORRIDA.md`). Cinco passos de produção do
conserto de segurança G6 (tirar segredos do `.env`, rotacionar token, etiqueta assinada) estão preparados e um deles
exige janela combinada no banco compartilhado (`laco/RETOMADA_20260906.md`).

Mapa dos documentos, na ordem em que convém ler:

| documento | o que responde |
|---|---|
| `README.md` | o que existe no repositório, comandos e contas de demonstração |
| `SISTEMA.md` (este) | o todo, de ponta a ponta, antes do código |
| `ARQUITETURA.md` | o que está construído e medido: componentes, portas, banco, identidade, fila, migrações, instalador, front, e a seção "O que ainda não existe" |
| `MANUAL.md` | uma seção por tela, com a captura do teste de ponta a ponta |
| `docs/PARIDADE.md` | tabela viva contra o ArcGIS Enterprise: capacidade, o que a Esri faz, o que existe aqui, estado, quem testou, data; a coluna Pro/AGOL real fica `pendente` até D20 |
| `docs/adr/` | 15 decisões de arquitetura numeradas 0001-0017 (0015 e 0016 não existem): fundação, identidade, fila, catálogo, ingestão vetorial, objetos, pacotes apt e assinatura, LDAP, homologação, worker em contêiner, documento de construtor, acervo e conexão externa, geocodificador, nome de migração, SMTP e convites |
| `CHANGELOG.md` | uma entrada por item e turno, com medições, vereditos e commits |
| `STATUS.md` | placar por linha, regenerado pelo supervisor a cada rodada |
| `PLANO_DA_CORRIDA.md` | o plano aprovado: papéis por modelo, fases A-C, o que só o dono destrava |
| `RECONSTRUIR.md` | o que não está no git (dado, segredos, objetos, pgstac) e como se recria em outra máquina |
| `CONTRIBUIR.md` | o contrato de um ramo externo `wt/<item>` e o que o servidor faz com ele |
| `laco/LEIA-ME.md` | a máquina que constrói o repositório: ordem de leitura, ferramentas, o que fica fora de propósito |
| `laco/decomposicao/*_CONCEITO.md` | as decisões que obrigam a não refazer, uma por linha, com opções, custo de mudar e motivo medido, lido ou documentado |
| `laco/estado.json` | os 506 itens com portão de pronto e refutação, o ledger e as decisões do dono |

Ressalvas de leitura. `README.md` e `ARQUITETURA.md` descrevem o fim do turno 2 e citam 74 rotas no OpenAPI; o laço
está no turno 3 e `docs/openapi.json` está dezenas de rotas atrás do aplicativo vivo, o que os testes de cobertura
ainda não pegam porque leem o retrato comitado (`laco/RETOMADA_20260906.md`). `VERSAO` diz `0.1.0` e o `CHANGELOG.md`
já tem entradas do turno 3. Os conceitos foram escritos em 05/09/2026 e o código que veio depois divergiu deles em
pontos nomeados: o mínimo de senha é 8 no código contra 10 no conceito (`L0_CONCEITO.md` D6; bloqueio de `L0-02-b`); a
credencial de conexão externa é cifrada em Python com AES-GCM, não com `pgp_sym_encrypt` do pgcrypto (`ARQUITETURA.md`
seção 15 contra `L3L6_CONCEITO.md` B7); o relógio das agendas é o worker, não o pg_cron (`ARQUITETURA.md` seção 5.6
contra `L3L6_CONCEITO.md` B9); a porta 8154 é a homologação em `ARQUITETURA.md` e `L7_CONCEITO.md` C15, e o serviço de
renderização em `L2_CONCEITO.md` C10, do mesmo modo que a 8155 é o worker em contêiner num documento e o `plat-fluxo`
no outro. Onde o código e o conceito discordam, vale o que está medido em `ARQUITETURA.md`; a decisão de conceito
continua obrigando a forma, não o detalhe.

