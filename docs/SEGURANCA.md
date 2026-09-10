# Segurança — segredos, certificados, dependências e upload

Item L7-19-segredos-e-certificados (§1-6). Esta seção é o mapa: onde cada segredo mora, como rotacionar
CADA um deles sem derrubar o produto (comando único `plat segredo rotacionar <nome>`), e como o
certificado TLS se renova sozinho. Ela não repete o que já está no `docs/adr/0001-fundacao.md` seção 8
(contrato de `.env`) — só o que mudou e o que é operação. Procedimento passo a passo para um humano em
plantão: `docs/RUNBOOKS/segredos.md`. Estendida com o item L7-03-f-dependencias-cve-log-correcoes (§7,
varredura de dependência + log de correções) e o item L7-03-b-antivirus-anexos (§8, varredura de
conteúdo em upload de anexo/miniatura).

## 1. Os 5 segredos — onde cada um mora hoje

| segredo | onde mora | quem lê | dono/modo |
|---|---|---|---|
| `PLAT_SECRET` | `/etc/plat/segredos/PLAT_SECRET` | `plat-api`, `plat-worker` (`LoadCredential=`) | root, 0600 |
| `PLAT_SECRET_ANTERIOR` (dupla-chave, 24h) | `/etc/plat/segredos/PLAT_SECRET_ANTERIOR` | `plat-api`, `plat-worker` | root, 0600 (normalmente vazio) |
| `PLAT_DSN` (senha da role `plat_app`) | `/etc/plat/segredos/PLAT_DSN` | `plat-api`, `plat-worker` (a chave é exigida sempre por `settings.py`, só a API se autentica de verdade com ela) | root, 0600 |
| `PLAT_DSN_WORKER` (senha da role `plat_worker`) | `/etc/plat/segredos/PLAT_DSN_WORKER` | `plat-worker` | root, 0600 |
| `PLAT_GARAGE_ADMIN_TOKEN` (bearer da Admin API do Garage, :3903) | `/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN` e `garage.toml` (`admin_token`) | `plat-api` (chama o Garage) e o próprio Garage (autentica quem chama) | root, 0600 / dono do Garage |
| chaves S3 por inquilino (`chave_rw_*`, `chave_ro_*`) | `plat.arquivo_bucket` (banco, uma linha por inquilino) | `plat-api`, resolvidas por `SELECT` a cada requisição — nunca em arquivo | RLS por `tenant_id` |
| segredo TOTP por usuário | banco, cifrado com `PLAT_SECRET`/`PLAT_SECRET_ANTERIOR` (`app/auth/totp.py`) | `plat-api` | coluna do banco |

Nenhum dos 5 primeiros está mais no `.env` (`tests/unit/test_segredos_fora_do_repo.py` e
`tests/unit/test_instalador.py::test_env_real_desta_maquina_nao_tem_nenhum_dos_cinco_segredos` provam
isso na máquina real, não só no texto de `install.sh`). A chave S3 por inquilino nunca esteve em
arquivo — é um desenho de banco que já existia (item L0-11); entra na tabela porque rotacioná-la é uma
das 5 cláusulas do portão deste item.

### O mecanismo: `LoadCredential=` do systemd (retomado do turno T3, agora nos 5)

`deploy/plat-api.service` declara `LoadCredential=` para `PLAT_SECRET`, `PLAT_SECRET_ANTERIOR`,
`PLAT_DSN` e `PLAT_GARAGE_ADMIN_TOKEN`; `deploy/plat-worker.service` para `PLAT_SECRET`,
`PLAT_SECRET_ANTERIOR`, `PLAT_DSN` e `PLAT_DSN_WORKER`. O systemd (root, antes de rebaixar para
`APP_USER`) lê o arquivo fonte e entrega uma cópia em `$CREDENTIALS_DIRECTORY`
(`/run/credentials/<unidade>/`); nenhum valor aparece em `ps`, `systemctl show` ou `journalctl` — só o
*caminho* do arquivo fonte, o que mantém a regra do ADR 0001 §8.

**Um detalhe que muda o desenho**: `LoadCredential=` EXIGE que o arquivo-fonte exista, mesmo vazio — se
não existir, a unidade não sobe. Isso é trivial para os 4 segredos que sempre têm um valor, mas
`PLAT_SECRET_ANTERIOR` normalmente NÃO tem (só existe durante a janela de 24h depois de uma rotação de
`PLAT_SECRET`) — por isso `install.sh` cria o arquivo **vazio** quando ele não existe (nunca pula a
criação), e `settings.py` trata conteúdo vazio como chave ausente, idêntico ao comportamento sem o
arquivo.

**O que isso NÃO isola — medido nesta máquina (systemd 255, sem `DynamicUser=`)**: a ACL do
`LoadCredential=` libera o arquivo só ao `User=`/`Group=` da unidade (`dev`, o mesmo usuário que roda
**todo outro produto desta máquina**); outro processo rodando como `dev` que souber o caminho em
`/run/credentials/` ainda lê. O ganho real é tirar o segredo de um `.env` que rotina de operação
(`cat`, `grep -r`, editor, backup, histórico do git) varre o tempo todo, e nunca aparecer em
`ps`/journal/unit file. Isolamento por-unidade de verdade pede `DynamicUser=` — muda a dono de toda a
árvore do repositório, fora de escopo aqui (ver §5 do handoff do item para o detalhe).

## 2. `plat segredo rotacionar <nome>` — um comando para os 5

```
sudo scripts/plat segredo rotacionar PLAT_SECRET
sudo scripts/plat segredo rotacionar PLAT_DSN
sudo scripts/plat segredo rotacionar PLAT_DSN_WORKER
sudo scripts/plat segredo rotacionar PLAT_GARAGE_ADMIN_TOKEN
sudo scripts/plat segredo rotacionar PLAT_GARAGE_CHAVE_S3:<slug-do-inquilino>
```

`scripts/plat` é o dispatcher; a lógica mora em `scripts/segredo_rotacionar.py` (Python, não bash —
os 5 casos manipulam banco, arquivo e a Admin API do Garage, cada um com sua prova de "o valor antigo
parou de funcionar"; um script só por caso viraria 5 arquivos quase iguais). Os nomes de unidade/porta
são **parâmetros com valor-padrão de produção** (`plat-api`:8150, `plat-worker`:8153,
`plataforma-garage`:3903) — o mesmo script roda em produção de verdade e, com os overrides
`--unidade-api`/`--unidade-worker`/`--unidade-garage`/`--cred-dir`, foi o que provou o mecanismo deste
item inteiro contra 3 serviços DE TESTE (`plat-teste-segredo-{a,b,garage}`, portas 8197-8199), sem
nunca reiniciar `plat-api`/`plat-worker`/`nginx`/`postgres` reais — ver `scripts/prova_segredos_l7_19.py`
(orquestra tudo, do zero até a limpeza) e `scripts/prova_garage_chave_s3.py` (o único dos 5 que roda de
verdade em produção, porque não reinicia nada — ver abaixo). Reprodução automatizada:
`pytest tests/e2e/test_rotacao_segredos.py -m lento`.

O que cada rotação faz, em ordem (a ordem sempre garante que nunca existe um instante em que o lado que
recebe o restart já tenha o valor novo antes do lado que o autentica):

1. **`PLAT_SECRET`** (dupla-chave): o valor atual vira `PLAT_SECRET_ANTERIOR` (grava-se ele **primeiro**,
   nunca se perde o que estava valendo), gera-se um valor novo, grava-se como `PLAT_SECRET`, reinicia-se
   `plat-api` (o único consumidor direto — o worker só precisa que a chave exista, ver tabela do §1)
   e espera-se `/saude` = 200. Por 24h (janela documentada, não automática — ver §5) o que foi
   cifrado/assinado com o valor antigo continua legível (`app/seguranca_rotacao.py`); depois disso,
   apagar (esvaziar) `/etc/plat/segredos/PLAT_SECRET_ANTERIOR` — não há hoje um timer que faça isso
   sozinho, é passo do runbook.
2. **`PLAT_DSN`** (senha de `plat_app`): `ALTER ROLE plat_app PASSWORD` no banco **primeiro** → grava o
   DSN novo no credential → reinicia `plat-api` → confere que a senha **antiga** já não autentica.
3. **`PLAT_DSN_WORKER`** (senha de `plat_worker`): mesmo desenho, sobre `plat-worker`.
4. **`PLAT_GARAGE_ADMIN_TOKEN`**: edita `admin_token` em `garage.toml` (texto exato, nunca por posição)
   → grava o token novo no credential do plat → reinicia o Garage → reinicia `plat-api` → confere que
   o token antigo já não autentica na Admin API e que o novo autentica. É o único dos 5 que reinicia
   DOIS serviços diferentes ("reinício em cadeia"), cada um com sua própria janela medida.
5. **`PLAT_GARAGE_CHAVE_S3:<slug>`**: cria uma chave NOVA no Garage (nunca reaproveita id), concede
   permissão no bucket do inquilino, grava a chave nova (a gravação em `plat.arquivo_bucket` é o mesmo
   caminho que `app/garage.py`/`app/objetos.py` já usam), confirma que a chave nova grava/lê um objeto
   de prova, **apaga a chave antiga no Garage** e confirma que ela já não autentica (403). **Nenhuma
   unidade reinicia** — a API resolve o par de chaves do bucket por `SELECT` a cada requisição
   (`app.objetos._resolver_bucket_por_slug`), nunca as guarda em memória de processo — por isso este é
   o único dos 5 cuja rotação real roda em produção de verdade dentro deste item: mede-se `/saude` de
   `plat-api` antes/depois (sempre 200, nunca reiniciado) contra um bucket **descartável**, nunca um
   inquilino real.

### Zero 5xx durante o restart — a técnica, não um acaso

Os 4 segredos que reiniciam serviço usam **ativação por soquete** (`Sockets=` do systemd) nos serviços
de teste: o soquete TCP é propriedade da unidade `.socket`, que continua no ar e enfileirando conexões
novas no kernel enquanto a unidade `.service` reinicia — por isso uma janela de restart não vira
"connection refused" nem 5xx, ela só some na fila até o processo novo assumir. `scripts/
segredo_rotacionar.py::reiniciar_e_medir` marreta `/saude` a cada 50 ms durante o `systemctl restart`
inteiro e conta os códigos de resposta à parte de qualquer erro de conexão (os dois nunca se somam:
"5xx" é uma resposta HTTP de servidor com erro; "erro de conexão" é ausência de resposta — confundir os
dois esconderia justamente a baixa real, se existisse). **Medido, `tests/medidas/L7-19.json`: 0
respostas 5xx nas 4 rotações que reiniciam algo**, num total de ~150 requisições martelo; um punhado de
erros de conexão isolados (a fração de segundo entre o processo velho soltar o soquete e o novo
assumi-lo, mesmo com socket activation) — reportados, nunca escondidos, nunca contados como 5xx.
**Produção hoje (`plat-api`/`plat-worker`) NÃO usa socket activation** — a técnica foi provada no
serviço de teste deste item; adotá-la em produção pede editar as unidades reais e um restart controlado
para aplicar, o que este turno não fez (limite duro: nenhum restart de produção). Fica registrado como
próximo passo natural em `docs/RUNBOOKS/segredos.md` §6.

## 3. Prova de que nenhum dos 5 está no repositório nem no journal

```
sudo scripts/plat segredo rotacionar <nome> --json-saida /tmp/resultado.json   # cada rotação já imprime a prova "antigo falha / novo funciona"
```

Automatizado (roda com `pytest`, lê os valores REAIS de `/etc/plat/segredos/` via `sudo cat` e procura
por eles — nunca imprime o valor, só o nome do segredo se achar):

```
pytest tests/unit/test_segredos_fora_do_repo.py -q
```

Três cláusulas: (1) `grep -rIl` na árvore de trabalho inteira (exceto `.git`/`venv`/`node_modules`);
(2) `git log --all -S<valor>` no histórico inteiro, não só o HEAD; (3) `journalctl -u plat-api -u
plat-worker -g <valor>` — as três dão zero para os 5 segredos hoje. `.env` sem nenhum dos 5:
`tests/unit/test_instalador.py::test_env_real_desta_maquina_nao_tem_nenhum_dos_cinco_segredos` lê o
`.env` real desta instalação (não um exemplo) e falha se qualquer um aparecer.

## 4. Como a suíte de testes ainda usa os 5 segredos

`tests/conftest.py` e `app/settings.py::valores_do_ambiente` sempre deixam o **ambiente do processo**
vencer o `.env` e o credential. O `Makefile` explora isso: a variável `SEGREDOS` lê os 5 arquivos com
`sudo cat` (mesmo privilégio que `install.sh`/`make migrar` já exigem) e os exporta só para o processo
filho (`pytest`, `uvicorn` de desenvolvimento) — nunca em argumento visível em `ps` — e só quando o
arquivo existe e não é vazio (assim `PLAT_SECRET_ANTERIOR`/`PLAT_GARAGE_ADMIN_TOKEN`, normalmente
vazios, não pisam em nada por engano):

```makefile
teste:
	$(SEGREDOS) $(VENV)/pytest -m "not lento"
```

Isso é só para desenvolvimento/CI local fora do systemd. Em produção o systemd é quem entrega o valor
(§1); nada no código de produção chama `sudo`.

## 5. O que fica de fora deste item (fora de escopo, não esquecido)

- **`DynamicUser=`** (isolamento por-unidade de verdade, nem outro processo do mesmo usuário lê) —
  mudaria a dono de toda a árvore do repositório hoje `dev:dev`; fora de escopo.
- **Socket activation em produção** (`plat-api`/`plat-worker` de verdade) — provada no serviço de teste
  (§2), não adotada nos serviços reais porque isso pede editar a unidade instalada e um restart
  controlado, banido neste turno. Ver `docs/RUNBOOKS/segredos.md` §6 para o procedimento de adoção.
- **Limpeza automática de `PLAT_SECRET_ANTERIOR` depois de 24h** — hoje é passo manual do runbook (§2
  do `docs/RUNBOOKS/segredos.md`); um timer/cron que zera o arquivo sozinho é próximo passo natural.
- **CA própria para appliance de cliente** (Degrau 0 da plataforma) — não existe cliente com appliance.
- **Alarme de expiração de certificado antes dos 30 dias do certbot** (blackbox exporter, proposto no
  backlog original) — não construído; `certbot.timer` automático continua sendo a única rede de
  segurança (§6).

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

**Alarme antes do vencimento**: não existe hoje (ver §5) — `systemctl status certbot.timer` é hoje a
única checagem, manual.

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

## 9. Cabeçalhos de segurança, CORS e perfil TLS (item L7-03-e-cabecalhos-csp-tls)

### 9.1 Quem declara cada cabeçalho

`add_header` do nginx ACRESCENTA, nunca substitui: cabeçalho posto nos dois lugares sai em dobro e o
serviço perde como dizer outra coisa numa rota. A repartição, então, é esta — e ela é provada por
`tests/unit/test_cabecalhos_fonte.py`, que lê `deploy/nginx.conf`:

| cabeçalho | quem declara | por quê |
|---|---|---|
| `Content-Security-Policy` | aplicação (`app/cabecalhos.py`) | depende da resposta: nonce novo a cada uma, política diferente para documento e para dado, `frame-ancestors` por inquilino |
| `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` | aplicação | idem: o CORP muda para `cross-origin` quando a origem é a de um token autorizado |
| `Referrer-Policy`, `X-Content-Type-Options` | aplicação | ficam ao lado dos demais, numa origem só |
| `Cache-Control` | aplicação (piso `no-store, must-revalidate`) | decisão do turno T2, mantida |
| `Strict-Transport-Security` | nginx, bloco 443 | é do transporte; a aplicação não sabe se a conexão chegou por TLS |
| `X-Robots-Tag` | nginx | vale para tudo o que o domínio serve, inclusive o que a aplicação não responde |
| conjunto inteiro em `/static/` | nginx | ali o nginx é a origem do corpo |

`X-Frame-Options` deixou de ser declarado. Quem manda no embutir passou a ser `frame-ancestors`, que
aceita uma LISTA de origens (o cabeçalho antigo só aceita `DENY`, `SAMEORIGIN` ou uma origem) e que os
navegadores atuais aplicam com precedência sobre ele quando os dois aparecem.

O HSTS continua em `max-age=31536000` (um ano). `includeSubDomains` e `preload` NÃO foram ligados:
`preload` é irreversível na prática (a lista embutida nos navegadores demora meses a sair) e alcança o
domínio inteiro da casa, não só este serviço — é decisão do dono, não do item.

### 9.2 A política

Documento HTML:

```
default-src 'self'; script-src 'self' 'nonce-<sorteado por resposta>'; style-src 'self';
img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; worker-src 'self' blob:;
child-src 'self' blob:; media-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none';
form-action 'self'; frame-src 'self'; upgrade-insecure-requests; frame-ancestors <por inquilino>
```

Sem `'unsafe-inline'` e sem `'unsafe-eval'`. `blob:` em `worker-src`/`child-src` porque o MapLibre cria o
próprio processo de trabalho por URL de blob. As páginas de `web/` não têm `<script>` em linha nem
tratador de evento em atributo (`onclick=`, `onerror=`…), e um teste que LÊ os arquivos impede que
voltem: com esta política eles não executariam, e a tela abriria em branco sem erro visível. A única
exceção é o script de arranque da Swagger UI, que recebe o nonce da própria resposta em `/api/docs`.

Resposta que não é documento (JSON, GeoJSON, imagem, tile, arquivo) leva
`default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.

### 9.3 Embutir a aplicação no sítio do cliente (`frame-ancestors` por inquilino)

Embutir é caso de uso, não acidente. A lista de origens autorizadas é do INQUILINO e mora em
`plat.tenant.config -> 'origens_embutidas'`, a mesma coluna jsonb das demais configurações da
organização. Sem lista, a política sai `frame-ancestors 'none'` — a falta fecha.

```sql
-- pela role da aplicação, com contexto de inquilino (igual ao PUT /api/org)
SELECT set_config('plat.tenant_id', '<id>', true);
UPDATE plat.tenant
   SET config = config || jsonb_build_object('origens_embutidas',
       '["https://sig.exemplo.gov.br"]'::jsonb)
 WHERE id = plat.tenant_atual();
```

O middleware descobre de quem é a página por `state.tenant_id` (quando houve autenticação) ou pelo
parâmetro `inquilino` da própria URL (páginas ainda sem sessão). A leitura vai pela função
`plat.origens_embutidas(slug, id)`, `SECURITY DEFINER` da migração `20260907T2047`: o cabeçalho é montado
antes de haver contexto de inquilino na conexão, e sem ela a RLS devolveria zero linhas e a política sairia
sempre fechada. A função devolve um campo de configuração de um inquilino, que o próprio cabeçalho já
publica. O valor fica em memória por 60 s (`app.cabecalhos.CACHE_ORIGENS_S`).

### 9.4 CORS por token

A lista de origens do CORS é a MESMA `restricao.referer` que o token de serviço já usa desde o item L0-02
para ser aceito. Só quando a requisição chega autenticada por token e a origem está naquela lista é que a
resposta ganha `Access-Control-Allow-Origin` com a origem pedida (nunca `*`), mais
`Access-Control-Expose-Headers: x-req-id` e `Cross-Origin-Resource-Policy: cross-origin`. `Vary: Origin`
sai sempre que há `Origin`, para que um intermediário não sirva a resposta de uma origem a outra.

O preflight (`OPTIONS` com `Access-Control-Request-Method`) é respondido sem consultar token, porque a
especificação proíbe o navegador de mandar crachá no preflight. Autorizar o preflight não entrega dado
nenhum: a requisição de verdade continua barrada pela restrição do token (401 `referer_nao_permitido`).

### 9.5 TLS, HTTP/2 e OCSP stapling

`deploy/nginx_tls.conf` (o `install.sh` escreve em `/etc/nginx/conf.d/plat_tls.conf`, contexto http, só
depois de existir certificado) põe o servidor no perfil **intermediate** do guia Server Side TLS da
Mozilla: TLS 1.2 e 1.3 apenas, escolha de cifra pelo cliente, retomada por ticket desligada. Uma
diferença declarada: a lista de cifras não traz as `DHE-*`, o que dispensa gerar e manter um
`ssl_dhparam` e não perde nenhum cliente do alvo do perfil — todos negociam ECDHE.

O OCSP stapling entrega no aperto de mão a resposta do respondedor da CA, poupando ao navegador uma
consulta que revela o sítio visitado; `ssl_stapling_verify on` exige a cadeia, que o certbot deixa em
`chain.pem`, e o resolvedor declarado é o do sistema.

HTTP/2: no nginx 1.24 (Ubuntu 24.04) ainda é opção do `listen`, não a diretiva `http2 on;` do 1.25.1+.
O `install.sh` acrescenta `http2` à linha `listen ... ssl;` que o certbot gerou, ao reescrever o bloco.

### 9.6 `security.txt`

`GET /.well-known/security.txt` responde no contrato da RFC 9116, gerado a cada leitura porque o campo
`Expires` é obrigatório e um arquivo com data fixa envelhece em silêncio. O contato vem de
`PLAT_SEGURANCA_CONTATO`; sem a chave vale `seguranca@<host de PLAT_URL_PUBLICA>`.
