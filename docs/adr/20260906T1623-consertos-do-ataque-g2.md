# ADR 20260906T1623 — consertos do ataque G2 ao catálogo de conteúdo (L0-03)

Estado: aceito. Data: 06/09/2026. Trilha: `wt/g2fix`.
Contexto: o laudo `laco/handoffs/T3/ataque-g2-ADVERSARIO.md` refutou 6 dos 12 itens do grupo G2 com nove achados
medidos, todos deixados como `xfail(strict=True)` em `tests/api/catalogo/test_adversario_g2.py` e
`tests/e2e/test_adversario_g2_conteudo.py`. Este ADR registra as três decisões que não são conserto óbvio: o teto
de linhas da compactação de versões, a cláusula impossível do portão do L0-03-f e o desenho da notificação interna.
Os outros consertos (lixeira, transferência, cache da miniatura, estrela de favorito) estão descritos no código e
nos testes, e não mudam decisão de arquitetura nenhuma.

## 1. Teto de 50 linhas na compactação de versões (achado G2-3)

**Medido.** `plat.item_versoes_compactar(item, manter)` guarda as `manter` versões mais recentes e resume cada
bloco de 10 das antigas numa linha só. Uma passada sobre N versões deixa, portanto,
`manter + teto((N - manter) / 10)` linhas: 66 com 200 gravações, 146 com 1.000 (medição do adversário, repetida
nesta trilha). O periódico rodava **uma passada por dia**, então um item ficava dias acima do teto que a refutação
do L0-03-l fixa em 50 linhas.

**Decisão.** O número do portão fica em 50 — não foi renegociado. Muda o CHAMADOR, em `app/catalogo/tarefas.py`:

1. `compactar_item(cur, item, teto)` repete a passada até estabilizar. O excedente cai por um fator de 10 a cada
   passada (951 → 96 → 10 → 1 no caso de 1.000 gravações), então a convergência custa no máximo 12 passadas para
   qualquer número de versões que caiba num inteiro.
2. O ponto fixo da função é `manter + 1` linha: as `manter` recentes mais UMA linha compactada que resume tudo o
   que veio antes. Por isso o chamador pede `manter = teto - 1`. Com o teto de 50, o item termina com no máximo
   50 linhas — 49 versões íntegras e 1 linha `compactada` com `compactou` = quantas ela resume.
3. O periódico passou de diário (`40 3 * * *`) para de hora em hora (`40 * * * *`). A janela em que um item pode
   estar acima do teto deixa de ser de um dia.

**O que NÃO foi feito e por quê.** `plat.item_versoes_compactar` não foi tocada. Ela é uma das funções
SECURITY DEFINER que a varredura das 102 funções definidoras está auditando nesta mesma sessão (achados G2-1 e
G2-2: a função não compara `plat.tenant_atual()` e apaga versão de item de outro inquilino). Mexer nela por dois
motivos ao mesmo tempo, em duas trilhas, é como se perde conserto. Os testes `test_g2_1` e `test_g2_2` continuam
`xfail(strict=True)` de propósito: o defeito de isolamento existe e é da outra trilha.

**Custo de mudar.** Se um dia a função ganhar um parâmetro de "teto de linhas" em vez de "quantas manter", o
chamador some. Enquanto isso, a conta `manter = teto - 1` mora num lugar só, com o comentário do porquê.

## 2. Cláusula impossível: "nome de item de 2.048 caracteres" (portão do L0-03-f)

**Medido.** A refutação do L0-03-f manda o adversário abrir a tela "com nome de item de 2.048 caracteres". Não é
produzível: `plat.item` tem `CHECK (length(titulo) BETWEEN 1 AND 250)` desde a migração `011_catalogo.sql`, e o
modelo de entrada recusa antes (`limites.ITEM_TITULO_MAX = 250`, `docs/LIMITES.md`). A cláusula é insatisfazível
como está escrita — não é defeito da tela.

**Decisão: fica o banco, muda a cláusula.** 250 é o mesmo teto de título de item do produto de referência (a
paridade do L0-03-a foi escrita contra ele), já está publicado em `docs/LIMITES.md`, no OpenAPI e na mensagem de
erro, e é o que a busca por `titulo` indexa. Subir para 2.048 obrigaria a migrar a restrição, a revisar a coluna
de busca e a mudar a tela sem ganho nenhum: um título de 2 mil caracteres é descrição, não nome — o item já tem
`resumo` (até 5.000) e `descricao_html`.

A cláusula do portão passa a ser: **"nome de item no teto do banco (250 caracteres)"**. A prova está em
`tests/api/catalogo/test_notificacoes.py::test_titulo_no_teto_de_250_e_recusa_acima`: 250 passa em criar e em
renomear, 251 é recusado com 422 nos dois caminhos. Quem mantém `laco/estado.json` (o gerente) precisa corrigir a
linha da refutação do `L0-03-f-tela-conteudo`; esta trilha não edita o estado.

## 3. Notificação interna: quem escreve, e por que não é o `evento` (achado G2-7)

**Medido.** Metade do item L0-03-k não existia: nenhuma rota, tabela, migração ou linha de código de notificação
(`grep` por "notific" em `app/`, `db/` e `web/` devolvia zero). O ADR 0004 seção 8.5 dizia que a fonte seria
`plat.evento`, lido pelo L0-10 — no futuro.

**Decisão.** Tabela própria `plat.notificacao` (migração `20260906T1607_notificacao_interna.sql`), escrita na
mesma transação de quem origina o fato. Três razões:

1. `plat.evento` é por inquilino e por ALVO, não por destinatário: não há como marcar "lida" nem contar não lidas
   por usuário sem uma tabela de junção — que é exatamente esta tabela.
2. Ler `evento` por usuário exigiria varrer partições mensais a cada abertura de tela; a contagem do sino tem
   cláusula de tempo (≤ 20 ms) e aqui é um índice parcial `(usuario_id) WHERE lida_em IS NULL`.
3. O L0-10 continua dono do histórico e da exportação; a notificação não substitui evento nenhum — quem convida
   grava `grupos/convidar` em `evento` E notifica o convidado.

**Isolamento.** A segurança de linha da tabela tem duas políticas: `p_notificacao_propria` (FOR ALL) restringe
ler, marcar e apagar a `usuario_id = plat.usuario_atual()`, e `p_notificacao_criar` (FOR INSERT, sem `USING`)
deixa qualquer usuário do inquilino CRIAR uma notificação para outro usuário do mesmo inquilino sem poder lê-la
depois. É isso que faz "notificação de outro por id" devolver 404.

**Teto por minuto.** `plat.notificar` conta as notificações do usuário no último minuto e devolve NULL acima de
`limites.NOTIFICACOES_POR_MINUTO` (60): a notificação é descartada, nunca enfileirada. É a resposta à refutação
"10 mil notificações para um usuário em 1 min". Somado ao índice único `(usuario_id, chave)`, uma origem que
repete a mesma chave não cria nem a segunda linha.

**Por que a função é SECURITY DEFINER.** O worker roda com a role `plat_worker`, que por desenho (migração 006)
não tem privilégio de tabela nenhum — só EXECUTE em funções nomeadas. Para o worker notificar o dono do job ao
terminar, ou a função é definidora, ou o worker ganha INSERT na tabela, o que abre muito mais. A função nasce com
`REVOKE ALL ... FROM PUBLIC` e GRANT só para `plat_app` e `plat_worker`, como manda a migração 011 (a regra que
o achado G2-8 mostrou quebrada em 13 funções de outras migrações — não consertadas aqui: são da trilha das
funções definidoras).

**O que fica PARCIAL, declarado.** A hipótese do item lista cinco origens de notificação: convite de grupo,
pedido de entrada, job concluído/falhou, item compartilhado comigo e prazo de token. As três primeiras estão
emitindo. **"Item compartilhado comigo" e "prazo de token" NÃO emitem notificação nesta passagem** — a primeira
precisa decidir o leque (compartilhar com um grupo de 500 pessoas gera 500 linhas: ou entra com limite de
destinatários, ou vira uma notificação por grupo), e a segunda depende do relógio de expiração de token do
L0-02-d. Enquanto isso, o item L0-03-k está PARCIAL, não entregue.
