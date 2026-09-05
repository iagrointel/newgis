-- 011_catalogo: catálogo de conteúdo (ADR 0004; item L0-03-catalogo e filhos a..l). Uma tabela plat.item para todo
-- tipo de conteúdo, registro plat.tipo_item com JSON Schema, versões imutáveis com sha256, relações com vocabulário
-- fechado e ciclo recusado, compartilhamento em cinco níveis decidido por plat.pode_ler/pode_editar na RLS, link por
-- token, busca FTS (configuração plat.pt_sem_acento com unaccent como dicionário; invólucro IMMUTABLE plat.tags_texto
-- porque array_to_string é STABLE), pastas hierárquicas, categorias, favoritos, lixeira lógica, proteção, status,
-- expurgo e eventos. Numeração 011 (009 = identidade, 010 = jobs). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- ---------------------------------------------------------------- 18.1 funções IMMUTABLE e configuração de busca
CREATE OR REPLACE FUNCTION plat.tags_texto(text[]) RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT array_to_string($1, ' ') $$;
CREATE OR REPLACE FUNCTION plat.tags_validas(text[]) RETURNS boolean
  LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT coalesce(bool_and(length(t) BETWEEN 1 AND 128 AND t !~ '[,\n\r\t]' AND t = btrim(t)), true) FROM unnest($1) t $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'pt_sem_acento' AND cfgnamespace = 'plat'::regnamespace) THEN
    CREATE TEXT SEARCH CONFIGURATION plat.pt_sem_acento (COPY = pg_catalog.portuguese);
    ALTER TEXT SEARCH CONFIGURATION plat.pt_sem_acento
      ALTER MAPPING FOR hword, hword_part, word, asciiword, asciihword, hword_asciipart
      WITH public.unaccent, portuguese_stem;
  END IF;
END $$;

-- ---------------------------------------------------------------- 18.2 vocabulários: tipo_item, relacao_tipo
CREATE TABLE IF NOT EXISTS plat.tipo_item (
  nome            text PRIMARY KEY CHECK (nome ~ '^[a-z][a-z0-9_]{1,40}$'),
  familia         text NOT NULL CHECK (familia IN ('camada','raster','mapa','app','painel','formulario','fluxo','rede',
                                                   'arquivo','ferramenta','documento')),
  rotulo          text NOT NULL,
  descricao       text NOT NULL,
  esquema         jsonb NOT NULL,
  esquema_versao  int NOT NULL DEFAULT 1,
  icone           text NOT NULL,
  modulo_front    text NOT NULL,
  abre_em         text[] NOT NULL DEFAULT '{}',
  tem_dado_fisico boolean NOT NULL DEFAULT false,
  linha_dona      text NOT NULL,
  criado_em       timestamptz NOT NULL DEFAULT now()
);
-- esquemas mínimos (Draft 2020-12, additionalProperties: false); cada linha futura completa o seu por migração
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, tem_dado_fisico, linha_dona) VALUES
  ('camada_vetorial', 'camada', 'Camada vetorial', 'camada vetorial hospedada ou referenciada (tabela PostGIS)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["schema","tabela","geometria","srid","campos","fonte"],
     "properties":{
       "schema":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "tabela":{"type":"string","pattern":"^[a-z][a-z0-9_]{1,62}$"},
       "geometria":{"type":"string","enum":["Point","MultiPoint","LineString","MultiLineString","Polygon","MultiPolygon","Geometry","nenhuma"]},
       "srid":{"type":"integer","minimum":1,"maximum":999999},
       "campos":{"type":"array","maxItems":500,"items":{"type":"object","additionalProperties":false,"required":["nome","tipo"],
                 "properties":{"nome":{"type":"string","maxLength":63},"tipo":{"type":"string","maxLength":64},"alias":{"type":"string","maxLength":200}}}},
       "fonte":{"type":"string","enum":["hospedada","referenciada"]},
       "edicao":{"type":"object","additionalProperties":false,"properties":{"habilitada":{"type":"boolean"}}},
       "procedencia":{"type":"object","additionalProperties":true}}}'::jsonb,
   1, 'camada', '/static/js/catalogo/tipos/camada_vetorial.js', '{mapa,tabela}', true, 'L0-04'),
  ('vista_de_camada', 'camada', 'Vista de camada', 'vista derivada de uma camada primária (filtro, campos, extent)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["camada_id"],
     "properties":{"camada_id":{"type":"string","format":"uuid","pattern":"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
       "filtro":{"type":"object"},"campos_ocultos":{"type":"array","items":{"type":"string"}},
       "extent":{"type":"array","minItems":4,"maxItems":4,"items":{"type":"number"}}}}'::jsonb,
   1, 'vista', '/static/js/catalogo/tipos/vista_de_camada.js', '{mapa,tabela}', true, 'L0-04-j'),
  ('raster', 'raster', 'Imagem', 'imagem ou coleção raster (pgstac + objeto)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["colecao","stac_id","perfil","origem","srid_nativo"],
     "properties":{"colecao":{"type":"string"},"stac_id":{"type":"string"},"perfil":{"type":"string","enum":["visual","cientifico","referencia"]},
       "origem":{"type":"string","enum":["copiado","referenciado"]},"srid_nativo":{"type":"integer"},
       "bandas":{"type":"array","items":{"type":"object","additionalProperties":false,"required":["nome"],
                 "properties":{"nome":{"type":"string"},"nome_comum":{"type":"string"}}}}}}'::jsonb,
   1, 'raster', '/static/js/catalogo/tipos/raster.js', '{mapa}', true, 'L1-01'),
  ('mapa', 'mapa', 'Mapa', 'documento de mapa (camadas por uuid)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["esquema_versao","corpo"],
     "properties":{"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'mapa', '/static/js/catalogo/tipos/mapa.js', '{mapa}', false, 'L2-01'),
  ('cena', 'mapa', 'Cena', 'documento de cena 3D',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["esquema_versao","corpo"],
     "properties":{"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'cena', '/static/js/catalogo/tipos/cena.js', '{cena}', false, 'L2-17'),
  ('estilo', 'documento', 'Estilo', 'estilo MapLibre com bloco plat_construtor',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["esquema_versao","corpo"],
     "properties":{"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'estilo', '/static/js/catalogo/tipos/estilo.js', '{}', false, 'L2-02'),
  ('app', 'app', 'Aplicativo', 'aplicativo construído (envelope L5)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
     "properties":{"tipo":{"const":"app"},"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'app', '/static/js/catalogo/tipos/app.js', '{app}', false, 'L5-01'),
  ('painel', 'painel', 'Painel', 'painel de indicadores (envelope L5)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
     "properties":{"tipo":{"const":"painel"},"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'painel', '/static/js/catalogo/tipos/painel.js', '{app}', false, 'L5-03'),
  ('formulario', 'formulario', 'Formulário', 'formulário de coleta (envelope L5)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
     "properties":{"tipo":{"const":"formulario"},"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'formulario', '/static/js/catalogo/tipos/formulario.js', '{app}', false, 'L5-04'),
  ('fluxo', 'fluxo', 'Fluxo', 'fluxo de automação (grafo JSON, envelope L5)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["tipo","esquema_versao","corpo"],
     "properties":{"tipo":{"const":"fluxo"},"esquema_versao":{"type":"integer","minimum":1},"corpo":{"type":"object"}}}'::jsonb,
   1, 'fluxo', '/static/js/catalogo/tipos/fluxo.js', '{app}', false, 'L5-02'),
  ('rede', 'rede', 'Rede de utilidades', 'rede composta por camadas de nós, arestas e equipamentos',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["camadas","regras_versao"],
     "properties":{"camadas":{"type":"object","additionalProperties":false,"required":["nos","arestas"],
       "properties":{"nos":{"type":"string","format":"uuid"},"arestas":{"type":"string","format":"uuid"},"equipamentos":{"type":"string","format":"uuid"}}},
       "regras_versao":{"type":"integer","minimum":1}}}'::jsonb,
   1, 'rede', '/static/js/catalogo/tipos/rede.js', '{mapa}', true, 'L4-01'),
  ('conexao', 'ferramenta', 'Conexão', 'fonte de dado externa (segredo fica no cofre, nunca em dados)',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["protocolo","url"],
     "properties":{"protocolo":{"type":"string","enum":["wms","wfs","wmts","ogc_api","esri_rest","postgres_fdw","s3","http"]},
       "url":{"type":"string","maxLength":2048},"credencial_id":{"type":"string","format":"uuid"},"parametros":{"type":"object"}}}'::jsonb,
   1, 'conexao', '/static/js/catalogo/tipos/conexao.js', '{}', false, 'L0-04-i'),
  ('arquivo', 'arquivo', 'Arquivo', 'arquivo guardado no armazenamento de objetos',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["chave","sha256","bytes","content_type","nome_original"],
     "properties":{"chave":{"type":"string","maxLength":512},"sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
       "bytes":{"type":"integer","minimum":0},"content_type":{"type":"string","maxLength":255},"nome_original":{"type":"string","maxLength":255}}}'::jsonb,
   1, 'arquivo', '/static/js/catalogo/tipos/arquivo.js', '{}', true, 'L0-11'),
  ('modelo_amc', 'ferramenta', 'Modelo multicritério', 'modelo AMC: fatores por camada, critério e peso',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"required":["esquema_versao","fatores","metodo"],
     "properties":{"esquema_versao":{"type":"integer","minimum":1},
       "fatores":{"type":"array","maxItems":50,"items":{"type":"object","additionalProperties":false,"required":["camada_id","criterio"],
         "properties":{"camada_id":{"type":"string","format":"uuid"},"criterio":{"type":"string","maxLength":200},"peso":{"type":"number"}}}},
       "metodo":{"type":"string","enum":["soma_ponderada","ahp","topsis"]}}}'::jsonb,
   1, 'amc', '/static/js/catalogo/tipos/modelo_amc.js', '{app}', false, 'L3-01')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo, descricao = EXCLUDED.descricao,
  esquema = CASE WHEN plat.tipo_item.esquema_versao > EXCLUDED.esquema_versao THEN plat.tipo_item.esquema ELSE EXCLUDED.esquema END,
  esquema_versao = greatest(plat.tipo_item.esquema_versao, EXCLUDED.esquema_versao),
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;
REVOKE INSERT, UPDATE, DELETE ON plat.tipo_item FROM plat_app;

CREATE TABLE IF NOT EXISTS plat.relacao_tipo (
  nome             text PRIMARY KEY,
  descricao        text NOT NULL,
  origem_familias  text[] NOT NULL,
  destino_familias text[] NOT NULL,
  arrasta_dono     boolean NOT NULL DEFAULT false,
  apaga_junto      boolean NOT NULL DEFAULT false
);
INSERT INTO plat.relacao_tipo VALUES
  ('camada_de_mapa',       'mapa usa camada',                                  '{mapa}',            '{camada,raster,rede}', false, false),
  ('dado_de_camada',       'camada aponta para o dado (STAC/arquivo de origem)','{camada,raster}',   '{raster,arquivo}',     true,  false),
  ('mapa_de_app',          'app/painel usa mapa',                              '{app,painel}',      '{mapa}',               false, false),
  ('vista_de_camada',      'vista deriva da camada primária',                  '{camada}',          '{camada}',             true,  true),
  ('estilo_de_camada',     'estilo pertence à camada',                         '{documento}',       '{camada,raster}',      true,  true),
  ('arquivo_de_camada',    'arquivo de origem da camada',                      '{arquivo}',         '{camada}',             true,  true),
  ('formulario_de_camada', 'formulário grava na camada',                       '{formulario}',      '{camada}',             false, false),
  ('resultado_de_job',     'item produzido por job (proveniência)',            '{camada,raster,arquivo,documento}', '{camada,raster,arquivo,mapa,ferramenta}', false, false),
  ('anexo_de_item',        'arquivo anexado a item',                           '{arquivo}',         '{camada,mapa,app,painel,formulario,fluxo,rede,ferramenta,documento,raster}', true, true),
  ('fator_de_motor',       'modelo AMC usa camada como fator',                 '{ferramenta}',      '{camada,raster}',      false, false),
  ('rede_de_camada',       'rede é composta por camadas',                      '{rede}',            '{camada}',             true,  true)
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao, origem_familias = EXCLUDED.origem_familias,
  destino_familias = EXCLUDED.destino_familias, arrasta_dono = EXCLUDED.arrasta_dono, apaga_junto = EXCLUDED.apaga_junto;
REVOKE INSERT, UPDATE, DELETE ON plat.relacao_tipo FROM plat_app;

-- ---------------------------------------------------------------- funções de contexto (superadmin)
CREATE OR REPLACE FUNCTION plat.eh_superadmin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = plat.usuario_atual() AND u.superadmin AND u.ativo)
$$;
-- a variável sozinha não basta: quem a liga tem de ser um superadmin real (refutação: set_config direto)
CREATE OR REPLACE FUNCTION plat.modo_superadmin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT current_setting('plat.superadmin', true) = 'on' AND plat.eh_superadmin()
$$;
CREATE OR REPLACE FUNCTION plat.tenant_permite_publico(p_tenant int) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->'auth'->>'compartilhar_publico')::boolean, false) FROM plat.tenant WHERE id = p_tenant
$$;
-- usuário da sessão pertence ao inquilino do contexto (superadmin lendo outro inquilino: falso)
CREATE OR REPLACE FUNCTION plat.usuario_do_inquilino() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = plat.usuario_atual() AND u.tenant_id = plat.tenant_atual() AND u.ativo)
$$;

-- ---------------------------------------------------------------- 18.3 pastas hierárquicas por inquilino
CREATE TABLE IF NOT EXISTS plat.pasta (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  pai_id       uuid REFERENCES plat.pasta(id) ON DELETE RESTRICT,
  nome         text NOT NULL CHECK (length(nome) BETWEEN 1 AND 128 AND nome !~ '[/\\]' AND nome = btrim(nome)),
  ancestrais   uuid[] NOT NULL DEFAULT '{}',
  profundidade smallint NOT NULL DEFAULT 0 CHECK (profundidade BETWEEN 0 AND 4),
  dono_id      int NOT NULL REFERENCES plat.usuario(id),
  criado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pasta_irmas ON plat.pasta (tenant_id, pai_id, lower(nome)) WHERE pai_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_pasta_raiz  ON plat.pasta (tenant_id, lower(nome)) WHERE pai_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_pasta_ancestrais ON plat.pasta USING gin (ancestrais);
CREATE INDEX IF NOT EXISTS ix_pasta_pai ON plat.pasta (tenant_id, pai_id);

CREATE OR REPLACE FUNCTION plat.tg_pasta_caminho() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pai plat.pasta;
BEGIN
  IF NEW.pai_id IS NULL THEN
    NEW.ancestrais := '{}'; NEW.profundidade := 0;
  ELSE
    SELECT * INTO pai FROM plat.pasta WHERE id = NEW.pai_id;
    IF pai.id IS NULL OR pai.tenant_id <> NEW.tenant_id THEN RAISE EXCEPTION 'pasta_de_outro_inquilino'; END IF;
    IF NEW.id = pai.id OR NEW.id = ANY (pai.ancestrais) THEN RAISE EXCEPTION 'pasta_ciclo'; END IF;
    IF pai.profundidade >= 4 THEN RAISE EXCEPTION 'pasta_profunda'; END IF;
    NEW.ancestrais := pai.ancestrais || pai.id; NEW.profundidade := pai.profundidade + 1;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.pai_id IS DISTINCT FROM OLD.pai_id THEN
    -- descendentes: recalcula o caminho; a mais funda não pode passar de 4
    IF EXISTS (SELECT 1 FROM plat.pasta d WHERE OLD.id = ANY (d.ancestrais)
               AND d.profundidade - OLD.profundidade + NEW.profundidade > 4) THEN
      RAISE EXCEPTION 'pasta_profunda';
    END IF;
    UPDATE plat.pasta d
       SET ancestrais = NEW.ancestrais || NEW.id || d.ancestrais[array_position(d.ancestrais, OLD.id) + 1:],
           profundidade = d.profundidade - OLD.profundidade + NEW.profundidade
     WHERE OLD.id = ANY (d.ancestrais);
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pasta_caminho ON plat.pasta;
CREATE TRIGGER pasta_caminho BEFORE INSERT OR UPDATE OF pai_id ON plat.pasta FOR EACH ROW EXECUTE FUNCTION plat.tg_pasta_caminho();

-- apagar pasta com subpasta ou item recusa (o item usa ON DELETE SET NULL só para o caso impossível)
CREATE OR REPLACE FUNCTION plat.tg_pasta_vazia() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM plat.pasta WHERE pai_id = OLD.id)
     OR EXISTS (SELECT 1 FROM plat.item WHERE pasta_id = OLD.id AND apagado_em IS NULL) THEN
    RAISE EXCEPTION 'pasta_nao_vazia';
  END IF;
  RETURN OLD;
END $$;

ALTER TABLE plat.pasta ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_pasta_ler ON plat.pasta;
CREATE POLICY p_pasta_ler ON plat.pasta FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_pasta_inserir ON plat.pasta;
CREATE POLICY p_pasta_inserir ON plat.pasta FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND dono_id = plat.usuario_atual() AND plat.usuario_do_inquilino());
DROP POLICY IF EXISTS p_pasta_alterar ON plat.pasta;
CREATE POLICY p_pasta_alterar ON plat.pasta FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')))
  WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_pasta_apagar ON plat.pasta;
CREATE POLICY p_pasta_apagar ON plat.pasta FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')));

-- ---------------------------------------------------------------- 18.4 categorias do inquilino
CREATE TABLE IF NOT EXISTS plat.categoria (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id int NOT NULL REFERENCES plat.tenant(id),
  pai_id    uuid REFERENCES plat.categoria(id) ON DELETE RESTRICT,
  nome      text NOT NULL CHECK (length(nome) BETWEEN 1 AND 100),
  caminho   text NOT NULL DEFAULT '',
  nivel     smallint NOT NULL DEFAULT 1 CHECK (nivel BETWEEN 1 AND 3),
  posicao   int NOT NULL DEFAULT 0,
  origem    text NOT NULL DEFAULT 'propria' CHECK (origem IN ('iso19115','inspire','propria')),
  codigo    text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_categoria_irmas ON plat.categoria (tenant_id, pai_id, lower(nome)) WHERE pai_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_categoria_raiz  ON plat.categoria (tenant_id, lower(nome)) WHERE pai_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_categoria_codigo ON plat.categoria (tenant_id, codigo) WHERE codigo IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_categoria_tenant ON plat.categoria (tenant_id, pai_id, posicao);

CREATE OR REPLACE FUNCTION plat.categorias_max(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT least(900, greatest(50, coalesce((config->'catalogo'->>'categorias_max')::int, 200))) FROM plat.tenant WHERE id = p_tenant
$$;

CREATE OR REPLACE FUNCTION plat.tg_categoria() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE pai plat.categoria; n int;
BEGIN
  IF NEW.pai_id IS NULL THEN
    NEW.nivel := 1; NEW.caminho := NEW.nome;
  ELSE
    SELECT * INTO pai FROM plat.categoria WHERE id = NEW.pai_id;
    IF pai.id IS NULL OR pai.tenant_id <> NEW.tenant_id THEN RAISE EXCEPTION 'categoria_de_outro_inquilino'; END IF;
    IF NEW.id = pai.id OR pai.caminho LIKE '%' || NEW.nome || '/%' AND pai.id = NEW.id THEN RAISE EXCEPTION 'pasta_ciclo'; END IF;
    IF pai.nivel >= 3 THEN RAISE EXCEPTION 'nivel_maximo'; END IF;
    NEW.nivel := pai.nivel + 1; NEW.caminho := pai.caminho || '/' || NEW.nome;
  END IF;
  IF TG_OP = 'INSERT' THEN
    SELECT count(*) INTO n FROM plat.categoria WHERE tenant_id = NEW.tenant_id;
    IF n >= plat.categorias_max(NEW.tenant_id) THEN RAISE EXCEPTION 'limite_categorias'; END IF;
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.nome <> OLD.nome OR NEW.pai_id IS DISTINCT FROM OLD.pai_id) THEN
    UPDATE plat.categoria c SET caminho = NEW.caminho || substr(c.caminho, length(OLD.caminho) + 1),
                                nivel = c.nivel - OLD.nivel + NEW.nivel
     WHERE c.tenant_id = NEW.tenant_id AND c.caminho LIKE OLD.caminho || '/%';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS categoria_arvore ON plat.categoria;
CREATE TRIGGER categoria_arvore BEFORE INSERT OR UPDATE OF nome, pai_id ON plat.categoria FOR EACH ROW EXECUTE FUNCTION plat.tg_categoria();

ALTER TABLE plat.categoria ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_categoria_ler ON plat.categoria;
CREATE POLICY p_categoria_ler ON plat.categoria FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_categoria_escrever ON plat.categoria;
CREATE POLICY p_categoria_escrever ON plat.categoria FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.tem('conteudo.categorias'))
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.tem('conteudo.categorias'));

-- ---------------------------------------------------------------- 18.5 item
CREATE TABLE IF NOT EXISTS plat.item (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  tipo               text NOT NULL REFERENCES plat.tipo_item(nome),
  titulo             text NOT NULL CHECK (length(titulo) BETWEEN 1 AND 250),
  resumo             text CHECK (length(resumo) <= 2048),
  descricao          text CHECK (length(descricao) <= 65536),
  descricao_html     text,
  tags               text[] NOT NULL DEFAULT '{}' CHECK (cardinality(tags) <= 50 AND plat.tags_validas(tags)),
  creditos           text CHECK (length(creditos) <= 2048),
  termos_de_uso      text CHECK (length(termos_de_uso) <= 65536),
  termos_de_uso_html text,
  dono_id            int NOT NULL REFERENCES plat.usuario(id),
  pasta_id           uuid REFERENCES plat.pasta(id) ON DELETE SET NULL,
  extent             geometry(Polygon, 4326)
                     CHECK (extent IS NULL OR (ST_XMin(extent) >= -180 AND ST_XMax(extent) <= 180
                                               AND ST_YMin(extent) >= -90 AND ST_YMax(extent) <= 90 AND ST_IsValid(extent))),
  extent_origem      text CHECK (extent_origem IN ('dado','usuario','inquilino')),
  miniatura_chave    text,
  miniatura_sha256   text,
  dados              jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(dados) = 'object'),
  acesso             text NOT NULL DEFAULT 'privado' CHECK (acesso IN ('privado','inquilino','publico')),
  status             text CHECK (status IN ('autoritativo','obsoleto')),
  protegido          boolean NOT NULL DEFAULT false,
  classificacao      jsonb,
  categorias         uuid[] NOT NULL DEFAULT '{}' CHECK (cardinality(categorias) <= 20),
  origem             text NOT NULL DEFAULT 'hospedado' CHECK (origem IN ('hospedado','referenciado')),
  url                text CHECK (url IS NULL OR (length(url) <= 2048 AND url ~ '^https?://')),
  tamanho_bytes      bigint NOT NULL DEFAULT 0,
  versao_atual       int NOT NULL DEFAULT 0,
  versao_publicada   int,
  pontuacao          smallint NOT NULL DEFAULT 0 CHECK (pontuacao BETWEEN 0 AND 10),
  criado_por         int REFERENCES plat.usuario(id),
  criado_em          timestamptz NOT NULL DEFAULT now(),
  modificado_por     int REFERENCES plat.usuario(id),
  modificado_em      timestamptz NOT NULL DEFAULT now(),
  apagado_em         timestamptz,
  apagado_por        int REFERENCES plat.usuario(id),
  busca              tsvector GENERATED ALWAYS AS (
                       setweight(to_tsvector('plat.pt_sem_acento'::regconfig, coalesce(titulo, '')), 'A') ||
                       setweight(to_tsvector('plat.pt_sem_acento'::regconfig, coalesce(plat.tags_texto(tags), '')), 'B') ||
                       setweight(to_tsvector('plat.pt_sem_acento'::regconfig, coalesce(resumo, '')), 'C') ||
                       setweight(to_tsvector('plat.pt_sem_acento'::regconfig, coalesce(descricao, '')), 'D')) STORED
);
CREATE INDEX IF NOT EXISTS ix_item_lista   ON plat.item (tenant_id, tipo, modificado_em DESC, id DESC) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_item_dono    ON plat.item (tenant_id, dono_id, modificado_em DESC) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_item_pasta   ON plat.item (pasta_id) WHERE apagado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_item_lixeira ON plat.item (tenant_id, apagado_em) WHERE apagado_em IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_item_busca   ON plat.item USING gin (busca);
CREATE INDEX IF NOT EXISTS ix_item_titulo_trgm ON plat.item USING gin (titulo public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_item_tags    ON plat.item USING gin (tags);
CREATE INDEX IF NOT EXISTS ix_item_categorias ON plat.item USING gin (categorias);
CREATE INDEX IF NOT EXISTS ix_item_extent  ON plat.item USING gist (extent) WHERE extent IS NOT NULL;

DROP TRIGGER IF EXISTS pasta_vazia ON plat.pasta;
CREATE TRIGGER pasta_vazia BEFORE DELETE ON plat.pasta FOR EACH ROW EXECUTE FUNCTION plat.tg_pasta_vazia();

-- pontuação de informação: um ponto por campo preenchido (2.6), os dez campos escritos aqui e no MANUAL
CREATE OR REPLACE FUNCTION plat.item_pontuacao(i plat.item) RETURNS smallint
LANGUAGE sql IMMUTABLE AS $$
  SELECT (1
    + (coalesce(length(i.resumo), 0) > 0)::int
    + (coalesce(length(i.descricao), 0) >= 100)::int
    + (cardinality(i.tags) >= 3)::int
    + (coalesce(length(i.creditos), 0) > 0)::int
    + (coalesce(length(i.termos_de_uso), 0) > 0)::int
    + (i.extent IS NOT NULL)::int
    + (i.miniatura_chave IS NOT NULL)::int
    + (cardinality(i.categorias) >= 1)::int
    + (i.dados #>> '{procedencia,fonte}' IS NOT NULL)::int)::smallint
$$;

-- retrato do item para item_versao: metadado editável + dados (nunca busca, tamanho, miniatura)
CREATE OR REPLACE FUNCTION plat.item_retrato(i plat.item) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_build_object(
    'titulo', i.titulo, 'resumo', i.resumo, 'descricao', i.descricao, 'tags', to_jsonb(i.tags),
    'creditos', i.creditos, 'termos_de_uso', i.termos_de_uso,
    'extent', CASE WHEN i.extent IS NULL THEN NULL ELSE jsonb_build_array(ST_XMin(i.extent), ST_YMin(i.extent), ST_XMax(i.extent), ST_YMax(i.extent)) END,
    'extent_origem', i.extent_origem, 'categorias', to_jsonb(i.categorias), 'classificacao', i.classificacao,
    'url', i.url, 'dados', i.dados)
$$;

CREATE OR REPLACE FUNCTION plat.tg_item_antes() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE mudou_corpo boolean; c uuid;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    -- 2.2 imutáveis
    IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id OR NEW.tipo <> OLD.tipo OR NEW.criado_em <> OLD.criado_em
       OR NEW.criado_por IS DISTINCT FROM OLD.criado_por OR NEW.versao_atual <> OLD.versao_atual THEN
      RAISE EXCEPTION 'campo_imutavel';
    END IF;
    IF NEW.dono_id <> OLD.dono_id AND current_setting('plat.transferencia', true) IS DISTINCT FROM 'on' THEN
      RAISE EXCEPTION 'dono_so_por_transferencia';
    END IF;
    -- 9.2 proteção: exclusão lógica de item protegido só em modo superadmin (variável + usuário superadmin real)
    IF NEW.apagado_em IS NOT NULL AND OLD.apagado_em IS NULL AND OLD.protegido AND NOT plat.modo_superadmin() THEN
      RAISE EXCEPTION 'item_protegido';
    END IF;
  END IF;
  -- 2.2 coerência de inquilino
  IF NOT EXISTS (SELECT 1 FROM plat.usuario u WHERE u.id = NEW.dono_id AND u.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'usuario_de_outro_inquilino';
  END IF;
  IF NEW.pasta_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM plat.pasta p WHERE p.id = NEW.pasta_id AND p.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'pasta_de_outro_inquilino';
  END IF;
  FOREACH c IN ARRAY NEW.categorias LOOP
    IF NOT EXISTS (SELECT 1 FROM plat.categoria k WHERE k.id = c AND k.tenant_id = NEW.tenant_id) THEN
      RAISE EXCEPTION 'categoria_de_outro_inquilino';
    END IF;
  END LOOP;
  -- 9.3 autoritativo liga proteção; 6.1 público exige o inquilino autorizar
  IF NEW.status = 'autoritativo' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'autoritativo') THEN
    NEW.protegido := true;
  END IF;
  IF NEW.acesso = 'publico' AND (TG_OP = 'INSERT' OR OLD.acesso <> 'publico') AND NOT plat.tenant_permite_publico(NEW.tenant_id) THEN
    RAISE EXCEPTION 'publico_desligado';
  END IF;
  -- versão: só quando o retrato muda (2.2, seção 4); pontuação sempre recalculada
  mudou_corpo := TG_OP = 'INSERT' OR plat.item_retrato(NEW) <> plat.item_retrato(OLD);
  NEW.pontuacao := plat.item_pontuacao(NEW);
  IF mudou_corpo THEN
    NEW.versao_atual := CASE WHEN TG_OP = 'INSERT' THEN 1 ELSE OLD.versao_atual + 1 END;
  END IF;
  IF TG_OP = 'UPDATE' AND (mudou_corpo OR NEW.pasta_id IS DISTINCT FROM OLD.pasta_id OR NEW.acesso <> OLD.acesso
     OR NEW.status IS DISTINCT FROM OLD.status OR NEW.protegido <> OLD.protegido
     OR NEW.miniatura_chave IS DISTINCT FROM OLD.miniatura_chave OR NEW.dono_id <> OLD.dono_id) THEN
    NEW.modificado_em := now();
    NEW.modificado_por := coalesce(plat.usuario_atual(), NEW.modificado_por);
  END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.modificado_por := coalesce(NEW.modificado_por, plat.usuario_atual());
    NEW.criado_por := coalesce(NEW.criado_por, plat.usuario_atual());
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS item_antes ON plat.item;
CREATE TRIGGER item_antes BEFORE INSERT OR UPDATE ON plat.item FOR EACH ROW EXECUTE FUNCTION plat.tg_item_antes();

-- ---------------------------------------------------------------- 18.6 item_versao (imutável; só o gatilho escreve)
CREATE TABLE IF NOT EXISTS plat.item_versao (
  item_id     uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  versao      int NOT NULL,
  tenant_id   int NOT NULL,
  corpo       jsonb NOT NULL,
  sha256      text NOT NULL,
  autor_id    int,
  comentario  text CHECK (length(comentario) <= 500),
  rotulo      text CHECK (rotulo IN ('edicao','restauracao','rascunho','publicacao','compactada','migracao')),
  compactou   int NOT NULL DEFAULT 0,
  criado_em   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (item_id, versao)
);
CREATE INDEX IF NOT EXISTS ix_item_versao_tenant ON plat.item_versao (tenant_id, criado_em DESC);
REVOKE INSERT, UPDATE, DELETE ON plat.item_versao FROM plat_app;

CREATE OR REPLACE FUNCTION plat.tg_item_versao() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE corpo jsonb;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.versao_atual = OLD.versao_atual THEN RETURN NULL; END IF;
  corpo := plat.item_retrato(NEW);
  INSERT INTO plat.item_versao(item_id, versao, tenant_id, corpo, sha256, autor_id, comentario, rotulo)
  VALUES (NEW.id, NEW.versao_atual, NEW.tenant_id, corpo, encode(digest(corpo::text, 'sha256'), 'hex'),
          plat.usuario_atual(), NULLIF(current_setting('plat.versao_comentario', true), ''),
          coalesce(NULLIF(current_setting('plat.versao_rotulo', true), ''), 'edicao'))
  ON CONFLICT (item_id, versao) DO NOTHING;
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS item_versao ON plat.item;
CREATE TRIGGER item_versao AFTER INSERT OR UPDATE ON plat.item FOR EACH ROW EXECUTE FUNCTION plat.tg_item_versao();

-- ---------------------------------------------------------------- 18.7 relações, grupos, links, favoritos
CREATE TABLE IF NOT EXISTS plat.item_relacao (
  origem    uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  destino   uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  tipo      text NOT NULL REFERENCES plat.relacao_tipo(nome),
  tenant_id int NOT NULL,
  posicao   int,
  criado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (origem, destino, tipo),
  CHECK (origem <> destino)
);
CREATE INDEX IF NOT EXISTS ix_item_relacao_destino ON plat.item_relacao (destino);
CREATE INDEX IF NOT EXISTS ix_item_relacao_origem  ON plat.item_relacao (origem);

CREATE OR REPLACE FUNCTION plat.tg_item_relacao() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE o plat.item; d plat.item; rt plat.relacao_tipo; fo text; fd text; caminho uuid[]; n int;
BEGIN
  SELECT * INTO o FROM plat.item WHERE id = NEW.origem;
  SELECT * INTO d FROM plat.item WHERE id = NEW.destino;
  IF o.id IS NULL OR d.id IS NULL OR o.tenant_id <> NEW.tenant_id OR d.tenant_id <> NEW.tenant_id
     OR NEW.tenant_id IS DISTINCT FROM plat.tenant_atual() OR o.apagado_em IS NOT NULL OR d.apagado_em IS NOT NULL THEN
    RAISE EXCEPTION 'relacao_com_outro_inquilino';
  END IF;
  SELECT * INTO rt FROM plat.relacao_tipo WHERE nome = NEW.tipo;
  SELECT familia INTO fo FROM plat.tipo_item WHERE nome = o.tipo;
  SELECT familia INTO fd FROM plat.tipo_item WHERE nome = d.tipo;
  IF NOT (fo = ANY (rt.origem_familias)) OR NOT (fd = ANY (rt.destino_familias)) THEN
    RAISE EXCEPTION 'relacao_familia_invalida';
  END IF;
  -- tetos (5.2)
  SELECT count(*) INTO n FROM plat.item_relacao WHERE origem = NEW.origem;
  IF n >= 5000 THEN RAISE EXCEPTION 'limite_relacoes'; END IF;
  SELECT count(*) INTO n FROM plat.item_relacao WHERE destino = NEW.destino;
  IF n >= 50000 THEN RAISE EXCEPTION 'limite_relacoes'; END IF;
  -- ciclo: NEW.destino já depende (direta ou indiretamente) de NEW.origem?
  WITH RECURSIVE dep AS (
    SELECT r.destino AS no, ARRAY[NEW.destino, r.destino] AS caminho, 1 AS nivel
      FROM plat.item_relacao r WHERE r.origem = NEW.destino
    UNION ALL
    SELECT r.destino, dep.caminho || r.destino, dep.nivel + 1
      FROM dep JOIN plat.item_relacao r ON r.origem = dep.no
     WHERE dep.nivel < 20 AND NOT r.destino = ANY (dep.caminho)
  )
  SELECT dep.caminho INTO caminho FROM dep WHERE dep.no = NEW.origem LIMIT 1;
  IF caminho IS NOT NULL THEN
    RAISE EXCEPTION 'relacao_ciclo' USING DETAIL = array_to_string(caminho, ',');
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS item_relacao_coerente ON plat.item_relacao;
CREATE TRIGGER item_relacao_coerente BEFORE INSERT OR UPDATE ON plat.item_relacao FOR EACH ROW EXECUTE FUNCTION plat.tg_item_relacao();

CREATE TABLE IF NOT EXISTS plat.item_grupo (
  item_id    uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  grupo_id   uuid NOT NULL REFERENCES plat.grupo(id) ON DELETE CASCADE,
  tenant_id  int NOT NULL,
  criado_por int,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  destaque   boolean NOT NULL DEFAULT false,
  PRIMARY KEY (item_id, grupo_id)
);
CREATE INDEX IF NOT EXISTS ix_item_grupo_grupo ON plat.item_grupo (grupo_id);

CREATE OR REPLACE FUNCTION plat.tg_item_grupo() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE g plat.grupo; n int; papel text;
BEGIN
  SELECT * INTO g FROM plat.grupo WHERE id = NEW.grupo_id;
  IF g.id IS NULL OR g.tenant_id <> NEW.tenant_id OR NEW.tenant_id IS DISTINCT FROM plat.tenant_atual() THEN
    RAISE EXCEPTION 'grupo_de_outro_inquilino';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.id = NEW.item_id AND i.tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'relacao_com_outro_inquilino';
  END IF;
  -- só se compartilha com grupo em que o ator pode contribuir (ADR 0002 4.2), salvo grupos.gerir_todos
  IF TG_OP = 'INSERT' AND NOT plat.tem('grupos.gerir_todos') THEN
    SELECT m.papel INTO papel FROM plat.grupo_membro m WHERE m.grupo_id = g.id AND m.usuario_id = plat.usuario_atual() AND m.estado = 'ativo';
    IF papel IS NULL OR (g.contribuicao = 'dono_gerentes' AND papel NOT IN ('dono','gerente')) THEN
      RAISE EXCEPTION 'sem_contribuicao_no_grupo';
    END IF;
  END IF;
  IF NEW.destaque THEN
    SELECT count(*) INTO n FROM plat.item_grupo WHERE grupo_id = NEW.grupo_id AND destaque AND item_id <> NEW.item_id;
    IF n >= 24 THEN RAISE EXCEPTION 'limite_destaques'; END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS item_grupo_coerente ON plat.item_grupo;
CREATE TRIGGER item_grupo_coerente BEFORE INSERT OR UPDATE ON plat.item_grupo FOR EACH ROW EXECUTE FUNCTION plat.tg_item_grupo();

CREATE TABLE IF NOT EXISTS plat.compartilhamento_link (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  item_id          uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  token_hash       text NOT NULL UNIQUE,
  prefixo          text NOT NULL,
  nome             text CHECK (length(nome) <= 128),
  criado_por       int NOT NULL REFERENCES plat.usuario(id),
  criado_em        timestamptz NOT NULL DEFAULT now(),
  expira_em        timestamptz,
  revogado_em      timestamptz,
  revogado_por     int,
  acessos          bigint NOT NULL DEFAULT 0,
  ultimo_acesso_em timestamptz,
  ultimo_ip        text,
  permite_download boolean NOT NULL DEFAULT false,
  CHECK (expira_em IS NULL OR expira_em <= criado_em + interval '365 days')
);
CREATE INDEX IF NOT EXISTS ix_link_item ON plat.compartilhamento_link (item_id) WHERE revogado_em IS NULL;
CREATE TABLE IF NOT EXISTS plat.compartilhamento_link_item (
  link_id   uuid NOT NULL REFERENCES plat.compartilhamento_link(id) ON DELETE CASCADE,
  item_id   uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  tenant_id int NOT NULL,
  PRIMARY KEY (link_id, item_id)
);

CREATE TABLE IF NOT EXISTS plat.favorito (
  usuario_id int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  item_id    uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  tenant_id  int NOT NULL,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (usuario_id, item_id)
);
CREATE INDEX IF NOT EXISTS ix_favorito_item ON plat.favorito (item_id);

-- ---------------------------------------------------------------- 18.8 pode_ler / pode_editar / link_resolver e RLS
CREATE OR REPLACE FUNCTION plat.pode_ler(p_item uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT EXISTS (
    SELECT 1 FROM plat.item i
    WHERE i.id = p_item
      AND i.tenant_id = plat.tenant_atual()
      AND (i.apagado_em IS NULL OR current_setting('plat.lixeira', true) = 'on')
      AND (
           -- link anônimo: só os itens listados no link desta requisição
           (plat.usuario_atual() IS NULL AND i.id::text = ANY (string_to_array(current_setting('plat.link_itens', true), ',')))
        OR -- público (anônimo ou autenticado), só com o inquilino autorizando
           (i.acesso = 'publico' AND plat.tenant_permite_publico(i.tenant_id))
        OR -- console do superadmin (variável + usuário superadmin real)
           plat.modo_superadmin()
        OR -- usuário autenticado DO inquilino
           (plat.usuario_do_inquilino() AND (
                i.dono_id = plat.usuario_atual()
             OR plat.tem('conteudo.ver_tudo')
             OR (i.acesso = 'inquilino' AND plat.tem('conteudo.ver_inquilino'))
             OR EXISTS (SELECT 1 FROM plat.item_grupo ig JOIN plat.grupo_membro gm
                          ON gm.grupo_id = ig.grupo_id AND gm.usuario_id = plat.usuario_atual() AND gm.estado = 'ativo'
                        WHERE ig.item_id = i.id)))
      )
  )
$$;

CREATE OR REPLACE FUNCTION plat.pode_editar(p_item uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT plat.usuario_atual() IS NOT NULL AND plat.usuario_do_inquilino() AND EXISTS (
    SELECT 1 FROM plat.item i
    WHERE i.id = p_item AND i.tenant_id = plat.tenant_atual()
      AND (i.dono_id = plat.usuario_atual()
        OR plat.tem('conteudo.editar_tudo')
        OR EXISTS (SELECT 1 FROM plat.item_grupo ig JOIN plat.grupo g ON g.id = ig.grupo_id AND g.atualizacao_compartilhada
                   JOIN plat.grupo_membro gm ON gm.grupo_id = g.id AND gm.usuario_id = plat.usuario_atual() AND gm.estado = 'ativo'
                   WHERE ig.item_id = i.id)))
$$;

-- pré-contexto (o hash é o segredo): devolve o link e conta o acesso quando válido
CREATE OR REPLACE FUNCTION plat.link_resolver(p_hash text, p_ip text)
RETURNS TABLE (motivo text, tenant_id int, item_id uuid, itens_incluidos uuid[], permite_download boolean, link_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE l plat.compartilhamento_link; inc uuid[];
BEGIN
  SELECT * INTO l FROM plat.compartilhamento_link k WHERE k.token_hash = p_hash;
  IF l.id IS NULL THEN RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, NULL::uuid; RETURN; END IF;
  IF l.revogado_em IS NOT NULL THEN RETURN QUERY SELECT 'revogado', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, l.id; RETURN; END IF;
  IF l.expira_em IS NOT NULL AND l.expira_em <= now() THEN RETURN QUERY SELECT 'expirado', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, l.id; RETURN; END IF;
  IF EXISTS (SELECT 1 FROM plat.item i JOIN plat.tenant t ON t.id = i.tenant_id WHERE i.id = l.item_id AND (i.apagado_em IS NOT NULL OR NOT t.ativo)) THEN
    RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::uuid[], NULL::boolean, l.id; RETURN;
  END IF;
  UPDATE plat.compartilhamento_link SET acessos = acessos + 1, ultimo_acesso_em = now(), ultimo_ip = p_ip WHERE id = l.id;
  SELECT coalesce(array_agg(li.item_id), '{}'::uuid[]) INTO inc FROM plat.compartilhamento_link_item li
    JOIN plat.item i ON i.id = li.item_id AND i.apagado_em IS NULL WHERE li.link_id = l.id;
  RETURN QUERY SELECT 'ok', l.tenant_id, l.item_id, ARRAY[l.item_id] || inc, l.permite_download, l.id;
END $$;

ALTER TABLE plat.item ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_item_ler ON plat.item;
CREATE POLICY p_item_ler ON plat.item FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual() AND plat.pode_ler(id));
DROP POLICY IF EXISTS p_item_inserir ON plat.item;
CREATE POLICY p_item_inserir ON plat.item FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_atual() IS NOT NULL AND dono_id = plat.usuario_atual()
              AND plat.usuario_do_inquilino() AND plat.tem('conteudo.criar'));
DROP POLICY IF EXISTS p_item_alterar ON plat.item;
CREATE POLICY p_item_alterar ON plat.item FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(id)) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_item_apagar ON plat.item;
CREATE POLICY p_item_apagar ON plat.item FOR DELETE TO plat_app USING (false);

ALTER TABLE plat.item_versao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_item_versao ON plat.item_versao;
CREATE POLICY p_item_versao ON plat.item_versao FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual() AND plat.pode_ler(item_id));

ALTER TABLE plat.item_relacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_item_relacao ON plat.item_relacao;
CREATE POLICY p_item_relacao ON plat.item_relacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_ler(origem)) WITH CHECK (tenant_id = plat.tenant_atual());

ALTER TABLE plat.item_grupo ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_item_grupo_ler ON plat.item_grupo;
CREATE POLICY p_item_grupo_ler ON plat.item_grupo FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (plat.pode_ler(item_id)
         OR EXISTS (SELECT 1 FROM plat.grupo_membro m WHERE m.grupo_id = grupo_id AND m.usuario_id = plat.usuario_atual() AND m.estado = 'ativo')));
DROP POLICY IF EXISTS p_item_grupo_inserir ON plat.item_grupo;
CREATE POLICY p_item_grupo_inserir ON plat.item_grupo FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id));
DROP POLICY IF EXISTS p_item_grupo_alterar ON plat.item_grupo;
CREATE POLICY p_item_grupo_alterar ON plat.item_grupo FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id)) WITH CHECK (tenant_id = plat.tenant_atual());
DROP POLICY IF EXISTS p_item_grupo_apagar ON plat.item_grupo;
CREATE POLICY p_item_grupo_apagar ON plat.item_grupo FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id));

ALTER TABLE plat.compartilhamento_link ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_link ON plat.compartilhamento_link;
CREATE POLICY p_link ON plat.compartilhamento_link FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id)) WITH CHECK (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id));
ALTER TABLE plat.compartilhamento_link_item ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_link_item ON plat.compartilhamento_link_item;
CREATE POLICY p_link_item ON plat.compartilhamento_link_item FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND EXISTS (SELECT 1 FROM plat.compartilhamento_link k WHERE k.id = link_id))
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id));

ALTER TABLE plat.favorito ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_favorito ON plat.favorito;
CREATE POLICY p_favorito ON plat.favorito FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual())
  WITH CHECK (tenant_id = plat.tenant_atual() AND usuario_id = plat.usuario_atual() AND plat.pode_ler(item_id));

-- item público (D24): inquilino do item quando o item é público, não está na lixeira e o inquilino autoriza
CREATE OR REPLACE FUNCTION plat.tenant_publico_itens(p_item uuid) RETURNS TABLE (id int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT t.id FROM plat.item i JOIN plat.tenant t ON t.id = i.tenant_id
  WHERE i.id = p_item AND i.acesso = 'publico' AND i.apagado_em IS NULL AND t.ativo AND plat.tenant_permite_publico(t.id)
$$;

-- ---------------------------------------------------------------- grafo de dependências (5.4): funções com pode_ler por linha
-- usado_por: origens que dependem de p_item (direta ou indiretamente), até p_prof níveis; `visivel` = pode_ler do ator
CREATE OR REPLACE FUNCTION plat.item_usado_por(p_item uuid, p_prof int DEFAULT 2)
RETURNS TABLE (id uuid, tipo_relacao text, profundidade int, caminho uuid[], visivel boolean, apaga_junto boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  WITH RECURSIVE dep AS (
    SELECT r.origem AS id, r.tipo, 1 AS profundidade, ARRAY[p_item, r.origem] AS caminho, rt.apaga_junto
      FROM plat.item_relacao r JOIN plat.relacao_tipo rt ON rt.nome = r.tipo
     WHERE r.destino = p_item AND r.tenant_id = plat.tenant_atual()
    UNION ALL
    SELECT r.origem, r.tipo, dep.profundidade + 1, dep.caminho || r.origem, rt.apaga_junto
      FROM dep JOIN plat.item_relacao r ON r.destino = dep.id JOIN plat.relacao_tipo rt ON rt.nome = r.tipo
     WHERE dep.profundidade < least(p_prof, 20) AND NOT r.origem = ANY (dep.caminho)
  )
  SELECT DISTINCT ON (dep.id) dep.id, dep.tipo, dep.profundidade, dep.caminho, plat.pode_ler(dep.id), dep.apaga_junto
  FROM dep JOIN plat.item i ON i.id = dep.id AND i.apagado_em IS NULL
  WHERE plat.pode_ler(p_item)
  ORDER BY dep.id, dep.profundidade
$$;

-- criado_a_partir_de: destinos de que p_item depende (um nível)
CREATE OR REPLACE FUNCTION plat.item_criado_a_partir_de(p_item uuid)
RETURNS TABLE (id uuid, tipo_relacao text, posicao int, visivel boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT r.destino, r.tipo, r.posicao, plat.pode_ler(r.destino)
  FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL
  WHERE r.origem = p_item AND r.tenant_id = plat.tenant_atual() AND plat.pode_ler(p_item)
  ORDER BY r.posicao NULLS LAST, r.criado_em
$$;

CREATE OR REPLACE FUNCTION plat.item_contagens(p_item uuid)
RETURNS TABLE (usado_por int, criado_a_partir_de int, grupos int, links_ativos int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT (SELECT count(*)::int FROM plat.item_relacao r JOIN plat.item i ON i.id = r.origem AND i.apagado_em IS NULL WHERE r.destino = p_item),
         (SELECT count(*)::int FROM plat.item_relacao r JOIN plat.item i ON i.id = r.destino AND i.apagado_em IS NULL WHERE r.origem = p_item),
         (SELECT count(*)::int FROM plat.item_grupo ig WHERE ig.item_id = p_item),
         (SELECT count(*)::int FROM plat.compartilhamento_link k WHERE k.item_id = p_item AND k.revogado_em IS NULL
             AND (k.expira_em IS NULL OR k.expira_em > now()))
  WHERE plat.pode_ler(p_item)
$$;

-- ---------------------------------------------------------------- 18.9 lixeira, expurgo, compactação, uso
-- exclusão lógica e restauração: quem pode = pode_editar OU conteudo.apagar_tudo OU modo superadmin; o gatilho
-- item_antes aplica a proteção. Devolve true quando agiu; false quando o item não é visível/permitido (rota → 404).
CREATE OR REPLACE FUNCTION plat.item_lixeira(p_item uuid, p_apagar boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int;
BEGIN
  IF plat.tenant_atual() IS NULL OR plat.usuario_atual() IS NULL THEN RETURN false; END IF;
  IF NOT (plat.pode_editar(p_item) OR (plat.usuario_do_inquilino() AND plat.tem('conteudo.apagar_tudo')) OR plat.modo_superadmin()) THEN
    RETURN false;
  END IF;
  IF p_apagar THEN
    UPDATE plat.item SET apagado_em = now(), apagado_por = plat.usuario_atual()
     WHERE id = p_item AND tenant_id = plat.tenant_atual() AND apagado_em IS NULL;
  ELSE
    UPDATE plat.item SET apagado_em = NULL, apagado_por = NULL
     WHERE id = p_item AND tenant_id = plat.tenant_atual() AND apagado_em IS NOT NULL;
  END IF;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;

-- itens a expurgar: apagados há mais de p_dias (relógio p_agora, só em dev pela API). Fora do inquilino técnico
-- `plataforma`, só o inquilino do contexto; p_ids restringe (esvaziar lixeira).
CREATE OR REPLACE FUNCTION plat.lixeira_expurgar(p_dias int DEFAULT 30, p_agora timestamptz DEFAULT now(), p_ids uuid[] DEFAULT NULL)
RETURNS TABLE (item_id uuid, tenant_id int, tipo text, dados jsonb, miniatura_chave text, tamanho_bytes bigint, titulo text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY
    SELECT i.id, i.tenant_id, i.tipo, i.dados, i.miniatura_chave, i.tamanho_bytes, i.titulo
    FROM plat.item i
    WHERE i.apagado_em IS NOT NULL AND i.apagado_em < p_agora - make_interval(days => p_dias)
      AND (t_plataforma OR i.tenant_id = t_ctx)
      AND (p_ids IS NULL OR i.id = ANY (p_ids))
    ORDER BY i.apagado_em;
END $$;

-- DELETE físico com cascatas (versões, relações, grupos, links, favoritos); só de item já na lixeira, do inquilino
-- do contexto (ou de qualquer um quando o contexto é o inquilino técnico `plataforma`, onde o periódico roda)
CREATE OR REPLACE FUNCTION plat.item_expurgar(p_item uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE n int; t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  DELETE FROM plat.item WHERE id = p_item AND apagado_em IS NOT NULL AND (t_plataforma OR tenant_id = t_ctx);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;

-- mantém as p_manter versões mais recentes; das mais antigas, cada bloco de 10 vira uma linha (a mais recente,
-- rotulo compactada, compactou = tamanho do bloco). Devolve quantas linhas foram removidas.
CREATE OR REPLACE FUNCTION plat.item_versoes_compactar(p_item uuid, p_manter int DEFAULT 50) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE corte int; removidas int := 0; r record; bloco int[]; n int;
BEGIN
  SELECT versao INTO corte FROM plat.item_versao WHERE item_id = p_item ORDER BY versao DESC OFFSET p_manter LIMIT 1;
  IF corte IS NULL THEN RETURN 0; END IF;
  FOR r IN SELECT array_agg(versao ORDER BY versao) AS vs, max(versao) AS topo,
                  sum(greatest(compactou, 1))::int AS resumidas
           FROM (SELECT versao, compactou, (row_number() OVER (ORDER BY versao) - 1) / 10 AS grupo
                 FROM plat.item_versao WHERE item_id = p_item AND versao <= corte) x
           GROUP BY grupo HAVING count(*) > 1 LOOP
    DELETE FROM plat.item_versao WHERE item_id = p_item AND versao = ANY (r.vs) AND versao <> r.topo;
    GET DIAGNOSTICS n = ROW_COUNT;
    removidas := removidas + n;
    UPDATE plat.item_versao SET rotulo = 'compactada', compactou = r.resumidas WHERE item_id = p_item AND versao = r.topo;
  END LOOP;
  RETURN removidas;
END $$;

-- itens com mais de p_manter versões (o periódico percorre); fora do inquilino técnico, só o próprio
CREATE OR REPLACE FUNCTION plat.itens_com_versoes_acima(p_manter int DEFAULT 50) RETURNS SETOF uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE t_plataforma boolean; t_ctx int := plat.tenant_atual();
BEGIN
  IF t_ctx IS NULL THEN RAISE EXCEPTION 'evento_sem_contexto'; END IF;
  SELECT slug = 'plataforma' INTO t_plataforma FROM plat.tenant WHERE id = t_ctx;
  RETURN QUERY SELECT v.item_id FROM plat.item_versao v WHERE (t_plataforma OR v.tenant_id = t_ctx)
               GROUP BY v.item_id HAVING count(*) > p_manter;
END $$;

CREATE OR REPLACE FUNCTION plat.catalogo_uso(p_tenant int)
RETURNS TABLE (itens bigint, na_lixeira bigint, bytes bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT count(*) FILTER (WHERE apagado_em IS NULL), count(*) FILTER (WHERE apagado_em IS NOT NULL),
         coalesce(sum(tamanho_bytes), 0)::bigint
  FROM plat.item WHERE tenant_id = p_tenant
$$;

-- cota de itens do inquilino (D16): tenant.config.catalogo.cota_itens, padrão 100.000
CREATE OR REPLACE FUNCTION plat.cota_itens(p_tenant int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT coalesce((config->'catalogo'->>'cota_itens')::int, 100000) FROM plat.tenant WHERE id = p_tenant
$$;

-- ---------------------------------------------------------------- 18.10 eventos (seção 12)
INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('itens/adicionar', 'item criado'),
  ('itens/atualizar', 'metadado ou dados do item alterados (propriedades.campos, versao)'),
  ('itens/apagar', 'item enviado à lixeira (forcado, cascata)'),
  ('itens/restaurar', 'item restaurado da lixeira'),
  ('itens/mover', 'item movido de pasta (de_pasta, para_pasta)'),
  ('itens/transferir', 'dono do item transferido (de, para, arrastados)'),
  ('itens/status', 'status do item alterado (de, para)'),
  ('itens/proteger', 'proteção contra exclusão ligada'),
  ('itens/desproteger', 'proteção contra exclusão desligada'),
  ('itens/miniatura', 'miniatura enviada, gerada ou removida'),
  ('itens/versao_restaurar', 'versão anterior restaurada (versao)'),
  ('itens/versao_publicar', 'versão publicada apontada'),
  ('itens/dados_migrar', 'dados migrados para esquema novo do tipo'),
  ('itens/relacoes', 'relações do item sincronizadas'),
  ('compartilhamento/alterar', 'nível de acesso ou grupos alterados (antes, depois)'),
  ('compartilhamento/link_criar', 'link por token criado (link_id, prefixo, itens_incluidos)'),
  ('compartilhamento/link_revogar', 'link por token revogado'),
  ('compartilhamento/link_acesso', 'primeiro acesso ao link (o contador vive em compartilhamento_link)'),
  ('pastas/criar', 'pasta criada'),
  ('pastas/renomear', 'pasta renomeada'),
  ('pastas/mover', 'pasta movida'),
  ('pastas/apagar', 'pasta apagada'),
  ('categorias/alterar', 'árvore de categorias alterada (antes, depois)'),
  ('categorias/importar', 'modelo de categorias importado (modelo, criadas)'),
  ('favoritos/adicionar', 'item favoritado'),
  ('favoritos/remover', 'favorito removido'),
  ('lixeira/expurgar', 'item expurgado fisicamente (item_id, tipo, bytes_liberados)'),
  ('lixeira/esvaziar', 'esvaziamento da lixeira pedido (job)')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- 18.12 permissões: grant EXPLÍCITO por função do catálogo
-- (nunca ON ALL FUNCTIONS depois da 006: as funções do worker só têm EXECUTE para plat_worker; regra da 013)
DO $$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'plat.tags_texto(text[])', 'plat.tags_validas(text[])', 'plat.eh_superadmin()', 'plat.modo_superadmin()',
    'plat.tenant_permite_publico(int)', 'plat.usuario_do_inquilino()', 'plat.categorias_max(int)',
    'plat.item_pontuacao(plat.item)', 'plat.item_retrato(plat.item)', 'plat.pode_ler(uuid)', 'plat.pode_editar(uuid)',
    'plat.link_resolver(text, text)', 'plat.tenant_publico_itens(uuid)', 'plat.item_usado_por(uuid, int)',
    'plat.item_criado_a_partir_de(uuid)', 'plat.item_contagens(uuid)', 'plat.item_lixeira(uuid, boolean)',
    'plat.lixeira_expurgar(int, timestamptz, uuid[])', 'plat.item_expurgar(uuid)', 'plat.item_versoes_compactar(uuid, int)',
    'plat.itens_com_versoes_acima(int)', 'plat.catalogo_uso(int)', 'plat.cota_itens(int)'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO plat_app', f);
  END LOOP;
  -- funções de gatilho: disparam pelo gatilho, nunca por chamada direta
  FOREACH f IN ARRAY ARRAY['plat.tg_pasta_caminho()', 'plat.tg_pasta_vazia()', 'plat.tg_categoria()', 'plat.tg_item_antes()',
                           'plat.tg_item_versao()', 'plat.tg_item_relacao()', 'plat.tg_item_grupo()'] LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, plat_app', f);
  END LOOP;
END $$;
GRANT SELECT ON plat.tipo_item, plat.relacao_tipo TO plat_app;
GRANT SELECT ON plat.item_versao TO plat_app;
