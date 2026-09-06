# ADR 0018 — Arquivo por URL pública: converter e reusar a ingestão, nunca um segundo pipeline

Data: setembro de 2026 · Item: `L6-02-h-csv-url-geojson-kml` · Estado: aceito

## Contexto

O Map Viewer 11.4 da Esri aceita CSV, KML, GeoRSS e GeoJSON por endereço web. A plataforma já tinha as duas
metades separadas: o modelo de conexão externa com defesa de SSRF (item L6-02-a, ADR 0012) e a ingestão
vetorial completa a partir de arquivo enviado (item L0-04, ADR 0005), que já lê CSV e GeoJSON, negocia CRS,
codificação, tipo de geometria e validade, e cria a tabela PostGIS com RLS.

## Decisão

1. **Um conversor, não um pipeline.** KML, KMZ, GeoRSS e GPX viram GeoJSON com `ogr2ogr` e entram no pipeline
   do L0-04 pela porta da frente (`plat.importacao` -> `ingestao.inspecionar` -> `ingestao.carregar`). CSV e
   GeoJSON entram direto. Nenhuma linha da ingestão foi copiada; as funções são CHAMADAS com o mesmo `ctx` do
   job. O ganho é que CRS, validade, cota, RLS, estatísticas e proveniência continuam num lugar só.

2. **A rede é sempre `buscar_seguro`.** Este é o primeiro item que busca URL de terceiro em volume. Ele não
   abre socket próprio: usa o cliente pinado do L6-02-a, com o teto de bytes e o timeout declarados em
   `app/limites.py`. Endereço interno, nome de DNS que resolve para faixa interna e redirecionamento para
   endereço interno são recusados lá, e cada um tem teste próprio neste item também — a defesa não vale só
   onde foi escrita, vale onde é usada.

3. **Credencial não atravessa host.** Achado do adversário do L6-02-a: `Authorization` seguia no
   redirecionamento para qualquer host. Consertado aqui (`_sem_credencial_em_outro_host`), porque este item é
   o primeiro que manda credencial para endereço de terceiro com frequência.

4. **Formato pelos bytes.** Extensão de URL e `Content-Type` são pistas fracas (servidor de arquivo estático
   erra as duas). O formato sai do conteúdo; a extensão nunca decide.

5. **Não recarregar o que não mudou tem duas camadas.** `If-None-Match`/`If-Modified-Since` a partir do que
   foi guardado (o servidor responde 304) e, quando o servidor ignora o condicional, o `sha256` do corpo. Os
   contadores `sincronizacoes` e `recargas` de `plat.conexao_arquivo` são a evidência auditável da diferença
   entre conferir e recarregar — sem eles a cláusula do portão não teria como ser provada.

6. **O job é `somente_sistema`.** Um tipo de job que recebe uma URL e faz a plataforma buscá-la não pode
   nascer de `POST /api/jobs` com parâmetro livre. Ele nasce da rota `POST /api/conexoes/{id}/arquivo/
   sincronizar` (que confere inquilino e privilégio antes) ou do periódico. É o mesmo padrão do convite por
   e-mail descrito em `app/jobs/sistema.py`.

7. **Coordenada fora de faixa recusa, nunca corrige.** CSV com a coluna de latitude fora de -90..90 é
   recusado com a mensagem dizendo que as colunas parecem trocadas. Trocar sozinho inventaria um dado que
   ninguém pediu. O limite disso está escrito: quando a troca deixa os dois valores dentro de -90..90 não há
   sinal no dado, e o arquivo passa.

## Consequências

- Formato novo por URL custa um par `(detector de bytes, driver GDAL)` em `app/conexao/arquivo_url.py`, não um
  conector inteiro.
- O teto dos formatos XML (40 MiB) é menor que o geral (64 MiB) por uma razão medida, não por gosto: o driver
  KML/GPX/GeoRSS do GDAL lê o documento inteiro na memória (200 mil pontos = 35,5 MB de arquivo = 417 MiB de
  RSS, GDAL 3.8.4 nesta máquina).
- Sincronização automática nunca pergunta nada: se a inspeção deixar uma pergunta que a proposta não responde
  sozinha (CRS sem sugestão, por exemplo), o job falha dizendo isso, em vez de chutar.
- CSV sem coluna de coordenada continua virando tabela sem geometria. Geocodificar endereço depende do
  item L2-11 estar ligado ao fluxo de ingestão e ficou de fora, declarado em `docs/PARIDADE.md`.
