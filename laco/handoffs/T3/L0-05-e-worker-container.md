# L0-05-e-worker-em-container — handoff (turno T3, papéis arquiteto+backend em um só, passagem única a pedido do dono)

**Objetivo**: registrar um executor ALTERNATIVO da fila de jobs (ADR 0003), em contêiner Docker, ao lado da
unidade systemd `plat-worker` — mesmo protocolo (fork por job, `RLIMIT_DATA`, `PR_SET_PDEATHSIG`), mesmo
`plat.job` no banco. Pedido explícito: `deploy/Dockerfile.worker`, `deploy/docker-compose.worker.yml`,
detecção de cgroup v2 para o `RLIMIT_DATA` do filho nunca exceder o limite do contêiner, teste ponta-a-ponta
(build, sobe, conecta no Postgres real, roda 1 job até `concluido`), `install.sh --worker-container` opcional,
`docs/ARQUITETURA.md` com a decisão contêiner × systemd. Disco a 98% no início; **não** restart do
`plat-worker` de produção.

## O que fiz

1. **`app/jobs/filho.py`** — `limite_memoria_cgroup_mb()` (novo): lê o teto de memória do cgroup v2 do
   processo atual, resolvendo o caminho via `/proc/self/cgroup` (nunca hardcoded — MEDIDO: só coincide com
   `/sys/fs/cgroup/memory.max` dentro de um contêiner Docker padrão; a unidade systemd vive em
   `/system.slice/plat-worker.service/memory.max`). `memoria_efetiva_mb()`/`preparar_ambiente()`: o
   `RLIMIT_DATA` de um filho nunca passa do teto do cgroup menos uma reserva fixa de 96 MB. `GET /saude` do
   worker ganhou `cgroup_memoria_max_mb` (app/jobs/worker.py).
2. **Bug achado e corrigido, não estava no pedido**: `_pdeathsig()` checava `os.getppid() == 1` para "o pai
   morreu"; dentro de um contêiner sem `--init` o PRÓPRIO WORKER É PID 1 — **100% dos jobs falhavam**,
   sempre, imediatamente, sem log nem traceback (o `os._exit()` acontecia antes de qualquer coisa escrever em
   qualquer lugar). Corrigido comparando contra o PID do pai medido ANTES do `fork()` (`worker.py._lancar()`
   repassa a `mod_filho.executar(..., pid_pai_esperado)` → `_pdeathsig(pid_pai_esperado)`). Sem essa correção
   o item inteiro não existiria de verdade (o contêiner subiria, o `/saude` responderia, mas NENHUM job
   jamais concluiria).
3. **`deploy/Dockerfile.worker`**: `python:3.12-slim-bookworm`, sem `--system-site-packages` (a base é Debian,
   Python de sistema 3.11; o host usa Ubuntu 24.04, Python 3.12 — os bindings apt não combinam com esta
   imagem). `apt-get`: `gdal-bin`, `libmagic1`, `ca-certificates`. Achado: `app.catalogo.tipos`/`miniatura`
   importam `jsonschema`/`Pillow`, nunca declarados em `requirements.txt` nem `deploy/pacotes_apt.txt` — só
   funcionam no host por acaso (instalação pip global de outro produto da máquina). Travados na imagem na
   versão medida (`jsonschema==4.26.0`, `Pillow==12.2.0`); `psycopg2-binary==2.9.12`, `cryptography==50.0.1`,
   `python-magic==0.4.27` (sem dpkg equivalente nesta base, versão = a que o pip resolveu no build,
   confirmada via `pip freeze` dentro da imagem). Usuário `plat` (uid 10001), nunca root no worker.
   `.dockerignore`: LISTA DE PERMISSÃO (`* ... !app !app/** !requirements.txt !VERSAO !deploy
   !deploy/entrypoint-worker.sh`) — uma lista de exclusão quebrou o build (arquivo dono root modo 700 deixado
   por outra trilha em `osrm/`, ilegível pelo daemon).
4. **`deploy/entrypoint-worker.sh`**: contêiner PARTE como root, lê `PLAT_SECRET`/`PLAT_DSN_WORKER` de
   `/run/secrets/*` (dono root:600, preservado pelo bind do Compose — MEDIDO: um processo uid 10001 não
   conseguiria ler), exporta como ambiente comum e solta o privilégio via `setpriv --reuid=plat --regid=plat
   --init-groups` ANTES de rodar uma linha do worker. `CREDENTIALS_DIRECTORY` nunca é propagada ao processo
   final (achado: `app.settings._credenciais_systemd()` tentaria reler os mesmos arquivos já como `plat` e
   morreria com `PermissionError` não capturada — bug pré-existente, documentado, não corrigido aqui:
   `app/settings.py` estava sob edição concorrente de outra trilha neste turno).
5. **`deploy/docker-compose.worker.yml`**: `network_mode: host` (Postgres/Garage só escutam 127.0.0.1 nesta
   máquina — MEDIDO em `postgresql.conf`/`pg_hba.conf`; uma rede em ponte chegaria de outro IP e nem
   autenticaria); `secrets:` apontando para os mesmos arquivos do systemd; `mem_limit`/`memswap_limit: 2g`
   (espelha `MemoryMax=2G` da unidade); `PLAT_WORKER_NOME=worker-container`,
   `PLAT_WORKER_URL=http://127.0.0.1:8155` (8154/8158 são permanentes do ambiente de homologação, achado ao
   checar `docs/HOMOLOGACAO.md`; 8151/8152 de martin/titiler).
6. **`install.sh`**: flag `--worker-container` (aceita em qualquer posição dos argumentos), passo novo "h4"
   depois da unidade systemd do worker — confere `docker`/`docker compose` (plugin v2), confere os segredos já
   existem, builda+sobe o compose, espera `/saude` responder. Sem a flag, comportamento idêntico a antes.
7. **`docs/adr/0010-worker-em-container.md`** (próximo número livre no momento de criar — 0008/0009 já
   tomados por outras duas trilhas neste turno): decisão completa, com os MEDIDOS de rede/segredos/memória/bug.
8. **`ARQUITETURA.md`** seção 5.8 (tabela de decisão contêiner × systemd, o que cada um exige, o que a
   containerização corrigiu) + nota em "7. install.sh"; **`MANUAL.md`** seção 11.6; **`CHANGELOG.md`** entrada
   no topo do turno 3.
9. **`tests/unit/test_jobs_filho_cgroup.py`** (9 testes): aritmética pura do clamp (monkeypatch de
   `/proc/self/cgroup` e da raiz do cgroup, sem tocar em `RLIMIT` de verdade) + 1 teste ponta-a-ponta em
   subprocesso isolado (chamando `preparar_ambiente()` de verdade) — `resource.setrlimit(RLIMIT_DATA)` só
   BAIXA o teto no processo que o chama; dois testes no mesmo processo do pytest quebrariam o segundo
   (`ValueError: not allowed to raise maximum limit`, reproduzido e documentado no docstring do teste).

## Evidência (comando + saída literal)

Build e ambiente:
```
$ docker build -f deploy/Dockerfile.worker -t plat-worker:test .
Successfully built ...
$ docker images plat-worker:test
DISK USAGE 1.27GB   CONTENT SIZE 315MB
$ docker run --rm --entrypoint venv/bin/pip plat-worker:test freeze | grep -E "psycopg2-binary|cryptography|python-magic|pillow|jsonschema"
cryptography==50.0.1
jsonschema==4.26.0
pillow==12.2.0
psycopg2-binary==2.9.12
python-magic==0.4.27
$ docker run --rm --entrypoint gdalinfo plat-worker:test --version
GDAL 3.6.2, released 2023/01/02
```

Detecção de cgroup dentro de contêiner de verdade (não simulado):
```
$ docker run --rm --memory=300m -e PLAT_SECRET=... -e PLAT_DSN=... -e PLAT_AMBIENTE=dev -e PLAT_URL_PUBLICA=https://x \
    --entrypoint venv/bin/python plat-worker:test -c "from app.jobs import filho; print(filho.limite_memoria_cgroup_mb()); print(filho.memoria_efetiva_mb(1536))"
300
204
```

Subida via compose e saúde (porta final 8155; 8157 foi usada durante a investigação para não colidir com
outra trilha que tinha 8154/8156 em uso no mesmo instante — documentado no ADR):
```
$ docker compose -f deploy/docker-compose.worker.yml up -d --build
... Started
$ curl -sS http://127.0.0.1:8155/saude
{"worker": "worker-container:1", "nome_base": "worker-container", "pid": 1, ...,
 "cgroup_memoria_max_mb": 2048}
```

Job real, criado pela API de produção (porta 8150), concluído pelo executor em contêiner:
```
$ curl -sS -X POST http://127.0.0.1:8150/api/jobs -b "plat_sessao=$TOK" \
    -d '{"tipo":"prova.progresso","parametros":{"duracao_s":2,"passos":2}}'
{"id":"535ebe35-...", "estado":"pendente", ...}
$ curl -sS http://127.0.0.1:8150/api/jobs/535ebe35-.../
{"estado": "concluido", "tentativa": 1, "worker": "worker-container:1",
 "resultado": {"passos": 2, "marcador": "...", "duracao_s": 2}, "erro": null}
```

Clamp de memória ponta-a-ponta (`mem_limit: 300m`; restaurado a `2g` depois):
```
$ curl -sS http://127.0.0.1:8150/api/jobs/d.../log -b "..."
{"linhas": [
  {"nivel": "AVISO", "mensagem": "RLIMIT_DATA reduzido de 256 MB para 204 MB pelo teto do cgroup ..."},
  {"nivel": "INFO", "mensagem": "início: 1 passos em 1 s; ..."}, ...
]}
```

Reprodução do bug ANTES da correção (`_pdeathsig`), pego via job real através da API (não sintético):
```
{"estado": "falhou", "tentativa": 3, "erro": "código de saída 1", "worker": null,
 "proveniencia": {"worker": "worker-container:1", ...}}
$ docker logs plat-worker-container | tail -6
{"msg": "job iniciado", ..., "pid_filho": 26}
{"msg": "job terminou: pendente (código 1)", ..., "pid_filho": 26}
... (3 tentativas, sempre código 1, nunca uma linha em job_log)
```

Testes de unidade:
```
$ venv/bin/ruff check app/jobs/filho.py app/jobs/worker.py tests/unit/test_jobs_filho_cgroup.py
All checks passed!
$ PLAT_SECRET=... PLAT_DSN_WORKER=... flock .../laco/.pytest.lock venv/bin/pytest -q tests/unit/test_jobs_filho_cgroup.py
.........                                                                [100%]
$ flock .../laco/.pytest.lock venv/bin/pytest -q tests/unit -k "jobs or filho"
.........................                                                [100%]   (25 testes)
```

Marcadores e limites:
```
$ grep -nI -E -f tests/marcadores.regex deploy/Dockerfile.worker deploy/docker-compose.worker.yml \
    deploy/entrypoint-worker.sh docs/adr/0010-worker-em-container.md app/jobs/filho.py app/jobs/worker.py \
    install.sh ARQUITETURA.md MANUAL.md CHANGELOG.md
(sem saída — nenhum marcador; achado no meio do caminho: "TODO"/"TODOS" em maiúsculas colidia com o regex
 como falso positivo do português "todo/todos" — reescrito em minúsculas, como o resto do repositório já fazia)
$ venv/bin/python docs/gerar_limites.py --check
(sem saída — nenhuma divergência)
$ bash -n install.sh && bash -n deploy/entrypoint-worker.sh && docker compose -f deploy/docker-compose.worker.yml config -q
(todos OK)
```

Disco (98% no início; build de imagem some 1-1,3 GB até a limpeza):
```
antes:  /dev/vda2  469G  452G   12G  98% /
depois: /dev/vda2  469G  453G   11G  98% /   (docker rmi + docker builder/image prune ao final)
```

## Riscos

- **`app/settings.py::_credenciais_systemd()` tem uma `PermissionError` não capturada** quando
  `CREDENTIALS_DIRECTORY` aponta para um diretório cujos arquivos o processo atual não pode ler (cenário real:
  um contêiner Compose com segredo montado dono root, processo já sem privilégio). Contornado (nunca propagar
  a variável), não corrigido — pertence a quem for dono de `app/settings.py`/item de segredos; a trilha que
  editava esse arquivo neste turno ainda não tinha terminado quando testei.
- **`jsonschema`/`Pillow` não declaradas em `requirements.txt`** (achado, seção acima) — o host só funciona
  hoje por um acaso de instalação global de outro produto; se essa instalação global for limpa um dia, o
  `plat-api`/`plat-worker` de PRODUÇÃO quebram na importação de `app.catalogo`, não só o contêiner. Vale
  abrir item próprio.
- `deploy/docker-compose.worker.yml` usa `restart: "no"` de propósito (arquivo de teste/demonstração do
  item); quem operar isto como executor permanente decide a política de reinício separadamente.
- Porta de saúde 8155 escolhida depois de checar `docs/HOMOLOGACAO.md` e `ss -tlnp`; a faixa 8150-8159 é
  disputada por várias trilhas do mesmo produto no mesmo turno — reconferir antes de reusar em outro item.
- `make check` completo (suíte inteira) NÃO rodou limpo neste turno por motivo ALHEIO a este item: outras
  trilhas deixaram `app/settings.py`/`app.main` momentaneamente inconsistentes enquanto editavam ao vivo
  (`/saude` da API chegou a devolver `{"erro": true}` numa janela); os testes ESPECÍFICOS deste item (unidade
  + o teste ponta-a-ponta manual via API real) todos passaram.

## Pendências

- Corrigir `_credenciais_systemd()` (item separado, dono de `app/settings.py`).
- Declarar `jsonschema`/`Pillow` em `requirements.txt` do host (item separado, dono de `app/catalogo`).
- Quando L2-16-b/c (execução de job em contêiner isolado por execução) entrar, o portão de pronto deste item
  ("a fixar pelo arquiteto no turno em que o item que a pediu entrar") pode ser escrito e testado contra este
  executor — a infraestrutura já existe e já prova job real até `concluido`.

## Para o próximo papel

Nenhum papel adicional pendente deste item (arquiteto+backend cobriram o pedido; testador = os comandos acima,
repetíveis). Quem pegar L2-16-b/c: o contêiner por-execução (isolado, criado/destruído por job) é uma variação
DESTE Dockerfile/entrypoint, não uma reescrita — reusar `limite_memoria_cgroup_mb()`/`preparar_ambiente()` e a
correção de `_pdeathsig` (ela vale para QUALQUER contêiner sem `--init`, inclusive um por execução).
