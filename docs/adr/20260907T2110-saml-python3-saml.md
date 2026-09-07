# ADR 20260907T2110 — SAML 2.0 Web SSO por inquilino (item L0-08-b)

Estado: aceito (07/09/2026). Linha L0, família L0-08-sso; irmão do OIDC (ADR 20260907T0147).

## D1. Biblioteca: python3-saml sobre xmlsec (wheel), não a validação escrita à mão

Havia uma implementação própria de XML-DSig em `wt/il008sso` (lxml + cryptography). Foi deixada de lado: a
superfície de ataque do SAML é conhecida (XML Signature Wrapping em várias formas, comentário no NameID,
algoritmos depreciados, esquema) e o python3-saml (OneLogin, MIT) cobre isso com `strict`, validação XSD,
referência única por ID e recusa de SHA-1. O `xmlsec` vem como wheel manylinux com libxmlsec embutida: não
precisou de apt nem mudou versão de lxml/cryptography (medido antes de instalar). Custo de mudar: baixo (o
módulo isola a biblioteca em `configuracao()` e `pedido_de()`).

## D2. Uma identidade, uma função de provisionamento; tabela de provedor própria

`plat.usuario` já aceitava `origem='saml'`. O provisionamento virou `plat.usuario_externo_provisionar(origem, …)`
e `plat.oidc_provisionar` passou a ser um atalho para ela — nenhum segundo modelo de identidade. O que é
próprio do SAML (entityId/URLs/certificados do IdP, par de chaves do SP, formato de NameID, nomes de
atributo) fica em `plat.provedor_saml`, espelho de `plat.provedor_oidc` (vários por inquilino, rótulo, ordem,
RLS). `GET /api/login/provedores` lista os botões dos dois tipos.

## D3. Assinatura de resposta E de asserção obrigatórias; cifra opcional; relógio com folga declarada

`wantMessagesSigned` e `wantAssertionsSigned` sempre ligados (o portão exige os dois). `assercao_cifrada`
por provedor: a decifra é sempre aceita (chave privada do SP gerada aqui e gravada cifrada com PLAT_SECRET,
prefixo `encsaml:v1:`), e quando a opção está ligada a asserção em claro é 401. Desvio de relógio tolerado =
`limites.SAML_DESVIO_RELOGIO_S` (300 s): 10 min à frente é 401.

## D4. Replay por ID de asserção; IdP-initiated sem InResponseTo

`plat.saml_assercao_usada` guarda o ID de toda asserção aceita até o `NotOnOrAfter` dela: a mesma asserção
(mesmo ID) nunca abre duas sessões. SP-initiated consome a transação de uso único pelo `InResponseTo`;
IdP-initiated é aceito sem `InResponseTo` (`rejectUnsolicitedResponsesWithInResponseTo: False`), e o provedor
é identificado pela `Audience` (o entityId do SP carrega o `provedor_id`; por isso o entityId tem um único
parâmetro — o python3-saml não escapa `&` no XML) ou pelo `Issuer` quando aponta para um só provedor.

## D5. Logout propagado nos dois sentidos

Sessão nascida por SAML guarda NameID + SessionIndex em `plat.saml_sessao`. `GET /api/sso/saml/logout` encerra
a sessão local e redireciona com LogoutRequest assinado ao SLO do IdP; `/api/sso/saml/slo` recebe a
LogoutResponse (apaga o cookie) ou um LogoutRequest vindo do IdP (encerra toda sessão local do NameID e
responde LogoutResponse assinado).

## Testes

Sem Docker: IdP sintético com chave gerada na hora (`tests/saml_fixture/idp_falso.py`) forja 16 casos contra o
ACS real. Com Docker: Keycloak 26 do L0-08-a com dois clientes SAML (assinado e cifrado), metadado lido por
URL, SP- e IdP-initiated, cifra, SLO e queda do IdP. Captura de tela não há (chromium headless quebrado nesta
máquina): a evidência é o log estruturado.
