# Manual do `plat`

Uma seção por tela ou operação, sempre com a captura real produzida pelo teste e2e do item. Em 0.1.0
existe uma tela (a página inicial de saúde) e uma operação de administração (instalar e atualizar).
Tudo o mais que o produto virá a fazer está em `/home/dev/plataforma/laco/PAINEL.md`, não aqui.

Estado: análise / beta privado. A URL é interna, marcada `noindex`, e não deve ser linkada de lugar
público.

---

## 1. Acesso e saúde do serviço

### 1.1 URL interna

`https://plat.iagrointel.com`. HTTP redireciona para HTTPS (301). Não há login em 0.1.0: a página
inicial e as duas rotas de saúde são públicas para quem conhece o endereço, e nenhuma delas devolve
dado de inquilino.

Captura do e2e (`tests/e2e/capturas/L0-01-repo_inicio.png`, gerada por
`tests/e2e/test_saude_pagina.py` no chromium do playwright; o PNG fica fora do git e é regravado a cada
`make e2e`):

![Página inicial do plat: versão, git, ambiente e o JSON de /saude com estado ok](tests/e2e/capturas/L0-01-repo_inicio.png)

O que a tela mostra, de cima para baixo: o nome `plat` e o aviso "análise / beta privado"; um painel
com `versão` (conteúdo do arquivo `VERSAO`), `git` (12 primeiros caracteres do commit em execução) e
`ambiente` (`producao` ou `dev`), lidos de `/api/versao`; um painel `saúde` com o estado (`ok` em verde,
ou o código HTTP e o estado do banco em vermelho) e o JSON completo de `/saude`. A tela não tem botão.

### 1.2 O que `/saude` devolve

`GET https://plat.iagrointel.com/saude` (também `HEAD`, para sondas com `curl -sI`):

```json
{
  "versao": "0.1.0",
  "git_sha": "8ffe950516f5",
  "ambiente": "producao",
  "banco": "ok",
  "migracoes_aplicadas": 2,
  "migracoes_pendentes": 0,
  "ultima_migracao": "002_identidade",
  "servicos": {"martin": "ausente", "titiler": "ausente", "garage": "ok"},
  "tempo_ms": 1.7,
  "em": "2026-09-05T13:14:45Z"
}
```

| campo | como ler |
|---|---|
| `versao` | versão do produto (arquivo `VERSAO`). Deve ser igual ao `versão` da tela e ao `CHANGELOG.md`. |
| `git_sha` | commit em execução. Compare com `git -C /home/dev/plataforma/enterprise rev-parse --short=12 HEAD`. Se diferir, alguém comitou sem reiniciar o serviço: `sudo systemctl restart plat-api`. |
| `ambiente` | `producao` na URL interna. `dev` só em instalação de desenvolvimento. |
| `banco` | `ok` = o banco respondeu e todas as migrações do repositório estão aplicadas. `desatualizado` = há arquivo em `db/migracoes/` sem registro no banco; rode `sudo bash install.sh plat.iagrointel.com 8150` (ou `make migrar`). `erro` = o banco não respondeu; veja `journalctl -u plat-api -o cat`. |
| `migracoes_aplicadas` / `migracoes_pendentes` / `ultima_migracao` | contagem em `plat.versao_migracao` contra os arquivos em disco. Pendentes tem de ser 0. |
| `servicos` | `martin` e `titiler` estão `ausente` porque os serviços ainda não existem (portas 8151 e 8152 reservadas); `garage` é o armazenamento de objetos já ativo na máquina, sondado com timeout de 1 s. Nenhum dos três muda o status HTTP em 0.1.0. |
| `tempo_ms` | tempo da rota, da entrada à montagem do JSON. |
| `em` | instante da resposta, UTC. |

O status HTTP é **200 só com `banco = ok`**; `desatualizado` e `erro` devolvem **503** com o mesmo JSON.
Um monitor deve tratar 503 como falha, não como "respondeu".

`GET /api/versao` devolve só `versao`, `git_sha`, `ambiente` e `em`, sem tocar o banco, sempre 200.
Serve para conferir que a página e a API são a mesma implantação.

Toda resposta traz `X-Robots-Tag: noindex, nofollow` e `Strict-Transport-Security: max-age=31536000`
(medido em 11 de 11 rotas HTTPS, incluindo 404 e arquivos estáticos; `tests/medidas/L0-01-repo.json`,
`x_robots_tag_rotas_com_noindex` e `hsts_rotas_https`) e a API traz `X-Req-Id`, um identificador de 16 caracteres hexadecimais que aparece na linha JSON do journal.

### 1.3 Conferência rápida pela linha de comando

```
curl -sS https://plat.iagrointel.com/saude | python3 -m json.tool     # 200 e banco ok
curl -sI https://plat.iagrointel.com/saude | grep -iE 'x-robots-tag|strict'   # noindex, nofollow · max-age=31536000
systemctl status plat-api --no-pager | sed -n 1,6p                    # active (running), NRestarts
journalctl -u plat-api -o cat -n 20 | jq .                            # últimas linhas JSON
```

Latência de referência, medida do próprio servidor, 20 chamadas (`curl -s -o /dev/null -w
%{time_total}`, rodada 2): mediana 19,8 ms com conexão TLS nova, 1,9 ms com conexão reaproveitada. Um usuário
remoto verá o tempo de rede somado a isso.

---

## 2. Instalação e atualização

### 2.1 Comando

```
cd /home/dev/plataforma/enterprise
sudo bash install.sh plat.iagrointel.com 8150
```

O script é idempotente: roda em máquina nova e roda de novo depois de cada `git pull` ou commit, sem
passo manual. É o único caminho de instalação e de atualização; o que ele não faz, não existe.

### 2.2 O que ele cria

| onde | o quê |
|---|---|
| banco `iagro_sat` | extensões `postgis` e `pgcrypto`; schema `plat`; role `plat_app` (sem BYPASSRLS, sem posse); migrações de `db/migracoes/` registradas em `plat.versao_migracao` com sha256; inquilinos `demo` e `demo2` com um administrador cada |
| `/etc/postgresql/16/main/pg_hba.conf` | linha `host iagro_sat plat_app 127.0.0.1/32 scram-sha-256` (uma vez) e `pg_reload_conf()` |
| repositório | `.env` (modo 600) com senha da role, `PLAT_SECRET`, ambiente, URL e `PLAT_GIT_SHA` do commit instalado; `venv/` com todas as dependências de `requirements.txt` (sem nada do diretório do usuário: `PYTHONNOUSERSITE=1`); `tests/credenciais.txt` (modo 600) com as senhas dos administradores `demo admin` e `demo2 admin`, entregues ao gerador de hash por stdin |
| `/etc/systemd/system/plat-api.service` | unidade habilitada e reiniciada; espera até 30 s por `/saude` = 200 na porta local |
| `/etc/nginx/sites-enabled/plat.iagrointel.com` | bloco gerado de `deploy/nginx.conf` (noindex e HSTS em toda `location`), preservando as linhas do certbot; troca atômica: se `nginx -t` reprovar, o bloco anterior volta e o script para com 5 |
| `/etc/letsencrypt/live/plat.iagrointel.com/` | só na primeira vez, via `certbot --nginx` |

A senha da role no banco é sempre realinhada à do `.env`; apagar o `.env` e reinstalar gera senha e
segredo novos (a senha antiga deixa de autenticar). As senhas dos administradores de demonstração só
são geradas se `tests/credenciais.txt` não existir; apagar o arquivo e reinstalar rotaciona as duas.

### 2.3 Como conferir

A última linha do script é `== instalado em N s: https://plat.iagrointel.com (serviço plat-api, porta
8150)`. Antes dela, o passo j imprime `https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag:
noindex, nofollow · Strict-Transport-Security: max-age=31536000`; qualquer outro resultado encerra o
script com erro (código de saída 1 no serviço ou na venv, 3 em migração divergente, 4 na conferência
pública, 5 em bloco nginx reprovado).

Depois:

```
make check                     # ruff + varredura de marcador + 81 testes rápidos + 1 e2e, em ~3 s
make vendor                    # sha256 de web/vendor contra VERSOES.txt
sudo -u postgres psql -d iagro_sat -Atc "select nome, left(sha256,12), aplicada_em from plat.versao_migracao"
sudo grep -c plat_app /etc/postgresql/16/main/pg_hba.conf      # 1
systemctl show plat-api -p NRestarts -p MemoryCurrent
```

Números do testador para esta instalação (`tests/medidas/L0-01-repo.json`): do zero, com schema e role
apagados, 6,24 s; com `.env`, credenciais e linha do pg_hba também apagados, 9,14 s; repetida em seguida,
4,69 s (rodada 1); reinstalação do zero pelo adversário sobre `8ffe950`, 9,66 s; `make check` 2,86 s,
rc=0; 82 testes coletados, 81 rápidos e 1 e2e passando; serviço com 88,5 MB no cgroup e 0 reinícios
(rodada 2).

### 2.4 Atualizar

```
cd /home/dev/plataforma/enterprise && git pull && sudo bash install.sh plat.iagrointel.com 8150
```

O `install.sh` aplica as migrações novas, reinstala dependências, reinicia o serviço e reconfere a URL.
Se `/saude` mostrar `banco: desatualizado` (HTTP 503), a migração não foi aplicada: veja a saída do
passo c. Se `git_sha` de `/saude` não bater com `git rev-parse HEAD`, o serviço não foi reiniciado.

### 2.5 Limites conhecidos em 0.1.0

- A "máquina que nunca viu o repositório" foi simulada nesta máquina (venv, `.env` e certificado
  reaproveitados; a prova é a importação da aplicação sem o diretório do usuário). Uma instalação em
  outro servidor ainda não foi feita.
- Os passos do certbot em domínio sem certificado (i2/i3) e a restauração do bloco nginx quando
  `nginx -t` reprova foram lidos, não exercitados.
- As contas `demo` e `demo2` são de teste; as senhas ficam só em `tests/credenciais.txt` (modo 600).
