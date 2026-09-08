# Runbook — Garage replicado (item L7-07-b-replica-garage)

Para quem opera o armazenamento de objetos da plataforma (Garage v2.3.0, S3-compatível; ADR 0006). Hoje a
instalação hospedada roda **1 nó com `replication_factor = 1`** (`plataforma-garage`, config em
`/home/dev/plataforma/pipeline/garage/garage.toml`); este documento diz como passar a 2 e 3 nós e o que muda.
Tudo abaixo foi exercitado por `tests/operacao/test_garage_replica.py` com o binário desta instalação em
processos locais; os números estão em `tests/medidas/L7-07-b-replica-garage.json`.

## 0. A regra que decide tudo: quórum

Garage grava um objeto em `replication_factor` nós e exige **quórum de escrita = rf/2 + 1** e **quórum de
leitura = 1** (`consistency_mode = "consistent"`, o padrão). Consequência medida (não opinião):

| nós | rf | 1 nó parado: leitura | 1 nó parado: escrita |
|---|---|---|---|
| 1 | 1 | não | não |
| 2 | 2 | **sim** | **não** — `503 ServiceUnavailable: Could not reach quorum of 2` |
| 3 | 3 | sim | sim (quórum 2 de 3) |

Ou seja: **2 nós com rf=2 protegem o DADO (uma cópia a mais) mas não a DISPONIBILIDADE de escrita.** Para
"perde um nó e continua escrevendo" são 3 nós com rf=3 — é o alvo quando houver a terceira máquina (spec 18).
Quem promete SLA de escrita com 2 nós está errado; o que se promete é que nenhum objeto se perde com a queda
de um disco.

## 1. Segredos fora do `garage.toml` (L7-19)

`rpc_secret`, `admin_token` e `metrics_token` vão em arquivo 0600 e o toml aponta com `*_file`:

```
rpc_secret_file    = "/etc/plat/segredos/GARAGE_RPC_SECRET"
[admin]
admin_token_file   = "/etc/plat/segredos/GARAGE_ADMIN_TOKEN"
metrics_token_file = "/etc/plat/segredos/GARAGE_METRICS_TOKEN"
```

`/metrics` na porta de administração responde 401 sem `Authorization: Bearer <metrics_token>` e 200 com ele
(é o que o Prometheus da casa usa; L7-06). O `rpc_secret` tem de ser **o mesmo em todos os nós** — é o que
autentica um nó no cluster; nó com segredo diferente não conecta.

## 2. Adicionar o segundo (ou terceiro) nó

Na máquina nova: mesmo binário, `garage.toml` com `replication_factor` igual ao do cluster (**todos os nós
precisam do mesmo valor**; mudar rf em cluster vivo exige `garage layout` novo e reescrita dos dados),
`rpc_bind_addr = "0.0.0.0:3901"`, `rpc_public_addr = "<ip da máquina>:3901"` (o IP que os outros alcançam;
em VPN/WireGuard, o IP da VPN), o mesmo `rpc_secret_file`.

```
# no nó novo, depois de `systemctl start plataforma-garage`
garage node id                     # -> <id>@<ip>:3901
# em qualquer nó já no cluster
garage node connect <id>@<ip>:3901
garage status                      # os dois aparecem; o novo sem papel ("NO ROLE ASSIGNED")
garage layout assign -z <zona> -c <capacidade, ex. 400G> <id-curto>
garage layout show                 # confere
garage layout apply --version <n+1>
```

Zona = onde o dado NÃO pode ter as duas cópias juntas (rack, sala, provedor): com rf=2 e duas zonas cada
objeto fica uma vez em cada zona. Capacidade é o que o Garage pode usar naquele disco, não o tamanho dele.

Depois do `apply` o cluster **rebalanceia sozinho** (blocos copiados para o nó novo pelos resync workers).
Acompanhe em `garage stats` (`resync queue length` cai até 0) e `garage worker list`.

## 3. Trocar um disco (ou perder um nó de vez)

1. Suba o nó novo com `metadata_dir`/`data_dir` vazios e o MESMO `rpc_secret`.
2. `garage node connect` a partir de um nó vivo.
3. `garage layout assign -z <zona> -c <cap> --replace <id-do-nó-morto> <id-do-nó-novo>`; `garage layout apply --version <n+1>`.
4. Depois que o nó religa, refaça `garage node connect <id>@<ip>:3901` A PARTIR de cada nó vivo (medido: sem
   isso o nó volta como "healthy" com hostname `?` e a sincronização não anda); então `garage repair --yes tables` em cada nó que TEM o dado (medido: sem isso a anti-entropia de metadados só
   roda a cada 10 min — o nó religado ficou 613 s sem uma referência de bloco; com o comando, 100 objetos em
   3 s), depois `garage repair --yes blocks` no nó novo; `garage worker set resync-tranquility 0` acelera.
   Critério de pronto: `garage stats` sem `blocks with resync errors` e o conjunto de blocos em `data_dir`
   igual ao dos outros nós (a fila de resync mantém entradas reagendadas mesmo depois de copiadas).
5. `garage repair --yes scrub start` e `garage block list-errors` vazio = integridade conferida.

Medido nesta máquina (3 nós rf=3, processos locais, disco compartilhado): 1.000 objetos de 16 KiB escritos
com um nó parado ficaram todos legíveis por esse nó depois de religado, sha256 por sha256, com o nó que os
recebeu DESLIGADO na conferência; 256 MiB re-sincronizados no tempo registrado na medida. **10 GB não foi
medido** (teto de 3 GB por trilha, D21) — não extrapole em documento de cliente.

## 4. Ver o estado

```
garage status                # nós, zonas, capacidade, dados/metadados disponíveis
garage layout show           # papel de cada nó e mudanças pendentes
garage stats                 # fila de resync, blocos com erro, tabelas
garage worker list           # resync workers, scrub worker (Busy/Idle), GC
garage block list-errors     # blocos que não conseguiram ser lidos/copiados (tem de estar vazio)
garage bucket info <bucket>  # cota, chaves, contagem, bytes
```

## 5. Scrub por timer

`deploy/plat-garage-scrub.service` + `.timer` (domingo 03:00, `Persistent=true`) rodam
`garage repair --yes scrub start` na instância da máquina. Caminhos do binário e da config vêm de
`/etc/plat/garage.env` (`GARAGE_BIN=`, `GARAGE_CONFIG=`); sem o arquivo valem os da prova desta máquina.
O scrub lê todos os blocos do disco e compara com o hash do nome; bloco corrompido vai para
`garage block list-errors` e é reparado a partir de outra réplica pelo resync (só existe réplica com rf >= 2 —
com rf=1 o scrub só AVISA).

## 6. Cotas por bucket

`garage bucket set-quotas --max-size <n>MiB|GiB [--max-objects n] <bucket>` — sobrevivem a réplica e
rebalanceamento (são metadado do bucket, replicado como tudo). Objeto acima da cota é recusado com
`403 AccessDenied` (é assim que o Garage responde; a aplicação já traduz para `cota_excedida`, ADR 0006).

## 7. O que NÃO fazer

- Não mude `replication_factor` no toml de um nó só: o nó não sobe ("replication factor mismatch").
- Não apague `metadata_dir` de um nó vivo para "limpar": é o índice; sem ele o nó re-baixa tudo.
- Não use `garage repair clear-resync-queue` sem `repair blocks` em seguida (a fila é o que ainda falta copiar).
- Com 2 nós rf=2, não prometa escrita durante manutenção de um nó: pare o nó em janela e avise; a leitura segue.
