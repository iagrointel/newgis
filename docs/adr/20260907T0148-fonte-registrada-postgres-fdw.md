# ADR — Fonte de dado registrada: conector `postgres_fdw` (item L0-04-i-fonte-registrada)

## Contexto

O modelo genérico de conexão externa (`plat.conexao`, item L6-02-a-modelo-conexao-e-seguranca) já existe:
credencial cifrada AES-GCM, defesa de SSRF para HTTP, teste de saúde, histórico de saúde (L6-02-l). O que
faltava era o próprio conector: "fonte de dado registrada" — o "data store item" da Esri Enterprise 11.4
("Data store items", ver `docs/PARIDADE.md`) ou o "store" do GeoServer — restrito nesta passagem ao
PostgreSQL/PostGIS externo do cliente. Escopo do item: registrar, listar tabelas, "publicar em massa" (uma
camada referenciada por tabela, sem copiar dado — o "bulk publish" da Esri). Pasta de rede e bucket S3
externo ficam para L6-02.

## Decisões

**1. TCP direto, não HTTP — a defesa de SSRF muda.** `app/conexao/seguranca.py` foi escrita para HTTP e
bloqueia toda faixa de IP privado (um alvo HTTP arbitrário não deveria estar numa rede interna). Um Postgres
de cliente real costuma estar numa rede privada/VPN — bloquear isso quebraria o produto. `pgfdw.validar_alvo`
bloqueia MENOS categoria de IP (só metadado de nuvem/multicast/não-especificado, reaproveitando
`seguranca.resolver_ips_bloqueando_categorias`, nova função pequena e genérica extraída do módulo HTTP) e MAIS
por LISTA EXPLÍCITA: o nome do banco `iagro_sat` é recusado em qualquer host, e o (host, porta, banco) do
`PLAT_DSN` desta própria instalação é recusado por IP. As duas defesas cobrem o mesmo alvo por caminhos
diferentes (nome e IP) de propósito — é exatamente o teste do adversário do item.

**2. `plat_app` não pode criar SERVER/USER MAPPING/FOREIGN TABLE.** `ADR 0001` já nega `CREATE` no banco a
`plat_app`; a extensão `postgres_fdw` também exige privilégio próprio. Solução: uma função `SECURITY DEFINER`
(`plat.conexao_fdw_publicar`, dona `postgres`) faz TODA a DDL — `CREATE SERVER`/`CREATE USER MAPPING`/
`CREATE FOREIGN TABLE`/`CREATE VIEW` — e devolve só o nome do schema/view criados. A credencial (senha do
Postgres do cliente) passa como parâmetro da função SQL, nunca concatenada por Python.

**Risco aceito e documentado**: `CREATE USER MAPPING ... OPTIONS (password %L)` e `ALTER USER MAPPING ...`
colocam a senha em texto claro DENTRO do `EXECUTE format(...)` que o Postgres roda — se o servidor tiver
`log_statement` acima de `none`/`ddl` sem redação, ou `pg_stat_statements` com `track_utility` ligado, a
senha pode aparecer em log/estatística. Esta é uma limitação conhecida e **inerente ao próprio `postgres_fdw`**
(nenhum wrapper evita isto — nem o Esri Enterprise nem o GeoServer, que guardam a senha do "data store" em
configuração no servidor, não numa chamada parametrizada). Mitigação real: a credencial cifrada nunca sai do
banco `plat.conexao.credencial_cifrada` em texto claro (isso o item garante e o teste prova); o texto claro
existe só durante os milissegundos da chamada da função. Não fechado 100%; registrado aqui em vez de
prometido como resolvido.

**3. `session_user`, nunca `plat_app` hardcoded.** A primeira versão da função gravava `CREATE USER MAPPING
FOR plat_app SERVER ...` — quebrou nas bases de trilha, onde o papel de aplicação chama
`plat_t<trilha>_app`, não `plat_app` (achado rodando o e2e contra a base da própria trilha: `SECURITY
DEFINER` troca `current_user` para o DONO da função, mas `session_user` continua sendo quem chamou). Trocado
para `session_user` em toda parte que precisa do papel que vai USAR a tabela (`CREATE/ALTER USER MAPPING`,
`GRANT USAGE ON FOREIGN SERVER`, `GRANT SELECT ON VIEW`) — funciona igual em produção (`plat_app`) e em
qualquer base de trilha, sem precisar saber o nome do papel de antemão.

**4. `tenant_id`/RLS "via view", porque uma `FOREIGN TABLE` não aceita política de RLS sobre uma coluna que a
tabela remota nunca tem.** A `VIEW` que embrulha a `FOREIGN TABLE` injeta `tenant_id` como CONSTANTE (o
inquilino que publicou) e filtra `WHERE plat.tenant_atual() = <essa constante>` — o mesmo predicado que uma
política de RLS teria, expresso em SQL de view porque o objeto de baixo é estrangeiro. `GRANT SELECT` só para
o papel de aplicação (nunca `PUBLIC`); a view nunca aceita `INSERT`/`UPDATE`/`DELETE` (nenhum `INSTEAD OF`
trigger foi escrito) — é aqui que "só leitura por padrão" e "recusa escrita mesmo com credencial superusuária"
viram estruturais, não uma checagem de "é superuser? então recusa".

**5. `url` do item de catálogo fica `NULL` para camadas `postgres_fdw`.** `plat.item.url` tem
`CHECK (url IS NULL OR url ~ '^https?://')` (achado rodando o teste: a rota `publicar_camada` genérica de
L6-02-a sempre grava `r["url"]`, que para HTTP É http(s); para `postgres_fdw` a URL é `postgres://host:porta/
banco` e violaria o `CHECK`). A origem real fica em `dados.procedencia` (mesmo lugar que as outras
`camada_vetorial` referenciadas já usam), não em `item.url`.

**6. `srid` sempre presente mesmo sem geometria.** O schema de `camada_vetorial` (migração 029) exige
`srid` (`minimum: 1`) mesmo quando `geometria = "nenhuma"` — tabela publicada sem geometria grava `srid: 4326`
por convenção neutra (o campo não tem sentido geográfico ali; documentado, não escondido). Mudar o schema
para tornar `srid` opcional quando `geometria = "nenhuma"` é trabalho de outra trilha (o schema é
compartilhado com `L0-04-c/d/e`), registrado como pendência no handoff.

## Paridade com Esri Enterprise 11.4 / GeoServer

| Esri "Data store item" (11.4) | GeoServer "Store" | Este item |
|---|---|---|
| registrar conexão de banco (`sde:postgresql:...`) | criar "Store" (PostGIS datastore) | `POST /api/conexoes` tipo `postgres_fdw` |
| listar tabelas do banco registrado | "Publish Layers" a partir do Store | `GET /api/conexoes/{id}/tabelas` |
| "bulk publish" de múltiplas camadas | publicar várias layers do mesmo Store | `POST /api/conexoes/{id}/publicar-em-massa` |
| item de conteúdo por camada, sem copiar dado (referenced) | layer referenciando a tabela do Store | `plat.item` tipo `camada_vetorial`, `dados.fonte = "referenciada"` |
| status do "Data store" (conectado/erro) | status do Store | `saude`/`estado_saude` de `plat.conexao` + `estado_fonte` por camada |

## Consequências

- Item futuro (L6-02-b em diante) que precise de outro banco (MySQL, SQL Server) reaproveita `plat.conexao`
  e a mesma forma de defesa (lista explícita de auto-referência + categorias de IP mínimas), mas precisa do
  próprio FDW e da própria função `SECURITY DEFINER` — o padrão desta ADR generaliza, o código não.
- O par (SERVER, USER MAPPING) é 1 por CONEXÃO, reaproveitado entre tabelas publicadas dela — apagar a última
  camada de uma conexão não apaga o SERVER (fica para o dia em que a própria conexão for apagada; hoje
  `DELETE /api/conexoes/{id}` não limpa objetos FDW — pendência registrada no handoff).
