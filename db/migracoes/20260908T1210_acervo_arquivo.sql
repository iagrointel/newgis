-- 20260908T1210_acervo_arquivo: camadas de ARQUIVO do acervo da casa no catálogo (item L6-01-i-raster-e-arquivos;
-- L3L6_CONCEITO B1/B2/B5). A migração 021 trouxe a FICHA de fonte e a 027 o registro de camada em TABELA; falta o
-- terceiro corpo do acervo: os arquivos com sha256 (`acervo.camada_arquivo`, medido 08/09/2026: 321 linhas, 27
-- fontes nomeadas + 121 linhas sem fonte, 3,6 GB, 100 % com sha256 — 18 raster .tif e 303 vetoriais/tabulares).
--
-- `plat.acervo_arquivo` é a vista de leitura (security_invoker, como plat.acervo_ficha). Diferença DECLARADA em
-- relação à 021: aquela filtra `licenca IS NOT NULL` (D17) porque lista FONTE para qualquer inquilino; aqui a
-- linha aparece SEM licença também, com `publicavel=false` — medido em 08/09/2026: NENHUMA das 27 fontes de
-- arquivo tem licença escrita, logo o filtro da 021 deixaria a lista vazia e o acervo de arquivo invisível
-- inclusive para a casa. A regra D17 continua valendo no lugar onde ela decide: a rota de exposição cria item
-- PRIVADO e marcado `uso_restrito` quando não há licença escrita, e o compartilhamento desse item é recusado.
--
-- `plat.acervo_arquivo_exposto` guarda o que cada inquilino expôs: caminho, item criado, sha256 CONFERIDO no
-- momento da exposição (não o do registro) e o instante. RLS por inquilino. Idempotente. Sem BEGIN/COMMIT.
GRANT SELECT ON acervo.camada_arquivo TO plat_app;

CREATE OR REPLACE VIEW plat.acervo_arquivo WITH (security_invoker = true) AS
SELECT a.caminho,
       a.base                                        AS nome,
       a.fonte_id,
       f.nome                                        AS fonte_nome,
       f.orgao,
       f.dominio,
       f.licenca,
       f.frescor,
       f.data_dado,
       f.script_gerador,
       f.sha256_cmd                                  AS comando_reexecucao,
       a.bytes,
       a.sha256,
       a.mtime,
       a.feicoes,
       a.srid,
       a.tipo_geom,
       lower(regexp_replace(a.caminho, '.*\.', ''))  AS extensao,
       CASE WHEN lower(regexp_replace(a.caminho, '.*\.', '')) IN ('tif', 'tiff', 'vrt')
            THEN 'raster' ELSE 'vetor' END           AS tipo,
       (f.licenca IS NOT NULL)                       AS publicavel
FROM acervo.camada_arquivo a
LEFT JOIN acervo.fonte f ON f.fonte_id = a.fonte_id;

GRANT SELECT ON plat.acervo_arquivo TO plat_app;

CREATE TABLE IF NOT EXISTS plat.acervo_arquivo_exposto (
  tenant_id        int NOT NULL REFERENCES plat.tenant(id) ON DELETE CASCADE,
  caminho          text NOT NULL,
  item_id          uuid NOT NULL REFERENCES plat.item(id) ON DELETE CASCADE,
  tipo             text NOT NULL CHECK (tipo IN ('raster', 'vetor')),
  sha256_registro  text NOT NULL,   -- o que o registro do acervo dizia
  sha256_conferido text NOT NULL,   -- o que a leitura do arquivo calculou na exposição (iguais, senão recusa)
  bytes            bigint,
  publicavel       boolean NOT NULL DEFAULT false,
  exposto_em       timestamptz NOT NULL DEFAULT now(),
  exposto_por      int REFERENCES plat.usuario(id) ON DELETE SET NULL,
  PRIMARY KEY (tenant_id, caminho)
);
CREATE INDEX IF NOT EXISTS acervo_arquivo_exposto_item_ix ON plat.acervo_arquivo_exposto (item_id);
ALTER TABLE plat.acervo_arquivo_exposto ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat.acervo_arquivo_exposto FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_acervo_arquivo_exposto ON plat.acervo_arquivo_exposto;
CREATE POLICY p_acervo_arquivo_exposto ON plat.acervo_arquivo_exposto FOR ALL TO plat_app, plat_worker
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
GRANT SELECT, INSERT, DELETE ON plat.acervo_arquivo_exposto TO plat_app, plat_worker;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('acervo/arquivo_expor', 'arquivo do acervo da casa exposto no catálogo (sha256 conferido antes de ingerir)'),
  ('acervo/arquivo_recusar', 'exposição de arquivo do acervo recusada (hash divergente, tamanho ou ausente)'),
  ('acervo/arquivo_remover', 'item de arquivo do acervo removido do catálogo do inquilino')
ON CONFLICT (nome) DO NOTHING;
