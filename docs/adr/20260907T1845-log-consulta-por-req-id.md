# Log consultável por pedido: um identificador, cinco escritores, um leitor

Item `L7-06-c-logs-consulta-req-id`. Setembro de 2026.

## Situação

Cada serviço da plataforma escreve o seu log e nenhum deles sabe do outro. Quando um pedido falha, o
operador tem a linha do nginx, a linha da aplicação, a linha do worker e a linha do Postgres em quatro
lugares, e junta as quatro pelo horário — que é o pior critério possível numa máquina com carga.

## Decisão

1. **O identificador nasce no nginx.** `$request_id` entra na linha de acesso (`log_format plat_json`,
   escrito pelo `install.sh` em `/etc/nginx/conf.d/plat_limites.conf`) e vai ao upstream em
   `X-Req-Id`. `proxy_set_header` **sobrescreve** o cabeçalho que o cliente mandou, então um
   identificador forjado de fora nunca chega à aplicação.
2. **A aplicação adota o identificador entrante** em vez de cunhar outro (`app/auth/middleware.py`),
   quando ele é hexadecimal de 8 a 40 caracteres. Sem isso a linha do nginx e a da API nunca casariam.
   Como o processo só escuta em 127.0.0.1, o cabeçalho já chega confiável; a conferência de formato
   existe para nunca deixar caractere de controle entrar numa linha de log JSON.
3. **O Postgres entra pelo `application_name`.** `app/db.py` faz `SET application_name = 'plat:<12 hex>'`
   a cada retirada de conexão do pool, e o `log_line_prefix` desta instalação já traz `app=%a`. Doze
   caracteres bastam para correlacionar e cabem em `pg_stat_activity` sem poluir.
4. **O worker entra pela proveniência do job.** `app/jobs/servico.py` grava `proveniencia.req_id` na
   criação (coluna que já existia e já é mesclada, não uma coluna nova) e o worker escreve esse campo
   nas linhas `job iniciado` e `job terminou`. É o que liga trabalho pesado ao pedido que o pediu.
5. **Martin e TiTiler não registram identificador de pedido próprio.** A ligação com eles é a linha do
   nginx que os proxia, com o mesmo `$request_id` e o `upstream_addr` deles. Isto está escrito no
   cabeçalho de `app/logs_consulta.py` para ninguém prometer o que não existe.
6. **A leitura é uma só:** `plat logs --req-id <id>` (`scripts/plat`) lê as fontes, filtra por
   substring do identificador (e do prefixo de 12 do `application_name`) e ordena por relógio. Linha
   sem o identificador não entra: não há junção por horário nem adivinhação.

## Nível de log em tempo de execução

O equivalente do `logLevel` do ArcGIS Server (OFF..DEBUG) é um arquivo JSON em `var/log_nivel.json`,
relido por cada processo quando o `mtime` muda. A raiz do `logging` fica em DEBUG e quem decide o corte
é um filtro no handler: se o corte fosse o `Logger.level`, um registro DEBUG seria descartado ANTES do
filtro e a torneira não reabriria sem reiniciar o processo. O override casa por nome de logger, por
prefixo de rota (`rota:/api/tiles`) ou `*`, o mais específico vence, e tem prazo (`--por 10min`).
Arquivo em vez de memória porque a API roda em vários processos que não compartilham memória.

## Retenção

`MaxRetentionSec=90d` em `/etc/systemd/journald.conf.d/plat.conf` (`deploy/journald-plat.conf`).
Duas limitações medidas e assumidas:

- o journald **não** tem teto por unidade; `SystemMaxUse` vale para o journal inteiro da máquina. Teto
  por serviço exigiria `LogNamespace=plat` nas unidades `plat-*` (com `journalctl --namespace=plat` na
  leitura e reinício das unidades), e **não** foi feito;
- `MaxRetentionSec` apaga o que passa do prazo, não garante que o prazo caiba. Medido em 07/09/2026:
  2,34 GB de journal guardando 2,9 dias — ~780 MB/dia da máquina inteira. As unidades da plataforma são
  0,83 MB/dia somadas (~75 MB em 90 dias): o horizonte de 90 dias do log da plataforma é barato, quem
  não cabe é o resto do servidor.

## Consequências

- Uma exceção não tratada devolve 500 pelo tratador do próprio servidor, **antes** de o middleware pôr
  o `X-Req-Id` na resposta. O cliente fica sem o identificador; quem o guarda é a linha do nginx. Não
  se esconde isso mudando a asserção do teste: está na medida e no manual.
- A escrita de `plat.log_acesso` acontece depois de o corpo sair, fora do contexto do pedido, então a
  conexão dessa escrita não leva o identificador no `application_name`. A linha guarda o `req_id` na
  coluna nova, que é o que importa.
- Redação: a mensagem de qualquer linha JSON passa pelo redator. Sem isso, uma biblioteca que registre
  a URL chamada (o `httpx` registra `HTTP Request: GET <url>`) deixava `?token=` inteiro no journal —
  medido na própria suíte antes do conserto.
