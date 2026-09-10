-- 20260908T1212_modelos3d (item L2-09-c-modelos-gltf-ifc-3dtiles): modelo 3D posicionado no mapa e a
-- tabela de elementos que vem do IFC.
--
-- Duas tabelas e nenhuma tabela por modelo:
--  * `plat.modelo3d`  — um arquivo (GLB enviado, ou IFC convertido) posto num ponto do globo: longitude,
--    latitude, altura elipsoidal, rotação (azimute horário a partir do norte) e escala. O arquivo em si
--    NUNCA fica aqui: fica no armazenamento de objetos por inquilino do L0-11 (`plat.arquivo`), e esta
--    tabela guarda só o sha256 e a classe com que ele foi gravado.
--  * `plat.modelo3d_elemento` — uma LINHA por elemento do IFC, com o identificador global (GUID) que o
--    próprio arquivo carrega. É a chave que liga o clique na tela (o nó do glTF traz `extras.guid`) às
--    propriedades: sem ela o clique só saberia o índice do nó, que muda a cada conversão.
--
-- `propriedades` é jsonb com a forma {conjunto: {campo: valor}} — é assim que o IFC organiza (Pset_/Qto_)
-- e achatar isso perderia de que conjunto veio cada campo.
--
-- `elementos_sem_forma` não é sujeira: é a FILA da decisão D32. Elemento cuja representação geométrica o
-- leitor em Python puro não converte (fronteira genérica, booleana, varredura) entra na tabela com
-- `tem_geometria=false` e espera a conversão pelo IfcOpenShell, que roda no servidor de GPU da casa.
-- Contar 13 elementos e desenhar 11 é o resultado honesto; dizer que o modelo tem 11 elementos não é.
--
-- Também acrescenta `modelos` ao esquema do documento de cena (tipo `cena`, migração 20260908T0601) por
-- `jsonb_set`, sem reescrever o esquema inteiro — a cena passa a poder citar modelos e tilesets.
--
-- Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.

CREATE TABLE IF NOT EXISTS plat.modelo3d (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            int NOT NULL REFERENCES plat.tenant(id),
  nome                 text NOT NULL CHECK (btrim(nome) <> '' AND length(nome) <= 200),
  origem               text NOT NULL CHECK (origem IN ('gltf', 'ifc')),
  arquivo_sha256       text NOT NULL CHECK (arquivo_sha256 ~ '^[0-9a-f]{64}$'),
  arquivo_classe       text NOT NULL DEFAULT 'modelo3d' CHECK (arquivo_classe ~ '^[a-z0-9_]{1,40}$'),
  glb_sha256           text CHECK (glb_sha256 IS NULL OR glb_sha256 ~ '^[0-9a-f]{64}$'),
  glb_bytes            bigint CHECK (glb_bytes IS NULL OR glb_bytes >= 0),
  lon                  double precision NOT NULL CHECK (lon BETWEEN -180 AND 180),
  lat                  double precision NOT NULL CHECK (lat BETWEEN -85.05 AND 85.05),
  altura_m             double precision NOT NULL DEFAULT 0 CHECK (altura_m BETWEEN -1000 AND 10000),
  rotacao_graus        double precision NOT NULL DEFAULT 0 CHECK (rotacao_graus BETWEEN 0 AND 360),
  escala               double precision NOT NULL DEFAULT 1 CHECK (escala > 0 AND escala <= 1000),
  estado               text NOT NULL DEFAULT 'pendente'
                       CHECK (estado IN ('pendente', 'processando', 'pronto', 'falhou')),
  erro                 text,
  elementos            int NOT NULL DEFAULT 0 CHECK (elementos >= 0),
  elementos_sem_forma  int NOT NULL DEFAULT 0 CHECK (elementos_sem_forma >= 0),
  tileset              boolean NOT NULL DEFAULT false,  -- existe árvore 3D Tiles gerada para este modelo
  tileset_tiles        int NOT NULL DEFAULT 0 CHECK (tileset_tiles >= 0),
  tileset_arquivos     jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {caminho relativo: chave do objeto}
  caixa                jsonb NOT NULL DEFAULT '{}'::jsonb,   -- caixa envolvente geográfica já posicionada
  dono_id              int NOT NULL REFERENCES plat.usuario(id),
  criado_em            timestamptz NOT NULL DEFAULT now(),
  atualizado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_modelo3d_nome ON plat.modelo3d (tenant_id, lower(nome));
CREATE INDEX IF NOT EXISTS ix_modelo3d_tenant ON plat.modelo3d (tenant_id, criado_em DESC);

CREATE TABLE IF NOT EXISTS plat.modelo3d_elemento (
  id             bigserial PRIMARY KEY,
  tenant_id      int NOT NULL REFERENCES plat.tenant(id),
  modelo_id      uuid NOT NULL REFERENCES plat.modelo3d(id) ON DELETE CASCADE,
  guid           text NOT NULL CHECK (btrim(guid) <> '' AND length(guid) <= 64),
  tipo           text NOT NULL CHECK (length(tipo) <= 80),
  nome           text CHECK (nome IS NULL OR length(nome) <= 300),
  descricao      text CHECK (descricao IS NULL OR length(descricao) <= 2000),
  pavimento      text CHECK (pavimento IS NULL OR length(pavimento) <= 200),
  tem_geometria  boolean NOT NULL DEFAULT false,
  propriedades   jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_modelo3d_elemento ON plat.modelo3d_elemento (modelo_id, guid);
CREATE INDEX IF NOT EXISTS ix_modelo3d_elemento_tenant ON plat.modelo3d_elemento (tenant_id);
CREATE INDEX IF NOT EXISTS ix_modelo3d_elemento_tipo ON plat.modelo3d_elemento (modelo_id, tipo);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['modelo3d', 'modelo3d_elemento'] LOOP
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

GRANT USAGE, SELECT ON SEQUENCE plat.modelo3d_elemento_id_seq TO plat_app;

INSERT INTO plat.evento_tipo(nome, descricao) VALUES
  ('modelos3d/criar', 'modelo 3D criado (nome, origem, posição) e conversão enfileirada'),
  ('modelos3d/apagar', 'modelo 3D apagado, com os elementos e o tileset em cascata'),
  ('modelos3d/converter', 'conversão concluída (elementos lidos, elementos com forma, bytes do GLB)'),
  ('modelos3d/tileset', 'árvore 3D Tiles gerada (tiles, bytes)')
ON CONFLICT (nome) DO NOTHING;

-- ---------------------------------------------------------------- cena: bloco `modelos` no documento
UPDATE plat.tipo_item
   SET esquema = jsonb_set(
         esquema,
         '{properties,corpo,properties,modelos}',
         $j${
           "type": "array", "maxItems": 100,
           "items": {
             "type": "object", "additionalProperties": false,
             "required": ["id", "modelo_id"],
             "properties": {
               "id": {"$ref": "#/$defs/ulid"},
               "modelo_id": {"$ref": "#/$defs/uuid"},
               "titulo": {"type": "string", "maxLength": 300},
               "visivel": {"type": "boolean"},
               "modo": {"type": "string", "enum": ["gltf", "tileset"]},
               "opacidade": {"type": "number", "minimum": 0, "maximum": 1}
             }
           }
         }$j$::jsonb,
         true)
 WHERE nome = 'cena'
   AND esquema #> '{properties,corpo,properties,modelos}' IS NULL;
