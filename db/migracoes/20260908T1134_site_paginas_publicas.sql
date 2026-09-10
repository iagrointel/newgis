-- item L5-20-sites-paginas-publicas (ADR 20260908T1140-sites-paginas-publicas; L5_CONCEITO D10/D24):
-- construtor de SITE do inquilino. O site é um item de tipo `site` (família nova `site`), documento com o
-- MESMO envelope de app/painel (`corpo.nos` plana + `pai`), publicado numa única URL por inquilino,
-- `/s/<inquilino>/` (D10 fixa a forma da URL). A publicação é uma linha por inquilino, não por item: um
-- inquilino tem um site público de cada vez.
--
-- Três funções SECURITY DEFINER, todas no desenho de `plat.publicacao_resolver` (leitura ANÔNIMA, sem
-- contexto de sessão): resolver o site do inquilino, listar os itens que a galeria pode mostrar e contar o
-- que a estatística mostra. As duas últimas filtram por `acesso = 'publico'` E `plat.tenant_permite_publico`
-- — a mesma dupla de `plat.tenant_publico_itens`, que é a definição de "compartilhado com todos" nesta
-- plataforma. Item privado ou de escopo `inquilino` nunca sai delas, nem por id, nem por busca.
--
-- `indexavel` é falso por padrão (regra da casa): quem quer aparecer em buscador liga a opção explicitamente.

-- ---------------------------------------------------------------- família nova no vocabulário de tipos
-- (a CHECK da 011 é reescrita aqui, em arquivo NOVO: a 011 está aplicada e é imutável)
ALTER TABLE plat.tipo_item DROP CONSTRAINT IF EXISTS tipo_item_familia_check;
ALTER TABLE plat.tipo_item ADD CONSTRAINT tipo_item_familia_check
  CHECK (familia IN ('camada','raster','mapa','app','painel','formulario','fluxo','rede',
                     'arquivo','ferramenta','documento','site'));

INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em,
                           tem_dado_fisico, linha_dona) VALUES
  ('site', 'site', 'Site', 'site público do inquilino: páginas de seções e cartões (envelope L5)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
     "properties":{"tipo":{"const":"site"},"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'site', '/static/js/catalogo/tipos/site.js', '{site}', false, 'L5-20')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo, descricao = EXCLUDED.descricao,
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('site/publicar', 'site do inquilino publicado ou republicado em /s/<inquilino>/'),
  ('site/despublicar', 'site do inquilino retirado do ar')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- publicação (uma por inquilino)
CREATE TABLE IF NOT EXISTS plat.site_publicado (
    tenant_id      integer PRIMARY KEY REFERENCES plat.tenant(id),
    item_id        uuid NOT NULL UNIQUE REFERENCES plat.item(id) ON DELETE CASCADE,
    indexavel      boolean NOT NULL DEFAULT false,  -- noindex é o padrão: aparecer em buscador é opção explícita
    publicado_por  integer REFERENCES plat.usuario(id),
    publicado_em   timestamptz NOT NULL DEFAULT now(),
    atualizado_em  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE plat.site_publicado ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_site_publicado ON plat.site_publicado;
CREATE POLICY p_site_publicado ON plat.site_publicado FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id))
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.site_publicado TO plat_app;

-- ---------------------------------------------------------------- leitura anônima do site
CREATE OR REPLACE FUNCTION plat.site_resolver(p_tenant_slug text)
RETURNS TABLE (motivo text, tenant_id int, item_id uuid, versao int, indexavel boolean,
               tenant_nome text, tenant_cor text, tenant_logo text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT CASE WHEN i.versao_publicada IS NULL THEN 'inexistente' ELSE 'ok' END,
         t.id, i.id, i.versao_publicada, s.indexavel, t.nome,
         coalesce(t.config->>'cor', '#1f4b99'), t.config->>'logo'
  FROM plat.site_publicado s
  JOIN plat.tenant t ON t.id = s.tenant_id
  JOIN plat.item i ON i.id = s.item_id
  WHERE t.slug = p_tenant_slug AND t.ativo AND i.apagado_em IS NULL
$$;

REVOKE EXECUTE ON FUNCTION plat.site_resolver(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.site_resolver(text) TO plat_app;

-- corpo da versão PUBLICADA (nunca o rascunho): a leitura anônima não tem contexto e a RLS de item_versao
-- exige tenant_atual(); por isso a leitura passa por aqui, escopada ao item que o site_resolver devolveu.
CREATE OR REPLACE FUNCTION plat.site_corpo(p_item uuid, p_versao int)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT v.corpo FROM plat.item_versao v
  JOIN plat.site_publicado s ON s.item_id = v.item_id
  WHERE v.item_id = p_item AND v.versao = p_versao
$$;

REVOKE EXECUTE ON FUNCTION plat.site_corpo(uuid, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.site_corpo(uuid, int) TO plat_app;

-- galeria e busca do site: SÓ item com acesso = 'publico' num inquilino que permite público (a mesma dupla de
-- plat.tenant_publico_itens). p_busca usa a mesma configuração de texto do catálogo; p_tipos vazio = todos.
CREATE OR REPLACE FUNCTION plat.site_itens_publicos(p_tenant int, p_tipos text[] DEFAULT '{}',
                                                    p_busca text DEFAULT NULL, p_limite int DEFAULT 12)
RETURNS TABLE (id uuid, titulo text, tipo text, resumo text, modificado_em timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT i.id, i.titulo, i.tipo, i.resumo, i.modificado_em
  FROM plat.item i
  WHERE i.tenant_id = p_tenant
    AND i.acesso = 'publico'
    AND i.apagado_em IS NULL
    AND plat.tenant_permite_publico(p_tenant)
    AND (coalesce(cardinality(p_tipos), 0) = 0 OR i.tipo = ANY (p_tipos))
    AND (p_busca IS NULL OR btrim(p_busca) = ''
         OR i.busca @@ websearch_to_tsquery('plat.pt_sem_acento'::regconfig, p_busca))
  ORDER BY i.modificado_em DESC, i.id
  LIMIT greatest(1, least(coalesce(p_limite, 12), 60))
$$;

REVOKE EXECUTE ON FUNCTION plat.site_itens_publicos(int, text[], text, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.site_itens_publicos(int, text[], text, int) TO plat_app;

-- estatística do cartão: contagem por família, só do que é público (mesma regra da galeria)
CREATE OR REPLACE FUNCTION plat.site_estatisticas(p_tenant int)
RETURNS TABLE (familia text, quantidade bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.familia, count(*)
  FROM plat.item i JOIN plat.tipo_item t ON t.nome = i.tipo
  WHERE i.tenant_id = p_tenant AND i.acesso = 'publico' AND i.apagado_em IS NULL
    AND plat.tenant_permite_publico(p_tenant)
  GROUP BY t.familia
  ORDER BY t.familia
$$;

REVOKE EXECUTE ON FUNCTION plat.site_estatisticas(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.site_estatisticas(int) TO plat_app;

-- um item público do inquilino, por id: o cartão de mapa/app cita um item pelo uuid e o renderizador precisa
-- saber se ele PODE ser mostrado. Devolve zero linha para item privado — é esta a defesa contra o cartão que
-- aponta para item que o visitante não poderia ver.
CREATE OR REPLACE FUNCTION plat.site_item_publico(p_tenant int, p_item uuid)
RETURNS TABLE (id uuid, titulo text, tipo text, resumo text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT i.id, i.titulo, i.tipo, i.resumo
  FROM plat.item i
  WHERE i.id = p_item AND i.tenant_id = p_tenant AND i.acesso = 'publico' AND i.apagado_em IS NULL
    AND plat.tenant_permite_publico(p_tenant)
$$;

REVOKE EXECUTE ON FUNCTION plat.site_item_publico(int, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.site_item_publico(int, uuid) TO plat_app;
