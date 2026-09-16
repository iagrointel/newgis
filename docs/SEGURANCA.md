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
está na cadeia de `check`/`check-rapido` ainda — rodar `make seguranca-deps` é manual. Ligar ao `check`
principal é o próximo passo natural do item, registrado aqui para não se perder: nesta janela o risco de um
`pip-audit` que depende de rede (OSV.dev) bloquear o `check` de todo mundo, numa hora ruim de rede, pesou
mais que o ganho de rodar em toda passagem. (`make seguranca`/HARD-01, esse sim dentro de `check`, já roda
pip-audit como uma das cinco ferramentas — mas com a política de exceção do §9.2, não com o nome
`seguranca-deps`; ver §7.6 para o que passou a rodar 1×/dia independente do `check`.)

### 7.5 Log de correções — GERADO, não mais escrito à mão

Superado pelo §7.6: até esta passagem esta seção era uma tabela em branco preenchida manualmente. Agora é
`docs/CORRECOES.md` (arquivo próprio, `make correcoes`), lido de `plat.vulnerabilidade` — a versão escrita à
mão nunca chegou a ganhar uma linha, então nada se perde na troca.

### 7.6 Banco, job diário, `/status` e `docs/CORRECOES.md` (turno de fechamento do item)

O que faltava — registrado no bloqueio de `laco/estado.json`: "sem plat.vulnerabilidade, sem
docs/CORRECOES.md, sem timer, sem /status e fora do make check". Fechado nesta passagem, com o que já
existia (pip-audit do §7.2 acima; `npm audit` do item HARD-01 §9, `scripts/varredura_seguranca.py::rodar_npm`
— reaproveitado, não duplicado):

- **`plat.vulnerabilidade`** (uma linha por achado; nunca apagada — `resolvida_em` fica `NULL` enquanto
  aberto e ganha data quando o pacote/CVE some de uma varredura para a próxima) e **`plat.varredura_cve`**
  (uma linha por execução: quando, rc, duração, resumo) — `db/migracoes/20260915T2252_vulnerabilidade.sql`.
  Sem `tenant_id` (telemetria da instalação, como `plat.status_amostra`); `plat_app` só lê, a escrita é só
  pela função SECURITY DEFINER `plat.varredura_cve_registrar()`. Uma fonte que não rodou (sem rede) nunca
  fecha um achado por ausência — só quem rodou de verdade pode dizer que um CVE sumiu por correção.
- **`scripts/varredura_cve.py`** — `rodar()` (pip-audit + npm audit, sem tocar banco, testável por dublê) e
  `main()`/`persistir()` (grava). **`app/jobs/seguranca.py`** — mesma varredura, registrada como tipo de job
  `seguranca.varrer_cve` e no periódico interno (`app/jobs/periodicos.py`, 05:20 diário, sincronizado no
  inquilino técnico `plataforma` — ADR 0003 §7). **`deploy/plat-varredura-cve.timer` + `.service`** — mesmo
  espírito de `deploy/plat-segredo-expira.timer`: caminho independente da fila, para quando o worker está
  fora do ar (LoadCredential=PLAT_DSN; `SuccessExitStatus=0 1 2` — rc 2 é "uma fonte não rodou", resultado
  válido do script, não falha da unidade). **Arquivos só; não habilitado por este turno** — para ligar:
  ```
  sudo cp deploy/plat-varredura-cve.{timer,service} /etc/systemd/system/
  sudo sed -i "s|APP_DIR|$(pwd)|; s|APP_USER|$(whoami)|" /etc/systemd/system/plat-varredura-cve.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now plat-varredura-cve.timer
  ```
- **`/api/status`** ganha o bloco `vulnerabilidades: {abertas, estado, ultima_varredura, fonte}` (função
  `plat.status_vulnerabilidades()`, agregado — nunca pacote/CVE individual numa rota sem sessão); `estado` é
  `"nunca_rodou"` / `"ok"` / `"falhou"` (rc da última execução) — é isso que fecha a cláusula "página /status
  mostra o último ciclo" do portão.
- **`docs/CORRECOES.md`** (`docs/gerar_correcoes.py`, `make correcoes`) — o log de correções de verdade: uma
  linha por achado com aviso/pacote/versão/gravidade/detectada/resolvida, gerado do banco (cai para o último
  instantâneo em `var/seguranca/ultima_varredura_cve.json` quando o banco não responde na hora da geração).
  **Fora de `check`/`check-rapido`** por decisão explícita (comentário no próprio `Makefile`, mesmo espírito
  do §7.4): a geração bate no banco vivo a cada chamada, e não há motivo para pagar essa consulta em toda
  passagem de `check` só para um documento que muda quando uma varredura nova roda, não a cada commit.
- Testes: `tests/unit/test_varredura_cve.py` (rodar() com pip-audit/npm dublados; ciclo aberto→resolvido e
  "fonte sem rede não resolve por ausência" contra a trilha corrente; `docs/gerar_correcoes.py` determinístico
  com dados fixos).
- **O que fica de fora, nomeado**: `osv-scanner`, `trivy` (CVE de imagem — `trivy config` de má configuração
  em `deploy/` já roda dentro de `make seguranca`/HARD-01 §9) e `gitleaks` continuam ausentes desta varredura
  específica — nenhum dos três está instalado nesta máquina (rule do dono: não instalar ferramenta nova sem
  o dono), e `gitleaks`/`trivy` (imagem) já são cobertos por `make seguranca`/HARD-01 §9, que é quem instala
  os binários fixados de `deploy/ferramentas_binarias.txt`. `seguranca-deps`/pip-audit isolado (§7.4) continua
  fora de `check`; o que passou a rodar dentro de `check` é `make seguranca` (HARD-01), que já inclui
  pip-audit e npm audit desde antes desta passagem.


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

### 8.2 A camada mínima que fica no lugar

`app/varredura_conteudo.py`: identifica o tipo REAL do arquivo pelos primeiros `CABECALHO_BYTES` (8 KiB, o
bastante para `libmagic`/`python3-magic` decidir — já dpkg nesta máquina, ver `deploy/pacotes_apt.txt` do item
L7-14/L0-04-a, que o cita pelo mesmo motivo: "confere o tipo declarado no upload contra o que o arquivo
realmente é") e recusa quando o tipo detectado não bate com a família esperada do `Content-Type` declarado
(`TIPOS_PERMITIDOS`, mesmas chaves de `app/objetos.EXTENSOES`). Isso já cobre o polyglot óbvio do portão: um
arquivo com assinatura de imagem que também é reconhecido como HTML/script continua batendo a checagem porque
o tipo que o `libmagic` reconhece primeiro já não é o da família declarada.

**Por que NÃO existe também um denylist "tipo perigoso, seja qual for o `Content-Type`"** — MEDIDO antes de
escrever a regra (`tests/unit/test_varredura_conteudo.py::test_binario_generico_aleatorio_nunca_e_recusado_
por_assinatura`): `libmagic` classifica ~0,9% de bytes PURAMENTE ALEATÓRIOS (18/2000 amostras de 4 KiB) como
algo diferente de `application/octet-stream`, inclusive `application/x-dosexec` por coincidência de assinatura.
Um denylist que valesse mesmo sob `Content-Type` genérico reprovaria upload binário legítimo (CAD, dado
proprietário) ao acaso — o oposto de P5 (reprodutível) e P3 (suíte sempre verde). Por isso o `Content-Type`
genérico (`application/octet-stream`) passa sem exame de assinatura nesta camada: é exatamente onde ClamAV
faria a diferença de verdade (assinatura de conteúdo malicioso conhecido, não heurística de tipo).

Onde a varredura entra (nunca depois de já ter gasto uma chamada ao Garage) — **de propósito na BORDA, não
dentro de `objetos.guardar()`**: esse adaptador é genérico (ADR 0004/0006) e também é chamado com conteúdo já
validado por outro meio (miniatura) ou sintético (a própria suíte grava `b"abc"` sob `image/png` em
`tests/api/catalogo/test_miniatura.py::test_adaptador_de_objetos_e_url_assinada` para testar só o contrato de
armazenamento) — varrer ali quebraria esse teste sem ganhar segurança nenhuma (o conteúdo real de produção
que chega em `guardar()` pela miniatura já passou por uma validação mais forte, ver linha 2 da tabela):

| caminho | onde a varredura corre | quem varre |
|---|---|---|
| `POST /api/arquivos`, arquivo pequeno (1 PUT só) | em `enviar()`, logo antes de chamar `objetos.guardar()` | `app/rotas_arquivos.py::enviar` |
| `POST /api/arquivos`, arquivo grande (multipart) | na 1ª parte do streaming, antes de `objetos.parte_iniciar` | `app/rotas_arquivos.py::enviar` |
| `POST /api/itens/{id}/miniatura` | não chama `app/varredura_conteudo.py` — a barreira já é `miniatura.normalizar()` (Pillow decodifica pixel real e reencoda para PNG limpo; mais forte que assinatura de bytes, existia antes deste item) | `app/catalogo/miniatura.py` |

`ConteudoRecusado` (nova exceção em `app/varredura_conteudo.py`, reexportada por `app/objetos.py` como
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
$ pytest tests/unit/test_varredura_conteudo.py tests/api/test_arquivos.py -k "script or disfarcado" -v
```

`test_extensao_jpg_com_conteudo_de_script_e_recusado` (unitário) e `test_api_recusa_script_disfarcado_de_jpeg`
(fim a fim, API real): `Content-Type: image/jpeg` com corpo `#!/bin/sh\necho pwned\n` → `415 conteudo_recusado`,
`tipo_detectado: text/x-shellscript`. `test_api_recusa_script_grande_disfarcado_de_png_antes_do_multipart` prova
o mesmo acima do teto de uma parte (nunca abre multipart no Garage para um conteúdo já recusado).

### 8.5 O que fica de fora desta passagem (não esquecido)

- ClamAV de verdade — §8.1, D21.
- Varredura de conteúdo dentro de arquivos compostos (abrir o zip do KMZ e varrer cada entrada) — hoje só o
  contêiner externo é conferido.
- O caminho de sincronização da PWA de campo (L2-07, ainda não construído) precisará da mesma barreira quando
  existir; `objetos.guardar()` já cobre automaticamente qualquer chamador futuro que passe por ele.


## 9. Varredura de segurança contínua (item HARD-01-varredura-de-seguranca-continua)

`make seguranca` (dentro de `make check`, o portão da fila de junção) roda `scripts/varredura_seguranca.py`: bandit
(análise estática do Python que roda), pip-audit (§7, delegado), `npm audit` sobre as bibliotecas de `web/vendor/`,
gitleaks sobre o HISTÓRICO inteiro do git, trivy sobre `deploy/` (e sobre a imagem `plat-worker:local` quando ela
existe na máquina) e, em `make seguranca-zap`, o baseline do OWASP ZAP (spider + regras passivas, nunca varredura
ativa) contra uma instância que o próprio script sobe e derruba — uvicorn + nginx renderizado de
`deploy/nginx.conf`, no ambiente de uma trilha, nunca produção. Ferramentas binárias fixadas por versão e sha256 em
`deploy/ferramentas_binarias.txt`, instaladas por `scripts/ferramentas_seguranca.sh` no cache do usuário
(`~/.cache/plat/ferramentas`), nunca no PATH da máquina; bandit e pip-audit vêm de `requirements.txt`.

Um achado que a política (§9.2) classifica como bloqueante só deixa de reprovar com uma exceção viva em
`docs/excecoes_seguranca.json` — cada linha com motivo, prazo, data de registro e responsável; passado o prazo a
exceção some sozinha e o achado volta a bloquear. O que segue entre os marcadores é GERADO por
`make seguranca-gravar` a partir de `tests/medidas/HARD-01-seguranca.json`, da lista de exceções e da lista de
binários; `make seguranca` confere (`--check-doc`) que a seção versionada bate com essas fontes.

<!-- inicio: gerado por scripts/varredura_seguranca.py — não editar à mão -->

### 9.1 Última varredura registrada

Registrada em 2026-09-07T21:25+00:00 (commit `874d7df5`, carga 1 min 14.38916015625, RAM livre 6.6 GB) por `make seguranca-gravar`. Resultado: **verde**.

| ferramenta | versão | achados | bloqueiam | com exceção | revisão | informativos | duração |
|---|---|---|---|---|---|---|---|
| bandit | 1.9.4 | 153 | 0 | 7 | 36 | 110 | 1.9 s |
| pip-audit | 2.10.1 | 1 | 0 | 0 | 0 | 1 | 7.2 s |
| npm | 10.9.7 | 0 | 0 | 0 | 0 | 0 | 0.8 s |
| gitleaks | 8.30.1 | 0 | 0 | 0 | 0 | 0 | 2.5 s |
| trivy | 0.74.0 | 1 | 0 | 1 | 0 | 0 | 0.9 s |
| zap | 2.17.0 | 7 | 0 | 2 | 0 | 5 | 17.6 s |

trivy: imagem `plat-worker:local` ausente nesta máquina — só deploy/ (Dockerfile e compose) foi varrido.

zap: instância própria (uvicorn + nginx renderizado de deploy/nginx.conf), com sessão autenticada no inquilino demo; só regras passivas.

### 9.2 Política de bloqueio

| ferramenta | regra |
|---|---|
| bandit | HIGH (qualquer confiança) ou MEDIUM com confiança HIGH bloqueia; MEDIUM com confiança menor = revisão; LOW = informativo |
| pip-audit | crítica/alta/desconhecida sem exceção em docs/excecoes_cve.json bloqueia (regra do item L7-03-f) |
| npm | critical/high bloqueia; moderate/low = informativo |
| gitleaks | todo achado bloqueia (regras padrão + .gitleaks.toml) |
| trivy | CRITICAL/HIGH bloqueia; MEDIUM = revisão; imagem só quando plat-worker:local existe na máquina |
| zap | High/Medium bloqueia; Low/Informational = informativo; só regras passivas, nunca varredura ativa |

### 9.3 Exceções vivas (docs/excecoes_seguranca.json)

| ferramenta | id | alvo | motivo | prazo | dias | registrada | quem |
|---|---|---|---|---|---|---|---|
| bandit | B310 | `app/saude.py` | urlopen com URL fixada em código (Garage/serviços locais em http://127.0.0.1); nenhuma parte da URL vem de entrada externa. Reavaliar ao trocar por httpx, que já é dependência. | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| bandit | B310 | `docs/xsd/baixar_iso19139.py` | script de manutenção baixa o XSD oficial de URL https fixada em código; roda à mão, nunca na API. | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| bandit | B310 | `scripts/prova_garage_chave_s3.py` | prova do item L7-19 contra http://127.0.0.1 fixado; não é caminho de produto. | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| bandit | B310 | `scripts/prova_segredos_l7_19.py` | prova do item L7-19 contra http://127.0.0.1 fixado; não é caminho de produto. | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| bandit | B310 | `scripts/segredo_rotacionar.py` | mede /saude e a Admin API do Garage em http://127.0.0.1 fixado durante a rotação (L7-19); esquema nunca vem de fora. | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| bandit | B310 | `scripts/varredura_dependencias.py` | consulta https://api.osv.dev fixada em código (L7-03-f); o id do CVE entra só no caminho, nunca no esquema/host. | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| trivy | DS-0002 | `deploy/Dockerfile.worker` | o contêiner parte como root DE PROPÓSITO e solta privilégio para `plat` via setpriv no entrypoint antes de importar o worker (comentário no próprio Dockerfile, item L0-05-e); trivy só vê a ausência de `USER`. | 2027-03-07 | 181 | 2026-09-07 | HARD-01 (líder de endurecimento) |
| zap | 10055 | `/api/docs` | swagger-ui em /api/docs arranca por script inline gerado pelo FastAPI (get_swagger_ui_html, sem nonce); o CSP desse bloco do nginx libera 'unsafe-inline' SÓ ali. Saída: servir o arranque como arquivo de web/vendor e tirar o unsafe-inline (candidato a item HARD). | 2026-12-06 | 90 | 2026-09-07 | HARD-01 (líder de endurecimento) |

### 9.4 Achados em revisão (não bloqueiam; lista de trabalho do adversário, item HARD-03)

- `bandit B608 app/acervo/rotas.py:166`
- `bandit B608 app/acervo/rotas.py:79`
- `bandit B608 app/acervo/rotas.py:82`
- `bandit B608 app/acervo/rotas.py:96`
- `bandit B608 app/auth/rotas_grupos.py:94`
- `bandit B608 app/auth/rotas_log.py:101`
- `bandit B608 app/auth/rotas_log.py:104`
- `bandit B608 app/auth/rotas_log.py:192`
- `bandit B608 app/auth/rotas_log.py:195`
- `bandit B608 app/auth/rotas_usuarios.py:349`
- `bandit B608 app/catalogo/miniatura.py:160`
- `bandit B608 app/catalogo/miniatura.py:173`
- `bandit B608 app/catalogo/rotas_itens.py:469`
- `bandit B608 app/catalogo/rotas_itens.py:475`
- `bandit B608 app/catalogo/rotas_itens.py:581`
- `bandit B608 app/catalogo/rotas_itens.py:725`
- `bandit B608 app/conexao/rotas.py:126`
- `bandit B608 app/conexao/rotas.py:200`
- `bandit B608 app/conexao/rotas.py:58`
- `bandit B608 app/ingestao/carregar.py:154`
- `bandit B608 app/ingestao/carregar.py:205`
- `bandit B608 app/ingestao/carregar.py:213`
- `bandit B608 app/ingestao/carregar.py:217`
- `bandit B608 app/ingestao/carregar.py:230`
- `bandit B608 app/ingestao/carregar.py:234`
- `bandit B608 app/ingestao/carregar.py:248`
- `bandit B608 app/ingestao/carregar.py:264`
- `bandit B608 app/ingestao/carregar.py:270`
- `bandit B608 app/ingestao/carregar.py:303`
- `bandit B608 app/ingestao/inspecionar.py:67`
- `bandit B608 app/jobs/servico.py:191`
- `bandit B608 app/jobs/servico.py:203`
- `bandit B608 app/jobs/servico.py:249`
- `bandit B608 app/jobs/servico.py:251`
- `bandit B608 app/jobs/servico.py:295`
- `bandit B608 scripts/acervo_sync.py:121`

### 9.6 Ferramentas binárias fixadas (deploy/ferramentas_binarias.txt)

| ferramenta | versão | sha256 do pacote |
|---|---|---|
| gitleaks | 8.30.1 | `551f6fc83ea457d6…` |
| trivy | 0.74.0 | `2ae6fe3ee734b7fd…` |
| zap | 2.17.0 | `efe799aaa3627db6…` |

<!-- fim: gerado por scripts/varredura_seguranca.py -->

## 10. Injeção em consulta: fechada por construção (item L7-03-d-injecao-consulta)

O `where` do FeatureServer e o `havingClause` passam por `app/consulta/where_ast.py` (tokenizador → AST → SQL
com `%s` e parâmetros; campo só da lista branca da camada); `outFields`, `orderByFields`,
`groupByFieldsForStatistics`, `outStatistics` e `objectIds` são validados contra o esquema da camada em
`app/consulta/motor.py` (nome fora do esquema = 400; `statisticType` fora da lista = 422; `resultOffset`/
`resultRecordCount` só inteiros). O OGC API Features desta versão não tem `filter` (CQL2): `bbox`/`limit`/
`offset` são numéricos validados e qualquer outro parâmetro é ignorado. Nome de schema/tabela vem sempre do
catálogo (`plat.item`), nunca do cliente.

Rede de segurança acrescentada neste item (`motor._executar`): erro de TIPO que só o Postgres descobre ao
executar a consulta parametrizada (`fid LIKE '1%'` num bigint, percentil fora de 0-1) vira 400
`consulta_invalida` sem texto do banco — antes era 500 com o SQL no traceback do servidor (dois defeitos
achados pela suíte, corrigidos).

Prova: `tests/seguranca/test_injecao.py` — 180 payloads (sqlmap tamper: comentários, unicode, `/**/`, encoding;
`; DROP/DELETE/UPDATE` numa tabela-canário; `UNION`; `pg_sleep`; `pg_read_file`, `lo_import`, `COPY TO
PROGRAM`; subconsulta em `outStatistics`/`havingClause`/`objectIds`; OGC `bbox`/`limit`/`offset`/`filter`) contra
uma camada importada de verdade: 0 respostas 5xx, latência máxima de 8 ms (nenhum `pg_sleep` executou),
canário intacto, contagem da camada inalterada, resposta 200 só com feições da própria camada e colunas do
esquema. Estático: `test_estatico_nenhum_sql_interpola_entrada_do_usuario` varre todo `.execute(` de `app/`
e reprova SQL interpolado (f-string, `.format`, `%`) que cite nome de parâmetro de entrada; `bandit -t B608`
sobre `app/consulta` acha 6 f-strings de SQL, todas com interpolação só de lista branca (`colunas_sql`,
`where_sql` compilado, schema/tabela do catálogo) — a lista é fixada no teste, linha nova é revisão.

Fora desta passagem: ZAP baseline (sem imagem nesta máquina, disco a 94 %, D21); `applyEdits` (item L2-03).



## 11. Limite de taxa contra abuso de volume (item L7-03-b-rate-limit-abuso)

Três camadas independentes (ADR `docs/adr/20260907T1500-limite-de-taxa-tres-camadas.md` tem as decisões e o
que ficou de fora):

| camada | onde | chave | o que segura |
|---|---|---|---|
| 1 — borda | nginx, zonas `plat_login`/`plat_api`/`plat_tiles` (`deploy/nginx.conf`, `install.sh` grava as zonas em `/etc/nginx/conf.d/plat_limites.conf`) | IP (`$binary_remote_addr`) | volume bruto, antes de gastar CPU/conexão de banco |
| 2 — inquilino/plano | `app/limite_taxa.py` + `plat.limite_taxa_verificar` (Postgres, janela deslizante), chamada de dentro de `app/auth/sessao.py::resolver` | `tenant:<id>` | um inquilino (ou um token comprometido dele) não afeta outro; teto lido de `tenant.config.limites.*`, cortado para a faixa de `limites.LIMITE_TAXA_PADROES` |
| 3 — reincidência | fail2ban, jail `plat` (`deploy/fail2ban/`) sobre `/var/log/nginx/plat_access.log` | IP (`$remote_addr` do log combined) | quem insiste em 401/429 depois de já ter sido recusado |

### 11.1 Camada 1 — nginx por IP

`deploy/nginx.conf` tem `location /api/` (zona `plat_api`, `rate=120r/m burst=60 nodelay`) e
`location /tiles/` (zona `plat_tiles`, `rate=600r/m burst=200 nodelay`), além do `location = /api/login`
já existente (zona `plat_login`, item L0-02). `limit_req` roda ANTES do roteamento da aplicação — a
rajada acima do burst nunca chega ao `proxy_pass`, então nunca invalida nem escreve num `proxy_cache`
que a rota venha a ter (prova em 9.3). As três zonas usam `$binary_remote_addr`, nunca um cabeçalho:
não há `ngx_http_realip_module` configurado neste vhost, então não existe "confiar no
X-Forwarded-For" para configurar errado aqui — a defesa é segura por padrão.

Medido com `scripts/bench_limite_taxa.sh` (nginx e uvicorn reais, ver 9.4):

```
== camada 1, zona plat_api (rate=120r/m burst=60) ==
direto (sem nginx), 90 pedidos rápidos: 90 404, 0 429   -- confirma que a defesa é só do nginx
via nginx,           90 pedidos rápidos: 53 404, 37 429
== camada 1, zona plat_tiles (rate=600r/m burst=200), sem existir rota de ladrilho ==
via nginx, 320 pedidos rápidos: 229 404, 91 429
== X-Forwarded-For forjado e ROTACIONADO a cada pedido, 200 pedidos cada rodada ==
sem forjar: 192/200 em 429 · forjando: 197/200 em 429 (diferença 5, ruído de tempo entre rodadas)
```

### 11.2 Camada 3 — fail2ban

`deploy/fail2ban/filter.d/plat-abuso.conf` casa linhas do log combined do nginx com status 401 ou 429
em `/api/`, `/svc/` ou `/tiles/`; `deploy/fail2ban/jail.d/plat.conf` (`backend=auto`, arquivo — NUNCA o
`backend=systemd`/journal que a jail `nginx-limit-req` já instalada nesta máquina usa, que leria todo
nginx de todo produto) aponta para `/var/log/nginx/plat_access.log`, um `access_log` DEDICADO do vhost
do plat (nunca o log genérico compartilhado com outros produtos da casa). `install.sh` copia os dois
arquivos para `/etc/fail2ban/` e recarrega o fail2ban (seção "i4"). `maxretry=15 findtime=120s
bantime=3600s`; `banaction` herdado do `[DEFAULT]` da casa (`nftables`).

**Prova real, medida em 07/09/2026** (nunca contra um IP de produção — `127.0.0.9` é loopback,
`curl --interface` alcança sem configurar nada, e nenhum outro serviço desta máquina compartilhada
depende dele; ver o ADR §Decisão 3 para o motivo de não usar um IP real neste teste):

```
$ fail2ban-regex /var/log/nginx/plat_access.log /etc/fail2ban/filter.d/plat-abuso.conf
Failregex: 2226 total
Lines: 3716 lines, 0 ignored, 2226 matched, 1490 missed

$ for i in $(seq 1 30); do curl -s --interface 127.0.0.9 -o /dev/null -X POST http://.../api/login \
    -H 'Content-Type: application/json' -d '{"inquilino":"demo","login":"zz-nao-existe","senha":"errada"}'; done
$ sudo fail2ban-client status plat
...
   |- Currently banned:	1
   `- Banned IP list:	127.0.0.9
$ curl --interface 127.0.0.9 http://.../saude   # sem resposta (000) -- o nftables está mesmo bloqueando
$ sudo fail2ban-client set plat unbanip 127.0.0.9   # limpeza; confirmado banned=0 depois
```

### 11.3 Camada 2 — por inquilino/plano, em Postgres

`app/limite_taxa.py` (mecanismo) + `plat.limite_taxa_verificar` (migração `20260907T1444_limite_taxa.sql`,
janela deslizante — mesmo desenho de `plat.redefinicao_solicitar`, migração 047). Chamada de dentro de
`app/auth/sessao.py::resolver()`, o único ponto por onde toda requisição autenticada passa (sessão OU
token), já com `tenant_id`/`config` resolvidos. 429 com `Retry-After` (RFC 6585), corpo
`{"erro": "limite_de_taxa", "detalhe": {"escopo", "maximo", "janela_s"}}`.

Teto por `tenant.config.limites.<escopo>_por_minuto`, cortado para a faixa de `limites.LIMITE_TAXA_PADROES`
(nunca abaixo do mínimo nem acima do máximo — mesma regra de corte de `AUTH_PADROES`):

| escopo | padrão | mínimo | máximo |
|---|---|---|---|
| `api` (todo `/api/*` autenticado) | 6000/min | 5/min | 500.000/min |
| `tiles` (`/tiles/*`, `/svc/<token>/(raster\|mosaico)`) | 12000/min | 10/min | 2.000.000/min |

O padrão é DE PROPÓSITO alto (100 req/s sustentado para `api`): o mesmo contador corre em toda a suíte
de teste da casa martelando os inquilinos `demo`/`demo2` (`sessao_a`/`sessao_b`, escopo de sessão do
pytest) — um teto pensado só para "uso normal de um cliente" derrubaria `make check` sem motivo nenhum
do produto (provado: `tests/api/test_limite_taxa.py::
test_limite_padrao_de_demo_e_alto_o_bastante_para_nao_atrapalhar_a_suite`).

Provas (`tests/api/test_limite_taxa.py`, 10 casos, todos verdes):

- **Cláusula "inquilino não afeta outro"**: dois inquilinos temporários com o mesmo teto baixo; esgota
  o de A, confere que B segue 200 no mesmo instante
  (`test_limite_de_um_inquilino_nao_afeta_outro_teste_cruzado`).
- **Refutação "50 IPs contra o mesmo token"**: rotaciona `X-Forwarded-For` a cada pedido contra o MESMO
  inquilino — a chave é `tenant:<id>`, nunca o IP, então rotacionar o cabeçalho não devolve cota nenhuma
  (`test_50_ips_forjados_contra_o_mesmo_token_a_camada_de_inquilino_segura`).
- **Refutação "1 IP contra 50 tokens"**: a camada 2, por desenho, NÃO segura isso sozinha — cada
  inquilino tem sua própria cota. Quem segura é a camada 1 (9.1): a zona `plat_api` não sabe o que é
  um token, então criar mais tokens (ou mais inquilinos) não dá mais cota de IP.
- **Contrato de erro e `Retry-After`**: `test_retry_after_e_o_corpo_seguem_o_contrato_de_erro_do_produto`.
- **Escopos independentes da mesma chave**: `test_escopos_diferentes_da_mesma_chave_sao_contadores_independentes`.
- **Não conta duas vezes na mesma requisição**: `test_nao_conta_duas_vezes_na_mesma_requisicao`.
- **Concorrência real nunca fura o teto**: achado do adversário do turno — a 1ª versão da função tinha
  uma corrida real (`SELECT count()` + `INSERT` sem trava, sob `READ COMMITTED` duas transações
  concorrentes viam a mesma contagem e as duas passavam; medido furando 20 para 21/23). Consertado com
  `pg_advisory_xact_lock` por `(chave, escopo)` na própria migração. Reproduzido depois do conserto:
  `test_concorrencia_real_nunca_fura_o_teto` — 5 rodadas de 200 chamadas concorrentes (thread pool),
  teto sempre exatamente respeitado.

### 11.4 X-Forwarded-For — por que não há nada novo para configurar

`deploy/plat-api.service` já sobe o uvicorn com `--proxy-headers --forwarded-allow-ips 127.0.0.1` (de
um item anterior, não tocado por este). Isso faz o `ProxyHeadersMiddleware` do uvicorn só confiar no
cabeçalho quando o peer TCP imediato é `127.0.0.1` (o nginx local); de qualquer outro peer, o cabeçalho
é ignorado e `request.client.host` fica com o IP real do socket. `app/auth/sessao.py::ip_de()` já lê só
`request.client.host` — todo código que já usava essa função (restrição de token por IP, bloqueio de
login, log de acesso) já herda a defesa sem mudança nenhuma. Este item PROVA isso, não inventa
mecanismo novo — ver o ADR (Decisão 3) para o raciocínio completo e por que o teste usa `127.0.0.9`
como "peer não confiável" em vez de tentar simular um atacante remoto de verdade numa máquina de teste
local.

### 11.5 O que ficou de fora (nomeado, não escondido)

- **"Tile acima do limite do plano" fim a fim por HTTP real**: `L1-02-tiles-token` (que cria as rotas
  `/tiles/...`/`/svc/<token>/raster/...`) está `entregue` mas **não mesclado** nesta base (`app/imagens/`
  não existe neste worktree — ver `laco/handoffs/T4/L1-02-tiles-token.md`). O MECANISMO da camada 2 é
  genérico por escopo e testado com `escopo="tiles"` diretamente contra a função SQL; a zona de nginx
  `plat_tiles` já protege `/tiles/` na borda (9.1, provado até sem existir a rota real). O que falta é
  só a FIAÇÃO — anexar `limite_taxa.exigir(..., "tiles", "tiles_por_minuto")` no ponto que resolve o
  token de ladrilho quando aquele ramo mesclar. Registrado como pendência do item, não como feito.
- **Limite nomeado por PLANO** (Bronze/Prata/Ouro, item L7-09-b): o mecanismo já lê
  `tenant.config.limites.*`; nomear planos e expor a UI de configuração é do L7-09-b.
- **`fail2ban` com IP real de produção no teste**: por segurança operacional desta máquina
  compartilhada (ver 9.2) — em produção o `banaction` é o real (`nftables`, herdado), sem dry-run;
  só o TESTE evita usar um IP de verdade.


## 12. Pipeline único de upload por classe (item L7-03-a-antivirus-upload)

Camada de CIMA da varredura de conteúdo do §8: a `classe` do upload (`POST /api/arquivos?classe=`) decide,
ANTES de ler um byte do corpo, quais `Content-Type` são aceitos e o teto de tamanho da classe
(`app/varredura_conteudo.POLITICAS`). `Content-Type` fora da lista da classe recusa com `415
politica_de_rota` sem gastar leitura de corpo nem chamada ao Garage — o mesmo espírito de "recusar cedo" da
checagem de `Content-Length` (§8.4). A checagem "bytes provam o tipo" do §8 continua valendo sempre, para
QUALQUER classe: a política aqui só estreita quais tipos cada classe aceita.

| classe | `Content-Type` aceitos | teto |
|---|---|---|
| `objeto` | sem lista por rota: qualquer `Content-Type` passa para a assinatura básica do §8 decidir sozinha — inclusive `application/octet-stream`, `text/plain` ou qualquer tipo sem família fixa em `TIPOS_PERMITIDOS` (`image/png`, `image/jpeg`, `image/gif`, `image/tiff`, `image/webp`, `application/json`, `application/geo+json`, `text/csv`, `application/pdf`, `application/zip`, `application/vnd.google-earth.kmz`); é a classe "arquivo bruto" (padrão de `POST /api/arquivos`) | `limites.ARQUIVO_BYTES_MAX` |
| `anexo` | `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/svg+xml`, `application/pdf`, `text/csv`, `text/plain`, `application/json`, `application/geo+json`, `application/zip`, `application/vnd.google-earth.kmz`, `application/vnd.google-earth.kml+xml`, `text/html` | `limites.ANEXO_BYTES_MAX` |
| `foto_campo` | `image/jpeg`, `image/png`, `image/webp` | `limites.ANEXO_BYTES_MAX` |
| `imagem` | `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/svg+xml` | `limites.IMAGEM_UPLOAD_BYTES_MAX` |
| `csv` | `text/csv`, `text/plain` | `limites.ANEXO_BYTES_MAX` |

Classe fora desta tabela cai em `objeto` (`varredura_conteudo.politica()`).

### 12.1 Pós-processamento sobre o arquivo inteiro

Só corre quando o arquivo coube no buffer único (`limites.ARQUIVO_BUFFER_UNICO_BYTES`, o que já vale para a
maioria dos anexos/imagens desta tabela) — `varredura_conteudo.pos_processar()`:

- **SVG** (`image/svg+xml`): sai sanitizado por `app/svg_seguro.py` (lista BRANCA de elemento/atributo,
  parse por `defusedxml` — nunca resolve entidade externa nem expande bomba de entidades). `<script>`,
  manipuladores `on*`, `<foreignObject>`, `href`/`xlink:href` para fora do arquivo e `url()` em `style` somem;
  o desenho (path/circle/rect/...) fica. SVG que não sobrevive ao parse (XML inválido, entidade externa) é
  recusado com `415`, motor `svg_seguro`.
- **zip/kmz** (`application/zip`, `application/vnd.google-earth.kmz`): passa pelas regras de zip-bomba de
  `app/ingestao/formatos.py::conferir_zip` (nº de entradas, tamanho descomprimido, razão de compressão,
  caminho de entrada) ANTES de gravar — nunca extrai para decidir. Acima do buffer único (multipart), a
  MESMA regra roda depois de gravado, lendo só o diretório central por intervalo
  (`app/uploads/zip_remoto.py::inspecionar_zip_remoto`); zip suspeito é apagado do Garage e recusado. Motor
  `zip_bomba` nos dois casminhos.

### 12.2 Antivírus opcional (`clamd`, D21)

`app/varredura_conteudo.py::MotorClamd` fala o protocolo `INSTREAM` do `clamd` por socket unix ou TCP
(biblioteca padrão só). Só entra na cadeia quando `PLAT_CLAMD` está definido nas configurações (endereço do
`clamd`) — sem isso, só a assinatura básica do §8 roda, exatamente como D21 decidiu (§8.1: a base de
assinaturas do `clamd` residente em RAM não cabe nesta máquina hoje). Com `PLAT_CLAMD` definido, `clamd` fora
do ar RECUSA o upload (`ClamdIndisponivel`) — nunca "passa sem varrer" só porque o antivírus caiu.

### 12.3 Evento na trilha

Recusa por qualquer motor deste pipeline (`politica_de_rota`, assinatura básica do §8, `svg_seguro`,
`zip_bomba`, `clamd`) grava um evento (`plat.evento`, tipo vocabulário `db/migracoes/
20260907T2225_upload_recusa_evento.sql`): `arquivos/quarentena` quando é o antivírus (guarda sha256 +
assinatura), `arquivos/conteudo_recusado` nos demais (guarda sha256 quando há dados, classe, `Content-Type`
declarado, tipo detectado, motivo) — nunca o conteúdo. A quarentena É o registro: o objeto recusado nunca é
gravado no Garage.

### 12.4 Entrega: nunca ativo, mesmo aberto direto na aba

`GET /api/arquivos/{sha256}` sempre entrega com `Content-Disposition: attachment` e tipo de mídia rebaixado
pela lista fechada do §8.6/`app/entrega_conteudo.py` (byte de cliente nunca volta como `text/html`,
`image/svg+xml` ou JavaScript). Por cima disso, `app/cabecalhos.py` acrescenta `Content-Security-Policy:
sandbox` só nesta rota (o resto da API usa a política de dado comum, §1-11): se o usuário ignora o download e
abre a URL direto na aba, o conteúdo não pode navegar a página, abrir formulário, popup ou plugin.
