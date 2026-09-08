-- Item L2-11-a-geocodificacao-csv: índice de igualdade por via no geo_endereco.
--
-- Medido na trilha plat_til211ageoco (RR, 260.515 linhas): o job de lote do item busca a via inteira
-- uma vez por linha do CSV com `WHERE cod_municipio = %s AND logradouro_norm = %s` (motor.buscar,
-- app/geocodificador/motor.py) e a única igualdade indexada era (cod_municipio, face_id, numero),
-- que não cobre logradouro_norm — cada busca virava varredura sequencial das 260 mil linhas
-- (~26 ms), e o trabalho do pg_trgm (`%` + similarity no HAVING) repetia candidatos de todo o
-- estado em vez de só do município pedido (~30-110 ms por endereço). Com 1.000 endereços o job
-- `geocodificador.lote_csv` não terminava nos 120 s do portão (6,7 endereços/s medidos em 08/09).
--
-- O índice btree (cod_municipio, logradouro_norm) atende os dois caminhos: a busca da via vira
-- varredura de índice e o planejador pode cruzá-la com o GIN trgm do logradouro_norm para restringir
-- os candidatos ao município. Nenhum texto de consulta muda; os resultados são os mesmos.
-- Idempotente (IF NOT EXISTS), igual aos índices irmãos da 045.

CREATE INDEX IF NOT EXISTS ix_geo_endereco_mun_logr ON plat.geo_endereco (cod_municipio, logradouro_norm);
