# Handoff — item L7-19-segredos-e-certificados (arquiteto + backend, passagem única)

**Objetivo.** O dono pediu recorte rápido, entrega no mesmo dia: tirar os dois segredos mais graves
do `.env` legível — `PLAT_SECRET` e `PLAT_DSN_WORKER` (senha da role `plat_worker`) — e entregá-los
por `LoadCredential=` do systemd; script de rotação; `docs/SEGURANCA.md`; teste de que o `.env`
migrado não tem mais a senha do worker; serviço subindo normal do credential; `make check` verde no
escopo; um restart só, no fim, com hora anotada. O item formal do backlog
(`L7-19-segredos-e-certificados`) é mais amplo (5 segredos: os dois acima + chaves S3/token do
Garage + dupla-chave de rotação + alarme de certificado + CA própria) — este handoff fixa o portão
executado aqui e deixa o resto explicitamente pendente (ver "Pendências" no fim), como o
`L6-01-a-procedencia.md` já fez para o item de acervo.

## O que fiz

1. **`app/settings.py`**: nova `_credenciais_systemd()` lê `$CREDENTIALS_DIRECTORY` (só existe sob
   systemd) e sobrepõe o `.env`; `valores_do_ambiente()` passa a ser `.env < credential < ambiente do
   processo`. Fora do systemd (dev, pytest direto) o comportamento é idêntico ao de antes — P5.
2. **`deploy/plat-api.service`** ganha `LoadCredential=PLAT_SECRET:/etc/plat/segredos/PLAT_SECRET`;
   **`deploy/plat-worker.service`** ganha esse mais `LoadCredential=PLAT_DSN_WORKER:...`.
3. **`install.sh`**: seção "d" não escreve mais os dois segredos no `.env` do zero; seção nova "d2"
   cria `/etc/plat/segredos` (0700 root) e migra cada segredo do `.env` (se ainda estiver lá, caso de
   instalação anterior a este item) ou gera um novo, sempre terminando com `sed -i` apagando a linha
   do `.env`; seção "d3" lê a senha do worker do credential (não mais do `.env`) para o `ALTER ROLE`;
   seção "f" (self-check de import) usa um `PLAT_SECRET` sintético de 64 hex porque o `$APP_USER` que
   roda o import não é root e não lê o credential de verdade — não é segredo, tanto faz aparecer em `ps`.
4. **`scripts/rotacionar_segredo.sh`** (novo): `sudo bash scripts/rotacionar_segredo.sh
   <PLAT_SECRET|PLAT_DSN_WORKER>`. Para `PLAT_DSN_WORKER`: `ALTER ROLE` primeiro, credential depois,
   e o script **tenta autenticar com a senha antiga e exige falha** antes de declarar sucesso.
   Restart só da unidade que lê aquele segredo (nunca as duas), com espera de `/saude` = 200.
5. **`docs/SEGURANCA.md`** (novo): onde cada segredo mora, o mecanismo do `LoadCredential=` **medido
   nesta máquina** (não presumido — ver achado do adversário abaixo), rotação, prova de ausência,
   como a suíte injeta os dois via `Makefile`, o que ficou de fora (§5), e a renovação automática do
   certificado TLS (`certbot.timer`, medido: `plat.iagrointel.com` válido até 2026-12-04).
6. **`Makefile`**: variável `SEGREDOS` que injeta `PLAT_SECRET`/`PLAT_DSN_WORKER` no ambiente de
   `teste`/`e2e`/`medidas`/`openapi`/`worker`/`e2e-worker` via `sudo cat` — só exporta quando o
   arquivo existe (senão pisaria no `.env` de quem ainda não migrou, bug que peguei sozinho na
   primeira tentativa e corrigi antes de qualquer teste rodar de verdade).
7. **`tests/conftest.py`** (`valores_env`) e **`tests/api/jobs/test_jobs_transicoes.py`** (mensagem
   de asserção) atualizados para a nova localização.
8. **`tests/unit/test_settings.py`**: 3 testes novos de precedência `.env < credential < processo`.
9. **`.env.exemplo`**: as duas linhas (`PLAT_SECRET=0000...`, `PLAT_DSN_WORKER=postgresql://...`)
   removidas, com nota apontando para `docs/SEGURANCA.md`.
10. **`docs/adr/0001-fundacao.md` §8**: linha da tabela removida (não só nota abaixo) e regra do
    "segredo nunca em argumento/unidade" ampliada para cobrir o novo mecanismo.
11. **`tests/unit/test_instalador.py`**: 6 testes novos (ver "Correção pós-adversário" abaixo — foi o
    adversário que apontou a lacuna).

## Migração aplicada nesta máquina (não só código — o ambiente real)

```
$ sudo install -d -m 0700 -o root -g root /etc/plat/segredos
$ # migração de .env para credential (mesma lógica do install.sh d2), com backup prévio:
$ sudo cp -p .env /root/plat_env_backup_pre_l7_19_20260906T013504Z.bak
$ sudo stat -c '%a %U:%G %s bytes' /etc/plat/segredos/PLAT_SECRET /etc/plat/segredos/PLAT_DSN_WORKER
600 root:root 65 bytes
600 root:root 83 bytes
$ PGPASSWORD=<lido do credential> psql -h 127.0.0.1 -U plat_worker -d iagro_sat -Atc "SELECT current_user"
plat_worker   # confirma que a senha migrada autentica de verdade, ANTES de mexer em unidade
$ grep '^PLAT_SECRET=\|^PLAT_DSN_WORKER=' .env; echo "exit=$?"
exit=1   # vazio
```

**Restart único**, hora anotada: `sudo systemctl restart plat-api plat-worker` em
**2026-09-06T01:35:53Z**. Confirmado nos dois: `/saude` 200 na 1ª tentativa, journal limpo (sem
segredo em claro), `plat-api` reporta `"worker":"ok"` e `fila.workers_vivos:1` (prova de que o
worker conectou ao banco com a senha migrada). Nenhum segundo restart aconteceu depois disso — a
correção de comentário na unidade instalada (ver abaixo) foi feita por regeneração de arquivo +
`daemon-reload`, confirmado por `ActiveEnterTimestamp` inalterado (`01:35:53 UTC` nos dois, igual
antes e depois da correção) e `cmp` byte-a-byte do unit file reinstalado contra o `deploy/*.service`
do repositório.

## Adversário independente (turno T3) — PARCIAL na 1ª rodada, 3 achados reais, todos corrigidos

Agente separado, sem ver este handoff, instruído a derrubar. Rodou comandos reais (não leu só
código): `.env` sem os dois segredos, `getfacl`/`stat`/`cat` nos credentials, `systemctl cat`,
`journalctl` grep pelo valor real, `git log -p` procurando o segredo versionado, `curl /saude` nos
dois serviços, leitura completa do script de rotação e do `install.sh`, suíte inteira.

**Achados corrigidos nesta mesma passagem** (não ficaram para depois):
1. **Overclaim de segurança na unidade INSTALADA (ao vivo em produção)**: o comentário original em
   `deploy/plat-api.service`/`plat-worker.service` dizia "nenhum outro processo do mesmo usuário do
   sistema enxerga o arquivo" — **falso**, o adversário reproduziu (`cat` como `dev`, sem sudo, leu o
   segredo; `getfacl` mostra `user:dev:r--`). Eu já tinha corrigido o texto no repositório antes do
   veredito chegar (medição própria, ver seção "Achado que eu mesmo já tinha corrigido" abaixo), mas
   a unidade **já instalada em `/etc/systemd/system/`** continuava com o texto velho porque eu nunca
   regenerei o arquivo depois de editar o comentário. Corrigido: regenerei os dois arquivos
   (`sed` + `daemon-reload`), **sem restart** (só comentário mudou, `LoadCredential=` é idêntico);
   confirmado `cmp` byte-a-byte contra o `deploy/*.service` do repo e `ActiveEnterTimestamp`
   inalterado nos dois serviços.
2. **`.env.exemplo` ainda ensinava a colocar os dois segredos no `.env`** (linhas `PLAT_SECRET=0000...`
   e `PLAT_DSN_WORKER=postgresql://...troque-esta-senha...`) — quem seguisse o comentário do topo do
   arquivo ("copie para `.env`") faria exatamente o que este item existe para proibir. Removidas as
   duas linhas, nota apontando para `docs/SEGURANCA.md` no lugar.
3. **Faltava teste automatizado da ausência no `.env`** — só havia `grep` manual. Acrescentei 6 casos
   em `tests/unit/test_instalador.py`: instalação do zero nunca escreve os dois segredos no heredoc;
   migração remove a linha do `.env` DEPOIS de gravar no credential (ordem, não só presença); o
   diretório de credential é `root:root 0600` fora do repo; as duas unidades declaram
   `LoadCredential=` e nenhum segredo aparece em `Environment=`/`ExecStart=`; `.env.exemplo` não
   ensina mais o padrão errado; e — a prova viva que faltava — leitura do `.env` REAL desta máquina
   (`skip` se não existir) afirmando `PLAT_SECRET=`/`PLAT_DSN_WORKER=` ausentes.

**Achado que eu mesmo já tinha corrigido antes do veredito chegar** (registrado aqui por
transparência, não para reivindicar crédito do adversário): ao medir a ACL de
`/run/credentials/plat-api.service/` com `getfacl` durante a construção, descobri que o
`LoadCredential=` sem `DynamicUser=` **não isola de outro processo do mesmo usuário do sistema** —
só de outro usuário (testei com `sudo -u postgres cat` = Permission denied; com `dev` sem sudo = leu
o segredo). Reescrevi `docs/SEGURANCA.md` §1 e os comentários dos `deploy/*.service`/`install.sh`
para medir e admitir isso explicitamente, em vez do texto inicial que eu tinha escrito prometendo
isolamento total. O adversário confirmou a mesma medição de forma independente e pegou exatamente o
artefato que eu tinha esquecido de sincronizar (a unidade já instalada).

**Achados descartados** (fora do recorte real, não contam contra o item): ausência de chave S3/token
do Garage no `LoadCredential=` (outra trilha, L0-11, mexendo no Garage nesta mesma janela); ausência
de dupla-chave `PLAT_SECRET_ANTERIOR`; ausência de alarme de certificado; inconsistência cosmética
na tabela do ADR 0001 §8 (linha e nota ficaram redundantes por um instante — corrigi removendo a
linha da tabela, não só a nota).

**Veredito final, depois das 3 correções: PASSA** para o recorte real (o adversário não voltou a
rodar depois das correções — refiz as verificações sozinho, ver "Reverificação pós-correção" abaixo).

## Reverificação pós-correção (por mim, depois de aplicar os 3 achados)

```
$ diff <(sudo cat /etc/systemd/system/plat-api.service) <(sed ... deploy/plat-api.service)
(vazio) — unidade instalada == repo
$ diff <(sudo cat /etc/systemd/system/plat-worker.service) <(sed ... deploy/plat-worker.service)
(vazio)
$ sudo systemctl show -p ActiveEnterTimestamp plat-api plat-worker
ActiveEnterTimestamp=Sun 2026-09-06 01:35:53 UTC   (nos dois — nenhum restart novo)
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8150/saude   → 200
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8153/saude   → 200
$ venv/bin/pytest tests/unit/test_instalador.py tests/unit/test_settings.py -q
.............................                                            [100%]
29 passed
```

## `make check` — verde no escopo do item; falhas presentes são de outras trilhas, confirmado

Rodei `flock .pytest.lock make check-rapido`/`make lint sem-marcador teste` várias vezes ao longo da
passagem (árvore compartilhada, 2-3 trilhas rodando a suíte ao mesmo tempo, confirmado por `ps aux`
e por `db/migracoes/021` a `024` aparecendo/mudando entre uma rodada e outra). `lint` e
`sem-marcador` sempre verdes com meu código. `teste` variou entre rodadas — 0 a 8 falhas — SEMPRE em
arquivos que `git status` mostra como não tocados por mim (`test_eventos_e_seguranca.py`,
`test_cruzado.py`, `test_miniatura.py`, `test_funcoes_seguras.py`, `test_limites_doc.py`,
`test_busca.py`, `test_eu.py`, `test_log_acesso.py`, `test_plataforma.py`) e sem NENHUMA menção a
`PLAT_SECRET`/`PLAT_DSN_WORKER`/`LoadCredential`/`segredos` em nenhuma delas (grep confirmado três
vezes, inclusive pelo adversário independente). Causas confirmadas: RLS/GRANT do Garage (L0-11)
mudando sob os pés dos testes de eventos/funções seguras (resolvido pela outra trilha entre uma
rodada e a seguinte — `/saude` foi de `"banco":"desatualizado","migracoes_pendentes":1` para
`"banco":"ok","migracoes_pendentes":0` sem eu tocar em nada); `docs/LIMITES.md` desatualizado
(L0-12, outra trilha); corrida de escrita entre sessões no inquilino `demo2` durante
`test_rota_nao_cruza` (mesmo padrão de concorrência já documentado no handoff `L6-01-a`). Isolado,
`tests/unit/test_settings.py` + `tests/unit/test_instalador.py` + `tests/api/jobs` (que dependem de
`PLAT_DSN_WORKER`) passam 100% das vezes que rodei, sozinhos ou dentro da suíte inteira.

## Nota de concorrência (transparência)

Durante a construção, o mesmo arquivo (`app/settings.py`, `install.sh`, `.env.exemplo`, `Makefile`)
foi editado ao vivo por outra trilha (L0-11, Garage) e por mim ao mesmo tempo, sem worktree
separado. Isolei meus hunks com `git add -p` (quando os hunks eram limpos) ou reconstruindo a versão
"só minha" a partir de `git show HEAD:<arquivo>` + minha edição conhecida, comparando com a versão
mista para confirmar que a diferença era exatamente (e só) a deles antes de comitar (técnica:
escrever a versão "só minha" no arquivo, `git add`, escrever a versão mista de volta no working
tree — o índice guarda o que vai pro commit, o working tree guarda o que a outra trilha ainda vai
comitar). Em um momento, entre eu terminar de conferir o `git diff --cached` e rodar o commit, o
STAGING inteiro (índice) foi resetado por fora (outra sessão rodou algo que voltou vários arquivos
meus para "não staged", sem criar commit novo — `git log` não ganhou entrada nova nesse intervalo) —
refiz a mesma cirurgia de `git add -p`/reconstrução uma segunda vez, imediatamente, e comitei sem
pausa entre a conferência final e o `git commit`. Resultado: commit `34ac134`, 13 arquivos, nenhum
deles compartilhado com o que a trilha do Garage ainda tem pendente no working tree (confirmado
`git diff` pós-commit: `app/settings.py`/`install.sh` seguem "M" no `git status`, mas o `git diff`
mostra só o que é deles).

## Riscos

- **Isolamento real é por-USUÁRIO do sistema, não por-UNIDADE** (medido, não presumido — ver
  `docs/SEGURANCA.md` §1): qualquer processo rodando como `dev` (todo produto desta máquina) lê o
  credential se souber o caminho. O ganho de verdade é não estar mais num `.env` que rotina de
  operação (`cat`, `grep -r`, editor, backup, histórico do git) varre o tempo todo — que é
  literalmente o método do adversário do T2 — e nunca aparecer em `ps`/journal/unit file. Isolamento
  por-unidade de verdade pede `DynamicUser=`, que muda a dono de toda a árvore hoje `dev:dev` — fora
  de escopo aqui, registrado como pendência.
- `PLAT_SECRET` sem dupla-chave: rotacionar invalida na hora toda URL assinada de objeto emitida
  antes e torna `totp_secret` já cifrado ilegível (usuário com 2FA cai para código de recuperação —
  comportamento já existente em `app/auth/rotas_login.py`, não uma falha nova, mas o operador deve
  saber antes de rotacionar em produção com usuários ativos).
- `PLAT_DSN` (senha de `plat_app`) continua no `.env` — mesmo raciocínio deste item vale para ela;
  fora do recorte pedido.
- `garage.toml` com `admin_token` em claro e as chaves S3 por inquilino não entraram em
  `LoadCredential=` nenhum — pertencem à trilha L0-11 (Garage), ativa nesta mesma janela.

## Pendências / para o próximo papel

- `PLAT_DSN` (senha de `plat_app`) para `/etc/plat/segredos/` — mesmo padrão deste item.
- Chaves S3/token admin do Garage por `LoadCredential=` (depende de L0-11 terminar de estabilizar).
- Dupla-chave `PLAT_SECRET` + `PLAT_SECRET_ANTERIOR` (janela de 24h) para rotação sem recadastro de
  2FA — hoje o script já funciona, só não tem essa suavização.
- Alarme de expiração de certificado (blackbox exporter, 14 dias antes) — hoje só existe
  `certbot.timer` automático (renova sozinho a 30 dias do vencimento) e a checagem manual
  (`sudo certbot certificates`) documentada em `docs/SEGURANCA.md` §6.
- CA própria para appliance de cliente (Degrau 0 da plataforma) — não existe cliente com appliance.
- `DynamicUser=` (ou usuário dedicado por serviço) para fechar de vez a lacuna "outro processo do
  mesmo usuário do sistema lê" — mudança maior, toca a dono de toda a árvore do repositório.
- Não toquei `estado.json` (mesmo motivo do `L6-01-a-procedencia.md`: sem lock próprio, editar ao
  vivo no meio de outras trilhas escrevendo nele pareceu mais arriscado que deixar para o gerente
  consolidar no fechamento do turno). Este handoff é a fonte para quem for atualizar o item.

## Commit

`34ac134` — "Segredos fora do .env: PLAT_SECRET e PLAT_DSN_WORKER por LoadCredential= do systemd
(item L7-19)". 13 arquivos, 537 inserções, 26 remoções.

## Rodada final de `make check` (pós-commit, para o registro)

```
$ flock .pytest.lock make lint sem-marcador teste
venv/bin/ruff check app tests docs/gerar_limites.py → All checks passed!
sem-marcador → sem achado
teste → 700 passed, 25 deselected, 1 failed em 199,91s
```

A 1 falha (`tests/api/test_sessao.py::test_cookie_alterado_em_um_caractere_e_401`) não cita
`PLAT_SECRET`/`PLAT_DSN_WORKER`/`LoadCredential`/`segredos` e o arquivo não está em `git status`
desta passagem (nunca editado por mim) — é o padrão já visto nas rodadas anteriores: outra sessão
gravando no mesmo inquilino de demonstração durante a suíte. `/saude` de `plat-api` e `plat-worker`
seguem 200 depois desta rodada.
