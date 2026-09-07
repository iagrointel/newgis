-- 20260907T1649_mapa_base: item L2-01-e-mapas-base — galeria de mapas base por inquilino.
--
-- Registra o tipo de item `mapa_base` (família 'mapa', mesma família de 'mapa'/'cena' — 011_catalogo.sql).
-- Cada mapa base é um item comum do catálogo (POST /api/itens já existente, sem rota nova de criação):
-- atribuição/licença de fonte usam os campos genéricos `creditos`/`termos_de_uso` do item; o resto
-- (tipo de fonte, estilo, URL do tile, faixa de zoom, ordem na galeria, se é o padrão do inquilino) vai em
-- `dados`, validado pelo esquema abaixo (Draft 2020-12, if/then/else por `dados.tipo` — nenhuma validação
-- extra em Python é necessária: JSON Schema já é o "recurso nativo" mais simples que resolve, escada do
-- Ponytail degrau 4).
--
-- Quatro fontes abertas de instalação (app/mapas_base/semear.py monta os dados; aqui só o contrato):
--   pmtiles            — PMTiles local servido por Range HTTP pelo próprio nginx (sem serviço dinâmico),
--                        url tem de casar com o caminho publicado em web/dados/basemap/*.pmtiles.
--   osm_raster_proxy   — raster ladrilho a ladrilho, sempre pelo NOSSO proxy com cache em disco e
--                        identificação (política de uso do tile.openstreetmap.org); a url É o próprio
--                        caminho do proxy — o esquema recusa qualquer outro valor, então não existe URL de
--                        terceiro para validar aqui (a defesa contra SSRF mora no proxy, que nunca lê o
--                        host de um parâmetro de requisição — app/mapas_base/proxy_osm.py).
--   satelite_titiler   — mosaico Sentinel-2 da casa servido por um TiTiler (item L1-02), URL com os três
--                        marcadores {z}/{x}/{y}; é o navegador que busca o tile direto (sem proxy nosso:
--                        não é segredo, não é dado de outro inquilino).
--   nenhum             — fundo cor sólida, sem fonte externa; único tipo sem url/licença obrigatórias.
--
-- Um só mapa base "padrão" por inquilino: índice único parcial sobre `dados->>'padrao'` (guarda de última
-- linha; a operação normal troca o padrão em transação única — app/mapas_base/rotas.py `tornar_padrao` —,
-- nunca dependendo desta violação). Idempotente. Sem BEGIN/COMMIT (ADR 0014).

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona) VALUES
  ('mapa_base', 'mapa', 'Mapa base',
   'mapa base da galeria do inquilino (PMTiles local, proxy raster do OSM, satélite via TiTiler ou fundo sem fonte)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["tipo","ordem"],
     "properties":{
       "tipo":{"type":"string","enum":["pmtiles","osm_raster_proxy","satelite_titiler","nenhum"]},
       "estilo":{"type":"string","enum":["claro","escuro","cinza"]},
       "url":{"type":"string","maxLength":2048},
       "zoom_min":{"type":"integer","minimum":0,"maximum":22},
       "zoom_max":{"type":"integer","minimum":0,"maximum":22},
       "ordem":{"type":"integer","minimum":0,"maximum":1000},
       "padrao":{"type":"boolean"}},
     "allOf":[
       {"if":{"properties":{"tipo":{"const":"nenhum"}}},"then":{},
        "else":{"required":["url","zoom_min","zoom_max"]}},
       {"if":{"properties":{"tipo":{"const":"pmtiles"}}},
        "then":{"properties":{"url":{"type":"string","pattern":"^/static/dados/basemap/[a-z0-9_-]+\\.pmtiles$"}}}},
       {"if":{"properties":{"tipo":{"const":"osm_raster_proxy"}}},
        "then":{"properties":{"url":{"const":"/api/mapas-base/osm/{z}/{x}/{y}.png"}}}},
       {"if":{"properties":{"tipo":{"const":"satelite_titiler"}}},
        "then":{"properties":{"url":{"type":"string","pattern":"^https?://.*\\{z\\}.*\\{x\\}.*\\{y\\}.*$"}}}}
     ]}'::jsonb,
   1, 'mapa_base', '/static/js/catalogo/tipos/mapa_base.js', '{mapa}', false, 'L2-01-e')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo, descricao = EXCLUDED.descricao,
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;

-- guarda de última linha: no máximo um `mapa_base` com dados.padrao=true por inquilino. A troca normal de
-- padrão (app/mapas_base/rotas.py) já limpa o antigo antes de gravar o novo na MESMA transação; isto só
-- pega a corrida entre duas requisições concorrentes (vira 409 "conflito" por app/auth/comum.erro_do_banco,
-- que já trata UniqueViolation genérica — nenhum código novo precisou entender este índice).
CREATE UNIQUE INDEX IF NOT EXISTS ux_item_mapa_base_padrao ON plat.item(tenant_id)
  WHERE tipo = 'mapa_base' AND apagado_em IS NULL AND ((dados->>'padrao')::boolean IS TRUE);
