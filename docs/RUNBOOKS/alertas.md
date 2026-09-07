# Runbook dos alertas (item L7-06-b-alertas)

Análise / beta privado. Uma seção por alerta de `deploy/alertas.yml`. O rótulo `runbook` de cada
regra é a chave desta página: a mensagem que chega ao e-mail ou ao webhook carrega o rótulo, e é por
ele que se acha o que fazer. `tests/unit/test_alertas_regras.py` reprova regra sem seção aqui e seção
sem "O que fazer" e "Como confirmar" — o runbook não pode envelhecer em silêncio.

## 1. Onde cada peça mora

| peça | arquivo | como conferir |
|---|---|---|
| regras | `deploy/alertas.yml` | `promtool check rules deploy/alertas.yml` |
| casos das regras | `deploy/alertas_teste.yml` | `cd deploy && promtool test rules alertas_teste.yml` |
| roteamento e canais | `deploy/alertmanager.yml` | `amtool check-config deploy/alertmanager.yml` |
| encenação de verdade | `deploy/alertas_homologacao.sh` | ver secao 2 |
| receptor da encenação | `deploy/alertas_receptor_teste.py` | grava hora de chegada em JSON |
| medida da entrega | `tests/medidas/L7-06-b-alertas.json` | resultado da última encenação |

## 2. Como reproduzir a encenação inteira

A encenação sobe um Prometheus e um Alertmanager próprios (portas 8306/8307/8308/8309, dados em
diretório temporário) e usa os MESMOS `alertas.yml` e `alertmanager.yml` de produção — só os caminhos
de segredo são trocados por arquivos do diretório de trabalho. Nada da casa em `/opt/monitoring` é
tocado, nenhuma unidade `plat-*` de produção é parada.

    set -a; source /home/dev/plataforma/laco/var/trilha/<nome>.env; set +a
    venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8305 --no-access-log &
    PLAT_API_METRICS=http://127.0.0.1:8305/metrics bash deploy/alertas_homologacao.sh /tmp/veredito.json

O que ela provoca de verdade: enche um volume ext4 de 64 MiB montado em `/mnt/plat_homolog_alertas`
com `fallocate`; derruba um alvo `plat-*` que estava no ar; grava um backup com data de 30 h atrás e
deixa o ensaio de restauração sem nenhum registro; marca um job como rodando há 35 min; aponta a API
para um certificado que vence em poucos dias. No fim mata o próprio Alertmanager e confere que o
Prometheus acusa — é a refutação exigida pelo item.

## 3. Silêncio durante manutenção

    amtool --alertmanager.url=http://127.0.0.1:9093 silence add \
      servico=~".*" --duration=2h --comment "manutenção: <o que se vai fazer>"

Regra de casa: **só se silencia o que já está em modo somente-leitura**. A janela do silêncio começa
depois de a instalação entrar em somente-leitura e termina antes de ela voltar a aceitar escrita —
silêncio aberto sobre um sistema que ainda aceita escrita esconde exatamente o estrago que a
manutenção pode causar. Hoje esse casamento é PROCEDIMENTO, não automação: a plataforma ainda não tem
um modo somente-leitura de instalação inteira (`app/db.py::somente_leitura` é por conexão, não global),
então quem abre o silêncio é a mesma pessoa que põe a instalação em somente-leitura. Ver secao 6.

Para listar e retirar: `amtool silence query` e `amtool silence expire <id>`.

## 4. Canais

- **E-mail**: `receivers[critico-email-e-webhook].email_configs`. Só severidade `critico`. Nesta
  instalação o relay é o postfix local (`127.0.0.1:25`), sem autenticação. Para um servidor da
  organização, mudam `smtp_smarthost`, `smtp_from` e `smtp_require_tls` no bloco `global`, e entram
  `auth_username:` e `auth_password_file: /etc/plat/segredos/PLAT_SMTP_SENHA`. Os campos são os
  mesmos do `emailsettings` do Portal for ArcGIS, o que facilita reaproveitar o que a organização já
  tem configurado. ⚠ O Alertmanager 0.26 **não** aceita `to_file` nem `auth_username_file` (conferido
  com `amtool check-config` em 07/09/2026): o destinatário e o usuário ficam no arquivo, só a senha
  vem de fora.
- **Webhook** (ntfy, Slack e compatíveis): endereço em
  `/etc/plat/segredos/PLAT_ALERTA_WEBHOOK_URL`, credencial em
  `/etc/plat/segredos/PLAT_ALERTA_WEBHOOK_TOKEN`, enviada como `Authorization: Bearer`.
- **Canal de teste**: `/etc/plat/segredos/PLAT_ALERTA_TESTE_URL`, para onde vai a Sentinela.

## 5. Decisão: Alertmanager, não o alerting do Grafana

Ver `docs/adr/20260907T1830-alertador.md`. Em uma frase: as regras ficam em YAML no repositório e são
testáveis fora do ar (`promtool test rules`), o que o alerting do Grafana não oferece; o preço é um
serviço a mais no appliance, e esse preço foi medido e aceito.

## 6. O que este item NÃO entrega

- **Banner de alerta no painel do produto.** Previsto na hipótese do item, não construído: exige
  decidir qual privilégio permite a um alertador externo escrever no produto, já que `/api` é
  publicado pelo nginx e `/metrics` não é. Preferimos deixar a cláusula nomeada a apontar um webhook
  do Alertmanager para uma rota que não existe.
- **Modo somente-leitura de instalação inteira** para casar com o silêncio de manutenção (secao 3).
- Encenação de verdade de `RamDisponivelBaixa`, `TaxaDeErro5xxAlta`, `TileP95Lento`,
  `ReplicaAtrasadaOuParada` e `ReplicaSemMetrica`: as três primeiras exigiriam degradar a máquina
  compartilhada da casa, e as duas de réplica exigem uma réplica, que esta instalação não tem. As
  cinco estão cobertas por caso determinístico em `deploy/alertas_teste.yml`, o que prova a
  EXPRESSÃO, não o caminho inteiro.

---

# Alertas, um a um

## DiscoQuaseCheio

`runbook: discoquasecheio` · severidade aviso · serviço disco · dispara com uso acima de 85 % por 2 min.

Ingestão de dado geográfico enche disco rápido e sem aviso: um único arquivo de imagem pode dobrar o
uso em uma tarde.

**O que fazer.** Achar o que cresceu: `df -h` para o ponto de montagem do rótulo `mountpoint`, depois
`du -xh --max-depth=2 <ponto> | sort -h | tail -20`. Os suspeitos usuais, nesta ordem: diretório de
trabalho de job (`PLAT_JOBS_DIR`), dados do Garage, WAL do Postgres, log do nginx. Nada se apaga sem
saber o que é; log velho e recorte temporário de job são as duas coisas que se podem retirar sem
decisão de ninguém.

**Como confirmar.** `df -h <ponto>` abaixo de 85 % e o alerta some sozinho em até 2 min (a regra
resolve com `resolve_timeout` de 5 min no Alertmanager).

## DiscoCritico

`runbook: discocritico` · severidade critico · serviço disco · dispara com uso acima de 95 % por 2 min.

Este é o degrau em que a plataforma deixa de funcionar direito: ingestão falha no meio, o backup não
tem onde escrever e o Postgres pode parar de aceitar escrita.

**O que fazer.** O mesmo diagnóstico do `DiscoQuaseCheio`, mas primeiro se compra tempo: retirar o
log rotacionado e o diretório de trabalho de jobs já concluídos costuma devolver alguns por cento em
segundos. Só depois se procura a causa. Se o ponto for o do banco, conferir se há WAL acumulado por
réplica parada (`pg_stat_replication`) antes de mexer em qualquer outra coisa.

**Como confirmar.** `df -h <ponto>` abaixo de 95 %, e o `DiscoQuaseCheio` volta a aparecer sozinho
(a inibição deixa de valer) até o uso cair de 85 %.

## RamDisponivelBaixa

`runbook: ramdisponivelbaixa` · severidade aviso · serviço ram · dispara com MemAvailable abaixo de
2 GiB por 5 min.

**O que fazer.** `free -g` e `ps -eo rss,comm --sort=-rss | head`. Se o topo for um job pesado, ele
tem teto declarado (`PLAT_WORKER_MEMORIA_MB`) e a fila deve estar respeitando — se não estiver, é
defeito, não capacidade. Nunca matar o Postgres para liberar memória: o matador por falta de memória
do núcleo já derrubou o banco desta casa antes, e a recuperação custa mais que a espera.

**Como confirmar.** `free -g` com disponível acima de 2 GiB por 5 min seguidos.

## FilaComJobLongo

`runbook: filacomjoblongo` · severidade aviso · serviço fila · dispara quando o job mais antigo em
estado `rodando` passa de 30 min.

Métrica: `plat_jobs_rodando_mais_antigo_segundos`, de `plat.fila_job_mais_antigo_rodando_segundos()`.

**O que fazer.** Ver qual é: `SELECT id, tipo, iniciado_em, executor FROM plat.job WHERE estado =
'rodando' ORDER BY iniciado_em LIMIT 5`. Job pesado de verdade (ingestão grande, construção de
pirâmide) pode passar de 30 min e o alerta é só aviso. O caso ruim é o job órfão: o worker morreu e a
linha ficou em `rodando`. Confirmar com `plat_jobs_workers_vivos` — se estiver em zero, o problema é
o worker, não o job.

**Como confirmar.** A métrica volta abaixo de 1800 no scrape seguinte à conclusão ou ao cancelamento.

## TaxaDeErro5xxAlta

`runbook: taxadeerro5xxalta` · severidade critico · serviço api · dispara com mais de 1 % de 5xx na
janela de 5 min, por 5 min.

**O que fazer.** `journalctl -u plat-api -n 200` procurando a exceção repetida; cruzar com o
`X-Req-Id` que a resposta devolve ao cliente e que está na linha de log de acesso. Causas que já
aconteceram nesta casa, em ordem de frequência: conexão morta no pool depois de o Postgres reiniciar,
disco cheio no caminho de upload, e serviço a montante (Garage, Martin) fora do ar — neste último
caso o `ServicoDaPlataformaFora` chega junto e é ele que se resolve primeiro.

**Como confirmar.** A fração volta abaixo de 1 % e o alerta resolve; `plat_http_requests_total`
por `status` mostra os 5xx parando de crescer.

## TileP95Lento

`runbook: tilep95lento` · severidade aviso · serviço tiles · dispara com p95 acima de 500 ms por
10 min, medido no histograma nativo do Martin.

**O que fazer.** Separar cache frio de máquina ocupada. `uptime` primeiro: com carga alta, o p95 é
sintoma da casa, não do produto. Se a carga estiver normal, ver se o `endpoint` do rótulo é uma
camada nova (primeira renderização de uma camada grande é lenta por construção) ou uma já quente, que
seria degradação de verdade. Consulta lenta no PostGIS por trás da camada é a causa mais comum:
`pg_stat_activity` filtrando `application_name` do Martin.

**Como confirmar.** p95 abaixo de 500 ms por 10 min seguidos, com a mesma amostra de camadas.

## CertificadoPertoDeVencer

`runbook: certificadopertodevencer` · severidade aviso · serviço tls · dispara com menos de 14 dias
para o vencimento, por 5 min.

Métrica: `plat_certificado_dias_restantes`, lida do arquivo em `PLAT_CERTIFICADO_CAMINHO` com
`openssl x509 -enddate`.

**O que fazer.** Conferir se a renovação automática parou: `systemctl list-timers | grep -i certbot` e
o log da última tentativa. Renovação manual só depois de saber por que a automática não rodou —
renovar à mão e não consertar o relógio faz o alerta voltar em 60 dias.

**Como confirmar.** `openssl x509 -enddate -noout -in $PLAT_CERTIFICADO_CAMINHO` com data nova, e a
métrica acima de 14 no scrape seguinte. Um valor de 999999 significa que o arquivo não pôde ser lido
— isso é problema de configuração, não certificado longo.

## BackupAtrasado

`runbook: backupatrasado` · severidade critico · serviço backup · dispara sem nenhuma execução com
sucesso nas últimas 26 h, por 10 min.

Métrica: `plat_backup_horas_desde_ultimo{tipo="backup"}`, de `plat.backup_horas_desde_ultimo()`. São
26 h e não 24 h para a janela diária poder deslizar duas horas sem acordar ninguém.

**O que fazer.** Ver a última linha: `SELECT * FROM plat.backup_execucao WHERE tipo='backup' ORDER BY
executado_em DESC LIMIT 5`. Se houver linha com `ok = false`, a rotina rodou e falhou — o motivo está
no `detalhe`. Se não houver linha nenhuma, a rotina não rodou: conferir o agendador. Disco cheio no
destino é a causa mais comum, e nesse caso o `DiscoCritico` costuma ter chegado antes.

**Como confirmar.** Rodar o backup e ver a métrica cair para perto de zero no scrape seguinte.

## DrillDoMesNaoExecutado

`runbook: drilldomesnaoexecutado` · severidade aviso · serviço backup · dispara sem ensaio de
restauração bem-sucedido há mais de 744 h (31 dias), por 10 min.

Backup que nunca foi restaurado é promessa, não garantia. O valor 999999 (nunca houve ensaio) cai
aqui de propósito: "nunca aconteceu" dispara, não silencia.

**O que fazer.** Executar o ensaio de restauração e registrar o resultado com
`SELECT plat.backup_registrar('drill', true, '<o que foi restaurado e conferido>')`. Registrar
`false` quando o ensaio falhar é obrigatório — é o registro que mantém o alerta disparado até alguém
resolver.

**Como confirmar.** `plat_backup_horas_desde_ultimo{tipo="drill"}` abaixo de 744 no scrape seguinte.

## ReplicaAtrasadaOuParada

`runbook: replicaatrasadaouparada` · severidade critico · serviço replica · dispara com atraso acima
de 5 min por 2 min, só em alvo que É réplica (`pg_replication_is_replica == 1`).

**O que fazer.** `SELECT * FROM pg_stat_replication` no primário e `SELECT
pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()` na réplica. Atraso que só cresce com consulta
longa na réplica se resolve terminando a consulta; atraso com rede saturada ou disco lento na réplica
é outro problema. Enquanto durar, o WAL se acumula no primário — o `DiscoCritico` do primário é o
próximo alerta se ninguém agir.

**Como confirmar.** `pg_replication_lag_seconds` abaixo de 300 por 2 min seguidos.

## ReplicaSemMetrica

`runbook: replicasemmetrica` · severidade critico · serviço replica · dispara quando a série
`pg_replication_lag_seconds` some por 5 min.

Réplica parada não publica atraso alto: ela some. Por isso a ausência da série é o sinal — a regra de
limiar sozinha nunca acusaria este caso.

**O que fazer.** Conferir, nesta ordem: o exporter (`systemctl status prometheus-postgres-exporter`),
o alvo no Prometheus (`/targets`), e só então a réplica em si. Alerta que chega junto com
`AlvoPrometheusCaido` do mesmo alvo é problema do exporter, não do banco.

**Como confirmar.** A série volta a aparecer em `/api/v1/query?query=pg_replication_lag_seconds`.

## ServicoDaPlataformaFora

`runbook: servicodaplataformafora` · severidade critico · serviço processo · dispara com `up == 0`
por 2 min em qualquer alvo de job `plat-*` (API, worker, Martin, TiTiler, Garage).

**O que fazer.** `systemctl status <unidade>` e `journalctl -u <unidade> -n 100`. Se o processo
morreu por falta de memória, o `RamDisponivelBaixa` chegou antes e é ele que se resolve. Reiniciar
sem ler o log só troca o alerta de hoje pelo de amanhã.

**Como confirmar.** O alvo volta a `up == 1` em `/targets` do Prometheus e o alerta resolve em até
5 min (`resolve_timeout`).

## AlvoPrometheusCaido

`runbook: alvoprometheuscaido` · severidade aviso · serviço monitor · dispara com `up == 0` por
5 min em QUALQUER alvo, inclusive os que não são da plataforma.

É a rede larga: pega exporter da casa e alvo que ninguém lembra que existe. Quando o alvo é `plat-*`,
o `ServicoDaPlataformaFora` já disparou e inibe este, para o mesmo fato não virar duas mensagens.

**O que fazer.** Abrir `/targets` no Prometheus e ler o erro do alvo. Alvo que não existe mais deve
sair do `prometheus.yml` — alerta permanente que ninguém pode resolver é o começo do hábito de
ignorar alerta.

**Como confirmar.** O alvo some da lista ou volta a `up == 1`.

## AlertmanagerFora

`runbook: alertmanagerfora` · severidade critico · serviço monitor · dispara com `up == 0` no job
`alertmanager` OU com a série ausente, por 2 min.

Este é o alerta do alertador, e o único que não pode chegar por e-mail nem por webhook — quem os
enviaria está morto. Ele existe no Prometheus, é visto em `/alerts`, e é o que a refutação do item
exercita: matar o Alertmanager e cronometrar quanto o Prometheus leva para acusar.

O ramo `absent()` está lá de propósito: sem ele, um Alertmanager que NUNCA subiu (ou que saiu do
`prometheus.yml`) não geraria série nenhuma e ninguém saberia.

**O que fazer.** `systemctl status prometheus-alertmanager` e o log. Enquanto ele estiver fora, o
Prometheus continua avaliando as regras e guardando os alertas — nada se perde, só não sai; ao voltar,
o que ainda estiver disparando é entregue.

**Como confirmar.** `curl -s http://127.0.0.1:9093/-/ready` e o alvo `alertmanager` em `up == 1`.

## PrometheusNaoConsegueFalarComAlertmanager

`runbook: prometheusnaoconseguefalarcomalertmanager` · severidade critico · serviço monitor · dispara
com `prometheus_notifications_alertmanagers_discovered` abaixo de 1 por 2 min.

Caso irmão do anterior e diferente dele: aqui o Alertmanager pode estar de pé, mas o Prometheus não o
enxerga — erro no bloco `alerting:` da configuração, ou nome que não resolve.

**O que fazer.** Ler `/status` do Prometheus, seção de configuração, e conferir o endereço do
Alertmanager. Depois de corrigir, `curl -X POST .../-/reload`. ⚠ Se a configuração estiver montada
por *bind mount* em contêiner, `sed -i` troca o inode e o recarregamento não vê a mudança: editar com
`tee` ou reiniciar o contêiner.

**Como confirmar.** A métrica volta a 1 ou mais.

## Sentinela

`runbook: sentinela` · severidade aviso · serviço monitor · dispara SEMPRE, de propósito.

Alerta permanente que percorre o caminho inteiro (regra, Alertmanager, canal) e é entregue só ao
canal de teste, a cada 5 min. Ele não avisa nada por si: o que informa é a AUSÊNCIA dele. Silêncio
prolongado da Sentinela significa que o caminho de alerta quebrou em algum ponto, e nesse caso
nenhum outro alerta desta página está funcionando.

**O que fazer.** Se a Sentinela parou de chegar: conferir `/alerts` no Prometheus (a regra está
disparando?), depois `/-/ready` do Alertmanager, depois o destino em
`/etc/plat/segredos/PLAT_ALERTA_TESTE_URL`. Um erro de entrega aparece no log do Alertmanager como
`notify retry`.

**Como confirmar.** Chegada nova no canal de teste dentro de 5 min.
