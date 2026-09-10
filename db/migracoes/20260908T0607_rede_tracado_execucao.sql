-- Item L4-02-f-resultados-e-exportacao: o HISTÓRICO dos traçados de cada pessoa.
-- depende: 20260908T0145_rede_config_tracado.sql
--
-- Uma EXECUÇÃO é o registro de um traçado que já rodou: o pedido inteiro que foi enviado a
-- POST /api/rede/{id}/tracar (tipo ou configuração, pontos de partida, barreiras, destino), o que ele
-- devolveu em contagem e tempo, e a data. Guarda-se o PEDIDO, nunca o resultado: repetir um traçado é
-- reenviar o mesmo pedido ao motor de sempre, sobre a rede como ela está hoje — um resultado guardado
-- envelheceria em silêncio junto com a rede, e a tela mostraria uma contagem que já não é verdade.
--
-- `topologia_construido_em` grava a data da rodada de "habilitar" que valia quando o traçado rodou: é a
-- versão da topologia, e é o que permite dizer, ao repetir, que a rede mudou desde então.
-- A lista é POR PESSOA (`usuario_id`): "os últimos traçados do usuário", como pede o portão do item.

CREATE TABLE IF NOT EXISTS plat.rede_tracado_execucao (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               int NOT NULL REFERENCES plat.tenant(id),
  rede_id                 uuid NOT NULL,
  usuario_id              int REFERENCES plat.usuario(id),
  tipo                    text NOT NULL CHECK (btrim(tipo) <> '' AND length(tipo) <= 40),
  config_id               uuid,
  pedido                  jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pedido) = 'object'),
  contagem                int,
  duracao_ms              int,
  topologia_construido_em timestamptz,
  criado_em               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS ix_rede_tracado_execucao_recentes
  ON plat.rede_tracado_execucao (rede_id, usuario_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_rede_tracado_execucao_tenant ON plat.rede_tracado_execucao (tenant_id);
ALTER TABLE plat.rede_tracado_execucao DROP CONSTRAINT IF EXISTS rede_tracado_execucao_tenant_rede_fkey;
ALTER TABLE plat.rede_tracado_execucao ADD CONSTRAINT rede_tracado_execucao_tenant_rede_fkey
  FOREIGN KEY (tenant_id, rede_id) REFERENCES plat.rede (tenant_id, id) ON DELETE CASCADE;

-- RLS: mesmo padrão de 20260908T0145.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['rede_tracado_execucao'] LOOP
    EXECUTE format('ALTER TABLE plat.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_ler ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_ler ON plat.%I FOR SELECT TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_inserir ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_inserir ON plat.%I FOR INSERT TO plat_app '
                   'WITH CHECK (tenant_id = plat.tenant_atual() AND plat.usuario_do_inquilino())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_alterar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_alterar ON plat.%I FOR UPDATE TO plat_app '
                   'USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('DROP POLICY IF EXISTS p_%s_apagar ON plat.%I', t, t);
    EXECUTE format('CREATE POLICY p_%s_apagar ON plat.%I FOR DELETE TO plat_app USING (tenant_id = plat.tenant_atual())', t, t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON plat.%I TO plat_app', t);
  END LOOP;
END $$;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('redes/tracar_exportar', 'resultado de traçado exportado (formato, contagem)'),
  ('redes/tracar_camada', 'resultado de traçado salvo como camada do catálogo (item, contagem)')
ON CONFLICT (nome) DO NOTHING;

-- ------------------------------------------------------- tipo de item: a camada salva a partir de um traçado
-- "Salvar como camada" põe o resultado no catálogo. O tipo é PRÓPRIO e não `camada_vetorial`: aquele exige
-- schema e tabela PostGIS, e este não tem tabela nenhuma — é uma FOTOGRAFIA do resultado (elementos,
-- geometria e agregações) com a procedência do traçado que a produziu. Sem dado físico, portanto sem cota.
INSERT INTO plat.tipo_item(nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front,
                           abre_em, tem_dado_fisico, linha_dona) VALUES
  ('camada_tracado', 'camada', 'Camada de traçado',
   'resultado de um traçado de rede de utilidades guardado como camada, com procedência',
   '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,
     "required":["fonte","procedencia","contagem","elementos"],
     "properties":{
       "fonte":{"type":"string","enum":["tracado_de_rede"]},
       "procedencia":{"type":"object","additionalProperties":true},
       "agregacoes":{"type":"object","additionalProperties":true},
       "contagem":{"type":"integer","minimum":0},
       "elementos":{"type":"array","items":{"type":"object","additionalProperties":true}},
       "geometria":{"type":["object","null"],"additionalProperties":true}}}'::jsonb,
   1, 'camada', '/static/js/catalogo/tipos/camada_tracado.js', '{mapa,tabela}', false, 'L4-02')
ON CONFLICT (nome) DO UPDATE SET familia = EXCLUDED.familia, rotulo = EXCLUDED.rotulo,
  descricao = EXCLUDED.descricao, esquema = EXCLUDED.esquema, esquema_versao = EXCLUDED.esquema_versao,
  icone = EXCLUDED.icone, modulo_front = EXCLUDED.modulo_front, abre_em = EXCLUDED.abre_em,
  tem_dado_fisico = EXCLUDED.tem_dado_fisico, linha_dona = EXCLUDED.linha_dona;
