-- procedencia_item (item L0-09-a-procedencia): bloco de procedência de todo item de dado, com a MESMA régua
-- do registro do acervo da casa (acervo.fonte + acervo.v_completude, 376 fontes) e do catálogo de camadas do
-- motor logístico. O bloco continua morando em plat.item.dados->'procedencia' (jsonb) — não há coluna nova:
-- a ingestão (app/ingestao/carregar.py), a publicação de conexão externa (app/conexao/proveniencia.py) e o
-- exportador de metadado ISO 19139 (app/catalogo/metadado.py) já falam esse formato desde o ADR 0005 6.3.
--
-- O que esta migração acrescenta:
--  1. funções IMMUTABLE que leem o bloco em SQL, para a BUSCA e o FILTRO poderem trabalhar sem trazer o jsonb
--     para o Python (plat.procedencia_licenca / plat.procedencia_campos / plat.procedencia_pontuacao);
--  2. índice funcional pela pontuação (filtro "procedência >= n" na lista do catálogo);
--  3. a propriedade `procedencia` nos esquemas dos tipos de item que carregam DADO e ainda não a tinham
--     (raster, arquivo, vista_de_camada, cena) — sem ela, `additionalProperties: false` recusava o bloco.
--
-- Pontuação: `round(campos / campos_possiveis * 10, 1)` sobre os MESMOS 10 campos de acervo.v_completude
-- (url, licenca, frescor, data_dado, script_gerador, sha256, metodo, confianca, limites, proxima_verificacao),
-- aqui com o nome canônico do catálogo (data_do_dado, gerador) e o nome do acervo aceito como apelido.
-- Item sem bloco tem pontuação NULL, nunca 0,0: ausência de registro não é medida de zero (mesma escolha do
-- acervo). Texto vazio conta como ausente — regra D17, "procedência errada é pior que procedência nenhuma":
-- licenca = '' nunca pode passar por licença registrada.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres. Nome com carimbo de tempo UTC (ADR 0014).

-- ---------------------------------------------------------------- leitura do bloco
CREATE OR REPLACE FUNCTION plat.procedencia_bloco(p_dados jsonb)
RETURNS jsonb LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE
    WHEN jsonb_typeof(p_dados -> 'procedencia') = 'object' AND p_dados -> 'procedencia' <> '{}'::jsonb
    THEN p_dados -> 'procedencia'
  END;
$$;

-- valor de um campo do bloco como texto útil: string vazia/branca = NULL; lista de avisos (limites) vira o
-- texto dos avisos com conteúdo, e lista vazia = NULL; null do JSON = NULL.
CREATE OR REPLACE FUNCTION plat.procedencia_valor(p_valor jsonb)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE jsonb_typeof(p_valor)
    WHEN 'null'   THEN NULL
    WHEN 'string' THEN nullif(btrim(p_valor #>> '{}'), '')
    WHEN 'array'  THEN (SELECT nullif(btrim(string_agg(x, ' | ')), '')
                          FROM (SELECT nullif(btrim(e #>> '{}'), '') AS x
                                  FROM jsonb_array_elements(p_valor) e) s
                         WHERE x IS NOT NULL)
    WHEN 'object' THEN nullif(p_valor::text, '{}')
    ELSE nullif(btrim(p_valor #>> '{}'), '')
  END;
$$;

-- campo canônico com apelido do acervo como segunda chance (data_dado, script_gerador, fonte_url, sha256_cmd)
CREATE OR REPLACE FUNCTION plat.procedencia_campo(p_bloco jsonb, p_campo text, p_apelido text DEFAULT NULL)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT coalesce(
    plat.procedencia_valor(p_bloco -> p_campo),
    CASE WHEN p_apelido IS NULL THEN NULL ELSE plat.procedencia_valor(p_bloco -> p_apelido) END);
$$;

-- `limites` é o único campo que pode vir como LISTA de avisos; lista sem aviso com conteúdo = ausente
CREATE OR REPLACE FUNCTION plat.procedencia_limites(p_bloco jsonb)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN jsonb_typeof(p_bloco -> 'limites') = 'array'
    THEN (SELECT nullif(btrim(string_agg(x, ' | ')), '')
            FROM (SELECT nullif(btrim(e #>> '{}'), '') AS x
                    FROM jsonb_array_elements(p_bloco -> 'limites') e) s
           WHERE x IS NOT NULL)
    ELSE nullif(btrim(p_bloco ->> 'limites'), '') END;
$$;

CREATE OR REPLACE FUNCTION plat.procedencia_licenca(p_dados jsonb)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT nullif(btrim(plat.procedencia_bloco(p_dados) ->> 'licenca'), '');
$$;

-- Os 10 campos de acervo.v_completude, na mesma ordem, em UMA expressão. Escrito sem encadear
-- `procedencia_campo` de propósito: a versão encadeada custava ~40 chamadas de função por linha e levou a lista
-- de 50 itens do corpus de 10 mil de 1,9 ms para 288 ms (medido com tests/api/catalogo/test_busca.py::
-- test_lista_por_tipo_p95, cujo portão é 100 ms). `->>` já devolve NULL para o `null` do JSON; o btrim+nullif
-- aplica a regra "vazio é ausente".
CREATE OR REPLACE FUNCTION plat.procedencia_campos(p_dados jsonb)
RETURNS int LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN b IS NULL THEN 0 ELSE
      (CASE WHEN nullif(btrim(coalesce(b ->> 'url', b ->> 'fonte_url')), '')      IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(b ->> 'licenca'), '')                              IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(b ->> 'frescor'), '')                              IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(coalesce(b ->> 'data_do_dado', b ->> 'data_dado')), '')
                                                                                 IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(coalesce(b ->> 'gerador', b ->> 'script_gerador')), '')
                                                                                 IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(b ->> 'sha256'), '')                               IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(b ->> 'metodo'), '')                               IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(b ->> 'confianca'), '')                            IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN plat.procedencia_limites(b)                                     IS NOT NULL THEN 1 ELSE 0 END)
    + (CASE WHEN nullif(btrim(b ->> 'proxima_verificacao'), '')                  IS NOT NULL THEN 1 ELSE 0 END)
  END
  FROM (SELECT plat.procedencia_bloco(p_dados)) AS s(b);
$$;

CREATE OR REPLACE FUNCTION plat.procedencia_campos_possiveis()
RETURNS int LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 10; $$;

CREATE OR REPLACE FUNCTION plat.procedencia_pontuacao(p_dados jsonb)
RETURNS numeric LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE WHEN plat.procedencia_bloco(p_dados) IS NULL THEN NULL
              ELSE round(plat.procedencia_campos(p_dados)::numeric
                         / nullif(plat.procedencia_campos_possiveis(), 0) * 10, 1) END;
$$;

-- resumo em UMA passada, para a LISTA do catálogo: `i.dados` não sai na consulta da lista (jsonb de 58 KB
-- em média, 2,8 MB no pior caso do corpus — ADR 0004 seção 13.2), então o selo de procedência de cada linha
-- vem daqui, calculado no servidor, e não do jsonb trafegado. plpgsql (não SQL) para guardar o bloco e a
-- contagem em variável: cada chamada a mais custa uma execução de plano por linha da lista.
CREATE OR REPLACE FUNCTION plat.procedencia_resumo(p_dados jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE b jsonb; c int;
BEGIN
  b := plat.procedencia_bloco(p_dados);
  IF b IS NULL THEN
    RETURN jsonb_build_object('pontuacao', NULL, 'campos', 0,
                              'campos_possiveis', plat.procedencia_campos_possiveis(), 'licenca', NULL);
  END IF;
  c := plat.procedencia_campos(p_dados);
  RETURN jsonb_build_object(
    'pontuacao',        round(c::numeric / nullif(plat.procedencia_campos_possiveis(), 0) * 10, 1),
    'campos',           c,
    'campos_possiveis', plat.procedencia_campos_possiveis(),
    'licenca',          nullif(btrim(b ->> 'licenca'), ''));
END $$;

-- ---------------------------------------------------------------- privilégio das funções
-- Nenhuma função do schema plat fica com EXECUTE para PUBLIC (invariante conferida por
-- tests/api/catalogo/test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app).
REVOKE ALL ON FUNCTION plat.procedencia_bloco(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_valor(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_campo(jsonb, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_limites(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_licenca(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_campos(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_campos_possiveis() FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_pontuacao(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION plat.procedencia_resumo(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.procedencia_bloco(jsonb) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_valor(jsonb) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_campo(jsonb, text, text) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_limites(jsonb) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_licenca(jsonb) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_campos(jsonb) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_campos_possiveis() TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_pontuacao(jsonb) TO plat_app, plat_worker;
GRANT EXECUTE ON FUNCTION plat.procedencia_resumo(jsonb) TO plat_app, plat_worker;

-- ---------------------------------------------------------------- índice do filtro da lista
CREATE INDEX IF NOT EXISTS ix_item_procedencia_pontuacao
  ON plat.item (plat.procedencia_pontuacao(dados)) WHERE apagado_em IS NULL;

-- ---------------------------------------------------------------- esquema dos tipos que carregam dado
-- `procedencia` passa a ser propriedade declarada (aceita objeto ou null; o conteúdo é validado em
-- app/catalogo/procedencia.py, que é onde mora a regra de vazio-vira-NULL e de origem declarado|medido).
UPDATE plat.tipo_item
   SET esquema = jsonb_set(esquema, '{properties,procedencia}',
                           '{"type":["object","null"],"additionalProperties":true}'::jsonb, true),
       esquema_versao = esquema_versao + 1
 WHERE nome IN ('raster', 'arquivo', 'vista_de_camada', 'cena')
   AND esquema -> 'properties' -> 'procedencia' IS NULL;

-- os dois que já tinham o bloco (camada_vetorial pelo L0-04, conexao pela migração 021) só ganham o `null`
UPDATE plat.tipo_item
   SET esquema = jsonb_set(esquema, '{properties,procedencia}',
                           '{"type":["object","null"],"additionalProperties":true}'::jsonb, true),
       esquema_versao = esquema_versao + 1
 WHERE nome IN ('camada_vetorial', 'conexao')
   AND esquema -> 'properties' -> 'procedencia'
       IS DISTINCT FROM '{"type":["object","null"],"additionalProperties":true}'::jsonb;
