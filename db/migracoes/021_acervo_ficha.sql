-- 021_acervo_ficha: ficha de procedência do acervo da casa como view só-leitura (item L6-01-a-procedencia-acervo;
-- decisões B1/B3/B5 de laco/decomposicao/L3L6_CONCEITO.md). `acervo.*` é escrito só pelos scripts da casa
-- (registro.py/contagem2.py/frescor.py); a plataforma nunca grava lá — esta migração só GRANTa leitura e cria a view.
--
-- Diferença explícita do L6-01-b (view por camada de DADO, RLS por assinatura do inquilino, sem GRANT direto na
-- tabela original): aqui é metadado de FONTE, 376 linhas, sem geometria, sem coluna identificável de pessoa — GRANT
-- direto de SELECT em acervo.fonte/acervo.v_completude a plat_app é aceitável nesta escala (nada de GRANT à role
-- PUBLIC; só plat_app lê). Regra D17: só fonte com licença ESCRITA aparece na ficha
-- (acervo.fonte.licenca IS NOT NULL AND btrim(licenca) <> ''); medido 06/09/2026: 68 de 376.
--
-- Numeração 021 (020 = item_contagens_rows). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- ---------------------------------------------------------------- leitura só-leitura do registro do acervo
GRANT USAGE ON SCHEMA acervo TO plat_app;
GRANT SELECT ON acervo.fonte, acervo.v_completude TO plat_app;

-- ---------------------------------------------------------------- ficha (view SECURITY INVOKER)
CREATE OR REPLACE VIEW plat.acervo_ficha WITH (security_invoker = true) AS
SELECT
  f.fonte_id,
  f.nome,
  f.orgao,
  f.dominio,
  f.url,
  f.url_http,
  f.url_conferida_em,
  f.licenca,
  f.frescor,
  f.data_dado,
  f.data_acesso,
  f.script_gerador,
  f.sha256,
  f.sha256_cmd                                                          AS comando_reexecucao,
  f.metodo,
  f.confianca,
  f.limites,
  f.proxima_verificacao,
  f.tabelas                                                             AS numero_tabelas,
  f.linhas_est                                                          AS registros_estimados,
  f.bytes,
  v.campos                                                              AS procedencia_campos,
  v.campos_possiveis                                                    AS procedencia_campos_possiveis,
  round(v.campos::numeric / NULLIF(v.campos_possiveis, 0) * 10, 1)      AS procedencia_pontuacao,
  f.atualizado_em
FROM acervo.fonte f
LEFT JOIN acervo.v_completude v ON v.fonte_id = f.fonte_id
WHERE f.licenca IS NOT NULL AND btrim(f.licenca) <> '';

REVOKE ALL ON plat.acervo_ficha FROM PUBLIC;
GRANT SELECT ON plat.acervo_ficha TO plat_app;

-- ---------------------------------------------------------------- tipo 'conexao': protocolo 'acervo' (esquema_versao 1 → 2)
-- fonte interna do acervo referenciada por dados.parametros.fonte_id (slug de acervo.fonte); nunca copia dado.
-- Mesma regra de UPSERT do ADR 0004 seção 3: o esquema só troca se a versão nova for maior que a gravada.
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona) VALUES
  ('conexao', 'ferramenta', 'Conexão',
   'fonte de dado externa (segredo fica no cofre, nunca em dados) ou fonte do acervo da casa (protocolo "acervo", referenciada por parametros.fonte_id, nunca copiada)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["protocolo","url"],
     "properties":{"protocolo":{"type":"string","enum":["wms","wfs","wmts","ogc_api","esri_rest","postgres_fdw","s3","http","acervo"]},
       "url":{"type":"string","maxLength":2048},"credencial_id":{"type":"string","format":"uuid"},"parametros":{"type":"object"}}}'::jsonb,
   2, 'conexao', '/static/js/catalogo/tipos/conexao.js', '{}', false, 'L0-04-i')
ON CONFLICT (nome) DO UPDATE SET
  descricao      = EXCLUDED.descricao,
  esquema        = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao);
