# L6-01-g-licenca-curada — handoff (papéis pesquisador + dados + adversário, T3, 06/09/2026)

## Objetivo

Preencher `plat.acervo_licenca` (fonte_id → tipo de licença em vocabulário fechado, URL testada por HTTP,
data, evidência) para ≥ 40 fontes do acervo com **geometria** (`plat.acervo_camada`, item L6-01-a-registro,
ENTREGUE) e **licença ESCRITA na origem** (regra D17: "dado público sem licença escrita" não conta — a URL
tem de mostrar o termo de verdade, não uma suposição).

## O que fiz

1. **Levantei o universo**: 192 fontes têm geometria em `plat.acervo_camada`. Cruzei com
   `acervo.fonte.licenca` (68 têm texto não vazio; só ~15 nomeiam uma licença de verdade, o resto é "dado
   público (licença não declarada na fonte)" — confirma o número já registrado no CLAUDE.md/estado.json).
2. **Pesquisei ao vivo, organização por organização** (não confiei em nenhuma nota antiga sem reconferir):
   ANEEL, ANA, EPE, FUNAI, IBAMA, INPE, MapBiomas, OpenStreetMap/OSRM, Prefeitura de São Paulo — todas com
   URL/endpoint que **mostra** o termo, testado por HTTP no momento da pesquisa. Métodos usados, em ordem de
   confiabilidade:
   - **Portal CKAN da própria fonte** (`.../api/3/action/package_show?id=<slug>`): ANEEL
     (`dadosabertos.aneel.gov.br`, ODbL confirmado em 5/5 pacotes amostrados), IBAMA
     (`dadosabertos.ibama.gov.br`, license_id varia por dataset: `other-open`/`other-pd` →
     `dado-aberto-com-termo-do-orgao`, um dataset específico é `cc-by`), Prefeitura de SP
     (`dados.prefeitura.sp.gov.br`, `cc-zero` confirmado).
   - **Feed DCAT** (`.../data.json`, convenção ArcGIS Hub): ANA (`dadosabertos.ana.gov.br/data.json`) — só as
     camadas BHO (Base Hidrográfica Ottocodificada) têm o campo `license` preenchido com texto próprio
     ("É permitida a reprodução de dados e de informações, desde que citada a fonte"); as outras 7 fontes ANA
     com geometria (atlas de inundações, atlas de esgotos, massas d'água, outorgas...) NÃO têm esse campo
     preenchido no feed — ficaram de fora.
   - **Texto explícito na própria página** (`html_regex`, string exigida no corpo da resposta): EPE
     (rodapé próprio do site, "Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)" — não é o template
     gov.br), FUNAI (parágrafo específico sobre "geoprocessamento e mapas" na página que já é `fonte.url` no
     acervo), INPE (página dedicada `citacoes-e-licenca-de-uso/` do TerraBrasilis, CC BY-SA 4.0), MapBiomas
     (rodapé do site, CC BY 4.0), OpenStreetMap/OSRM (`openstreetmap.org/copyright`, ODbL).
3. **Testei e DESCARTEI** ~20 outras organizações candidatas (a hipótese do item cita IBGE, Copernicus,
   ICMBio/INDE, ANM, INCRA como candidatas) — nenhuma passou no critério "a URL mostra o termo":
   - **IBGE**: `www.ibge.gov.br` bloqueia todo acesso não-navegador com HTTP 403 (WAF/Cloudflare — testado com
     `httpx` e `curl` com UA de browser completo, mesmo resultado); `ftp.ibge.gov.br` só diz "todos os
     arquivos aqui disponíveis são públicos", que a própria casa já classifica como não-declarado (mesma nota
     em `acervo.fonte.licenca` para `ibge-favelas-e-comunidades-urbanas`) — não é um termo de uso, é uma
     afirmação de que o arquivo é acessível.
   - **ANP, ANM, SGB/CPRM, ICMBio, INCRA, IPHAN, DECEA, CONAB, DNIT, INMET, ONS, CEMADEN, Embrapa**: sem
     portal CKAN/DCAT vivo encontrado (`dadosabertos.<órgão>.gov.br` inexistente ou timeout/DNS); WFS
     GetCapabilities testado (ANP `geomaps.anp.gov.br`) com `ows:AccessConstraints`/`ows:Fees` = `NONE`
     (mesmo padrão já visto pela casa em Guarulhos); ArcGIS REST `copyrightText` testado (IAT-PR) e veio
     vazio. Único texto encontrado nessas páginas é o **rodapé genérico do template `gov.br`** ("Todo o
     conteúdo deste site está publicado sob a licença Creative Commons Atribuição-SemDerivações 3.0 Não
     Adaptada") — **decidido não contar como licença de DADO**: é o mesmo texto idêntico em dezenas de
     domínios `.gov.br` diferentes, cobre o conteúdo EDITORIAL do site (texto, imagens), e "SemDerivações"
     contradiz a própria noção de dado aberto reutilizável — usar esse texto para dado geográfico seria
     "procedência errada", que a casa já registrou no CLAUDE.md como pior do que nenhuma procedência.
   - **Estados ambientais** com WFS/FeatureServer (IAT-PR, IMASUL-MS, IDEMA-RN, SUDEMA-PB, SEMAD-GO, SEMA-RS,
     SEMA-MT, IPAAM-AM, INEA-RJ, IMA-SC, NATURATINS-TO, SERHMA-SE, SEDAM-RO, SEMA/IMAC-AC, SEMAD/FEAM-MG,
     SEDURBS-SE): testados portais `dados.<uf>.gov.br` (funcionam para GO/RS/ES/SC/PB/RO/AC) mas nenhum tem
     dataset correspondente à camada ambiental específica do acervo (autos de infração, embargos —
     tipicamente não publicados no portal de transparência geral do estado).
   - **SICAR**: termo de uso carregado por JavaScript (SPA), não aparece no HTML estático — mantém
     `nao-declarada`, como já registrado.
4. **Achado incidental**: `acervo.fonte.licenca` tem "MapBiomas: CC BY-SA 4.0 (conforme site do projeto)" —
   mas o texto AO VIVO do rodapé do site (06/09/2026) diz **CC BY 4.0**, não CC-BY-SA. Usei o valor ao vivo
   (é o que o script testa agora) e registrei a discrepância aqui e em `decisoes_do_dono` — pode ser mudança
   recente do MapBiomas ou imprecisão da nota antiga; não corrigi `acervo.fonte.licenca` (schema de outro
   projeto, só leitura).
5. **Migração 043** (`db/migracoes/043_acervo_licenca.sql`): cria `plat.acervo_licenca` com vocabulário
   fechado via `CHECK` (CC0, CC-BY, CC-BY-SA, ODbL, dado-aberto-com-termo-do-orgao, Copernicus,
   licenca-propria, nao-declarada), FK para `acervo.fonte`, colunas obrigatórias não vazias (`url_licenca`,
   `metodo`, `evidencia`, `confianca`) e `http_status`. `plat_app` só lê (mesmo padrão de
   `plat.acervo_camada`/`plat.acervo_lgpd`); quem escreve é o script, como `postgres`.
6. **Script** `scripts/acervo_licenca_sync.py`: 29 entradas de curadoria (fonte_id, tipo esperado, URL,
   método, confiança); cada rodada faz o GET/chamada de API DE VERDADE, confere o termo/`license_id`
   esperado, extrai um recorte literal da resposta como evidência, e só então grava (UPSERT idempotente).
   Se a rede falhar ou o termo sumir, a linha NÃO é gravada/atualizada e o script termina com código 1 —
   nunca inventa.
7. **Rodei o script** como `postgres`: **29/29 verificações passaram** na hora (todas HTTP 200, todos os
   termos encontrados). Rodei de novo para confirmar idempotência (mesmo resultado, sem duplicata — PK
   `fonte_id`).
8. **Testes** (`tests/api/test_acervo_licenca.py`): idempotência do script; nenhuma linha sem URL testada/
   HTTP 200/evidência; tipo sempre no vocabulário fechado (nunca `nao-declarada` gravado); toda fonte
   registrada tem geometria em `plat.acervo_camada`; **reexecução literal dos GETs** (função separada,
   independente do script, refaz cada URL agora e exige 200 — é o teste que o portão pede) — marcada
   `@pytest.mark.lento` (roda em `make e2e`/`make check`, fora do `make teste` rápido do driver, mesmo
   critério de "medição demorada" já usado em outros itens); e um teste `xfail` (não escondido) para o
   portão literal `>= 40`, que hoje falha honestamente em 29 — ver "Portão" abaixo.
9. **Papel adversário** (eu mesmo, contexto separado da curadoria): reabri **10 das 29 URLs por `curl`
   independente** do script (sem reusar nenhum código já escrito) e confirmei manualmente que a página/API
   realmente diz o que a tabela diz — **10/10 confirmadas** (um falso-alarme inicial em `epe.gov.br`, porque
   o primeiro `curl` não seguia o redirect 301 — corrigido com `-L`, ver Evidência).

## Evidência (saída literal)

Rodada real do script, como `postgres`:

```
$ sudo -u postgres python3 scripts/acervo_licenca_sync.py --banco iagro_sat
[acervo_licenca_sync] ok aneel: tipo=ODbL http=200
[acervo_licenca_sync] ok aneel-bdgd: tipo=ODbL http=200
[acervo_licenca_sync] ok aneel-sigel: tipo=ODbL http=200
[acervo_licenca_sync] ok aneel-sigel-linhas-de-transmissao: tipo=ODbL http=200
[acervo_licenca_sync] ok ana-base-hidrografica-ottocodificada-bho: tipo=licenca-propria http=200
[acervo_licenca_sync] ok ana-bho-base-hidrografica-ottocodificada: tipo=licenca-propria http=200
[acervo_licenca_sync] ok epe-blocos-de-e-p: tipo=CC-BY http=200
[acervo_licenca_sync] ok epe-eolica-offshore: tipo=CC-BY http=200
[acervo_licenca_sync] ok epe-gasodutos-planejados: tipo=CC-BY http=200
[acervo_licenca_sync] ok epe-linhas-de-transmissao-planejadas: tipo=CC-BY http=200
[acervo_licenca_sync] ok epe-polos-de-gas: tipo=CC-BY http=200
[acervo_licenca_sync] ok epe-subestacoes-planejadas: tipo=CC-BY http=200
[acervo_licenca_sync] ok funai: tipo=licenca-propria http=200
[acervo_licenca_sync] ok funai-terras-indigenas: tipo=licenca-propria http=200
[acervo_licenca_sync] ok ibama-autorizacoes-de-supressao-asv-federal: tipo=CC-BY http=200
[acervo_licenca_sync] ok ibama-autos-de-infracao: tipo=dado-aberto-com-termo-do-orgao http=200
[acervo_licenca_sync] ok ibama-dados-abertos: tipo=dado-aberto-com-termo-do-orgao http=200
[acervo_licenca_sync] ok ibama-dof-documento-de-origem-florestal: tipo=dado-aberto-com-termo-do-orgao http=200
[acervo_licenca_sync] ok ibama-sinaflor-autorizacoes-de-exploracao-supressao: tipo=dado-aberto-com-termo-do-orgao http=200
[acervo_licenca_sync] ok ibama-termos-de-embargo-adipe-consulta-publica: tipo=dado-aberto-com-termo-do-orgao http=200
[acervo_licenca_sync] ok inpe-deter-alertas-amazonia-cerrado: tipo=CC-BY-SA http=200
[acervo_licenca_sync] ok inpe-prodes-desmatamento-6-biomas: tipo=CC-BY-SA http=200
[acervo_licenca_sync] ok mapbiomas: tipo=CC-BY http=200
[acervo_licenca_sync] ok mapbiomas-alerta-alertas-validados: tipo=CC-BY http=200
[acervo_licenca_sync] ok mapbiomas-colecoes-de-uso-e-cobertura-do-solo: tipo=CC-BY http=200
[acervo_licenca_sync] ok openstreetmap: tipo=ODbL http=200
[acervo_licenca_sync] ok osm: tipo=ODbL http=200
[acervo_licenca_sync] ok osrm-local: tipo=ODbL http=200
[acervo_licenca_sync] ok prefeitura-de-sao-paulo-2: tipo=CC0 http=200
[acervo_licenca_sync] total=29 ok=29 falha=0
```

Contagem no banco (`psql`):

```
 tipo                           | count
--------------------------------+-------
 CC-BY                          |    10
 ODbL                           |     7
 dado-aberto-com-termo-do-orgao |     5
 licenca-propria                |     4
 CC-BY-SA                       |     2
 CC0                            |     1
(6 rows)

 total | com_tipo
-------+----------
    29 |       29
```

Amostra adversária (10/29), `curl` independente do script, feito depois de rodar o sync:

```
$ curl -sL "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id=base-de-dados-geografica-da-distribuidora-bdgd" | python3 -c "...json..."
license_id: odc-odbl | title: Open Data Commons Open Database License (ODbL)

$ curl -s "https://dadosabertos.ana.gov.br/data.json" | python3 -c "...busca 'ottocodificada'..."
Base Hidrográfica Ottocodificada 2017 - bacias nível 2 -> É permitida a reprodução de...

$ curl -s "https://www.epe.gov.br/"    # SEM -L: 301, corpo vazio -> falso alarme
$ curl -sL "https://www.epe.gov.br/" | grep -o "Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)"
Creative Commons Atribuição 4.0 Internacional (CC BY 4.0)     # com -L: confirmado

$ curl -sL ".../geoprocessamento-e-mapas" | grep -o "Licença de uso: ..."
Licença de uso: o conteúdo dos arquivos correspondentes a geoprocessamento e mapas poderão ser
reproduzidos desde que citada a fonte

$ curl -sL "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=fiscalizacao-auto-de-infracao"
license_id: other-open | title: Outra (Aberta)

$ curl -sL "https://terrabrasilis.dpi.inpe.br/citacoes-e-licenca-de-uso/" | grep -o "creativecommons.org/licenses/by-sa/4.0"
creativecommons.org/licenses/by-sa/4.0

$ curl -sL "https://brasil.mapbiomas.org/" | grep -o "CC BY 4.0"
CC BY 4.0

$ curl -sL "https://www.openstreetmap.org/copyright" | grep -o "Open Data Commons Open Database License"
Open Data Commons Open Database License

$ curl -sL -A "Mozilla/5.0" "https://dados.prefeitura.sp.gov.br/api/3/action/package_show?id=favelas"
license_id cc-zero, license_title "Creative Commons CCZero"   # sem UA de navegador: bloqueado (385 bytes)

$ curl -sL "https://dadosabertos.ibama.gov.br/api/3/action/package_show?id=supressao-de-vegetacao-nao-florestal-no-bioma-amazonia"
license_id: cc-by | title: Creative Commons Attribution
```

10/10 confirmadas — a única surpresa foi que `dados.prefeitura.sp.gov.br` bloqueia requisição sem
User-Agent de navegador (o script de produção já usa um UA identificável, então não é afetado).

Lint e marcadores de placeholder:

```
$ venv/bin/ruff check scripts/acervo_licenca_sync.py tests/api/test_acervo_licenca.py
All checks passed!
$ grep -E -f tests/marcadores.regex scripts/acervo_licenca_sync.py db/migracoes/043_acervo_licenca.sql tests/api/test_acervo_licenca.py
(sem saída — nenhum marcador de placeholder)
```

Migração aplicada (`bash db/migrar.sh`):

```
aplicada   043_acervo_licenca (1941 ms)
migracoes: aplicadas 1 · reaplicadas 0 · iguais 36 · pendentes 0
```

## Riscos

- **Correspondência por nome, não por link direto tabela→dataset**, em vários casos (todos os `ckan_package_show`
  e o `dcat_data_json`): a curadoria escolheu o pacote CKAN/dataset DCAT mais plausível pelo **nome do
  assunto**, não por um vínculo técnico gravado no acervo (o próprio acervo não guarda esse vínculo — mesma
  limitação que a 1ª mineração de URL da casa já enfrentou e documentou no CLAUDE.md: "a 1ª mineração de URL
  foi REPROVADA... SIGEF apontando para GeoServer de prefeitura"). Mitigado com: (a) o host do portal bate
  com o órgão da fonte (regra `confirma.py` da casa), (b) quando várias amostras do MESMO portal têm a MESMA
  licença (ANEEL: 5/5 amostras = ODbL; a maioria do IBAMA = other-open/other-pd), o risco de errar o TIPO é
  baixo mesmo que o dataset exato não seja o certo; (c) cada linha grava `confianca` com a limitação
  explícita, nunca escondida.
- **Ambiguidade ASV-federal × SINAFLOR** (dois fonte_id de supressão de vegetação do IBAMA podem, na
  verdade, ser a MESMA tabela ou tabelas sobrepostas no acervo) — mapeados para dois pacotes CKAN diferentes
  (`cc-by` vs `other-open`) por interpretação de nome; se forem a mesma tabela, um dos dois tipos está
  errado. Não consegui confirmar sem acesso à definição exata da tabela por trás de cada fonte_id (fora do
  escopo deste item — isso é `plat.acervo_camada`, L6-01-a, já entregue).
- **MapBiomas CC-BY vs CC-BY-SA**: usei o valor ao vivo (CC BY 4.0); a nota antiga do acervo diz CC-BY-SA.
  Registrado em D39; não corrigi `acervo.fonte.licenca` (só leitura).
- **Teste `test_reexecuta_todos_os_gets_registrados` depende de rede e de 29 serviços de terceiros
  ficarem no ar** — se um órgão mudar a página/API amanhã, o teste falha honestamente (é o comportamento
  esperado: "erro nunca é sucesso"; a rodada seguinte do script também vai falhar naquela linha, sem gravar
  nada errado por cima).
- **Suíte inteira (`tests/api/`) estava com o inquilino `demo`/`plataforma` BLOQUEADO por lockout de login**
  durante a validação (HTTP 423, desbloqueio às 14:31:13Z) — contenção de outra sessão rodando a suíte em
  paralelo no mesmo ambiente compartilhado, não causada por este item (reproduzido também com
  `test_acervo_camada.py`, item já ENTREGUE, sem tocar neste código). Ver seção "Pendências" para o retest
  agendado.

## Pendências

- **Portão literal (`>= 40`) NÃO fechado**: 29/40. `test_portao_quantidade_minima` fica `xfail` (visível em
  `pytest -rx`, não escondido) até uma de duas coisas acontecer: (a) aparecer fonte nova com geometria +
  portal com licença real (ex.: se o WAF do IBGE liberar, ou a casa registrar convênio de acesso), ou (b) o
  dono decidir outra rota (contato direto com órgão, aceitar 29 como suficiente para este item, etc.) —
  aberto em `decisoes_do_dono` **D39**.
- **Suíte `tests/api/` (via `pytest`/FastAPI TestClient) não pôde ser validada ponta a ponta nesta janela**:
  o autouse `limpeza_de_residuos` (session-scoped, `tests/api/conftest.py`) força login real + 2FA contra o
  inquilino de demonstração para QUALQUER teste coletado em `tests/api/`, mesmo os que (como os meus) só
  usam `conexao_plat_app`. Tentei duas vezes (14:20Z e 14:31Z UTC) — a primeira encontrou o inquilino
  bloqueado até 14:31:13Z, a segunda (já depois desse horário) encontrou um NOVO bloqueio até 14:39:13Z,
  confirmando que outra sessão está fazendo login concorrente NESTE MOMENTO (não é um bloqueio velho, é
  ativo). **Reproduzi o MESMO erro em `tests/api/test_acervo_camada.py`** (item já `entregue`, código que eu
  não toquei) para confirmar que não é bug meu — é contenção do ambiente compartilhado descrita no meu
  próprio briefing. Não fiquei martelando o login (pioraria a contenção para as outras trilhas); em vez
  disso, **validei os MESMOS invariantes que os testes de estrutura/vocabulário/geometria cobrem, direto por
  `psycopg2` contra `PLAT_DSN`** (sem TestClient/login), com saída limpa:
  ```
  linhas invalidas (deve ser vazio): []
  tipos: {'CC-BY-SA', 'dado-aberto-com-termo-do-orgao', 'CC0', 'licenca-propria', 'ODbL', 'CC-BY'} | subset do vocabulario: True | sem nao-declarada: True
  sem geometria (deve ser vazio): []
  total com tipo confirmado: 29 (portao pede >=40)
  ```
  e reexecutei o script mais uma vez (3ª rodada) confirmando idempotência: `total=29 ok=29 falha=0`.
  `venv/bin/ruff check` e a varredura de marcadores de placeholder já passam limpos (ver Evidência).
  **Falta**: rodar `tests/api/test_acervo_licenca.py` de ponta a ponta com login funcionando (fora da janela
  de contenção) e anexar a saída aqui — o próximo papel/turno que pegar este item (ou eu mesmo, se retomado)
  deve rodar `flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/api/test_acervo_licenca.py`
  com `PLAT_SECRET`/`PLAT_DSN_WORKER` exportados (`make teste`/`make check` já fazem isso) numa janela sem
  outra sessão batendo login ao mesmo tempo.
- Estado do item em `estado.json`: `parcial` (mecanismo funciona ponta a ponta, verificado por fora do
  TestClient; cláusula de quantidade pendente, nomeada; suíte via TestClient pendente de retest sem
  contenção).
