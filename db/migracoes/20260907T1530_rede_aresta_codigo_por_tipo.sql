-- 20260907T1530_rede_aresta_codigo_por_tipo: o código externo da aresta é único POR TIPO, não na rede.
-- Achado do item L4-01-c na cooperativa de teste INTEIRA (07/09): na BDGD o COD_ID é único por
-- CAMADA — 26.567 dos 29.244 trechos de baixa tensão (SSDBT) têm o mesmo COD_ID de um trecho de
-- média (SSDMT). Com UNIQUE (rede_id, codigo_externo) o ON CONFLICT DO NOTHING descartava 91 % da
-- baixa tensão EM SILÊNCIO (entraram 2.677 = 29.244 − 26.567). No recorte de um alimentador a
-- coincidência era zero, por acaso. É o mesmo desenho do Utility Network da Esri: o asset id é
-- único dentro do asset group, não do dataset.
ALTER TABLE plat.rede_aresta DROP CONSTRAINT IF EXISTS rede_aresta_rede_id_codigo_externo_key;
ALTER TABLE plat.rede_aresta ADD CONSTRAINT rede_aresta_rede_tipo_codigo_key UNIQUE (rede_id, tipo_id, codigo_externo);
COMMENT ON CONSTRAINT rede_aresta_rede_tipo_codigo_key ON plat.rede_aresta IS
  'código externo único por (rede, tipo): na BDGD o COD_ID repete entre camadas (SSDMT × SSDBT); item L4-01-c, 07/09';
