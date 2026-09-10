# Bancos externos: PostgreSQL/PostGIS referenciado e consulta SQL do cliente (item L6-02-j-bancos-externos)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L3L6_CONCEITO.md` (decisão B8: "SELECT com lista
branca, LIMIT obrigatório, sem DDL/DML"); ADR `20260907T0148` (conector `postgres_fdw`, item L0-04-i).

## Contexto

O conector `postgres_fdw` (L0-04-i) já referencia tabelas de um PostgreSQL externo como camadas (view sobre
FOREIGN TABLE, sem cópia). Faltava o que o Esri chama de "query layer" e o GeoServer de "SQL view": o cliente
escreve um SELECT sobre o banco DELE e recebe o resultado pela plataforma. Texto SQL vindo do cliente sobre um
banco que também é do cliente muda o risco de lugar: não é o nosso banco que está em jogo, é a conexão
registrada virar um canal para o resto do banco dele (outros schemas, catálogo, funções de arquivo/rede) ou
para escrita.

## Decisão

1. **Validador em quatro camadas** (`app/conexao/consulta_sql.py`), todas antes de qualquer conexão:
   forma (um só comando, começa por SELECT/WITH, sem `;`, comentário, `$$`), palavras de escrita e funções de
   sistema proibidas em qualquer posição (dentro de CTE, subconsulta, string já apagada), **lista branca** das
   tabelas que a própria conexão enxerga (`pgfdw.listar_tabelas` no schema da conexão; nome com schema só se for
   esse schema), e **LIMIT explícito no fim**, entre 1 e `CONEXAO_PG_CONSULTA_LINHAS_MAX` (5.000). Consulta sem
   LIMIT é recusada com `limit_obrigatorio` sem ler uma linha.
2. **Execução só-leitura** pela mesma `pgfdw.conectar` (readonly, `statement_timeout` de 8 s, timeout de
   conexão de 5 s), `fetchmany(limite)`, tempo medido e devolvido (`tempo_ms`). Erro do banco do cliente vira
   422 `consulta_invalida` com a primeira linha da mensagem; tempo esgotado vira 422 `tempo_esgotado`; banco fora
   do ar vira 503 e marca a saúde da conexão.
3. **Rota** `POST /api/conexoes/{id}/consulta` (permissão de editar a conexão; RLS do inquilino), evento
   `conexoes/consultar` com tabelas, nº de linhas e tempo — nunca o texto da consulta nem o dado devolvido.
4. **Lista de palavras, não gramática**: não se escreve um parser de SQL. O custo é recusar consultas
   legítimas que usem uma palavra da lista como identificador (uma coluna chamada `update`, por exemplo), e
   aspas não escapam da lista, de propósito. A alternativa (parser completo) teria mais superfície de ataque
   do que a rota que protege.
5. **SQL Server (GDAL MSSQLSpatial, copiado) e Oracle ficam PENDENTES**: sem container liberado pelo dono não
   há como testar, e o item manda registrar em vez de fingir (`marcar_item.py` e handoff dizem isso).

## Consequências

- A "tabela de 100 mi de linhas" da refutação nunca é tocada sem LIMIT; com LIMIT, o custo de uma agregação
  que varre a tabela (`count(*)`) é limitado pelo `statement_timeout`, não pelo validador — medido e declarado
  em `tests/medidas/L6-02-j-bancos-externos.json` sobre 2 mi de linhas.
- `;` é recusado até dentro de string: "um comando só" é regra de forma, auditável a olho.
- Defesa em profundidade testada: uma `ConsultaValidada` forjada com DELETE é recusada pelo próprio banco
  (`read-only`), porque a conexão nunca é de escrita.
- Sem tela: a rota é consumida pela API (tela de consulta é item de L6 posterior, com o editor de camadas).
