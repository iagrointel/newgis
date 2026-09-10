# Segurança — segredos, certificados, dependências e upload

Item L7-19-segredos-e-certificados (§1-6). Esta seção é o mapa: onde cada segredo mora, como rotacionar sem
derrubar o produto, e como o certificado TLS se renova sozinho. Ela não repete o que já está no
`docs/adr/0001-fundacao.md` seção 8 (contrato de `.env`) — só o que mudou e o que é operação. Estendida com
o item L7-03-f-dependencias-cve-log-correcoes (§7, varredura de dependência + log de correções) e o item
L7-03-b-antivirus-anexos (§8, varredura de conteúdo em upload de anexo/miniatura).

## 1. Onde cada segredo mora

| segredo | onde mora hoje | quem lê | dono do arquivo | modo |
|---|---|---|---|---|
| `PLAT_SECRET` | `/etc/plat/segredos/PLAT_SECRET` | `plat-api`, `plat-worker` (via `LoadCredential=`) | root | 0600, diretório 0700 |
| `PLAT_DSN_WORKER` (senha da role `plat_worker`) | `/etc/plat/segredos/PLAT_DSN_WORKER` | `plat-worker` (via `LoadCredential=`) | root | 0600 |
| `PLAT_DSN` (senha da role `plat_app`) | `/etc/plat/segredos/PLAT_DSN` | `plat-api`, `plat-worker` (via `LoadCredential=`) | root | 0600 — **preparado, valor ainda no `.env` até o dono rodar o passo 1 de `docs/AMBIENTES.md` §5** |
| `PLAT_GARAGE_ADMIN_TOKEN` (credencial raiz do armazenamento) | `/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN` | `plat-api`, `plat-worker` (via `LoadCredential=`) | root | 0600 — **mesma situação, mesmo passo 1** |
| `rpc_secret` e `admin_token` do daemon Garage | `pipeline/garage/garage.toml`, em claro | `plataforma-garage` | `dev` | 0600 — **drop-in pronto em `deploy/plataforma-garage-segredos.conf`, troca é o passo 2 de `docs/AMBIENTES.md` §5** |
| `PLAT_GARAGE_CHAVE_SEGREDO` (chave S3 sem administração, só homologação) | `var/homolog/homolog.env` | processos de homologação | `APP_USER` | 0600 |
| credenciais dos admins semeados (`tests/credenciais.txt`) | arquivo na raiz, gitignorado | `install.sh` (semente) | `APP_USER` | 0600 |
| segredo TOTP por usuário (`plat.usuario.totp_secret`) | banco, cifrado com `PLAT_SECRET` (`app/auth/totp.py`) | `plat-api` | — | coluna do banco |

Antes deste item, `PLAT_SECRET` e `PLAT_DSN_WORKER` moravam no `.env` (modo 600, mas dono do usuário do
sistema que roda o repositório inteiro — o mesmo usuário que roda todo outro produto desta máquina).
O adversário do turno T2 (item L0-05, `laco/handoffs/T2/L0-05-jobs/refutacao.json`) registrou a
ameaça: quem lê `PLAT_DSN_WORKER` tem autoridade total sobre o estado de job de **qualquer** inquilino
(`plat.job_terminar`/`plat.job_devolver` são `SECURITY DEFINER` e só conferem `worker = nome`, e o nome
do worker é público em `GET /api/jobs/{id}.worker`) — não há autenticação por processo, a senha é o
único portão. Um `.env` legível por qualquer processo do usuário do sistema é portão fraco demais para
isso.

### O mecanismo: `LoadCredential=` do systemd

`deploy/plat-api.service` e `deploy/plat-worker.service` declaram:

```
LoadCredential=PLAT_SECRET:/etc/plat/segredos/PLAT_SECRET
LoadCredential=PLAT_DSN_WORKER:/etc/plat/segredos/PLAT_DSN_WORKER   # só plat-worker
```

O systemd (rodando como root, antes de rebaixar para `APP_USER`) lê o arquivo fonte e entrega uma cópia
à unidade que a declarou, em `$CREDENTIALS_DIRECTORY` (tipicamente `/run/credentials/<unidade>/`). Isso
é diferente de um segredo em argumento de linha de comando ou em `Environment=` da unidade: nenhum dos
dois aparece em `ps` nem em `systemctl show` (só o *caminho* do arquivo fonte aparece ali, nunca o
valor), o que mantém a regra do ADR 0001 §8 ("segredo nunca em argumento de linha de comando nem em
unidade systemd") — e o arquivo fonte em `/etc/plat/segredos/` é `root:root 0600`, ilegível para
qualquer usuário do sistema que não seja root.

**O que isso NÃO isola — medido nesta máquina (systemd 255, sem `DynamicUser=`), não presumido:**

```
$ sudo getfacl /run/credentials/plat-api.service/PLAT_SECRET
user::r--
user:dev:r--          # dev = APP_USER desta unidade
group::---
other::---

$ cat /run/credentials/plat-api.service/PLAT_SECRET     # rodando como dev, sem sudo
851a69...                                                # LÊ — mesmo usuário do sistema, mesma ACL

$ sudo -u postgres cat /run/credentials/plat-api.service/PLAT_SECRET
cat: ...: Permission denied                              # outro usuário do sistema: bloqueado
```

O `LoadCredential=` sem sandboxing adicional (`DynamicUser=`, `PrivateMounts=`) libera o arquivo por
ACL só ao `User=`/`Group=` configurado na unidade — aqui, `APP_USER` (`dev`), o mesmo usuário que roda
**todo outro produto desta máquina** (CLAUDE.md: `/home/dev/*` é uma única conta operando dezenas de
serviços). Não existe isolamento *por processo* nesta configuração: outro processo rodando como `dev`
que conheça o caminho lê o arquivo igual. O ganho real deste item é outro, e é genuíno: o segredo sai
de um `.env` dentro de um repositório que rotina de operação (`cat`, `grep -r`, editor, backup,
histórico do git) varre o tempo todo — exatamente o método do adversário do T2 ("lê o repositório...
o histórico do git à procura de qualquer segredo") — e passa a exigir saber o caminho específico em
`/run/credentials/` e ter UID `dev`, nunca aparece em `ps`/journal/unit file, e fica ilegível para
qualquer usuário do sistema que não seja root ou `dev`. Isolamento por-unidade de verdade (nem outro
processo do mesmo usuário lê) pediria `DynamicUser=` (usuário efêmero por serviço, alocado a cada
início) — mudaria a dono de toda a árvore do repositório hoje `dev:dev` e ficou fora desta passagem.

`app/settings.py` (`_credenciais_systemd`) lê `$CREDENTIALS_DIRECTORY` quando ela existe e sobrepõe o
`.env` com qualquer arquivo de lá cujo nome bata com um campo de `Settings`; o ambiente do processo
continua por cima de tudo (é assim que a suíte injeta valor de teste sem tocar em arquivo, ver §4).
Fora do systemd (dev, CLI, pytest fora do `Makefile`) a variável não existe e a função devolve vazio —
comportamento idêntico ao de antes deste item, retrocompatibilidade P5.

### Segredo por ambiente (item L7-31, achado 11 do adversário no turno 3)

Até 06/09/2026 o `PLAT_GARAGE_ADMIN_TOKEN` era byte a byte o mesmo em produção e em homologação, e com
o token do arquivo de homologação o adversário listou e leu os buckets de produção `plat-demo` e
`plat-demo2`. Homologação passou a ter uma chave S3 própria, sem poder de administração, dona apenas
dos buckets que ela mesma cria. O desenho, o que ainda é compartilhado e por quê, e o procedimento de
troca em produção estão em **`docs/AMBIENTES.md`**; a prova viva em
`tests/unit/test_isolamento_homologacao.py`.

`app/settings.SEGREDOS` é a lista canônica dos segredos do produto e
`app.settings.segredos_em_claro(<arquivo .env>)` devolve, por nome e nunca por valor, os que ainda
estiverem em claro num arquivo de ambiente.

## 2. `scripts/rotacionar_segredo.sh` — rotação sem reinstalar

```
sudo bash scripts/rotacionar_segredo.sh PLAT_SECRET
sudo bash scripts/rotacionar_segredo.sh PLAT_DSN_WORKER
sudo bash scripts/rotacionar_segredo.sh PLAT_DSN
sudo bash scripts/rotacionar_segredo.sh PLAT_GARAGE_ADMIN_TOKEN
sudo bash scripts/rotacionar_segredo.sh PLAT_GARAGE_S3 <slug-do-inquilino>
```

O que cada rotação faz, em ordem (a ordem importa: nunca existe um instante em que o serviço novo suba
com um segredo que o outro lado — banco ou processo — ainda não aceita):

1. **`PLAT_DSN_WORKER`**: gera senha nova (`openssl rand -hex 16`) → `ALTER ROLE plat_worker PASSWORD`
   no banco **primeiro** → grava o DSN novo em `/etc/plat/segredos/PLAT_DSN_WORKER` → confere que a
   senha **antiga** já não autentica mais (tenta conectar com ela e exige falha) → `systemctl restart
   plat-worker` → espera `/saude` responder 200 (mesmo laço de espera do `install.sh`).
2. **`PLAT_SECRET`**: gera valor novo (`openssl rand -hex 32`) → grava em
   `/etc/plat/segredos/PLAT_SECRET` → `systemctl restart plat-api` → espera `/saude` responder 200.
3. **`PLAT_DSN`**: mesma ordem do `PLAT_DSN_WORKER`, sobre a role `plat_app` — banco primeiro,
   credential depois, conferência de que a senha anterior já não autentica, e então DOIS reinícios, um
   de cada vez, `plat-api` antes de `plat-worker` (as duas unidades leem esse segredo).
4. **`PLAT_GARAGE_ADMIN_TOKEN`**: cria um token de administração GERENCIADO pelo Garage
   (`garage admin-token create`, existe a partir da v2) → grava no credential → confere que o token
   novo é aceito em `/v2/ListBuckets` → reinicia `plat-api` e `plat-worker` → apaga os tokens
   gerenciados anteriores com o mesmo prefixo de nome. O token ESTÁTICO do `garage.toml` não é tocado:
   ele só morre quando sai do arquivo (passo 2 de `docs/AMBIENTES.md` §5).
5. **`PLAT_GARAGE_S3 <slug>`**: cria o par RW/RO novo de um bucket, dá permissão a cada um, grava em
   `plat.arquivo_bucket` e apaga as chaves anteriores do Garage. É a única rotação **sem reinício e sem
   janela de indisponibilidade**: a aplicação lê essas chaves do banco a cada chamada.

Downtime = o tempo do `systemctl restart` daquela unidade só (poucos segundos; `plat-worker` devolve os
jobs em andamento ao receber `SIGTERM`, `TimeoutStopSec=40`, e o `plat-api` tem `Restart=on-failure`).
Nenhuma outra unidade é tocada — rotacionar `PLAT_DSN_WORKER` nunca reinicia `plat-api` e vice-versa.

**Consequência de rotacionar `PLAT_SECRET` (avisar antes, em produção com usuários ativos):**
- Toda URL assinada de objeto (`app/objetos.py`, HMAC-SHA256 do `PLAT_SECRET`) emitida antes da troca
  para de validar imediatamente — o cliente pede o link de novo, sem novo estado a limpar.
- O `totp_secret` de cada usuário com 2FA ligado está cifrado com o `PLAT_SECRET` anterior
  (`app/auth/totp.py`); depois da troca ele fica ilegível. Isto **já é tratado no código**, não é uma
  falha nova: `app/auth/rotas_login.py` captura a exceção de decifragem e cai para código de
  recuperação (`# segredo ilegível (PLAT_SECRET trocado): só recuperação vale`). A pessoa entra com um
  código de recuperação e recadastra o 2FA. Não há hoje uma janela de dupla-chave (`PLAT_SECRET` +
  `PLAT_SECRET_ANTERIOR`) que evite esse recadastro — ficou de fora deste passe por tamanho; ver §6.

## 3. Prova de que o segredo não está mais no repositório

```
grep -c '^PLAT_SECRET=\|^PLAT_DSN_WORKER=' .env        # 0
sudo stat -c '%a %U' /etc/plat/segredos/PLAT_SECRET     # 600 root
sudo stat -c '%a %U' /etc/plat/segredos/PLAT_DSN_WORKER # 600 root
sudo -u "$(stat -c %U .)" cat /etc/plat/segredos/PLAT_SECRET   # Permission denied — nem o dono do repo lê direto
```

`journalctl -u plat-api -o cat | grep -i PLAT_SECRET` e o mesmo para `plat-worker` continuam vazios
(o middleware de log nunca grava valor de configuração; isso já valia antes deste item).

## 4. Como a suíte de testes ainda usa os dois segredos

`tests/conftest.py` (`valores_env`) e `app/settings.py` (`valores_do_ambiente`) sempre deixam o
**ambiente do processo** vencer o `.env` e o credential. O `Makefile` explora exatamente isso: a
variável `SEGREDOS` lê os dois arquivos com `sudo cat` (o mesmo privilégio que `install.sh` e `make
migrar` já exigem — nenhuma novidade de permissão) e os passa como variável de ambiente só para o
processo filho (`pytest`, `uvicorn` de desenvolvimento), nunca como argumento visível em `ps`:

```makefile
SEGREDOS=PLAT_SECRET="$$(sudo cat /etc/plat/segredos/PLAT_SECRET 2>/dev/null)" PLAT_DSN_WORKER="$$(sudo cat /etc/plat/segredos/PLAT_DSN_WORKER 2>/dev/null)"
teste:
	$(SEGREDOS) $(VENV)/pytest -m "not lento"
```

Isso é só para desenvolvimento/CI local fora do systemd. Em produção o systemd é quem entrega o valor
(§1); nada no código de produção chama `sudo`.

## 5. O que fica de fora deste item (fora de escopo, não esquecido)

- `PLAT_DSN` (senha da role `plat_app`) continua no `.env`. O mesmo raciocínio deste item vale para
  ela; ficou de fora desta passagem porque o pedido foi específico (`PLAT_DSN_WORKER` + `PLAT_SECRET`,
  os dois nomeados no achado do adversário do T2). Item futuro: migrar `PLAT_DSN` do mesmo jeito.
- Chaves S3 do Garage por inquilino e o token admin do Garage (`garage.toml`, hoje em claro) — parte
  maior do backlog original deste item (hipótese completa em `laco/estado.json`), tocam um daemon que
  outra trilha (L0-11) está construindo em paralelo nesta mesma janela; não mexido aqui para não
  colidir.
- Dupla-chave de `PLAT_SECRET` (`PLAT_SECRET` + `PLAT_SECRET_ANTERIOR` por 24h) para rotação sem
  recadastro de 2FA — ver §2.
- CA própria para appliance de cliente (Degrau 0 da plataforma) — não existe cliente com appliance
  ainda.

## 6. Certificado TLS — expiração e renovação

`plat.iagrointel.com` usa Let's Encrypt via `certbot --nginx` (o `install.sh` só chama o certbot quando
`/etc/letsencrypt/live/<domínio>` não existe; depois disso a renovação é inteiramente automática).

Medido em 06/09/2026 (`sudo certbot certificates`):

```
Certificate Name: plat.iagrointel.com
Expiry Date: 2026-12-04 11:19:37+00:00 (VALID: 89 days)
Certificate Path: /etc/letsencrypt/live/plat.iagrointel.com/fullchain.pem
```

Renovação automática já instalada e ativa nesta máquina, comum a **todos** os domínios da casa (não é
específica do `plat`):

```
$ systemctl status certbot.timer
● certbot.timer - Run certbot twice daily
     Loaded: loaded (/usr/lib/systemd/system/certbot.timer; enabled; preset: enabled)
     Active: active (waiting)
    Trigger: <próxima janela em até 12h>
```

`certbot.timer` roda `certbot renew` duas vezes ao dia; `certbot renew` só age em certificados a menos
de 30 dias do vencimento (`renew_before_expiry = 30 days` em
`/etc/letsencrypt/renewal/plat.iagrointel.com.conf`) e, como `authenticator = nginx` e
`installer = nginx`, o próprio certbot reconfigura e recarrega o nginx depois de renovar — não existe
passo manual em operação normal.

**Como conferir manualmente:**
```
sudo certbot certificates                 # data de validade de todo domínio
sudo certbot renew --dry-run              # simula a renovação sem gastar rate limit da Let's Encrypt
```

**Como forçar renovação fora do calendário** (certificado comprometido, mudança de domínio):
```
sudo certbot renew --cert-name plat.iagrointel.com --force-renewal
```

**Alarme antes do vencimento**: não existe hoje (o backlog original deste item propunha um exporter
`blackbox` avisando 14 dias antes — fonte `PROM-blackbox` em `laco/estado.json`); com a renovação
automática em 30 dias de folga o risco real é o *timer* parar (ex.: máquina desligada por mais de 30
dias) — `systemctl status certbot.timer` acima é hoje a única checagem, manual.

## 7. Varredura de dependência com CVE conhecido (item L7-03-f-dependencias-cve-log-correcoes)

`requirements.txt` fixa toda dependência (§ADR 0001 seção 2.1); isso impede deriva de versão, mas por si só
não avisa quando uma versão fixada **ganha** um CVE novo depois de fixada. Este item cobre esse segundo
relógio: `scripts/varredura_dependencias.py` roda `pip-audit` contra `requirements.txt`, classifica cada
achado por severidade e reprova (`make seguranca-deps`) quando há CVE crítico ou alto sem exceção viva.

### 7.1 Por que `pip-audit`, não `safety`

Medido/lido em 06/09/2026 antes de escolher:

| | `pip-audit` 2.10.1 | `safety` (CLI atual, `safety scan`) |
|---|---|---|
| mantenedor | PyPA (mesma organização do `pip`/`packaging`) | pyup.io, empresa |
| licença | Apache-2.0 | MIT no pacote, mas o comando principal (`safety scan`) **exige login/API key** da pyup para o banco de vulnerabilidade atual; o comando antigo sem conta (`safety check`, banco livre) está **descontinuado** pelo próprio projeto |
| fonte de CVE | OSV.dev (agregador aberto, sem chave) | banco proprietário pyup, atrás de conta |
| roda sem credencial nem rede paga | sim | não (a varredura completa exige conta) |
| formato de saída p/ script | `--format json` estável, documentado | também tem `--json`, mas atrás do mesmo gate de conta |

`make seguranca-deps` tem de rodar numa máquina que nunca cadastrou nada (mesmo espírito do §3 do ADR 0001,
"máquina que nunca viu o repo") — um scanner que para de funcionar sem conta paga reprovaria o build por
motivo errado. `pip-audit` não tem esse problema: é só `pip install pip-audit` (pinado em `requirements.txt`)
e roda contra qualquer `requirements.txt`, sem chave.

### 7.2 O que o script faz

```
$ make seguranca-deps
venv/bin/python scripts/varredura_dependencias.py --json var/seguranca/ultima_varredura.json
[      media] idna==3.13  PYSEC-2026-215  fix=['3.15']  (cvss:PYSEC-2026-215=5.3)  ok
varredura_dependencias: nenhum achado grave sem exceção — ok
```

(saída real, MEDIDA em 06/09/2026 contra o `requirements.txt` deste repositório — o único achado hoje é uma
CVE de negação de serviço em `idna` 3.13→3.15, nota CVSS 5.3, classificada "média": não bloqueia.)

Passo a passo (`scripts/varredura_dependencias.py`):

1. `pip-audit -r requirements.txt --format json` (via `venv/bin/pip-audit`, nunca `~/.local`) — lista pacote,
   versão, id do achado (CVE/GHSA/PYSEC), `fix_versions`.
2. **Severidade** de cada achado: primeiro tenta um rótulo pronto (`database_specific.severity` do registro
   OSV.dev do próprio id; quando o id é um `PYSEC-*` sem rótulo, tenta o mesmo campo no *alias* `GHSA-*` —
   MEDIDO: o par `PYSEC-2026-215`/`GHSA-65pc-fj4g-8rjx` da tabela acima só tem o rótulo `"MODERATE"` gravado
   no registro do GHSA, o do PYSEC vem com `database_specific` nulo). Sem rótulo pronto, calcula a nota CVSS
   v3.1 do vetor (`cvss_v3_nota`, fórmula oficial do FIRST, testada contra três vetores publicados em
   `tests/unit/test_varredura_dependencias.py` — inclusive o vetor exato do Log4Shell, nota 10.0) e mapeia
   ≥9,0 crítica / ≥7,0 alta / ≥4,0 média / abaixo baixa. Sem rótulo E sem CVSS (rede fora, ou OSV sem dado) →
   severidade **desconhecida**, tratada como grave por padrão-seguro (nunca passa em silêncio).
3. **Exceção**: um achado grave (crítico/alto/desconhecido) só deixa de bloquear se houver uma entrada viva
   em `docs/excecoes_cve.json` que bata `cve` (id OU qualquer alias) e `pacote`, com `prazo` no futuro —
   depois do prazo a exceção some sozinha e o achado volta a bloquear, sem editar nada.
4. Sai `0` (nada grave sem exceção), `1` (bloqueia — CI/terminal veem o motivo) ou `2` (o próprio `pip-audit`
   não rodou: binário ausente, timeout, `requirements.txt` inexistente — nunca vira silenciosamente "0 CVE").

Cache local do OSV em `var/cache/osv/<id>.json` (gitignorado): a 2ª execução do dia não bate a rede de novo
para o mesmo achado.

### 7.3 Como abrir uma exceção

```json
{
  "excecoes": [
    {"cve": "GHSA-xxxx-yyyy-zzzz", "pacote": "nome-do-pacote", "motivo": "sem versão corrigida ainda / correção quebra X",
     "prazo": "2026-10-15", "registrado_em": "2026-09-06", "quem": "quem decidiu"}
  ]
}
```

Em `docs/excecoes_cve.json`. `cve` casa com o id do achado OU qualquer alias (CVE/GHSA/PYSEC costumam
apontar para o mesmo problema); `prazo` é obrigatório na prática — sem ele a exceção nunca expira sozinha,
o que o portão deste item não permite ficar sem revisão.

### 7.4 `make seguranca-deps` é opcional hoje, não bloqueia `make check`

Por decisão explícita desta passagem (item pequeno, entrega de hoje): o alvo existe e funciona, mas **não**
está na cadeia de `check`/`check-rapido` ainda — rodar `make seguranca-deps` é manual (ou de um timer futuro
diário, ainda não construído nesta passagem). Ligar ao `check` principal é o próximo passo natural do item,
registrado aqui para não se perder: nesta janela o risco de um `pip-audit` que depende de rede (OSV.dev)
bloquear o `check` de todo mundo, numa hora ruim de rede, pesou mais que o ganho de rodar em toda passagem.

### 7.5 Log de correções

Tabela viva, preenchida à mão a cada correção de CVE aplicada (formato pronto; começa vazia — nenhuma
correção foi necessária ainda, o único achado de hoje, §7.2, é média e não crítica/alta):

| CVE | pacote | versão corrigida | data | quem aplicou |
|---|---|---|---|---|
| _(vazio — primeira correção entra aqui)_ | | | | |


## 8. Varredura de conteúdo em upload de anexo (item L7-03-b-antivirus-anexos)

Pedido do dono: os dois caminhos de upload de anexo do catálogo — `POST /api/arquivos` (L0-11-arquivos-
objetos) e `POST /api/itens/{id}/miniatura` (L0-03-catalogo) — precisavam de varredura de conteúdo. Medido
antes de construir: **L0-11 aceitava qualquer sequência de bytes sob o `Content-Type` que o cliente
declarasse** (a extensão/tipo é escolha de quem envia; nada conferia se o CONTEÚDO batia) — essa é a lacuna
real que este item fecha com uma camada mínima (`app/varredura_conteudo.py`) na espera de um motor melhor
(ClamAV, ver §8.1). **L0-03 (miniatura) já tinha barreira antes deste item** — `miniatura.normalizar()`
decodifica os bytes com Pillow e SÓ aceita PNG/JPEG/GIF de verdade, reencodando para um PNG novo sem
metadado; é mais forte que checar assinatura de bytes, então este item formaliza isso como a resposta de
L0-03 em vez de duplicar a checagem (ver §8.2, por que duplicar quebraria um teste do L0-11 sem ganhar nada).

### 8.1 Por que não é ClamAV nesta passagem — D21

`laco/estado.json` já tem D21 aberta desde 05/09/2026 ("disco: os dois servidores estão a 98%... qualquer dado
de rede/imagem além disso exige decisão"). MEDIDO de novo em 06/09/2026, antes de decidir por esta passagem:

```
$ df -h / /mnt/pgdata
/dev/vda2  469G  452G   13G  98% /
/dev/vdb   688G  675G   14G  99% /mnt/pgdata
$ free -h
               total   used   free  shared  buff/cache  available
Mem:            23Gi    20Gi  323Mi    6.1Gi        9.2Gi        3.1Gi
Swap:          8.0Gi   8.0Gi  248Ki
```

O pacote `clamav-daemon` em si é pequeno (~1 MB instalado); o custo real é a base de assinaturas do
`freshclam` (`main.cvd`+`daily.cvd`+`bytecode.cvd`), que o `clamd` mantém **carregada em RAM** — na ordem de
1,3-1,5 GiB residentes, a mesma estimativa que a hipótese original do item já registrava. Com 323 MiB livres e
o swap (8 GiB) inteiro já ocupado, subir `clamd` agora tem risco real e concreto de repetir o incidente já
registrado na casa (`reference_oom-derrubou-postgres`: 20 sessões de 370 MiB cada derrubaram o Postgres
compartilhado). Por decisão desta passagem — dentro do espírito de D21, não uma decisão nova —
**ClamAV fica de fora até o disco/RAM da máquina mudar** (D21 resolver, ou servidor dedicado do D37).

### 8.2 A camada que fica no lugar (versão de 06/09/2026, depois da refutação)

A primeira versão desta camada comparava só "família declarada x tipo devolvido pelo `libmagic`" e foi
**REFUTADA por adversário independente** no mesmo dia (laço, handoff T3, achados 22-25): o polyglot passava
(arquivo que COMEÇA com assinatura de imagem válida e carrega script depois recebe do `libmagic` exatamente a
família declarada); `Content-Type` fora da tabela significava "não examinar", ou seja, quem decidia se a
varredura rodava era o remetente; só os primeiros 8 KiB eram olhados; e zip/kmz não era aberto. `app/
varredura_conteudo.py` agora roda cinco checagens, na ordem abaixo, e a primeira que recusar decide:

| # | checagem | o que pega |
|---|---|---|
| 1 | família declarada x tipo real (`TIPOS_PERMITIDOS`, mesmas chaves de `app/objetos.EXTENSOES`) | script puro declarado `image/jpeg`; zip declarado `application/pdf` |
| 2 | lista de NEGAÇÃO determinística, válida sob QUALQUER `Content-Type` (inclusive vazio, inventado e `application/octet-stream`): shebang no início, assinatura de executável conferida à mão, tipo real de script/HTML quando os bytes são texto | script declarado `text/plain`, `text/html` ou `application/x-inventado`; ELF/PE sob tipo genérico |
| 3 | busca de carga executável no CORPO INTEIRO entregue pelo chamador (`<script`, `<iframe`, `<?php`, `<!doctype html`, `#!/bin/`, `#!/usr/`), com emenda entre as partes do multipart | polyglot imagem+script; carga além dos 8 KiB |
| 4 | integridade estrutural de imagem: PNG termina no chunk `IEND`, JPEG no marcador `FFD9`, GIF no byte `0x3B`; byte depois do fim = recusa | qualquer coisa colada depois de uma imagem válida, mesmo carga que não está na lista da linha 3 |
| 5 | lista de entradas do zip/kmz: extensão de script/executável, ou entrada cujo conteúdo começa com shebang | `carga.sh` dentro de um kmz |

**Tipo declarado desconhecido virou rigor máximo, não isenção.** Antes, `TIPOS_PERMITIDOS.get(declarado, None)`
devolvia `None` para qualquer tipo fora da tabela e `None` queria dizer "não examinar". Agora `None` quer dizer
só "não há família para comparar na linha 1"; as linhas 2-5 valem para todo mundo. A rota `POST /api/arquivos`
continua aceitando `Content-Type` fora de `app/objetos.EXTENSOES` (a suíte envia `text/plain`, e a chave no
Garage cai na extensão `.bin`), mas esse arquivo é varrido com o mesmo rigor e é ENTREGUE de volta como anexo
genérico (§8.6).

**A armadilha que a regra tem de contornar, e como.** MEDIDO nesta máquina: `libmagic` classifica ~0,9% de
bytes PURAMENTE ALEATÓRIOS (18/2000 amostras de 4 KiB) como algo diferente de `application/octet-stream`,
inclusive `application/x-dosexec` por coincidência de assinatura. Recusar pelo RÓTULO faria o upload binário
legítimo (CAD, dado proprietário, e o `os.urandom` que a própria suíte envia) reprovar de vez em quando — o
oposto de P5 (reprodutível) e de P3 (suíte sempre verde). Por isso nenhuma checagem depende do rótulo para
binário:

- família de executável só recusa com a assinatura mágica REAL no início dos bytes: `\x7fELF`, Mach-O, Wasm,
  Dalvik e `MZ` **com o `PE\0\0` conferido no deslocamento que o próprio arquivo declara em 0x3C** (dois bytes
  `MZ` sozinhos aparecem por acaso em 1 de cada 65 mil blocos aleatórios; o `PE\0\0` fecha isso);
- família de script/HTML só recusa quando os bytes são texto de verdade (sem byte nulo e decodificáveis em
  UTF-8, ou 99% de ASCII imprimível) — 4 KiB aleatórios não passam nessa porta;
- todo padrão da busca de carga tem 5 bytes ou mais (o mais curto, `<?php`, dá probabilidade da ordem de 3e-8
  por amostra de 4 KiB);
- o shebang exige `#!` mais um caminho ASCII plausível na primeira linha, nunca os dois bytes sozinhos.

`tests/unit/test_varredura_conteudo_polyglot.py` roda 300 amostras aleatórias sob `application/octet-stream` e
100 sob `text/plain` justamente para que uma regra que volte a depender de sorte comece a falhar.

**Quanto do arquivo é varrido, honestamente.** A varredura só enxerga o que o chamador entrega. `POST /api/
arquivos` entrega o corpo inteiro quando ele cabe em uma parte (`limites.ARQUIVO_BUFFER_UNICO_BYTES`, 8 MiB) e,
acima disso, parte por parte (8 MiB de cada vez, com 32 bytes de emenda entre elas), sem nunca carregar o
arquivo inteiro em RAM. As checagens 1, 2, 4 e 5 valem sobre a primeira parte; a 3 vale sobre o corpo inteiro.
Um zip de mais de 8 MiB não tem o diretório central na primeira parte: a checagem 5 não dá veredito nele (as
outras continuam valendo) — é o limite declarado desta camada, não um esquecimento.

Onde a varredura entra (nunca depois de já ter gasto uma chamada ao Garage) — **de propósito na BORDA, não
dentro de `objetos.guardar()`**: esse adaptador é genérico (ADR 0004/0006) e também é chamado com conteúdo já
validado por outro meio (miniatura) ou sintético (a própria suíte grava `b"abc"` sob `image/png` em
`tests/api/catalogo/test_miniatura.py::test_adaptador_de_objetos_e_url_assinada` para testar só o contrato de
armazenamento) — varrer ali quebraria esse teste sem ganhar segurança nenhuma (o conteúdo real de produção
que chega em `guardar()` pela miniatura já passou por uma validação mais forte, ver linha 3 da tabela):

| caminho | onde a varredura corre | quem varre |
|---|---|---|
| `POST /api/arquivos`, arquivo pequeno (1 PUT só) | em `enviar()`, logo antes de chamar `objetos.guardar()`, sobre o corpo inteiro | `app/rotas_arquivos.py::enviar` |
| `POST /api/arquivos`, arquivo grande (multipart) | na 1ª parte, antes de `objetos.parte_iniciar`; nas partes seguintes, busca de carga com emenda entre blocos | `app/rotas_arquivos.py::enviar` |
| `POST /api/itens/{id}/miniatura` | não chama `app/varredura_conteudo.py` — a barreira já é `miniatura.normalizar()` (Pillow decodifica pixel real e reencoda para PNG limpo; mais forte que assinatura de bytes, existia antes deste item) | `app/catalogo/miniatura.py` |

`ConteudoRecusado` (exceção de `app/varredura_conteudo.py`, reexportada por `app/objetos.py` como
`objetos.ConteudoRecusado`, mesmo padrão de `objetos.CotaExcedida`) vira `415 conteudo_recusado` com
`detalhe.tipo_detectado` na rota de `POST /api/arquivos`.

### 8.3 O gancho para trocar por ClamAV depois

`app/varredura_conteudo.py` define `Motor` (`Protocol`, um único método `escanear(cabecalho, content_type) ->
Resultado`) e `MOTOR_ATIVO` (hoje `MotorAssinaturaBasica()`). Um `MotorClamAV` futuro implementa a mesma
interface (fala com `clamd` por socket unix — `INSTREAM` do protocolo do ClamAV, que também só precisa dos
primeiros bytes até achar o marcador de fim, não do arquivo inteiro) e troca `MOTOR_ATIVO`; nenhuma das três
rotas do §8.2 muda — todas conhecem só `escanear_cabecalho()`.

### 8.4 Teste do portão

```
$ pytest tests/unit/test_varredura_conteudo.py tests/unit/test_varredura_conteudo_polyglot.py \
         tests/adversario/test_g6_varredura_anexos.py tests/api/test_arquivos.py
```

Os quatro grupos que o adversário deixou como `xfail(strict=True)` em
`tests/adversario/test_g6_varredura_anexos.py` passaram a reprovar de verdade em 06/09/2026 e a marca saiu
(polyglot GIF/JPEG/PNG + script; script sob `text/html`, `application/x-inventado`, `""` e `text/plain`; carga
além de 8 KiB; `carga.sh` dentro de um kmz). O registro do ataque ficou no arquivo, como comentário.

`test_extensao_jpg_com_conteudo_de_script_e_recusado` (unitário) e `test_api_recusa_script_disfarcado_de_jpeg`
(fim a fim, API real): `Content-Type: image/jpeg` com corpo `#!/bin/sh\necho pwned\n` → `415 conteudo_recusado`,
`tipo_detectado: text/x-shellscript`. `test_api_recusa_script_grande_disfarcado_de_png_antes_do_multipart` prova
o mesmo acima do teto de uma parte (nunca abre multipart no Garage para um conteúdo já recusado).

### 8.5 O que fica de fora desta passagem (não esquecido)

- ClamAV de verdade — §8.1, D21. Nada aqui procura assinatura de malware conhecido: esta camada recusa CLASSE
  de conteúdo (script, executável, HTML, imagem com carga colada), não vírus por nome.
- Do zip/kmz é aberta a LISTA de entradas (nome e primeiros bytes de cada uma), não o conteúdo de cada entrada
  inteira; e só quando o pacote cabe na primeira parte do envio (8 MiB), porque acima disso o diretório central
  do zip não está no que o chamador entrega.
- A busca de carga é por padrão literal em texto: conteúdo malicioso ofuscado ou comprimido dentro de um
  formato binário legítimo não é alcançado por ela (é o que ClamAV faria).
- O preço da checagem 3, declarado: um arquivo LEGÍTIMO que carregue um desses padrões literalmente (uma
  coluna de CSV com `<script`, um PDF com JavaScript embutido) é recusado com `415 conteudo_recusado` e a
  mensagem diz qual padrão e em que deslocamento. É escolha desta camada — o mesmo padrão é a carga de XSS
  quando o arquivo volta pelo navegador — e não há exceção por inquilino; se um cliente real precisar enviar
  esse conteúdo, a decisão volta ao dono, não se afrouxa a regra em silêncio.
- O caminho de sincronização da PWA de campo (L2-07, ainda não construído) precisará da mesma barreira quando
  existir; `objetos.guardar()` já cobre automaticamente qualquer chamador futuro que passe por ele.

### 8.6 Entrega segura: o conteúdo do cliente volta como anexo, nunca como página

Medido pelo adversário no mesmo ataque (achado 23, cadeia): `GET /api/arquivos/{sha256}` devolvia o conteúdo
com `media_type=r["content_type"]` — o MESMO `Content-Type` que o remetente escolheu — e sem
`Content-Disposition`. Um arquivo enviado como `text/html` voltava renderizando como HTML na própria origem da
aplicação, onde a sessão do usuário vale; `X-Content-Type-Options: nosniff` não resolve esse caso, porque o
tipo declarado É `text/html` (não há adivinhação para desligar).

`app/entrega_conteudo.py` aplica três regras juntas em toda rota que devolve byte que veio de fora:

1. **tipo de mídia por lista fechada**: só os tipos de `app/objetos.EXTENSOES` voltam como foram declarados;
   qualquer outro — `text/html`, `application/xhtml+xml`, `image/svg+xml`, JavaScript, tipo inventado — é
   rebaixado para `application/octet-stream`. Lista fechada, não lista de proibidos: tipo novo já nasce
   rebaixado, sem ninguém precisar lembrar de acrescentá-lo.
2. **`Content-Disposition: attachment`** com nome saneado, nas duas formas da RFC 6266 (`filename=` só ASCII e
   `filename*=UTF-8''...` da RFC 5987).
3. **`X-Content-Type-Options: nosniff`**.

| rota | tratamento |
|---|---|
| `GET /api/arquivos/{sha256}` | tipo da lista fechada + anexo + nosniff |
| `GET /api/objetos/{chave}` (URL assinada, anônima) | tipo da lista fechada + anexo + nosniff |
| `GET /api/itens/{id}/miniatura` (e as variantes pública/compartilhada) | só nosniff: o conteúdo é um PNG REDESENHADO pelo Pillow, nunca os bytes do cliente, e é servido dentro de `<img>` na aplicação — forçar download quebraria a tela sem fechar risco nenhum |
