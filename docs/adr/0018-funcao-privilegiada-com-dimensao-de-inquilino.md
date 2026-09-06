# ADR 0018 — Função privilegiada precisa de dimensão de inquilino

Estado: aceito (turno T3, setembro de 2026). Complementa o ADR 0001 seção 3.3 (SECURITY DEFINER como
única porta para o que a RLS proíbe) e o ADR 0002 seção 16.2 (isolamento por linha).

## 1. Contexto: o mesmo defeito em dois grupos de ataque diferentes

Em 06/09/2026 dois adversários independentes, trabalhando em grupos de itens diferentes e sem se
falarem, acharam o mesmo defeito:

- laudo G2 (`laco/handoffs/T3/ataque-g2-ADVERSARIO.md`, achados G2-1/G2-2): no contexto do inquilino A,
  `plat.item_versoes_compactar` apagou 2 linhas de `plat.item_versao` de um item do inquilino B; e
  `POST /api/jobs` aceitou o pedido com identificador de item de outro inquilino (201).
- laudo G4 (`laco/handoffs/T3/ataque-g4-ADVERSARIO.md`, achado G4-10): `plat.evento_expurgar(-1)`
  derrubou a partição do mês corrente e zerou a auditoria de todos os inquilinos; `plat.log_expurgar`
  tem o mesmo defeito.

Um terceiro adversário (laudo G1) achou a causa da outra metade do problema: a migração 047 criou seis
funções de convite e de redefinição de senha e não revogou de PUBLIC. Como `iagro_sat` é um banco
COMPARTILHADO com outros projetos da casa, PUBLIC ali não quer dizer "usuário anônimo da web" — quer
dizer "todo papel do banco".

Dois achados iguais em grupos diferentes é classe, não caso. A varredura das 102 funções SECURITY
DEFINER do schema (`laco/handoffs/T3/VARREDURA-funcoes-privilegiadas.md`) confirmou: **18 furavam o
isolamento e 11 eram destrutivas sem validar o argumento**.

O que as 29 têm em comum:

1. são SECURITY DEFINER, logo rodam como o dono (postgres) e **a RLS não se aplica a elas**;
2. recebem o alvo por argumento (`p_tenant_id`, `p_item`, `p_meses`) vindo, no fim da corda, de uma
   requisição HTTP;
3. o isolamento do produto é por LINHA (RLS) e **permissão de função é recurso PARTILHADO**: não tem
   linha, logo não tem inquilino. Foi exatamente aí que o produto ficou sem defesa.

## 2. Decisão

**Toda função SECURITY DEFINER do schema `plat` tem de ter dimensão de inquilino explícita no corpo,
e todo argumento numérico tem de ter piso.** Três guardas reusáveis, criadas pela migração
`20260906T1601_funcoes_privilegiadas_isolamento.sql`:

| guarda | quando usar | comportamento |
|---|---|---|
| `plat.inquilino_do_argumento(p_tenant int) -> int` | a função recebe `tenant_id` por argumento | devolve o argumento se não há inquilino no contexto (rota anônima, worker), se ele é igual ao do contexto, ou se o contexto é o inquilino técnico `plataforma`; senão levanta `contexto_de_outro_inquilino` |
| `plat.inquilino_do_slug(p_slug text) -> void` | a função recebe o inquilino por slug | a mesma regra, resolvendo o slug |
| `plat.so_manutencao(p_o_que text) -> void` | expurgo GLOBAL, que por natureza cruza inquilinos | passa sem contexto ou sob `plataforma`; levanta `insufficient_privilege` para qualquer outro |
| `plat.argumento_no_minimo(p_valor int, p_min int, p_nome text) -> int` | todo número de meses/dias/segundos/itens a manter | levanta `argumento_invalido` para nulo ou abaixo do piso |

O padrão de uso é uma linha, na própria cláusula que escolhe a linha:

```sql
UPDATE plat.arquivo_bucket SET cota_bytes = p_cota_bytes
 WHERE tenant_id = plat.inquilino_do_argumento(p_tenant_id);
```

Escrever a guarda no `WHERE` (e não num `IF` antes) é de propósito: quem editar a consulta depois não
consegue apagar a guarda sem apagar também o filtro.

**Toda migração que cria função em `plat` revoga essa função de PUBLIC no MESMO arquivo.** A prática
anterior — criar num arquivo e revogar noutro, dias depois — funcionou seis vezes e falhou duas
(migração 030, esquecida por três dias; migração 046, esquecida), e essas duas ficaram em produção.

## 3. Consequências

- Chamada legítima não muda: todas as rotas passam o inquilino da sessão, e o worker roda sem contexto.
- O periódico que cruza inquilinos (`uploads.expirar`, `jobs.sessoes_expurgar`, `jobs.expurgo`) passa a
  exigir o inquilino técnico. Um administrador de inquilino comum que enfileire esses trabalhos pela
  API recebe `insufficient_privilege` em vez de disparar um expurgo sobre a base inteira.
- A trava permanente é `tests/api/test_funcoes_privilegiadas.py`: varre `pg_proc` (função nova sem
  comparação de inquilino, função com EXECUTE para PUBLIC fora de lista justificada) e varre
  `db/migracoes/` (função criada sem `REVOKE ... FROM PUBLIC` no mesmo arquivo). A dívida das migrações
  `NNN_`, que são imutáveis (ADR 0014), está congelada numa lista onde cada entrada nomeia o arquivo
  que a pagou.
- Onde a exceção for legítima, ela é escrita: `PUBLICO_JUSTIFICADO` e `SEM_COMPARACAO_JUSTIFICADO` no
  arquivo de teste exigem uma frase de motivo por nome. Hoje `PUBLICO_JUSTIFICADO` está VAZIO — nenhuma
  função do schema precisa de PUBLIC.

## 4. O que esta decisão NÃO resolve

- Não substitui a RLS: a guarda é a segunda camada, para o caminho que passa por fora dela.
- Não conserta a rota que enfileira trabalho com identificador de outro inquilino (achado G2 do lado da
  API, `POST /api/jobs`): a função agora não estraga nada, mas a rota continua aceitando o pedido e o
  trabalho termina sem efeito. Fechar isso é do item de fila, não deste.
- Não cobre o schema `plat` de PRODUÇÃO, que em 06/09/2026 tinha cinco funções `amc_*`, uma
  `arquivo_bucket_cotas_atualizar` e duas colunas a mais em `arquivo_bucket` vindas de ramos ainda NÃO
  juntados. Quem juntar aqueles ramos aplica a mesma guarda; a varredura registra o desvio.
