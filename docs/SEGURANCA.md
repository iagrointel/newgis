# Segurança — segredos e certificados

Item L7-19-segredos-e-certificados. Esta seção é o mapa: onde cada segredo mora, como rotacionar sem
derrubar o produto, e como o certificado TLS se renova sozinho. Ela não repete o que já está no
`docs/adr/0001-fundacao.md` seção 8 (contrato de `.env`) — só o que mudou e o que é operação.

## 1. Onde cada segredo mora

| segredo | onde mora hoje | quem lê | dono do arquivo | modo |
|---|---|---|---|---|
| `PLAT_SECRET` | `/etc/plat/segredos/PLAT_SECRET` | `plat-api`, `plat-worker` (via `LoadCredential=`) | root | 0600, diretório 0700 |
| `PLAT_DSN_WORKER` (senha da role `plat_worker`) | `/etc/plat/segredos/PLAT_DSN_WORKER` | `plat-worker` (via `LoadCredential=`) | root | 0600 |
| `PLAT_DSN` (senha da role `plat_app`) | `.env` na raiz do repositório | `plat-api` | dono do repositório (`APP_USER`) | 0600 — **fora do escopo deste item**, ver §5 |
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

## 2. `scripts/rotacionar_segredo.sh` — rotação sem reinstalar

```
sudo bash scripts/rotacionar_segredo.sh PLAT_SECRET
sudo bash scripts/rotacionar_segredo.sh PLAT_DSN_WORKER
```

O que cada rotação faz, em ordem (a ordem importa: nunca existe um instante em que o serviço novo suba
com um segredo que o outro lado — banco ou processo — ainda não aceita):

1. **`PLAT_DSN_WORKER`**: gera senha nova (`openssl rand -hex 16`) → `ALTER ROLE plat_worker PASSWORD`
   no banco **primeiro** → grava o DSN novo em `/etc/plat/segredos/PLAT_DSN_WORKER` → confere que a
   senha **antiga** já não autentica mais (tenta conectar com ela e exige falha) → `systemctl restart
   plat-worker` → espera `/saude` responder 200 (mesmo laço de espera do `install.sh`).
2. **`PLAT_SECRET`**: gera valor novo (`openssl rand -hex 32`) → grava em
   `/etc/plat/segredos/PLAT_SECRET` → `systemctl restart plat-api` → espera `/saude` responder 200.

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
