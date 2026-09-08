# ADR 20260908T1120 — vista de camada é uma VIEW do PostgreSQL, não um filtro na rota

Item `L5-32-vistas-de-camada` (linha L5 builder).

## Contexto

A vista de camada é o equivalente da *hosted feature layer view*: mesma tabela, filtro próprio, campos
escondidos, leitura ou escrita, extensão limitada, estilo e janela de atributos próprios, compartilhável
separadamente da camada-mãe.

O caminho óbvio seria guardar filtro e campos ocultos no item e aplicá-los em cada rota de leitura. Isso
exige que TODA rota — `query` do FeatureServer, OGC API Features, WFS, descritor de serviço, tile — lembre
de aplicar os dois. Um esquecimento em qualquer uma delas não dá erro: entrega o campo escondido.

## Decisão

A vista é uma VIEW no schema do inquilino (`d_<slug>.c_<16 hex do item da vista>`, o mesmo padrão de nome de
uma tabela de camada), registrada no catálogo como item `vista_de_camada` com `schema`/`tabela` apontando
para ela. O tipo `vista_de_camada` já existia reservado desde `011_catalogo.sql`, com o tipo de relação
`vista_de_camada` (`arrasta_dono`, `apaga_junto`); este item o preenche e sobe o esquema para v2.

Três consequências:

1. **Campo oculto não é filtrado na saída: ele não está na relação.** `information_schema.columns` não o
   devolve, logo `app.consulta.campos.campos_da_camada` não o vê, `outFields=*` não o pede e a lista branca
   do `where` não o aceita. Não existe parâmetro do cliente que o traga de volta.
2. **O filtro está congelado um nível abaixo do cliente.** O texto passa por `app.consulta.where_ast`
   (lista branca de coluna, valor parametrizado) e os parâmetros são literalizados por `cur.mogrify`, porque
   definição de view não guarda parâmetro. `where=1=1` do cliente vira `1=1 AND <filtro>`.
3. **Nenhuma rota de leitura precisou aprender o conceito.** Só o filtro por tipo mudou, de
   `tipo = 'camada_vetorial'` para `tipo = ANY(TIPOS_CAMADA)`, num só lugar (`app.catalogo.tipos`).

`security_invoker = true` (PostgreSQL 15+): a política de RLS da tabela-mãe é avaliada com o papel e o
contexto de QUEM CONSULTA, nunca com os do dono da view. Sem isso, uma view seria um caminho lateral em
volta do isolamento por inquilino.

Vista editável nasce `WITH CASCADED CHECK OPTION`: edição que empurraria a feição para fora do filtro ou da
extensão é recusada pelo banco. A violação vira 422 `fora_da_vista` em `app.auth.comum.erro_do_banco`, não
500. Vista `somente_leitura` é recusada na porta única de escrita
(`app.edicao.servico.exigir_camada_editavel`), ANTES do atalho de administrador: ali a recusa não é
permissão de quem escreve, é a natureza do objeto — quem precisa escrever escreve pela camada-mãe.

## O que não se decidiu aqui

- **Tile vetorial da vista.** As funções SQL de tile (`L2-04-a`, Martin) filtram `tipo = 'camada_vetorial'`
  dentro de migrações já aplicadas. Servir a vista por tile é mudança dessas funções, do item delas.
- **Filtro CQL2.** A casa ainda não tem analisador CQL2; o dialeto usado é o `where` do FeatureServer, que já
  tem analisador próprio e testado. Quando o CQL2 chegar (item `L2-04-g`), ele compila para a mesma
  `ConsultaSQL` e a vista o aceita sem mudar de forma.
- **Vista de vista.** Recusada com 422: encadear views multiplicaria o custo de plano sem pedido de ninguém.

## Consequência incômoda, registrada

A ficha pública de um item entrega `dados` inteiro. Para a vista isso entregaria a LISTA do que ela esconde e
o identificador da camada-mãe, então `app.catalogo.comum.item_json` passa a remover `campos_ocultos` e
`camada_id` quando a leitura é pública. Para os demais tipos, `dados` continua saindo como sempre — não é
regressão deste item, mas é dívida conhecida.
