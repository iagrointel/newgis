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

## 9. Limite de taxa contra abuso de volume (item L7-03-b-rate-limit-abuso)

Três camadas independentes (ADR `docs/adr/20260907T1500-limite-de-taxa-tres-camadas.md` tem as decisões e o
que ficou de fora):

| camada | onde | chave | o que segura |
|---|---|---|---|
| 1 — borda | nginx, zonas `plat_login`/`plat_api`/`plat_tiles` (`deploy/nginx.conf`, `install.sh` grava as zonas em `/etc/nginx/conf.d/plat_limites.conf`) | IP (`$binary_remote_addr`) | volume bruto, antes de gastar CPU/conexão de banco |
| 2 — inquilino/plano | `app/limite_taxa.py` + `plat.limite_taxa_verificar` (Postgres, janela deslizante), chamada de dentro de `app/auth/sessao.py::resolver` | `tenant:<id>` | um inquilino (ou um token comprometido dele) não afeta outro; teto lido de `tenant.config.limites.*`, cortado para a faixa de `limites.LIMITE_TAXA_PADROES` |
| 3 — reincidência | fail2ban, jail `plat` (`deploy/fail2ban/`) sobre `/var/log/nginx/plat_access.log` | IP (`$remote_addr` do log combined) | quem insiste em 401/429 depois de já ter sido recusado |

### 9.1 Camada 1 — nginx por IP

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

### 9.2 Camada 3 — fail2ban

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

### 9.3 Camada 2 — por inquilino/plano, em Postgres

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

### 9.4 X-Forwarded-For — por que não há nada novo para configurar

`deploy/plat-api.service` já sobe o uvicorn com `--proxy-headers --forwarded-allow-ips 127.0.0.1` (de
um item anterior, não tocado por este). Isso faz o `ProxyHeadersMiddleware` do uvicorn só confiar no
cabeçalho quando o peer TCP imediato é `127.0.0.1` (o nginx local); de qualquer outro peer, o cabeçalho
é ignorado e `request.client.host` fica com o IP real do socket. `app/auth/sessao.py::ip_de()` já lê só
`request.client.host` — todo código que já usava essa função (restrição de token por IP, bloqueio de
login, log de acesso) já herda a defesa sem mudança nenhuma. Este item PROVA isso, não inventa
mecanismo novo — ver o ADR (Decisão 3) para o raciocínio completo e por que o teste usa `127.0.0.9`
como "peer não confiável" em vez de tentar simular um atacante remoto de verdade numa máquina de teste
local.

### 9.5 O que ficou de fora (nomeado, não escondido)

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
