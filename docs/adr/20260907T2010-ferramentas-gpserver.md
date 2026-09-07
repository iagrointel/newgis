# ADR 20260907T2010 — registro de ferramentas, execução com proveniência e GPServer compatível

Item L2-05-a-catalogo-ferramentas-gpserver. Segue L2_CONCEITO C8 (job por padrão, síncrono só abaixo de um
custo declarado, resultado é item com proveniência), C9 (superfície Esri em `/rest/services`, código HTTP real
com corpo no vocabulário do cliente) e C19 (registro declarativo validado no `make check`).

## Decisões

1. **Manifesto em código, validado na importação.** `@ferramenta(nome, titulo, categoria, versao, parametros,
   custo, limites)` em `app/ferramentas/registro.py`; cada `Parametro` tem tipo do vocabulário GP da Esri
   (GPFeatureRecordSetLayer, GPRasterDataLayer, GPString, GPDouble, GPLong, GPBoolean, GPLinearUnit, GPDate,
   GPMultiValue). Parâmetro sem tipo, tipo fora do vocabulário, saída ausente ou assinatura errada é
   `ErroRegistro` na importação; `tests/unit/test_ferramentas_registro.py` importa o módulo dentro de
   `make teste`, logo `make check` recusa manifesto inválido. A função da ferramenta recebe
   `(ctx, entradas, parametros, destino)` e escreve a tabela de destino; fid/globalid/RLS/índices vêm de
   `plat.camada_preparar`, como na ingestão.
2. **Um executor, dois contextos.** `app/ferramentas/executor.py::executar` roda tanto no worker
   (`@tarefa ferramentas.executar`, `ContextoJob`) quanto no processo da API (`ContextoSincrono`, para o
   `/execute` do GPServer e para a API própria quando o custo estimado fica em ou abaixo de
   `limites.FERRAMENTA_SINCRONO_CUSTO_MAX`). Cancelamento ou falha depois de a tabela existir apaga a tabela.
3. **Proveniência dentro de `dados.procedencia.ferramenta`.** O esquema do tipo `camada_vetorial` é fechado
   (`additionalProperties: false`) e pertence ao L0-04; `procedencia` é o ramo aberto que a ingestão já usa.
   O bloco tem ferramenta, versão, parâmetros normalizados, entradas (uuid + versão do item + sha256 de
   conteúdo), data, autor, job e custo. O sha256 de conteúdo de uma camada é `sha256(string_agg(md5(row(fid,
   campos…, ST_AsBinary(geom))) ORDER BY fid))` — exclui colunas de sistema para que rerodar dê o mesmo hash.
   A ficha do item (`web/js/catalogo/item.js`) mostra o bloco na linha "proveniência".
4. **Relação `derivado_de`** (migração `20260907T2005_ferramentas.sql`), resultado → entrada, sem arrastar dono
   nem apagar junto; evento `analises/executar` no item de resultado.
5. **Histórico = fila.** `GET /api/jobs?tipo=ferramentas.executar` é o histórico por usuário (filtro de dono do
   L0-05) e `POST /api/jobs/{id}/repetir` é o rerodar; nenhuma tabela nova.
6. **GPServer por ferramenta** em `/rest/services/<ferramenta>/GPServer/<ferramenta>` (descritores públicos;
   execute, submitJob, jobs/{id}, results/{param}, cancel com `token=` por querystring/form, mesmo padrão do
   GeocodeServer); `jobId` = uuid do job da fila; estados mapeados para `esriJobSubmitted/Executing/Succeeded/
   Failed/Cancelled`; erro com código HTTP real e `{error:{code,message,details}}`.

## Fora deste item
Entrada por seleção salva, desenho ou camada temporária (L2-01-h/L2-01-k, na fila), entrada raster (L1-01),
FeatureSet inline no GPServer, ArcGIS Pro real (D20), demais ferramentas (itens irmãos do L2-05).
