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

## 1. `PLAT_SECRET` (chave de cifra/HMAC da aplicação)

**O que quebra**: nenhuma URL assinada de objeto emitida ANTES da rotação (a cliente pede outra, sem
estado a limpar) nem sessão TOTP/LDAP/SMTP/conexão externa (o valor antigo continua legível por 24h
como `PLAT_SECRET_ANTERIOR` — dupla-chave). Depois das 24h, quem tinha algo cifrado só com o valor de
DUAS rotações atrás perde acesso (recadastra 2FA, reconfigura LDAP/SMTP/conexão) — normal, é a janela.

```
sudo scripts/plat segredo rotacionar PLAT_SECRET
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

**O que quebra**: nada em produção normal — a troca de senha e o restart de `plat-api` acontecem juntos,
não há usuário conectado diretamente com essa role fora da própria API.

```
sudo scripts/plat segredo rotacionar PLAT_DSN
```

Confirme:
```
curl -s http://127.0.0.1:8150/saude | head -c 300; echo    # 200, banco ok
```

## 3. `PLAT_DSN_WORKER` (senha da role `plat_worker`, autoridade sobre estado de job)

Rotacione se suspeitar que alguém obteve essa senha (ela sozinha basta para terminar/devolver job de
QUALQUER inquilino, achado do adversário do T2 — não há segunda checagem).

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
