# gov.br (Login Único) como provedor OIDC por inquilino (item L0-08-c-govbr)

Data: 08/09/2026. Estado: aceito. Par: `20260907T0147-oidc-authlib.md` (OIDC genérico),
`20260908T0240-provisionamento-federado.md` (regras de mapeamento).

## Contexto

Órgão público entra pelo gov.br. O roteiro técnico (acesso.gov.br/roteiro-tecnico) é OIDC padrão (Authorization
Code + PKCE S256, `/authorize`, `/token`, `/jwk`, `/userinfo`) com duas coisas próprias: `sub` é o CPF, e o
nível da conta (bronze/prata/ouro) e os selos chegam em `reliability_info` no id_token (escopo
`govbr_confiabilidades_idtoken`) ou pela API de confiabilidades (`/confiabilidades/v3/contas/{cpf}/niveis` e
`/confiabilidades`, `response-type=ids`). O cadastro do cliente exige ofício do órgão: não há credencial real.

## Decisões

1. **Não é um provedor novo: é um `modelo` do provedor OIDC** (`plat.provedor_oidc.modelo = 'govbr'`, mais
   `api_base`). Descoberta, PKCE, JWKS, validação de assinatura/iss/aud/nonce/exp e a transação de uso único
   são as do L0-08-a, sem cópia. O adaptador (`app/auth/govbr.py`) só transforma claims/API em valores.
2. **Nível, selos e fatores viram valores do atributo de grupos** (`nivel:ouro`, `selo:801`, `amr:mfa`) e o
   mapeamento para perfil/papel/grupos é o do L0-08-e (valor exato, regra explícita). Não existe regra implícita
   "ouro = admin": o admin do órgão decide na tela Logins.
3. **CPF nunca em claro**: `sujeito_externo = <issuer>#sha256(cpf)`, login = parte local do e-mail ou
   `govbr-<12 hex>`, nada do CPF em evento ou log (teste procura o CPF sintético em usuário e eventos).
4. **id_token primeiro, API depois**: a API de confiabilidades só é consultada quando o id_token não trouxe
   `reliability_info` (escopo não concedido); falha da API não derruba o login (aviso no log, valores do
   id_token seguem). `api_base` é deduzida do issuer oficial (staging/produção) quando ausente.
5. **Refutação por construção**: um id_token com `reliability_info.level = gold` assinado por outro issuer é
   recusado em `validar_id_token` (kid fora do JWKS do issuer configurado; `iss` divergente) antes de qualquer
   leitura de claim — 401 `token_invalido`, sem sessão (teste com o segundo issuer do IdP sintético).
6. **Teste real é pendente** (`docs/PARIDADE.md`): o adaptador é provado contra `tests/govbr_fixture/idp_falso.py`
   (servidor em thread, chaves geradas na hora, formato do roteiro, inclusive `1 (Bronze)`/`2 (Prata)`/`3 (Ouro)`
   da API). Sem credencial do órgão nunca se marca "feito".
7. **Tela**: Logins > Novo provedor OIDC com os campos que o roteiro pede (ambiente/issuer, client_id,
   client_secret cifrado, redirect_uri fixa da instalação mostrada para copiar, escopos, rótulo).

## Consequências

- `GET /api/org/logins` passa a devolver `redirect_uri_oidc` e o bloco `govbr` (issuers, API, escopos, valores).
- Este ramo contém `wt/cx2l008e` (que contém `wt/cx008`): junte nessa ordem ou aceite o merge.
