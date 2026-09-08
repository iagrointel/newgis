# Adversário — linha isolamento entre inquilinos (RLS, token de serviço, links públicos)

**Veredito: PASSA nos vetores atacados.** Ataques ao vivo contra `plat-api` real
(`127.0.0.1:8150`), sessão própria desta rodada (sem subagente). Cobre o que a varredura
automatizada (`L0-02-e-varredura-cruzada-rls`, 138/138 rotas do OpenAPI vivo) estruturalmente NÃO
testa: containment de link público entre itens irmãos do MESMO inquilino, e revogação de link.

## Itens cobertos
`L0-02-e-varredura-cruzada-rls` (complemento) · `L0-03-i-dependencias` (compartilhamento) ·
rotas de `app/catalogo/rotas_compartilhamento.py`.

## Ataques e evidência literal

1. **Link de compartilhamento não vaza item irmão do mesmo inquilino.** Criei dois itens no
   inquilino `demo` (X e Y, tipo `mapa`, sem relação entre si), um link cobrindo só X (`itens_incluidos: []`
   além do próprio X). `GET /api/compartilhado/{token}/itens/{X}` -> `200` (esperado). `GET
   /api/compartilhado/{token}/itens/{Y}` (item irmão, MESMO inquilino, não incluído no link) ->
   `404 item_inexistente`. PASSA — confirma que `compartilhado_item` checa `if iid not in
   link["itens"]` de verdade, não só filtra por inquilino.

2. **Link revogado para de funcionar imediatamente.** `GET /api/compartilhado/{token}` antes de
   revogar -> `200`. `DELETE /api/itens/{id}/links/{link_id}` -> `204`. Mesmo token, mesma URL,
   logo depois -> `404 link_invalido "link inexistente ou revogado"`. PASSA — sem janela de uso
   após revogação (a query de `link_resolver` já checa `revogado_em` na mesma leitura).

3. **Cookie de A não abre recurso de B por id direto** (já registrado no laudo de
   `L0-02-ADVERSARIO.md`, reaproveitado aqui como parte desta linha): `GET /api/usuarios/{id de B}`
   com cookie de A -> `404`. PASSA.

## O que ESTE laudo NÃO cobre (nomeado)

- Não ataquei rotas de listagem/agregação (`GET /api/itens`, `/api/itens/facetas`,
  `/api/itens/tags`) para procurar vazamento por filtro mal escopado (ex.: facetas contando itens
  de outro inquilino). A varredura automatizada cobre a ROTA, não necessariamente todo caminho de
  código de agregação — pendência nomeada para a próxima rodada desta linha.
- Não ataquei o link público "por inquilino que permite público" (`_contexto_publico` /
  `tenant_publico_itens`, D24) — não tentei achar um item de um inquilino que NÃO habilitou
  público e ver se `plat.tenant_publico_itens` mesmo assim devolve algo.
- Não testei token de serviço com restrição de IP/Referer sob ataque real (só a escalada de escopo
  `admin:inquilino`, já registrada no laudo de identidade).
- Não testei condição de corrida em `criar_link`/`revogar_link` (duas revogações simultâneas, ou
  uso do link no exato instante da revogação).

## Conclusão

Os 3 vetores atacados nesta passagem (containment de link entre irmãos, revogação imediata,
cookie cruzado por id direto) resistem. Nenhum achado novo. Recomendo a próxima rodada desta linha
focar nas rotas de agregação/faceta e no fluxo de item público por inquilino (D24), que ainda não
foram atacados de verdade nesta sessão.
