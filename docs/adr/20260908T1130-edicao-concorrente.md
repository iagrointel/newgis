# Edição concorrente sem CRDT: mesclagem por nó, presença e bloqueio leve (item L5-13-edicao-concorrente)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L5_CONCEITO.md` D2 (nós com id ULID), D3 (histórico de
versões é o registro oficial), D12 (versão otimista, presença por SSE, mesclagem por nó, CRDT adiado); ADR
`20260907T1522-desfazer-refazer-rascunho.md` (L5-09: 409 sem perda silenciosa).

## Contexto

O L5-09 deixou o construtor com versão otimista (`versao_atual` no PATCH; 409 quando diverge) e um painel de
conflito que nunca perde a edição local. Faltava o que D12 pede para várias pessoas no mesmo documento: quando
os dois lados tocaram NÓS DIFERENTES, gravar os dois sem incomodar ninguém; quando tocaram o MESMO nó, mostrar a
diferença e deixar a pessoa decidir; e dizer quem está no documento e em que nó, antes de o conflito acontecer.

## Decisão

1. **`base_versao` no PUT/PATCH** (`app/catalogo/modelos.py::ItemEditar`): a versão que o cliente LEU. Igual à
   atual, caminho normal. Diferente e item de família de grafo (`app`, `painel`) com `dados` no corpo:
   mesclagem de três vias por nó (`app/catalogo/mesclagem.py`) entre o corpo da `base_versao` (lido de
   `plat.item_versao`), o corpo atual e o do cliente. Sem conflito, grava o resultado e devolve o item com
   `mesclagem` (`do_cliente`, `do_servidor`, `versao_servidor`); com conflito, 409 `versao_conflito` com o documento
   ATUAL inteiro no `detalhe.dados` e os ids em `detalhe.conflitos` — nada é escolhido às escondidas. `versao_atual`
   (regra estrita do L5-09) continua valendo intacto para quem preferir.
2. **Unidade de mesclagem = nó por id** (e ligação por JSON canônico; chave de corpo fora `nos` como unidade). Nó
   mudado só de um lado fica como esse lado deixou; mudado igual dos dois, fica; diferente dos dois (inclusive
   removido × alterado), conflito. Ordem: a do cliente, com os nós que só o servidor criou inseridos depois do seu
   antecessor. Função pura, determinística, provada com 100 pares de edições aleatórias em nós disjuntos sem uma
   alteração perdida (`tests/unit/test_mesclagem.py`) e outros 100 pares pela API (`tests/api/catalogo/...`).
3. **Presença efêmera, sem tabela** (`app/catalogo/presenca.py`): batimento `POST /api/itens/{id}/presenca` (aba,
   nó selecionado) a cada 5 s, expira em 12 s; fluxo `GET .../presenca/eventos` (SSE) manda a lista inteira a cada
   mudança. Registro em memória por processo com fan-out por `NOTIFY <PLAT_CANAL_JOB>_presenca` (a API de produção
   tem 2 workers, L7-19). Só quem lê o item entra (RLS: outro inquilino = 404). O que sai é login, nome, nó e
   instante — nunca o documento.
4. **Bloqueio leve por nó**: a tela marca os nós ocupados por outras abas (`data-ocupado`, contorno) e avisa quem
   seleciona um nó ocupado (`#aviso-no-ocupado`); nada trava (D12: aviso, não trava). Ao gravar, o servidor é a
   única verdade — o aviso só reduz a chance de conflito.
5. **A tela absorve a mesclagem**: 200 com `mesclagem` entra no editor sem passar pelo histórico de desfazer (não é
   uma edição da pessoa), mantendo a seleção; estado "gravado (versão N; mesclado com a versão M de outra sessão)".
   O autosave de rascunho (L5-09) usa o mesmo `base_versao`.
6. **CRDT continua adiado** (Yjs, 300 kB): o e2e desta fase não mediu perda de trabalho — 4 nós em 2 rodadas com o
   PATCH retido 3 s e liberado fora de ordem, 0 alteração perdida.

## Consequências

- O e2e do L5-09 "duas abas em conflito" mudou de sentido: nós diferentes agora mesclam (200), e o 409 com a
  diferença só acontece no mesmo nó (`tests/e2e/test_edicao_concorrente.py`). O painel de conflito ganhou o
  documento atual do próprio 409 (sem buscar a versão) e o nó em conflito marcado na árvore de diferença.
- Item sem grafo (`mapa`, `camada`...) com `base_versao` diferente cai no 409 estrito com o documento atual: a
  mesclagem por nó só faz sentido onde há nó.
- Duas pessoas que trocam o MESMO nó ao mesmo tempo continuam tendo de escolher; a escolha explícita "gravar a
  minha nos nós em conflito" reenvia com a `base_versao` atual (o resto já foi mesclado pelo servidor).
- Presença some sozinha em 12 s sem batimento; fechar a aba avisa por `sendBeacon`. Com o processo reiniciado, a
  lista recomeça vazia e se refaz no batimento seguinte (5 s).
