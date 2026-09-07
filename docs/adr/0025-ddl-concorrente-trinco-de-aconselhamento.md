# ADR 0025 — DDL concorrente em função SECURITY DEFINER: trinco de aconselhamento por transação

Estado: aceito · 07/09/2026 · substitui nada · afeta `db/migracoes/20260907T0240_ddl_concorrente_trinco.sql`

## 1. O que aconteceu

Em produção-de-teste, sob carga, um item de planilha por URL passava quando rodava sozinho e nunca
passava junto com outro: seis tentativas, nenhuma com as duas cláusulas juntas. A causa não era o item.
Era a publicação de camada. Dois carregamentos simultâneos do mesmo inquilino chamam
`plat.camada_schema_garantir(slug)` (`app/ingestao/carregar.py`, passo 0), que faz

```sql
CREATE SCHEMA IF NOT EXISTS d_<slug> AUTHORIZATION plat_app;
GRANT USAGE ON SCHEMA d_<slug> TO plat_leitor;
```

sem nenhuma serialização. Medido em 07/09 com seis sessões alinhadas por barreira no mesmo schema:
três das seis terminaram com `ERROR: tuple concurrently updated`. Com a bancada de teste deste ADR,
antes do conserto: **2 falhas em 12 chamadas com 2 conexões, 10 em 24 com 4 conexões, 15 em 36 com 6**.
Quando isso acontece o job de ingestão morre no primeiro passo e a importação inteira falha.

Isto não é problema de ambiente de teste. É o caminho que um cliente com dois usuários publicando ao
mesmo tempo percorre todo dia.

## 2. Por que `IF NOT EXISTS` não resolve

As duas linhas falham por motivos diferentes, e só uma delas tem `IF NOT EXISTS`.

1. `CREATE SCHEMA IF NOT EXISTS` **não é atômico** contra outra transação criando o mesmo schema. O
   teste de existência lê o catálogo com a visão da própria transação; a linha da concorrente ainda
   não está confirmada. As duas passam pelo teste, as duas tentam inserir, e a segunda a confirmar
   leva `duplicate_schema` (ou violação do índice único de `pg_namespace`).
2. O `GRANT` **não tem `IF NOT EXISTS` nenhum**. Ele atualiza a coluna `nspacl` da mesma linha de
   `pg_namespace`. Duas atualizações concorrentes da mesma linha de catálogo não passam pelo
   EvalPlanQual que salva uma tabela comum: o executor de catálogo aborta com
   `tuple concurrently updated` (SQLSTATE XX000). Isso acontece **mesmo quando o schema já existe** —
   isto é, no caso mais comum de todos, o inquilino antigo publicando a décima camada.

Repetir a transação inteira (retry) foi descartado: esconde o defeito em vez de consertá-lo, custa
latência, e ainda deixaria o `duplicate_schema` do item 1 de pé. `tuple concurrently updated` não é um
erro serializável e não vem com a garantia de que a segunda tentativa terá sorte.

## 3. A decisão

Tomar `pg_advisory_xact_lock(hashtext(<chave>))` **antes** do DDL, dentro da própria função, com a
chave derivada do objeto que o DDL toca.

```sql
PERFORM pg_advisory_xact_lock(hashtext('camada_schema_garantir:' || p_slug));
```

Três propriedades importam:

- **De aconselhamento**: não bloqueia nenhuma tabela nem nenhuma leitura. Só quem chama a mesma função
  com a mesma chave espera.
- **De transação** (`_xact_`): some sozinho no COMMIT ou no ROLLBACK. Não existe trinco preso por
  sessão que morreu — que é o risco do `pg_advisory_lock` de sessão.
- **Por chave**: inquilinos diferentes não esperam um pelo outro. Está provado, não suposto, em
  `tests/api/test_camada_schema_corrida.py::test_inquilinos_diferentes_nao_esperam`: com uma transação
  segurando o trinco de `demo`, uma chamada para `demo2` completa dentro de 5 s e a chamada para `demo`
  estoura o `statement_timeout` de 1 s. Colisão de `hashtext` entre chaves diferentes causaria espera
  desnecessária, nunca erro.

O espaço de trinco do PostgreSQL é por banco de dados. É o escopo certo aqui: os schemas `d_<slug>`
também são globais ao banco (não levam prefixo de instalação), logo produção, homologação e as bases
por trilha disputam o mesmo objeto e têm de disputar o mesmo trinco.

## 4. A classe, não o caso

A mesma forma existe em toda função `SECURITY DEFINER` que emite DDL em tempo de execução. As sete
consertadas na migração:

| função | DDL que corre | chave |
|---|---|---|
| `plat.camada_schema_garantir` | `CREATE SCHEMA` + `GRANT` no schema | `camada_schema_garantir:<slug>` |
| `plat.camada_preparar` | DDL da tabela da camada + `GRANT SELECT` | `camada_preparar:<schema>.<tabela>` |
| `plat.tenant_criar` | cria o MESMO `d_<slug>` | `camada_schema_garantir:<slug>` (chave partilhada de propósito) |
| `plat.evento_particao_garantir` | `CREATE TABLE PARTITION OF` + `REVOKE` + `ALTER` + `CREATE POLICY` | `particao:plat.<partição>` |
| `plat.log_particao_garantir` | idem | `particao:plat.<partição>` |
| `plat.evento_expurgar` | `DROP TABLE` de partição | `particao:plat.<partição>` |
| `plat.log_expurgar` | idem | `particao:plat.<partição>` |

As duas funções de partição ganharam também a **reconferência depois do trinco**: quem esperou já
encontra a partição criada pela outra sessão e não tenta criar de novo. Sem isso o trinco só trocaria
o erro de lugar. O gatilho dessa corrida é a virada do mês: a primeira escrita de cada mês, com duas
requisições ao mesmo tempo, é exatamente o cenário.

Fica **fora** de propósito `plat.tenant_apagar_interno`, que só emite `ALTER TABLE`. `ALTER TABLE`
pega bloqueio pesado na própria tabela antes de mexer no catálogo, logo duas sessões serializam em vez
de colidir. A exceção está escrita no teste, com essa razão, em `SEM_TRINCO_JUSTIFICADO`.

## 5. O que impede a regressão

`tests/api/test_camada_schema_corrida.py::test_toda_funcao_com_ddl_tem_trinco` lê o corpo **vivo** das
funções (`pg_proc.prosrc`, não o arquivo) e reprova qualquer função `SECURITY DEFINER` de `plat` que
monte `CREATE SCHEMA`, `GRANT`, `CREATE TABLE` ou `DROP TABLE` sem `pg_advisory_xact_lock`. Antes da
migração ele acusa as sete pelo nome; depois, nenhuma.

Essa guarda existe por um motivo concreto: a migração **redefine funções inteiras**. Qualquer ramo que
redefina uma delas com carimbo de tempo posterior derruba o trinco em silêncio. O teste transforma esse
silêncio em reprovação.

## 6. Custo

Uma chamada a `pg_advisory_xact_lock` por publicação de camada, sem disputa, é uma operação em memória
compartilhada. Com disputa, o segundo carregamento espera o primeiro terminar o DDL — dezenas de
milissegundos — em vez de morrer. A suíte de corrida com 4 conexões × 6 rodadas passou de 10 falhas em
24 chamadas para 0 em 24, e a rodada inteira do arquivo leva poucos segundos.
