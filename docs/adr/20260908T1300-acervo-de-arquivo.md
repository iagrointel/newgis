# Camadas de arquivo do acervo da casa no catálogo (item L6-01-i-raster-e-arquivos)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L3L6_CONCEITO.md` B1/B2/B5 (acervo com procedência),
migração 021 (ficha de FONTE), migração 027 (registro de camada em TABELA), ADR `20260907T0300` (ladrilho por
token, item L1-02, dependência).

## Contexto

O acervo da casa tem três corpos: fontes (376), tabelas com geometria no Postgres (475 candidatas) e ARQUIVOS.
O terceiro estava fora do catálogo. Medido em 08/09/2026 em `acervo.camada_arquivo`: 321 arquivos, 3,6 GB, 27
fontes nomeadas e 121 linhas sem fonte, **100 % com sha256** — 26 raster (`.tif`/`.vrt`) e 295 vetoriais.

## Decisão

1. **Vista `plat.acervo_arquivo`** (security_invoker) sobre `acervo.camada_arquivo` + `acervo.fonte`, com
   `tipo` (raster × vetor pela extensão) e `publicavel` (licença escrita). Diferença DECLARADA em relação à
   migração 021: aquela filtra `licenca IS NOT NULL` (D17); esta NÃO filtra. Motivo medido: **nenhuma das 27
   fontes de arquivo tem licença escrita** — com o filtro, o acervo de arquivo seria invisível até para a casa.
   A regra D17 passa a valer onde ela decide: o item nasce **privado** e com `dados.uso_restrito = true`.
2. **sha256 conferido antes de ingerir**: `app/acervo/arquivos.py::conferir` lê o arquivo em blocos de 1 MiB e
   compara com o registro. Divergiu, `hash_divergente` e NADA é criado (a refutação do item morre aqui). O hash
   gravado em `plat.acervo_arquivo_exposto` é o do DISCO, com o instante e o autor.
3. **Raster por REFERÊNCIA, nunca cópia**: o item `raster` e o item STAC apontam para `acervo://<caminho>`, e o
   motor de ladrilho (rio-tiler) abre o arquivo local — `bytes_copiados_para_o_balde = 0`. Copiar 3,6 GB para o
   balde dobraria o acervo no mesmo disco (guardrail D21, disco a 96 %).
4. **Vetor ingerido uma vez** para `d_<slug>.c_<hash>` com `ogr2ogr`, a MESMA tabela e a mesma preparação
   (`plat.camada_schema_garantir` + `plat.camada_preparar`) da ingestão do L0-04 — sem uma segunda máquina de
   ingestão. O item é `camada_vetorial` com `fonte: hospedada`.
5. **Guardrail de tamanho**: arquivo acima de `ACERVO_ARQUIVO_BYTES_MAX` (2 GB, o mesmo teto do raster do
   L1-01) é recusado sem job; o lote tem teto próprio de 3 GB (D21). A rota recusa antes de enfileirar.
6. **A raiz dos arquivos é configuração** (`PLAT_ACERVO_ARQUIVOS_RAIZ`), não caminho no código: o registro é da
   casa, a instalação pode ser outra. Sem raiz, a lista responde vazia e a exposição responde 409 — nunca erro.
   Todo caminho é resolvido dentro da raiz (`..`, caminho absoluto e symlink que sai dela são recusados).

## Consequências

- O ladrilho do raster do acervo custa segundos no primeiro pedido (medido: 3.156 ms): os `.tif` da casa são
  GeoTIFF comum, sem visão geral nem organização em blocos. Converter para COG resolveria a latência e custaria
  disco — decisão do dono (D21), não tomada aqui. O cache do nginx (L1-02) absorve o segundo pedido em diante.
- Item exposto de fonte sem licença é privado e marcado; publicar ou compartilhar continua sendo decisão de
  quem tem o privilégio, com o aviso no próprio item. A licença escrita é a fila de trabalho do acervo (D17).
- A exposição é idempotente por caminho: pedir duas vezes devolve o item que já existe.
- O `fonte_id` vira tag do item; o DOMÍNIO não, porque o vocabulário do acervo tem vírgula ("Empresas, trabalho
  e renda") e `plat.tags_validas` recusa vírgula em tag.
