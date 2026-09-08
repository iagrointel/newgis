-- item L5-14-publicacao-links-embed (ADR 0018-publicacao-links-embed): publicar um documento de construtor
-- (família app/painel) numa URL pública /p/<inquilino>/<slug> que lê SÓ a versão apontada por
-- plat.item.versao_publicada; acesso público, ou por link-com-token (reaproveita plat.link_resolver); dado
-- servido ao vivo é lido por um token de serviço PRÓPRIO da publicação, escopado às camadas citadas pelo
-- documento (plat.item_relacao, calculado em Python — app/catalogo/publicacao.py), revogável e restrito por
-- domínio (plat.token_servico.restricao.referer, mecanismo já existente do L0-02/L1-02); contagem de
-- visualização por dia.

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('publicacao/publicar', 'documento de construtor publicado ou republicado em /p/<inquilino>/<slug>'),
  ('publicacao/despublicar', 'publicação removida (token do app revogado, slug liberado)')
ON CONFLICT (nome) DO NOTHING;

CREATE TABLE IF NOT EXISTS plat.item_publicacao (
    item_id             uuid PRIMARY KEY REFERENCES plat.item(id) ON DELETE CASCADE,
    tenant_id           integer NOT NULL REFERENCES plat.tenant(id),
    slug                text NOT NULL,
    dominios_permitidos text[] NOT NULL DEFAULT '{}',
    token_id            integer REFERENCES plat.token_servico(id) ON DELETE SET NULL,
    token_valor         text,  -- "chave publicável": visível a qualquer visitante da página pública por definição
                                -- (vai embutida no HTML/JS servido); o segredo de autorização é o escopo+restrição
                                -- da linha em plat.token_servico (hash), não o sigilo deste valor. Ver ADR seção 3.
    publicado_por       integer REFERENCES plat.usuario(id),
    publicado_em        timestamptz NOT NULL DEFAULT now(),
    atualizado_em       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT item_publicacao_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,58}[a-z0-9]$'),
    CONSTRAINT item_publicacao_dominios_check CHECK (cardinality(dominios_permitidos) <= 20)
);

CREATE UNIQUE INDEX IF NOT EXISTS item_publicacao_tenant_slug_uk ON plat.item_publicacao(tenant_id, slug);

CREATE TABLE IF NOT EXISTS plat.item_publicacao_visualizacao (
    item_id        uuid NOT NULL REFERENCES plat.item_publicacao(item_id) ON DELETE CASCADE,
    dia            date NOT NULL,
    visualizacoes  integer NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, dia)
);

ALTER TABLE plat.item_publicacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_item_publicacao ON plat.item_publicacao;
CREATE POLICY p_item_publicacao ON plat.item_publicacao FOR ALL TO plat_app
  USING (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id))
  WITH CHECK (tenant_id = plat.tenant_atual() AND plat.pode_editar(item_id));

ALTER TABLE plat.item_publicacao_visualizacao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_item_publicacao_visualizacao ON plat.item_publicacao_visualizacao;
CREATE POLICY p_item_publicacao_visualizacao ON plat.item_publicacao_visualizacao FOR SELECT TO plat_app
  USING (EXISTS (SELECT 1 FROM plat.item_publicacao p
                 WHERE p.item_id = item_publicacao_visualizacao.item_id
                   AND p.tenant_id = plat.tenant_atual() AND plat.pode_editar(p.item_id)));

-- revoga o token do app sempre que a linha de publicação some — inclusive por CASCADE quando o item é
-- apagado de vez (plat.item_expurgar): sem isto o token fica órfão, não revogado, e continua contando
-- para o teto de plat.limites.TOKENS_POR_USUARIO do dono (achado ao rodar a suíte: 3 rodadas de teste
-- sem isto esgotaram os 20 tokens do admin de demonstração e derrubaram testes de OUTROS itens).
CREATE OR REPLACE FUNCTION plat.tg_item_publicacao_revogar_token() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
BEGIN
  IF OLD.token_id IS NOT NULL THEN
    UPDATE plat.token_servico SET revogado_em = now() WHERE id = OLD.token_id AND revogado_em IS NULL;
  END IF;
  RETURN OLD;
END $$;

DROP TRIGGER IF EXISTS item_publicacao_revogar_token ON plat.item_publicacao;
CREATE TRIGGER item_publicacao_revogar_token BEFORE DELETE ON plat.item_publicacao
  FOR EACH ROW EXECUTE FUNCTION plat.tg_item_publicacao_revogar_token();
-- função de gatilho: dispara pelo gatilho, nunca por chamada direta (mesma regra da 011_catalogo.sql seção 18.12)
REVOKE EXECUTE ON FUNCTION plat.tg_item_publicacao_revogar_token() FROM PUBLIC, plat_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.item_publicacao TO plat_app;
GRANT SELECT ON plat.item_publicacao_visualizacao TO plat_app;  -- escrita só pela função SECURITY DEFINER abaixo
REVOKE INSERT, UPDATE, DELETE ON plat.item_publicacao_visualizacao FROM plat_app;

-- pré-contexto público (o mesmo desenho de plat.link_resolver/tenant_publico_itens, ADR 0004 seção 18.8):
-- resolve <inquilino>/<slug>, exige versão publicada, incrementa a visualização do dia.
CREATE OR REPLACE FUNCTION plat.publicacao_resolver(p_tenant_slug text, p_slug text)
RETURNS TABLE (motivo text, tenant_id int, item_id uuid, versao int, dominios_permitidos text[], acesso text,
               token_valor text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
#variable_conflict use_column
-- sem isto, "item_id" no INSERT/ON CONFLICT abaixo fica ambíguo: o próprio RETURNS TABLE desta função
-- declara uma saída chamada "item_id", que o plpgsql expõe como variável e colide com a coluna da
-- tabela dentro do INSERT (achado ao rodar o teste, não hipotético).
DECLARE p plat.item_publicacao%ROWTYPE; it plat.item%ROWTYPE; t plat.tenant%ROWTYPE;
BEGIN
  SELECT tt.* INTO t FROM plat.tenant tt WHERE tt.slug = p_tenant_slug;
  IF t.id IS NULL OR NOT t.ativo THEN
    RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::int, NULL::text[], NULL::text, NULL::text; RETURN;
  END IF;
  SELECT pp.* INTO p FROM plat.item_publicacao pp WHERE pp.tenant_id = t.id AND pp.slug = p_slug;
  IF p.item_id IS NULL THEN
    RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::int, NULL::text[], NULL::text, NULL::text; RETURN;
  END IF;
  SELECT ii.* INTO it FROM plat.item ii WHERE ii.id = p.item_id;
  IF it.id IS NULL OR it.apagado_em IS NOT NULL OR it.versao_publicada IS NULL THEN
    RETURN QUERY SELECT 'inexistente', NULL::int, NULL::uuid, NULL::int, NULL::text[], NULL::text, NULL::text; RETURN;
  END IF;
  INSERT INTO plat.item_publicacao_visualizacao(item_id, dia, visualizacoes)
    VALUES (p.item_id, (now() AT TIME ZONE 'utc')::date, 1)
  ON CONFLICT (item_id, dia) DO UPDATE SET visualizacoes = plat.item_publicacao_visualizacao.visualizacoes + 1;
  RETURN QUERY SELECT 'ok', t.id, it.id, it.versao_publicada, p.dominios_permitidos, it.acesso, p.token_valor;
END $$;

REVOKE EXECUTE ON FUNCTION plat.publicacao_resolver(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.publicacao_resolver(text, text) TO plat_app;

-- só os domínios (sem incrementar visualização): usado para decidir o cabeçalho frame-ancestors da CASCA
-- HTML antes de o front pedir o documento (que aí sim conta a visualização, uma vez por carregamento).
CREATE OR REPLACE FUNCTION plat.publicacao_dominios(p_tenant_slug text, p_slug text)
RETURNS TABLE (encontrado boolean, dominios_permitidos text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT true, p.dominios_permitidos
  FROM plat.item_publicacao p JOIN plat.tenant t ON t.id = p.tenant_id JOIN plat.item i ON i.id = p.item_id
  WHERE t.slug = p_tenant_slug AND p.slug = p_slug AND t.ativo AND i.apagado_em IS NULL AND i.versao_publicada IS NOT NULL
$$;

REVOKE EXECUTE ON FUNCTION plat.publicacao_dominios(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.publicacao_dominios(text, text) TO plat_app;

-- visão só de leitura para o dono editar (contagem dos últimos dias, sem função nova por rota)
CREATE OR REPLACE FUNCTION plat.publicacao_visualizacoes(p_item uuid, p_dias int DEFAULT 30)
RETURNS TABLE (dia date, visualizacoes int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = plat, public AS $$
  SELECT v.dia, v.visualizacoes FROM plat.item_publicacao_visualizacao v
  WHERE v.item_id = p_item AND v.dia > (now() AT TIME ZONE 'utc')::date - p_dias AND plat.pode_editar(p_item)
  ORDER BY v.dia DESC
$$;

REVOKE EXECUTE ON FUNCTION plat.publicacao_visualizacoes(uuid, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.publicacao_visualizacoes(uuid, int) TO plat_app;
