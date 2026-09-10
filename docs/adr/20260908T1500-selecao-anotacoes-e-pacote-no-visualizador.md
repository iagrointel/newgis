# ADR 20260908T1500 — seleção, anotações e importação de pacote com controle no visualizador (UX-23)

## Contexto

Seis rotas de escrita do mapa existiam sem controle em tela: filtro por atributo, seleção por geometria e
seleção espacial entre camadas (L2-01-h, `app/mapa/selecao.py`), edição e remoção de anotação (L2-01-k) e a
importação de pacote de mapa (L2-01-l). O painel de anotações chamava PATCH com PUT (405 silencioso) e
avisava por `window.alert`. O ramo `wt/il201hselec` traz só o backend; o cliente da seleção não existia.

## Decisão

1. Painel **Seleção** (`web/js/mapa/selecao.js`, atalho `s`) no chrome único de UX-04, sobre UMA camada
   hospedada ligada. Três maneiras: por atributo (condições campo · operador · valor combinadas com E/OU,
   traduzidas para CQL2-JSON no vocabulário da lista branca; valores únicos do campo como sugestão via
   `/valores`; o SQL equivalente devolvido pelo servidor é mostrado), por geometria do painel Desenho
   (intersecta / a até X m, combinada com a seleção atual: nova, somar, subtrair, interseccionar) e entre
   camadas (feições desta que intersectam / estão a X m de outra). Validação local nomeada por condição
   (número em campo numérico, valor vazio, distância) antes de qualquer chamada; erro do servidor nomeado com
   o campo e a referência.
2. O resultado não cria estado novo: vai para a **tabela de atributos** (`tabela.selecionar(camada, ids)`,
   mesma trilha do clique numa linha, com realce no mapa), pode virar **filtro da camada no mapa** (filtro de
   ids nas camadas de estilo, declarado "amostra" quando o servidor truncou; o filtro original é guardado e
   reposto) e é **guardado como item `selecao`** (`POST /api/itens`, `criterio.modo` no vocabulário do esquema
   do tipo: filtro / retangulo / poligono / laco / espacial).
3. Anotações reescritas com `<plat-estado>` (sem alvo, carregando, vazio, erro com tentar de novo) e
   `<plat-aviso>` no lugar de `alert`: editar o texto (só o autor, PATCH via `remendar`), resolver/reabrir,
   apagar com confirmação (só o autor). 403 e 404 viram texto nomeado; a lista fica.
4. Importar pacote no painel Exportar (`POST /api/mapa/pacotes/importar`, zip cru no corpo): sem arquivo e
   arquivo que não é zip são recusados no navegador; 413/422 nomeados com referência; sucesso mostra o resumo e
   a ligação para o mapa importado, e o resumo sobrevive ao redesenho do painel após a recarga do catálogo.
5. `Desenho.aoMudar` passa a aceitar vários ouvintes (era um callback único, e o segundo painel apagava a
   lista do primeiro). `remendar` (PATCH) entra em `web/js/base/api.js`.

## Consequências

- A cobertura do mapa fica sem lacuna de escrita; PATCH/DELETE de anotação passam a funcionar (o PUT nunca
  funcionou). O gerador de cobertura só reconhece a chamada quando o caminho está na mesma linha do
  `enviar(`/`chamar('POST'`; o código segue essa forma e comenta o porquê.
- Seleção e filtro no mapa são por amostra de ids (limite do servidor, 5.000 por padrão): o painel diz quando
  a amostra é menor que a contagem. Filtro persistente como `vista_de_camada` fica para a ADR 0004.
- O tipo `selecao` aponta para `/static/js/catalogo/tipos/selecao.js`, que não existe no tronco: o item abre
  no catálogo pela ficha genérica. Fica registrado para o dono do catálogo.
