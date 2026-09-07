# Classes de relacionamento entre camadas (item L2-10-b-relacionamentos)

## Contexto

O ArcGIS Enterprise publica "relationship classes" entre camadas hospedadas: 1:1, 1:N e N:M, com chave de
origem/destino (campo ou `GlobalID`), relacionamento "composto" (apagar a origem apaga os destinos) ou
"simples", nome direto/inverso, cardinalidade mínima/máxima opcional, e o protocolo REST
`relationships`/`queryRelatedRecords` nos hosted feature layers (11.4). O item pede o mecanismo completo:
integridade real no banco, API própria, paridade REST, popup no navegador e sobrevivência a reimportação
pela chave (nunca pelo `fid` físico).

## Decisão

- **1:N/1:1 vira FK real** na tabela de camada de DESTINO, `(tenant_id, chave_destino) -> (tenant_id,
  chave_origem)`: `ON DELETE CASCADE` quando `composto=true`, `ON DELETE SET NULL`/`RESTRICT` quando simples
  (conforme a coluna aceitar nulo). É a mesma regra da casa: toda FK entre tabelas de inquilino é composta
  com `tenant_id`, nunca só a chave de negócio.
- **N:M não ganha FK real** (o valor de junção pode ligar QUALQUER um dos dois lados, sem ordem fixa de
  criação): a integridade é por GATILHO (`plat.relacionamento_junc_conferir`), consultando a tabela viva na
  hora de ligar. Uma tabela de junção ÚNICA (`plat.relacionamento_junc`, discriminada por `rel_id`) serve
  toda classe N:M do inquilino — evita DDL dinâmico por classe.
- **A chave nunca é o `fid` físico.** `chave_origem`/`chave_destino` são um nome de campo ou `'globalid'`; a
  cláusula "sobrevive a reimportação" (apagar e recriar a linha com o mesmo `globalid`, `fid` mudando) é
  testada e passa porque a FK e a junção guardam o VALOR da chave, nunca o `fid`.
  V. `db/migracoes/20260907T1244_relacionamentos.sql`.
- **Cardinalidade máxima** (1:N) é um gatilho GERADO por tabela de destino (mesmo padrão do L2-10-a: só
  `%I`/`%L`, nunca concatenação crua no corpo do dollar-quote — a mesma classe de bug que o L2-10-a corrigiu
  depois de publicado). Cardinalidade mínima é só imposta ao DESLIGAR um par N:M; ao CRIAR não é imposta
  (mesma lacuna que o Pro deixa fora de uma sessão editável — exigir o mínimo a cada instante intermediário
  de uma edição incremental travaria a criação normal de pai antes dos filhos).
- **`GET /api/camadas/{id}/relacionamentos`** (novo nesta passagem) lista as classes que uma camada enxerga,
  dos dois sentidos (nome direto quando é origem, nome inverso quando é destino) — é o que a tela usa para
  montar o popup sem conhecer o nome do relacionamento de antemão.
- **Popup** (`web/js/dominios/tela.js`, reaproveitando a tela `/camadas/{id}/dominios` do L2-10-a): um botão
  "Relacionados" por linha da tabela de feições abre um `<plat-dialogo>` com uma seção por classe, listando
  os fids relacionados com link para `/camadas/{alvo}/dominios?fid=N`; a página de destino lê `?fid=` da URL
  e destaca (`tr.destaque`) a linha correspondente, se estiver na primeira página carregada — é a forma mais
  simples de "navegar para o registro" sem duplicar a tela de feições por camada.

## Fora desta passagem (fronteira honesta)

- Formulário de **criar/ligar/desligar um registro relacionado a partir do popup** (a hipótese do item cita;
  o portão literal só pede "popup mostra e navega" — ligar/desligar já existe pela API própria, só não tem
  botão na tela). Registrado para item futuro, não é regressão: o mecanismo de banco já suporta.
- Importação/exportação FGDB preservando relacionamento: a ingestão vetorial desta versão (L0-04) não cobre
  File Geodatabase; sem ingestão de FGDB não há o que preservar ainda.
- Paginação medida em 100 mil relacionados numa única origem: o mecanismo (`limite_relacionados`, testado
  travando o teto pedido pela consulta) é o MESMO em qualquer N; a rodada de 100 mil concreta não foi feita
  nesta passagem por custo de disco/tempo compartilhado da máquina (`tests/medidas/L2-10-b-relacionamentos.json`,
  medida `paginacao_limite_relacionados_trava_teto`, N=25).
