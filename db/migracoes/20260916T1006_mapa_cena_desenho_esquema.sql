-- 20260916T1006_mapa_cena_desenho_esquema: item L2-01-k-desenho-anotacoes. A camada de desenho do mapa
-- (`corpo.desenho`, GeoJSON + estilo, sem tabela própria) tinha rota, tabela de anotação e motor de
-- "promover a camada" prontos (app/mapa/anotacoes.py, app/mapa/promover.py, ambos registrados em app/main.py),
-- mas a propriedade `desenho` NUNCA foi acrescentada ao esquema JSON de `mapa`/`cena` em migração nenhuma
-- (varredura em todo o histórico do repositório: nenhum commit toca `properties,corpo,properties,desenho`).
-- Como `corpo.additionalProperties = false` nos dois tipos, todo POST/PUT com `corpo.desenho` sempre foi 422
-- `dados_invalidos` — a rota de promover nunca teve como ser exercida por um documento gravado pela API.
--
-- MEDIDO 16/09/2026 (tests/api/catalogo/test_desenho_anotacoes.py, todos os 15 casos).
--
-- A FORMA aqui é deliberadamente permissiva (GeoJSON + estilo como objeto livre): o par tipo_desenho×geometria,
-- o teto de feições/caracteres, a faixa de estilo e o "círculo no polo" são validados em Python
-- (`app/catalogo/documento.py::erros_de_desenho`, restaurado nesta mesma rodada — também nunca chegou a esta
-- árvore), porque dependem de olhar a LISTA inteira e o PAR de campos, o que JSON Schema simples não expressa
-- sem `$data`. Aditivo por `jsonb_set`; não muda `esquema_versao` (chave nova e opcional, documento antigo sem
-- `desenho` continua válido). Idempotente; sem BEGIN/COMMIT.
UPDATE plat.tipo_item
SET esquema = jsonb_set(
  esquema, '{properties,corpo,properties,desenho}',
  '{"type":"object","additionalProperties":false,
    "properties":{
      "features":{"type":"array","maxItems":5000,
        "items":{"type":"object","required":["type","id","geometry","properties"],
          "properties":{
            "type":{"const":"Feature"},
            "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
            "geometry":{"type":"object","required":["type","coordinates"],
              "properties":{
                "type":{"type":"string","enum":["Point","LineString","Polygon"]},
                "coordinates":{}
              }},
            "properties":{"type":"object","additionalProperties":true,
              "required":["tipo_desenho"],
              "properties":{"tipo_desenho":{"type":"string","maxLength":20}}}
          }}}
    }}'::jsonb,
  true)
WHERE nome IN ('mapa', 'cena');

DO $$
DECLARE faltando text[];
BEGIN
  SELECT array_agg(nome) INTO faltando
    FROM plat.tipo_item
   WHERE nome IN ('mapa', 'cena') AND esquema #> '{properties,corpo,properties,desenho}' IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'esquema sem corpo.desenho: %', faltando;
  END IF;
END $$;
