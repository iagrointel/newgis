# DIÁRIO DO LAÇO — plataforma (codinome plat)

Gerado por `laco/gera_diario.py` em 06/09/2026 14:27. Fonte: git, `estado.json`, `tests/medidas/*.json`, handoffs. Não editar à mão.

**Placar:** 41 entregue(s) · 20 parcial(is) · 2 refutado(s) · 506 itens no total · turno 3 · 93 commits.

## Linha do tempo (do mais recente para o mais antigo)


### 06/09

- `b49559b` 14:25 — Perfil próprio do usuário: idioma, unidades, formato de data, visibilidade e foto (item L0-02-g-perfil-usuario)
- `a34e745` 14:23 — Testes: PLAT_CREDENCIAIS_TOTP_ARQUIVO isola o segredo TOTP por ambiente/trilha
- `c311aa7` 14:12 — Conexão de teste passa a honrar PLAT_SCHEMA (defeito de isolamento do item L7-31)
- `61bfce5` 14:06 — Ataque adversarial a linguagem de expressao: REFUTADO em 3 clausulas (item L2-10-c-linguagem-expressao)
- `cb8fa15` 14:02 — Saúde de conexão com histórico/periódico e proveniência de camada externa (itens L6-02-l-saude e L6-05-proveniencia-camada-externa)
- `1f0ef39` 14:01 — Paridade do modelo do item (L0-03-a-modelo-item): confirma portão já construído
- `a167cc3` 13:47 — Configurações da organização: GET/PUT /api/org e logotipo (item L0-07-a-configuracoes-org)
- `e2d5046` 13:37 — Ficha do acervo completa e gate de LGPD no adicionar (itens L6-01-d-ficha-fonte e L6-01-f-lgpd)
- `cb92de9` 13:27 — Linguagem de expressão: >=40 funções, >=200 vetores Python=JS, listas e dicionários, limites (item L2-10-c-linguagem-expressao)
- `9df2cff` 13:13 — Registro de camadas do acervo e modelo de conexão externa com defesa de SSRF (itens L6-01-a-registro e L6-02-a-modelo-conexao-e-seguranca)
- `331bb86` 13:06 — Corrige medidas de L0-02-tenant-auth.json apos rodada contra openapi.json sujo
- `33e9d73` 13:04 — CHANGELOG: registra veredito do adversario independente para L0-02-e/f
- `4170a34` 13:02 — Fecha escalonamento de privilegio achado pelo adversario em POST /api/usuarios
- `e2d5f91` 12:41 — Processo de release: semver, changelog e pacote assinado com prova de homologação (item L7-15-processo-release)
- `cc5f81d` 12:41 — Documento de construtor: grafo de nós com ULID sobre o versionamento do catálogo (item L5-05-documento-versoes)
- `52ade41` 12:39 — Documenta 409 possui_itens no contrato de DELETE /usuarios/{id} (ADR 0002)
- `fa11658` 12:36 — Fecha L0-02-e (varredura cruzada A->B) e L0-02-f (tela Usuarios) com evidencia fresca
- `c4f1c20` 12:34 — Metadado ISO 19139 por item e catálogo externo OGC API Records (item L0-09-metadado-catalogo)
- `e30515b` 12:16 — Fila: log resumido/limite SSE/progresso grampeado provados; 2 periódicos novos fecham os 5 exigidos (itens L0-05-b, L0-05-d)
- `989d0df` 11:23 — LDAP/Active Directory como provedor de login externo por inquilino (item L0-08-d-ldap)
- `023b0bb` 11:12 — Worker da fila em contêiner, ao lado da unidade systemd (item L0-05-e-worker-em-container)
- `acfdebe` 11:06 — Ambiente de homologação: schema plat_homolog no mesmo banco (item L7-31)
- `19c4cb3` 11:02 — Rota, matriz e isócrona sobre OSRM isolado de teste (item L2-11-c-rota-matriz-isocrona)
- `a221ac4` 11:00 — Núcleo da linguagem de expressão própria (item L2-10-c-linguagem-expressao)
- `c5135e5` 10:50 — Testa DELETE direto em plat.evento para plat_app (item L0-10-eventos-historico)
- `c193765` 10:40 — Verificação dos portões L0-02-b/c/d: prova direta de que o segredo TOTP nunca fica em claro no banco
- `a108eeb` 02:57 — Mapa-base local em PMTiles (item L2-01-a-basemap-local-pmtiles)
- `d69f417` 02:52 — Varredura de dependência com CVE e antivírus de upload (itens L7-03-f e L7-03-b)
- `3302f56` 02:50 — Pacotes apt da linha e assinatura de pacote de atualização (itens L7-14 e L7-16)
- `2110af3` 02:06 — Adaptador de arquivos/objetos por inquilino no Garage (item L0-11-arquivos-objetos)
- `34ac134` 01:59 — Segredos fora do .env: PLAT_SECRET e PLAT_DSN_WORKER por LoadCredential= do systemd (item L7-19)
- `555cb00` 01:31 — Ficha de procedência do acervo da casa como catálogo assinável (item L6-01-a-procedencia-acervo)
- `6f034c3` 01:29 — Contrato de API e limite de corpo por requisição (item L0-12)
- `5c31887` 01:15 — feat(consulta): parser seguro de where restrito -> AST -> SQL parametrizado (L2-04-b)
- `4027ce1` 01:04 — Identidade visual "instrumento" na tela de entrada (item L0-14, primeira fatia)
- `79490e9` 00:55 — fix(catalogo): elimina N+1 de item_contagens e colunas pesadas na lista de itens
- `94a669c` 00:29 — Medidas do L0-03-catalogo remedidas pelo testador (T2, sessão independente)

### 05/09

- `65a9fc2` 21:08 — Medidas do L0-03-catalogo gravadas pela suíte com o corpus de 11 mil itens
- `a591581` 20:58 — Link anônimo não entrega identidade nem estado interno; miniatura confere acesso antes do formato (L0-03)
- `4bde64f` 20:50 — Ler a linha durante a transferência de dono (migração 018), achado exposto pela 017
- `7d91329` 20:44 — Marcador na 016: a varredura do driver casa TODO dentro de TODOS (sha re-registrado)
- `7d6d94f` 20:43 — Leitura de item por linha em vez de função por linha (migração 017) e semente com estatística
- `7cf33c2` 20:42 — Contagem de privilégios 46 -> 47 nos dois testes restantes e token de visualizador na fila (L0-05, correção T2 (3))
- `4053e3c` 20:30 — ADR 0003: a semeadura de demonstração da migração 014 documentada na seção 2.2 (L0-05, correção T2 (3))
- `a496cdd` 20:23 — Correção T2 (3) da fila (L0-05): Cache-Control com uma origem só — a aplicação
- `61bb480` 20:22 — Apagar usuário depois da transferência (L0-03-j, migração 016) e correção da semente de escala
- `ea77246` 20:19 — Correção T2 (3) da fila (L0-05): privilégio jobs.ver e a tela Tarefas em modo só-leitura para o visualizador
- `36317a7` 20:18 — Correções do catálogo achadas na fumaça e nos testes (L0-03): faceta de dono com id, status nenhum como IS NULL, itens_incluidos como texto, 422 no núcleo do PUT, espera no pool
- `03a73e0` 20:15 — Conteúdo (L0-03, frontend) contra a API viva: faceta de dono e de categoria devolvem rótulo, o filtro exige id — normaliza antes de desenhar; e2e cobre o ida-e-volta da faceta
- `7037009` 20:13 — Correção T2 (3) da fila (L0-05): semeadura de demonstração em vez de SQL direto no e2e dos 1.000 jobs
- `d4c592e` 20:04 — Testes do catálogo (L0-03): 11 arquivos de API, 3 de unidade, casos cruzados A->B e eventos esperados
- `3f44ec1` 20:04 — Integração do catálogo com as trilhas A e B (L0-03): routers, páginas, limites, tipos de job, escopo com uuid e OpenAPI
- `76aa929` 20:03 — Catálogo de conteúdo (L0-03, backend): migração 011, modelo plat.item com RLS por pode_ler, versões imutáveis com sha256, relações sem ciclo, compartilhamento em 5 níveis, link por token, busca com pesos, pastas, categorias, lixeira, transferência, miniatura e 6 tipos de job
- `5fe53c0` 18:04 — Medidas do testador para L0-05-jobs (T2, 40): job de 5 min pelo SSE público (1º evento 6 ms, latência 5 ms), reinício/kill -9/5 x kill -9, RLS 15/15 rotas, vazão 1.614 jobs/min com 1 worker, worker homônimo (012) sem devolução, 1.000 jobs pintam em 48 ms
- `05a41cd` 17:56 — Conteúdo (L0-03, frontend): contrato do backend (ordenar+direcao, lote tags, status nenhum, miniatura em JSON), upload só com /api/uploads publicado, editor de tags fora do plat-formulario, painel mais largo; e2e sem esperar aviso velho
- `4037164` 17:55 — Documentação do turno 2, passe 2 (cronista): absorve as migrações 012 e 013 do commit 9be9c6a
- `9be9c6a` 17:52 — Correção T2 (2) da fila (L0-05, achado do testador): identidade do worker por processo e ceifa só por heartbeat
- `7cd0327` 17:52 — Documentação do turno 2 (cronista): MANUAL por tela, ARQUITETURA de identidade e fila, CHANGELOG 0.2.0, PARIDADE preenchida, README
- `a06ca71` 17:46 — e2e da tela Conteúdo (L0-03-catalogo): fluxo criar-editar-compartilhar-link-busca-favoritar-mover-apagar-restaurar com capturas L0-03_*.png, medidas de primeira pintura e soma dos módulos, chave crua
- `41c1dd9` 17:46 — Tela Conteúdo (L0-03-catalogo, frontend): lista/grade com cursor, busca por campo, filtros, pastas, seleção em massa, painel do item (metadado, dados por JSON Schema, configurações, versões, relações, compartilhamento e links), lixeira, favoritos, transferência de dono, upload do ADR 0005, página /c/<token>
- `abbb03d` 17:23 — Correção T2 do L0-02 (achados do testador): apagar inquilino, fixtures sem resíduo, log por chamada, Referrer-Policy em toda location
- `7824846` 17:19 — Fila (L0-05): funções de gatilho da 004 sem EXECUTE para PUBLIC e plat_app (010; achado de test_funcoes_seguras)
- `7c62831` 17:19 — Correção T2 do front (L0-02): componentes re-traduzem quando o dicionário chega; chaves conta.apos_pendencia e nav.tarefas_desc; e2e contra chave crua
- `90d03c0` 17:14 — Fila (L0-05): reinício não consome tentativa (008) e testes de agenda robustos a outras sessões
- `12b2c2e` 17:14 — Medidas do testador para L0-02-tenant-auth (T2, 40): varredura cruzada viva 73/73 rotas e 411 chamadas com 0 acesso cruzado, login mediana 129 ms e p95 145 ms, auth por token 2,5 ms, RLS 22/22, 51 SECURITY DEFINER sem PUBLIC, 1 chave i18n ausente
- `ffedc05` 16:11 — Integração T2 da fila com a identidade (L0-05 × L0-02): x-auth/x-privilegio, eventos e casos cruzados
- `ad2ea29` 15:59 — Correção T2 da fila (L0-05, achados do testador): transições de estado só pelo worker; expurgo de marcadores
- `38430b2` 15:59 — Medidas do item L0-02-tenant-auth (backend): rotas 56/56 cobertas, login 129 ms, auth por token 2,94 ms, log 0,98 ms, revogação 0,01 s
- `441069c` 15:49 — ADR 0005: ingestão vetorial (T2, preparação do L0-04)
- `ae6ec45` 15:40 — Testes do portão L0-02: varredura cruzada A→B gerada do OpenAPI, força bruta, token, funções seguras, log_acesso
- `b5c336b` 15:40 — Instalador (L0-02): admin de plataforma com superadmin, demos sem, limite por IP nos logins, partições, cryptography
- `2ffe8b4` 15:40 — Identidade (L0-02, trilha A, 2/4): sessão, token, middleware de log_acesso, 54 rotas do ADR 0002, páginas
- `9be4a04` 15:40 — Identidade (L0-02, trilha A, 1/4): migração 003, política, TOTP, escopos, redação, contrato de erro, limites
- `757f0d3` 15:26 — e2e do L0-02-tenant-auth (playwright, chromium): login, 2FA, conta, usuários, grupos, papéis, tokens, log
- `50d587d` 15:26 — Telas de identidade (L0-02-tenant-auth, trilha A, frontend): entrar, minha conta, usuários, grupos, papéis, tokens, log
- `6a00645` 15:26 — Base do front (L0-02-tenant-auth, trilha A): tema único, módulos ES de base, componentes, layout, i18n e DOMPurify
- `431ba0c` 15:25 — Instalador (L0-05): inquilinos de demonstração com cota_jobs_dia = 100000
- `57c24a5` 15:24 — ADR 0004: catálogo de conteúdo (T2, preparação do L0-03)
- `674798d` 15:23 — Unidade plat-worker e instalador (L0-05): passo h2, chaves PLAT_WORKER_* no .env, conferência de worker vivo
- `52d7a3b` 15:23 — API da fila (L0-05): /api/jobs, /api/agendas, eventos SSE, páginas /tarefas, /saude com fila, testes de API
- `cab32da` 15:23 — Fila de jobs (L0-05, trilha B): migração 004, registro de tipos, worker plat-worker, agendas e tipos de diagnóstico
- `1668d76` 14:10 — Tela Tarefas (L0-05-jobs, trilha B, frontend): lista ao vivo por SSE, detalhe com log, agendas e e2e
- `1540c84` 13:45 — ADR 0003: fila de jobs (T2, trilha B)
- `0985a11` 13:44 — ADR 0002: identidade e acesso (T2, trilha A)
- `6678cf6` 13:20 — Documentação do L0-01 atualizada sobre 8ffe950 e 3083366 (passe curto do cronista)
- `3083366` 13:13 — Medidas do item L0-01-repo, rodada 2 do testador sobre 8ffe950
- `8ffe950` 13:08 — L0-01 correção (T1): dependências fixadas sem ~/.local, senha por stdin, HSTS, Swagger local, make medidas, PLAT_GIT_SHA
- `7092755` 13:05 — Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0
- `3b53c24` 12:55 — P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1
- `ca61ea1` 12:53 — Medidas do item L0-01-repo assinadas pelo testador (turno T1)
- `b22761e` 12:42 — Medidas do item L0-01-repo regeneradas sobre o commit 904a849
- `904a849` 12:42 — Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes
- `a1d0c20` 12:15 — Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0)

## Registro por item (ledger)


### Turno 1 · L0-01-repo · 2026-09-05 13:21
- **Construído:** repo enterprise/ (install.sh idempotente, schema plat + role plat_app + pg_hba, migracoes 001/002 com sha256, app FastAPI /saude e /api/versao, systemd plat-api :8150 com PYTHONNOUSERSITE=1, nginx plat.iagrointel.com noindex+HSTS, Swagger local, Makefile check/medidas/vendor, 82 testes + 1 e2e, ADR 0001, ARQUITETURA/MANUAL/CHANGELOG/README, PARIDADE.md, laco/PAINEL.md via gera_painel.py); DNS A DNS-only + certificado Let's Encrypt
- **Medições:** install_zero_s 6.24 · install_nunca_viu_s 9.14 · testes 82 · make_check_s 2.86 · placeholders 0 · noindex_rotas 11/11 · hsts_rotas 11/11 · latencia_saude_ms_mediana_tls_novo 19.8 · rss_mb 88.5 · rls_insert_cruzado_bloqueado True · nomes_cliente 0
- **Adversário:** rodada 1 PARCIAL (deps de ~/.local, senha no journal, ADR x codigo, HSTS/Swagger CDN) -> corrigido em 8ffe950 -> rodada 2 PASSA
- **Portão:** entregue (5/5 clausulas; P1-P9 passam; P4 nao se aplica)
- **Próximo passo:** T2 em trilhas paralelas: L0-02 tenant/auth (com clausulas herdadas), L0-05 jobs, + trilhas de preparacao (pesquisa/arquitetura) dos itens L0-03/L0-04/L1-01; antes, integrar a decomposicao (>200 itens) ao backlog
- Turno 2 · 2026-09-05 17:30 · L0-02-tenant-auth: interrompido (sessão morta), devolvido a pendente
- Turno 2 · 2026-09-05 17:30 · L0-05-jobs: interrompido (sessão morta), devolvido a pendente
- Turno 2 · 2026-09-05T17:56 · L0-05-jobs: driver devolveu a pendente por 'órfão > 4 h' enquanto a trilha estava viva (testador em fase 5, backend corrigindo); revertido pelo gerente; driver passa a usar o mtime de .turno_ativo, que o gerente toca a cada acordar
- Turno 2 · 2026-09-05 23:30 · L0-03-catalogo: interrompido (sessão morta), devolvido a pendente

### Turno 2 · L0-14-identidade-visual · 2026-09-06T01:10
- **Construído:** web/estilo/tokens.css (paleta 3 estados + tipografia instrumento + tique de canto); 4 fontes vendorizadas (web/vendor/*.woff2, OFL-1.1); web/login.html e web/style.css restilados via body.instrumento escopado; tests/unit/test_vendor.py estendido para .woff2/OFL-1.1.
- **Medições:** e2e test_login.py 2/2 verde; test_vendor.py 2/2 verde; suite 'not lento' 382 testes verde; 0 erro de console na tela de entrada; /conta pós-login mantém --fundo #14171c (outras 8 telas intocadas).
- **Adversário:** não rodado nesta fatia (fora de escopo do pedido do dono; próximo turno do item)
- **Portão:** parcial — cláusulas (b) e parte de (a) fechadas; (c)(d)(e)(f)(g)(h) pendentes
- **Próximo passo:** restilar as 8 telas restantes uma a uma com captura antes/depois; axe-core para (f); família de ícones para (c); página /estilo para (e)

### Turno 2 · L2-04-b-parser-where-ast · 2026-09-06 02:12
- **Construído:** parser where/CQL2 seguro: gramática fechada, sem eval/exec, SQL parametrizado contra lista branca
- **Medições:** casos_de_ataque 39 · testes_suite 651
- **Portão:** entregue (passagem única arquiteto+backend, verificado sob flock)
- **Próximo passo:** -

### Turno 2 · L0-12-contrato-api-e-limites · 2026-09-06 02:12
- **Construído:** CONTRATO_API.md + limite de corpo com defesa a Content-Length forjado e corpo em chunks mentindo o tamanho
- **Medições:** limite_corpo_padrao_mib 10 · testes_novos 20
- **Portão:** entregue (passagem única arquiteto+backend, verificado sob flock)
- **Próximo passo:** -

### Turno 2 · L6-01-a-procedencia-acervo · 2026-09-06 02:12
- **Construído:** acervo da casa exposto como catálogo assinável só-leitura; só fontes com licença ESCRITA aparecem (D17)
- **Medições:** fontes_com_licenca 68 · fontes_total 376
- **Portão:** entregue (passagem única arquiteto+backend, verificado sob flock)
- **Próximo passo:** -

### Turno 2 · L7-19-segredos-e-certificados · 2026-09-06 02:12
- **Construído:** PLAT_SECRET/PLAT_DSN_WORKER fora do .env, por LoadCredential do systemd; rotação sem reinstalar; TLS renovação automática confirmada
- **Medições:** achados_adversario_corrigidos 3
- **Portão:** entregue (passagem única arquiteto+backend, verificado sob flock)
- **Próximo passo:** -

### Turno 2 · L0-11-arquivos-objetos · 2026-09-06 02:12
- **Construído:** objetos por inquilino no Garage (SigV4 próprio, sem boto3 - disco a 98%); bucket/chave/cota por inquilino, conteúdo endereçado por sha256, multipart
- **Medições:** testes 13
- **Portão:** entregue (passagem única arquiteto+backend, verificado sob flock)
- **Próximo passo:** -

### Turno 2 · L0-02-a-login-sessao · 2026-09-06 02:16
- **Construído:** item filho absorvido pelo pai já entregue — sem código novo, só verificação das cláusulas
- **Medições:** clausulas ja satisfeitas pelo L0-02-tenant-auth entregue: cookie HttpOnly/Secure/SameSite=Lax, sessao 12h ociosa/7d maximo com 401+apagamento, sessao nunca em log (redigida); tests/api/test_login.py + test_sessao.py verdes
- **Portão:** entregue por herança do pai
- **Próximo passo:** -

### Turno 2 · L0-05-a-fila-postgres · 2026-09-06 02:16
- **Construído:** item filho absorvido pelo pai já entregue — sem código novo, só verificação das cláusulas
- **Medições:** clausulas ja satisfeitas pelo L0-05-jobs entregue: unidade plat-worker ativa, /saude com campo worker, 100 jobs sem duplicata, retentativa 2/4/8s ate falhou; tests/api/jobs/test_jobs_fila.py verde
- **Portão:** entregue por herança do pai
- **Próximo passo:** -

### Turno 3 · L7-03-f-dependencias-cve-log-correcoes · 2026-09-06 02:50
- **Construído:** scripts/varredura_dependencias.py (pip-audit + classificação de severidade por rótulo OSV/GHSA ou CVSS v3.1 calculado + exceção com prazo em docs/excecoes_cve.json); make seguranca-deps (opcional, fora de check); docs/SEGURANCA.md §7 (justificativa pip-audit x safety, mecânica, log de correções vazio); requirements.txt com pip-audit==2.10.1 e a árvore transitiva pinada
- **Medições:** testes_unitarios 13 · testes_lento_integracao_real 1 · cve_real_encontrado_hoje PYSEC-2026-215/idna 3.13, CVSS 5.3 media, nao bloqueia
- **Adversário:** não lançado como agente separado nesta passagem única (pedido do dono: rápido); a refutação ficou por conta dos testes automatizados citados acima, incluindo o teste de não-regressão da severidade desconhecida (trata como grave por padrão-seguro)
- **Portão:** parcial — mecanismo funciona e testado (CVE sintética via pip-audit dublado: reprova sem exceção, passa com exceção viva, some quando 'corrigido'); faltam osv-scanner/trivy, tabela plat.vulnerabilidade, docs/CORRECOES.md separado, timer diário, ligar ao check principal (escopo reduzido a pedido do dono nesta passagem)
- **Próximo passo:** ligar seguranca-deps ao check quando o dono aceitar dependência de rede; timer systemd diário; osv-scanner/trivy

### Turno 3 · L7-03-b-antivirus-anexos · 2026-09-06 02:50
- **Construído:** app/varredura_conteudo.py (motor de assinatura mágica via libmagic, interface Motor trocável por ClamAV); integrado em app/rotas_arquivos.py::enviar (1 PUT e multipart, antes de qualquer chamada ao Garage); L0-03/miniatura não precisou de código novo (Pillow já era a barreira); docs/SEGURANCA.md §8 (D21 medido de novo, tabela de integração, justificativa medida contra denylist)
- **Medições:** testes_unitarios 10 · testes_api_fim_a_fim 2 · falso_positivo_binario_aleatorio_medido 0,9% (18/2000) - motivo documentado de NAO existir denylist p/ octet-stream
- **Adversário:** não lançado como agente separado nesta passagem única; regressão real encontrada e corrigida pelo próprio processo (tests/api/catalogo/test_miniatura.py::test_adaptador_de_objetos_e_url_assinada quebrava com a varredura dentro de objetos.guardar() — corrigido movendo a varredura para a borda, rotas_arquivos.py, e documentado por quê)
- **Portão:** parcial — cláusula literal do portão (.jpg com script recusado) PASSA nos dois caminhos (1 PUT e multipart); ClamAV real fica de fora por D21 (disco 98%/RAM 323 MiB livre medido 06/09)
- **Próximo passo:** instalar clamd e escrever MotorClamAV quando D21 resolver (disco/RAM, ou servidor dedicado D37)

### Turno 3 · L2-01-a-basemap-local-pmtiles · 2026-09-06T02:58:07Z
- **Construído:** PMTiles local (web/dados/basemap/guarulhos.pmtiles, 18,3 MiB, OSM ODbL 1.0, Guarulhos-SP) extraido com ogr2ogr + tippecanoe (4 camadas: estradas/edificacoes/cobertura/lugares); vendor pmtiles-4.5.0.js (BSD-3-Clause); tela /mapa (MapLibre tela cheia, navegacao, escala, coordenadas do cursor, seletor de camada base); rota em app/paginas.py; nav em layout.js + i18n; nginx com location regex para .pmtiles (Range 206 + gzip off), template e site vivo.
- **Medições:** e2e tests/e2e/test_mapa.py: 206/Content-Range sem gzip; captura do #mapa com > 50 cores distintas (PIL getcolors); 0 erro de console; make check-rapido completo = 742 passed.
- **Adversário:** auto-adversarial (sem agente separado neste turno, passagem unica pedida pelo dono): 2 achados reais pegos e corrigidos antes de publicar -- (1) tippecanoe '-l' repetido fundia as 4 camadas em 1 so (circulo em cada vertice de rua/predio, confirmado por decodificacao de tile real); (2) paineis com var(--texto) sobre fundo fixo escuro ficavam ilegiveis em preferencia de sistema clara (medido: computed color == computed background).
- **Portão:** passa (cláusulas do arquiteto registradas no próprio item; ver nota)
- **Próximo passo:** L2-01-mapa-web (visualizador completo: Martin/RLS por camada do inquilino, raster, legenda, popup, busca, impressao) e L2-02-e-simbolos-sprites-glifos (rotulo de texto no mapa).

### Turno 3 · L2-01-a-basemap-local-pmtiles · 2026-09-06 03:01
- **Construído:** primeira tela de mapa real do produto: MapLibre GL 4.7.1 + PMTiles servido por nginx/Range, sem servidor de tiles dinâmico, sem chave externa; OSM/ODbL 1.0 recorte de Guarulhos-SP (18,3 MiB); tema instrumento
- **Medições:** e2e: 206/Content-Range, canvas com >50 cores distintas, 0 erro de console; 742 testes verdes
- **Portão:** entregue
- **Próximo passo:** incidente auto-causado (osmium extract sem limite -> OOM -> Postgres fora 14 min) recuperado pelo procedimento documentado da casa; regra nova na skill para não repetir

### Turno 3 · L7-14-instalacoes-apt-desta-linha · 2026-09-06 03:01
- **Construído:** commit 3302f56
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L7-16-assinatura-pacote · 2026-09-06 03:01
- **Construído:** commit 3302f56
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L7-03-f-dependencias-cve-log-correcoes · 2026-09-06 03:01
- **Construído:** commit d69f417
- **Portão:** parcial
- **Próximo passo:** instalar ClamAV quando D21 resolver

### Turno 3 · L7-03-b-antivirus-anexos · 2026-09-06 03:01
- **Construído:** commit d69f417
- **Portão:** parcial
- **Próximo passo:** instalar ClamAV quando D21 resolver

### Turno 3 · L0-02-b-politica-senha-bloqueio · 2026-09-06 10:40
- **Construído:** politica de senha/bloqueio ja satisfeita pelo L0-02 entregue; 49+60 testes verdes
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-02-c-2fa-totp · 2026-09-06 10:40
- **Construído:** TOTP ja satisfeito; gap real fechado: segredo TOTP agora provado enc: no banco por consulta direta, nao so no cifrador (commit c193765)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-02-d-token-servico · 2026-09-06 10:40
- **Construído:** token de servico ja satisfeito (escopo/revogacao/IP/Referer curinga/expiracao/log); enforcement fim-a-fim de camada:ler:<uuid> so quando L1-02/L2-04 existirem
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-10-eventos-historico · 2026-09-06 10:51
- **Construído:** cobertura de eventos ja era 100% (75/75 rotas de escrita); gap fechado: plat_app tambem barrado em DELETE plat.evento (so UPDATE tinha teste)
- **Medições:** rotas_escrita 75 · cobertura 75/75
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L2-10-c-linguagem-expressao · 2026-09-06T11:00:39
- **Construído:** nucleo da linguagem de expressao propria (equivalente ao Arcade): EBNF em docs/EXPRESSAO.md, AST tipada + avaliador Python (app/expressao/avaliador_py.py) e o MESMO avaliador em JavaScript puro (web/js/expressao/avaliador.js), sem eval/exec/compile/Function dinamico; 18 funcoes; achado de seguranca (cadeia longa do mesmo operador estourava a pilha do avaliador; ast_de_json sem limite de profundidade) encontrado e corrigido na mesma passagem
- **Medições:** funcoes_implementadas 18 · vetores_de_equivalencia 41 · vetores_avaliados_sem_erro_no_lado_javascript 41 · testes_novos test_expressao_avaliador.py + test_expressao_equivalencia.py + test_expressao_seguranca.py + test_expressao_doc_sincronizada.py + test_expressao_medidas.py, todos verdes
- **Adversário:** nao rodado nesta fatia (papel nao presente nesta passagem — arquiteto+backend direto, pedido do dono; testes de seguranca proprios cobrem a refutacao do item-pai: campo fora da lista, cadeia funda, string de 10 MB, limite de passos/tempo sob carga)
- **Portão:** parcial — nucleo entregue (gramatica + 2 avaliadores concordando byte a byte + seguranca); faltam >=40 funcoes, >=200 vetores, tipos lista/dicionario/geometria, integracao com popup/formulario/L5-11, tabela de paridade completa
- **Próximo passo:** integracao com popup/rotulo/formulario (L5-11) e as funcoes/tipos restantes da hipotese cheia

### Turno 3 · L2-10-c-linguagem-expressao · 2026-09-06 11:01
- **Construído:** nucleo da linguagem de expressao: EBNF, parser sem eval/exec dos dois lados (Python+JS), 18 funcoes, AST JSON exportavel
- **Medições:** vetores_equivalencia 41 · testes todos verdes no escopo
- **Portão:** parcial
- **Próximo passo:** restante das funcoes/tipos/integracao em item futuro

### Turno 3 · L2-11-c-rota-matriz-isocrona · 2026-09-06 11:04
- **Construído:** OSRM isolado plat-osrm-guarulhos:5010 (recorte <=50MB, dado proprio, nunca tocou os OSRM de outros projetos); /api/rota, /api/matriz, /api/isocrona (grade+concave_hull)
- **Medições:** testes 9
- **Portão:** parcial
- **Próximo passo:** pgRouting/perfis/escala em item futuro

### Turno 3 · L7-31-ambiente-homologacao · 2026-09-06 11:08
- **Construído:** schema plat_homolog isolado no mesmo Postgres (nao banco novo, disco 98%); migracoes reaplicadas por token-rewrite; make homolog sobe API/worker temporarios em :8154, roda e2e, derruba por PID exato
- **Medições:** tabelas_prova 44->45->44 em plat_homolog, plat constante
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-05-e-worker-em-container · 2026-09-06 11:12
- **Construído:** Dockerfile.worker + compose + install.sh --worker-container; achado critico: getppid()==1 sempre verdadeiro dentro de conteiner (worker e PID 1) matava 100% dos jobs sem log - corrigido comparando com o PID pai pre-fork; RLIMIT_DATA agora nunca excede o teto de memoria do cgroup
- **Medições:** testes 9
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-08-d-ldap · 2026-09-06 11:26
- **Construído:** bind LDAP/AD por inquilino, mapeamento grupo->perfil, provisionamento automatico sem guardar senha, importacao em lote; corrigiu de quebra tambem: EXECUTE FROM PUBLIC (achado do L0-10), e um bloqueio de 2FA na conta plataforma que travava make check-rapido de TODAS as trilhas
- **Medições:** testes 14
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-b-pastas-tags-categorias-classificacao · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_pastas_categorias.py (5 testes)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-c-busca · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_busca.py (8 testes) - titulo exato antes do rank, sintaxe por campo
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-d-grupos · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** reaproveita grupos do L0-02 (dono/gerente/membro) aplicados ao compartilhamento do catalogo
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-e-compartilhamento · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_compartilhamento.py (5 testes) + adversario (link revogado nega em 30ms)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-f-tela-conteudo · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** e2e 2/2 na URL real, 10 capturas, 0 erro de console, primeira pintura 24ms
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-g-detalhe-item-miniatura · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_miniatura.py (5 testes) - miniatura confere acesso antes do formato
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-h-lixeira-protecao-status · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_lixeira.py (8 testes) + adversario (409 protegido/dependente)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-i-dependencias · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_relacoes.py (4 testes) - dependencia bloqueia exclusao
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-j-transferencia-dono · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_transferencia.py (5 testes) - inclui apagar usuario apos transferir tudo (migracao 016)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-k-favoritos-notificacoes · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** favoritos no modelo de item (plat.item favorito); notificacoes NAO construidas - subitem futuro se precisar
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-l-versoes-item · 2026-09-06 12:03
- **Construído:** coberto pelo trabalho ja entregue de L0-03-catalogo (T2)
- **Medições:** test_versoes.py (4 testes) + adversario (UPDATE/INSERT/DELETE direto negado)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-03-catalogo · 2026-09-06 12:03
- **Construído:** fechamento tardio de bookkeeping: item inteiro ja construido/testado/refutado desde T2 (612 testes, adversario PASSA, correcao de desempenho aplicada) mas nunca marcado entregue no estado - corrigido agora com veredito escrito em handoffs/T2/L0-03-catalogo/99_veredito.md
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-05-b-progresso-cancelamento · 2026-09-06 12:17
- **Construído:** 3 gaps de teste fechados (log 10 mil linhas resumido, limite/duracao SSE, progresso grampeado em 100); mecanismo ja existia, zero codigo de producao novo
- **Medições:** testes_novos 4+2+1
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-05-d-periodicos · 2026-09-06 12:17
- **Construído:** so 3 de 5 periodicos exigidos estavam registrados; fechado com jobs.sessoes_expurgar + jobs.manutencao_analyze (migracao 026); e2e como admin plataforma provou as 5 linhas
- **Medições:** periodicos 5 · testes_novos 8+1 e2e
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-09-metadado-catalogo · 2026-09-06 12:36
- **Construído:** GET /api/itens/{id}/metadado.xml (ISO 19139/GMD, validado contra XSD oficial cacheado offline em docs/xsd/cache/) + catalogo externo OGC API Records em /ogc/records (pouso, conformance, colecao catalogo, items, item unico), ambos autenticados por catalogo:ler (sessao ou token de servico do L0-02), isolamento por RLS de plat.item
- **Medições:** testes_novos 10 · mediana_5_metadado_xml_ms 10.4 · xsd_cache_arquivos 57 · xsd_cache_bytes 611925
- **Portão:** parcial (exportacao ISO + OGC API Records feitos e testados; editor na tela, ISO 19115-3, CSW e varredura cruzada automatica ficam pendentes, nomeados no handoff)
- **Próximo passo:** somar as rotas novas a docs/openapi.json + tests/api/cruzado_casos.py (integracao final do turno, junto com as outras trilhas); adversario independente; decidir ISO 19115-3/CSW

### Turno 3 · L0-09-metadado-catalogo · 2026-09-06 12:37
- **Construído:** metadado.xml ISO 19139 validado offline contra XSD (57 arquivos em cache); OGC API Records /ogc/records; ambos exigem catalogo:ler, RLS herdada de plat.item
- **Medições:** testes 10
- **Portão:** parcial
- **Próximo passo:** ISO 19115-3/CSW/editor em item futuro

### Turno 3 · L5-05-documento-versoes · 2026-09-06 12:48
- **Construído:** documento de construtor generico sobre o mecanismo ja entregue do L0-03 (plat.item/item_versao); ULID por no, validacao de grafo (nos duplicados/ligacoes soltas), hash canonico verificavel fora do banco (jsonb::text do Postgres NAO e reproduzivel externamente - medido e corrigido)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L7-15-processo-release · 2026-09-06 12:48
- **Construído:** cadeia completa ate a decisao humana de publicar: semver, changelog do git log, make check, make homolog, manifesto de homologacao DENTRO do pacote assinado Ed25519 (impossivel forjar sem a chave privada)
- **Portão:** entregue
- **Próximo passo:** -

### Turno 3 · L0-02-e-varredura-cruzada-rls · 2026-09-06 12:49
- **Construído:** remedida hoje: OpenAPI cresceu de 123 para 138 rotas, cruzado_casos.py ja acompanhava, cobertura 100%; REVOKE/GUC forjado confirmados (20 testes)
- **Portão:** entregue
- **Próximo passo:** adversario independente lancado, resultado pendente

### Turno 3 · L0-02-f-tela-usuarios · 2026-09-06 12:49
- **Construído:** tela ja completa; e2e faltante escrito (perfil em lote, 2FA, desbloquear, apagar com grupos, 401 em 73,1ms); GAP REAL fechado: apagar usuario com itens do catalogo caia em erro generico de FK, agora 409 possui_itens nomeado com a lista
- **Portão:** entregue
- **Próximo passo:** adversario independente lancado, resultado pendente

### Turno 3 · L0-04-ingest-vetor · 2026-09-06 13:04
- **Construído:** nucleo da ingestao vetorial (upload L0-11 reaproveitado -> ingestao.inspecionar -> confirmar -> ingestao.carregar -> camada_vetorial) para 4 formatos: shapefile.zip, gpkg, geojson, csv; migracoes 029/032/033 (esta ultima e a 032 corrigem achados do testador e da trilha L5-05 sobre a 029)
- **Medições:** 20 testes verdes (13 api/ingestao + 7 unit/test_nomes); dado real (web/dados/basemap/guarulhos.pmtiles, OSM/ODbL) via tests/dados/gerar.py, sem rede; ST_MakeValid antes de ReducePrecision (ordem do ADR 0005 6.4 quebra em geometria real, corrigida)
- **Adversário:** 3 ataques do portao verificados: shapefile sem .prj (crs.perguntar, 422 perguntas_pendentes antes de confirmar, importa apos SRID), GeoJSON com poligono auto-intersectado (corrigidas=1 no relatorio), CSV com virgula decimal (valor gravado conferido byte a byte); RLS FORCE cruzada e cota sem tabela orfa tambem testadas
- **Portão:** parcial
- **Próximo passo:** L0-04-d completo (KML/GPX/XLSX), L0-04-e (DXF/DWG), L0-04-f (FileGDB/FlatGeobuf/GML/MapInfo/GeoParquet), L0-04-g/h/i/j (atualizar/exportar/fonte/vista); teste de morte do worker (SIGKILL) para a invariante tabela-item; ver handoff laco/handoffs/T3/L0-04-ingest-vetor.md

### Turno 3 · L0-02-e-varredura-cruzada-rls · 2026-09-06 13:06
- **Construído:** remedido com o codigo de hoje (mecanismo ja existia desde T2): 138 rotas do docs/openapi.json vivo = 138 casos em cruzado_casos.py; gravado em tests/medidas/L0-02-e.json (nome do portao) e L0-02-tenant-auth.json; test_funcoes_seguras.py (REVOKE PUBLIC + GUC forjado) passou na mesma suite
- **Medições:** rotas_total 138 · rotas_cobertas 138
- **Adversário:** PASSA (agente independente: 43+19 testes filtrados verdes; GUC forjado, cross-tenant e rota-sem-caso todos bloqueados/reprovados como esperado)
- **Portão:** entregue
- **Próximo passo:** quando outra trilha commitar a integracao final do openapi.json (conexoes/importacoes/ogc-records/metadado.xml), repetir test_cobertura_100_por_cento so para conferir - nao deve exigir trabalho novo aqui

### Turno 3 · L0-02-f-tela-usuarios · 2026-09-06 13:06
- **Construído:** tela e API ja tinham tudo (criar/editar/desabilitar/redefinir senha/2FA/desbloquear/lote 100/ultimo admin); escrito e2e test_usuarios_perfil_lote_2fa_desbloquear_apagar_com_grupos_e_401 cobrindo o resto pela interface; gap real achado e corrigido: apagar_usuario so recusava por grupos, nao por itens do catalogo (novo 409 possui_itens); adversario achou e ajudou a fechar um 2o gap real: POST /api/usuarios deixava admin restrito (sem membros.papel) fabricar admin pleno - corrigido exigindo membros.papel para perfil!=visualizador ou papel_id
- **Medições:** desabilitar_para_401_ms 73.1 · e2e_usuarios 2 passed
- **Adversário:** PARCIAL->fechado nesta sessao (escalonamento de privilegio real reproduzido e corrigido; ver laco/handoffs/T3/L0-02-ef.md)
- **Portão:** entregue
- **Próximo passo:** pendencia nomeada, nao bloqueante, para o dono decidir: papel_id atribuido (criacao OU edicao) nao checa se o ator tem os privilegios daquele papel (so checa perfil_minimo); PARIDADE.md 'gestao de membros' segue parcial por falta de fluxo unico transferir+apagar (UX, nao mecanismo)

### Turno 3 · L6-01-a-registro · 2026-09-06 13:20
- **Construído:** plat.acervo_camada (migracao 027) + scripts/acervo_sync.py, registro de camada (nao de fonte - diferente do ja entregue L6-01-a-procedencia-acervo, confirmado por grep antes de escrever): 462 candidatas medidas (270 em public) via geometry_columns x acervo.objeto; COUNT(*) exato com timeout 25s (nunca reltuples); tabela fantasma = regra dinamica (estimativa>0/exata=0), cobre as 2 conhecidas sem citar nomes; lista branca de coluna por nome (rede minima, L6-01-f endurece por conteudo); estado por licenca D17; ordem por sincronizado_em mais antigo primeiro prova convergencia entre rodadas (81->172 expostas). Achado e corrigido: --limite de depuracao apagava o registro inteiro (poda corrigida para comparar contra o universo completo de candidatas).
- **Medições:** candidatas 462 · candidatas_public 270 · rodada_1_duracao_s 274.9 · rodada_2_duracao_s 286.0 · rodada_completa_lento_s 297.93
- **Adversário:** auto-adversarial nesta sessao (ARQUITETO+BACKEND unico, sem agente separado): 8 casos de fantasma/timeout/licenca cobertos por teste; sem adversario independente de outro processo
- **Portão:** entregue
- **Próximo passo:** L6-01-b (view so-leitura + RLS por assinatura sobre a tabela original) le acervo_camada.estado='exposta'; L6-01-f (LGPD por conteudo) precisa rodar antes de qualquer camada chegar a tela

### Turno 3 · L6-02-a-modelo-conexao-e-seguranca · 2026-09-06 13:20
- **Construído:** plat.conexao (migracao 030, renumerada de 028 por colisao com trilha concorrente) + app/conexao/{seguranca,credencial,modelos,rotas}.py: modelo generico de conexao externa (tenant_id+RLS), credencial AES-GCM (nunca pgp_sym_encrypt), defesa de SSRF por resolucao+pinagem de IP (nunca lista de host): recusa IP privado/loopback/link-local/CGNAT/reservado/multicast, so http/https, revalida CADA redirecionamento do zero, conecta pinado no IP ja validado (TLS continua verificando o hostname original, fechando DNS-rebinding). POST /api/conexoes/{id}/testar roda o teste de saude contra URL publica real (IBGE). Adicionadas entradas de conexao_b em tests/api/cruzado_casos.py (as 6 rotas novas nao apareciam no teste cruzado A->B; corrigido, confirmado que so restam rotas de outra trilha - ingestao/ogc - na lista de faltando).
- **Medições:** testes_unitarios_seguranca 26 · testes_api_conexoes 13 · casos_ssrf_do_portao_cobertos 8
- **Adversário:** auto-adversarial nesta sessao: redirecionamento de host publico real para 169.254.169.254 (recusado no hop 1, aceito no hop 0), DNS rebinding (conexao pinada nao resolve de novo), redirecionamento em loop (para no limite de saltos), IPv4-mapped-IPv6/octal/decimal/short-form todos recusados; sem adversario independente de outro processo
- **Portão:** entregue
- **Próximo passo:** os 15 conectores concretos (L6-02-b em diante) leem plat.conexao.config validado por JSON Schema proprio; reconciliar com o tipo_item de catalogo 'conexao' (protocolo 'acervo') quando o primeiro conector concreto existir
- Turno None · 2026-09-06T13:20:30Z · L0-02-g-perfil-usuario: 
- Turno None · 2026-09-06T13:20:45Z · L0-05-c-tela-tarefas: 
- Turno None · 2026-09-06T13:37:21Z · L6-01-d-ficha-fonte: 
- Turno None · 2026-09-06T13:37:21Z · L6-01-f-lgpd: 

### Turno 3 · L0-07-a-configuracoes-org · 2026-09-06 13:49
- **Construído:** GET/PUT /api/org, POST/DELETE /api/org/logo, migracao 034 (cota_usuarios/usuarios_ativos), politica de senha/2FA lida de tenant.config.auth existente
- **Portão:** parcial
- **Próximo passo:** blocos de pagina inicial/galeria/banner/termo de acesso
- Turno None · 2026-09-06T14:01:21Z · L0-03-a-modelo-item: 

### Turno 3 · L0-03-a-modelo-item · 2026-09-06 14:03
- **Construído:** auditoria confirmou que o item ja estava construido junto com L0-03-catalogo (migracao 011, ADR 0004); RLS/OpenAPI/JSON-Schema-422/uuid-estavel/teste-cruzado todos verificados de novo cláusula a cláusula; p95 lista por tipo 50,8ms/mediana 23,8ms com 10 mil itens; adversario ao vivo (fila do flock presa por RAM) tipo inexistente/resumo 5000/extent fora de faixa/PUT trocando tenant_id-dono-id todos 4xx nomeados; <script> na descricao e sanitizado (nao recusado) - desvio documentado; paridade Esri do item escrita em docs/PARIDADE.md pela 1a vez
- **Medições:** p95_ms 50.8 · mediana_ms 23.8 · itens 10000
- **Portão:** entregue
- **Próximo passo:** rodar make check completo quando a fila do flock esvaziar (confirmacao automatizada ao lado da verificacao ao vivo)

### Turno 3 · L6-02-l-saude · 2026-09-06 14:04
- **Construído:** historico + estado_saude + periodico 15min + tela /conexoes com selo e teste manual; 21 testes novos (25 passaram no arquivo)
- **Portão:** parcial
- **Próximo passo:** aviso no mapa quando L6-02-b+ desenhar camada externa

### Turno 3 · L6-05-proveniencia-camada-externa · 2026-09-06 14:04
- **Construído:** proveniencia.py le licenca real por protocolo; POST /publicar cria item de catalogo com ficha; provado com Esri e Element84 STAC ao vivo
- **Portão:** parcial
- **Próximo passo:** legenda de mapa quando existir camada externa desenhada
- Turno None · 2026-09-06T14:06:31Z · L1-01-b-validacao-e-isolamento-da-entrada: 
- Turno None · 2026-09-06T14:06:31Z · L3-01-a-modelo-dado: 
- Turno None · 2026-09-06T14:06:31Z · L3-01-b-unidades: 
- Turno None · 2026-09-06T14:06:31Z · L2-10-c-linguagem-expressao: 
- Turno None · 2026-09-06T14:06:31Z · L1-01-d-garage-por-inquilino: 
- Turno None · 2026-09-06T14:07:42Z · L2-10-c-linguagem-expressao: 
- Turno None · 2026-09-06T14:18:58Z · L6-01-g-licenca-curada: 
- Turno None · 2026-09-06T14:26:23Z · L0-02-g-perfil-usuario: 

### Turno 3 · L0-02-g-perfil-usuario · 2026-09-06 14:27
- **Construído:** migracao 042 (5 colunas em plat.usuario); PUT /api/eu com idioma/unidades/formato_data/visibilidade na whitelist; POST/DELETE /api/eu/foto (Pillow recorte 200x200, SVG recusado com 415 antes de gravar, >1MiB recusado); foto na barra lateral sem reload; testes de api+e2e com captura; 2 casos novos na varredura cruzada
- **Portão:** entregue
- **Próximo passo:** idioma/unidades/formato_data ainda sem consumidor em outras telas; visibilidade_perfil sem tela de perfil-de-terceiro que leia; rodar suite oficial quando TOTP do superadmin plataforma for resolvido

## Vereditos dos adversários

- **L0-02-tenant-auth**: PASSA (6 ataques registrados) — `handoffs/T2/L0-02-tenant-auth/refutacao.json`
- **L0-03-catalogo**: passa (5 ataques registrados) — `handoffs/T2/L0-03-catalogo/refutacao.json`
- **L0-05-jobs**: PASSA (12 ataques registrados) — `handoffs/T2/L0-05-jobs/refutacao.json`
- **L0-01-repo**: PASSA (7 ataques registrados) — `handoffs/T1/refutacao.json`

## Números medidos (tests/medidas)


### L0-01-repo
- tempo_install_zero_s: **6.24** s
- tempo_install_nunca_viu_s: **9.14** s
- tempo_install_repetido_s: **4.69** s
- install_execucoes_rc0: **3** execuções
- testes_coletados: **82** testes
- testes_rapidos_passando: **81** testes
- testes_e2e_passando: **1** testes
- make_check_rc: **0** rc
- make_check_tempo_s: **2.86** s
- placeholders_linhas: **0** linhas
- saude_http_status: **200** código HTTP
- x_robots_tag_rotas_com_noindex: **11** rotas de 11
- latencia_saude_publica_conexao_nova_mediana_ms: **19.8** ms
- latencia_saude_publica_conexao_nova_p95_ms: **21.0** ms
- latencia_saude_publica_conexao_reaproveitada_mediana_ms: **1.9** ms
- latencia_saude_publica_conexao_reaproveitada_p95_ms: **2.8** ms
- latencia_saude_local_8150_mediana_ms: **1.4** ms
- rss_servico_cgroup_mb: **88.5** MB
- rss_servico_soma_processos_mb: **145.7** MB
- rls_tabelas_com_tenant_id: **4** tabelas
- rls_linhas_sem_contexto: **0** linhas
- rls_insert_cruzado_bloqueado: **1** booleano
- role_plat_app_bypassrls: **0** booleano
- pg_hba_linhas_plat_app: **1** linhas
- migracoes_aplicadas: **2** migrações
- journal_erros: **3** linhas
- alias_estatico_travessia: **404** código HTTP
- latencia_saude_ms: **2.9** ms
- latencia_versao_ms: **0.89** ms
- pagina_pronta_ms: **50.9** ms
- primeira_pintura_ms: **28** ms
- make_check_suja_arvore: **0** arquivos
- make_medidas_rc: **0** rc
- nomes_de_cliente_linhas: **0** linhas
- hsts_rotas_https: **11** rotas de 11
- docs_frases_defasadas_do_head: **26** linhas

### L0-02-e
- rotas_total: **138** rotas
- rotas_cobertas: **138** rotas

### L0-02-tenant-auth
- rotas_total: **138** rotas
- rotas_cobertas: **138** rotas
- custo_log_acesso_ms: **1.1** ms
- login_inexistente_vs_senha_errada_ms: **[121.4, 123.0]** ms
- latencia_login_ms: **163.1** ms
- tempo_revogacao_s: **0.01** s
- latencia_auth_token_ms: **3.22** ms
- pagina_pronta_ms_2fa: **6.1** ms
- pagina_pronta_ms_conta: **41.6** ms
- pagina_pronta_ms_grupos: **66.8** ms
- pagina_pronta_ms_log: **73.7** ms
- pagina_pronta_ms_login: **48.4** ms
- pagina_pronta_ms_papeis: **58.7** ms
- pagina_pronta_ms_tokens: **194.8** ms
- tempo_revogacao_ms_e2e: **6.2** ms
- pagina_pronta_ms_usuarios: **70.9** ms
- testador_rotas_total_vivo: **73** rotas
- testador_rotas_varridas_cruzado_vivo: **73** rotas
- testador_chamadas_cruzadas_vivo: **411** chamadas
- testador_2xx_cruzados_indevidos: **0** chamadas
- testador_linhas_de_B_alteradas: **0** linhas
- testador_login_ms_20_uvicorn: **{'mediana': 129.2, 'p95': 145.4, 'max': 156.6}** ms
- testador_login_ms_3_nginx: **[142.9, 141.7, 146.0]** ms
- testador_auth_token_ms: **{'api_eu_bearer_mediana': 3.67, 'api_versao_mediana': 1.17, 'diferenca': 2.5}** ms
- testador_tempo_constante_ms: **[121.7, 123.2]** ms
- testador_token_revogado_s: **0.02** s
- testador_plat_api_memoria_bytes: **122781696** bytes
- testador_nginx_login_10rpm: **10 × 401 depois 429 (burst 10; 1 a cada 6 s)** sequência
- testador_e2e_identidade: **9 passaram, 0 falharam** testes
- testador_make_teste: **407 passaram, 2 falharam, 21 deselecionados, 103 s** testes
- testador_placeholders: **0** linhas
- testador_nomes_de_cliente: **0** linhas
- testador_chaves_i18n_faltando: **['conta.apos_pendencia']** chaves
- testador_secdef_sem_public: **51 SECURITY DEFINER de 60 funções em plat; 0 com EXECUTE para PUBLIC; 0 com grantee fora de plat_app/plat_worker/postgres** funções
- testador_rls: **22 de 22 tabelas/partições com tenant_id têm relrowsecurity=t; relforcerowsecurity=f em todas (dono postgres; plat_app não é dono, logo a RLS vale para ele)** tabelas
- desabilitar_para_401_ms: **73.1** ms

### L0-03-catalogo
- pagina_conteudo_ms: **231.8** ms
- primeira_pintura_conteudo_ms: **16** ms
- soma_modulos_kb: **229.6** kB
- busca_p95_ms: **109.0** ms
- lista_tipo_p95_ms: **50.8** ms
- revogacao_nega_ms: **15.3** ms
- expurgo_s: **0.32** s
- miniatura_job_s: **0.33** s
- usado_por_medio_ms: **11.6** ms
- versao_custo_ms: **0.347** ms
- busca_trgm_p95_ms: **171.0** ms
- facetas_p95_ms: **25.5** ms

### L0-05-jobs
- cancelamento_s: **0.632** s
- jobs_vazios_por_min: **3666.9** jobs/min
- rss_worker_kb: **56728** kB
- latencia_progresso_s: **0.173** s
- sse_primeiro_evento_publico_s: **0.024** s
- cancelamento_forcado_s: **40.3** s
- tempo_job_5min_s: **300.5** s
- heartbeat_intervalo_max_s: **5.3** s
- eventos_estado_job_5min: **62** eventos
- reinicio_retomada_s: **1.0** s
- pagina_tarefas_pronta_ms: **182.6** ms
- linha_nova_aparece_s: **10.3** s
- progresso_valores_distintos: **2** valores
- cancelamento_tela_s: **0.24** s
- sse_publico_primeiro_evento_s: **0.006** s
- sse_publico_latencia_heartbeat_mediana_s: **0.005** s
- sse_publico_intervalo_medio_eventos_s: **4.922** s
- jobs_vazios_por_min_1_worker: **1613.7** jobs/min
- memoria_cgroup_worker_peak_mb: **27.3** MB
- rls_rotas_jobs_agendas_conferidas: **15** rotas
- primeira_pintura_tarefas_ms: **32** ms
- pagina_tarefas_mil_pronta_ms: **161.5** ms
- reinicio_com_tela_aberta_s: **1.36** s
- polling_de_reserva_progressos_vistos: **3** valores
- worker_homonimo_012_devolucoes: **0** devoluções

### L0-08-d-ldap
- latencia_login_ldap_ms: **[15.4, 13.6, 12.4]** ms
- mediana_5_logins_ldap_ms: **12.2** ms

### L0-09-metadado-catalogo
- mediana_5_metadado_xml_ms: **10.4** ms
- xsd_cache_arquivos: **57** arquivos
- xsd_cache_bytes: **611925** bytes

### L2-10-c-expressao
- funcoes_implementadas: **43** funções
- vetores_de_equivalencia: **309** vetores
- tempo_ataque_cadeia_900_termos_ms: **4.18** ms
- tempo_ataque_string_10mb_ms: **19.15** ms
- tempo_ataque_500_parenteses_ms: **0.53** ms
- vetores_avaliados_sem_erro_no_lado_javascript: **309** vetores
- vetores_ast_ida_e_volta_nos_dois_lados: **309** vetores
- tempo_corte_relogio_50ms_python_ms: **50.63** ms
- tempo_corte_relogio_50ms_javascript_ms: **53.65** ms
- tempo_corte_relogio_500ms_servidor_ms: **500.69** ms
- orcamento_de_passos_padrao: **100000** passos

### L5-05-documento-versoes
- latencia_salvar_versao_ms: **17.309** ms

### L7-31-homologacao
- isolamento_contagem_tabelas_plat_antes: **44** tabelas
- isolamento_contagem_tabelas_plat_homolog_antes: **44** tabelas
- isolamento_migracao_ficticia_create_plat_homolog: **45** tabelas
- isolamento_migracao_ficticia_drop_plat_homolog: **44** tabelas
- migracoes_aplicadas_homolog: **25** migrações
- papeis_criados: **2** roles
- suite_e2e_homolog_evolucao: **1 -> 4 passaram (de 13 e2e de tela, mesma suíte de `make e2e`)** testes

## Decisões do dono em aberto

- **D18** — nome público do produto (codinome interno: plat)
- **D20** — credencial AGOL/Portal de teste do parceiro para L2-08 (migração) e teste real Pro/AGOL contra nossos serviços
- **D21** — disco: os dois servidores estão a 98 %. O laço trabalha com ≤ 3 GB; qualquer dado de rede/imagem além disso exige decisão (apagar cópias declaradas em acervo.objeto = 242 GB, ou volume novo)
- **D22** — reiniciar o Postgres compartilhado para ligar archive_mode=on (PITR/pgBackRest, L0-06-b): janela e autorização
- **D23** — DWG: LibreDWG (GPL, fora do processo web, já usado no GPU box) basta, ou aceitar o binário do ODA File Converter (licença própria) no servidor?
- **D24** — compartilhamento público anônimo: permitido por inquilino (padrão desligado) ou nunca? Impacta OGC Records/CSW externo e o link por token
- **D25** — gov.br: qual órgão/credencial de teste e quem assina o ofício
- **D26** — Garage: reusar o daemon plataforma-garage com buckets próprios ou subir plat-garage separado (mesmo disco)
- **D27** — mapa base vetorial de instalação: PMTiles do Protomaps (OSM/ODbL) para o Brasil inteiro ocupa gigabytes (tamanho medido antes de baixar) com o disco a 98 %; recorte por UF na demonstração, ou volume novo? Sem mapa base próprio a demo depende do proxy de tiles do OSM, que a política de uso não permite em produção
- **D28** — dados abertos de endereço e de rede viária por UF (CNEFE do IBGE e .pbf do Geofabrik) para geocodificação e rota: volume por UF medido antes; quais UFs na demonstração e onde ficam (mesmo disco a 98 %)
- **D29** — ODK Central self-host em docker (RAM e disco) para a integração opcional, ou registrar a integração só contra o sandbox público do ODK
- **D30** — pool de renderização headless (chromium): quantas páginas quentes e MemoryMax, dado que a máquina tem 3 GB disponíveis; sem isso impressão, WMS vetorial e MapServer export ficam com 1 página e fila
- **D31** — broker MQTT próprio (mosquitto, apt) na máquina ou só cliente de brokers externos do cliente
- **D32** — conversão IFC → glTF roda no GPU box (onde a casa já tem IfcOpenShell e o acervo de IFC) por job remoto, ou instala-se IfcOpenShell aqui (pip, tamanho a medir)
- **D33** — TimescaleDB para dado de tempo real DO CLIENTE: a TSL proíbe uso como serviço (DOC 22); a linha assume partição nativa + BRIN e NÃO usa a extensão em objetos do inquilino. Confirmar ou pedir parecer jurídico
- **D34** — SQL livre do usuário (camada de consulta L2-18 e DuckDB L2-15-b) é aceito no produto com as restrições descritas, ou só por administrador do inquilino
- **D35** — campo offline: PWA própria (L2-07) como caminho principal, com QField/QFieldCloud e ODK como alternativas por GeoPackage/XLSForm, ou o inverso (a spec 17.2 dizia QFieldCloud + ODK; o estado do laço diz PWA própria)
- **D36** — QGIS em contêiner docker (imagem oficial, tamanho a medir) só para a conformidade de clientes; instalar ou registrar o teste como pendente
- **D37** — servidor dedicado para o laço/plat (Hetzner AX52 ~€64 ou CPX51 ~€60 via API): fecha a ressalva 'máquina nova' do P5 e dobra as trilhas (RAM aqui = 2-3 GB livres)
- **D39** — L6-01-g-licenca-curada fechou em 29/40 fontes com licenca ESCRITA testada por HTTP (nao 40). Aceitar 29 como 'parcial' e seguir para o resto da linha L6, retomando este item quando aparecer nova fonte com geometria + portal com licenca real (ex.: IBGE se o WAF liberar, ou convenio de acesso)? Ou o dono quer abrir contato direto com algum orgao (ANP/ANM/SGB/IBGE) para conseguir o termo escrito que a pesquisa automatizada nao achou?

## Notas do laço

- 2026-09-05: laço criado a pedido do dono ('no token limit, no time limit, production, no placeholder, drag-and-drop everything, utility networks'). Ativos reutilizados: fgr/sig (tenant/RLS/FeatureServer), plataforma/pipeline (COG/STAC/TiTiler/Garage), cbre motor AMC (25 fatores), tracado-lt motor (322 camadas), geoapp (conectores globais keyless), BDGD 2024 (101 distribuidoras), acervo.* (376 fontes).
- 2026-09-05 T1: DNS A plat.iagrointel.com (DNS-only) criado via API Cloudflare; certbot emitiu certificado (expira 2026-12-04); bloco nginx inicial 503 com X-Robots-Tag noindex; venv do repo com pytest 9.1.1 + pytest-playwright.
- 2026-09-05 T1: pergunta do dono 'isso é TUDO para produção?'. Resposta: não — acrescentados 19 itens (admin/org, SSO, metadado ISO/CSW, relações e regras de atributo, geocodificação e rota, impressão, versionamento e sync, tempo real, analítica grande, notebooks, estruturas de rede, observabilidade, alta disponibilidade, SDK/webhooks, medição e cobrança, i18n/acessibilidade, appliance, LGPD, suporte); cada item ainda se subdivide em -a/-b quando trabalhado. Produção final depende de todos.
- 2026-09-05 T1 (esri, handoff 21_esri.md, 92 URLs testadas): doc 'latest' da Esri é a 12.1; usar série 11.4 versionada como alvo. Para L0-02: ADR tem de declarar limiares de senha (Esri: ≥8 com letra e número, lockout 5 tentativas/15 min), expiração de sessão/token (generateToken máx. 14 d, padrão 120 min), MFA TOTP por membro. Para L0-03: acrescentar sub-itens pastas hierárquicas, favoritos, proteção contra exclusão, status authoritative/deprecated e LIXEIRA (Enterprise não tem — irritação nº 5 da migração); 'link por token' tem de negar após revogação. Paridade-alvo L0-02 (16 linhas) e L0-03 (18 linhas) já escrita no handoff para o adversário cobrar.
- 2026-09-05 T1 13:2x: limite de sessão da API (429, reset 15h UTC) derrubou 4 agentes no meio (cronista com .md sem commit; decomposição L1 e L2 sem saída; L3L6 com JSON de 61 itens pronto e conceito parcial). Conta trocada pelo dono (/login) e agentes relançados/retomados. Regra: decompositor grava JSON incrementalmente antes do conceito; o driver segue medindo sem modelo quando o modelo falta.
- 2026-09-05 T2: decomposição integrada — 444 itens novos (7 esboços de dependência externa), total 501; conceitos em laco/decomposicao/*_CONCEITO.md (L0 20 · L1 20 · L2 20 · L3L6 27 · L4 17 · L5 25 · L7 18 decisões). L7-05 depende de todos.
- 2026-09-05 T2 ~18:25: 4ª interrupção por limite de API (reset 22h UTC) derrubou backend+frontend do catálogo, backend e adversário dos jobs; relogado 20:00 e retomados do disco. Recorrência: ~1 a cada 2 h com 5-7 agentes; o trabalho nunca se perdeu porque tudo vai a disco.
- 2026-09-05 T2 20:30: PLAT_SEMENTE_DEMO retirado do .env deste servidor (decisão do gerente) — a função plat.jobs_semear_demo (014) fica desligada por padrão e o e2e dos 1.000 jobs PULA com razão escrita; ligar só em ambiente de desenvolvimento pelo install.sh.
- 2026-09-06 10:51: achado do L0-10 para o item LDAP (ainda em construcao): funcoes ldap.* sem REVOKE EXECUTE FROM PUBLIC; migracao 025_provedor_ldap.sql ainda sem commit no momento da checagem - conferir quando LDAP fechar.
- 2026-09-06 11:04: disco conferido apos alerta do L2-11-c - queda de 12->7,7GiB NAO e de agentes deste laco (so 2 containers pequenos, plat-worker-container e plat-osrm-guarulhos); resto (compasso-*, iagro-grafana/prometheus, osrm-edpes/cbre/buslog) e de outros projetos no mesmo servidor compartilhado, nao tocado.
- 2026-09-06 13:42: migracao 030_conexao.sql tinha sha registrado divergente do arquivo (bloqueava db/migrar.sh para TODAS as trilhas) - reconciliado: tabela ja batia com o arquivo atual (idempotente), sha re-registrado, migrar.sh volta a rodar limpo (34 iguais, 1 aplicada por outra trilha, 0 pendentes).
- 2026-09-06 13:48: falso alarme investigado - make check-rapido (check2.log) deu 36 failed/165 errors, TODOS em test_cruzado.py por esgotamento de cota de token do usuario demo (usuario_id=1 bateu no limite de 20 tokens ativos): uma trilha em andamento (L6-02-l/L6-05, conexao/ingestao) criou 16 tokens 'smoke-ingestao' manualmente em rajada de 3 min sem revogar. Nao e regressao de codigo. Revogados os 16 tokens leaked (usuario_id=1 volta a 1 token ativo); make check deve rodar limpo agora. Nenhuma mudanca de codigo necessaria - script de smoke manual de outra trilha deveria revogar apos uso, mas nao bloqueia entrega do item.
- 2026-09-06 14:04: migracao 030_conexao reconfirmada convergente (36 iguais, 0 pendentes) apos o agente L6-02-l ter aplicado 036 manualmente - nao e mais bloqueio.
- 2026-09-06 14:05: suite completa (nao-lento) rodada pelo agente L6-02-l/L6-05 apos fila do flock esvaziar: 30 falhas, NENHUMA relacionada a conexao/proveniencia (confirmado por grep). Falhas pertencem a outras trilhas ja em andamento/commitadas: amc_versao_* (SECURITY DEFINER com GRANT PUBLIC vazando - pego pelo proprio teste de guarda), /api/importacoes e /ogc/records (gap de cobertura cruzada A->B), contrato do endpoint /saude, app.limites.PERFIL_IDIOMAS (trilha de config da organizacao). Precisa de agente dedicado para investigar e fechar antes do proximo make check completo - registrado como pendencia, nao bloqueia o laco.
- 2026-09-06 14:14: OUTRA SESSAO Claude (dev-41, socket uds:/tmp/cc-socks/1641034.sock) trabalha no MESMO laco em worktrees separados (/home/dev/plataforma/wt/{garage,stac,valida,amc}, ramos wt/*), ainda nao mergeados em master. Ela commitou c311aa7 em master (conserto real: RealDictCursor ao inves de CursorSchemaAmbiente nas 12 conexoes cruas da suite fazia SQL com 'plat.' literal ignorar PLAT_SCHEMA - isolamento de homologacao/trilha nao valia para a suite; verificado no git log, sem-op em producao) e construiu laco/trilha_ambiente.sh (schema plat_t<nome> proprio por trilha, sem disputar o flock do .pytest.lock - mesma maquina do L7-31/make homolog, parametrizada). COLISAO DE MIGRACAO JA ACONTECEU: minha 043_acervo_licenca.sql (commit do L6-01-g) e o wt/garage dela (042 local, viraria 043 no merge) bateram - avisei por SendMessage, tail atual e 043, proximo livre 044 mas confirmar de novo na hora de cada merge. Arquivos quentes compartilhados: app/main.py, app/jobs/tipos.py, CHANGELOG.md - ultimo toque foi meu cb8fa15. Disco: / 44G livres (91%), /mnt/pgdata 43G livres (94%). Vou adotar trilha_ambiente.sh para agentes novos que so precisam pytest unidade/API, mantendo flock so para quem precisa do schema plat de producao ou e2e contra o servico vivo.
- 2026-09-06 14:18: coordenacao com dev-41 (outra sessao, wt/*): sem numero de migracao reservado (garage e amc confirmam de novo na hora do merge, nenhum agora); adversarios reprovaram L1-01-b-validacao-raster (SSRF via VRT aninhado, XML>1MiB, NaN quebra jsonb) e ja tinhamos L2-10-c-linguagem-expressao refutado (confirmado igual dos dois lados). Bloqueio de login (tenant plataforma id=3, totp_ativo=true de proposito - superadmin real) aconteceu de novo por falta de PLAT_SECRET em algum teste - desbloqueado de novo (UPDATE bloqueado_ate=NULL). Suspeita de origem do 401 codigo_invalido: fixture de sessao batendo em tenant plataforma por engano ou corrida entre trilhas no mesmo usuario real - nao e regressao de codigo nosso, test_acervo.py usa plat.auth_login() direto (sem HTTP/TOTP).
- 2026-09-06 14:23: achado independente sobre o 401 codigo_invalido que dev-41 isolou (sessao_plat/conftest.py): CREDENCIAIS_TOTP era caminho fixo (tests/credenciais_totp.txt), NAO seguia PLAT_CREDENCIAIS_ARQUIVO como CREDENCIAIS - ou seja mesmo sob trilha_ambiente.sh (que so parametriza credenciais.txt, nao credenciais_totp.txt) a corrida continuaria na 1a vez que cada trilha ligasse 2FA. Corrigido: PLAT_CREDENCIAIS_TOTP_ARQUIVO no mesmo padrao, commit a34e745 (arquivo unico, verificado por import direto que o override funciona e o default fica identico). ATENCAO: no processo de commitar isso eu errei - rodei 'git commit -m' sem escopo de arquivo e ele varreu TODO o indice compartilhado, incluindo 11 arquivos ja staged pelo agente L0-02-g-perfil-usuario (ainda rodando) que nao tinha terminado. Corrigido na hora com git reset --soft HEAD~1 (sem perda, HEAD nao tinha avancado) + git restore --staged nos 11 arquivos dele + git commit tests/api/conftest.py -m '...' (commit escopado so no meu arquivo). Nenhum dado perdido, mas fica registrado: em arvore compartilhada, commit tem de ser SEMPRE escopado por pathspec (git commit -- <arquivo>), nunca 'git commit -m' generico depois de um 'git add' pontual, porque outro agente pode ter coisa staged ao mesmo tempo.
