# Changelog

Uma entrada por turno do laço PLATAFORMA ENTERPRISE. Números só de `tests/medidas/<item>.json` (com o comando que
os gerou) ou dos vereditos do adversário em `laco/handoffs/T<n>/<item>/refutacao.json`.

## turno 3, setembro de 2026 (item L0-02-g-checagem-privilegio-papel-id: quem concede papel tem de ter o papel)

Fecha um escalonamento de privilégio real na tela de usuários. O papel personalizado RESTRINGE o teto do perfil
(`plat.privilegios_de` é a interseção entre os dois), mas `POST /api/usuarios` e `PUT /api/usuarios/{id}`
conferiam apenas se o papel CABIA no perfil do alvo, nunca se o ATOR tinha o que estava concedendo. Um
administrador restrito por papel podia atribuir a outro um papel mais amplo que o seu, ou zerar o `papel_id` de
alguém — inclusive o próprio — e recuperar o teto inteiro do perfil, ou ainda promover um editor a administrador
sem papel, e fazer qualquer um dos três em massa pelo lote. `_nao_conceder_alem_do_proprio` (ADR 0016) recusa
com 403 `privilegio_proprio_insuficiente` e devolve no `detalhe` a lista do que sobraria. Vale para perfil e
papel juntos, porque promover a admin com papel nulo concede exatamente o mesmo conjunto.

A refutação exigida foi rodada na forma completa, não em um caso: para **cada um dos 47 privilégios** do
vocabulário, o papel do ator passa a ser "todos menos ele" e o papel oferecido passa a ser "todos" — um
privilégio a mais. **94 chamadas (POST e PUT), 94 respostas 403, nenhuma 2xx**; 92 pela conferência nova
(`privilegio_proprio_insuficiente`) e 2 pelo portão de privilégio (`sem_privilegio`), que são exatamente os
casos em que o privilégio retirado do ator era `membros.gerir` ou `membros.papel`. Retirando as duas chamadas
da conferência, 7 dos 10 testes do arquivo reprovam — a prova de que mordem.

Varredura de privilégio rota por rota, em duas camadas, sobre as **138 rotas** de `docs/openapi.json`. A
estática lê o fecho da dependência `autenticado(...)` de cada rota viva e compara com o declarado: **41 rotas**
cobram na dependência exatamente o privilégio nomeado que declaram, **72** declaram valor especial ou
alternativa e cobram no corpo, **8** cobram na dependência um privilégio que a declaração não menciona. A
dinâmica prova as 41 com chamada real: um administrador de inquilino descartável recebe um papel com todos os
privilégios menos um e **as 41 rotas respondem 403 `sem_privilegio` com `exigido` igual ao declarado**; com o
papel completo, nenhuma delas responde `sem_privilegio` (controle positivo). Fronteira declarada: **31 rotas**
de privilégio alternativo cobrado depois de carregar o recurso ficam fora do alcance deste item — a medida
`rotas_alternativas_nao_provadas` guarda o número, e as duas de `/api/usuarios` que o item alcança foram
provadas.

As 8 rotas de declaração incompleta (`/api/tokens/{id}` e `/renovar` cobrando `tokens.gerar` sem declarar,
`/api/acervo/{fonte_id}/adicionar` cobrando `conteudo.criar` numa declaração que promete alternativa,
`/api/itens/{id}/miniatura/gerar` e `/api/lixeira/esvaziar` cobrando `jobs.executar`, e `POST /api/logout` sem
dependência) **apertam** o acesso em vez de afrouxá-lo: exigem mais do que a documentação promete, então não são
falha de segurança, e sim documentação errada. O conserto é do dono de cada rota. A lista está CONGELADA em
`DIVERGENCIAS_CONHECIDAS` no teste: divergência nova reprova.

De quebra, um defeito que impedia a homologação inteira: `CursorSchemaAmbiente` não sobrescrevia `executemany`,
então o INSERT em lote de `plat.papel_privilegio` ia ao servidor com o literal `plat.` e todo ambiente fora do
schema de produção respondia 403 "operação fora do inquilino da sessão" nas rotas de papel. Corrigido junto com
`mogrify`, com guarda em `tests/unit/test_schema_ambiente_metodos.py` que varre `app/` atrás de método de cursor
usado sem sobrescrita. O cursor de `conexao_plat_app` passou a ser o mesmo, senão nenhum teste que escreve
`plat.` na mão roda fora de produção.

## turno 3, setembro de 2026 (item L1-01-b-validacao-e-isolamento-da-entrada: validação de raster)

Abre a linha L1 (imagens) com o portão que fica ANTES de qualquer conversão: `app/raster/validacao.py` (ADR
0015) roda toda a inspeção do arquivo do cliente em **subprocesso separado**, com `RLIMIT_AS` 768 MB,
`RLIMIT_CPU` 60 s, `RLIMIT_NOFILE` 64, `RLIMIT_CORE` 0, relógio de parede de 90 s (SIGKILL no grupo de
processos) e ambiente GDAL sem leitura de diretório (`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`), sem
`/vsicurl` (nenhuma extensão permitida ao driver HTTP), sem `.aux.xml`, sem `VRTRawRasterBand` e sem função
de pixel. O processo pai **nunca importa rasterio para olhar o arquivo do cliente**: só lê os 64 primeiros
bytes e confere a ASSINATURA de formato contra a extensão declarada (um PNG renomeado para `.tif` é recusado
sem sequer abrir subprocesso). Qualquer morte do filho — memória, CPU, relógio, sinal, saída sem JSON — vira
relatório `recusado` com a causa em português, nunca exceção subindo pela fila.

Três estados no mesmo relatório JSON, gravado inteiro no resultado do job `raster.validar`
(`app/raster/tarefas.py`): `recusado` (defeito do arquivo, mensagem exata), **`pendente`** (falta o que só o
usuário sabe — CRS, NoData, data de aquisição, escala para reduzir 16 bits a 8 no perfil visual: a
plataforma PERGUNTA e grava a resposta em `respostas`, **nunca assume um CRS**) e `aceito` (avisos não
impedem: CRS sem EPSG resolvível é aceito com o WKT2 inteiro gravado; extensão fora do Brasil vira aviso).
O tamanho descompactado é estimado pelo CABEÇALHO (`largura × altura × bandas × itemsize`) e comparado com a
cota do inquilino antes de ler um pixel; no zip só o diretório central é lido antes de decidir (nº de
entradas, soma declarada contra a cota, razão declarado/comprimido ≥ 50× = recusa, nome de caminho, link
simbólico, zip aninhado) e **nada é extraído antes de aprovado**.

Medido (`tests/medidas/L1-01-b.json`, 33 casos com arquivo sintético gerado em `tmp_path`, 31 deles com
subprocesso): tempo do subprocesso mediana **0,294 s**, máximo 0,406 s fora do caso que prova o relógio;
pico de RSS do subprocesso entre **87,1 MB e 130,4 MB**, ou seja 17 % do `RLIMIT_AS` declarado.
Um BigTIFF esparso de **320.000 × 320.000** (95,4 GB descompactados estimados, **menos de 200 kB em disco**)
é recusado em 0,3 s sem derrubar o pai; um TIFF fabricado à mão de 400.000 × 400.000 (menos de 1 kB) idem.
Os três casos de invenção do adversário estão na suíte e passam: TIFF com IFD circular (o laço não trava —
o relatório sai em menos de 10 s), JP2 truncado pela metade (recusado ao ler a janela de prova) e GeoTIFF
declarando **65.535 bandas** (recusado, RSS abaixo do limite). Provas de isolamento: filho que tenta alocar
2 GB morre e o pai devolve `morte=memoria`; filho em laço infinito é morto por relógio em 2,01 s com
`codigo_saida=-9`.

Fora deste turno de propósito: o e2e do job `raster.validar` (fila real) — a trilha rodou em worktree e não
sobe worker que dispute a fila de produção; o registro do tipo é provado por teste de unidade.

### conserto do laudo do adversário (mesmo turno)

Um adversário independente REFUTOU a primeira versão com 9 achados (`laco/handoffs/T3/L1-01-b-ADVERSARIO.md`,
23 casos em `tests/unit/test_raster_validacao_adversario.py`, 9 deles `xfail(strict=True)`). Os 9 foram
consertados e os 23 casos passam, sem nenhum ser apagado ou afrouxado — o texto de cada achado ficou como
comentário em cima do teste que o registrou. O que mudou:

* **A rede fecha no processo, não por variável.** O filho recebe um filtro **seccomp** (BPF clássico montado
  com `ctypes` sobre a libc; nenhuma dependência nova) que faz `socket(AF_INET/AF_INET6)` devolver
  `EAFNOSUPPORT`, com `PR_SET_NO_NEW_PRIVS` para sobreviver ao `execve`. Antes, `CPL_VSIL_CURL_ALLOWED_
  EXTENSIONS` aceitava qualquer extensão que o remetente escrevesse na URL e o `http://` direto nem passava
  por ela: o adversário recebeu `HEAD /x.nenhuma-extensao-permitida` e `GET /y.tif` num ouvinte em
  127.0.0.1. Medido depois do conserto, com o mesmo ouvinte e quatro caminhos de ataque (`/vsicurl` e
  `http://`, direto e por VRT aninhado): **0 pedido recebido**. Provado também com a camada de conferência
  DESLIGADA (chamando o GDAL direto no filho): 0 pedido, e `socket()` cru devolve erro. O filho MEDE o
  próprio isolamento em `/proc/self/status` e grava `info.isolamento` (`seccomp: 2`, `no_new_privs: 1`) no
  relatório. Namespace de rede foi testado e recusado: funciona, mas o kernel desta máquina não deixa
  escrever `uid_map`, e o filho passaria a valer como `nobody` para permissão de arquivo.
* **VRT conferido RECURSIVAMENTE.** Toda `SourceFilename` é resolvida com `os.path.realpath` (desfaz `..` e
  **ligação simbólica**) e tem de cair dentro do diretório do envio; VRT que aponta para VRT é conferido até
  5 níveis, com referência circular recusada. O XML é lido INTEIRO até 16 MiB — o corte de 1 MiB escondia
  uma segunda banda atrás de um comentário grande. Fechou os achados 1, 2 e 3 (leitura de arquivo de fora do
  envio por três caminhos).
* **`NaN` não derruba mais a gravação.** NoData `NaN` (comum em float32) virava `NaN` no JSON, que o `jsonb`
  do Postgres recusa: o relatório não chegava a ser gravado no job. Agora `NaN`/`±Infinity` viram o texto
  declarado `"NaN"`/`"Infinity"`/`"-Infinity"` na única saída do relatório, e há teste que **atravessa o
  `jsonb` de verdade** (`psycopg2.extras.Json` → `SELECT %s::jsonb`) com a role da aplicação.
* **Teto de VOLUME no zip**, além da razão de 50× e da cota: `min(cota, 8 × tamanho do envio + 8 MiB)`. Antes,
  um envio de 1,4 MB escrevia 60 MB no diretório de trabalho (42× o enviado) sem violar regra nenhuma.
* **Coordenada impossível vira PERGUNTA.** Latitude de 7.400.000° (resposta de CRS errada num arquivo em
  metros) saía como aviso e o arquivo era aceito; agora é pendência de `crs`, com a sugestão de UTM.
  "Fora do Brasil" continua aviso.
* **Nenhum defeito do arquivo sai como traceback.** `rasterio._err.CPLE_AppDefinedError` não é
  `RasterioError` nem `ValueError` e escapava do `except`, devolvendo ao usuário a última linha do traceback
  em inglês. Três redes novas (por operação, no `_inspecionar` inteiro e no `main` do filho) e um
  `_sem_caminho()` que tira caminho absoluto do servidor de toda mensagem vinda do GDAL/SO.
* **Zip legítimo de 200 rasters volta a ser aceito.** O código abria todos os arquivos ao mesmo tempo e
  batia no `RLIMIT_NOFILE=64` a partir de ~55 arquivos, recusando envio válido com `Too many open files` e o
  caminho do servidor na mensagem. Agora abre **um de cada vez** (cabeçalho numa passagem, janela de prova
  noutra) e o teto subiu para 256 como folga.
* **`complex64`/`int64` declarados.** Continuam aceitos (o arquivo está íntegro), mas o relatório passa a
  trazer `info.tipo_convertivel: false`: nenhum COG ou tile serve esses tipos, e a recusa é da conversão.

Suíte dos dois arquivos juntos: **55 passed** (32 do construtor, 23 do adversário), `ruff` limpo,
`make sem-marcador` limpo.

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
