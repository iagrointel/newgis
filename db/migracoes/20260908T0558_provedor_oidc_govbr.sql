-- 20260908T0615_provedor_oidc_govbr: item L0-08-c-govbr. gov.br (Login Único) como provedor OIDC por inquilino:
-- o provedor OIDC da 20260907T0147 ganha `modelo` ('generico' | 'govbr') e `api_base` (API de confiabilidades,
-- https://api.acesso.gov.br em produção, https://api.staging.acesso.gov.br em homologação). No modelo govbr o
-- nível da conta (bronze/prata/ouro) e os selos entram como valores do atributo de grupos ('nivel:ouro',
-- 'selo:801', 'amr:mfa') e o mapeamento de perfil/papel/grupos é o mesmo do L0-08-e. A função de leitura do
-- provedor devolve tipo fixo (20260907T0147), por isso um acessor próprio.
-- depende: 20260908T0212_provisionamento_federado.sql

ALTER TABLE plat.provedor_oidc ADD COLUMN IF NOT EXISTS modelo text NOT NULL DEFAULT 'generico';
ALTER TABLE plat.provedor_oidc DROP CONSTRAINT IF EXISTS provedor_oidc_modelo_check;
ALTER TABLE plat.provedor_oidc ADD CONSTRAINT provedor_oidc_modelo_check CHECK (modelo IN ('generico', 'govbr'));
ALTER TABLE plat.provedor_oidc ADD COLUMN IF NOT EXISTS api_base text;

CREATE OR REPLACE FUNCTION plat.provedor_oidc_modelo(p_id int)
RETURNS TABLE (modelo text, api_base text)
LANGUAGE sql SECURITY DEFINER STABLE SET search_path = plat, public AS $$
  SELECT po.modelo, po.api_base FROM plat.provedor_oidc po WHERE po.id = p_id
$$;
REVOKE EXECUTE ON FUNCTION plat.provedor_oidc_modelo(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.provedor_oidc_modelo(int) TO plat_app;
