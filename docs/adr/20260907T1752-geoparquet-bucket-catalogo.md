# ADR 20260907T1752 — GeoParquet particionado no bucket, registrado no catálogo (item L2-15-a)

## Contexto

O item pede GeoParquet como "formato de trabalho para o grande": diferente da exportação comum
(L0-04-h-exportar, ADR 0018), aqui o resultado não é um download efêmero de 7 dias — é um ou mais arquivos
que ficam VIVOS no bucket do inquilino, com esquema/contagem/bbox/sha256/proveniência registrados como item
do catálogo, atualizáveis por versão, e (no modo `arquivar`) capazes de substituir uma tabela de histórico
inteira depois de conferir a contagem.

## Decisão

1. **Reusar o motor do L0-04-h, não recriar.** `app/geoparquet/motor.py` importa direto de
   `app.exportacao.motor` (conninfo com `-c plat.tenant_id=N`, guarda de disco, cronômetro, limpeza) — só a
   montagem do SELECT muda (colunas de partição derivadas), e a montagem do intermediário GPKG usa o mesmo
   `Formato("gpkg")` do catálogo de formatos da exportação. `app/geoparquet/duckdb_cli.py` reusa
   `_conexao`/`_literal` de `app.exportacao.parquet_cli` (mesmos três ajustes de memória medidos em
   06/09/2026; DuckDB não sobrevive a `fork()`, por isso continua rodando como processo próprio, neto do
   job).
2. **Selo de versão GeoParquet 1.1.0 por troca binária.** O DuckDB 1.5.5 desta máquina escreve o metadado
   `geo` na versão 1.0.0 (medido; sem opção para pedir 1.1). O conteúdo que ele escreve já satisfaz o schema
   1.1 (campos obrigatórios batem; os novos campos de 1.1 são opcionais), então a troca é um find-and-replace
   binário de `"version":"1.0.0"` por `"version":"1.1.0"` (mesmo número de bytes, não mexe em offset do
   rodapé Parquet) — só acontece quando o padrão aparece exatamente uma vez. Vendorizado
   `app/geoparquet/geoparquet_1_1_schema.json` (schema oficial, `github.com/opengeospatial/geoparquet` tag
   v1.1.0, baixado em 07/09/2026) para o portão validar contra ele.
3. **Partição hive opcional, por valor ou por ano/mês.** `particionar_por: {coluna, grao}` — `grao: "valor"`
   particiona pela própria coluna (ex.: UF); `grao: "ano_mes"` deriva `_geoparquet_ano`/`_geoparquet_mes` via
   `to_char()` no SELECT (essas duas colunas técnicas nunca entram no `esquema` do item do catálogo). Sem
   partição, um arquivo único `dados.parquet`.
4. **Um item do catálogo por fonte+partição, atualizado a cada rodada, nunca recriado.** `plat.geoparquet_job`
   é o histórico de rodadas (auditoria); o item `tipo=parquet` em `plat.item` é o estado atual, e sua
   `catalogo_item_id` é achada pela rodada `pronta` mais recente da MESMA origem+partição. Isso é o que torna
   a atualização "por versão": `versao` sobe 1 a cada rodada, e cada arquivo de partição é comparado por
   sha256 com a rodada anterior — como `objetos.guardar_arquivo` (L0-11) já deduplica por conteúdo (a chave É
   o sha256), a partição sem mudança nunca gera PUT novo no Garage; só o sha256/chave mudam para a partição
   que de fato mudou. Não existe tabela extra de "partições anteriores": o próprio `dados.arquivos` do item é
   a fonte da verdade lida a cada rodada.
5. **Modo `arquivar`: conferir antes de apagar, na MESMA transação.** O `DELETE` da tabela de origem só roda
   depois que o Parquet já foi gerado e contado; se `rowcount` do DELETE não bater com a contagem do arquivo,
   a exceção sobe e `app/db.py` reverte a transação inteira (nunca um DELETE parcial). `plat.
   geoparquet_arquivar_confirmar` (SECURITY DEFINER) só registra o número confirmado — nunca decide.
6. **Nenhum privilégio novo.** `conteudo.exportar` (mesmo do L0-04-h) para gerar; `conteudo.apagar_tudo`
   (já existe, administrativo) OBRIGATÓRIO ADEMAIS para `modo=arquivar`, porque apaga linha de origem.
7. **Leitura por URL assinada reusa o contrato existente.** `GET /api/geoparquet/{item}/arquivos` só assina
   (`objetos.url_assinada`, `/api/objetos/{chave}` — ADR 0004 seção 11.2); não existe rota nova de entrega.
   O contrato de assinatura vencida é **404**, não 403 (mesmo de `test_miniatura.py`) — este item não inventa
   um código de erro próprio só para bater com o texto do portão.

## Achado que ficou de fora do código (registrado para o gerente)

Durante o teste deste item, um job `pesado` ficou **pendente por > 7 minutos** porque outra trilha
(`trilha-il701cdadod`) mantinha o advisory lock global `plat.job.pesado` mesmo com 0 job em execução
(`pg_stat_activity` mostrava esse worker `idle`). Lendo `app/jobs/worker.py::_pegar()`: a variável local
`pesado_ok` só é recalculada quando `self.lock_pesado` ainda é `False`; num tick em que o worker JÁ possui o
lock (`self.lock_pesado = True` de um tick anterior) e não há job pesado pendente para ele, `pesado_ok` fica
`False` por inicialização e a linha `if pesado_ok: self._soltar_pesado()` nunca dispara — o lock fica preso
até o processo do worker morrer. Isso trava TODO job pesado da frota (exportação, ingestão, geoparquet) atrás
de um único worker ocioso. Não foi corrigido aqui (`app/jobs/worker.py` é arquivo que a árvore principal
também mexe, fora do escopo deste item) — reportado no handoff para o gerente decidir quem conserta.

## Fontes

- `github.com/opengeospatial/geoparquet` (format-specs/schema.json, tag v1.1.0) — vendorizado.
- `duckdb.org/docs/stable/core_extensions/spatial/overview` — `COPY ... PARTITION_BY`, `ST_Extent`/min-max.
- Reuso de ADR 0018 (L0-04-h-exportar) e ADR 0006 (L0-11-arquivos-objetos).
