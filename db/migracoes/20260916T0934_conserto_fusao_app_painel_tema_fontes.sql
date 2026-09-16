-- 20260916T0934_conserto_fusao_app_painel_tema_fontes: três migrações irmãs — 20260907T1505_vista_movel.sql,
-- 20260908T1040_app_fontes_vistas_mensagens.sql e 20260908T1709_temas_marca.sql — escreveram
-- plat.tipo_item.esquema de 'app' com a MESMA guarda `WHERE nome = 'app' AND esquema_versao < 3`, cada uma
-- SUBSTITUINDO o esquema inteiro em vez de somar ao que as outras trariam. A fusão aplicou as três em
-- sequência (por carimbo de tempo) e só a PRIMEIRA a rodar venceu — as outras duas viraram no-op silencioso
-- porque a guarda já via esquema_versao = 3. Para 'painel' o mesmo aconteceu com um quarto escritor,
-- 20260906T2145_documento_painel.sql, que grava esquema_versao = 3 SEM checar versão (nem sequer `< 3`) e por
-- isso venceu antes de vista_movel ou temas_marca rodarem.
--
-- MEDIDO 16/09/2026 (laço f2fixcatalogo; tests/api/catalogo/test_app_modelo.py,
-- test_documento_tema.py, test_documento.py::test_migracao_de_esquema_na_leitura_com_evento):
--   - 'app' ficou com o esquema de vista_movel (nos/ligacoes/mapas/mapa_id/vista_movel); faltam
--     `fontes`/`vistas`/`mensagens` (L5-07) e a chave `tema` (L5-10) inteira.
--   - 'painel' ficou com o esquema rico de 20260906T2145 (elementos/grade/fontes/filtros/semente/
--     parametros_url/mensagens — todos específicos do construtor de painel, NADA disso mexe aqui), mas com
--     `tema` no formato PLACEHOLDER pré-L5-10 (`{"modo":"claro"|"escuro"}`, comentário do próprio arquivo:
--     "até o L5-10 existir") e sem `vista_movel` nenhum.
--
-- Conserto ADITIVO por `jsonb_set` (nunca substitui o esquema inteiro — é exatamente a causa do defeito):
--   'app'    ganha `fontes`/`vistas`/`mensagens` (forma de 20260908T1040) e `tema` (forma de 20260908T1709).
--   'painel' ganha `vista_movel` (forma de 20260907T1505) e `tema` novo (substitui o placeholder — nenhum
--            documento em uso grava `corpo.tema` no formato antigo, então não há dado para migrar).
--
-- `app/catalogo/documento.py` (`validar_grafo`, `_migrar_app_v2_v3`, `_migrar_painel_v2_v3`) recebeu o mesmo
-- conserto aditivo nesta rodada: as três funções homônimas de cada commit também se sobrescreviam par a par no
-- registro `_MIGRACOES`, e ficava só a última.
--
-- Idempotente (jsonb_set com o mesmo valor não muda nada); sem BEGIN/COMMIT. `esquema_versao` continua 3: os
-- testes fixam a versão 3 no corpo do pedido, e isto é o conserto de uma perda de fusão dentro da versão que
-- já existia, não uma versão nova.

-- ---------------------------------------------------------------- 'app': fontes/vistas/mensagens (L5-07)
UPDATE plat.tipo_item
SET esquema = jsonb_set(
  jsonb_set(
    jsonb_set(
      esquema,
      '{properties,corpo,properties,fontes}',
      '{"type":"array","maxItems":50,
        "items":{"type":"object","required":["id","origem","campos"],
          "properties":{
            "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
            "nome":{"type":"string","maxLength":120},
            "origem":{"type":"object","required":["tipo"],
              "properties":{"tipo":{"type":"string","enum":["item","url","embutida"]},
                "item_id":{"type":"string","maxLength":64},"url":{"type":"string","maxLength":2000},
                "feicoes":{"type":"array","maxItems":20000}}},
            "campos":{"type":"array","maxItems":500,
              "items":{"type":"object","required":["nome","tipo"],
                "properties":{"nome":{"type":"string","minLength":1,"maxLength":120},
                  "tipo":{"type":"string","enum":["texto","inteiro","decimal","booleano","data","data_hora","geometria"]},
                  "rotulo":{"type":"string","maxLength":120}}}}
          }}}'::jsonb,
      true),
    '{properties,corpo,properties,vistas}',
    '{"type":"array","maxItems":200,
      "items":{"type":"object","required":["id","fonte"],
        "properties":{
          "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
          "nome":{"type":"string","maxLength":120},
          "fonte":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
          "filtro":{"type":["object","null"]},
          "selecao":{"type":"array","maxItems":10000},
          "ordenacao":{"type":"array","maxItems":10,"items":{"type":"object","required":["campo"],
            "properties":{"campo":{"type":"string","maxLength":120},"direcao":{"type":"string","enum":["asc","desc"]}}}},
          "campos":{"type":["array","null"],"maxItems":500,"items":{"type":"string","maxLength":120}}
        }}}'::jsonb,
    true),
  '{properties,corpo,properties,mensagens}',
  '{"type":"array","maxItems":500,
    "items":{"type":"object","required":["id","gatilho","acoes"],
      "properties":{
        "id":{"type":"string","pattern":"^[0-7][0-9A-HJKMNP-TV-Z]{25}$"},
        "gatilho":{"type":"object","required":["origem","evento"],
          "properties":{"origem":{"type":"string","maxLength":26},
            "evento":{"type":"string","enum":["clique","dado_adicionado","filtro_mudou","extensao_mudou","localizacao","registros_carregados","selecao_mudou","vista_mudou"]}}},
        "acoes":{"type":"array","minItems":1,"maxItems":20,
          "items":{"type":"object","required":["alvo","acao"],
            "properties":{"alvo":{"type":"string","maxLength":26},
              "acao":{"type":"string","enum":["filtrar","selecionar","limpar_filtro","limpar_selecao","zoom","pan","piscar","popup","abrir","fechar","definir_parametro"]},
              "parametros":{"type":"object"},
              "relacao":{"type":["object","null"],
                "properties":{"tipo":{"type":"string","enum":["mesma_fonte","atributo","espacial"]},
                  "campo_origem":{"type":"string","maxLength":120},"campo_alvo":{"type":"string","maxLength":120},
                  "operador":{"type":"string","enum":["=","in"]}}}}}}
      }}}'::jsonb,
  true)
WHERE nome = 'app';

-- ---------------------------------------------------------------- 'app'/'painel': tema de verdade (L5-10)
UPDATE plat.tipo_item
SET esquema = jsonb_set(
  esquema, '{properties,corpo,properties,tema}',
  '{"oneOf":[
      {"type":"object","additionalProperties":false,"required":["id"],
       "properties":{"id":{"type":"string","minLength":1,"maxLength":60}}},
      {"type":"object","additionalProperties":false,"required":["definicao"],
       "properties":{"definicao":{"type":"object"}}}
    ]}'::jsonb,
  true)
WHERE nome IN ('app', 'painel');

-- ---------------------------------------------------------------- 'painel': vista móvel (L5-15)
UPDATE plat.tipo_item
SET esquema = jsonb_set(
  esquema, '{properties,corpo,properties,vista_movel}',
  '{"type":"object","additionalProperties":false,
    "properties":{
      "manual":{"type":"boolean"},
      "nos":{"type":"object",
        "additionalProperties":{"type":"object","additionalProperties":false,
          "properties":{
            "oculto":{"type":"boolean"},
            "ordem":{"type":"integer","minimum":0,"maximum":100000},
            "largura_colunas":{"type":"integer","minimum":1,"maximum":12}
          }}}
    }}'::jsonb,
  true)
WHERE nome = 'painel';

DO $$
DECLARE app_props jsonb; painel_props jsonb;
BEGIN
  SELECT esquema #> '{properties,corpo,properties}' INTO app_props FROM plat.tipo_item WHERE nome = 'app';
  IF NOT (app_props ? 'fontes' AND app_props ? 'vistas' AND app_props ? 'mensagens'
          AND app_props ? 'tema' AND app_props ? 'vista_movel') THEN
    RAISE EXCEPTION 'esquema de app não ganhou fontes/vistas/mensagens/tema/vista_movel: %', app_props;
  END IF;
  SELECT esquema #> '{properties,corpo,properties}' INTO painel_props FROM plat.tipo_item WHERE nome = 'painel';
  IF NOT (painel_props ? 'vista_movel' AND painel_props -> 'tema' ? 'oneOf') THEN
    RAISE EXCEPTION 'esquema de painel não ganhou vista_movel/tema novo: %', painel_props;
  END IF;
END $$;
