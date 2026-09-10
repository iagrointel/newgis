# Traçado de custo mínimo: rota síncrona com teto de células (item L3-10-corredor-custo-minimo)

Data: 08/09/2026. Estado: aceito. Par: ADR `20260906T1640-grades-aninhadas-multiescala.md` (a grade e a execução
que este traçado lê); ADR `0003-fila-de-jobs.md` (o mecanismo que se decidiu NÃO usar aqui).

## Contexto

O motor de traçado (`app/amc/corredor.py`) é síncrono por natureza: sobre o teto de células da grade do motor
multicritério (`ESCALA_CELULAS_MAX`, 250 mil), o caminho de custo mínimo e o corredor-epsilon levam MENOS de um
segundo (medido: a rota responde em 8 ms sobre uma grade de 120 células, e o próprio teto de 250 mil células é
33× menor que a grade de referência de 9,5 milhões traçada em 5,8 s com janela — `tests/medidas/L3-10-corredor-custo-minimo.json`).
A pergunta de desenho era expor isso como rota HTTP direta ou como job da fila.

## Decisão

1. **Rota SÍNCRONA (`POST /api/multiescala/execucoes/{id}/corredor`), não job.** A fila de jobs existe para
   trabalho que passa do ciclo de resposta; este não passa. O que a resposta traz é a DURAÇÃO MEDIDA
   (`duracao_ms`), não uma promessa de prazo. O teto de células já vem da grade da execução, e a rota recusa
   com `grade_grande_demais` o que passar de `ESCALA_CELULAS_MAX` — defesa em profundidade, porque a grade
   acima do teto não se cria pelas rotas do multicritério.
2. **Ponto de origem ou destino em cima de veto é erro 422 que diz QUAL dos dois pontos; o ponto do usuário
   NUNCA é movido.** "Aproximar para a célula livre mais perto" entregaria um traçado que ninguém pediu e é
   exatamente a refutação do item (adversário põe A ou B dentro de veto). Ponto fora da área é 422
   (`ponto_fora_da_area`), pela mesma razão.
3. **A geometria do corredor tem teto próprio (`CORREDOR_CELULAS_GEOJSON_MAX`, 20 mil células).** O cálculo
   escala com a grade; o que derruba a resposta é a UNIÃO PostGIS das células e o corpo GeoJSON dela. Acima do
   teto a resposta traz a contagem (`corredor_celulas`) e `corredor_geometria_omitida: true`, e a linha (sempre
   pequena) vai inteira. O teto de células da grade e o teto de geometria são coisas diferentes de propósito.
4. **O traçado não cria tabela; o que fica gravado é o EVENTO** (`multiescala/corredor`, migração
   `20260908T1450_corredor_evento.sql`) com os parâmetros declarados e as medidas — é o rastro que repete a
   corrida com o mesmo resultado. Guardar linha e corredor como camada é o item de resultado-como-camada.

## Consequências

- Quem traça sobre uma execução grande espera menos de um segundo e recebe tudo na resposta; não há consulta
  de status nem fila para monitorar.
- O limite real de tamanho de estudo é o da grade do multicritério, não um limite novo deste item (uma
  constante a mais em `app/limites.py`, documentada em `docs/LIMITES.md` gerado).
- A conferência do motor contra o trecho de referência da casa fica em `scripts/corredor_referencia.py`
  (superfície bit a bit, Hausdorff ≤ 100 m, 382 km em ≤ 10 s) e no teste lento que o exercita
  (`tests/unit/test_corredor_referencia.py`) — fora do caminho do serviço.
