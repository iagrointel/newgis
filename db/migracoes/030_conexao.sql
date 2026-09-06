-- 030_conexao: modelo genérico de CONEXÃO externa (item L6-02-a-modelo-conexao-e-seguranca; ADR 0012; decisão
-- B6/B7 de laco/decomposicao/L3L6_CONCEITO.md). Só o MODELO e a defesa de segurança nesta trilha — os 15
-- conectores concretos (WMS, WFS, WMTS, OGC API, ArcGIS REST, STAC, GeoParquet, PMTiles, ...) são itens
-- futuros (L6-02-b em diante) que leem/escrevem esta MESMA tabela, cada um com seu `config` validado por
-- `app/conexao/tipos.py`.
--
-- Diferente de `plat.acervo_ficha` (021) e `plat.acervo_camada` (027), que são REGISTRO GLOBAL do acervo da
-- CASA (só leitura, sem tenant): `plat.conexao` é dado do INQUILINO (tenant_id + RLS) — cada inquilino guarda
-- as próprias conexões a serviço de terceiro, com a própria credencial.
--
-- A credencial nunca é lida pela API depois de gravada (`app/conexao/rotas.py` nunca faz SELECT da coluna
-- `credencial_cifrada` para responder um GET; só o processo de teste de saúde e o proxy do conector a
-- decifram, em memória, para autenticar contra o serviço externo). Cifrada com AES-GCM
-- (`app/conexao/credencial.py`, prefixo `encconexao:v1:`), chave derivada de PLAT_SECRET — nunca `pgp_sym_encrypt`
-- (a chave ficaria dentro do próprio SQL de cada chamada, visível em log de consulta lenta; o padrão desta
-- casa, já usado no TOTP e no bind LDAP, cifra em Python antes do INSERT).
--
-- Numeração 030 (029 = ingestao_vetor). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

-- vocabulário fechado de tipo: mesma lista de app/limites.py CONEXAO_TIPOS (Map Viewer 11.4 "add-layers-mv.htm"
-- + STAC/GeoParquet/PMTiles da spec da casa + bancos externos, decisão B6/B8) — as duas listas mudam juntas.
CREATE TABLE IF NOT EXISTS plat.conexao (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            int NOT NULL REFERENCES plat.tenant(id),
  tipo                 text NOT NULL CHECK (tipo IN (
                         'wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles',
                         'postgres_fdw', 's3', 'http'
                       )),
  modo                 text NOT NULL DEFAULT 'referenciada' CHECK (modo IN ('referenciada', 'copiada')),
  nome                 text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  url                  text NOT NULL CHECK (btrim(url) <> '' AND length(url) <= 2048),
  config               jsonb NOT NULL DEFAULT '{}'::jsonb,
  credencial_cifrada   text,                     -- AES-GCM 'encconexao:v1:' (app/conexao/credencial.py); NUNCA texto puro
  saude                text NOT NULL DEFAULT 'nunca_testada' CHECK (saude IN ('nunca_testada', 'ok', 'erro')),
  saude_mensagem       text,
  saude_verificada_em  timestamptz,
  saude_latencia_ms    int,
  dono_id              int NOT NULL REFERENCES plat.usuario(id),
  criado_em            timestamptz NOT NULL DEFAULT now(),
  atualizado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_conexao_tenant ON plat.conexao (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_conexao_nome ON plat.conexao (tenant_id, lower(nome));

CREATE OR REPLACE FUNCTION plat.tg_conexao_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS conexao_atualizado_em ON plat.conexao;
CREATE TRIGGER conexao_atualizado_em BEFORE UPDATE ON plat.conexao FOR EACH ROW EXECUTE FUNCTION plat.tg_conexao_atualizado_em();

ALTER TABLE plat.conexao ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_conexao_ler ON plat.conexao;
CREATE POLICY p_conexao_ler ON plat.conexao FOR SELECT TO plat_app
  USING (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_conexao_inserir ON plat.conexao;
CREATE POLICY p_conexao_inserir ON plat.conexao FOR INSERT TO plat_app
  WITH CHECK (tenant_id = plat.tenant_atual() AND dono_id = plat.usuario_atual() AND plat.usuario_do_inquilino());

DROP POLICY IF EXISTS p_conexao_alterar ON plat.conexao;
CREATE POLICY p_conexao_alterar ON plat.conexao FOR UPDATE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')))
  WITH CHECK (tenant_id = plat.tenant_atual());

DROP POLICY IF EXISTS p_conexao_apagar ON plat.conexao;
CREATE POLICY p_conexao_apagar ON plat.conexao FOR DELETE TO plat_app
  USING (tenant_id = plat.tenant_atual() AND (dono_id = plat.usuario_atual() OR plat.tem('conteudo.editar_tudo')));

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('conexoes/criar', 'conexão externa criada (tipo, nome, modo)'),
  ('conexoes/editar', 'conexão externa editada (campos alterados)'),
  ('conexoes/apagar', 'conexão externa apagada (nome)'),
  ('conexoes/testar', 'teste de saúde da conexão executado (ok, status, mensagem)')
ON CONFLICT (nome) DO NOTHING;
