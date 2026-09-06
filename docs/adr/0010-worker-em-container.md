# ADR 0010 — Worker da fila em contêiner (item L0-05-e-worker-em-container)

Estado: aceito (arquiteto+backend, turno T3, setembro de 2026). Continuação do ADR 0003 (fila de jobs, worker
`plat-worker`, executor por processo filho com fork() + `RLIMIT_DATA` + `PR_SET_PDEATHSIG`). Este item NÃO
muda o protocolo da fila: registra um SEGUNDO executor possível, em contêiner Docker, ao lado da unidade
systemd — o mesmo pai, os mesmos filhos, o mesmo `plat.job` no banco. Nasceu de L2-16-b/c (execução de job
dentro de contêiner com limites de CPU/RAM/disco/rede e token do usuário injetado): antes de qualquer item
depender disso, o executor alternativo tinha de existir e provar que funciona.

## 1. O que muda e o que não muda

**Não muda**: o esquema `plat.job`/`plat.job_log`/`plat.worker`, as funções `SECURITY DEFINER`, o protocolo
fork-por-job, `RLIMIT_DATA` (não `RLIMIT_AS`), o contrato de saída pelo pipe, o registro de tipos por
decorador. Um job criado pela API não sabe nem precisa saber se vai ser pego pela unidade systemd ou pelo
contêiner — `job_pegar` com `FOR UPDATE SKIP LOCKED` já resolve dois workers concorrentes apontando para o
mesmo banco (ADR 0003 seção 4.4); só é preciso `PLAT_WORKER_NOME` e porta de saúde distintos.

**Muda**: dois arquivos de deploy novos (`deploy/Dockerfile.worker`, `deploy/docker-compose.worker.yml`), um
entrypoint (`deploy/entrypoint-worker.sh`), e — o que só apareceu ao testar de verdade, não estava previsto no
pedido — uma correção em `app/jobs/filho.py`/`app/jobs/worker.py` para um bug que só existe dentro de
contêiner (seção 4).

## 2. Imagem: `python:3.12-slim-bookworm`, sem `--system-site-packages`

A venv do HOST usa `--system-site-packages` para reaproveitar pacotes dpkg (`python3-psycopg2`,
`python3-gdal`, `python3-cryptography`, `python3-magic`) porque o Python de sistema do host é 3.12 (Ubuntu
24.04), a MESMA versão da venv. `python:3.12-slim` é Debian bookworm, cujo Python de sistema é 3.11; um
binding apt compilado para 3.11 não carrega numa venv 3.12. Por isso a imagem NÃO usa
`--system-site-packages`: todas as dependências Python entram via pip, versão fixada, dentro da própria venv.
Ficam de fora do pip e entram por `apt-get` só o que o worker chama como BINÁRIO ou biblioteca C:

| pacote apt | por quê |
|---|---|
| `gdal-bin` | `ogr2ogr`/`ogrinfo` chamados por subprocesso (ADR 0003 seção 4.3, ADR 0005); nenhuma tarefa registrada hoje importa o binding Python do GDAL (`grep -rn "ferramentas=" app/` confere) |
| `libmagic1` | biblioteca C que o pacote pip `python-magic` carrega via `ctypes.CDLL`; sem ela o import não quebra, a chamada em runtime sim |
| `ca-certificates` | requisições HTTPS de subprocessos/bibliotecas que validam certificado |

### 2.1 Achado da containerização: duas dependências Python nunca declaradas

`python -m app.jobs.worker` importa todos os tipos de job na partida (`app.jobs.tipos` → `app.catalogo.tarefas`
→ `app.catalogo.{tipos,miniatura}`). Isolado do host (venv nova, só `requirements.txt`, sem
`--system-site-packages`), o import falha em `jsonschema` (`app/catalogo/tipos.py`) e depois em `PIL`/Pillow
(`app/catalogo/miniatura.py`) — **nenhuma das duas está em `requirements.txt` nem em `deploy/pacotes_apt.txt`**.
No host, a única razão de funcionar é uma instalação pip GLOBAL de outro produto da máquina (fora de dpkg, fora
desta venv, em `/usr/local/lib/python3.12/dist-packages` e `/home/dev/.local`) que por acaso deixa as duas
alcançáveis via `--system-site-packages`. Reproduzir esse acaso dentro do contêiner violaria o portão P5
(reprodutível): a imagem trava as duas como dependência de primeira classe, na versão medida no host em
06/09/2026 (`jsonschema==4.26.0`, `Pillow==12.2.0`). `psycopg2-binary`, `cryptography` e `python-magic` (sem
equivalente dpkg utilizável nesta base, seção 2) entram na versão mais recente que o pip resolveu no dia da
construção, medida e travada no Dockerfile: `psycopg2-binary==2.9.12`, `cryptography==50.0.1`,
`python-magic==0.4.27`. **O CONSERTO do `requirements.txt` do host (declarar `jsonschema`/`Pillow` lá também,
para não depender do acaso) fica para o item dono de `app/catalogo` — fora do escopo deste item, e outras duas
trilhas já mexiam em `requirements.txt`/`app/settings.py` quando este rodou (risco de colisão real, não
hipotético: aconteceu neste mesmo turno).**

Contexto de build: `.dockerignore` na raiz é uma LISTA DE PERMISSÃO (`*` seguido de `!app`, `!app/**`,
`!requirements.txt`, `!VERSAO`, `!deploy`, `!deploy/entrypoint-worker.sh`), não uma lista de exclusão. Motivo
medido: uma trilha concorrente (`osrm/`) deixou um arquivo dono `root`, modo 700, no diretório raiz do
repositório durante este mesmo turno — o daemon Docker não conseguia nem LER o arquivo para decidir se
ignorava, e o build falhava com "no permission to read from". Uma lista de exclusão quebra a cada diretório
novo e alheio; a lista de permissão é imune a isso.

## 3. Rede: `network_mode: host`

Medido 06/09/2026: `postgresql.conf` tem `listen_addresses = '127.0.0.1'`; `pg_hba.conf` só tem linha para
`plat_app`/`plat_worker` em `127.0.0.1/32`; o `.env` do repositório usa esses mesmos endereços (`PLAT_DSN`,
`PLAT_GARAGE_URL=http://127.0.0.1:3900`). Um contêiner numa rede em ponte chegaria de outro IP (o gateway da
ponte, ex. `172.17.0.1`) — a conexão TCP nem chegaria a autenticar. Abrir esse caminho exigiria mudar
`listen_addresses`/`pg_hba.conf` de um Postgres compartilhado por ~20 bancos de outros produtos da casa
(CLAUDE.md: "role nova sem linha no pg_hba.conf... quebra"; aqui seria pior, é o `listen_addresses` global),
fora do escopo deste item e um risco real para produtos que não são este. **Decisão: `network_mode: host`.**
Custo aceito: o contêiner enxerga toda porta do host (perde o isolamento de rede que uma ponte daria) — o que
este item constrói é isolamento por PROCESSO (`RLIMIT_DATA` + cgroup, seção 4), não isolamento de rede;
isolamento de rede fica para quem precisar dele decidir explicitamente (rede em ponte + regra de
`pg_hba.conf`/`listen_addresses` dedicada), documentado aqui como alternativa, não como decisão tomada.

## 4. Bug encontrado só em contêiner: `_pdeathsig` matava todo filho, sempre

`app/jobs/filho.py::_pdeathsig()` (ADR 0003 seção 4.3) fazia `prctl(PR_SET_PDEATHSIG, SIGKILL)` e então
`if os.getppid() == 1: os._exit(CODIGO_ERRO)` — "se meu pai já morreu entre o fork e o prctl, o kernel me
reparentou para o init (PID 1), então saio". Verdadeiro fora de contêiner. **Dentro de um contêiner Docker sem
`--init`, o PRÓPRIO WORKER roda como PID 1 do contêiner** (confirmado em `GET /saude`: `"pid": 1`) — PID 1 aqui
não é "o init do sistema", é o pai vivíssimo. A checagem antiga não distinguia as duas coisas: **100% dos jobs
falhavam**, imediatamente, com código de saída 1, SEM log e SEM traceback (o `os._exit()` acontece dentro de
`_pdeathsig()`, a primeira chamada do `try` — antes de qualquer `ContextoJob`, antes de qualquer coisa que
escreva no pipe ou no `job_log`; o pai só via "código de saída 1", a mensagem de fallback para saída vazia).
Reproduzido com todos os tipos de job registrados (`prova.progresso`, `prova.falha`, `catalogo.*`, `jobs.*`) —
não é específico de um tipo, é a função universal chamada por todo filho.

**Correção**: `worker.py._lancar()` mede `pid_pai_esperado = os.getpid()` ANTES do `fork()` e repassa a
`mod_filho.executar(..., pid_pai_esperado)`, que repassa a `_pdeathsig(pid_pai_esperado)`. A comparação vira
`os.getppid() != pid_pai_esperado` — certa dentro ou fora de contêiner: se o pai mudou, o pai de verdade
morreu (reparentado para QUALQUER PID, 1 ou não); se PID 1 sempre foi o pai (contêiner sem `--init`), nada
mudou e o filho segue. Testado ponta-a-ponta: com a correção, `curl -X POST /api/jobs {"tipo":"prova.progresso"}`
processado pelo contêiner conclui na 1ª tentativa (antes: falhava as 3 tentativas, sempre).

Por que não só `init: true` (tini) no lugar: tini resolveria o sintoma (PID 1 vira tini, o worker vira PID 2,
a checagem antiga voltaria a fazer sentido), mas é um remendo de implantação — reaparece em qualquer ambiente
que rode a imagem sem `--init` (um `docker run` avulso, um Pod Kubernetes sem `shareProcessNamespace`/init
próprio). A correção em `_pdeathsig` resolve na raiz, independente de como o contêiner é lançado, e continua
correta fora de contêiner. `deploy/docker-compose.worker.yml` também não declara `init: true`: não precisa mais.

## 5. Segredos: `PLAT_SECRET`/`PLAT_DSN_WORKER` continuam nos MESMOS arquivos

`/etc/plat/segredos/PLAT_SECRET` e `PLAT_DSN_WORKER` (dono `root`, modo 600) são os arquivos que a unidade
systemd já lê via `LoadCredential=` (ADR 0001, item L7-19). `deploy/docker-compose.worker.yml` monta os dois
como `secrets:` do Compose. **Medido**: fora do modo swarm, o Compose bind-monta o arquivo de origem
preservando dono e permissão — um processo não-root dentro do contêiner não conseguiria ler nenhum dos dois
(testado: `PermissionError` em uid 10001 contra o arquivo). O systemd resolve isso ajustando o dono/ACL do
diretório de credenciais para o usuário da unidade; o bind mount do Compose não replica esse ajuste.

**Solução**: o contêiner PARTE como root (nenhum `USER` antes do `ENTRYPOINT` no Dockerfile).
`deploy/entrypoint-worker.sh` lê os dois arquivos como root, exporta como variável de ambiente comum
(`PLAT_SECRET`, `PLAT_DSN_WORKER`) e SÓ ENTÃO troca de privilégio via `setpriv --reuid=plat --regid=plat
--init-groups` (não `su`: troca uid/gid e faz `exec()` direto, sem PAM, sem filtrar o ambiente do processo —
as variáveis exportadas chegam intactas). O worker em si nunca roda como root.

Achado colateral: `app/settings.py::_credenciais_systemd()` também sabe ler `CREDENTIALS_DIRECTORY` (mesmo
nome de variável que o `LoadCredential=` do systemd usa) — MAS se o processo já rodando como `plat` também
vir essa variável apontando para o mesmo diretório root:600, tenta reabrir os arquivos e morre com
`PermissionError` não capturada (bug pré-existente em `_credenciais_systemd`, não corrigido aqui: fora do
escopo deste item, e `app/settings.py` já estava sob edição concorrente de outra trilha neste turno — risco de
colisão real). **Contorno, dentro do escopo deste item**: `docker-compose.worker.yml` nunca declara
`CREDENTIALS_DIRECTORY`; sem essa variável, `_credenciais_systemd()` nem tenta, e as duas variáveis já chegam
como ambiente comum (prioridade mais alta em `valores_do_ambiente()`, a mesma regra que a suíte de teste usa
para injetar `PLAT_SECRET` via `Makefile`).

## 6. Memória: cgroup do contêiner é o mesmo mecanismo que a unidade systemd já usa

`app/jobs/filho.py::limite_memoria_cgroup_mb()` (mesmo item) lê o `memory.max` do cgroup v2 do PRÓPRIO
processo, resolvendo o caminho via `/proc/self/cgroup` (nunca `/sys/fs/cgroup/memory.max` hardcoded — só
coincide com a raiz dentro de um contêiner Docker padrão; a unidade `plat-worker` mede
`/system.slice/plat-worker.service/memory.max` = 2147483648, os 2 GiB do `MemoryMax=2G` do
`deploy/plat-worker.service`). `docker-compose.worker.yml` usa `mem_limit`/`memswap_limit` (não
`deploy.resources.limits`, que só vale em modo swarm) espelhando o mesmo `2g`. `preparar_ambiente()` nunca
deixa o `RLIMIT_DATA` de um filho passar do teto do cgroup menos uma reserva fixa de 96 MB (RSS do pai medido
no ADR 0003 = 25.920 kB; a reserva cobre o pai + margem — RLIMIT_DATA conta segmento de dados/mmap privado do
PRÓPRIO filho, o cgroup conta RSS+cache de página do cgroup INTEIRO). Testado ponta-a-ponta com
`mem_limit: 300m`: `cgroup_memoria_max_mb` no `/saude` do worker relata 300; um job com `memoria_mb=256`
(padrão de `prova.progresso`) roda com `RLIMIT_DATA` clampado para 204 MB e grava `AVISO` no `job_log`
("RLIMIT_DATA reduzido de 256 MB para 204 MB pelo teto do cgroup"); com `mem_limit: 2g` (o padrão do arquivo,
espelhando produção) o mesmo job NÃO é clampado — regressão coberta (produção de hoje não muda de
comportamento). `GET /saude` do worker ganhou o campo `cgroup_memoria_max_mb` (mesmo número, para observação).

## 7. Quando usar contêiner, quando usar a unidade systemd

Não é substituição: são dois executores da MESMA fila. `docs/ARQUITETURA.md` tem a tabela de decisão completa;
resumo:

- **Unidade systemd** (padrão, produção hoje): já provada, `install.sh` já a instala e verifica, menor
  superfície (sem Docker), acesso direto ao `--system-site-packages` do host (GDAL/psycopg2/cryptography/magic
  do dpkg, sem duplicar).
- **Contêiner** quando o item que pede precisa de um dos dois: (a) limite de recursos por EXECUÇÃO que o
  cgroup da unidade única não separa por job (hoje `MemoryMax=2G` é do WORKER inteiro, não por job — um
  contêiner por execução, criado e destruído pelo item L2-16-b/c, dá um cgroup por job de verdade); (b) uma
  imagem versionada e distribuível para rodar em outra máquina (o item de execução remota/GPU, fora deste
  escopo) sem repetir `install.sh` inteiro.

## 8. `install.sh --worker-container` (flag opcional, não quebra o padrão)

`install.sh` sem a flag continua exatamente como era: instala e sobe a unidade systemd `plat-worker`. Com
`--worker-container`, ALÉM da unidade systemd (nunca no lugar dela — a API sempre depende de pelo menos um
worker vivo, `GET /saude` reprova sem `workers_vivos >= 1`), builda e sobe
`deploy/docker-compose.worker.yml` como segundo executor, com `PLAT_WORKER_NOME=worker-container` e
`PLAT_WORKER_URL=http://127.0.0.1:8155`. A porta 8154 (e 8158) NÃO estava livre para este item: MEDIDO
06/09/2026 em `docs/HOMOLOGACAO.md`, são as portas PERMANENTES do nginx/uvicorn do ambiente de homologação
(`ARQUITETURA.md` reserva 8150-8159 ao produto inteiro, não só a este item — 8151/8152 já são de
`martin`/`titiler`, reservadas e sem serviço). **8155** é a escolhida (confira com `ss -tlnp | grep 815`
antes de mudar: a faixa é dividida por várias frentes do mesmo produto, não só systemd × contêiner). Exige
`docker`/`docker compose` instalados (o script confere e para com mensagem clara se faltar, nunca instala
Docker sozinho — decisão do dono, fora do escopo de um item que só constrói o worker).

## 9. Testado (handoff completo em `laco/handoffs/T3/L0-05-e-worker-container.md`)

`docker build` da imagem; `docker compose up` sobe o contêiner, `GET /saude` responde saudável e registra
`worker-container:1` em `plat.worker`; job real criado pela API (`prova.progresso`) roda até `concluido` pelo
executor em contêiner (`worker` no registro = `worker-container:1`), na 1ª tentativa; teste de clamp de
memória com `mem_limit: 300m` (seção 6); 9 testes de unidade novos (`tests/unit/test_jobs_filho_cgroup.py`,
pura aritmética + um único teste ponta-a-ponta em subprocesso isolado — `resource.setrlimit(RLIMIT_DATA)` só
BAIXA o teto no processo que o chama, testar a syscall de verdade duas vezes no mesmo processo do pytest
quebra a segunda chamada). `make check` completo NÃO passou neste turno por motivo alheio a este item
(concorrência de outras trilhas no mesmo repositório deixou `app/settings.py`/`app.main` momentaneamente
inconsistentes; ver o handoff). A unidade systemd `plat-worker` de produção NUNCA foi parada nem reiniciada
para este item — todo teste rodou contra um executor em contêiner adicional, com nome e porta distintos.
