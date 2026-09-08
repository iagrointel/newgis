-- 045_geocodificador: geocodificador próprio (item L2-11-b-geocodificador-brasil). Base = CNEFE 2022 do IBGE
-- (endereço com coordenada por face de quadra, dado aberto), carregado pelo instalador por UF
-- (scripts/geocodificador_instalar_uf.py). Sem tenant_id: é referência aberta compartilhada por toda a casa,
-- mesmo padrão de plat.acervo_ficha (migração 021) e plat.rota (L2-11-c, que nem tabela tem) — P6 não se aplica
-- (nada é lido/escrito por inquilino aqui). Idempotente. Sem BEGIN/COMMIT. Aplicada como postgres.
-- Exige as extensões pg_trgm e unaccent no schema public (já instaladas na casa, conferido em 06/09) e PostGIS.

CREATE TABLE IF NOT EXISTS plat.geo_uf (
  cod   smallint PRIMARY KEY,
  sigla text NOT NULL UNIQUE,
  nome  text NOT NULL
);

CREATE TABLE IF NOT EXISTS plat.geo_municipio (
  cod         integer PRIMARY KEY,       -- código IBGE de 7 dígitos
  cod_uf      smallint NOT NULL REFERENCES plat.geo_uf (cod),
  nome        text NOT NULL,
  nome_norm   text NOT NULL,             -- upper(unaccent(nome)), mesma função usada na busca
  centro_lat  double precision,
  centro_lon  double precision,
  enderecos   integer NOT NULL DEFAULT 0 -- nº de pontos carregados (proveniência da instalação)
);
CREATE INDEX IF NOT EXISTS ix_geo_municipio_nome_trgm ON plat.geo_municipio USING gin (nome_norm public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_geo_municipio_uf ON plat.geo_municipio (cod_uf);

-- endereço-ponto do CNEFE: 1 linha = 1 coordenada oficial do IBGE (face de quadra). PK é surrogate: medido
-- (06/09) que COD_UNICO_ENDERECO NÃO é único em Roraima (260.516 linhas, só 249.268 ids distintos — o IBGE
-- repete o código quando há mais de um domicílio/estabelecimento na mesma coordenada), por isso vira coluna
-- indexada (`cod_unico_endereco`), nunca chave primária.
CREATE TABLE IF NOT EXISTS plat.geo_endereco (
  id                  bigserial PRIMARY KEY,
  cod_unico_endereco  bigint NOT NULL,
  cod_uf              smallint NOT NULL,
  cod_municipio       integer NOT NULL,
  cod_setor           text,
  num_quadra          text,
  num_face            text,
  face_id             text NOT NULL,       -- cod_setor||'/'||num_quadra||'/'||num_face: pontos da mesma face
  cep                 text,
  localidade          text,                -- DSC_LOCALIDADE (bairro/distrito do CNEFE)
  localidade_norm     text,
  tipo_logradouro     text,                -- NOM_TIPO_SEGLOGR (RUA, AVENIDA, ...; vocabulário do IBGE)
  titulo_logradouro   text,                -- NOM_TITULO_SEGLOGR (DOM, SAO, ...; raro)
  nome_logradouro     text,
  logradouro_norm     text NOT NULL,       -- upper(unaccent(tipo||titulo||nome)) p/ trigram
  numero              integer,             -- NUM_ENDERECO (0 quando sem_numero)
  sem_numero          boolean NOT NULL DEFAULT false,
  modificador         text,                -- DSC_MODIFICADOR (SN, KM, ...)
  especie             smallint,            -- COD_ESPECIE (1 domicílio particular, 6 estabelecimento, ...)
  nivel_geo           smallint,            -- NV_GEO_COORD (precisão da coordenada declarada pelo IBGE)
  lat                 double precision NOT NULL,
  lon                 double precision NOT NULL,
  geom                geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_logradouro_trgm ON plat.geo_endereco
  USING gin (logradouro_norm public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_localidade_trgm ON plat.geo_endereco
  USING gin (localidade_norm public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_geom ON plat.geo_endereco USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_face ON plat.geo_endereco (cod_municipio, face_id, numero);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_cep ON plat.geo_endereco (cep);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_municipio ON plat.geo_endereco (cod_municipio);
CREATE INDEX IF NOT EXISTS ix_geo_endereco_cod_unico ON plat.geo_endereco (cod_unico_endereco);

-- proveniência da instalação por UF (tamanho medido antes de baixar, D28: teto de disco): 1 linha por UF
-- instalada, escrita pelo job scripts/geocodificador_instalar_uf.py.
CREATE TABLE IF NOT EXISTS plat.geo_instalacao (
  cod_uf         smallint PRIMARY KEY,
  sigla          text NOT NULL,
  fonte_url      text NOT NULL,
  arquivo_bytes  bigint NOT NULL,
  csv_bytes      bigint NOT NULL,
  linhas         bigint NOT NULL,
  municipios     integer NOT NULL,
  duracao_s      numeric NOT NULL,
  sha256_zip     text NOT NULL,
  instalado_em   timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON plat.geo_uf, plat.geo_municipio, plat.geo_endereco, plat.geo_instalacao
  TO plat_app;
