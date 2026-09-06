-- 040_acervo_endpoint: endpoints testados por HTTP de cada fonte do acervo (item L6-01-d-ficha-fonte).
-- A ficha (plat.acervo_ficha, migração 021, ENTREGUE) já tinha os 10 campos de procedência da hipótese do item
-- (url, licença, frescor, data_dado, script_gerador, sha256, método, confiança, limites, próxima_verificação) —
-- conferido por leitura antes de escrever qualquer código (docs/adr/0012, app/acervo/rotas.py::ver). O que
-- faltava era só "endpoints confirmados e vivos", que a casa já mede em `acervo.endpoint` (minera2.py/confirma.py/
-- procedencia2.py, citados no CLAUDE.md: "779 endpoints, 442 confirmados, 345 confirmados e vivos") mas que a
-- API nunca expunha. Esta migração GRANTa leitura de `acervo.endpoint` e cria uma view fina sobre ela, com a
-- MESMA regra D17 da ficha (só endpoint de fonte com licença ESCRITA aparece — nunca um vazamento de metadado
-- de fonte sem licença por uma porta lateral).
--
-- "vivo" replica a definição já usada pela própria casa para "confirmado e vivo": `confirmado = true AND
-- http = '200'` (não "2xx" — medido em 06/09/2026 que a casa só grava o código exato '200' para sucesso; outros
-- 2xx como '202' aparecem à parte e não entram na definição de "vivo" até a casa decidir alargar).
--
-- Numeração 040 (033 = ingestao_funcoes_privilegios; 034-039 tomados por outras trilhas do mesmo turno, checado ao vivo antes de escrever). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

GRANT SELECT ON acervo.endpoint TO plat_app;

CREATE OR REPLACE VIEW plat.acervo_endpoint WITH (security_invoker = true) AS
SELECT
  e.fonte_id,
  e.url,
  e.origem,
  e.http,
  e.content_type,
  e.bytes,
  e.ms,
  e.testado_em,
  e.confirmado,
  (coalesce(e.confirmado, false) AND e.http = '200') AS vivo
FROM acervo.endpoint e
JOIN acervo.fonte f ON f.fonte_id = e.fonte_id
WHERE f.licenca IS NOT NULL AND btrim(f.licenca) <> '';

REVOKE ALL ON plat.acervo_endpoint FROM PUBLIC;
GRANT SELECT ON plat.acervo_endpoint TO plat_app;
