-- 20260906T2136_conexao_google_sheets: Google Sheets como tipo de conexão (item L6-02-i-google-sheets).
--
-- Duas mudanças, as duas de vocabulário fechado (mesma regra da 030: `app/limites.py` CONEXAO_TIPOS e este
-- CHECK mudam juntos; mesma regra da 036: o enum de `protocolo` do tipo_item 'conexao' acompanha o CHECK):
--
-- 1. `plat.conexao.tipo` aceita 'google_sheets'. A conexão desse tipo guarda a URL CANÔNICA de exportação
--    CSV da planilha (normalizada na entrada por `app/conexao/rotas.py`) e, quando a planilha é privada, o
--    JSON da conta de serviço em `credencial_cifrada` (mesma cifra `encconexao:v1:` do L6-02-a — nada de
--    coluna nova: credencial é credencial, e o padrão da casa é cifrar em Python antes do INSERT).
--
-- 2. tipo_item 'conexao' sobe para o esquema v4 com 'google_sheets' no enum de `protocolo`, senão
--    `POST /api/conexoes/{id}/publicar` reprovaria na validação do esquema ao publicar a camada.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- depende: 036_conexao_saude_e_camada.sql

ALTER TABLE plat.conexao DROP CONSTRAINT IF EXISTS conexao_tipo_check;
ALTER TABLE plat.conexao ADD CONSTRAINT conexao_tipo_check
  CHECK (tipo IN (
    'wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles',
    'postgres_fdw', 's3', 'http', 'google_sheets'
  ));

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona) VALUES
  ('conexao', 'ferramenta', 'Conexão',
   'fonte de dado externa (segredo fica no cofre, nunca em dados) ou fonte do acervo da casa (protocolo "acervo", '
   'referenciada por parametros.fonte_id, nunca copiada); camada publicada a partir de uma plat.conexao '
   '(parametros.conexao_id) carrega bloco de procedência lido do serviço, nunca um valor padrão (item '
   'L6-05-proveniencia-camada-externa); protocolo "google_sheets" (item L6-02-i) é a URL de exportação CSV '
   'da planilha, pública ou lida com conta de serviço',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["protocolo","url"],
     "properties":{"protocolo":{"type":"string","enum":["wms","wmts","wfs","ogc_api","esri_rest","stac","geoparquet","pmtiles","postgres_fdw","s3","http","google_sheets","acervo"]},
       "url":{"type":"string","maxLength":2048},"credencial_id":{"type":"string","format":"uuid"},"parametros":{"type":"object"},
       "procedencia":{"type":"object","additionalProperties":true}}}'::jsonb,
   4, 'conexao', '/static/js/catalogo/tipos/conexao.js', '{}', false, 'L0-04-i')
ON CONFLICT (nome) DO UPDATE SET
  descricao      = EXCLUDED.descricao,
  esquema        = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);
