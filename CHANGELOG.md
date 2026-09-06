# Changelog

Uma entrada por turno do laço PLATAFORMA ENTERPRISE. Números só de `tests/medidas/<item>.json` (com o comando que
os gerou) ou dos vereditos do adversário em `laco/handoffs/T<n>/<item>/refutacao.json`.

## turno 3, setembro de 2026 (item L0-07-d-smtp-convites: SMTP, convite de membro por e-mail e redefinição de senha por e-mail)

SMTP configurável na instalação (`.env`, `PLAT_SMTP_*`) e por inquilino (`tenant.config->'smtp'`, senha
cifrada AES-GCM com rótulo próprio `plat-smtp`); `GET/PUT /api/org/smtp` e `POST /api/org/smtp/testar`
(envio síncrono, erro legível, nunca a senha). E-mail sempre por job `correio.enviar` (fila do L0-05),
`somente_sistema=True` (campo novo em `app/jobs/registro.py`) impede a criação via `POST /api/jobs` mesmo
por admin — fecharia canhão de spam com o SMTP do inquilino; só `app/jobs/sistema.py::enfileirar` cria.
Convite de membro (`plat.convite`, migração 047): o link carrega só o token, nunca o e-mail — o servidor
sempre lê o que o convite guarda (`ConviteAceitarEntrada` é `extra="forbid"`, um `email` extra no corpo
vira 422 antes de tocar o banco); token de uso único (sha256), validade 7 dias, aceitar roda numa função
SQL `SECURITY DEFINER` com `FOR UPDATE` que cria a conta e marca o convite usado na mesma transação. Sem
SMTP, a resposta devolve `link_manual` (mesmo padrão de senha temporária mostrada uma vez). Redefinição de
senha por e-mail (`plat.redefinicao_senha` + `plat.redefinicao_pedido`): solicitar sempre devolve
`202 {"ok":true}`, exista ou não a conta; limite de taxa por (inquilino, e-mail), 5 pedidos a cada 15
minutos, contado mesmo para e-mail inexistente (senão o próprio limite revelaria existência); aplicar
reusa a mesma rotina de troca de senha/histórico/sessões de `PUT /api/eu/senha`. Telas: `/admin/organizacao`
(seção SMTP), `/admin/usuarios` (convidar + lista de pendentes), `/aceitar-convite` e `/redefinir-senha`
(públicas). ADR 0017.

Três defeitos reais achados rodando de verdade contra `https://plat.iagrointel.com` com um servidor SMTP
de captura em stdlib puro (`tests/api/util_smtp_captura.py` — `aiosmtpd` está ausente) e o `plat-worker`
real, corrigidos ANTES do adversário (migrações 048/049): (1) variável PL/pgSQL `chave` ambígua contra a
coluna homônima em `plat.redefinicao_pedido` — todo `POST /api/senha/redefinir/solicitar` caía em 500;
(2) sete tipos de evento novos nunca inseridos em `plat.evento_tipo` — toda `registrar_evento` correspondente
violava a FK (500 em `PUT/DELETE /api/org/smtp`, `POST /api/convites`, aceitar convite, aplicar
redefinição); (3) duas consultas a `plat.tenant` sem contexto de inquilino (a conta ainda não existe)
caíam na RLS e devolviam `None` em vez da linha; (4) `correio.enviar` com `memoria_mb=192` estourava de
verdade o `RLIMIT_DATA` do filho (cryptography importado pela primeira vez depois do fork), subiu para 512.
Medido, com o worker/API reais e o servidor de captura: convite chega e-mail→resolver→aceitar→conta
criada→login funciona; link usado de novo e expirado (7 dias simulados por UPDATE direto) dão `410`
nos dois casos; e-mail malicioso extra no corpo do aceite vira `422` e nunca altera o e-mail da conta
criada (sempre o do convite); redefinição ponta a ponta com o mesmo padrão; 12 pedidos seguidos de
redefinição para o mesmo e-mail estouram o limite de taxa antes do fim (refutação do item); `testar envio`
com host inexistente devolve erro legível em menos de 1 s; a senha SMTP em claro NUNCA aparece no
`journalctl` real de `plat-worker`/`plat-api` (grep direto no log real, não simulado);
`POST /api/jobs {"tipo":"correio.enviar"}` recusa `403` mesmo para o admin do inquilino; isolamento
cruzado confirmado (admin de outro inquilino recebe `404` ao tentar cancelar convite alheio).
`tests/api/test_smtp_convites.py` + `tests/unit/test_correio_cifra.py` + `test_correio_cliente.py`:
21/21 passam contra o schema `plat` de produção. **Pendência nomeada**: o e2e de navegador
(`tests/e2e/test_convite.py`, escrito e com lint limpo) não foi executado neste turno — swap da
máquina em 7,7/8,0 GiB no momento do fechamento (contenção de múltiplos agentes concorrentes no laço,
não desta mudança), e a casa já teve OOM por lançar Chromium sob essa pressão; roda no próximo `make e2e`
com RAM livre. Fora do portão literal deste turno (hipótese do item, registrado no ADR 0017 §D5): avisos
de expiração de token (90/30/7/1 dia) e notificação de grupo por e-mail — o job `correio.enviar` já serve,
falta só o gatilho periódico cross-tenant.

## turno 3, setembro de 2026 (nome de migração por carimbo de tempo — ADR 0014)

Migração nova passa a se chamar `db/migracoes/YYYYMMDDTHHMM_<slug>.sql` (carimbo UTC, mais 3 hexadecimais
quando duas nascem no mesmo minuto em trilhas diferentes). O nome do arquivo é CHAVE em
`plat.versao_migracao`, não etiqueta: renumerar um arquivo já aplicado faz o aplicador tratá-lo como novo e
reaplicá-lo. Com trilhas em paralelo, a numeração sequencial colidiu três vezes no mesmo dia (o mesmo arquivo
foi 031 → 037 → 044 → 045). A família de três dígitos fica FECHADA em 048, imutável; nenhum arquivo existente
foi renomeado. `app/migracoes.py` concentra o padrão de nome, a chave de ordenação (legado antes de qualquer
carimbo) e o cabeçalho opcional `-- depende: <arquivo>`; `db/migrar.sh`, `db/migrar_homolog.sh` e
`laco/trilha_ambiente.sh` repetem a mesma chave em bash. `tests/unit/test_migracoes_nome_e_dependencia.py`
reprova nome fora do padrão, três dígitos novos e dependência que vem depois na ordem;
`tests/api/test_saude.py` deixa de casar o glob de três dígitos e escreve o que "última migração" passa a
significar (a de autoria mais recente pela chave, não a maior string nem a última aplicada no relógio).
## turno 3, setembro de 2026 (item L6-02-c-wfs-ogcapi: conector WFS 2.0 e OGC API - Features)

Primeiro conector que LÊ dado de serviço de terceiro (ADR 0018). WFS 2.0 (GetCapabilities, DescribeFeatureType,
GetFeature com `COUNT`/`STARTINDEX`/`BBOX`, `RESULTTYPE=hits`, saída GeoJSON e GML 3.2) e OGC API - Features
(`/collections`, `/queryables`, `/items` com `limit`, `bbox`, `datetime` e link `rel=next`), nos dois modos:

- **referenciado** — `GET /api/conexoes/{id}/colecoes`, `.../colecoes/{c}/campos` e `.../colecoes/{c}/feicoes`,
  ao vivo, com cache de 30 s no processo (`app/conexao/cache.py`); editar ou apagar a conexão esquece o cache.
- **copiado** — job `conexao.copiar_vetor` (`POST /api/jobs`), que traz a coleção para uma tabela PostGIS do
  inquilino com item `camada_vetorial`, procedência e as mesmas colunas obrigatórias/RLS da ingestão de arquivo.

Regra dura do desenho: **todo I/O de rede passa por `app.conexao.seguranca.buscar_seguro`** (item L6-02-a) —
os drivers `WFS:`/`OAPIF:` do GDAL foram recusados de propósito, porque fariam a requisição fora da defesa
contra requisição forjada pelo servidor. O `ogr2ogr` só entra depois, sobre arquivo LOCAL, e roda com
`GDAL_HTTP_PROXY` apontando para porta fechada, de modo que nenhuma requisição sua possa sair da máquina.

Medido (`tests/medidas/L6-02-c-wfs-ogcapi.json`): 50 mil feições copiadas de um WFS 2.0, com o tempo de
download e o de carga separados; paginação conferida contra o `numberMatched` declarado; tipos de atributo
(`xsd:int`, `xsd:double`, `xsd:boolean`, `xsd:date`) preservados como o serviço os declarou; geometria
reprojetada de EPSG:31983 para 4326 com o CRS nativo gravado na ficha.

Refutação do adversário provada: um WFS que declara 5.000.000 de feições e ignora `COUNT`/`STARTINDEX` faz a
cópia parar no limite declarado, gravar o aviso na procedência da camada e devolver o worker à fila — três
travas independentes (limite, página maior do que a pedida, página repetida) além dos tetos de bytes e de
páginas.

Novo em `app/conexao/seguranca.py`: `PLAT_TESTE_CONEXAO_ALVOS`, par `host:porta` exato aceito só fora de
produção, para que a suíte fale com um WFS e um OGC API DE VERDADE subidos no loopback
(`tests/api/conexao/servidor_ogc.py`) em vez de depender do serviço de um órgão estar de pé.

## turno 3, setembro de 2026 (item L0-09-a-procedencia: bloco de procedência em todo item de dado)

Todo item que carrega dado passa a ter um bloco de procedência com o vocabulário que a casa já usa no registro
do acervo (`acervo.fonte`, 376 fontes) e no catálogo de camadas do motor logístico: fonte, endereço, licença,
data do dado, data de acesso, gerador, sha256, comando de reexecução, método, confiança, limites, frescor,
próxima verificação e responsável. Cada campo pode declarar a `origem`: `declarado` (alguém afirmou) ou
`medido` (a máquina calculou). O vocabulário campo a campo está em `docs/PROCEDENCIA.md`.

A pontuação é a régua da `acervo.v_completude`, sem peso novo: `round(campos / campos_possiveis * 10, 1)` sobre
os mesmos 10 campos. Item sem bloco tem pontuação nula, nunca `0,0` — ausência de registro não é medida de zero.
A conta existe em Python (`app/catalogo/procedencia.py`) e em SQL (`plat.procedencia_pontuacao`), e um teste
compara as duas em 7 blocos, porque a lista do catálogo não trafega `dados` (jsonb de 58 KB em média) e lê o
selo direto do banco.

Medido (`tests/medidas/L0-09-a-procedencia.json`): camada importada por arquivo nasce com os **4 campos que a
máquina mede** — sha256 do arquivo lido de volta, data de acesso, gerador e método — sem ninguém digitar;
licença e endereço ficam nulos de propósito, porque deduzi-los do nome do arquivo seria a procedência errada
que a regra D17 proíbe.

Onde aparece: ficha e lista (`procedencia` no objeto item), busca (`licenca:CC`, `licenca:nenhuma`,
`procedencia:[5 TO 10]`), filtro lateral (`?licenca=`, `?procedencia_min=`, faceta de licença) e exportação da
lista (colunas `licenca`, `procedencia_pontuacao`, `procedencia_campos`, `procedencia_sha256`,
`procedencia_gerador` no CSV; bloco inteiro no JSON).

Refutação do adversário provada em teste: o mesmo arquivo importado duas vezes dá o mesmo sha256 (e igual ao
`sha256sum` do arquivo de origem); um byte a mais dá hash diferente; licença preenchida com texto vazio vira
`null`, nunca string vazia — na criação e na edição.

Fronteira honesta: a exportação do inquilino inteiro em GeoPackage (`L0-06-d-exportar-inquilino`) ainda não
existe, então a cláusula "exportação leva a procedência" está cumprida na exportação que existe hoje, a da
lista do catálogo. A tela do item mostra o bloco e a pontuação, mas ainda não os EDITA (isso é o
`L0-09-b-editor-iso-mgb`); hoje a edição é pelo formulário de `dados` do próprio item.

## turno 3, setembro de 2026 (item L2-04-a-leitor-rls-martin: quem serve o tile não sabe o que é inquilino)

O servidor de tiles vetoriais fala direto com o PostGIS e não tem noção de sessão, privilégio ou inquilino.
Passa a existir um **papel de banco só de leitura** — LOGIN, sem BYPASSRLS, sem ser dono de nada, com SELECT
nas tabelas de camada e EXECUTE nas funções de tile — e uma função `plat.contexto_por_token`, que valida o
token de serviço, confere escopo `camada:ler` e restrição de Referer/IP, grava o uso em `plat.log_acesso` e
põe o inquilino na transação. Cada camada ganha a sua função de tile `d_<slug>.t_<16 hex>(z, x, y,
query_params)`, criada junto com a tabela; a primeira instrução dela é o contexto por token. Contrato no ADR
0020; o papel, a senha e a linha do `pg_hba.conf` saem de `db/leitor_instalar.sh`, chamado pelo `install.sh`.

A política de RLS do papel de leitura **não olha a GUC `plat.tenant_id` crua**: qualquer papel conectado
escreve nela, e o papel de leitura é o mesmo para todos os inquilinos. Ela olha `plat.tenant_leitor()`, que
exige uma prova (sha256 de um segredo que nenhum papel comum lê, mais o inquilino e o processo) emitida só
por `contexto_por_token`. Medido em `tests/medidas/L2-04-a-leitor-rls-martin.json`: `SET plat.tenant_id` feito
pelo próprio leitor devolve **0 linhas**; **6 chamadas cruzadas** às funções de tile com o token do outro
inquilino devolvem **0 tiles com dado**; token revogado deixa de valer em **0,002 s**; **1 linha de log por
chamada** de contexto aceita; segunda execução do instalador = **0 mudanças**.

⛔ Fronteira honesta: a linha de log de uma RECUSA é escrita e desfeita com a transação abortada (o PostgreSQL
não tem transação autônoma) — medida `linhas_log_de_recusa_persistidas: 0`. O rastro da recusa fica no log do
servidor (a exceção é nomeada) e no log de acesso da API. E o Martin em si não está instalado nem configurado
por este item: o que se entrega é o contrato de banco que ele consome.

## turno 3, setembro de 2026 (item L2-01-a-documento-mapa: o mapa é um documento com esquema, não um punhado de URLs)

O tipo `mapa` deixa de ter `corpo` livre e passa a carregar um **JSON Schema publicado**
(`docs/esquemas/mapa-v1.json`, gerado de `plat.tipo_item`): mapa-base, lista ordenada de camadas com
visibilidade, opacidade, faixa de escala, grupo (até 3 níveis), estilo, popup, filtro CQL2-JSON, rótulos,
campo de tempo e intervalo de atualização; extensão inicial, rotação, CRS de exibição fixo em 3857 e
favoritos. Cada camada aponta o item do catálogo por **uuid** (`ref`), nunca por URL — o oposto do Web Map
JSON da Esri, onde a URL do portal fica congelada dentro de cada mapa salvo. Rotas novas: `POST/GET/PUT
/api/mapas`, `GET /api/mapas` e `GET /api/mapas/{id}/completo`, que devolve o documento com as camadas já
resolvidas (título, tipo, campos, estilo, popup) em UMA chamada. Contrato no ADR 0022; de-para chave a chave
contra a Web Map Specification em `docs/PARIDADE.md`.

Medido em `tests/medidas/L2-01-a.json`: `/completo` de um mapa com **10 camadas** responde com p95 de
**20,7 ms** (mediana 12,2 ms) em **50 chamadas**, contra o teto de 150 ms do portão. Camada de outro inquilino
citada no documento = **404** (o mesmo 404 de uuid inexistente, sem revelar que existe); apagar camada usada
por mapa = **409** com a lista dos mapas dependentes; 500 camadas, 5 níveis de grupo, ciclo de grupo e
extensão fora do mundo = **422**, nenhum 200 e nenhum 500. Na tela `/mapa?id=<uuid>` a lista de camadas
reordena arrastando (e por teclado, Alt+seta): e2e grava a ordem, recarrega a página e confere que voltou a
mesma, com captura em `tests/e2e/capturas/L2-01-a-documento-mapa_painel_camadas.png`.

⛔ Fronteira honesta: `/completo` devolve o CONTRATO da URL de tiles com `pronto: false` e o motivo — não há
servidor de tiles vetoriais nem raster instalado nesta máquina (itens L2-01-b e L1-02) —, e `dominios` sai
vazio com o motivo escrito, porque a camada ainda não guarda vocabulário de domínio (L0-04-c, parcial). A tela
lista e reordena as camadas do documento; não as desenha no canvas, pelo mesmo motivo, e diz isso em cada
linha. ⛔ Quebra declarada: documento com `corpo.camadas` como lista de uuid soltos passa a ser 422.

## turno 3, setembro de 2026 (item L4-01-a-pacote-de-ativos: o esquema da rede de utilidades é dado)

Primeiro item da linha L4. O esquema de uma rede de utilidades — redes de domínio, tiers, grupos e tipos de
ativo, categorias de rede, atributos e configurações de terminal — passa a ser um **pacote de ativos**: um
documento JSON versionado, importado para dez tabelas `plat.rede_*` do inquilino (`POST
/api/rede/{rede_id}/pacote`) e exportado de volta a partir delas (`GET .../pacote`). O contrato está no ADR
0019; o mapeamento coluna a coluna, em `docs/PACOTE_REDE.md`, gerado do próprio dado.

A exportação é **reconstruída das tabelas**, nunca o arquivo recebido — dos 96.042 bytes importados do pacote
`eletrica-br`, saem os mesmos 96.042 bytes, e um teste altera uma linha no banco para mostrar que a exportação
muda junto (`test_a_exportacao_vem_das_tabelas_e_nao_do_arquivo_recebido`). Pacote recusado sai com a lista
inteira de problemas, cada um com o caminho (`tipos[41].grupo`) e a **linha do arquivo enviado**.

Dois pacotes vêm com a instalação: `eletrica-br` (2 domínios, 4 tiers, 14 grupos, 24 tipos, 214 atributos, 24
regras) cobrindo as 13 camadas de rede da BDGD do Módulo 10 do PRODIST, e `agua-epanet` (1 domínio, 2 tiers, 6
grupos, 14 tipos, 41 atributos, 16 regras) no vocabulário do EPANET 2.2.

⛔ Fronteira honesta declarada no próprio dado: dos 214 atributos do pacote elétrico, **154 têm a coluna de
origem conferida contra uma extração real** (11 camadas) e **60 são declarados do documento da fonte, sem
conferência** (`SUB`, `UNSEMT`, `UNCRMT`, `UNREMT`, `UGMT_tab`); o pacote de água é inteiramente declarado.
Nenhum atributo com `conferida = false` deve decidir carga de dado sem antes conferir o dicionário da entrega.
Topologia, traçado e subrede não existem ainda — este item entrega só o catálogo do esquema.
## turno 3, setembro de 2026 (item L2-10-a-dominios-subtipos: domínios de atributo e subtipos por camada)

Domínio de atributo como objeto do inquilino (`plat.dominio`: codificado com lista de códigos, ou intervalo
com mínimo e máximo), ligação campo -> domínio por camada e por subtipo (`plat.dominio_campo`), subtipo como
campo inteiro designado da camada (`plat.camada_subtipo`). **ADR 0021**; migrações
`20260906T1548_dominios_subtipos.sql` e `20260906T1620_dominios_gatilho_gerado.sql`.

- **A regra vale no banco.** Um INSERT direto na tabela da camada como `plat_app`, sem passar pela API, é
  recusado com `campo "uf": o valor 'ZZ' não pertence ao domínio "UF"` e com o nome do campo em `COLUMN` —
  a API repassa isso em `detalhe.campo`. Domínio de intervalo recusa abaixo do mínimo e acima do máximo
  (`campo "altura": o valor -0.1 está fora do intervalo 0.0 a 10.0`). Medido em
  `tests/medidas/L2-10-a-dominios-subtipos.json`.
- **Subtipo troca o domínio do mesmo campo.** Com dois subtipos ligados ao campo `situacao`, `terra` passa no
  subtipo 2 e é recusado no 1; sem subtipo vale o domínio padrão da camada; subtipo fora da lista é recusado.
- **Remover valor em uso = 409 com a contagem.** Quem conta é `plat.dominio_uso_contar`, a mesma função que
  responde `GET /api/dominios/{id}/uso`: quatro feições usando `C1` dão
  `{"erro": "valor_em_uso", "detalhe": {"codigo": "C1", "usos": 4}}`. Valor não usado sai sem drama.
- **Custo do gatilho, medido e corrigido.** A primeira versão, genérica, lia a linha com `to_jsonb(NEW)` e
  custou **1,80x** (10 mil inserções: 1,72 s sem gatilho, 3,11 s com) — acima do teto de 1,5x do item. Um
  gatilho que só faz `to_jsonb(NEW)` já custa cerca de 129 us por linha, porque converte a linha inteira, com
  geometria. O gatilho passou a ser GERADO por camada (`plat.dominio_v_<item>`, com `NEW.uf` no código), e
  três gatilhos AFTER (em `plat.dominio_campo`, `plat.camada_subtipo` e `plat.dominio`) regeneram a função
  sozinhos — nenhuma rota instala gatilho, e quem mexe por `psql` regenera do mesmo jeito.
- **FeatureServer com domains e types.** `GET /rest/services/{item_id}/FeatureServer/0` publica
  `fields[].domain` (codedValue e range) e `types[]` com `domains` por subtipo e `templates` com os valores
  padrão; conferido contra o que `GET /api/camadas/{id}/dominios` devolve do banco. É só o METADADO: `/query`
  e `/applyEdits` são da linha L2-08.
- **Tela `/camadas/{id}/dominios`.** Campo com domínio codificado vira lista de escolha que mostra a descrição
  e grava o código; trocar o subtipo refaz os campos dependentes e aplica os padrões; a tabela de feições usa
  a mesma tradução (`web/js/dominios/valores.js`, a função única do formulário, da tabela e — quando o painel
  de camada existir — do popup).
- **CSV de ida e volta** (`GET /api/dominios.csv`, `POST /api/dominios/csv`) e **importação do `fields`/`types`
  de um FeatureServer/FGDB** (`POST /api/dominios/importar`), que reaproveita domínio de mesmo nome em vez de
  duplicar.

Testes: `tests/api/test_dominios_subtipos.py` (inclui a refutação exigida: domínio de outro inquilino = 404,
50 mil códigos = 422, código duplicado recusado na API e no banco, trocar o tipo de campo com domínio ligado
= 409) e `tests/e2e/test_dominios.py` (playwright, com capturas).

## turno 3, setembro de 2026 (item L0-04-a-upload-arquivo: upload retomável pelo navegador)

Upload de arquivo em partes de 16 MiB pelo navegador, retomável (`POST /api/uploads` reserva cota do inquilino
e abre o multipart no Garage; `PUT /api/uploads/{id}/partes/{n}` aceita partes fora de ordem e reenviadas — o
`addPart` da Esri; `POST /api/uploads/{id}/concluir` fecha o multipart, confere sha256/tamanho/tipo×conteúdo e
registra o item `arquivo` no catálogo; `DELETE` aborta). Vocabulário de 14 tipos declarados (shapefile.zip,
gpkg, geojson, kml, kmz, csv, gpx, xlsx, dxf, dwg, gdb.zip, parquet, fgb, gml, zip) provados pelo CONTEÚDO real,
nunca só a extensão (`app/uploads/tipos.py`); os zip-baseados usam `app.ingestao.formatos.conferir_zip`
(arquivo pequeno) ou um parser do formato PKZIP por leitura em intervalo (`app/uploads/zip_remoto.py`, arquivo
grande — nunca baixa o objeto inteiro para RAM, motivo é a máquina ter pouca RAM livre e o item aceitar até
2 GiB por arquivo). Periódico `uploads.expirar` (`*/30 * * * *`) apaga upload sem atividade há 24 h em
qualquer inquilino (SECURITY DEFINER cruzando tenants, mesmo mecanismo de `plat.sessoes_expurgar`). Tela
`/uploads` (dropzone, barra de progresso nativa, identidade "instrumento").

Decisão registrada: a cota reservada NÃO usa `tenant.uso_reservado_bytes` (a hipótese do ADR 0005) — aquela
coluna já foi tomada por outra trilha para "armazenamento de tabela carregada", com significado explicitamente
"independente da cota do bucket Garage". A reserva deste item é a soma de `plat.upload.bytes_declarado` em
estado `iniciado` do inquilino (`plat.upload_reservado_bytes`), sob o mesmo `SELECT ... FOR UPDATE` da linha
do tenant.

Achado de processo (não de produto): a migração original (`044_uploads.sql`) colidiu com uma tabela IDÊNTICA
já aplicada ao banco compartilhado por outra sessão desta árvore, cujo código Python nunca apareceu em lugar
nenhum encontrado — registrado no handoff para o coordenador verificar se há uma segunda linha de trabalho no
mesmo item. Renomeada para `046_upload_retomavel.sql`, escrita para ser segura contra o schema já existir.

Testes: `tests/unit/test_uploads_tipos.py` (32, sem banco) + `tests/api/uploads/test_uploads.py` (18, API real:
100 MB em 7 partes com a 4ª reenviada e sha256 igual; `.gpkg` com zip dentro recusado com a mensagem exata;
2,1 GiB e cota insuficiente recusados com 413 antes de qualquer byte; zip-bomba de 1.500 entradas e caminho
`../` recusados; duas conclusões concorrentes — uma vence, a outra vê `ja_concluido`; duas sessões enviando
partes diferentes ao mesmo tempo — as duas terminam OK; upload esquecido expira em 24 h pelo periódico real)
+ `tests/e2e/test_uploads.py` (playwright contra a URL interna, barra de progresso, 0 erro de console).
`taxa_upload_mb_s` = 92,1 MB/s (local, `tests/medidas/L0-04-a-upload-arquivo.json`).

## turno 3, setembro de 2026 (item L0-07-b-papeis-privilegios: vocabulário fino, conferência Esri e gate de rebaixamento)

O grosso de privilégios/papéis já existia do L0-02 (vocabulário fechado, papéis personalizados, tela `/admin/papeis`,
`plat.tem`/`plat.privilegios_de`); este item fechou o que faltava do portão. `docs/gerar_privilegios.py` lê
`plat.privilegio`/`plat.perfil_privilegio` AO VIVO no banco (nunca `app/auth/privilegios.py`) e escreve
`docs/PRIVILEGIOS.md` (47 privilégios, 12 grupos, 20 administrativos), com `tests/api/test_privilegios_doc.py`
provando que o comitado bate com o banco agora. `tests/api/test_privilegios_matriz.py` chama toda rota do OpenAPI
vivo cujo `x-privilegio` é um nome puro do vocabulário (sozinho ou em composição `a|b`) com um usuário que
provadamente não o tem, e exige `403` em todas — dois clientes só bastam (um só com `tokens.gerar`, outro só com
`membros.ver`, a interseção perfil×papel do ADR 0002 faz o resto); a exceção nomeada (`PUT
/api/itens/{id}/compartilhamento`, que checa posse do item ANTES do privilégio de compartilhar) ganhou teste à
parte provando o gate real com o dono do item.

Achado do adversário: rebaixar o perfil de um usuário que possui itens do catálogo não era recusado —
`_editar` (`app/auth/rotas_usuarios.py`) só checava grupos (`409 possui_grupos`); a regra da Esri (E12-members)
é "não possui conteúdo NEM grupos". Corrigido com o mesmo padrão (`409 possui_itens`, listando os itens);
`tests/api/test_usuarios.py::test_rebaixar_perfil_com_itens_e_recusado` prova a recusa, que promover não
esbarra na regra, e que a purga do item destrava o rebaixamento.

Paridade linha a linha contra a lista de privilégios da Esri 11.4 (E12-priv, `laco/handoffs/T1/21_esri.md` §1.3):
43 gerais + 33 administrativos = 76 privilégios Esri, **35 feito · 11 parcial · 30 fora** — cada `fora` é uma
decisão de escopo já nomeada em outro item (notebook, app OAuth, pipeline, versionamento de dado, colaboração
entre organizações, licença/assento, vídeo, grafo de conhecimento, relatório de uso), nunca uma lacuna descoberta
agora. Tabela completa em `docs/PARIDADE.md` seção "Privilégios e papéis personalizados".

e2e novo (`tests/e2e/test_papeis.py::test_papel_curador_categoriza_mas_nao_publica`, captura
`L0-02-tenant-auth_papel_curador.png`): papel "Curador" (`conteudo.criar` + `conteudo.categorias`, este último
administrativo — só cabe em perfil `admin`) criado pela tela, atribuído a um usuário novo; ele reescreve a árvore
de categorias e cria conteúdo comum, mas uma tentativa de criar/publicar camada vetorial nega com `403
sem_privilegio` (`exigido: conteudo.publicar_camada`).

Refutação própria (papel esri+backend+frontend+testador+adversário, sem subagentes — item pequeno o bastante
para uma sessão): papel administrativo atribuído a perfil abaixo do teto → `422 papel_incompativel` (já provado
em `test_so_admin_cria_altera_e_apaga_admin`); ninguém concede privilégio que não tem → `403
privilegio_proprio_insuficiente` (`test_privilegios_e_papeis`); apagar papel em uso → `409 papel_em_uso`; as
~40 rotas de privilégio puro do OpenAPI vivo, uma a uma, sem o privilégio declarado → `403` em todas
(`test_privilegios_matriz.py`). Nenhuma reprovação nova encontrada além da já corrigida (`possui_itens`).

Pendente, registrado no handoff: teste automatizado do downgrade de tipo Esri "Creator → Viewer com conteúdo"
não tem equivalente 1:1 (nossa spec não tem tipo separado de perfil — decisão D5/D16 já registrada); relatório
de uso administrativo (`Content: Create and manage administrative reports`) e alguns privilégios de
colaboração/servidor seguem `fora` por decisão de escopo, não por falta de tempo.


## turno 3, setembro de 2026 (item L2-11-b-geocodificador-brasil: geocodificador próprio sobre CNEFE 2022)

Geocodificador PRÓPRIO em PostgreSQL/PostGIS (sem Nominatim/Pelias, decisão D28 sobre disco), base = CNEFE
2022 do IBGE. `db/migracoes/045_geocodificador.sql` (`plat.geo_uf`, `plat.geo_municipio`, `plat.geo_endereco`,
`plat.geo_instalacao`) + `scripts/geocodificador_instalar_uf.py` (baixa e mede o tamanho por `HEAD` antes,
carrega por `COPY` em lotes) + `app/geocodificador/` (normalização, motor de busca/reverso/sugestão, API
própria e `GeocodeServer` compatível Esri). Demo instalada: Roraima (menor arquivo de UF do CNEFE, 4,52 MB
comprimidos, 260.515 pontos, 15 municípios, carga em 10,4 s).

Medido (`tests/medidas/L2-11-b-geocodificador-brasil.json`, 50 endereços reais + 50 pontos reais do CNEFE):
erro mediano de geocodificação **0,0 m** (portão ≤ 30 m), acerto de número/face **98,0%** (portão ≥ 90%),
reverso acerta o logradouro em **100%** (portão ≥ 90%), sugestão p95 **33,1 ms** (portão ≤ 100 ms). Achado
de carga corrigido ANTES do commit: `COD_UNICO_ENDERECO` do CNEFE não é chave única (260.516 linhas, só
249.268 ids distintos em Roraima) — a tabela usa `id bigserial` como chave e guarda o código do IBGE em
coluna indexada não-única. Ambiguidade entre municípios (a refutação pede "Rua A" em São Paulo, o maior
arquivo do CNEFE, fora do teto de disco D28) foi provada com o mesmo fenômeno em Roraima: `RUA A` se repete
em 8 dos 15 municípios, medido. Consistência CEP × município/UF recusa com `422` quando os dois sinais
apontam lugares diferentes. QGIS como locator real fica como PENDÊNCIA nomeada (sem QGIS/ambiente gráfico
nesta máquina) — o protocolo foi provado por chamada HTTP direta simulando o que o QGIS manda. Ver ADR 0013
e `docs/PARIDADE.md` seção "Geocodificador".

## turno 3, setembro de 2026 (item L2-10-c-linguagem-expressao: conserto das três refutações do adversário)

O ataque adversarial (`laco/handoffs/T3/L2-10-c-ADVERSARIO.md`) refutou o item em três cláusulas. As três
foram consertadas no código e no documento; os 38 testes que o adversário deixou como `xfail(strict=True)`
passam sem que nenhum tenha sido apagado ou afrouxado (`venv/bin/pytest tests/unit/test_expressao_*.py`
= 1.652 casos, 0 falha, 0 xfail).

1. **Equivalência Python × JavaScript.** As 26 divergências que ele mediu fora dos 309 vetores vinham todas
do mesmo lugar: operação entregue ao operador ou à biblioteca da língua. A semântica passou a ser do
CONTRATO, escrita à mão nos dois lados e publicada em `docs/EXPRESSAO.md` §3.1 — resto (`%`) com o sinal do
DIVIDENDO (`math.fmod`, como o JavaScript/C/SQL); texto medido, cortado, comparado e casado em PONTO DE
CÓDIGO, com par substituto contando como um; `Numero` só com algarismo ASCII; data arredondada sempre para
baixo. Os 26 casos viraram vetor compartilhado em `tests/expressoes/vetores_convergencia.json` (30 vetores,
`vetores_de_convergencia_pos_adversario`), rodados junto dos 309 pelo teste de equivalência.

2. **Exceção crua.** `TextoNumero($x,15)` com 1e13 levantava `decimal.InvalidOperation` (contexto padrão de
28 dígitos). `_decimal_fixo` passou a usar `decimal.localcontext` com 60 dígitos e `avaliar` a capturar
`decimal.DecimalException` como `numero_invalido`: o Python agora formata o mesmo texto que o `toFixed` do
JavaScript nos cinco casos do ataque.

3. **Tabela de paridade com o Arcade.** A tabela inteira (134 linhas em 7 categorias) foi revista com o
critério estreito — `feito` só sem NENHUMA diferença conhecida e com vetor de teste da nossa função. As 6
linhas que o adversário derrubou (`Month`, `Now`, `Abs`, `Reverse`, `Back`, `Front`) e mais 12 viraram
`parcial` com a diferença escrita; `DefaultValue` deixou de ter estado contraditório. De **29 feito · 24
parcial · 81 fora** para **11 feito · 42 parcial · 81 fora** (`linhas_feito_na_paridade_arcade`).
`tests/unit/test_expressao_paridade.py` (novo) impede a volta da mentira: linha `feito` sem vetor reprova,
contagem de cabeçalho que não bate com as linhas reprova, `docs/PARIDADE.md` fora de sincronia reprova.

Também consertado (gravidade baixa, mesmo laudo): contexto de topo do lado JavaScript recusa objeto que não
é dicionário simples e, no Node, recusa `Proxy` (`util.types.isProxy`) — no navegador não há detecção
possível e isso está escrito em §7; campo desconhecido dentro de nó de AST passou a ser RECUSADO
(`no_desconhecido`) em vez de ignorado, e a importação lê cada campo por descritor, sem disparar getter.

## turno 3, setembro de 2026 (item L0-02-g-perfil-usuario: perfil próprio — foto, idioma, unidades, formato de data, visibilidade)

Conferido antes de escrever (portão da hipótese vs. o que já existia): a tela `/conta` herdada do
L0-02-tenant-auth já cobria 2 das 8 cláusulas do portão deste item (domínio de e-mail recusado com mensagem;
`login`/`perfil`/`papel_id`/`ativo` já fora da whitelist de `PUT /api/eu`) — as outras 6 (idioma, unidades,
formato de data, foto com limite de tamanho e recodificação, visibilidade) não tinham uma linha de código
(`grep` de `idioma_preferido`/`unidades`/`formato_data`/`foto_perfil`/`visibilidade_perfil` em `app/`, `web/`,
`db/migracoes/` = 0 ocorrências, handoff `laco/handoffs/T3/L0-02g-L0-05c.md` do turno anterior). Migração 042
acrescenta as 5 colunas a `plat.usuario` (idioma_preferido, unidades, formato_data, visibilidade_perfil,
foto_sha256), todas com `CHECK` de vocabulário fechado. `PUT /api/eu` ganha os 4 campos novos na MESMA
whitelist de `campos_json` (nunca uma segunda checagem: o mecanismo que já impedia escalar perfil/login é o
mesmo que agora valida os campos novos). `POST/DELETE /api/eu/foto` reaproveita o adaptador do L0-11
(`app/objetos.py::guardar`, classe `usuario_foto`) e o MESMO truque de base64 sob cookie que
`POST /api/org/logo` (L0-07-a) já usa — recorte central 200×200 pelo Pillow (`ImageOps.fit`, não `contain`
como o logotipo: rosto fica melhor cortado que emoldurado), sem metadado, sem os bytes originais do cliente.

Refutação do próprio item testada e passando: um SVG com `<script>` como foto nunca chega a ser interpretado
(o Pillow não abre SVG, recusa com `415 formato_nao_aceito` antes de qualquer gravação); tentativa de
`login`/`perfil`/`papel_id`/`ativo`/`superadmin` no `PUT /api/eu` continua `400 campo_nao_editavel`; e-mail
fora do domínio do PRÓPRIO inquilino (testado restringindo `demo`, não só o teste unitário de
`email_permitido`) continua `422 email_dominio` nomeando a lista. Foto acima de 1 MiB é `413 foto_grande`
(ou `422` quando o próprio limite do corpo em base64 já corta antes). e2e novo em `tests/e2e/test_conta.py`
(`test_perfil_nome_unidades_foto_na_barra_e_email_fora_do_dominio`) prova edição de nome/unidades, envio de
foto com aparição na barra lateral SEM recarregar (`#pessoa-foto`), e a mensagem de domínio recusado —
captura `L0-02-tenant-auth_perfil.png`, verificada visualmente. 20 testes de API novos em
`tests/api/test_eu.py` + 2 casos novos em `tests/api/cruzado_casos.py` (varredura cruzada A→B de
`POST/DELETE /api/eu/foto`, mesmo padrão do `org_logo`).

Bloqueio ambiental encontrado e NÃO causado por este item: o fixture `autouse` de sessão
`limpeza_de_residuos` (`tests/api/conftest.py`) depende de `sessao_plat` (superadmin do inquilino
`plataforma`, 2FA obrigatório) e o segredo TOTP guardado em `tests/credenciais_totp.txt` não bate mais com
o que está no banco — bloqueia `pytest` de TODA a suíte de API (não só deste item) até alguém religar o 2FA
do superadmin pela via legítima. A API completa foi verificada por um script equivalente fora do pytest
(mesmo `TestClient`, mesmo banco, autenticando como admin do inquilino `demo`, que não exige 2FA) — ver o
handoff do turno. `docs/openapi.json` e `docs/LIMITES.md` regenerados; `plat-api` (systemd) reiniciado para
servir o código novo aos e2e (verificado antes e depois: RAM estável, sem incidente). Docs: `MANUAL.md` §3.1a,
`ARQUITETURA.md`, `docs/PARIDADE.md`. Pendente, nomeado (não prometido como feito): consumo de
`unidades`/`formato_data` para reformatar número/data em outras telas e uma tela de "perfil de outro
usuário" que leia `visibilidade_perfil` — nenhuma das duas existe hoje; `idioma_preferido` é preferência
guardada, a aplicação de fato é o item `L7-10-a-i18n-pt-en-es` (pendente).

## turno 3, setembro de 2026 (itens L6-01-d-ficha-fonte · L6-01-f-lgpd: ficha do acervo completa + gate de LGPD no "adicionar")

Conferido antes de escrever: a ficha (`GET /api/acervo/{fonte_id}`, migração 021, item anterior) já tinha os
10 campos de procedência da hipótese (url, licença, frescor, data do dado, script gerador, sha256, método,
confiança, limites, próxima verificação) — `limites` já é "o que este dado não sustenta" em conteúdo real.
Somado nesta passagem: **`endpoints`/`endpoints_total`/`endpoints_confirmados_vivos`**
(`plat.acervo_endpoint`, migração 040, sobre `acervo.endpoint`, "vivo" = `confirmado AND http = '200'`) e
**`completude_texto`** ("4,5/10" por extenso; `None` nunca fabricado quando falta base de cálculo).

`acervo.fonte` não tinha campo de classificação de risco de dado pessoal (conferido por `\d`) — criada
**`plat.acervo_lgpd`** (migração 041), curada à mão (sem GRANT de escrita a `plat_app`), depois de uma
varredura real de 219 tabelas canônicas das 68 fontes licenciadas contra um padrão amplo de coluna (114
batidas, lidas uma a uma — a maioria nome de lugar ou CNPJ de fundo, não pessoa física). Achado real único:
**`onr`** (matrículas) — `url_mat` aponta para o documento de cartório com o nome do titular, mesmo a tabela
ingerida não guardando o nome. `POST /api/acervo/{fonte_id}/adicionar` recusa com 409
`confirmacao_pii_exigida` para fonte marcada sem `{"confirma_risco_pii": true}` no corpo, registrando a
recusa como evento (`acervo/adicionar_recusado_pii`) em transação própria (mesmo padrão de
`_falhou()`/`_bloqueado()` do login — registrar e levantar no mesmo bloco de `db.db()` apagaria o evento no
rollback). 16 testes novos/estendidos em `tests/api/test_acervo.py` (ficha de 20 fontes campo a campo,
campo ausente nunca fabricado, gate de LGPD com e sem confirmação, regressão da maioria sem curadoria).
**Sem tela ainda** (L6-01-c) e sem a classificação por COLUNA em `plat.acervo_camada` (fica pendente, não
prometida como feita). Docs: `MANUAL.md` §19, `ARQUITETURA.md` §16, `docs/PARIDADE.md`.

## turno 3, setembro de 2026 (item L2-10-c-linguagem-expressao: extensão do núcleo — 43 funções, 309 vetores Python=JavaScript, listas e dicionários, formatação pt-BR)

Continuação do núcleo entregue no mesmo turno (18 funções, 41 vetores). Passa a **43 funções**
(`tests/medidas/L2-10-c-expressao.json`, `funcoes_implementadas`), com texto (`Trim`, `Left`, `Right`,
`Mid`, `Find`, `Split`, `Replace`), número (`Floor`, `Ceil`, `Sqrt`), data (`Weekday`), escolha
(`Decode`), onze de coleção (`Lista`, `Contagem`, `Primeiro`, `Ultimo`, `Obter`, `Contem`, `Soma`,
`Media`, `Reverter`, `Unicos`, `Juntar`) e formatação pt-BR (`TextoNumero`, `TextoData`). Os tipos
**lista e dicionário** entram como valor de primeira classe, sem gramática de literal: a lista vem de
`Lista(...)` e o dicionário vem do contexto — o que fecha o caminho de um literal grande no texto da
expressão virar custo de análise.

**309 vetores** (`vetores_de_equivalencia`) rodam nos dois avaliadores e são comparados byte a byte
(`test_expressao_equivalencia.py`); os mesmos 309 passam pelo AST exportado → JSON → reimportado em
Python, em JavaScript e CRUZADO (AST escrita pelo Python, lida pelo JavaScript), com resultado idêntico
(`vetores_ast_ida_e_volta_nos_dois_lados` = 309). Erro nomeado igual nos dois runtimes em 46 casos de
ataque de tipo, limite e chave proibida (`test_expressao_extensao.py`); `__proto__`, `prototype` e
`constructor` são `campo_nao_permitido`, e o lado JavaScript não lê propriedade herdada nem executa
getter (medido: 0 leituras).

Limites medidos SOB ATAQUE, com o custo escondido dentro de uma chamada (comparação estrutural
quadrática em `Unicos` sobre 1.024 dicionários, 40 termos ≈ 21 milhões de comparações), não só com
árvore funda: corte pelo relógio em **50,63 ms** no Python e **53,65 ms** no JavaScript contra o teto de
50 ms do cliente, e **500,69 ms** contra o teto de 500 ms do servidor; com o relógio folgado o mesmo
ataque para em `limite_passos` (10^5), provando que os dois orçamentos cortam de forma independente.
Novos tetos por VALOR (1.024 itens por coleção, 4.096 nós, 20.000 pontos de código, profundidade 20)
recusam com `valor_grande` antes de a memória crescer.

**Paridade função a função com o Arcade function reference** (269 funções em 17 categorias, lido em
setembro de 2026) na seção 10 de `docs/EXPRESSAO.md`, resumida por categoria em `docs/PARIDADE.md`:
29 feito · 24 parcial · 81 fora nas 7 categorias com correspondência; as outras 10 categorias
(135 funções — FeatureSet, geometria, pixel, voxel, trajetória, portal, grafo, IA, depuração, empresa)
ficam inteiras de fora, cada uma com o motivo. Paridade de CAPACIDADE, nunca promessa de rodar script
Arcade sem adaptação: todo nome nosso é em português.

A EBNF do documento continua GERADA das tabelas de precedência do parser e conferida byte a byte
(`test_expressao_doc_sincronizada.py`), o que pegou nesta passagem uma divergência real: a ordem dos
operadores de comparação mudou no código e o documento ficou para trás.

FICA DE FORA e está escrito na seção 11: geometria, `Filter`/`Map`, domínio, `FeatureSetByRelationship`,
integração com popup/rótulo/formulário (L5-11), fuso horário do usuário e máscara livre de formatação.
A cláusula do portão "expressão que acessa camada de outro inquilino = erro de permissão" **não foi
provada**: não há camada ligada à expressão, logo não há caminho de acesso para atacar.

## turno 3, setembro de 2026 (itens L6-01-a-registro · L6-02-a-modelo-conexao-e-seguranca: registro de camadas do acervo + modelo genérico de conexão externa com defesa de SSRF)

Dois itens da linha L6, ADR 0012. **L6-01-a-registro** é FILHO DIFERENTE do já entregue
L6-01-a-procedencia-acervo (migração 021): aquele é a ficha da FONTE (376 linhas, sem geometria); este é o
registro de CAMADA — `plat.acervo_camada` (migração 030, renumerada de 028 por colisão com a trilha
concorrente do documento de construtor), uma linha por tabela canônica com geometria, populada por
`scripts/acervo_sync.py` (roda como `postgres`, psycopg2 do dpkg, sem venv). Medido 06/09/2026: 462
candidatas (270 em `public`) via `geometry_columns`×`acervo.objeto`; `COUNT(*)` exato com timeout de 25 s
(nunca `reltuples`); tabela fantasma é regra DINÂMICA (estimativa > 0 e exata = 0), nunca lista de nomes —
cobre as 2 fantasmas conhecidas do registro (`public.prodes_yearly_all_indexed`,
`farma.djen_pub_termo`) sem citá-las em código. Lista branca de colunas por nome (rede mínima, provisória —
o reforço por conteúdo é o item L6-01-f, ainda não construído). Duas rodadas completas medidas: 274,9s e
286,0s (ambas sob o portão de 5 min), com a máquina disputada por outro job pesado da casa (REFRESH
MATERIALIZED VIEW de 3h + COUNT(*) de 18 min concorrentes); ordem de processamento por "há mais tempo sem
sincronizar" prova convergência entre rodadas (81→172 expostas da 1ª para a 2ª). Achado ao testar: `--limite`
de depuração estava apagando o registro completo de rodadas anteriores (a poda comparava contra o que a
rodada limitada processou, não contra o universo real de candidatas) — corrigido antes de qualquer uso além
de teste. 6 testes em `tests/api/test_acervo_camada.py` (+ 1 `lento` rodando o universo inteiro).

**L6-02-a-modelo-conexao-e-seguranca**: `plat.conexao` (tenant_id+RLS; mesma migração 030) — tipo em
vocabulário fechado (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/PMTiles/postgres_fdw/s3/http), `config`
JSONB, credencial cifrada com AES-GCM (`app/conexao/credencial.py`, prefixo `encconexao:v1:`, mesmo padrão do
TOTP e do bind LDAP — nunca `pgp_sym_encrypt`, que deixaria a chave passar pelo SQL). Só o MODELO e a
segurança nesta trilha — os 15 conectores concretos são itens futuros. `app/conexao/seguranca.py` defende
contra SSRF: esquema só http/https, sem userinfo, resolve o host com timeout numa thread separada, recusa IP
privado/loopback/link-local (inclui `169.254.169.254`)/CGNAT(100.64.0.0/10, gap medido de
`ipaddress.is_private`)/reservado/multicast, conecta PINADO no IP já validado (subclasse de
`httpcore.SyncBackend`; o TLS continua verificando o hostname original via `server_hostname`, então
DNS-rebinding não passa), e revalida CADA redirecionamento do zero (nunca segue automático) até 5 saltos.
Provado com servidor de teste bindado no IP PÚBLICO REAL desta máquina (nunca loopback, para não confundir
com o caso 1) redirecionando para `169.254.169.254`: aceita o hop 0, recusa só o hop 1. `POST /api/conexoes/
{id}/testar` roda o teste de saúde com timeout curto (conectar 3s/ler 6s) contra um endpoint público real
(IBGE, dado aberto); a credencial nunca aparece em resposta de API nem em log (provado com `caplog`). 25
testes em `tests/unit/test_conexao_seguranca.py` (os 8 casos do portão) + 13 em `tests/api/test_conexoes.py`
(CRUD, RLS cruzada A→B, unicidade de nome, tamanho de `config`, credencial oculta).

`make check` rodado sob `flock laco/.pytest.lock`; migração `030_conexao.sql` aplicada via `db/migrar.sh`
(registrada em `plat.versao_migracao`, junto com `027_acervo_camada.sql` e as migrações da trilha
concorrente que já estavam no disco). Documentação: `docs/adr/0012-registro-do-acervo-e-conexao-externa.md`,
`docs/PARIDADE.md` (2 seções novas).

## turno 3, setembro de 2026 (item L5-05-documento-versoes: documento de construtor — grafo de nós com ULID)

Base genérica que qualquer construtor do L5 (app, painel, e depois formulário, fluxo) vai usar para gravar um
grafo: reaproveita por inteiro `plat.item.dados`/`plat.tipo_item.esquema`/`plat.item_versao` de L0-03 (nenhuma
tabela nova). `app/catalogo/documento.py` acrescenta o que JSON Schema puro não expressa: `validar_grafo`
recusa (`422 grafo_invalido`) dois nós com o mesmo `id` ULID ou uma ligação apontando para um nó inexistente
em `corpo.nos`; `migrar_para_leitura` aplica `migrar_<tipo>_v<N>_v<N+1>` **na leitura** (nunca grava de volta
no banco) e registra o evento `itens/esquema_migrado`; `sha256_canonico` (json.dumps ordenado, sem espaço) é
um hash À PARTE do `sha256` de `item_versao`, reproduzível fora do banco por qualquer `sha256sum` — o
`sha256` de `item_versao` vem de `corpo::text` do jsonb do Postgres, MEDIDO nesta máquina como NÃO
reproduzível fora sem reimplementar a serialização interna do banco (ordena chave por comprimento-depois-
alfabeto, espaço depois de `:`/`,`).

Migração `028_documento_grafo.sql`: esquema de `app`/`painel` passa de trivial (`corpo:{}`) para grafo
(`corpo.nos`/`corpo.ligacoes` — os dois OPCIONAIS, então os 1.573/1.571 itens já semeados em demo/demo2
continuam válidos sem migração de escrita); `corpo.mapas`/`mapa_id` continuam aceitos porque são o contrato
já entregue de `app/catalogo/relacoes.py::_app` (item L0-03-i) — quebrar esse campo quebraria "usado-por" de
app/painel→mapa. Endpoints novos: `GET /api/esquemas` (lista de tipos com esquema publicado), `GET
/api/esquemas/{tipo}?versao=N` (serve o mesmo JSON Schema que valida `dados`, para o editor e para o agente
escreverem contra o mesmo contrato), `GET /api/itens/{id}/integridade` (recomputa o sha256 de cada versão a
partir do `corpo` gravado e compara com o `sha256` da linha — detecta edição direta em `plat.item_versao` por
fora do gatilho; só quem tem acesso de superusuário ao Postgres consegue fazer isso, `plat_app` tem
INSERT/UPDATE/DELETE revogados na tabela desde a 011). `docs/gerar_esquemas.py` espelha o esquema vigente de
`app`/`painel` em `docs/esquemas/<tipo>-v2.json` (mesma disciplina de `docs/gerar_limites.py`, `--check`
falha se divergir do banco); `docs/esquemas/<tipo>-v1.json` ficam como registro histórico, nunca regerados.

10 testes em `tests/api/catalogo/test_documento.py`: grafo válido cria e a versão traz `sha256_canonico`;
hash reproduzido fora do banco com `sha256sum` de verdade (subprocesso Python + hashlib, bate byte a byte);
nó sem ULID / ULID repetido / ligação pendente recusados na criação E na edição; rascunho nunca muda a versão
publicada até publicar explicitamente (e a versão anterior continua legível depois de publicar a seguinte);
ULID de nó nunca se repete em nenhuma versão ao longo de 5 edições; migração de esquema_versao=1 para 2 na
leitura, com o evento gravado, e a linha do banco continua em 1 (a migração não gravou de volta); RLS cruzado
(versões e integridade de um documento de outro inquilino = `404`); `plat_app` não consegue editar
`plat.item_versao` direto (confere a premissa do teste de corrupção); corrupção direta na linha de versão
(`sudo -u postgres psql`, simulando acesso de superusuário) aparece em `/api/itens/{id}/integridade`.
Latência medida: mediana de 30 `PUT /api/itens/{id}` (painel, 2 nós) = **17,3 ms**
(`tests/medidas/L5-05-documento-versoes.json`, `latencia_salvar_versao_ms`). Rotas novas cadastradas em
`tests/api/cruzado_casos.py` (P6: `/api/esquemas`, `/api/esquemas/{tipo}` como vocabulário — mesmo padrão de
`/api/tipos-item`; `/api/itens/{id}/integridade` como alvo padrão 401/403/404).

Decisões em `docs/adr/0011-documento-de-construtor.md`. Detalhe: `MANUAL.md` seção 17, `ARQUITETURA.md` seção 14.

## turno 3, setembro de 2026 (item L1-01-d-garage-por-inquilino: balde por inquilino com cota dupla, chave só-leitura e COG por Range)

Constrói sobre o adaptador do L0-11 (ADR 0006) o que a linha de imagens precisa. **ADR 0016**; migração
`20260906T1547_garage_inquilino.sql` (a reserva original era 034, e depois 042, mas a árvore principal já tinha commitado 034/036/040/041/042
— renumerada e registrada no handoff).

- **Cota dupla.** `plat.tenant.cota_objetos` e `plat.arquivo_bucket.cota_objetos` novas; `UpdateBucket` do Garage
  passa a receber `quotas: {maxSize, maxObjects}`. Medido: com `maxObjects` na conta exata, o PUT seguinte volta
  403 e a mensagem que chega à API é **"o Garage recusou a gravação: a cota de objetos do inquilino foi atingida
  (limite do balde: N objetos)"** — em português, com o limite que o próprio Garage citou
  (`app/garage.traduzir_erro_s3`, classe `CotaGarage`). Para bytes a instância mediu **"o Garage recusou a
  gravação: a cota de armazenamento do inquilino foi atingida"** — sem número, porque essa mensagem do Garage não
  cita o limite. `POST /api/arquivos` acima da cota devolve **413 `cota_excedida`**; a frase que chega ali é a da
  checagem prévia ("cota de 500 bytes excedida: uso atual 138906, objeto de 2048 bytes"), porque ela corre antes e
  é mais informativa — a do Garage é a que sobe quando a prévia deixa passar.
- **Semeadura de instalação.** Passo `g3` do `install.sh` (`python -m app.baldes_semear`): balde, duas chaves,
  as duas cotas e o endpoint web por inquilino ativo. Medido no inquilino de teste: 1ª execução **1
  criado/alterado**, 2ª **0 criados/alterados**. A semeadura lê o balde de volta pela Admin API e reaplica quando
  o Garage discorda do banco — foi assim que se descobriu `plat-demo` com `maxObjects: null` no Garage e 200000
  no banco.
- **Objeto nomeado por conteúdo, nunca sobrescrito.** `app/objetos_raster.py`: `<item_id>/<asset>_<sha8>.<ext>`,
  `HEAD` antes de gravar, `ObjetoJaExiste` na segunda gravação do mesmo conteúdo; conteúdo novo produz chave nova
  (medido: `demo/zt_sobrescrita/cog_c9e41e3e.tif` → `cog_ebd6a855.tif`, a versão 1 intacta). A expressão da chave
  não admite ponto nem barra no item/asset: dez formas erradas (`..`, `../../etc`, maiúscula, sha curto) recusadas
  no teste unitário.
- **Chave só-leitura que sai de casa.** `GET /api/arquivos/_chave-leitura` (sessão + `org.integracoes`) entrega a
  credencial S3 RO do balde para a conexão do ArcGIS Pro e o `/vsis3` do TiTiler; a chave RW nunca sai. Refutação
  medida com boto3: com a chave RO, `PutObject` **403**, `DeleteObject` **403**, `CopyObject` no mesmo balde
  **403**, `CopyObject` entre baldes **403**, `CreateMultipartUpload` **403**; `ListBuckets` responde 200 mas
  mostra só `['plat-demo']` (o balde do outro inquilino não aparece). Contra o balde do vizinho, `GetObject`,
  `HeadObject` e `ListObjectsV2` = **403** cada.
- **COG por HTTPS com Range.** Bloco `/svc/<token>/cog/<slug>/...` em `deploy/nginx.conf` (`slice 1m`, cache das
  fatias, `auth_request` contra `GET /api/arquivos/_cog/autorizar`). Provado contra um nginx PRÓPRIO de teste
  (porta 8162, certificado autoassinado): objeto de 3.146.505 bytes, `Range: bytes=1048576-1048591` responde
  **206** com `Content-Range: bytes 1048576-1048591/3146505`, 16 bytes conferidos contra o conteúdo gravado;
  token inválido no caminho = **403** antes de o Garage ver a requisição. **O bloco NÃO foi aplicado no nginx do
  sistema neste turno** — quem aplica é o gerente.
- **Apagar devolve a cota.** `objetos_raster.apagar_item` mediu 72 objetos/138.095 bytes antes → 75/153.095 com
  3 objetos gravados → 72/138.095 depois, com os contadores do próprio Garage (GetBucketInfo). Segunda chamada
  devolve zeros. `objetos.apagar_bucket_do_inquilino` desfaz o balde inteiro (objetos, as duas chaves, o balde e
  a linha), porque `plat.inquilino_apagar` só limpa o banco.

Medidas em `tests/medidas/L1-01-d.json`. Testes: `tests/unit/test_objetos_raster.py` (30) e
`tests/api/test_garage_inquilino.py`.

## turno 3, setembro de 2026 (itens L0-02-e-varredura-cruzada-rls · L0-02-f-tela-usuarios: fechamento com evidência fresca + gap real corrigido)

Os dois itens já tinham quase todo o mecanismo construído desde a fundação do `L0-02-tenant-auth` (turno 2);
esta passagem mediu de novo com o código de HOJE (outras trilhas do turno adicionaram rotas por baixo desde a
última medição) e fechou o único gap real encontrado.

**L0-02-e (varredura cruzada A→B):** `tests/api/test_cruzado.py::test_cobertura_100_por_cento` rodado agora —
**138 rotas no `docs/openapi.json` vivo, 138 com caso em `tests/api/cruzado_casos.py`** (era 123 na última
medição gravada; o OpenAPI cresceu com LDAP e outros itens de T3, e `cruzado_casos.py` já tinha acompanhado).
Gravado em `tests/medidas/L0-02-e.json` (nome exigido pelo portão) e mantido também em
`tests/medidas/L0-02-tenant-auth.json` (convenção do item-pai, usada por `MANUAL.md`/`ARQUITETURA.md` desde o
turno 2 para o bloco inteiro de identidade e acesso). `tests/api/test_funcoes_seguras.py` (REVOKE EXECUTE de
PUBLIC em toda função SECURITY DEFINER do schema `plat`, `tenant_criar` por GUC forjado levanta
`so_superadmin`) roda dentro da mesma suíte e passou.

**L0-02-f (tela Usuários):** a tela (`web/admin/usuarios.html` + `web/js/auth/usuarios.js`) já tinha TUDO
construído — criar, editar, desabilitar/reabilitar, redefinir senha, desligar 2FA, desbloquear, lote até 100
(mudar perfil/desabilitar/reabilitar), recusa do último admin — mas só um e2e cobria a fatia
criar/editar/senha/lote-desabilitar/último-admin. Escrito `tests/e2e/test_usuarios.py::
test_usuarios_perfil_lote_2fa_desbloquear_apagar_com_grupos_e_401`, cobrindo pela INTERFACE o que faltava:
mudar perfil em massa (3 usuários), desligar 2FA, desbloquear (com bloqueio real de 5 senhas erradas antes),
apagar recusado listando 2 grupos, e o tempo entre desabilitar e o 401 do próprio usuário na próxima
requisição — **medido 73,1 ms** (`desabilitar_para_401_ms`, bem abaixo do 1 s do portão).

**Gap real encontrado e corrigido:** `apagar_usuario` só recusava por grupos possuídos; `plat.item.dono_id` é
FK sem `ON DELETE`, então um usuário com itens do catálogo (mapas, camadas, pastas) na verdade causava um
`409 em_uso` genérico do banco (nome da constraint, nunca os títulos) em vez da recusa nomeada que o portão
pede ("recusa listando os 2"). Adicionado `_itens_do_dono` (mesmo padrão de `_grupos_do_dono`) em
`app/auth/rotas_usuarios.py`, novo erro `409 possui_itens` com a lista de títulos, chave de i18n
`usuarios.possui_itens` e o mesmo tratamento no JS que já existia para `possui_grupos`. Provado por
`tests/api/test_usuarios.py::test_apagar_com_2_itens_do_catalogo_recusa_listando_os_2` (cria 2 itens, recusa
409 listando os 2 títulos, purga os itens pelo mesmo caminho de `tests/api/catalogo/conftest.py::
_expurgar_zt`, confirma que a exclusão passa a funcionar).

`docs/PARIDADE.md` linha "gestão de membros" atualizada (apagar recusa por grupos E itens, não só grupos).
Achado colateral, não deste item: `GET /saude` respondeu 503 durante a varredura porque outra trilha do turno
tinha uma migração (`028_documento_grafo`, depois `029_ingestao_vetor`) pendente de aplicar no banco
compartilhado — não é regressão de L0-02-e/f, é o estado normal de trilhas paralelas no mesmo turno.

**Adversário independente do turno**: PASSA em L0-02-e (43+19 testes filtrados; GUC forjado, cross-tenant e
rota-sem-caso todos bloqueados/reprovados como esperado). Achou um escalonamento de privilégio real em L0-02-f
(não cross-tenant): `POST /api/usuarios` checava admin só por `auth.perfil`, nunca por `membros.papel` — um
segundo admin com papel restrito a `{membros.ver, membros.gerir}` fabricava um admin PLENO. Corrigido nesta
mesma sessão (`criar_usuario` agora exige `membros.papel` para `perfil≠visualizador` ou `papel_id`), com
regressão própria (`test_criar_usuario_com_perfil_ou_papel_exige_membros_papel`) e sem falha nova na suíte
alvo. Pendência nomeada, não bloqueante: `papel_id` atribuído (na criação OU na edição) ainda não checa se o
ATOR possui os privilégios daquele papel — mesmo princípio que `_validar_papel` já aplica na criação de papéis,
ausente na atribuição de um papel já existente; fica para o dono decidir se abre item novo.

## turno 3, setembro de 2026 (item L0-09-metadado-catalogo: metadado ISO 19139 por item + catálogo externo OGC API Records)

`GET /api/itens/{id}/metadado.xml` (`app/catalogo/metadado.py`) gera `gmd:MD_Metadata` (ISO 19139/GMD — o
perfil que o Perfil MGB 2.0/GeoNetwork da INDE consomem) a partir do próprio item (título, resumo/descrição,
palavras-chave, créditos, termos de uso, extensão geográfica, dono como `pointOfContact`, inquilino como
`contact`) e de `dados.procedencia` quando existir (vira `dataQualityInfo`/`lineage`, D17 do L0_CONCEITO); o
servidor VALIDA o XML contra o XSD oficial antes de responder — nunca confia em si mesmo. O XSD (perfil
`schemas.opengis.net/iso/19139/20070417`, 57 arquivos, 796 KB) é baixado uma vez por
`docs/xsd/baixar_iso19139.py`, que reescreve todo `schemaLocation` absoluto para caminho relativo dentro do
próprio cache — depois de rodado, a validação nunca mais toca rede (comitado em `docs/xsd/cache/`, refeito
pelo `install.sh`; prova: a validação passa com o `socket.socket` da máquina bloqueado de propósito).

Catálogo externo por protocolo padrão: **OGC API Records** (OGC 20-004r1) em `/ogc/records`
(`app/catalogo/rotas_ogc.py`) — pouso, `/conformance`, uma coleção (`catalogo`, o catálogo inteiro do
inquilino), `/items` (GeoJSON, filtros `q`/`bbox`/`tipo`/`tags`, paginação cursor, reaproveitando
`listar_ids`/`carregar_varios` de `rotas_itens.py`) e `/items/{id}`, com link para o metadado ISO acima. CSW
fica de fora desta passagem (justificativa no próprio módulo: RAM da máquina no limite, nenhuma biblioteca
CSW instalada, protocolo legado frente à API REST — custo de mudar registrado como médio). As duas rotas
exigem sempre `catalogo:ler` (sessão OU token de serviço do L0-02) — nunca abertas, nem a página de pouso; o
isolamento por inquilino é o MESMO mecanismo de RLS de `plat.item` que `GET /api/itens` já usa (nenhum filtro
novo escrito nas rotas), o que é também a prova mais forte da refutação do item.

9 testes próprios verdes (`tests/api/catalogo/test_metadado_ogc.py`): item completo e item mínimo (só
obrigatórios) validam contra o XSD; item inexistente e de outro inquilino → `404`; token `catalogo:ler` lê o
próprio inquilino e nunca o outro (nem por XML nem pelo registro OGC); as duas rotas OGC recusam chamada sem
autenticação (`401`); coleção e conformidade respondem; o registro do item aponta para o seu próprio
metadado.xml. Sem migração: nada disto precisou de coluna nova em `plat.item` (o bloco `dados.procedencia`
que a exportação usa já é do modelo existente da ADR 0004).

**Pendências nomeadas** (não escondidas): ISO 19115-3 (só 19139 nesta passagem); CSW; e a varredura cruzada
A→B AUTOMÁTICA das duas rotas novas via `docs/openapi.json`/`tests/api/cruzado_casos.py` — este turno tinha
outras trilhas regravando esses dois arquivos ao vivo (concorrência real no mesmo repositório: `app/main.py`
e `app/catalogo/rotas_itens.py` também mudaram por baixo durante a construção, por outro item —
`L0-04-ingestao` e `L5-05-documento-versoes` — sem colisão real de linha graças a `git update-index` cirúrgico
em vez de `git add` cru); regenerar `docs/openapi.json` agora capturaria estado parcial de trilhas alheias,
por isso fica para a integração final do turno. O isolamento por inquilino já está PROVADO pelos 9 testes
próprios; falta só o item na varredura genérica. Ver `docs/PARIDADE.md` e `laco/handoffs/T3/L0-09-metadado.md`.

### Commits

| sha | mensagem |
|---|---|
| (este) | Metadado ISO 19139 por item e catálogo externo OGC API Records (item L0-09-metadado-catalogo) |

## turno 3, setembro de 2026 (item L0-08-d-ldap: LDAP/Active Directory como provedor de login externo)

Módulo isolado `app/auth/ldap.py` (`ldap3` 2.9.1, puro Python, sem dependência de sistema — só a venv):
`POST /api/login/ldap` faz bind de serviço opcional (ou anônimo) contra o diretório do inquilino, busca o
usuário por um filtro sempre ESCAPADO (`escape_filter_chars`, RFC 4515 — a refutação do item pedia
`*)(uid=*`; neutralizado), exige exatamente 1 resultado, faz bind do usuário com a senha informada (nunca
com senha vazia: recusada antes de abrir qualquer conexão) e mapeia `memberOf` para um dos 4 perfis da
plataforma via `plat.provedor_ldap.mapa_grupo_perfil` (maior alcance quando mais de um grupo mapeado bate).
Provisiona o usuário local automaticamente (`plat.ldap_provisionar`, migração `025_provedor_ldap.sql`) sem
nunca gravar a senha do LDAP e sem nunca sobrescrever uma conta `origem='local'` homônima (`409
login_em_uso_local`); depois do bind validado, **reaproveita** `app.auth.rotas_login._abrir_sessao` para
abrir a sessão — zero duplicação da lógica de cookie/política/evento do login local, e
`app/auth/rotas_login.py` não foi tocado (só `app/main.py` ganhou o registro da rota). Administração por
inquilino (privilégio `org.integracoes`, já reservado pela ADR 0002): `GET/PUT /api/org/ldap` (nunca devolve
a senha de bind, só cifrada em repouso — AES-GCM sob `PLAT_SECRET`) e `POST /api/org/ldap/importar` (grupo do
diretório → N usuários locais desabilitados, ativados no primeiro login — a opção do portão). Força bruta
contra o bind: contador em memória por processo, reaproveitando `bloqueio_tentativas`/`bloqueio_minutos` da
política do PRÓPRIO inquilino (cobre também login que ainda não existe localmente).

Servidor de teste: contêiner Docker `glauth` efêmero (imagem 98,9 MB medida; disco/RAM conferidos antes —
12 GiB livres, ~2,5 GiB disponíveis), nunca em produção (`tests/ldap_fixture/`), 4 usuários sintéticos (um
por perfil + um dedicado ao teste de colisão) + 1 conta de serviço + 4 grupos. Decisões e o formato de DN
medido (glauth usa `ou=` no RDN de grupo, não `cn=`) em `docs/adr/0008-ldap-ad.md`.

14 testes em `tests/api/ldap/test_login_ldap.py` (marcados `lento`), todos verdes: bind OK cai no perfil
certo (3 perfis); senha errada recusada; senha vazia nunca tenta bind; injeção de filtro neutralizada; grupo
não mapeado recusa com `403`; colisão com conta local recusa com `409`; **diretório fora do ar não derruba o
login local** (para o contêiner, LDAP responde `503`, login local no mesmo processo responde `200`, religa);
6ª tentativa errada de bind bloqueia como o login local (`423`); importação em massa cria desabilitado e
ativa no primeiro login; admin nunca vê a senha de bind; perfil inválido recusado; teste cruzado A/B
(`org.integracoes` de um inquilino nunca é o de outro); sem privilégio toma `403`. Latência medida:
mediana de 5 logins completos (bind de serviço + busca + bind do usuário + provisionamento + sessão) =
**12,2 ms** (`tests/medidas/L0-08-d-ldap.json`, `mediana_5_logins_ldap_ms`).

A suíte INTEIRA (não só a do item) apontou 3 lacunas que o teste próprio não cobria, todas corrigidas antes do
commit: (1) `CREATE FUNCTION` concede `EXECUTE` a PUBLIC por padrão — as 3 funções novas ganharam `REVOKE
EXECUTE ... FROM PUBLIC` explícito na própria migração, mesmo padrão da 003; (2) `tests/api/eventos_esperados.py`
e `tests/api/cruzado_casos.py` são listas fechadas por rota (o portão P6 do laço, teste cruzado A→B automático
gerado do OpenAPI) — as 3 rotas novas ganharam entrada nas duas.

**Incidente durante a construção (não escondido):** o contador de bloqueio local do superadmin `plataforma`
foi atingido por colisões de código TOTP entre rodadas de teste concorrentes desta sessão contra a MESMA
conta compartilhada por todas as trilhas do turno, e travou `make check-rapido` inteiro (503 erros em cascata
por causa da fixture `sessao_plat`, autouse). Diagnosticado (o segredo TOTP cacheado em
`tests/credenciais_totp.txt` estava desatualizado em relação ao do banco) e corrigido pelo mesmo caminho que
o `install.sh` já documenta (reset do 2FA da conta + remoção do cache; a suíte religou o 2FA sozinha na
rodada seguinte, novo segredo cacheado) — sem editar nenhum teste alheio. `tests/api/ldap/conftest.py`
também passou a sobrescrever a fixture `limpeza_de_residuos` só para o próprio diretório, para os testes de
LDAP nunca mais dependerem de `sessao_plat` (conta mais disputada da árvore).

### Commits

| sha | mensagem |
|---|---|
| (este) | LDAP/Active Directory como provedor de login externo por inquilino (item L0-08-d-ldap) |

## turno 3, setembro de 2026 (item L0-05-e-worker-em-container: worker da fila em contêiner)

Segundo executor da fila de jobs (ADR 0003), em contêiner Docker, ao lado da unidade systemd `plat-worker`
(nunca no lugar dela — os dois podem apontar para o mesmo banco): `deploy/Dockerfile.worker` (python:3.12-slim-
bookworm, sem `--system-site-packages`; ver ADR 0010 seção 2 para por quê), `deploy/docker-compose.worker.yml`
(`network_mode: host` — Postgres/Garage só escutam 127.0.0.1, ADR 0010 seção 3; segredos pelo mesmo arquivo que
o `LoadCredential=` do systemd usa, lidos como root e soltos via `setpriv` antes do worker rodar uma linha) e
`deploy/entrypoint-worker.sh`. `install.sh` ganhou a flag opcional `--worker-container` (seção h4), sem mudar o
comportamento padrão.

Achado ao testar de verdade (não estava previsto no pedido): `app/jobs/filho._pdeathsig()` checava
`os.getppid() == 1` para decidir "o pai morreu" — certo fora de contêiner, **sempre falso dentro de um
contêiner sem `--init`, onde o próprio worker roda como PID 1**: 100% dos jobs falhavam, imediatamente, sem
log nem traceback. Corrigido comparando contra o PID medido ANTES do fork (`worker.py._lancar()` repassa),
correto nos dois ambientes; testado ponta-a-ponta (job real via API concluído na 1ª tentativa pelo contêiner,
antes: falhava as 3 tentativas sempre). `app/jobs/filho.limite_memoria_cgroup_mb()` (novo) lê o teto do cgroup
v2 pelo caminho real do processo (`/proc/self/cgroup`, nunca hardcoded) — serve tanto o `MemoryMax=` da
unidade systemd quanto o `mem_limit=` do contêiner sem distinção de código — e `preparar_ambiente()` nunca
deixa o `RLIMIT_DATA` de um filho passar do teto do cgroup menos uma reserva de 96 MB; testado com
`mem_limit: 300m` (clamp de 256→204 MB, com `AVISO` gravado no `job_log`) e com `2g` (sem clamp, regressão da
produção de hoje coberta). `GET /saude` do worker ganhou o campo `cgroup_memoria_max_mb`.

Achado colateral, documentado mas não corrigido aqui (fora do escopo do item, risco de colisão com duas outras
trilhas editando os mesmos arquivos neste turno): `app/catalogo/tipos.py`/`miniatura.py` importam
`jsonschema`/`Pillow`, nunca declarados em `requirements.txt` nem em `deploy/pacotes_apt.txt` — só funcionam no
host por uma instalação pip global de outro produto da máquina. A imagem do contêiner trava as duas versões
medidas (`jsonschema==4.26.0`, `Pillow==12.2.0`); o conserto do `requirements.txt` do host fica para o item
dono de `app/catalogo`.

9 testes de unidade novos (`tests/unit/test_jobs_filho_cgroup.py`): aritmética pura do clamp + 1 teste ponta-a-
ponta em subprocesso isolado (`resource.setrlimit(RLIMIT_DATA)` só baixa o teto no processo que o chama — dois
testes no mesmo processo do pytest quebrariam o segundo). A unidade systemd `plat-worker` de produção nunca foi
parada nem reiniciada para este item. Detalhe completo: ADR `docs/adr/0010-worker-em-container.md`,
`ARQUITETURA.md` seção 5.8, handoff `laco/handoffs/T3/L0-05-e-worker-container.md`.

## turno 3, setembro de 2026 (item L2-10-c-linguagem-expressao: linguagem de expressão própria — PARCIAL, só o núcleo)

Núcleo da linguagem de expressão própria (equivalente ao Arcade da Esri para os perfis popup, rótulo, cálculo,
restrição, validação, indicador — L2_CONCEITO.md decisão C6): gramática publicada em EBNF (`docs/EXPRESSAO.md`),
analisador recursivo descendente escrito à mão (mesmo padrão de `app/consulta/where_ast.py`, sem
`eval`/`exec`/`compile`), AST tipada exportável/reimportável em JSON, e **dois avaliadores que têm de concordar
byte a byte**: `app/expressao/avaliador_py.py` (Python, servidor) e `web/js/expressao/avaliador.js` (JavaScript
puro, sem `eval`/`new Function`, roda tanto no navegador quanto no Node de teste).

18 funções (texto: `Maiuscula`/`Minuscula`/`Concatenar`/`Texto`; número: `Arredondar`/`Absoluto`/`Minimo`/
`Maximo`/`Numero`/`Potencia`; data — convenção epoch-ms UTC, sem tipo dedicado, para os dois avaliadores não
dependerem de biblioteca de fuso horário nenhuma das duas línguas: `AgoraUTC`/`Ano`/`Mes`/`Dia`/`DiferencaDias`;
nulo: `SeNulo`/`EhNulo`; condicional: `Se`), semântica de nulo de três valores (como SQL), curto-circuito em
`Se`/`SeNulo`/`&&`/`||` (o ramo não escolhido nunca avalia — provado forçando `10 / 0` no ramo descartado).

Dois algoritmos escritos à mão, idênticos nos dois avaliadores (onde Python e JavaScript mais divergem por
padrão): formatação de número → texto (inteiro sem ponto, decimal até 6 casas sem zero à direita) e
arredondamento meio-para-longe-de-zero (nem o `round()` banker's do Python, nem o `Math.round` do JavaScript).

Segurança (refutação do item-pai): texto/tokens/argumentos acima do limite, string de 10 MB, cadeia longa do
mesmo operador (profundidade medida na ÁRVORE inteira, não só na descida do parser — uma cadeia
`1+1+1+...+1` é montada em laço, não recursão, e por isso não disparava o contador de descida do parser
sozinho; achado corrigido nesta mesma passagem), parênteses/unários/chamadas profundamente aninhados, limite
de passos (10⁵) e de tempo (500 ms servidor / 50 ms cliente) sob carga, campo fora da lista branca do
`contexto` (nunca `getattr` de objeto do chamador) — todos com erro nomeado, nunca `RecursionError` nem
travamento. `ast_de_json` (reimportação da AST gravada) ganhou os MESMOS limites de profundidade/aridade que o
texto, depois de identificado que um JSON fabricado à mão contornaria os dois guarda-corpos do lado texto.

Prova de equivalência: 41 vetores (`tests/expressoes/vetores.json`, portão pede ≥ 20) avaliados nos dois
avaliadores e comparados byte a byte (`tests/unit/test_expressao_equivalencia.py`, runner Node
`tests/expressoes/executar_js.mjs`); `docs/EXPRESSAO.md` conferido contra o código dos dois lados
(`tests/unit/test_expressao_doc_sincronizada.py` — toda função e todo código de erro documentado existe no
código, e vice-versa).

**Fora desta passagem** (item grande; fica para quando a integração existir): tipos lista/dicionário/geometria,
`FeatureSetByRelationship`, os ≥ 40 funções e ≥ 200 vetores da hipótese cheia, fuso horário de usuário,
formatação pt-BR, compilação para expressão MapLibre e para SQL, integração com popup/rótulo/formulário/regra
de atributo (`L5-11`), tabela de paridade completa com o Arcade function reference. Ver
`laco/handoffs/T3/L2-10-c-expressao.md`; medidas em `tests/medidas/L2-10-c-expressao.json`.

## turno 3, setembro de 2026 (item L2-11-c-rota-matriz-isocrona: rota, matriz e isócrona — PARCIAL)

Serviço de localização sobre um OSRM isolado de teste: `POST /api/rota` (dois pontos → geometria GeoJSON,
distância, duração, instruções resumidas em português — `app/rede/instrucoes.py`, vocabulário fechado de
`maneuver.type`/`maneuver.modifier` da doc OSRM v5.24), `POST /api/matriz` (N origens × M destinos, teto
N×M configurável por `PLAT_ROTA_MATRIZ_MAX`, padrão 625) e `POST /api/isocrona` (ponto + minutos → polígono
de alcance: grade de pontos ao redor do centro, tempo de cada um por `/table` do OSRM, casco côncavo por
`shapely.concave_hull` sobre os pontos alcançáveis — o OSRM não tem serviço de isócrona nativo, doc
testada só lista route/table/nearest/match/trip/tile). Escopo de token novo `rota:usar`.

Dado: recorte de Guarulhos **isolado, novo, ≤ 50 MB** (`osrm/guarulhos.osm.pbf`, 1,6 MiB, 210.065 nós,
42.720 vias, mesma área do mapa-base `L2-01-a`), construído sem tocar nenhum dos 4 contêineres OSRM já
ativos na máquina para outras frentes (portas 5000-5003) — novo contêiner `plat-osrm-guarulhos` em
**127.0.0.1:5010**, unidade systemd própria (`deploy/plat-osrm-guarulhos.service`, decisão de manter vivo:
memória medida ~40 MB, mesmo padrão dos outros 4). `osmium extract` no `.pbf` regional inteiro (135 MB, 17,5
milhões de nós) **morreu de OOM sob teto próprio três vezes** (RAM disponível ~2,5 GB, swap cheio) sem
afetar o sistema (`ulimit -v` conteve cada tentativa); o caminho que funcionou foi `ogr2ogr` (mesmo padrão
já medido seguro no `L2-01-a`, RSS ~300 MB) extraindo só as vias com `highway=*`, seguido de uma síntese
própria de `.osm` XML (`osrm/gerar_osm_xml.py`, deduplicando nó por coordenada) — proveniência completa em
`osrm/PROVENIENCIA.md`.

**Escopo entregue nesta trilha (ARQUITETO+BACKEND) é MENOR que o item completo do backlog**: pgRouting,
`/mais-proximo`, `/ajuste-de-trajeto` (match), perfis pé/bicicleta, NAServer Esri-compatível
(`solve`/`solveServiceArea`/`solveClosestFacility`), teste de 1.000×1.000, e a validação de 200 pontos
amostrados contra a isócrona de 15/30/45 min **não foram construídos** — ficam para a continuação do item
(ver handoff `laco/handoffs/T3/L2-11-c-rota.md`). Testado com 9 casos em `tests/api/rede/test_rota.py`
(rota real Guarulhos↔GRU, matriz 5×5, teto de matriz, isócrona de 10 min não vazia e conferida contra a
própria API de rota, autenticação, perfil/coordenada inválidos) — todos verdes contra o OSRM real via
`TestClient` (sem tocar o `plat-api` ao vivo, que outras trilhas do turno ainda editavam).

## turno 3, setembro de 2026 (item L2-01-a-basemap-local-pmtiles: mapa-base local em PMTiles)

Primeiro item de mapa real do produto: MapLibre GL JS 4.7.1 (já vendorizado) mais o protocolo `pmtiles-4.5.0.js`
(novo, BSD-3-Clause) lendo um PMTiles local (`web/dados/basemap/guarulhos.pmtiles`, 18,4 MiB, OSM ODbL 1.0,
proveniência em `web/dados/basemap/PROVENIENCIA.md`) servido pelo próprio nginx do appliance por Range HTTP —
sem Martin, sem serviço de tiles dinâmico, sem chave de terceiro. Tela `/mapa`, tela cheia, dentro do sistema de
identidade visual "instrumento" (`class="instrumento"` no `<body>`, cores copiadas da paleta escura de
`web/estilo/tokens.css`): navegação, escala, coordenadas do cursor e seletor de camada base (uma opção hoje).
Detalhe em `MANUAL.md` seção 13; medidas em `tests/medidas/L2-01-a-basemap-local-pmtiles.json`.

**Incidente registrado (não escondido):** a primeira tentativa de extrair o recorte de OSM usou `osmium extract`
(índice de nós inteiro em memória) com RAM disponível já abaixo do guardrail de 4 GB do laço; o processo foi
morto pelo OOM killer do sistema, que na mesma varredura também matou um backend do Postgres, travando o cluster
14 minutos em `deactivating` (mesmo padrão de incidentes anteriores da casa). Remediado com o procedimento já
documentado (`pg_ctlcluster 16 main stop -m immediate --skip-systemctl-redirect`); o banco voltou consistente
(23 migrações aplicadas, nenhuma perdida) em cerca de 40 s e todos os serviços dependentes reconectaram sozinhos.
A extração foi refeita com `ogr2ogr` (streaming, GDAL, pico de RSS medido ~500 MB por chamada), sem repetir o erro.

### Commits

| sha | mensagem |
|---|---|
| (este) | Mapa-base local em PMTiles (item L2-01-a-basemap-local-pmtiles): MapLibre + PMTiles servido pelo nginx, tela `/mapa`, e2e |

## turno 3, setembro de 2026 (itens L7-14-instalacoes-apt-desta-linha · L7-16-assinatura-pacote)

### O que entrou — pacotes apt e assinatura de release (ADR 0007)

- `deploy/pacotes_apt.txt`: lista fechada de 7 pacotes dpkg que o `plat` já exige ou vai exigir em curto prazo
  (`python3-uvicorn`, `python3-psycopg2`, `python3-venv`, `python3-cryptography`, `gdal-bin`, `python3-gdal`,
  `python3-magic`); `install.sh` passo "e2" instala de forma idempotente só o que faltar (`dpkg -s` antes e
  depois do `apt-get install -y`). `tests/unit/test_pacotes_apt.py` confere a lista e a instalação real.
  `postgresql-16-pgrouting`/`pgstac`/FDW de terceiro ficam de fora de propósito (item `L7-14-extensoes-fdw`,
  dono próprio); `ezdxf`/LibreDWG ficam de fora porque a decisão de usá-los (ADR 0005 seção 12.4, D23) ainda
  não foi tomada.
- `scripts/assinar_pacote.sh` + `scripts/verificar_pacote.sh` (com `scripts/plat_assinatura.py`): assinatura e
  verificação Ed25519 de pacote de atualização via `cryptography`. Gera o par de chaves na primeira execução
  (privada fora do repositório, `/etc/plat/chaves/…` ou `$HOME/.config/plat/chaves/…`; pública registrada em
  `deploy/chaves_publicas_release.txt`, versionado no git). Funciona sem rede nos dois lados. Rotação de chave
  com período de dupla chave: a pública nova só é aceita depois de distribuída numa versão assinada com a
  antiga (`tests/unit/test_assinatura_pacote.py` prova a recusa cedo e a aceitação tarde). `gitleaks` não é
  pacote apt nesta distribuição; a cláusula "chave privada nunca no git" foi provada com uma varredura direta
  do histórico (`git log --all -p`) à procura do cabeçalho PEM.

## 0.2.0 — turno 2, setembro de 2026 (itens L0-02-tenant-auth: identidade e acesso · L0-05-jobs: fila de trabalhos)

O produto passa a ter login com senha e segundo fator, sessão, usuários, grupos, papéis, tokens de serviço, log de
acesso e eventos por inquilino, superadmin em inquilino técnico, e uma fila de trabalhos com worker em processo
filho, progresso em tempo real, cancelamento, sobrevivência a reinício, agendas por cron e tela Tarefas. Nota: o
arquivo `VERSAO` ainda diz `0.1.0`; o gerente o sobe para `0.2.0` no fechamento do turno, junto com o `git_sha` de
`/saude` (o serviço no ar é `abbb03d`).

### O que entrou — identidade e acesso (L0-02, ADR 0002, migrações 003 e 009)

- Migração `003_identidade_acesso`: 46 privilégios com teto por perfil, papéis personalizados, colunas novas de
  `usuario` (segundo fator, bloqueio, pendências, origem), histórico de senha, grupos e membros, `evento` e
  `log_acesso` particionados por mês, inquilino técnico `plataforma` com 2FA obrigatório, funções `SECURITY DEFINER`
  reescritas com checagem de inquilino (`contexto_confere`) e superadmin por hash de sessão (`plataforma_operador`),
  `REVOKE EXECUTE FROM PUBLIC` em todas as funções e no privilégio padrão do schema.
- `app/auth/`: política de senha por inquilino (`tenant.config.auth`, padrões e faixas em `app/limites.py`), hash
  fantasma para tempo constante, bloqueio 5/15 min no banco, TOTP de biblioteca padrão com segredo cifrado
  (AES-GCM) e 8 códigos de recuperação, cookie `plat_sessao` com hash no banco e CSRF por `SameSite=Lax` + JSON +
  `Origin`, token de serviço `plat_…` com escopos, restrições de origem e IP, rotação de 24 h e revogação imediata,
  middleware que grava `plat.log_acesso` (bytes contados no fluxo) e redige segredos do journal, `X-Plat-Inquilino`
  só de leitura para o superadmin.
- 54 rotas do ADR mais `DELETE /api/plataforma/inquilinos/{id}` (migração 009: `tenant_apagar`), todas com
  `x-auth`, `x-privilegio`, `response_model` e evento declarado; erros no formato `{erro, mensagem, detalhe, req_id}`
  (`app/erros.py`); páginas em `app/paginas.py`.
- Sete telas sobre uma base reutilizável (`web/js/base/`: api, estado, i18n, dom, 6 componentes, layout;
  `style.css` tema único; DOMPurify 3.4.14 vendorizado com sha256): `/entrar`, `/conta`, `/admin/usuarios`,
  `/admin/grupos`, `/admin/papeis`, `/admin/tokens`, `/admin/log`; barra lateral por privilégio; página inicial com
  atalhos quando há sessão.
- Instalador: `plataforma/admin` semeado com superadmin, `demo`/`demo2` sem; 2FA reiniciado a cada instalação;
  partições de 4 meses; `plat_limites.conf` (10 r/min por IP em `/api/login` e `/api/login/2fa`); `Referrer-Policy`
  em toda `location`; limpeza de resíduos `zt-*` em `dev`; `python3-cryptography` conferido; `qrcode==8.2`.
- Testes: 5 unitários novos, 17 arquivos em `tests/api/` (varredura cruzada A→B gerada do OpenAPI com digest md5
  de todo o dado de B, força bruta, tempo constante, TOTP, token, funções seguras por `psql`, log de acesso por
  `User-Agent` único, eventos e privilégios declarados, inquilino temporário), 9 e2e playwright com captura mais
  `test_i18n_cru.py` (chave de tradução crua na tela reprova).

### O que entrou — fila de trabalhos (L0-05, ADR 0003, migrações 004, 006, 007, 008 e 010)

- Migração `004_jobs`: `job`, `job_log`, `worker`, `agenda`, RLS, gatilhos de estado final e de NOTIFY, funções do
  worker, cotas (`cota_jobs_simultaneos` 2, `cota_jobs_dia` 1.000, `cota_agendas` 50), schema `plat_trabalho`.
- `app/jobs/`: registro de tipos por decorador (`@tarefa`), worker com conexão própria, `LISTEN/NOTIFY`,
  `SKIP LOCKED`, heartbeat, "1 pesado por vez" por advisory lock, processo filho com `PR_SET_PDEATHSIG`,
  `RLIMIT_DATA`, BLAS em 1 thread e códigos de saída por causa, cancelamento cooperativo com escalonamento
  SIGTERM 30 s / SIGKILL +10 s, retentativa 2/4/8 s, teto de 5 reinícios, agendas por cron com fuso (croniter
  6.2.4) e relógio no worker, periódico `jobs.expurgo`, SSE `GET /api/jobs/{id}/eventos` com `Last-Event-ID`, 13
  rotas `/api/jobs*` e `/api/agendas*`, `/saude` com `fila` e `servicos.worker`, 6 tipos de diagnóstico.
- Unidade `plat-worker` (`Restart=always`, `KillMode=mixed`, `OOMPolicy=continue`, `MemoryMax=2G`), passo `h2` do
  instalador, chaves `PLAT_WORKER_*`, `PLAT_JOBS_DIR`, `PLAT_JOB_MAX_REINICIOS`, `PLAT_GPU_*`, `PLAT_DSN_WORKER`.
- Tela `/tarefas` (lista ao vivo por SSE com reserva por consulta, detalhe com log ao vivo, cancelar, repetir,
  baixar log, agendas) sobre a base da identidade; e2e `test_tarefas.py` com 5 provas e 3 capturas.
- Correções por achados do testador, cada uma com teste:
  - `006_jobs_transicoes` (commit `ad2ea29`): a role `plat_app` conseguia por SQL levar um job `pendente → rodando
    → concluido` com resultado forjado. Agora existe a role `plat_worker`, única com `EXECUTE` nas funções que
    mudam estado; `plat_app` perdeu `UPDATE` em `plat.job` (cancela por `job_cancelar`, reporta por
    `job_progresso`); gatilho `job_transicao` exige o GUC `via_worker` que só as funções do worker ligam;
    `jobs_expurgar` apaga marcadores e passos órfãos (1.371 acumulados antes).
  - `008_jobs_tentativa` (commit `90d03c0`): reinício e ceifa desfazem o incremento de `tentativa` feito por
    `job_pegar`; a retomada volta ao mesmo número (tentativa 1, reinícios 1). Testes de agenda robustos a resíduo
    de outras sessões.
  - `010_jobs_gatilhos_execute` (commit `7824846`): as três funções de gatilho da 004 nasceram com `EXECUTE` para
    `PUBLIC` e `plat_app` pelo privilégio padrão da 001; revogado (achado de `test_funcoes_seguras`).
  - `007_jobs_eventos` e integração com a identidade (commit `ffedc05`): `x-auth`/`x-privilegio` nas rotas da
    fila, eventos declarados, casos cruzados das 17 rotas.
  - `012_jobs_identidade_worker` e `013_jobs_execute_reafirma` (commit `9be9c6a`, depois do passe do cronista ter
    começado): identidade do worker por processo e ceifa só por heartbeat; `EXECUTE` do worker reafirmado contra o
    `GRANT ON ALL FUNCTIONS` da 011. Sem veredito do testador e do adversário neste turno.

### Medições (`tests/medidas/L0-02-tenant-auth.json`, gerado às 17:28 UTC sobre `90d03c0`)

| medida | valor | comando |
|---|---|---|
| rotas no OpenAPI / com caso cruzado | 74 / 73 | `len(paths×methods)` de `docs/openapi.json`; casos em `tests/api/cruzado_casos.py` (o 74º caso entrou em `abbb03d`) |
| varredura cruzada viva: rotas, chamadas, 2xx indevidos, linhas de B alteradas | 73, 411, 0, 0 | `varredura_viva.py` do testador contra `/api/openapi.json` vivo, 6 vetores por rota; md5 das linhas de B como `postgres` |
| login (senha certa) | mediana 128,6 ms | 3 `POST /api/login` no TestClient (inclui pbkdf2 600.000) |
| login pela URL pública | 142,9 · 141,7 · 146,0 ms | 3 `POST /api/login` individuais (nginx + TLS) |
| login: 20 chamadas direto no uvicorn | mediana 129,2 · p95 145,4 · máx 156,6 ms | `testador_login_ms_20_uvicorn` |
| tempo constante (inexistente × senha errada) | 122,3 × 123,6 ms (TestClient); 121,7 × 123,2 ms (testador) | mediana de 4 e de 6 `POST /api/login` |
| autenticação por token | 3,0 ms (TestClient); 2,5 ms (testador) | mediana de `GET /api/eu` com Bearer menos `GET /api/versao` |
| custo de gravar `log_acesso` | 0,66 ms | mediana de 30 `GET /api/eu` com e sem `log_registrar` |
| revogação de token até o 401 | 0,01 s (TestClient) · 0,02 s (URL pública) · 6,2 ms (e2e) | `DELETE /api/tokens/{id}` e chamada seguinte |
| limite por IP no nginx | 10 × 401 depois 429 | 25 `POST /api/login` em 15 s de outro IP |
| RLS | 22 de 22 tabelas e partições com `tenant_id` | `pg_class × pg_attribute` |
| funções `SECURITY DEFINER` sem `PUBLIC` | 51 de 60 funções; 0 com `PUBLIC` | `pg_proc × aclexplode` |
| memória do `plat-api` | 122.781.696 bytes | `systemctl show plat-api -p MemoryCurrent` |
| páginas prontas (chromium) | login 54,3 · conta 37,8 · 2FA 9,7 · usuários 59,4 · grupos 60,8 · papéis 58,7 · tokens 78,9 · log 73,7 ms | `goto` até `body[data-pronto=1]` |
| e2e de identidade | 9 aprovados, 0 falhas | `make e2e` 16:03-16:27 UTC |
| marcadores de pendência / nomes de cliente | 0 / 0 | grep com a expressão do driver; grep da lista do testador |

### Medições (`tests/medidas/L0-05-jobs.json`, gerado às 17:28 UTC sobre `90d03c0`)

| medida | valor | comando |
|---|---|---|
| job de 5 min | 300,4 s; 62 eventos `estado`; heartbeat ≤ 5,0 s; latência heartbeat → cliente 0,065 s | `prova.progresso(300 s, 60 passos)` pelo SSE (`test_jobs_progresso.py`) |
| primeiro evento SSE pela URL pública | 0,022 s | `GET https://plat.iagrointel.com/api/jobs/{id}/eventos` até o primeiro `estado` |
| cancelamento cooperativo | 0,426 s (API) · 0,24 s (tela) | `POST .../cancelar` até `estado = cancelado`; clique até `tr[data-estado=cancelado]` |
| cancelamento de tarefa que ignora a flag | 40,5 s | pedido até SIGTERM (30 s) + SIGKILL (10 s) |
| retomada após `systemctl restart plat-worker` | 1,0 s | job volta a `pendente`/`rodando` com `reinicios = 1` (`test_jobs_reinicio.py`) |
| vazão de jobs vazios | 2.135,9 por min (2 workers, 3 processos) | 100 `prova.progresso(duracao_s=0)` (`test_jobs_fila.py`); só a unidade com 1 processo: 1.613,7 por min (`40_testes.md`, seção 6) |
| RSS do processo pai do worker | 40.556 kB | `GET :8153/saude` após o job de memória |
| tela Tarefas pronta | 142,9 ms | `goto('/tarefas')` até `body[data-pronto=1]` |
| linha nova sem recarregar | 10,3 s | `POST /api/jobs` até `tr[data-id]` |
| valores distintos de progresso na linha | 2 | leituras de `.c-progresso .valor` num job de 60 s |

### Vereditos

- **L0-02-tenant-auth: adversário PASSA em 2 rodadas** (`refutacao.json`). Rodada 1, não destrutiva, 16 famílias de
  ataque no serviço vivo: varredura A→B em 40 rotas por id (40 × 404, 0 cross 200), 8 listas sem vazamento, spoof
  por cabeçalho (403), token de B age só como B, 0 função com `PUBLIC`, GUC forjado (`so_superadmin`), força bruta
  (6ª = 423), TOTP e recuperação sem replay, tempo existente × inexistente (delta 2,7 ms em 60 amostras), fixação e
  encerramento de sessão, CSRF (403/415), escalada a superadmin (422/404), token (escopo, revogado, IP, não se
  perpetua), segredos fora do git e do journal, 0 marcador, 0 nome de cliente. Rodada 2, com reinstalação do zero
  (schemas e roles apagados, `install.sh` em 50 s, 63 s fora do ar): invariantes recriados, login real pelo
  navegador, nova varredura cruzada de 34 rotas sem cross 200. Gerente (`99_veredito.md`): todas as 7 cláusulas do
  portão passam; item **parcial** só porque P3 (suíte inteira verde) dependia da trilha B em curso e P9 (esta
  documentação) estava pendente; vira `entregue` no fechamento do turno se a suíte fechar verde.
- **L0-05-jobs: testador com correções 006/008/010 por achados** (`40_testes.md`, em escrita no fim deste passe).
  Cláusulas do portão medidas: job de 5 min com progresso em tempo real, cancelamento, sobrevivência a
  `systemctl restart` e a `kill -9` (nunca `concluido` sem execução inteira: marcador só no último passo; 5 × `kill -9`
  → `falhou`), 1 worker por padrão com limite de RAM declarado, tela Tarefas por inquilino com RLS varrida em 15
  rotas, testes automatizados. **Achado 2 aberto** (acrescentado ao portão em `estado.json`): um worker homônimo
  fora do systemd (nome padrão = host) fez `job_ceifar` devolver os jobs do worker vivo, que foram reexecutados do
  zero; o portão passa a exigir identidade de worker única por processo e ceifa só por heartbeat vencido, com teste
  de dois workers. O adversário do L0-05 ainda não rodou; o item foi devolvido a `pendente` pelo driver às 17:30 UTC
  (sessão do gerente interrompida). A correção entrou no commit `9be9c6a` (17:52 UTC), sem veredito ainda:
  migração `012_jobs_identidade_worker` (identidade `<nome-base>:<pid>`, ceifa só por heartbeat vencido do job e do
  worker dono, assinatura por nome removida; a partida não devolve nada por nome e um `kill -9` no pai é recolhido
  pela ceifa em até cerca de 90 s; `worker.py`, `test_jobs_identidade.py` com dois workers do mesmo nome-base) e
  `013_jobs_execute_reafirma`, motivada por outra regressão achada depois da reinstalação destrutiva: a
  `011_catalogo` (em construção) faz `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app` e devolvia a
  `plat_app` as funções do worker, inclusive `via_worker_ligar`, desfazendo a 006. Testador e adversário ainda não
  conferiram a correção; até lá o estado do item é o descrito acima.
- Ressalvas registradas: `auth_login`, `auth_sessao` e `auth_token` são pré-contexto por chave-segredo (o portão as
  cita como "checam o inquilino"; a checagem acontece na função seguinte, `auth_sessao_criar`); "expiração
  configurável" é por `tenant.config.auth`, não por `.env`; `X-Forwarded-For` só é confiável atrás do nginx
  (herdado ao L7-03); job devolvido 5 vezes mostra "tentativa 0"; com 1 processo a fila é serial e sem justiça
  entre inquilinos.

### Commits do turno

| sha | mensagem |
|---|---|
| `0985a11` | ADR 0002: identidade e acesso (T2, trilha A) |
| `1540c84` | ADR 0003: fila de jobs (T2, trilha B) |
| `1668d76` | Tela Tarefas (L0-05-jobs, trilha B, frontend): lista ao vivo por SSE, detalhe com log, agendas e e2e |
| `cab32da` | Fila de jobs (L0-05, trilha B): migração 004, registro de tipos, worker plat-worker, agendas e tipos de diagnóstico |
| `52d7a3b` | API da fila (L0-05): /api/jobs, /api/agendas, eventos SSE, páginas /tarefas, /saude com fila, testes de API |
| `674798d` | Unidade plat-worker e instalador (L0-05): passo h2, chaves PLAT_WORKER_* no .env, conferência de worker vivo |
| `57c24a5` | ADR 0004: catálogo de conteúdo (T2, preparação do L0-03) |
| `431ba0c` | Instalador (L0-05): inquilinos de demonstração com cota_jobs_dia = 100000 |
| `6a00645` | Base do front (L0-02-tenant-auth, trilha A): tema único, módulos ES de base, componentes, layout, i18n e DOMPurify |
| `50d587d` | Telas de identidade (L0-02-tenant-auth, trilha A, frontend): entrar, minha conta, usuários, grupos, papéis, tokens, log |
| `757f0d3` | e2e do L0-02-tenant-auth (playwright, chromium): login, 2FA, conta, usuários, grupos, papéis, tokens, log |
| `9be4a04` | Identidade (L0-02, trilha A, 1/4): migração 003, política, TOTP, escopos, redação, contrato de erro, limites |
| `2ffe8b4` | Identidade (L0-02, trilha A, 2/4): sessão, token, middleware de log_acesso, 54 rotas do ADR 0002, páginas |
| `b5c336b` | Instalador (L0-02): admin de plataforma com superadmin, demos sem, limite por IP nos logins, partições, cryptography |
| `ae6ec45` | Testes do portão L0-02: varredura cruzada A→B gerada do OpenAPI, força bruta, token, funções seguras, log_acesso |
| `441069c` | ADR 0005: ingestão vetorial (T2, preparação do L0-04) |
| `38430b2` | Medidas do item L0-02-tenant-auth (backend) |
| `ad2ea29` | Correção T2 da fila (L0-05, achados do testador): transições de estado só pelo worker; expurgo de marcadores |
| `ffedc05` | Integração T2 da fila com a identidade (L0-05 × L0-02): x-auth/x-privilegio, eventos e casos cruzados |
| `12b2c2e` | Medidas do testador para L0-02-tenant-auth (T2, 40) |
| `90d03c0` | Fila (L0-05): reinício não consome tentativa (008) e testes de agenda robustos a outras sessões |
| `7c62831` | Correção T2 do front (L0-02): componentes re-traduzem quando o dicionário chega; chaves conta.apos_pendencia e nav.tarefas_desc; e2e contra chave crua |
| `7824846` | Fila (L0-05): funções de gatilho da 004 sem EXECUTE para PUBLIC e plat_app (010) |
| `abbb03d` | Correção T2 do L0-02 (achados do testador): apagar inquilino, fixtures sem resíduo, log por chamada, Referrer-Policy em toda location |
| `41c1dd9`, `a06ca71` | Tela Conteúdo e e2e do L0-03-catalogo (outra trilha, em curso; documentada no passe do cronista desse item) |
| `7cd0327` | Documentação do turno 2 (cronista): MANUAL, ARQUITETURA, CHANGELOG 0.2.0, PARIDADE, README |
| `9be9c6a` | Correção T2 (2) da fila (L0-05, achado do testador): identidade do worker por processo e ceifa só por heartbeat (012, 013) |
| (este) | Documentação do turno 2, passe 2: absorve 012/013 e o commit 9be9c6a |

## 0.1.0 — turno 1, setembro de 2026 (item L0-01-repo: fundação)

Primeira versão. O repositório instala, sobe um serviço, responde saúde por HTTPS e isola inquilinos no
banco. Não há login, catálogo, camada nem mapa.

### O que entrou

- API FastAPI `plat-api` em 127.0.0.1:8150 (2 workers uvicorn, `MemoryMax=1G`), com `GET/HEAD /saude`
  (200 só com banco atualizado; 503 em `desatualizado`/`erro`), `GET/HEAD /api/versao`, página inicial
  `/` e `/api/docs`.
- nginx em `https://plat.iagrointel.com` com `X-Robots-Tag: noindex, nofollow` e
  `Strict-Transport-Security` em toda `location`, `/static/` servido do disco com `no-store`,
  redirecionamento de HTTP para HTTPS.
- Schema `plat` no banco `iagro_sat`: role `plat_app` (sem BYPASSRLS, sem posse), tabelas
  `versao_migracao`, `tenant`, `usuario`, `sessao`, `token_servico`, `log_acesso`; RLS em toda tabela com
  `tenant_id` (USING e WITH CHECK); 9 funções `SECURITY DEFINER` para autenticação, sessão, token e log;
  inquilinos de demonstração `demo` e `demo2`.
- Migrações `001_fundacao` e `002_identidade`, aplicadas por `db/migrar.sh` com sha256 por arquivo,
  uma transação por arquivo e recusa (código 3) de arquivo aplicado que tenha mudado.
- `install.sh` idempotente (extensões, migrações, `.env` 600 com senha da role e `PLAT_GIT_SHA`, linha
  no `pg_hba.conf`, venv com `PYTHONNOUSERSITE=1` e prova de importação sem o diretório do usuário,
  administradores de demonstração com senha por stdin, unidade systemd, nginx com troca atômica
  preservando certbot, certbot na primeira vez, conferência pública de 200 + noindex + HSTS).
- `requirements.txt` com toda dependência da aplicação e da suíte fixada com `==` (`fastapi 0.138.0`,
  `starlette 1.3.1`, `pydantic 2.13.4`, `python-dotenv 1.2.2`, `httpx 0.28.1`, ...); `uvicorn` e
  `psycopg2` do sistema, conferidos por nome de pacote dpkg.
- `make check`: ruff, varredura de marcador de pendência (inclui os `.md`), 81 testes rápidos (unit,
  instalador, dependências, vendor, contrato de `/saude`, `/api/docs`, banco, migrações, RLS, cabeçalhos
  HTTP reais) e 1 e2e playwright com captura; `make medidas` e `make vendor`.
- Front mínimo em módulos ES sem bundler; MapLibre GL JS 4.7.1 (ainda não carregado por nenhuma tela) e
  Swagger UI 5.32.15 (serve `/api/docs` sem CDN) em `web/vendor/`, versão no nome, sha256 e licença em
  `VERSOES.txt`; `favicon.svg`.
- Documentos: `docs/adr/0001-fundacao.md` (13 seções), `docs/openapi.json` gerado e comitado,
  `ARQUITETURA.md`, `MANUAL.md`, este arquivo, `README.md`; `docs/PARIDADE.md` só com cabeçalho (nenhuma
  capacidade de usuário para comparar ainda).

### Medições (`tests/medidas/L0-01-repo.json`, rodada 2 do testador sobre `8ffe950`, commit `3083366`; instalação e RLS da rodada 1)

| medida | valor | comando |
|---|---|---|
| instalação do zero (schema e role apagados) | 6,24 s | `/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150` (rodada 1) |
| reinstalação do zero pelo adversário sobre `8ffe950` | 9,66 s | `refutacao.json`, rodada 2, ataque 1 |
| instalação com `.env`, credenciais e linha do pg_hba também apagados | 9,14 s | idem; o script imprimiu `.env criado`, `linha acrescentada`, `tests/credenciais.txt criado` |
| instalação repetida em seguida | 4,69 s | idem; 0 migrações novas, 1 linha no pg_hba, NRestarts=0 |
| testes coletados / rápidos passando / e2e passando | 82 / 81 / 1 | `venv/bin/pytest --collect-only -q` (unit 31, api 50, e2e 1); `make check` |
| `make check` | rc=0, 2,86 s | `/usr/bin/time -f %e make check` |
| árvore suja depois de `make check` | 0 arquivos | `git status --short` |
| marcadores de pendência no código e nos documentos | 0 linhas | grep com a expressão do driver em `app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md` |
| nomes de cliente/parceiro no repositório | 0 linhas | `grep -rniE` com a lista do testador, fora de venv/.git/vendor |
| `/saude` pela URL pública | HTTP 200, `git_sha` = HEAD `8ffe950516f5`, 2 migrações, 0 pendentes | `curl -sSI` e `curl -sS https://plat.iagrointel.com/saude` |
| `X-Robots-Tag` com noindex | 11 de 11 rotas | `curl -sI` em API, estático, docs e 404 |
| `Strict-Transport-Security` | 11 de 11 rotas HTTPS; ausente no 301 de http | `curl -sI` |
| `/api/docs` sem URL externa; `make vendor` | 0 URLs; 4 arquivos OK | leitura do HTML; `sha256sum -c` |
| latência `/saude` pública, conexão nova (mediana / p95) | 19,8 / 21,0 ms | 20 × `curl -s -o /dev/null -w %{time_total}` |
| latência `/saude` pública, conexão reaproveitada (mediana / p95) | 1,9 / 2,8 ms | 20 URLs numa invocação de curl |
| memória do serviço (cgroup) | 88,5 MB | `systemctl show plat-api -p MemoryCurrent` |
| tabelas com `tenant_id` e RLS | 4 (mais `tenant` por `id`) | `pg_class × pg_attribute` |
| linhas visíveis a `plat_app` sem contexto | 0 | `psql` como `plat_app` sem `set_config` |
| página pronta / primeira pintura (chromium) | 62,6 / 48 ms | e2e `tests/e2e/test_saude_pagina.py` |

### Adversário (`laco/handoffs/T1/refutacao.json`): veredito final PASSA (rodada 2, HEAD `8ffe950`)

Rodada 1 (sobre `3b53c24`): PARCIAL. A refutação literal resistiu (apagar schema e role, reinstalar em
6,46 s, `/saude` 200 com noindex, 58 testes verdes), mas caíram: dependências `fastapi`, `starlette`,
`pydantic`, `python-dotenv` fora do `requirements.txt` (máquina nova não subia); senha de demonstração
em argumento de `sudo` (ficava no journal); documentos de topo vazios; sem `Strict-Transport-Security`;
Swagger de CDN externo; promessas do ADR sem código.

Rodada 2 (sobre `8ffe950`): PASSA. Reinstalação do zero em 9,66 s, 82 testes verdes, `/saude` 200 com
noindex e HSTS; os quatro achados reatacados e fechados com reprodução: aplicação importa e roda sem o
diretório do usuário (`PYTHONNOUSERSITE=1` na unidade viva); 0 senha no journal durante e depois da
reinstalação; ADR e código batem (`make medidas`, vendor com versão no nome, `PLAT_GIT_SHA` gravado,
`requirements.txt` completo, gravação em `log_acesso` adiada explicitamente ao L0-02); HSTS só no bloco
443 e `/api/docs` com 0 requisição externa em chromium real. Ressalvas que não derrubam o item: prova de
"máquina nova" por simulação; funções `SECURITY DEFINER` sem checagem de inquilino (regra para o L0-02);
caminhos do `install.sh` só lidos (`.env` inexistente, certbot emitindo, `nginx -t` reprovando).

### Commits

| sha | mensagem |
|---|---|
| `a1d0c20` | Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0) |
| `904a849` | Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes |
| `b22761e` | Medidas do item L0-01-repo regeneradas sobre o commit 904a849 |
| `ca61ea1` | Medidas do item L0-01-repo assinadas pelo testador (turno T1) |
| `3b53c24` | P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1 |
| `7092755` | Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0 |
| `8ffe950` | L0-01 correção (T1): dependências fixadas sem ~/.local, senha por stdin, HSTS, Swagger local, make medidas, PLAT_GIT_SHA |
| `3083366` | Medidas do item L0-01-repo, rodada 2 do testador sobre 8ffe950 |
| (este) | Documentação atualizada sobre 8ffe950 e 3083366 (passe curto do cronista) |
