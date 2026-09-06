# ADR 0022 — Documento de mapa: item do catálogo, referência por uuid, esquema publicado

Data: 2026-09-06 · Item: `L2-01-a-documento-mapa` · Estado: aceito (turno 3, trilha `stac`)
Decorre de: ADR 0004 (catálogo), ADR 0011 (documento de construtor), C1/C2/C3/C12 de `laco/decomposicao/L2_CONCEITO.md`

## Contexto

Vinte e quatro itens da linha do mapa web (lista de camadas, legenda, popup, filtro, tabela de atributos,
impressão, incorporação, aplicação, painel) leem e escrevem a mesma coisa: o documento que diz QUAIS camadas
o mapa tem, em que ordem, com que estilo e em que extensão. Se esse formato mudar depois, muda tudo — por
isso ele é decidido aqui, por escrito, antes dos 24.

Na Web Map Specification da Esri (lida em 06/09/2026) a camada do mapa carrega a URL absoluta do serviço
(`url`) ou o `itemId` do portal. O handoff do papel `esri` (T1) registra que a irritação nº 1 de quem migra é
exatamente essa: a URL do portal fica congelada dentro de cada JSON, e trocar o endereço do portal quebra
todo mapa salvo.

## Decisão

1. **O mapa é um item do catálogo** (`plat.item`, tipo `mapa`), não uma tabela nova. Ganha de graça RLS por
   inquilino, compartilhamento, pasta, versão imutável (`plat.item_versao`), relação (`plat.item_relacao`) e
   evento de auditoria. `POST/GET/PUT /api/mapas` é uma porta curta para o mesmo item; `/api/itens` continua
   valendo, e a validação é a mesma nas duas portas porque mora no modelo, não na rota.
2. **Referência só por uuid.** Toda camada é `{"id": <ULID local>, "ref": <uuid do item>}`. Nunca URL, nunca
   `itemId` de outro sistema. O `id` é local ao documento (a mesma camada pode entrar duas vezes, com estilos
   diferentes); o `ref` é o item. A URL de serviço é RESOLVIDA na leitura, em `GET /api/mapas/{id}/completo`.
3. **Esquema publicado.** O JSON Schema (Draft 2020-12) vive em `plat.tipo_item.esquema` e é publicado em
   `docs/esquemas/mapa-v1.json` por `docs/gerar_esquemas.py` (o arquivo é gerado do banco, nunca digitado).
   Documento fora do esquema = `422` com o caminho do campo.
4. **O que o esquema não expressa fica em `app/mapas/documento.py`**: id repetido, grupo inexistente, ciclo de
   grupo, profundidade de grupo acima de 3, favorito apontando para camada fora do documento, extensão
   invertida. São as regras que precisam olhar a lista inteira.
5. **Grupos achatados, não árvore.** `corpo.grupos[]` é uma lista com `pai`, e a camada aponta o grupo por id.
   Motivo: a ordem de desenho é a da lista `camadas` (uma só sequência, como o `layers` da Style Spec do
   MapLibre); com árvore aninhada a ordem de desenho passaria a depender de percurso, e todo consumidor
   (renderizador, impressão, legenda, exportação) teria de repetir esse percurso. Aninhamento até 3 níveis,
   ciclo recusado — a Esri não documenta limite de profundidade.
6. **CRS de exibição fixo em 3857**, CRS do dado livre (C12). `crs_exibicao` é `const: 3857` no esquema: quem
   mandar 4326 leva 422, em vez de descobrir na tela que o mapa não desenha.
7. **Escala com nome honesto.** `escala_min` é o MENOR denominador (mais perto) e `escala_max` o maior; visível
   quando `escala_min <= denominador <= escala_max`. A Esri usa `minScale` para o limite AFASTADO, o que
   inverte a intuição; a tabela de paridade (`docs/PARIDADE.md`) diz o de-para para quem migra.
8. **Dependência registrada.** As referências viram linhas em `plat.item_relacao` pelo extrator de `mapa`
   (`app/catalogo/relacoes.py`): camada/raster/rede como `camada_de_mapa`, estilo/popup como `estilo_de_mapa`,
   conexão do acervo como `servico_de_mapa` (tipos novos nesta migração, porque `plat.relacao_tipo` limita as
   famílias de destino). É daí que sai o `409 possui_dependentes` ao apagar uma camada usada por um mapa.
   Como o extrator não tem cursor para descobrir a família do destino, ele emite `auto:mapa` e `sincronizar`
   resolve o tipo em uma consulta.

## Consequências

- **Quebra compatível declarada**: `corpo.camadas` como lista de uuid soltos (a forma que existia enquanto o
  tipo `mapa` tinha `corpo` livre) passa a ser `422`. Nenhum código de `app/` gravava assim; quatro arquivos de
  teste gravavam, e passaram a usar o ajudante `documento_mapa(...)` de `tests/api/catalogo/conftest.py`.
- `esquema_versao` continua 1: todo documento gravado até aqui é `{"esquema_versao":1,"corpo":{}}`, que segue
  válido (nenhuma propriedade de `corpo` é obrigatória). Não há migração de conteúdo, só aperto de validação.
- Quem lê o mapa faz UMA chamada (`/completo`), não 1 + N. Medido: p95 de 20,7 ms com 10 camadas em 50 chamadas
  (`tests/medidas/L2-01-a.json`), contra o teto de 150 ms do portão.

## Fronteira honesta (o que este ADR NÃO decide)

- **URL de tiles não é promessa**: `/completo` devolve o contrato (`/tiles/{token}/c_<16 hex>/{z}/{x}/{y}.pbf`
  para vetor, `/raster/{token}/<uuid>/{z}/{x}/{y}.png` para raster) com `pronto: false` e o motivo, porque não
  há Martin nem TiTiler instalados nesta máquina (itens L2-01-b e L1-02). Camada de conexão externa é a única
  que sai com URL de verdade — a que o próprio item de conexão registra.
- **`dominios` sai sempre vazio**, com o motivo escrito: a camada ainda não guarda vocabulário de domínio por
  campo (L0-04-c está PARCIAL). Campo vazio com motivo, nunca valor inventado.
- **`filtro`** é validado como objeto; a gramática CQL2-JSON é do item L2-01-h.
- **`estilo.embutido` e `popup.embutido`** são objetos livres até L2-02-a e L2-01-d fixarem a forma.
- A tela `/mapa?id=` lista, reordena (arrastando, por teclado e por botão) e salva; ela **não desenha** as
  camadas do documento no canvas, pelo mesmo motivo dos tiles — e diz isso na própria linha da camada.

## Alternativas descartadas

- **Adotar o Web Map JSON da Esri como formato interno**: carrega a URL absoluta e o vocabulário de 27 tipos de
  camada da Esri, e amarraria nosso catálogo ao portal deles. A conversão de ida e volta vira item próprio
  (L2-08-c/d), que é onde ela deve estar.
- **Configuração em colunas** (sem documento): não sobrevive a estilo, popup, filtro e favorito por camada.
- **Árvore aninhada de grupos**: ver decisão 5.
