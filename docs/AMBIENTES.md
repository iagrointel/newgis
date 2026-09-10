# Ambientes: o que é separado, o que é compartilhado, e como se troca segredo em produção

Item L7-31 (ambiente de homologação) e item L7-19 (segredos e certificados), depois da refutação do
adversário independente no turno 3 (`laco/handoffs/T3/ataque-g6-ADVERSARIO.md`, achados 11, 17 e 18).

O documento responde três perguntas, nesta ordem: o que passou a ser separado por ambiente; o que
continua compartilhado e por quê; que passos ficaram para o dono executar em produção.

## 1. O achado que gerou este documento

O adversário mediu que `PLAT_GARAGE_ADMIN_TOKEN` era byte a byte o mesmo em produção e em homologação:

    sha256 do token de PRODUCAO: e36bc0be9a6500d9
    sha256 do token de HOMOLOG : e36bc0be9a6500d9

Com o token lido de `var/homolog/homolog.env` ele listou e leu, pela API de administração do Garage, os
buckets de produção `plat-demo` (84 objetos, 127.026.292 bytes) e `plat-demo2`. O prefixo de bucket
(`homolog-plat-` contra `plat-`) separava o nome do caminho, não o poder da credencial.

## 2. O que é separado por ambiente (medido)

| o que | produção | homologação | como se garante |
|---|---|---|---|
| schema do banco | `plat` / `plat_trabalho` | `plat_homolog` / `plat_trabalho_homolog` | `PLAT_SCHEMA`, `app/schema_ambiente.py` |
| role do Postgres | `plat_app`, `plat_worker` | `plat_homolog_app`, `plat_homolog_worker` | `db/homolog_bootstrap.sh` seção b |
| senha de banco | credencial do systemd | gerada em `var/homolog/segredos.env` | bootstrap, seção b |
| `PLAT_SECRET` | credencial do systemd | gerado em `var/homolog/segredos.env` | bootstrap, seção b |
| credencial do armazenamento | token de administração do Garage | **chave S3 própria**, sem administração | `scripts/garage_homolog_provisionar.sh` |
| bucket | alias GLOBAL `plat-<slug>` | alias LOCAL da chave, `homolog-plat-<slug>` | `ClienteS3.criar_bucket` |
| senha de administrador semeada | `tests/credenciais.txt` | `tests/credenciais_homolog.txt` | bootstrap, seção e |

O mecanismo novo é o da penúltima linha. Homologação recebe uma chave S3 do Garage com permissão de
criar bucket e nenhum poder de administração. Duas propriedades foram medidas nesta máquina (Garage
v2.3.0) antes de o desenho entrar:

1. Bucket criado por essa chave nasce com **alias local dela** — não entra no espaço de nomes global.
   `ListBuckets` da API de administração mostra `"globalAliases": []` e
   `"localAliases": [{"accessKeyId": "GKa8ea06…", "alias": "homolog-plat-…"}]`.
2. Essa chave recebe `403 AccessDenied` em qualquer bucket de que não seja dona, tanto para ler quanto
   para escrever. Medido contra `plat-demo` e `plat-demo2`.

Quando `PLAT_GARAGE_ADMIN_TOKEN` está ausente e `PLAT_GARAGE_CHAVE_ID`/`PLAT_GARAGE_CHAVE_SEGREDO`
estão presentes, `app/objetos.py` entra sozinho no modo de chave própria: cria o bucket pelo
`CreateBucket` do S3 e usa a mesma chave para tudo. Produção não declara essas duas chaves e continua
no modo de administração, sem uma linha de comportamento alterada.

A prova viva está em `tests/unit/test_isolamento_homologacao.py` (8 testes, só leitura, pulam com motivo
se o Garage não estiver de pé). Ela cobre: nenhum valor de segredo repetido entre os dois arquivos de
ambiente; nenhum token de administração no ambiente de homologação, inclusive na configuração EFETIVA
(que herda o `.env` de produção); `ListBuckets` da chave de homologação sem bucket de produção; `403` ao
listar `plat-demo` e `plat-demo2`; recusa da API de administração ao segredo de homologação.

### Limitações declaradas do modo de chave própria

São consequência de não haver poder de administração ali, e valem **só em homologação**:

- **Não há par RW/RO distinto.** Criar chave nova é chamada de administração. A mesma chave é gravada
  como RW e RO em `arquivo_bucket`. Homologação, portanto, não exercita a separação de leitura e
  escrita por chave; produção continua exercitando.
- **A cota não é gravada no Garage.** Quem barra o excesso em homologação é só a checagem da aplicação
  em `objetos.guardar()`. Em produção o Garage também barra, com `403`.
- **O uso em bytes vem de uma listagem**, não do `GetBucketInfo` somado pelo servidor. Mesmo número, um
  pedido a mais; aceitável no volume de homologação.

## 3. O que continua compartilhado, e por quê

- **O daemon do Garage** (`plataforma-garage`, S3 em `127.0.0.1:3900`) é um só nesta máquina. O disco
  está a 98% nos dois servidores (D21) e não há espaço para uma segunda instância. O que deixou de ser
  compartilhado é a CREDENCIAL, não o processo.
- **O servidor Postgres e o banco `iagro_sat`** são os mesmos, pelo mesmo motivo. A separação é por
  schema e por role, com `GRANT` — o papel `plat_homolog_app` não tem `USAGE` em `plat`.
- **O `.env` da raiz do repositório** é lido por qualquer processo que rode dessa árvore, inclusive o de
  homologação (`app/settings.py::valores_do_ambiente` lê o `.env` primeiro e o ambiente do processo
  depois). Por isso `var/homolog/homolog.env` declara `PLAT_GARAGE_ADMIN_URL=` e
  `PLAT_GARAGE_ADMIN_TOKEN=` **vazios**: sem isso o token de produção voltaria a valer para homologação
  por herança. O teste `test_configuracao_efetiva_de_homologacao_nao_tem_administracao` existe
  exatamente para pegar essa regressão.
- **O usuário do sistema.** Tudo nesta máquina roda como `dev`. Um segredo entregue por
  `LoadCredential=` fica fora do `.env`, do `argv` e do journal, e fora do alcance de outro usuário —
  mas outro processo rodando como `dev` lê o arquivo em `/run/credentials/<unidade>/` se souber o
  caminho. Isolamento por unidade de verdade pediria `DynamicUser=`, que reescreveria o dono de toda a
  árvore do repositório. Está registrado em `docs/SEGURANCA.md` §1 e continua valendo.
- **O passo de provisionamento é de operador, não do ambiente.** Quem roda
  `scripts/garage_homolog_provisionar.sh` precisa do `garage.toml` (que tem o `rpc_secret`) para falar
  com o daemon. Nesta máquina isso não é criptograficamente separável do ambiente, pelo motivo do item
  anterior. O que mudou, e é o que o portão pede: o arquivo de ambiente de homologação e os processos
  de homologação não carregam mais a credencial raiz.
- **As trilhas do laço** (`laco/var/trilha/*.env`) ainda recebem o token de administração de produção,
  com prefixo de bucket próprio. Elas não foram convertidas para o modo de chave própria nesta passagem;
  são ambientes de trabalho de agente, não a homologação que o L7-15 usa como portão antes de produção.
  Fica nomeado, não escondido.

## 4. Os quatro segredos do produto e onde moram

`app/settings.SEGREDOS` é a lista canônica; `app.settings.segredos_em_claro(<arquivo>)` devolve os que
ainda estiverem em claro num `.env`, por nome, nunca por valor.

| segredo | o que é | onde deve morar | quem lê |
|---|---|---|---|
| `PLAT_SECRET` | HMAC de URL assinada e cifra do TOTP | `/etc/plat/segredos/PLAT_SECRET` | `plat-api`, `plat-worker` |
| `PLAT_DSN_WORKER` | senha da role `plat_worker` | `/etc/plat/segredos/PLAT_DSN_WORKER` | `plat-worker` |
| `PLAT_DSN` | senha da role `plat_app` | `/etc/plat/segredos/PLAT_DSN` | `plat-api`, `plat-worker` |
| `PLAT_GARAGE_ADMIN_TOKEN` | credencial raiz do armazenamento | `/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN` | `plat-api`, `plat-worker` |
| `PLAT_GARAGE_CHAVE_SEGREDO` | chave S3 de ambiente sem administração | `var/homolog/homolog.env` (0600) | só homologação |

Os dois primeiros já estavam fora do `.env` antes deste conserto. Os dois seguintes **ainda não estão**
na instalação de produção desta máquina — o código, a unidade, o instalador e a rotação já os esperam
lá, mas mover o valor derruba serviço vivo e é passo do dono, abaixo.

Rotação: `sudo bash scripts/rotacionar_segredo.sh <NOME>` cobre os quatro, mais
`PLAT_GARAGE_S3 <slug>` (par de chaves S3 do bucket de um inquilino, guardado em
`plat.arquivo_bucket`; é a única rotação sem reinício, porque a aplicação lê essas chaves do banco a
cada chamada).

## 5. Passos para o DONO executar em produção

Nenhum destes passos foi executado. Cada um diz o comando exato, o efeito e como voltar atrás.

### Passo 1 — tirar `PLAT_DSN` e `PLAT_GARAGE_ADMIN_TOKEN` do `.env`

Efeito: as duas linhas somem do `/home/dev/plataforma/enterprise/.env`; os valores passam a viver em
`/etc/plat/segredos/`, 0600, dono `root`, entregues por `LoadCredential=`. `plat-api` e `plat-worker`
reiniciam (poucos segundos cada).

    cd /home/dev/plataforma/enterprise
    sudo cp .env /root/plat-env-antes-L7-19.bak        # rede de segurança
    sudo bash install.sh                                # seção d2 migra, h instala as unidades e reinicia
    curl -fsS http://127.0.0.1:8150/saude               # tem de devolver 200
    grep -cE '^(PLAT_DSN|PLAT_GARAGE_ADMIN_TOKEN)=' .env   # tem de devolver 0

Voltar atrás: `sudo cp /root/plat-env-antes-L7-19.bak .env`, apagar as duas linhas `LoadCredential=`
novas de `/etc/systemd/system/plat-api.service` e `plat-worker.service`, `sudo systemctl daemon-reload`,
`sudo systemctl restart plat-api plat-worker`.

### Passo 2 — tirar `rpc_secret` e `admin_token` do `garage.toml`

Efeito: os dois segredos saem do arquivo lido por qualquer processo do usuário `dev` e passam a ser
entregues por `LoadCredential=` à unidade. O daemon `plataforma-garage` reinicia: o S3 fica indisponível
por alguns segundos, e com ele a entrega de objeto e os tiles que dependem dela.

    sudo install -d -m 0700 -o root -g root /etc/plat/segredos-garage
    sudo sh -c 'grep -oP "^rpc_secret\s*=\s*\"\K[^\"]+" /home/dev/plataforma/pipeline/garage/garage.toml > /etc/plat/segredos-garage/rpc_secret'
    sudo sh -c 'grep -oP "^admin_token\s*=\s*\"\K[^\"]+" /home/dev/plataforma/pipeline/garage/garage.toml > /etc/plat/segredos-garage/admin_token'
    sudo chmod 600 /etc/plat/segredos-garage/*
    sudo cp /home/dev/plataforma/pipeline/garage/garage.toml /root/garage-toml-antes-L7-19.bak
    sudo install -d /etc/systemd/system/plataforma-garage.service.d
    sudo cp /home/dev/plataforma/enterprise/deploy/plataforma-garage-segredos.conf \
            /etc/systemd/system/plataforma-garage.service.d/segredos.conf
    sudo -u dev sed -i -E '/^(rpc_secret|admin_token)[[:space:]]*=/d' /home/dev/plataforma/pipeline/garage/garage.toml
    sudo systemctl daemon-reload
    sudo systemctl restart plataforma-garage
    curl -fsS -H "Authorization: Bearer $(sudo cat /etc/plat/segredos-garage/admin_token)" \
         http://127.0.0.1:3903/v2/ListBuckets | head -c 120     # tem de listar os buckets

Voltar atrás: `sudo cp /root/garage-toml-antes-L7-19.bak /home/dev/plataforma/pipeline/garage/garage.toml`,
`sudo rm /etc/systemd/system/plataforma-garage.service.d/segredos.conf`, `sudo systemctl daemon-reload`,
`sudo systemctl restart plataforma-garage`.

Já medido nesta máquina, para o passo não ser uma aposta: `GARAGE_RPC_SECRET_FILE=<arquivo>
garage -c <garage.toml sem a linha rpc_secret> status` fala com o daemon vivo e devolve o nó saudável —
a forma por arquivo funciona neste binário (v2.3.0).

### Passo 3 (opcional) — deixar de usar o token estático do `garage.toml` na aplicação

Só faz sentido depois do passo 1. Cria um token de administração gerenciado pelo próprio Garage, com
nome e histórico, e aponta a aplicação para ele:

    sudo bash /home/dev/plataforma/enterprise/scripts/rotacionar_segredo.sh PLAT_GARAGE_ADMIN_TOKEN

O token estático continua valendo enquanto existir no `garage.toml` (ou no arquivo do passo 2): esta
rotação troca a credencial da APLICAÇÃO, não mata a antiga. Voltar atrás: gravar o valor anterior em
`/etc/plat/segredos/PLAT_GARAGE_ADMIN_TOKEN` e reiniciar `plat-api` e `plat-worker`.

### Passo 4 — reconstruir o ambiente de homologação com a credencial nova

Já rodado nesta máquina para o `var/homolog/homolog.env` instalado; fica escrito porque toda instalação
nova precisa dele, e porque é o comando que reaplica o conserto se alguém regenerar o ambiente:

    cd /home/dev/plataforma/enterprise
    bash db/homolog_bootstrap.sh        # seção f2 chama scripts/garage_homolog_provisionar.sh

## 6. O que este documento NÃO conserta

- Achado 12 (o schema de dado por inquilino, `d_<slug>`, é criado por `format()` dentro de função
  PL/pgSQL e não é reescrito por ambiente) e achado 13 (`executemany()` e consulta em `bytes` escapam de
  `CursorSchemaAmbiente`) continuam abertos. São outra parte do item L7-31.
- As cláusulas `install.sh --ambiente homolog` e a unidade `plat-homolog.service` (e o `MemoryPeak` que
  ela permitiria medir) continuam sem artefato.
- O `.env` de produção desta máquina continua com os dois segredos em claro até o passo 1 acima ser
  executado. O teste do adversário `test_env_de_producao_nao_pode_ter_segredo_em_claro` continua
  `xfail(strict=True)` justamente por isso, e vai virar falha estrita — que é o sinal de que passou a
  aguentar — no minuto em que o dono rodar o passo 1.
