# ADR 0018 — Publicação sem cópia do acervo: view definer, porteiro de assinatura, só leitura

Data: setembro de 2026 · Item `L6-01-b-view-so-leitura` · Migração `20260906T15521aa_acervo_publicacao.sql`

## Contexto

O acervo da casa tem 1,1 mil tabelas de fonte espalhadas por três servidores. Copiar qualquer uma delas para
dentro do schema da plataforma custaria disco (que está a 91-94 % nas duas máquinas) e criaria uma segunda
verdade, que envelhece sozinha. O item L6-01-a já entregou o REGISTRO de camadas (`plat.acervo_camada`, uma
linha por tabela canônica com geometria, com lista branca de colunas). Falta a porta: como um inquilino lê uma
dessas tabelas sem que a plataforma copie o dado e sem que o papel da aplicação ganhe acesso ao schema
`public` inteiro.

## Decisão

Uma VIEW por camada exposta, no schema `plat_acervo`, com quatro propriedades:

1. **Lista branca de colunas.** A view seleciona exatamente `plat.acervo_camada.colunas_expostas` mais a
   coluna de geometria. Coluna fora da lista não existe na view — não é filtrada na aplicação, não existe.
2. **Dona é `plat_acervo_publicador`**, papel `NOLOGIN` criado só para isso. É o privilégio dele que a view
   usa na tabela de origem, e ele recebe `SELECT` de uma tabela por vez, à medida que o publicador roda.
   `plat_app` não tem privilégio nenhum em `public`.
3. **Porteiro no `WHERE`**: `plat.acervo_pode_ler('<acervo_camada_id>')`, que é verdadeiro só quando existe
   linha em `plat.acervo_assinatura` para o inquilino da sessão (o mesmo GUC `plat.tenant_id` que a RLS do
   resto da plataforma usa).
4. **Só leitura no banco**: a view recebe `GRANT SELECT` e nada mais. `INSERT`/`UPDATE`/`DELETE` são recusados
   pelo Postgres, não pela ausência de rota.

Quem cria as views é `scripts/acervo_publicar.py`, rodando como `postgres`; a migração cria só o schema, o
papel, a tabela de assinatura, o porteiro e o registro do que foi publicado. A lista de colunas muda a cada
varredura da casa, então não pode ser congelada em migração.

## Duas coisas que a hipótese do item pedia e a medição derrubou

**`SECURITY INVOKER` não pode ser usado aqui.** Com `security_invoker = true` o Postgres checa o privilégio da
tabela de ORIGEM contra quem chama. Como o mesmo portão do item proíbe qualquer `GRANT` direto de tabela
`public` a `plat_app`, a leitura falha: medido, `ERROR: permission denied for table car_area_imovel`. As duas
cláusulas não podem valer juntas. A que ficou de pé é a do isolamento (`plat_app` sem privilégio em `public`);
a view fica no modo padrão, definer. O teste
`test_security_invoker_seria_negado_pelo_banco` cria a view invoker e prova a recusa a cada rodada.

**`security_barrier` não pode ser usado nesta consulta.** É a proteção clássica de view definer, mas ela
impede que o qual do usuário desça abaixo do qual da view; o operador `&&` de geometria não é `LEAKPROOF`
(`pg_proc.proleakproof = false`, conferido), então ele deixa de chegar ao índice GiST e a consulta de mapa
vira varredura sequencial da tabela inteira — cancelada depois de 2 min 10 s, contra 1,5 ms sem barrier.

O que protege no lugar da barreira, e protege melhor: o porteiro recebe um argumento CONSTANTE e não olha
nenhuma coluna, então o planejador o transforma em `One-Time Filter`, avaliado uma única vez antes de a
varredura começar. Sem assinatura, o nó do índice aparece no plano como `(never executed)`: não existe linha
para vazar por qual malicioso porque nenhuma linha chega a ser lida. O teste
`test_porteiro_vira_filtro_de_uma_vez_e_nao_varre_a_tabela` guarda essa propriedade do plano.

**Limite honesto que sai daí**: se um dia o porteiro passar a depender de coluna (assinatura por UF, por
exemplo), ele deixa de ser `One-Time Filter` e toda esta análise tem de ser refeita.

## Consequências

- Publicar uma camada é uma operação de catálogo, não de dado: nenhum byte é copiado, e a atualização da fonte
  aparece na view no mesmo instante.
- Despublicar é derrubar a view: camada que sai de `estado = 'exposta'` no registro perde a view na próxima
  rodada do publicador, sem passo manual.
- O raio de exposição de um erro é o conjunto de tabelas que `plat_acervo_publicador` enxerga, nunca "tudo que
  o `postgres` enxerga".
- O schema `plat_acervo` entra na reescrita de ambiente (`app/schema_ambiente.py`): sem isso uma trilha ou a
  homologação escreveria no `plat_acervo` de produção, porque nem `plat_acervo` nem
  `plat_acervo_publicador` casam com a fronteira de palavra de `plat`.

## Fronteiras que este item NÃO cruzou

- **Martin não existe nesta máquina** (porta 8151 reservada, `ARQUITETURA.md` seção 2). O SQL de tile que ele
  publicaria existe e é servido pela própria API (`/api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt`), com o
  porteiro dentro; "Martin serve tiles pela função com inquilino" fica pendente do serviço.
- **FeatureServer e OGC API de feição não existem** no repositório (`L2-04` não construído). A garantia de só
  leitura que dá para provar hoje é a do banco (a view não tem `GRANT` de escrita) mais a da superfície HTTP
  (qualquer verbo de escrita nestes caminhos é 405). `applyEdits = 405` literal depende do FeatureServer.
- **`e2e adiciona ao mapa`** depende de `L2-01-mapa-web` (camada do catálogo no visualizador), que não existe:
  hoje `/mapa` só desenha o mapa-base PMTiles.
