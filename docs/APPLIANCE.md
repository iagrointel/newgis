# Appliance sem internet — o que funciona, o que não, e a mensagem exata (item L7-11-b-appliance-sem-internet)

Modelo: "configure a disconnected deployment" do Portal (L7_CONCEITO C13: sem telefonar para casa, licença em
arquivo, mapa-base local). Regra: depois de instalado, a plataforma **não pede nada fora da instalação**. O que
depende de rede externa não quebra: avisa, com a mensagem abaixo, e o resto da tela segue.

## 1. O que a tela nunca busca fora (provado)

| recurso | de onde vem no appliance | prova |
|---|---|---|
| bibliotecas (MapLibre GL 4.7.1, PMTiles 4.5.0, DOMPurify 3.4.14, Swagger UI 5.32.15) | `web/vendor/`, sha256 em `VERSOES.txt`, servidas em `/static/vendor/` | `tests/unit/test_appliance_sem_cdn.py`, `make vendor` |
| fontes de letra (IBM Plex Sans/Mono, Big Shoulders Display) | `web/vendor/*.woff2` | `tests/unit/test_appliance_sem_cdn.py` |
| mapa-base | PMTiles local `web/dados/basemap/*.pmtiles` lido por Range HTTP do próprio nginx/API (item L2-01-a) | `tests/e2e/test_mapa.py` atrás do proxy de captura |
| documentação da API (`/api/docs`) | Swagger UI local, `validatorUrl: null` (sem validador externo) | `tests/api/test_docs.py` |
| `/api/openapi.json`, i18n, ícones, CSS | arquivos do repositório | e2e inteiro atrás do proxy |

Prova dinâmica: `scripts/appliance_offline_medir.py --base-url <instalação>` roda a suíte e2e inteira com o
navegador atrás de `tests/operacao/proxy_captura.py`, que repassa só o host da instalação e recusa (502) e conta
qualquer outro. Resultado em `tests/medidas/L7-11-b-appliance-sem-internet.json`: `pedidos_a_host_externo`
tem de ser 0 e `hosts_externos_vistos` vazio.

## 2. O que NÃO funciona sem internet (e como a tela avisa)

Nada disto derruba a página; cada um vira uma marca ou um aviso no lugar do dado.

| função | comportamento offline | mensagem exata na tela |
|---|---|---|
| conexão externa (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC de terceiro) — "testar agora" em `/conexoes` | o teste de saúde falha na resolução de nome antes de qualquer conexão; a conexão fica com estado **fora** | linha da conexão: marcador `fora`; no histórico: mensagem `url_insegura:dns_falhou` (ou `url_insegura:dns_timeout`, `tempo_esgotado`, `erro_de_conexao:ConnectError`) — nunca 500 |
| criar conexão externa (`POST /api/conexoes`) com host que não resolve | recusada na entrada | `URL recusada: dns_falhou` (erro `url_insegura`, HTTP 422) — a tela mostra `não foi possível ... : URL recusada: dns_falhou` |
| publicar camada de conexão externa | publica com a ficha de procedência "não registrado" no que o serviço não respondeu | na ficha: `<url>: o serviço não respondeu (ou respondeu vazio) no momento da publicação`; campos `não registrado` |
| descoberta por catálogo CSW (`/conexoes`, "descobrir por catálogo") | 502 nomeado, sem conexão criada | `o catálogo não respondeu de forma utilizável: url_insegura:dns_falhou` |
| catálogo de conectores públicos (`/conexoes`, "conectores públicos prontos") | o reteste semanal marca tudo **fora do ar**; a lista viva fica vazia | `nenhum conector vivo com esse filtro`; seção "fora do ar" com motivo `url_insegura:dns_falhou` por entrada |
| imagens de satélite por conector keyless (Sentinel-2/Landsat via STAC de terceiro, linha L1) | não disponível | ficha do conector: `a fonte pode sumir; última verificação em <data>` e estado `fora` (L1 C12) |
| geocodificação | funciona: CNEFE do IBGE instalado por UF (L2-11-b), nada externo | — |
| rota/isócrona | funciona se o OSRM da instalação (`plat-osrm-*`, recorte local) estiver de pé; OSRM parado: | erro `osrm_erro`: `OSRM devolveu HTTP <código>` (a tela mostra a mensagem, o mapa segue) |
| e-mail (convite, redefinição) | sem SMTP alcançável cai no caminho manual | `SMTP não configurado neste inquilino nem na instalação` ou `não conectou a <host>:<porta> (código <n>)`; a senha temporária é mostrada ao administrador e o convite tem o link para copiar |
| certificado TLS público (certbot) | não renova; usar a CA interna do cliente (§3) | — |
| atualização de versão | por pacote assinado copiado à mão (L7-16), nunca por rede | — |

## 3. CA interna do cliente

O nginx do appliance recebe certificado e chave da CA do cliente em `/etc/plat/tls/` (`fullchain.pem`,
`privkey.pem`); os serviços internos (API, worker, TiTiler, Martin, Garage) falam entre si por HTTP na rede
interna do compose e não precisam de certificado. Para que o próprio backend aceite a CA do cliente ao chamar
um serviço HTTPS DENTRO da rede do cliente (WMS interno, ArcGIS Server interno), exporte `SSL_CERT_FILE` com o
`ca.pem` do cliente no ambiente das unidades `plat-api`/`plat-worker` (o `httpx` da casa lê a variável).

## 4. Rede docker `--internal` (perfil `appliance` do compose)

O compose do item L7-01-a (`deploy/compose/docker-compose.yml`, perfil `appliance`) coloca db, garage, martin,
titiler, api, worker e nginx numa rede `interna`; para a prova "sem saída" a rede é criada com
`docker network create --internal`. **Não executado nesta máquina**: as cinco imagens do perfil appliance
ficaram pendentes por disco (95-96 % no L7-01-a; 94 % hoje, D21) — a prova aqui é a mesma suíte e2e contra
uma instalação em processo, atrás do proxy de captura, que é onde se vê se o NAVEGADOR tenta sair. O que o
BACKEND tenta sair (conectores) é recusado por `app/conexao/seguranca.py` antes de abrir conexão quando o nome
não resolve, e vira as mensagens da seção 2.

## 5. Telemetria: desligada por padrão, opt-in do superadmin (item L7-11-c)

`GET /api/telemetria` (superadmin) mostra o estado e a **prévia** — o JSON exatamente como sairá; `PUT
/api/telemetria {"ligada": true, "nome_instalacao": "..."}` liga; `POST /api/telemetria/enviar` manda agora; o
periódico `telemetria.enviar` manda uma vez por dia (04:30) enquanto ligada. Desligada, o job devolve
`telemetria desligada: nenhum pedido de rede` sem abrir conexão (provado por `tests/api/test_telemetria.py`,
que conta as chamadas HTTP: 0). Destino = `PLAT_TELEMETRIA_URL` do `.env` (vazio = nada sai, e o estado diz
`sem_destino_configurado`). Chave própria por appliance (`plat.telemetria.chave`, gerada na migração), enviada
no cabeçalho `X-Plat-Chave`. O JSON enviado fica em `ultimo_relatorio` e é byte a byte o que a prévia mostrou
(teste compara).

Campos, e nada além deles (`app/telemetria.py::CAMPOS`; o teste reprova chave a mais):

| campo | conteúdo |
|---|---|
| `esquema` | versão do formato (1) |
| `chave` | identidade do appliance (hex gerado, sem significado) |
| `nome_instalacao` | texto escolhido pelo superadmin ao ligar (ou nulo) |
| `enviado_em` | instante UTC |
| `versao`, `git_sha`, `ambiente` | versão do produto |
| `banco`, `migracoes_aplicadas`, `migracoes_pendentes` | saúde do banco |
| `servicos` | estado de cada serviço da instalação (`ok`/`erro`/`ausente`, o mesmo de `/saude`) |
| `fila` | `pendentes`, `rodando`, `workers_vivos` |
| `contagens` | `inquilinos`, `usuarios`, `itens`, `camadas`, `jobs_24h`, `gb_arquivos` — só números agregados |

Nunca: nome de inquilino, login, e-mail, título de item, geometria, coordenada, endereço, IP, conteúdo.

Receptor (na instalação da casa): `POST /api/telemetria/receber` aceita só chave registrada pelo superadmin em
`POST /api/telemetria/appliances` (`403 chave_desconhecida` para o resto, nada gravado; `422
relatorio_fora_do_contrato` se vier campo a mais); `GET /api/telemetria/appliances` alimenta o painel de suporte.
