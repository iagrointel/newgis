# Runbook — rotacionar um segredo do plat (item L7-19-segredos-e-certificados)

Para quem está de plantão às 3 da manhã e precisa rotacionar um segredo AGORA (vazamento suspeito,
saída de alguém com acesso, ou rotina de higiene). Leia a seção do segredo que você precisa e siga os
passos na ordem — não pule a checagem "confirme antes de seguir".

Todo comando abaixo roda **dentro do repositório instalado** (`/home/dev/plataforma/enterprise` em
produção), como root (`sudo`). Nada aqui pede senha em texto — os comandos geram valor novo sozinhos.

## 0. Antes de qualquer rotação

```
cd /home/dev/plataforma/enterprise
sudo systemctl is-active plat-api plat-worker         # os dois devem estar "active" antes de mexer
curl -s http://127.0.0.1:8150/saude | head -c 300; echo
```

Se algum dos dois não estiver `active`, resolva isso primeiro — rotacionar um segredo com o serviço já
caído não tem como provar "o serviço não caiu".

Pré-requisito só da PROVA (não da rotação em si): o binário do k6 — o portão do item exige "0 erro 5xx
durante a rotação, medido pelo k6 curto". Nesta máquina está em `/home/dev/tools/k6/k6` (tar.gz de
github.com/grafana/k6/releases, linux-amd64); fora dela, aponte `PLAT_K6=<caminho>` ou ponha `k6` no
PATH. `tests/e2e/test_rotacao_segredos.py` falha com mensagem nomeada se não achar o binário — nunca
passa com régua substituta.

## 1. `PLAT_SECRET` (chave de cifra/HMAC da aplicação)

**O que quebra**: nenhuma URL assinada de objeto emitida ANTES da rotação (a cliente pede outra, sem
estado a limpar) nem sessão TOTP/LDAP/SMTP/conexão externa (o valor antigo continua legível por 24h
como `PLAT_SECRET_ANTERIOR` — dupla-chave). Depois das 24h, quem tinha algo cifrado só com o valor de
DUAS rotações atrás perde acesso (recadastra 2FA, reconfigura LDAP/SMTP/conexão) — normal, é a janela.
**As 24 h são automáticas**: a rotação grava o carimbo em `PLAT_SECRET_ANTERIOR_EM` e o timer
`plat-segredo-expira.timer` (de hora em hora) esvazia o ANTERIOR e reinicia API e worker na virada —
janela efetiva de 24 h a 24 h 59 min (granularidade do timer). O worker TAMBÉM reinicia na rotação:
ele carrega a chave uma única vez na subida e decifra SMTP/conexão dentro de jobs — sem o restart ele
ficaria semanas com a chave velha e não leria o que a API re-cifrar com a nova.

```
sudo scripts/plat segredo rotacionar PLAT_SECRET --unidade-worker plat-worker --porta-worker 8153
```

Confirme:
```
curl -s http://127.0.0.1:8150/saude | head -c 300; echo    # 200, banco ok
sudo stat -c '%s bytes' /etc/plat/segredos/PLAT_SECRET_ANTERIOR   # > 0: o valor antigo foi preservado
```

**24 horas depois** (ou quando tiver certeza de que nenhuma sessão/URL antiga ainda circula), esvazie o
anterior — sem isso a próxima rotação vai sobrescrevê-lo de qualquer forma, mas o valor de DUAS trocas
atrás fica "morto mas presente" por mais tempo do que precisa:
```
sudo truncate -s 0 /etc/plat/segredos/PLAT_SECRET_ANTERIOR
```

## 2. `PLAT_DSN` (senha da role `plat_app` no Postgres)

**Como o script evita qualquer 5xx**: trocar senha de role tem uma contradição — depois do
`ALTER ROLE` e antes de cada serviço subir com a credencial nova, quem atende com a senha velha leva
erro do banco (a sequência "restart em cadeia" deixou 57 respostas 500 nessa janela, medidas pelo k6
na prova do item; parar o serviço não resolve, porque com ativação por soquete a própria conexão do
cliente o religa com a credencial velha). O script abre uma **janela `trust` de segundos no pg_hba**
(só aquela role, só aquele banco, só 127.0.0.1, linha marcada `# plat-rotacao-temporaria`), troca a
senha, grava a credencial, reinicia `plat-api` e `plat-worker`, e só então remove a linha — velho e
novo autenticam durante a troca; a senha velha morre quando a janela fecha (a prova confere isso
depois da remoção). **Custo assumido**: durante ~2-5 s, um processo LOCAL conecta como `plat_app` sem
senha — janela curta, só localhost, só uma role, remoção garantida por `finally`. Rode em horário de
baixa se isso pesar na sua avaliação de risco.

**Ativação por soquete**: com `plat-api.socket` ativo (instalado pelo `install.sh` desta versão),
quem chama a API durante o restart espera na fila do kernel e recebe a resposta segundos depois, sem
erro. Confira com `systemctl is-active plat-api.socket`; numa máquina instalada antes desta versão,
rode `sudo bash install.sh <dominio> <porta>` uma vez para ativar (sem o soquete, a janela do restart
é connection refused de ~1-2 s, e 502 no nginx).

```
sudo scripts/plat segredo rotacionar PLAT_DSN
```

Confirme:
```
systemctl is-active plat-api.socket plat-api plat-worker
sudo grep -c plat-rotacao-temporaria /etc/postgresql/16/main/pg_hba.conf   # tem de ser 0 (janela fechada)
curl -s http://127.0.0.1:8150/saude | head -c 300; echo    # 200, banco ok
```

## 3. `PLAT_DSN_WORKER` (senha da role `plat_worker`, autoridade sobre estado de job)

Rotacione se suspeitar que alguém obteve essa senha (ela sozinha basta para terminar/devolver job de
QUALQUER inquilino, achado do adversário do T2 — não há segunda checagem). Mesma janela `trust` de
segundos da seção 2, agora para a role `plat_worker`; o worker reinicia e os jobs em andamento são
devolvidos (`reinicios += 1`) e retomados — não são perdidos, só atrasam alguns segundos.

```
sudo scripts/plat segredo rotacionar PLAT_DSN_WORKER
```

Confirme:
```
curl -s http://127.0.0.1:8153/saude | head -c 300; echo
```
Jobs em andamento no momento do restart são devolvidos automaticamente (`reinicios += 1`) e retomados
pelo worker novo — não são perdidos, só atrasam alguns segundos.

## 4. `PLAT_GARAGE_ADMIN_TOKEN` (bearer da Admin API do Garage, cria/apaga bucket e chave)

**Único que reinicia DOIS serviços** — o Garage primeiro, depois `plat-api`. Se o Garage estiver
servindo upload/download ativo de outro produto desta máquina (não só o `plat`), avise as outras
frentes antes: o restart do Garage é rápido, mas é um restart de verdade.

```
sudo scripts/plat segredo rotacionar PLAT_GARAGE_ADMIN_TOKEN \
  --unidade-garage plataforma-garage --porta-garage-admin 3903 --saude-garage /health \
  --garage-toml /home/dev/plataforma/pipeline/garage/garage.toml
```

Confirme:
```
sudo systemctl is-active plataforma-garage plat-api
curl -s http://127.0.0.1:8150/saude | head -c 300; echo
```

**Ressalva declarada (lida pelo adversário do item):** o `garage.toml` do daemon continua com
`admin_token` e `rpc_secret` em texto — o Garage não aceita `LoadCredential=` para a própria
configuração, e o arquivo é da frente `plataforma/pipeline` (regra da casa: nunca editar). A
mitigação é a que existe: `0600`, dono `dev` (o mesmo usuário do daemon), e o `plat` nunca lê esse
arquivo em operação — o `install.sh` só copia o token dele para `/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN`
(root 0600), que é o que as unidades `plat-*` recebem por `LoadCredential=`. O segredo que o PRODUTO
usa está fora de texto plano; o do daemon é fronteira da outra frente.

## 5. Chave S3 de um inquilino (`PLAT_GARAGE_CHAVE_S3:<slug>`)

Use quando suspeitar que a chave S3 de UM inquilino específico vazou (nunca precisa rotacionar a de
todo mundo por causa de um). **Não reinicia nada** — efeito imediato na próxima requisição.

```
sudo scripts/plat segredo rotacionar PLAT_GARAGE_CHAVE_S3:<slug-do-inquilino>
```

Confirme (peça para o inquilino tentar um upload/download logo em seguida, ou verifique
`plat.arquivo_bucket` pelo painel interno) — não há `/saude` específico porque nenhum processo
reiniciou.

## 6. Se algo der errado no meio de uma rotação

Todo script grava o JSON do resultado na saída padrão (e com `--json-saida <caminho>`, também em
arquivo) — ele traz `restart_falhou` (bool) e, para os dois que checam autenticação, se o valor
ANTIGO/NOVO efetivamente bateu. Se `restart_falhou: true`:

```
sudo journalctl -u <unidade> -n 50 --no-pager     # a unidade que falhou a subir
```

O credential ANTIGO nunca é apagado até o novo estar gravado (a ordem de escrita está fixada no
próprio script — banco/Garage primeiro, arquivo depois, restart por último), então o pior caso é a
unidade não subir com o valor novo — nesse caso, restaure manualmente o valor anterior no arquivo de
`/etc/plat/segredos/<NOME>` (você tem o `sha_antigo`/`sha_senha_antiga` no JSON para conferir contra o
que restaurar, mas não o valor em si — se você não guardou o valor antes de rodar o comando, terá que
gerar um novo de novo, o que é seguro: nenhum estado depende do valor específico, só de ele bater dos
dois lados).

## 7. Adotar socket activation em produção (pendência registrada, não deste turno)

A técnica que garante "zero 5xx durante o restart" (§2 de `docs/SEGURANCA.md`) foi medida contra um
serviço DE TESTE, não contra `plat-api`/`plat-worker` reais — adotá-la pede editar
`deploy/plat-api.service`/`plat-worker.service` para declarar `Sockets=` e criar as unidades `.socket`
companheiras, e isso só tem efeito depois de UM restart controlado (para o processo passar a receber o
FD do socket em vez de abrir a porta sozinho). Isso é uma mudança maior que uma rotação de segredo —
trate como um item novo, com o restart agendado e avisado, não como parte do plantão de rotação.
