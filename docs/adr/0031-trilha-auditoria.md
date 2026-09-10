# ADR 0031 — Trilha de auditoria de negócio (item L7-20-trilha-auditoria)

Contexto: a plataforma já tinha duas coisas parecidas com auditoria e nenhuma das duas era auditoria.
`plat.log_acesso` (migração 003, seção 12.8) responde "que requisição entrou": método, rota, status, bytes,
tempo. `plat.evento` (003, seção 12.7) responde "que ato de negócio aconteceu", com antes/depois — mas é
particionado por mês, o expurgo (`plat.evento_expurgar`) derruba a partição inteira, a retenção é a mesma
para todos os inquilinos, e a única proteção contra alteração é o `REVOKE` para `plat_app`. Além disso, as
rotas de escrita que por decisão não geram evento de domínio (upload de arquivo, cálculo de rota, início de
2FA) não deixavam rastro de negócio nenhum.

Este ADR fecha o item e, na seção final, fixa uma regra de casa sobre pg_cron que vale para todo mundo.

## D1. Tabela própria, append-only, NÃO particionada

`plat.auditoria` não é partição de `plat.evento` nem coluna nova nele. Duas razões:

1. **Retenção por inquilino exige expurgo por LINHA.** Partição mensal só sabe apagar o mês inteiro, de
   todos os inquilinos ao mesmo tempo. Se a retenção é configuração de cada inquilino — e é, porque o
   contrato de cada um é diferente — o expurgo tem de olhar a linha.
2. **Append-only exige trigger, e trigger de linha em tabela particionada é um andar a mais de coisa que
   pode dar errado** (partição criada em tempo de execução por `evento_particao_garantir`, trigger clonada
   pelo PostgreSQL, expurgo que hoje é `DROP TABLE` e não passaria por trigger nenhuma).

Índices: `(tenant_id, em DESC)`, `(tenant_id, ator_id, em DESC)`, `(tenant_id, acao, em DESC)` e um parcial
em `req_id`, que é o que a cobertura consulta a cada transação de escrita.

## D2. Imutabilidade em duas camadas, e a marca de expurgo sozinha não vale

`REVOKE INSERT, UPDATE, DELETE, TRUNCATE ... FROM plat_app` é a primeira camada. A segunda é a trigger
`auditoria_imutavel`, que levanta `auditoria_imutavel` em qualquer UPDATE ou DELETE, mais uma trigger de
statement que barra TRUNCATE.

A exceção do expurgo precisa de **duas** condições ao mesmo tempo: a marca de transação
`plat.auditoria_expurgo = '1'` **e** `current_user` ser o dono da tabela. Só a marca não serve, porque
`set_config` é livre: `plat_app` pode pô-la. Só o dono não serve, porque um DELETE distraído como `postgres`
passaria. A checagem do dono é lida de `pg_class`, não escrita como nome de papel — assim a regra vale igual
em produção, em homologação e em base de trilha, onde o papel muda de nome.

## D3. Duas escritas que se completam, as duas na MESMA transação do ato

**(a) Trigger sobre `plat.evento`.** `AFTER INSERT ... FOR EACH ROW` na tabela-mãe; o PostgreSQL 13+ clona a
trigger para toda partição, inclusive as criadas depois. Como `plat.evento_registrar` é chamada dentro da
transação da rota, a linha de auditoria nasce na mesma transação do ato: ou o ato e o rastro existem, ou
nenhum dos dois. Não foi preciso tocar em nenhuma das ~97 rotas que já registram evento.

**(b) Cobertura no fim da transação.** `app/db.py` chama `plat.auditoria_cobrir()` antes do `commit` de toda
transação de requisição de escrita. A função grava uma linha `origem='cobertura'` se, e só se, aquele
`req_id` ainda não deixou nenhuma. É isso que torna a cláusula "toda rota de escrita do OpenAPI gera linha"
verdadeira **mecanicamente**, e não por uma lista curada que alguém esquece de atualizar na próxima rota.

O contexto que o banco não tem como descobrir (req_id, IP, token de serviço, método, rota redigida) chega
por GUC de transação, gravada em `app/db.py` na mesma instrução que já gravava `plat.tenant_id`. O transporte
da rota até o cursor é um `ContextVar` (`app/auditoria.py`), porque quem prepara o cursor não recebe o
`Request`.

**Limite honesto:** requisição que erra antes de abrir transação de escrita (422 de validação, 404, 401) não
deixa linha na trilha de negócio, e não deve mesmo — não houve ato. Ela continua no `plat.log_acesso`, que é
onde tentativa se conta.

## D4. Retenção por inquilino, com piso

`tenant.config.auditoria_retencao_dias`, padrão 730 dias (dois anos), lido por
`plat.auditoria_retencao_dias(tenant)` — mesmo desenho de `plat.cota_usuarios` (migração 034): número em
`tenant.config`, função com `COALESCE` do padrão, nunca constante na rota. O log de acesso continua com 12
meses; a trilha de negócio responde por contrato, não por diagnóstico de requisição.

O **piso de 90 dias** não é conforto de interface: é a resposta ao "expurgo prematuro" da refutação do item.
Sem ele, o administrador do inquilino põe a retenção em 1 dia e a trilha some sozinha amanhã. Com ele, a
menor retenção possível ainda cobre um trimestre, e a própria mudança de retenção deixa linha com antes e
depois. Teto de 3.650 dias para que ninguém peça retenção infinita sem decidir onde o dado mora.

`plat.auditoria_expurgar()` é `SECURITY DEFINER` e **negada a `plat_app`** — ver D5.

## D5. `REVOKE ... FROM PUBLIC` não protege nada neste schema

Achado medido durante a construção deste item, e a razão de esta seção existir: a migração `001_fundacao`
tem

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT EXECUTE ON FUNCTIONS TO plat_app;
```

Toda função nova criada por `postgres` no schema `plat` **já nasce executável por `plat_app`**. O
`REVOKE EXECUTE ... FROM PUBLIC` que o repositório usa por hábito (migração 003, linha 834) não tira esse
grant, porque ele é para o papel, não para PUBLIC. Medido nesta trilha antes da correção:
`SELECT plat.auditoria_expurgar()` como `plat_app` **rodou**. Ou seja, a aplicação poderia apagar a trilha
que existe para vigiá-la — exatamente a refutação nomeada do item.

Regra que sai daqui: **função que não é para a aplicação precisa de `REVOKE EXECUTE ... FROM plat_app`
explícito.** Neste item: `auditoria_registrar` (aceita inquilino e ator como argumento — forjaria linha de
outro inquilino), `auditoria_expurgar`, `auditoria_cron_agendar`, `auditoria_cron_desagendar` e as três
funções de trigger. Provado em `tests/api/test_auditoria.py::test_funcoes_de_expurgo_e_de_cron_negadas_a_plat_app`.

## D6. Privilégio reaproveitado: `org.log_ver`

A tela e a API de consulta pedem `org.log_ver` ("ler log_acesso e evento do inquilino, exportar CSV"), que já
existe e já é administrativo; a configuração de retenção pede `org.configurar`. Não se criou privilégio novo
de propósito: privilégio novo obriga a mexer em `app/auth/privilegios.py`, na migração 003 e na matriz de
perfis, três arquivos que várias frentes tocam ao mesmo tempo. Se um dia a auditoria precisar ser vista por
quem não vê o log de acesso, aí sim se separa — e o custo de separar depois é uma linha de política.

## D7. Exportação sai da MESMA função que a contagem

`plat.auditoria_listar` e `plat.auditoria_contar` recebem os mesmos parâmetros e a mesma cláusula `WHERE`;
a tela, o CSV e o JSON chamam as duas. A contagem da exportação bate com a contagem da tabela por
construção, não porque dois SQL parecidos foram escritos com cuidado. O cabeçalho `X-Plat-Linhas` diz quantas
linhas saíram, para quem exporta conferir sem contar quebra de linha dentro de campo.

A exportação é ela mesma um ato auditado (`auditoria/exportar`), registrado **depois** de o conjunto ser
lido: se fosse antes, a linha da exportação entraria no que ela mesma exportou e a contagem nunca fecharia.

## D8. O que ficou de fora, e por quê

- **`pgaudit` para DDL.** A extensão está carregada na máquina, mas ligá-la é decisão de instância
  (`pgaudit.log` em `postgresql.conf`, reinício), não de migração de aplicação, e o banco é compartilhado com
  outros projetos da casa. Fica registrado como pendência de operação, não como código deste item.
- **Envio a SIEM (syslog/CEF).** A trilha já sai em CSV e JSON por período; o coletor que a leva a um SIEM
  depende de qual SIEM, e não há um escolhido. Sem destino não se escreve conector.
- **Acesso a camada `pessoal` (L7-12-a).** A classificação `pessoal` existe hoje só como valor de
  `web/.../modelos_classificacao/sigilo.json`; não há rota nem tabela que registre leitura de camada por
  classificação. `plat.auditoria_registrar` com `origem='aplicacao'` é o gancho pronto para quando L7-12-a
  existir.
- **Janela máxima de consulta: 92 dias** (`limites.LOG_JANELA_DIAS`, reaproveitada de `/api/log`). Retenção
  de 2 anos com consulta de 92 dias por vez é deliberado: protege o servidor de uma varredura de 730 dias
  numa tabela sem partição. Quem precisa do período inteiro exporta em fatias.

## Regra para quem usar pg_cron nesta plataforma

Isto não é sobre auditoria; é sobre o defeito que derrubou 38 itens num único dia. O padrão, nomeado por um
dos adversários: **o que é protegido por linha (RLS) aguenta; o que é recurso partilhado não tem dimensão de
inquilino nenhuma.** A fila, a chave do trinco consultivo, o nome do schema de dados, o contador de cota, o
orçamento de conexões — todos caíram pelo mesmo motivo. **O nome de um job do pg_cron é dessa família:**
`cron.job` é uma tabela única, global da instância do PostgreSQL, e um job com nome constante é o mesmo
defeito com outra roupa. Um schema de teste agendando `auditoria_expurgo` sem qualificar apaga a auditoria de
produção, e ninguém percebe até faltar linha.

Quem for usar pg_cron aqui, faça as quatro:

1. **Derive o nome do job de `current_schema()`, nunca de uma constante.** Neste item,
   `plat.auditoria_cron_nome()` devolve `current_schema() || '_auditoria_expurgo'`; o comando agendado também
   é qualificado com `format('SELECT %I.…', current_schema())`. Cuidado: dentro de um bloco `DO` o
   `search_path` é o do cliente (normalmente `public`) — chame uma FUNÇÃO com `SET search_path`, não
   `current_schema()` solto.
2. **Agende de forma idempotente.** Consulte `cron.job` pelo nome e faça `cron.unschedule` antes de
   `cron.schedule`. Reaplicar a migração não pode deixar dois jobs.
3. **Desagende o job da SUA trilha ao terminar o turno.** `plat.auditoria_cron_desagendar()`, ou
   `sudo -u postgres python3 scripts/auditoria_manutencao.py desagendar --schema plat_t<trilha>`. Job de
   trilha esquecido é máquina rodando expurgo para sempre num schema que ninguém mais olha.
4. **Trate o nome do job como recurso partilhado**, sujeito à mesma exigência de dimensão de dono que a fila
   e o trinco consultivo. Se você não consegue dizer de quem é aquele nome só de olhar, o nome está errado.

Provado, não só afirmado, em
`tests/api/test_auditoria.py::test_cron_nome_sai_do_schema_e_agendar_e_idempotente`: o nome tem de ser
`<schema>_auditoria_expurgo`, agendar duas vezes deixa **um** job, e todo job de `cron.job` cujo nome termina
em `_auditoria_expurgo` tem de apontar para a função do schema que está no próprio nome.
