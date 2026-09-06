# ADR 0012 — Registro de camadas do acervo (L6-01-a) e modelo de conexão externa com defesa de SSRF (L6-02-a)

Estado: aceito (arquiteto+backend, turno T3, setembro de 2026). Base: `laco/decomposicao/L3L6_CONCEITO.md`
(decisões B1-B13, 05/09/2026). Dois itens da linha L6 (conectores e acervo), construídos juntos porque
compartilham a mesma pergunta de fundo — "como uma camada de fora entra no catálogo sem virar risco" — mas
resolvem metades diferentes: L6-01-a é o acervo DA CASA (interno, sem credencial, sem rede); L6-02-a é o
modelo GENÉRICO de conexão a serviço de TERCEIRO (externo, com credencial, com toda a superfície de SSRF).

## Parte 1 — `plat.acervo_camada` (item L6-01-a-registro)

### Contexto

O item-pai (`L6-01-acervo-casa`) já tinha entregue `plat.acervo_ficha` (migração 021): uma view sobre
`acervo.fonte`/`acervo.v_completude`, 376 linhas de metadado de FONTE (quem publica, licença, frescor),
sem geometria. `L6-01-a-registro` é um item DIFERENTE, filho do mesmo pai: não a ficha da fonte, e sim o
registro de CAMADA — uma linha por TABELA canônica com geometria, candidata a virar camada só-leitura no
mapa do inquilino (esse é o L6-01-b, ainda não construído). Confirmado por leitura antes de escrever
qualquer código: `grep -rn acervo_camada` na árvore não achava nada; a hipótese do item em
`laco/estado.json` (`fonte_id, schema.tabela, srid, tipo de geometria, lista branca de colunas, COUNT(*),
sha256, estado`) não tem sobreposição com a view de 021 (que não tem `schema`/`tabela`/`srid`/coluna
alguma de banco — é puramente sobre a FONTE). As duas convivem: `acervo_camada.fonte_id` aponta para a
mesma `acervo.fonte` que a ficha descreve.

### Decisão: tabela GLOBAL (sem tenant_id), escrita só por um script fora da API

`plat.acervo_camada` seguiu o MESMO padrão de `plat.acervo_ficha`: sem `tenant_id`/RLS (é referência da
CASA, igual para todo inquilino — RLS por assinatura entra só na VIEW sobre a tabela original, item
L6-01-b, ainda não construído), `GRANT SELECT` a `plat_app` com `REVOKE INSERT/UPDATE/DELETE` (mesmo
padrão de `plat.versao_migracao` na migração 001: quem escreve não é a API). Quem escreve é
`scripts/acervo_sync.py`, rodando como `postgres` (mesma identidade de `db/migrar.sh`), com o
`psycopg2` do dpkg — sem venv, porque o script não depende de FastAPI/pydantic, só de Postgres.

Medido no momento de escrever (06/09/2026): `geometry_columns` × `acervo.objeto` (canônico, tipo `fonte`,
servidor `vultr`, banco `iagro_sat`) dá **475 candidatas, 270 em `public`** — perto do "462/269" que a
hipótese do item citava (a diferença é o acervo mudando entre uma varredura e outra; por isso o número
nunca é digitado em teste, só medido de novo a cada rodada).

### O que o script faz e por quê

1. **Candidata = tabela canônica com geometria.** Junta `acervo.objeto` (`tipo='fonte'`, `canonico`) com
   `geometry_columns`; se uma tabela tem mais de uma coluna de geometria, fica a que se chama `geom`/
   `geometry` (a esmagadora maioria — 607 de 711 no servidor inteiro), documentado como simplificação
   deliberada (uma linha por TABELA, não por coluna).

2. **`COUNT(*)` exato, nunca `reltuples`, com timeout de 25 s.** Mesmo padrão do `contagem2.py` da casa
   (citado na hipótese do item). Medido: a maioria das 475 candidatas tem `COUNT(*)` em milissegundos
   (mediana de linhas estimadas = 1.710), mas um punhado de tabelas grandes (`cbre.osm_lines_raw`,
   `cbre.cad_lote`, `public.car_nativa_go`...) estoura o timeout quando a máquina está ocupada com OUTRO
   job pesado da casa — medido ao vivo neste mesmo turno: uma `REFRESH MATERIALIZED VIEW` de 3h e um
   `COUNT(*)` de 18 min concorrentes de outra frente, competindo pelo mesmo disco. Timeout nunca vira
   `linhas_exatas = 0`; vira `NULL` com `motivo_bloqueio = 'contagem_nao_concluida_em_25s'`
   (metodologia §7.31 — ausência de dado nunca é medição).

3. **Tabela fantasma é regra DINÂMICA, nunca lista de nomes.** `linhas_exatas = 0 AND linhas_estimadas > 0`
   → `bloqueada`/`tabela_fantasma_estimativa_sem_dado`. As duas fantasmas conhecidas do registro
   (`public.prodes_yearly_all_indexed`, `farma.djen_pub_termo`) nunca são citadas em código — só a REGRA
   é escrita, porque um nome digitado não pega a PRÓXIMA fantasma que aparecer (é literalmente a
   refutação do item: "adversário confere que as 2 tabelas fantasma conhecidas... não aparecem").

4. **Lista branca de colunas: GROSSA e PROVISÓRIA, por nome — nunca por conteúdo.** O item pede "lista
   branca de colunas expostas" mas não depende de `L6-01-f` (LGPD por conteúdo, com amostra e regex de
   CPF/CNPJ), que é outro item, sem essa dependência declarada em `estado.json`. Em vez de expor TODAS as
   colunas (o que violaria a regra da casa "nunca publicar dado pessoal identificado" mesmo antes de
   L6-01-f existir), o script nega por NOME exato — case-insensitive, nunca substring, para não confundir
   `nom_tema`/`nom_munic` (nomes de coisa, comuns nas tabelas do CAR/SIGEF) com identificador de pessoa —
   contra uma lista pequena (`cpf`, `nome`, `email`, `telefone`, `rg`...). Isto é rede de segurança
   MÍNIMA, documentada como tal em três lugares (docstring do script, comentário da migração, este ADR):
   quando L6-01-f existir, ele reforça por conteúdo; até lá, nenhuma tabela cujo nome de coluna bata com
   a lista negra expõe esse campo.

5. **Estado depende da MESMA regra de licença que `plat.acervo_ficha` já usa (D17).** `licenca IS NOT
   NULL AND btrim(licenca) <> ''`; sem isso, `pendente_de_licenca`, nunca `exposta` — nenhuma tabela
   nova de curadoria (`plat.acervo_licenca`, item L6-01-g, não construído ainda) é necessária para este
   item cumprir seu próprio portão, e a decisão B3 (vocabulário fechado) fica para quando L6-01-g existir.

6. **Prazo duro de 270 s dentro de um portão de "≤ 5 min".** Medido: uma rodada completa das ~475
   candidatas, com a máquina disputada por outro job pesado, levou 274,9s (4m35s de parede) na primeira
   tentativa e 286,0s (4m46s) na segunda — ambas sob o limite. Quando o prazo esgota, as candidatas que
   sobram entram como `bloqueada`/`nao_processada_no_prazo` (nunca travam o processo, nunca viram
   `exposta` por omissão). A ORDEM de processamento é por "última sincronização" (nunca sincronizada
   primeiro), não alfabética — medido em duas rodadas seguidas: a 1ª cobriu 81 expostas/292 bloqueadas
   (prazo)/87 pendentes; a 2ª, processando principalmente as que ficaram de fora da 1ª, foi para 172
   expostas/192 bloqueadas(prazo)/93 pendentes — prova de que rodadas sucessivas (cron semanal, B5)
   convergem para cobrir o universo inteiro em vez de sempre travar nas mesmas primeiras tabelas da
   ordem alfabética.

7. **Poda: só contra o universo COMPLETO de candidatas, nunca contra o que foi processado nesta rodada.**
   Achado ao testar: rodar com `--limite N` (depuração) apagava as 432 linhas de rodadas completas
   anteriores, porque a poda comparava contra "o que este `--limite` processou" em vez de "o que ainda é
   candidata de verdade" — corrigido antes de qualquer `--limite` chegar a produção: o conjunto de poda é
   sempre a consulta COMPLETA a `geometry_columns`×`acervo.objeto`, calculada antes do corte de
   `--limite`. `--limite` serve só para teste rápido; nunca reduz o que conta como "ainda existe".

### O que fica para os itens seguintes (nunca prometido como pronto aqui)

L6-01-b (view só-leitura + RLS por assinatura), L6-01-f (LGPD por conteúdo), L6-01-g (licença curada em
vocabulário fechado), L6-01-h (verificação semanal automatizada — hoje o script roda manual/via cron
externo, não plugado em `L0-05` ainda).

## Parte 2 — `plat.conexao` e defesa de SSRF (item L6-02-a-modelo-conexao-e-seguranca)

### Contexto

Decisão B6 (L3L6_CONCEITO.md): um objeto `conexao` (tabela própria, com credencial cifrada e teste de
saúde) + camada externa em dois modos, referenciada × copiada. Esta trilha entrega só o PRIMEIRO — modelo
+ segurança —, não os 15 conectores concretos (WMS, WFS, WMTS, OGC API, ArcGIS REST, STAC, GeoParquet,
PMTiles, bancos externos — cada um é item futuro, L6-02-b em diante, que lê/escreve esta MESMA tabela).

Achado ao ler o código antes de escrever: a migração 021 (item L6-01-a-procedencia-acervo, ENTREGUE) já
tinha criado um `tipo_item` de catálogo chamado `conexao` (protocolo `wms|wfs|wmts|ogc_api|esri_rest|
postgres_fdw|s3|http|acervo`, usado hoje só para o protocolo `acervo` — o item do catálogo que representa
"assinei esta fonte do acervo"). `plat.conexao` (esta migração) é uma tabela DIFERENTE, propositalmente:
o `tipo_item` de catálogo guarda `dados` num JSONB que a API DEVOLVE inteiro na resposta (`GET /api/itens/
{id}`) — não é lugar seguro para uma credencial. `plat.conexao` nunca é exposta por essa rota; tem rotas
próprias (`/api/conexoes`) que nunca devolvem a coluna `credencial_cifrada`. As duas listas de tipo (o
enum do `tipo_item.esquema` e o `CHECK` de `plat.conexao.tipo`) ficam propositalmente independentes por
ora — reconciliar é trabalho de quando o primeiro conector concreto ligar um item de catálogo a uma linha
de `plat.conexao` (via `conexao_id` em `dados.parametros`, ainda não construído).

### Decisão: cifra em Python (AES-GCM), nunca `pgp_sym_encrypt`

A casa já tem o padrão (TOTP, bind LDAP): `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, chave
derivada de `PLAT_SECRET` (SHA-256 do segredo + um "domínio" fixo por uso, para que a mesma
`PLAT_SECRET` nunca produza a mesma chave em dois contextos), nonce aleatório de 12 bytes, AAD fixo (liga
o texto cifrado ao propósito — decifrar com o AAD errado falha mesmo com a chave certa). `app/conexao/
credencial.py` copia esse padrão com prefixo próprio (`encconexao:v1:`) para nunca ser decifrado com o
código errado por engano. `pgp_sym_encrypt` foi descartado porque a CHAVE entraria no próprio SQL de cada
`INSERT`/`SELECT` — visível em log de consulta lenta, em `pg_stat_statements`, em qualquer réplica de
log; cifrar em Python antes do INSERT nunca deixa a chave passar perto do banco.

### Decisão: defesa de SSRF por resolução + pinagem de IP, não por lista de bloqueio de host

O portão do item lista 8 casos que o adversário testa: IP literal privado (127.0.0.1, 10.0.0.0/8,
169.254.169.254), `file://`, host que resolve para IP interno, redirecionamento para IP interno, userinfo
na URL, porta interna, e DNS que muda entre a validação e a conexão (rebinding). Uma lista de hosts
proibidos nunca cobre "host que resolve para interno" nem rebinding; a defesa tem de ser sobre o IP
RESOLVIDO, sempre.

`app/conexao/seguranca.py` faz:

1. **Esquema**: só `http`/`https` (rejeita `file://`, `ftp://`, `gopher://` — testado).
2. **Userinfo**: `partes.username`/`password` não `None` → recusa (o `http://user:pass@host` do portão).
3. **Resolução com timeout**: `socket.getaddrinfo` roda numa `ThreadPoolExecutor` (a função da stdlib não
   aceita timeout direto); DNS que não responde em `CONEXAO_DNS_TIMEOUT_S` é falha de validação, nunca
   "sem restrição" — testado derrubando o `getaddrinfo` global via monkeypatch.
4. **Categoria do IP**: `ipaddress` (`is_loopback`/`is_link_local`/`is_multicast`/`is_unspecified`/
   `is_reserved`/`is_private`) cobre loopback, RFC 1918, link-local (inclui `169.254.169.254`, o
   metadado de nuvem), `::1`, ULA IPv6 (`fc00::/7`). Gap MEDIDO nesta versão do Python: **CGNAT
   (100.64.0.0/10, RFC 6598) não é `is_private`** — acrescentado à mão como rede extra bloqueada,
   porque é um vetor conhecido de bypass de filtro de SSRF em outras casas.
5. **Pinagem de conexão**: depois de validar, a conexão REAL nunca resolve o hostname de novo —
   `_BackendPinado` (subclasse de `httpcore.SyncBackend`) troca, só para o par `(host, porta)` já
   validado, o alvo do `connect_tcp` pelo IP resolvido; o TLS (`start_tls`) continua recebendo
   `server_hostname` = o hostname ORIGINAL (é assim que `httpcore._sync.connection.HTTPConnection.
   _connect` já funciona — conferido na fonte instalada, não suposto), então a verificação de
   certificado segue olhando o nome certo mesmo com o socket na IP pinada. Isto fecha o caso 8
   (rebinding) sem precisar reimplementar TLS: entre validar e conectar não existe uma segunda consulta
   de DNS para aquele host.
6. **Redirecionamento nunca automático**: `buscar_seguro` desliga `follow_redirects` e segue cada
   `Location` MANUALMENTE, revalidando do zero (passos 1-5 de novo) a cada salto, até
   `CONEXAO_REDIRECT_MAX`. Provado com um servidor de teste bindado no IP PÚBLICO REAL desta máquina
   (nunca loopback — senão o hop 0 já recusaria e o teste provaria só o caso 1 de novo) que responde 302
   para `169.254.169.254`: `buscar_seguro` aceita o hop 0 (host público de verdade) e recusa só no hop 1,
   com `saltos=1` no resultado.
7. **Corpo limitado**: `buscar_seguro` lê em streaming e aborta ao passar de `CONEXAO_RESPOSTA_MAX_BYTES`
   (1 MiB) — o teste de saúde nunca baixa o serviço inteiro.
8. **Porta nunca é critério isolado**: a porta 8150 (reservada nesta máquina) só é bloqueada porque o
   HOST de teste é loopback — um serviço público de verdade pode escutar em qualquer porta; testado
   explicitamente que a MESMA porta 443 num host público é aceita.

### O que fica para os itens seguintes

Os 15 conectores concretos (cada um lê `plat.conexao.config` com um JSON Schema próprio, ainda a
escrever); a materialização em modo "copiada" (hoje só o campo `modo` existe, sem agendamento —
isso é L0-05/L6-02-k); a reconciliação entre o `tipo_item` de catálogo `conexao` e esta tabela.

## Parte 3 — ficha completa (item L6-01-d-ficha-fonte) e Parte 4 — gate de LGPD no "adicionar" (item L6-01-f-lgpd)

Estado: aceito (arquiteto+backend, turno T3, setembro de 2026).

### Parte 3: o que faltava na ficha, e só isso

Conferido antes de escrever qualquer coisa: `app/acervo/rotas.py::ver` (então lendo só `plat.acervo_ficha`,
migração 021) já devolvia os 10 campos de procedência da hipótese do item — não havia nada para "completar"
nesses dez. O gap real, medido contra a hipótese completa do item em `estado.json`, era só:
"endpoints confirmados e vivos (`acervo.endpoint`)" e "completude x/10 exibida" (a pontuação já existia como
número cru, `procedencia_pontuacao`, mas não como texto pronto). `plat.acervo_endpoint` (migração 040) segue
o padrão exato de `plat.acervo_ficha` (`security_invoker`, GRANT só a `plat_app`, filtro D17 pela mesma
junção com `acervo.fonte`); "vivo" foi definido igual ao que a casa já usa fora da plataforma
(`confirmado = true AND http = '200'`), não inventado. `completude_texto` é derivado em Python
(`_completude_texto`), não em SQL, porque é só formatação de exibição — `None` propagado sem fabricar zero.

### Parte 4: por que a classificação NÃO entrou em `acervo.fonte`

A hipótese do item (`estado.json`) sugere um campo do tipo "identidade_resolvente" na própria fonte. Decisão:
NÃO alterar `acervo.fonte` — o ADR 0012 (Parte 1) já registrava a regra "`acervo.*` é escrito só pelos
scripts da casa" três vezes; adicionar uma coluna ali pela plataforma quebraria essa invariante para sempre
(a próxima recontagem/varredura da casa, rodada fora da plataforma, não saberia preservar a coluna). A
classificação foi para `plat.acervo_lgpd`, tabela própria da plataforma, com FK de leitura para
`acervo.fonte(fonte_id)` mas gravação só por migração/acesso direto — mesmo padrão já usado em
`plat.acervo_camada` (Parte 1) para "curado à mão, nunca pela API".

A curadoria em si não foi um exercício de suposição: rodou-se uma varredura real de
`information_schema.columns` sobre as 219 tabelas canônicas (`acervo.objeto`, `canonico = true`) das 68
fontes licenciadas, com um padrão de nome de coluna deliberadamente LARGO (a mesma lição da Parte 1 sobre
lista branca "grossa e provisória, por nome, nunca por conteúdo" — aqui invertida: usar o nome como
PRIMEIRO filtro, depois ler o conteúdo de verdade antes de decidir). 114 colunas bateram; cada uma foi
inspecionada (`\d` da tabela, contagem de preenchimento quando havia dúvida real, como em
`cbre.cad_gu_face_pgv.id_responsavel`, preenchida em 1 de 25.436 linhas — não é cadastro de contato pessoal,
é flag de infraestrutura de rua ao lado de `agua`/`luz`/`esgoto`). Achado único: `onr`, por um caminho que a
varredura de NOME não pegaria sozinha — a tabela ingerida (`cbre.onr_matricula`) não guarda o nome do
titular, mas guarda `url_mat`, um link para o documento de matrícula real no cartório, que guarda. A decisão
de marcar `onr` não veio da regex; veio de abrir o link e ver o que está do outro lado.

Isto é DELIBERADAMENTE mais estreito que o portão completo do item em `estado.json` ("teste automatizado
percorre TODA view exposta e falha se existir coluna cujo nome case com a lista negra ou cujo conteúdo case
com regex de CPF/CNPJ em amostra de 1.000 linhas; `make check` inclui o teste"): essa varredura genérica e
automática, medida ao vivo nesta mesma passagem, produz mais ruído do que sinal sem revisão humana por
tabela (114 colunas suspeitas, 1 achado real) — automatizar o BLOQUEIO em cima dessa regex, sem a mesma
leitura manual, teria bloqueado `cad_gu_face_pgv` e uma dúzia de tabelas de nome de lugar por engano, e
ainda assim não teria pego `onr` (cujo risco está no link, não na coluna). O que se entrega aqui é o gate
no fluxo específico pedido ("bloqueie POST /adicionar para fontes marcadas sem confirmação explícita");
a varredura automática de TODA view exposta (incluindo `plat.acervo_camada`, que já tem
`colunas_bloqueadas` por nome desde a Parte 1) fica registrada como pendência, não prometida como feita.

### O que fica para os itens seguintes

L6-01-c (tela de navegação do acervo — nenhuma das duas partes tem front); a classificação por CONTEÚDO em
`plat.acervo_camada.colunas_expostas` (hoje só por nome); a varredura automática de toda view exposta contra
o padrão de LGPD (o portão completo do item L6-01-f); revisão periódica de `plat.acervo_lgpd` quando novas
fontes ganharem licença (a curadoria de hoje cobre as 68 fontes licenciadas em 06/09/2026, não as futuras).
