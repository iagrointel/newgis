# T1 · 21_esri — especialista Esri · itens L0-02-tenant-auth e L0-03-catalogo (referência de paridade, portão P4)

Data de acesso a toda fonte: 2026-09-05 (12:30–12:39 UTC). Papel: `esri`. Não toquei em nenhum arquivo além deste.

## Objetivo

Descrever, a partir da documentação oficial Esri, o que o ArcGIS Enterprise / Portal for ArcGIS 11.x faz EXATAMENTE
em (1) identidade e acesso e (2) conteúdo (Portal "Content"); entregar (3) a tabela de paridade-alvo dos itens
L0-02-tenant-auth e L0-03-catalogo no formato de `docs/PARIDADE.md`, com a coluna "nós" preenchida com o que o portão
de cada item promete e estado `pendente`; e (4) as dez coisas em que o usuário Esri mais se irrita ao migrar de
plataforma, com fonte e URL, para o desenho evitá-las. Tudo com URL testada por HTTP.

## O que fiz

1. Li `SKILL.md` do laço (papel `esri`, portão P4), os itens `L0-02-tenant-auth` e `L0-03-catalogo` em
   `laco/estado.json`, o `00_plano.md` e o `20_arquitetura.md` do T1 (ADR 6: `tenant`, `usuario` com perfis
   admin/editor/visualizador/campo + superadmin, 2FA, bloqueio; `sessao`; `token_servico` com hash, escopos,
   restrição, revogação; `log_acesso`; RLS `FOR ALL` com `USING`/`WITH CHECK`).
2. Levantei a documentação oficial. Achado de método que o próximo papel precisa saber: **as URLs
   `enterprise.arcgis.com/en/portal/latest/...` hoje redirecionam (301 → 301 → 200) para `doc.esri.com/en/arcgis-enterprise/latest/...`,
   e "latest" no doc.esri.com é a versão 12.1** (sitemap com 1.231 URLs, todas em `/12.1/`; `<meta version 12.1>`). Nove
   nomes antigos de página (user-types-roles-and-privileges, privileges-for-roles, configure-saml, configure-openid-connect,
   configure-multifactor-authentication, set-password-policy, password-policy, create-api-keys, manage-content) caem na
   página inicial da doc com HTTP 200: um "200" que não prova nada. Por isso usei duas séries de fontes: a série
   **E11** (páginas versionadas `enterprise.arcgis.com/en/portal/11.4/...`, HTTP 200 sem redirecionamento, versão-alvo do
   laço) e a série **E12** (`doc.esri.com/.../latest/`, 12.1, texto mais completo). Onde 11.4 e 12.1 divergem, digo.
3. Extraí o texto de 45 páginas por `curl -sL` + remoção de marcação (`totext.py`, no scratchpad) e li o texto; para o
   `developers.arcgis.com` (renderizado por JavaScript) usei a leitura via WebFetch. Nenhum download de binário.
4. Testei por HTTP HEAD (`curl -sIL ... -w "%{http_code} %{url_effective}"`) as 92 URLs citadas neste handoff:
   91 responderam 200; 1 (blog da Esri) responde 403 à máquina e por isso NÃO é usada como evidência.
5. Conferi as diferenças entre 11.4 e 12.1 nos pontos que mudaram: "Enforce MFA" (obrigar MFA a toda a organização)
   existe na 12.1 e não aparece na página de segurança 11.4 (11.4 tem MFA opcional por membro); o estilo de metadado
   "Dublin Core+" é padrão de organização criada na 12.0+ e não existe na lista 11.4; chaves de API (credenciais de
   desenvolvedor) existem desde a 11.4; logs de auditoria do Portal existem na 11.4; tetos de token são idênticos.

## Evidência (comandos e saídas literais)

Comando de teste (um por URL; a lista completa está no anexo A):

```
$ while IFS='|' read k u; do r=$(curl -sIL --max-time 25 -A "Mozilla/5.0 (X11; Linux x86_64)" -o /dev/null \
    -w "%{http_code} %{url_effective}" "$u"); echo "$k|$u|$r"; done < urls_final.txt
$ date -u +"acesso %Y-%m-%d %H:%MZ"
acesso 2026-09-05 12:39Z
```

Saída resumida (código HTTP final por chave; a tabela completa com URL está no anexo A):

```
E11-roles 200 · E11-usertypes 200 · E11-priv 200 · E11-security 200 · E11-saml 200 · E11-oidc 200 · E11-tokenexp 200
E11-audit 200 · E11-licenses 200 · E11-members 200 · E11-manageitems 200 · E11-usage 200 · E11-itemdetails 200
E11-configitem 200 · E11-share 200 · E11-groups 200 · E11-search 200 · E11-metadata 200 · E11-supported 200
E11-hosted 200 · E11-categories 200 · E11-delete 200 · E11-move 200 · E11-migration 200
E12-* (38 páginas) 200 · DEV-* (6) 200 · KB-* (4) 200 · COM-* (18) 200 · MERGIN-migrate 200 · BLOG-migrategroup 403
```

Prova do redirecionamento "latest" → 12.1 e da armadilha do 200 falso:

```
$ curl -sIL -o /dev/null -w "%{http_code} %{url_effective}\n" \
  https://enterprise.arcgis.com/en/portal/latest/administer/windows/user-types-roles-and-privileges.htm
200 https://doc.esri.com/en/arcgis-enterprise/latest/            <- página inicial, não a página pedida
$ curl -sIL -o /dev/null -w "%{http_code} %{url_effective}\n" \
  https://enterprise.arcgis.com/en/portal/latest/administer/windows/roles.htm
200 https://doc.esri.com/en/arcgis-enterprise/latest/administer/roles.html
$ grep -o 'arcgis-enterprise/[0-9.]*/' sitemap.txt | sort | uniq -c
   1231 arcgis-enterprise/12.1/
$ curl -sIL -o /dev/null -w "%{http_code}\n" https://doc.esri.com/en/arcgis-enterprise/11.4/administer/configure-security.html
404
$ curl -sIL -o /dev/null -w "%{http_code}\n" https://enterprise.arcgis.com/en/portal/11.4/administer/windows/configure-security.htm
200
```

Prova das diferenças de versão (grep no texto extraído das páginas 11.4):

```
$ grep -i -o -E "enforce multifactor[^.]*\.|Enable multifactor authentication for organization|Generate API keys" v114-sec.txt v114-priv.txt | sort -u
v114-priv.txt:Generate API keys
v114-sec.txt:Enable multifactor authentication for organization          <- sem "Enforce" na 11.4
$ grep -E "^ (Dublin|FGDC|INSPIRE|ISO|North America)" v114-metadata.txt | cut -c1-40
 FGDC CSDGM Metadata—This style allows y
 INSPIRE Metadata Directive—This style a
 ISO 19139 Metadata Implementation Speci
 ISO 19139 Metadata Implementation Speci
 North America Profile of ISO 19115 2003
 ISO 19115-3 XML Schema Implementation—T                                  <- sem "Dublin Core+" na 11.4
$ grep -E "days|minutes" v114-tokenexp.txt | head -4
 ArcGIS token—14 days (20,160 minutes)
 OAuth access token, when created with the Implicit or Client Credentials grant types—14 days (20,160 minutes)
 OAuth access token, when created with the Authorization Code grant type—30 minutes
 OAuth refresh token—90 days (129,600 minutes)
```

Trechos literais que sustentam as afirmações centrais estão citados dentro de cada seção, com a chave da fonte
(E11-…, E12-…, DEV-…, KB-…, COM-…) que remete ao anexo A.

---

## 1. Identidade e acesso no ArcGIS Enterprise / Portal 11.x

### 1.1 Tipos de usuário (user types)

O que a doc diz (E11-usertypes, E12-usertypes; E12-roles): o tipo de usuário é atribuído ao membro quando ele é
adicionado; "controla que apps o usuário acessa" e "determina o escopo de privilégios que podem ser atribuídos
através de um papel". Os tipos listados nas duas versões (a página 11.4, revisada em 2025, já usa os nomes novos):

| tipo | o que pode | limite |
|---|---|---|
| Viewer | ver itens compartilhados; apps de visualização | "não pode criar, editar, compartilhar nem analisar" |
| Contributor | ver e EDITAR dados em mapas/apps compartilhados; apps de edição | não analisa, não cria, não compartilha |
| Mobile Worker | ver/editar em campo, coletar, compartilhar localização, gravar trilhas (apps de campo) | não analisa, não cria, não compartilha |
| Creator | criar/editar mapas e apps, análise no portal, coletar, compartilhar, administrar; inclui ArcGIS Pro Basic | — |
| Professional | tudo do Creator + ArcGIS Pro Standard + extensão ArcGIS Advanced Editing | — |
| Professional Plus | tudo do Professional + ArcGIS Pro Advanced | — |

Regras que o usuário Esri conhece: (a) Viewer/Contributor/Mobile Worker não podem receber papel que crie conteúdo
("um membro com tipo Viewer não pode ser adicionado ao papel Publisher nem a papel personalizado com privilégio de
criar conteúdo" — E12-roles); (b) papel personalizado com privilégio ADMINISTRATIVO só cabe em Creator/Professional/
Professional Plus (E12-priv); (c) rebaixar o tipo (ex.: Creator → Viewer) só se o membro "não possui conteúdo nem
grupos, não tem licença adicional incompatível e não pertence a grupo de atualização compartilhada" (E12-members);
(d) a lista de tipos "pode mudar de uma versão para outra" (nota literal, E12-usertypes).

Na interface: **Organization > Members** (coluna User type, filtro por tipo/papel/grupo/licença/último login,
seleção de até 100 membros, "Manage user types"); **Organization > Licenses > User types** (atribuídos × disponíveis,
papéis compatíveis); **Organization > Settings > New member defaults** (tipo e papel padrão para quem entra por SAML/OIDC).

### 1.2 Papéis padrão (default roles)

Correção ao enunciado: "Creator" e "Professional" são TIPOS DE USUÁRIO, não papéis. Os papéis padrão são cinco, com
privilégios fixos ("não podem ser alterados" — E11-roles, E12-roles):

| papel | resumo literal da doc (E12-roles) | tipos compatíveis |
|---|---|---|
| Viewer | ver itens compartilhados; entrar em grupos da organização; geocodificar, geosearch e roteamento; "não pode criar ou compartilhar conteúdo nem analisar" | todos |
| Data Editor | Viewer + "editar feições compartilhadas por outros usuários" | todos exceto Viewer |
| User | Data Editor + "criar grupos e conteúdo"; entrar em grupos de atualização compartilhada; criar mapas/apps, adicionar itens, compartilhar | Creator, Professional, Professional Plus |
| Publisher | User + "publicar camadas hospedadas, camadas de ArcGIS Server, registrar data stores, publicar a partir de data store, análise de feições e raster" | Creator, Professional, Professional Plus |
| Administrator | Publisher + gerir a organização e os outros usuários; "a organização deve ter pelo menos um administrador" | Creator, Professional, Professional Plus |

Mudar papel de/para Administrator só por quem já é Administrator padrão (E12-members). Ao entrar automaticamente
por SAML/OIDC o membro recebe o papel configurado em "New member defaults" (E12-saml); no fluxo de federação de IdPs a
doc diz "recebe o papel User" (E12-saml-fed, citado em E12-saml).

### 1.3 Papéis personalizados e a lista completa de privilégios

Como se cria (E12-configroles; E11-priv): Organization > Settings > **Member roles** > Create role; nome único, até
128 caracteres, sem distinção de maiúsculas; descrição até 250; "Set from existing role" (copiar de papel ou de
modelo); "privilege compatibility setting" escolhe o tipo de usuário mais baixo que o papel aceita; não se apaga papel
padrão nem papel atribuído a alguém. Modelos prontos: Analyst, Author, Data Curator, Student, Publisher, User, Data
Editor, Viewer. Regra: "os privilégios concedidos por um papel personalizado não podem exceder os do tipo de usuário do
membro" (E12-roles).

Privilégios GERAIS (E12-priv; a página 11.4 lista o mesmo conjunto — E11-priv), entre parênteses os papéis padrão que
os incluem:

- Members: View (todos) · Take ArcGIS Pro license offline (todos).
- Groups: Create, update, and delete (User, Publisher, Admin) · Join organizational groups (todos; só User/Publisher/
  Admin entram em grupo de atualização compartilhada) · View groups shared with organization (todos).
- Content: Create, update, and delete (User+) · Publish hosted feature layers (Publisher+) · Publish hosted tile layers
  (Publisher+) · Publish hosted scene layers (Publisher+) · Publish hosted dynamic imagery layers (Publisher+, exige
  raster analysis) · Publish server-based layers (Publisher+) · Publish hosted knowledge graphs (Publisher+) · View
  content shared with organization (todos) · Register data stores (Publisher+) · Create feature layers in bulk from a
  data store (Publisher+) · View location tracks (Admin) · Create and edit notebooks (Admin) · Schedule notebooks
  (Admin) · Reassign content (Admin) · Receive content (Admin) · Create and run data pipelines (Publisher+) · Publish
  livestream video (Publisher+) · Publish video (Publisher+) · Generate API keys (Admin) · Assign privileges to OAuth
  2.0 applications (Admin) · Create workflow item (Publisher+).
- Sharing: Share with groups · Share with portal · Share with public · Make groups visible to portal · Make groups
  visible to public (todos os cinco: User, Publisher, Admin).
- Content and Analysis: Geocoding (todos) · Network Analysis (todos) · Standard Feature Analysis (User+) ·
  GeoEnrichment (User+) · Imagery Analysis (Publisher+) · Advanced notebooks (Admin) · Run web tools (Admin) ·
  Reality Mapping (Admin).
- Features: Edit (Data Editor+) · Edit with full control (Admin).
- Version Management: Manage all (User+; liga Edit e Edit with full control).
- Webhooks: Feature layer (Admin).

Privilégios ADMINISTRATIVOS atribuíveis a papel personalizado (E12-priv):

- Members: View all · Update (inclui reset de senha e categorias de membro) · Delete · Add · Disable · Change roles ·
  Manage licenses · Manage categories.
- Groups: View all · Update · Delete · Reassign ownership · Assign members · Link to organization-specific group ·
  Create with leaving disallowed (grupos administrativos) · Create with update capabilities (grupos de atualização
  compartilhada).
- Content: View all · Update (inclui editar dados de qualquer camada hospedada mesmo sem edição habilitada) · Delete ·
  Reassign ownership · Manage categories · Publish web tools · Share member content with organization · Share member
  content with public · Create and manage administrative reports.
- Webhooks: Geoprocessing.
- Portal settings: Security and infrastructure · Organization website · Collaborations · Member roles · Servers ·
  Utility services · Organization webhooks.

Reservados ao Administrator padrão (não vão para papel personalizado): mudar papel de/para administrador; apagar
outros administradores; resetar senha de administradores; ser contato administrativo; criar backup; atribuir papel
administrativo a membro novo; exportar/importar itens de grupo; gerir relatórios agendados de outros; registrar
custom data providers; criar categoria de login para app de outro; **criar pastas em nome de membros**; habilitar a
extensão Workflow Management (E12-priv).

Na interface: a tela Member roles mostra cada papel com "Role information" (descrição + lista de privilégios),
se é padrão ou personalizado e quantos membros tem; o membro vê o próprio papel em My settings > General.

### 1.4 Grupos e compartilhamento

Níveis de compartilhamento de um item (E11-share, E12-share): **Owner** (padrão: "o conteúdo que você adiciona é
acessível só a você"; não aparece em busca), **Organization** (exige credencial do portal), **Everyone (public)**
(qualquer um com acesso ao site; camada de feição pública pode ser exportada por clientes externos e, se editável,
editada por quem tiver a URL), **grupos** (só grupos a que o dono pertence e que aceitam contribuição), e as
combinações Organization+grupo e Everyone+grupo. Camada de feição editável só vai a público depois de habilitar
"public data collection"; camadas dinâmicas de imagem, knowledge graphs e Indoors Spaces não podem ir a público.
Dependência literal: camada de feição de ArcGIS Server e seu map image layer "são itens dependentes": compartilhar
o map image layer expõe também o feature service; o inverso não vale.

Grupo (E12-groups, E12-owngroups, E12-managegroups): campos de criação — miniatura (400×400, 1:1), nome, tags,
resumo; **Who can view** (Only group members / All organization members / Everyone (public), padrão público);
**How can people join** (By invitation / By request / By adding themselves / membro de grupo SAML / OIDC / Active
Directory / LDAP — os quatro últimos só com "Enable ... group membership" ligado e privilégio "Link to
organization-specific group"; o nome digitado tem de ser o valor exato do atributo `groups`/`MemberOf` da asserção);
**Who can contribute** (All group members / Group owner and managers); **Who can see the full list of members**
(só administrador padrão; irreversível quando escondido); designações **Shared update** (todos os membros do grupo
editam detalhes e conteúdo dos itens; o dono continua dono; só na criação, só com convite/pedido; reservam-se ao dono:
apagar, compartilhar, mover, mudar dono, delete protection, registrar app, campos e sobrescrita; os membros ganham
poderes elevados: editar dados, anexar, alterar esquema) e **Administrative group** (membro não pode sair). Papéis de
grupo: Owner, Group manager, Group member. Limites: 512 grupos por usuário; até 24 itens em destaque; categorias de
grupo até 3 níveis e 200 no total; a lista de membros só é atualizada em grupo SAML a cada login. Grupo tem "Prevent
this group from being accidentally deleted" e não se apaga com isso ligado. Mudança de dono de grupo shared update
exige que o novo dono tenha o privilégio "Create with update capabilities". Convite de grupo é notificação no site,
"não é enviado como e-mail" (E12-managegroups).

Na interface: página **Groups** (My groups / Featured / My organization / Public), página do grupo com Overview
(Invite members, Membership requests, Share, Link to this group), Content (filtros, categorias de grupo, Add items to
group, Remove from group), Members (papel, filtro "My organization view"), Settings (Delete group, deletion
management). No item: botão **Share** > Organization / Everyone / Edit group sharing (filtro "Special groups").

### 1.5 Logins internos × SAML / OIDC (e AD/LDAP)

Identity stores (E12-access): **built-in** (obrigatório para o administrador inicial; "útil para começar,
desenvolvimento e teste; produção tipicamente usa store da organização") e **organization-specific** (LDAP, Windows
Active Directory, SAML 2.0, OpenID Connect). Com store da organização "o acesso anônimo é desabilitado" e "o portal
não cria, edita nem apaga contas no store": só registra contas existentes, individualmente ou em massa a partir de
grupos AD/LDAP/SAML. AD suporta vários domínios numa floresta, não entre florestas (para isso, SAML).

SAML (E11-saml, E12-saml): SAML 2.0 Web SSO; SP-initiated (botão no sign-in do portal) e IdP-initiated; opções na
criação: nome que aparece no botão ("Using your City of Redlands account"), **Automatically** (conta registrada no 1º
login) ou **Upon invitation from an administrator** (registro por utilitário de linha de comando); fonte de metadado
(URL, arquivo ou parâmetros: Login URL Redirect, Login URL POST, certificado Base64); avançado: Allow Encrypted
Assertion, Enable signed request, Propagate logout (Logout URL), Update profiles on sign in (padrão ligado), Enable
SAML based group membership (padrão desligado), Entity ID. Atributos: `NameID` obrigatório e vira o username
(permitidos alfanuméricos, `_`, `.`, `@`; o resto vira `_`); e-mail, givenName, surname, grupos (lista de nomes de
atributo aceita: Group, Groups, Role, Roles, MemberOf, member-of, urn:oid:…). O portal também aceita **federação de
IdPs** (discovery service WAYF + metadado agregado). Metadado do SP em
`/sharing/rest/portals/self/sp/metadata?token=`.

OpenID Connect (E11-oidc, E12-oidc): rótulo do botão; entrada automática ou por administrador; Registered client ID;
método de autenticação Client secret ou par de chaves pública/privada (gerado pelo portal; regenerar invalida o
anterior); scopes (`openid profile email`); Provider issuer ID; URLs de autorização, token, JWKS (usada só sem
userinfo), userinfo (recomendada), logout; "Send access token in header"; PKCE (S256); "Enable OpenID Connect login
based group membership" (claim `groups`); claim de username do ArcGIS (6–128 caracteres) e claim de identificador
(`sub` padrão; "configurar só uma vez: mudar depois quebra as contas já criadas"); redirect URIs de login/logout a
registrar no IdP. "Um login OIDC não pode ser apagado até que todos os membros do provedor sejam removidos."

O que o usuário SAML/OIDC NÃO faz no portal: mudar senha ou pergunta de segurança ("o portal não reseta senha de
login da organização" — E12-profile), receber reset de senha do administrador (E12-members), ser regido pela política
de senha do portal (E12-security) nem pela MFA do portal (E12-security, E12-profile). Ao ser apagado do portal, a
conta é "desregistrada" e continua no IdP; conta built-in apagada "é permanentemente apagada e não pode ser
recuperada" (E12-members).

Na interface: Organization > Settings > **Security > Logins** (toggle ArcGIS login, New SAML login, New OpenID
Connect login, ordem dos botões arrastável, Preview); "Custom sign-in" com categorias (até 100); "Allow users to
create new built-in accounts" em Policies. A tela de sign-in mostra os botões na ordem configurada.

### 1.6 MFA

Doc (E11-security, E12-security, E12-profile): só para contas built-in ("para SAML/OIDC, configure no IdP"); exige
**e-mail configurado** na organização; TOTP por app autenticador (Google Authenticator citado; QR ou código de 16
caracteres; código de 6 dígitos); a organização designa **pelo menos dois administradores** que recebem e-mail
para desabilitar MFA de um membro ("Still having trouble signing in?"); "funciona com apps Esri que suportam OAuth
2.0" e "tem de ser desabilitada para apps sem OAuth" (geocodificação/geoprocessamento de rota e elevação, credenciais
guardadas de conteúdo premium). 11.4: o membro liga em My settings > Security > Multifactor Authentication > Enable;
a coluna "Multifactor Authentication" da tabela de membros mostra um check. 12.1 acrescenta **Enforce MFA** com lista
de isenção ("desloga na hora todo membro built-in sem MFA") e **Reset** pelo próprio membro. O administrador desliga a
MFA de um membro em Members > More options > Disable multifactor (privilégio reservado ao Administrator).

### 1.7 Política de senha e bloqueio

Doc (E11-security, E12-security, E12-access, E12-profile): padrão "pelo menos oito caracteres com pelo menos uma
letra e um número; espaços não permitidos"; case sensitive; não pode ser igual ao username; senhas fracas
recusadas ("password1", "aaaabbbb", "1234abcd"). **Manage password policy**: comprimento mínimo; obrigar maiúscula,
minúscula, número, caractere especial; dias até expirar; número de senhas anteriores que não podem ser reusadas;
"Use portal defaults". A política "não se aplica a logins SAML e a credenciais de app (app ID/secret)". Lockout
padrão: **5 tentativas falhas em 15 minutos → bloqueio de 15 minutos**, inclusive para o administrador inicial;
**Manage lockout settings** muda tentativas e duração. Reset pelo administrador gera senha temporária (mostrada na
tela ou enviada por e-mail) e obriga troca no 1º login; "Forgot password" usa pergunta de segurança ou link por e-mail.
Mudança de política dispara e-mail aos contatos administrativos.

Na interface: Organization > Settings > Security > **Sign-in policy** (Password policy, Lockout settings);
Members > More options > **Reset password**; My settings > Security (senha, pergunta de segurança, MFA).

### 1.8 Tokens (generateToken, expiração, referer, IP)

`POST /sharing/rest/generateToken` (DEV-gentoken): parâmetros `username`, `password`, `client` = `referer` | `ip` |
`requestip`, `referer` (obrigatório com client=referer), `ip`, `expiration` (minutos), `f`; para token de servidor
federado, `token` + `serverURL`. Resposta: `token`, `expires` (ms desde 1970 UTC), `ssl`. "Tokens expirados são
rejeitados pelo servidor."

Tetos e padrões do Portal (E11-tokenexp, E12-tokenexp; iguais nas duas versões): três tipos — ArcGIS token, OAuth
access token, OAuth refresh token. Máximos: ArcGIS token **14 dias (20.160 min)**; OAuth access por Implicit/Client
Credentials 14 dias; OAuth access por Authorization Code **30 min**; OAuth refresh **90 dias**. Padrões quando não se
pede: ArcGIS token **120 min**; access Implicit/Client Credentials 120 min; access Authorization Code 30 min; refresh
2 semanas. Pedido acima do máximo "recebe token com o máximo". O administrador só DIMINUI, por
`maxTokenExpirationMinutes` em Portals > Self > Update (Portal Directory), valor único para toda a organização ("não é
possível valor diferente por membro"). Recomendação (E12-tokens): enviar o token no cabeçalho
`X-Esri-Authorization: Bearer …`, não na query string; trocar a chave compartilhada invalida todos os tokens.

Restrição por referer/IP no nível do ITEM (E12-limitusage): item de serviço seguro com credencial guardada pode ter
**Limit Usage**: rate limit (N pedidos por período) e lista de referrer URLs/IPs (com curinga `https://*.example.com`,
porta e protocolo explícitos); nota de que navegadores modernos mandam só a origem no Referer.

### 1.9 Chaves de API (credenciais de desenvolvedor)

Doc (DEV-apikey; E12-security "Developer credentials"; E12-priv): disponíveis **"somente com ArcGIS Enterprise 11.4
ou superior"**; exigem tipo Creator+ e os privilégios "Generate API keys" e "Assign privileges to OAuth 2.0
applications"; a credencial é um ITEM ("API key credentials") que gera **até 2 chaves**, com privilégios escolhidos,
lista de **até 100 itens** próprios acessíveis, referrers e expiração de **até 1 ano**; o valor só é visível na
criação; mudar privilégios, itens ou expiração **invalida todas as chaves** da credencial; "não suficiente para
proteger informação confidencial" (recomendada para conteúdo público). O administrador acha credenciais por
"Find API key, token, or client ID" e ordena por data de expiração em Settings > Security > Developer credentials.

### 1.10 Licenças por membro

Doc (E11-licenses, E12-licenses, E12-ut-extensions): um único `.json` do My Esri importado em Organization >
**Licenses** > Import Licenses (ou `importlicense.sh`); importar sobrescreve tudo (app que saiu do arquivo some);
abas **User types** (atribuídos × disponíveis, licenças incluídas, add-ons e papéis compatíveis) e **Add-on licenses**
(por produto: Manage, filtros, "Manage all on page"; até 100 membros por vez); extensões de tipo de usuário (Advanced
Editing = utility network, trace network, parcel fabric, topologia, attribute rules, branch versioning; incluída em
Professional/Professional Plus; Location Sharing; IPS); ArcGIS Pro: License activity (último uso, check-out
offline, End session), offline até 360 dias, aviso de expiração 1–15 dias; "pode ficar com número negativo de
licenças"; membro com tipo expirado não entra; e-mail de expiração de licença 90 dias antes.

### 1.11 Auditoria disponível

Três mecanismos, todos no Portal Administrator Directory ou na aba Reports (E11-audit, E12-audit, E12-portallogs,
E12-worklogs, E11-usage, E12-usage):

1. **Audit logs** do Portal (JSON, um registro por evento: `timeStamp`, `eventId`, `event`, `status`, `actor`,
   `actorRole`, `sourceIp`, `destinationHost`, `resource`, `userAgent`…), em
   `<install>/usr/arcgisportal/logs/<machine>/audit`; eventos: acesso ao site, criar/apagar/atualizar/desabilitar
   membro, criar/atualizar papéis, grupos e membros de grupo, compartilhar, mudar dono, adicionar/atualizar/mover/apagar
   item; retenção herdada dos logs do portal; "processáveis por SIEM". ArcGIS Server tem os próprios audit logs
   (operações de acesso a Map/Feature/GP/Image services).
2. **Portal logs** (níveis Severe…Debug, padrão Warning): códigos 202000–203999 conteúdo, 204000–205999 segurança
   (login, geração de token, criação/remoção de usuário, mudança de papel), 206000–207999 organização; consulta com
   filtro por nível, fonte, tempo, código, usuário (sem curinga), request ID e servidores federados. **Não registra**:
   logout, "REST requests to edit and query items".
3. **Usage reports** (Activity Dashboard, Organization > Reports): Content (contribuidores, resumo de compartilhamento,
   tags, "Most Popular Content" = 10 itens mais vistos desde a instalação, "máximo de 10.000 itens reportáveis"),
   Members (por papel, utilização), Groups; janela de até 12 meses; e **relatórios administrativos** (membro e item)
   em CSV, "um por tipo por hora", agendáveis diário/semanal/mensal/trimestral.

Coluna "Last login" na tabela de membros e filtro por data de último login (E12-members).

### 1.12 Gestão de membros (o que o administrador espera)

Adicionar (built-in, convite, CSV, contas do IdP em massa), editar perfil e e-mail (membro sem privilégio "não pode
mudar o próprio e-mail"), categorias de membro (3 níveis, 200 no total, 20 por membro), mudar tipo e papel (100 por
vez), **Transfer member** (tipo, papel, conteúdo, grupos, licenças, configurações e categorias para outro membro,
com "Keep account / Delete account"), reset de senha, **Disable** (não entra, "ainda conta como usuário"), **Delete**
(exige transferir ou apagar conteúdo e grupos; em massa os grupos são apagados; licenças de Pro têm de estar
devolvidas; só administrador apaga administrador), `ListUsers`/`DeleteUsers`/`TransferOwnership` por linha de comando.
Visibilidade de perfil: Private / Organization / Everyone (E12-profile, E12-members).

---

## 2. Conteúdo (Portal "Content")

### 2.1 Tipos de item

Fonte REST (DEV-itemtypes), agrupada como na doc:

- Mapas e cenas: Web Map, Web Scene, Map Area, Pro Map, 360 VR Experience.
- Camadas: Feature Service, Map Service, Image Service, Vector Tile Service, Scene Service, 3DTilesService, Stream
  Service, Feed, Group Layer, Media Layer, KML, KML Collection, WMS, WFS, WMTS, WCS, OGCFeatureServer, Feature
  Collection, Feature Collection Template, Geodata Service, Oriented Imagery Catalog.
- Ferramentas: Geocoding Service, Geometry Service, Geoprocessing Service, Network Analysis Service, Workflow Manager
  Service.
- Aplicações: Web Mapping Application, Web Experience (+ Template, Widget), Dashboard, Form (Survey123), StoryMap,
  Hub Site/Page/Project/Initiative, Notebook, Mission, Workforce Project, Mobile/Native Application, Solution, Data
  Pipeline, Code Attachment, Web AppBuilder Widget, Urban Project, Investigation, Knowledge Studio Project, etc.
- Arquivos de dado: CSV, CSV Collection, Shapefile, File Geodatabase, GeoJson, GeoPackage, GML, Apache Parquet, CAD
  Drawing, Image, PDF, Microsoft Word/Excel/PowerPoint, Visio, iWork, Document Link, Service Definition, Style,
  StoryMap Theme, Report Template, Administrative Report, Export Package, SQLite Geodatabase, Statistical Data
  Collection, Content Category Set.
- Desktop: Map/Tile/Vector Tile/Mobile Map/Mobile Scene/Project/Layer/Scene/Locator/Geoprocessing Package, Layout,
  Layer, Desktop Style, Pro Add In, Task File, Raster Function Template, Deep Learning Package, Image Collection.

Na interface (E11-supported, E12-supported, E12-add-items): My content > **New item** > Your device (arquivo, "até
500 GB pelo navegador", nome sem espaço) / URL (serviço, app, documento) / data store; ao adicionar: título, pasta
(ou criar), categorias (até 20), tags (vírgula separa), resumo, classificação. Itens de serviços de servidores
federados "são adicionados automaticamente"; web maps, scenes, dashboards etc. são criados pelos apps.

Propriedades REST de um item (DEV-itemtypes): `id`, `owner`, `created`, `modified`, `title`, `type`, `typeKeywords`,
`description`, `tags`, `snippet`, `thumbnail`, `extent`, `spatialReference`, `accessInformation`, `licenseInfo`,
`culture`, `url`, `access`, `size`, `protected`, `numComments`, `numRatings`, `avgRating`, `numViews`, `categories`,
`contentStatus`, `ownerFolder`, `properties`, `orgId`, `scoreCompleteness`.

### 2.2 Metadado do item

Página do item (E11-itemdetails, E12-itemdetails, E12-configitem), aba **Overview**: título (Edit), **resumo**
(snippet, "limite de 2.048 caracteres", aparece na busca), **descrição** (texto rico com imagem e link), **miniatura**
(600×400, 3:2, PNG/JPEG/GIF → PNG; ou "Create thumbnail from map"), **Terms of use** (licenseInfo), **Acknowledgements**
(accessInformation; aparece no rodapé do Map Viewer), **tags**, **categorias** (até 20), **classificação** (se o
administrador configurou esquema; "não restringe acesso"), **Item ID** (na URL e em Details), **Item status**
(Authoritative — só administrador, "boosted in search", liga delete protection; Deprecated — dono ou administrador),
Level of sharing, tamanho, criado/modificado, dono, pasta, **Item information score** com sugestões, ratings
(média ponderada de 5 estrelas, um voto por membro, não se vota no próprio) e comentários (se habilitados; RSS só de
item público), Short URL, Copy URL do serviço, Add to favorites, Open in… Abas **Data** (tabela e campos, edição
inline), **Visualization** (estilo, filtro, pop-up, rótulo, salvar no item ou "save a copy" como novo item), **Settings**
(content status, **Prevent this item from being accidentally deleted**, **extent** — org, feições, busca, desenho ou
coordenadas —, e ajustes por tipo: edição, exportação, sync/offline, attachments, webhooks, Limit Usage). Sublayer de
feature layer tem página própria com resumo, descrição, créditos, URL e metadado próprios.

Metadado padronizado (E11-metadata, E12-metadata, E12-editmetadata): o administrador habilita "editing metadata" e
escolhe UM estilo por organização: 11.4 = FGDC CSDGM, INSPIRE (ISO 19139), **ISO 19139 Metadata Implementation
Specification**, ISO 19139 GML3.2, North America Profile of ISO 19115 2003, ISO 19115-3; 12.0+ soma Dublin Core+
(padrão de organização nova). Armazenamento sempre em "ArcGIS metadata format" (trocar de estilo não perde nada);
editor com abas Essential/All metadata, Validate, View XML/HTML, Download (XML), Overwrite (de arquivo XML ArcGIS ou de
outro item; "Maintain metadata from item details" ou "Overwrite all"), Synchronize (campos de camada hospedada) e Reset;
o editor nasce preenchido com título, tags, resumo, descrição, créditos, termos e extent do item; limitações
literais: "o título NÃO é sincronizado entre o editor e a página do item"; só o formato ArcGIS é importável; metadado
de WFS hospedado não atualiza o capabilities.

### 2.3 Pastas e favoritos

Pastas (E11-move, E12-move): "específicas de cada conta de membro", **um nível** (a doc não descreve subpasta;
ver irritação 3); criar em My content > Create new folder; mover item pelo Overview (Folder > Move) ou em massa na
lista; administrador move itens de outro pela página do membro; administrador padrão "cria pastas em nome de
membros"; na transferência de conteúdo há "Maintain folder structure" / "Select one folder for all content" / prefixo
`from_<usuário>`; filtro de pasta por nome em My content. Favoritos (E12-itemdetails, E12-search): "Add to favorites"
no Overview ou no preview; aba **My favorites** na página Content e na busca de camadas do Map Viewer; lista por membro.

### 2.4 Busca e filtros

Página Content (E11-search, E12-search): abas **My content / My favorites / My groups / My organization / Living Atlas**;
vistas tabela, lista, grade; ordenação por título, data de modificação etc.; filtros laterais: tipo de item, data de
modificação, data de criação, tags, e conforme privilégio Categories, Collaboration, **Status** (authoritative/
deprecated), **Location** (lugar, região ou coordenadas — usa o extent do item). Busca simples: "resultados incluem todos
os itens que contêm as palavras no **título ou nas tags**" (inclui sublayers), com "Search using related terms"
ligado por padrão. Busca avançada (E12-advsearch): campos padrão de item title, tags, snippet, description, type,
typekeywords; campos nomeados `id:`, `title:`, `snippet:`, `contentstatus:`, `owner:` (case sensitive), `created:`,
`modified:` (UNIX ms, range `[a TO b]`), `type:"Feature Service"`, `typekeywords:"Hosted Service"`, `description:`,
`tags:`, `accessinformation:`, `access:` (private/shared/org/public), `categories:`, `group:<id>`, `numratings:`,
`numcomments:`, `avgrating:`, `orgid:`; operadores AND (padrão), OR, NOT, `-`, parênteses, aspas para frase. URL de
busca compartilhável: `/home/search.html?q=streets&t=content` (E12-links). Grupos têm campos próprios (`isinvitationonly`,
`access`, `phone`…).

### 2.5 Propriedade e transferência

E12-manageitems, E12-members, DEV-changeowner: o dono só reatribui se tiver "Reassign content" e o destinatário
"Receive content"; administrador transfere em massa (Members > Transfer content; Content > My organization > Change
owner; utilitário `TransferOwnership` com arquivo `atual|novo`, que cria pasta `<antigo>_root`). Regras: o novo dono
tem de ser membro de todos os grupos com que o item está compartilhado e o grupo tem de permitir que ele contribua;
trocar o dono de camada hospedada troca também o arquivo de origem e as **views dependentes**; trocar o dono de camada
NÃO troca o dono dos mapas que a usam nem dos apps; "além de apagar, nenhuma das opções muda a localização em disco
nem o ID do item".

### 2.6 Delete protection, status, exclusão e ausência de lixeira

E11-delete, E12-delete, E12-configitem, E12-manageitems, KB-recover, DEV-recyclebin: dono ou administrador apagam;
com "Prevent this item from being accidentally deleted" ligado é preciso desligar na aba Settings antes; em massa
(Content > tabela > Delete) ou por página do membro; "marque como deprecated antes de apagar"; "**uma vez apagado, o
item não está mais disponível**"; a Esri responde na base de conhecimento que "a Lixeira NÃO é suportada em ArcGIS
Enterprise" — recuperação só por restauração de backup `webgisdr` (perde tudo desde o backup). A lixeira com retenção
mínima de 14 dias existe no ArcGIS Online (junho de 2024) e tem endpoint REST próprio. Delete protection em massa
(More > Enable/Disable delete protection) por dono ou por administrador na página do membro; "Mark as Authoritative"
liga delete protection automaticamente.

### 2.7 Versões e histórico do item

Não há, na documentação lida (E11-itemdetails, E12-itemdetails, E12-configitem, E12-manageitems), histórico de
versões de item nem restauração de versão anterior: a página do item mostra só "Item updated" (data da última edição
de detalhes) e "modified"; o que existe de reprodutibilidade é exportar/importar conteúdo de grupo em pacote `.epk`
(E12-migrategroup: mantém os IDs de item, 1 GB por item, 5 GB por pacote, só de administrador padrão, só para versão
igual ou mais nova) e o `webgisdr`. Registro como "não encontrado na doc oficial", não como "não existe".

### 2.8 Dependências entre itens

Camadas hospedadas (E11-hosted, E12-hosted): dependências com o arquivo de origem ("apagar o shapefile impede
sobrescrever a camada") e entre camadas publicadas a partir da camada de feição primária — tile layer, WFS, feature
layer view, map image layer (só do Pro); "views e WFS dependem inteiramente da camada primária para acesso ao dado";
"dependentes e primária têm de ter o mesmo dono"; "**todos os dependentes têm de ser apagados antes da camada
primária**"; a página mostra "Created from", "Published as" e "Other Views". Views (E12-views): até 20 por camada;
filtro, área de interesse e campos ocultos; joined views não editáveis; herdam attachments, editor tracking, metadado
de camada e domínios; compartilhamento, delete protection, extent, export, edição e sync são independentes.
Relações formais no REST (DEV-relationships), 45 tipos, entre eles: `Map2Service`, `Data2Map`, `Data2Scene`, `Map2App`,
`Data2App`, `Scene2App`, `App2DependentApp`, `Service2Data`, `Service2Service`, `Service2Layer`, `Service2Style`,
`Style2Style`, `Map2Area`, `Area2Package`, `Item2Attachment`, `Item2Report`, `Survey2Service`, `Survey2Data`,
`SurveyForm2Service`(sic na doc como `Data2Survey`), `WorkforceMap2FeatureService`, `Notebook2WebTool`, `APIKey2Item`,
`Listed2Provisioned`, `Solution2Item`. A UI só mostra dependência de camada hospedada e a caixa de "Update sharing" de
web map (irritação 2); a "deletion order" é o que o usuário sente.

### 2.9 Hosted × referenced

E12-hosted, E12-migration, E11-share: **hosted** = dado copiado para o ArcGIS Data Store do hosting server (feature,
tile, vector tile, scene/3D tiles, imagery em Image Server, WFS de feature hospedada, knowledge graph); privadas ao
publicar; expostas por GeoServices REST; **referenced** = serviço de ArcGIS Server federado que aponta para data store
registrado (banco do cliente, pasta); item criado automaticamente ao publicar; migração de referenced exige republicar
em cada deployment (Pro, `.sd`, bulk publish). Item de serviço externo (WMS/WFS/WMTS/OGC API/KML/GeoJSON por URL) é
um "item por URL" cuja credencial pode ser guardada e cujo uso pode ser limitado (E12-limitusage). Exportação de
dado de camada hospedada é opção do dono ("allow others to export").

### 2.10 Limites conhecidos (todos literais nas fontes citadas)

| limite | valor | fonte |
|---|---|---|
| upload de arquivo pelo navegador | 500 GB | E12-supported |
| resumo (snippet) | 2.048 caracteres | E12-configitem |
| categorias por item | 20 | E12-configitem |
| categorias da organização | 3 níveis, 900 no total, nome ≤ 100 caracteres | E12-manageitems |
| categorias de grupo / de membro | 3 níveis, 200 no total | E12-owngroups, E12-members |
| grupos por usuário | 512 | E12-managegroups |
| itens em destaque por grupo | 24 | E12-owngroups |
| views por camada hospedada | 20 | E12-views |
| seleção em massa de membros | 100 | E12-members |
| itens no relatório de uso | 10.000 | E12-usage |
| exportação de grupo | 1 GB por item, 5 GB por pacote, 10 GB livres no content store | E12-migrategroup |
| categorias de login personalizadas | 100 | E12-security |
| origens CORS permitidas | 100 | E12-security |
| chaves de API | 2 por credencial, 100 itens por credencial, expiração ≤ 1 ano | DEV-apikey |
| token ArcGIS | máx. 14 dias, padrão 120 min; refresh 90 dias | E11-tokenexp |
| lockout | 5 falhas / 15 min → 15 min | E11-security |
| nome de papel / descrição | 128 / 250 caracteres | E12-configroles |
| username OIDC | 6–128 caracteres, `. _ @` | E12-oidc |
| miniatura de item / de grupo / foto de perfil | 600×400 · 400×400 · 200×200 (10 MB) | E12-configitem, E12-groups, E12-profile |
| relatório administrativo | 1 por tipo por hora | E12-usage |

---

## 3. Tabela de paridade-alvo (formato de `docs/PARIDADE.md`)

Coluna "nós" = o que o portão/hipótese do item (estado.json) e o ADR 6 (20_arquitetura.md) prometem; onde o portão
não promete, escrevo "fora do portão" para o adversário não cobrar como falta oculta e para virar sub-item quando o
gerente decidir. Estado `pendente` em toda linha (nada foi construído nem testado). "testado por" e "data" ficam
vazios até o testador do turno do item preencher.

### 3.1 L0-02-tenant-auth

| capacidade | Esri | nós | estado | testado por | data |
|---|---|---|---|---|---|
| isolamento por organização | 1 portal = 1 organização; várias organizações = vários portais ou collaboration (E12-access) | inquilino (`tenant`) na mesma instalação, RLS `FOR ALL` com `USING`/`WITH CHECK` em toda tabela com `tenant_id`; teste cruzado A→B falha em toda rota do OpenAPI | pendente | | |
| conta interna (built-in) | usuário/senha no identity store do portal; criação pelo admin, convite, CSV, ou auto-cadastro se permitido (E12-access, E12-members) | `usuario` por inquilino, criado pelo admin do inquilino pela tela "Usuários"; sem auto-cadastro | pendente | | |
| login / logout | sign-in com botões na ordem configurada; token de sessão; logout não é logado (E12-security, E12-portallogs) | login/logout pelo navegador (e2e com captura); `sessao` com hash e `tenant_id`; logout registrado em `log_acesso` | pendente | | |
| tipos de usuário (Viewer, Contributor, Mobile Worker, Creator, Professional, Professional Plus) e licença por membro | tipo define apps e teto de privilégios; licença `.json` do My Esri (E11-usertypes, E11-licenses) | fora do portão: não há licença por assento; perfil cobre o que o tipo cobre (visualizador ≈ Viewer; campo ≈ Mobile Worker; editor ≈ Contributor/Data Editor; admin ≈ Administrator) | pendente | | |
| papéis padrão (Viewer, Data Editor, User, Publisher, Administrator) | 5 papéis fixos, compatibilidade por tipo (E11-roles) | perfis admin / editor / visualizador / campo + superadmin (ADR 6); sem equivalente a Publisher separado de editor | pendente | | |
| papéis personalizados com lista de privilégios | Member roles > Create role, ~70 privilégios gerais + administrativos (E11-priv) | fora do portão: `permissao` prevista no portão ("tabelas tenant/usuario/sessao/token/permissao") mas sem editor de papel na tela | pendente | | |
| MFA por app TOTP, admin desliga, exigir para todos | TOTP opcional por membro (11.4), "Enforce MFA" com isenções (12.1), exige e-mail (E11-security, E12-security) | 2FA TOTP no `usuario`; ligar/desligar pelo próprio usuário e desligar pelo admin do inquilino (e2e); sem exigência global no portão | pendente | | |
| política de senha e bloqueio | ≥ 8 c/ letra e número; complexidade, expiração, histórico; lockout 5/15 min configurável (E11-security) | troca de senha pelo navegador (portão); regra de senha e bloqueio no `usuario` ("bloqueio", ADR 6) — limiares a declarar no ADR do item | pendente | | |
| reset de senha pelo admin, senha temporária, e-mail | Members > Reset password; e-mail se SMTP configurado (E12-members) | fora do portão (sem e-mail no L0-02) | pendente | | |
| SAML 2.0 / OpenID Connect / AD-LDAP, grupos do IdP | New SAML login / New OpenID Connect login; grupos SAML/OIDC ligados a grupos do portal (E11-saml, E11-oidc) | fora do portão | pendente | | |
| token de sessão (generateToken): expiração, referer, IP, tetos | `generateToken` com `expiration`, `client`/`referer`/`ip`; máx. 14 d, padrão 120 min; `maxTokenExpirationMinutes` (DEV-gentoken, E11-tokenexp) | `sessao` com expiração; `token_servico` com hash, escopos, restrição (referer/IP), revogação (ADR 6); tetos a declarar | pendente | | |
| token de serviço de longa duração (API key) | credencial de desenvolvedor: 2 chaves, 100 itens, ≤ 1 ano, referrers, invalidação (DEV-apikey) | `token_servico` revogável, com escopo, com **log de leitura (IP/rota/bytes)** — vai além da Esri, que não loga leitura REST (E12-portallogs) | pendente | | |
| log de auditoria (login, membro, papel, grupo, compartilhamento, dono, item) | audit logs JSON + portal logs por código; consulta no Portal Admin Directory (E11-audit, E12-worklogs) | `log_acesso` unifica login e leitura por token (ADR 6); consulta pela tela: fora do portão | pendente | | |
| relatórios de uso e relatório administrativo de membros | Activity Dashboard, CSV agendável (E11-usage) | fora do portão | pendente | | |
| gestão de membros: adicionar, desabilitar, apagar com transferência de conteúdo, transferir membro | Members tab, Disable, Delete (transferir ou apagar conteúdo), Transfer member (E12-members) | tela "Usuários (admin)" com criar/editar/desabilitar (portão: "usuários (admin) funcionam pelo navegador"); apagar com transferência: fora do portão | pendente | | |
| perfil do membro: nome, foto, bio, visibilidade, idioma, unidades, página inicial | My profile / My settings (E12-profile) | fora do portão (nome e e-mail no `usuario`) | pendente | | |
| ao menos um administrador por organização; só admin muda papel de admin | regra literal (E12-roles, E12-members) | superadmin + admin do inquilino (ADR 6); regra "último admin não se apaga" a testar | pendente | | |

### 3.2 L0-03-catalogo

| capacidade | Esri | nós | estado | testado por | data |
|---|---|---|---|---|---|
| item = objeto de catálogo com tipo | ~150 tipos REST em 6 famílias (DEV-itemtypes) | item = camada vetorial, raster, mapa, app, painel, formulário, fluxo, rede (hipótese) | pendente | | |
| metadado básico: título, resumo, descrição, tags, créditos, termos de uso, miniatura, extent, categorias, ID | Overview + Settings do item (E11-itemdetails, E12-configitem) | metadado editável no detalhe do item (portão); campos mínimos = título, resumo, descrição, tags, dono, miniatura; créditos, termos, extent e categorias: a declarar no ADR | pendente | | |
| metadado ISO 19139 / 19115-3 / FGDC / INSPIRE com editor, validação, XML | um estilo por organização; editor com Validate, XML, Overwrite (E11-metadata) | fora do portão | pendente | | |
| pastas (um nível, por membro) | Create new folder, Move (E11-move) | criar pasta (portão) | pendente | | |
| favoritos | Add to favorites, aba My favorites (E12-itemdetails) | fora do portão | pendente | | |
| tela Conteúdo: lista/grade, ordenar, filtrar por tipo, data, tags, dono, status, categoria, localização | Content page com abas My content / My favorites / My groups / My organization (E11-search) | tela "Conteúdo" com lista/grade, busca, filtros por tipo/tag/dono (portão) | pendente | | |
| busca em título e tags; busca avançada por campo, booleana, intervalo | E11-search, E12-advsearch | busca (portão); sintaxe por campo: fora do portão | pendente | | |
| compartilhamento: privado / grupo / organização / público, com regra de dependência mapa → camada | Share > Owner/Organization/Everyone/Groups; "Update sharing" (E11-share) | privado / grupo / inquilino / **link por token** (hipótese); "público" (anônimo) não prometido; link revogado tem de negar acesso (refutação) | pendente | | |
| grupos: visibilidade, entrada, contribuição, shared update, administrativo, papéis de grupo | E12-groups, E12-owngroups | tabela `grupo` + compartilhamento por grupo (portão); shared update, papéis de grupo, entrada por pedido: fora do portão | pendente | | |
| propriedade e transferência de dono (com regra de grupos e de dependentes) | Change owner, Transfer content, TransferOwnership (E12-manageitems) | dono no item (hipótese); transferência: fora do portão | pendente | | |
| delete protection e exclusão com confirmação; status authoritative/deprecated | Settings > Prevent … deleted; Mark as Authoritative/Deprecated (E12-configitem) | excluir (portão); delete protection e status: fora do portão | pendente | | |
| lixeira / restauração | não existe no Enterprise (KB-recover) | fora do portão (a Esri também não tem — ver irritação 5) | pendente | | |
| histórico de versões do item | não encontrado na doc oficial (seção 2.7) | fora do portão | pendente | | |
| dependências entre itens (camada ↔ mapa ↔ app; views; ordem de exclusão) | 45 tipos de relação REST; regra "apague os dependentes antes" (E12-hosted, DEV-relationships) | fora do portão | pendente | | |
| hosted × referenced | Data Store × serviço federado de dado registrado (E12-hosted) | conceito futuro (L2): fora do portão | pendente | | |
| limites: 500 GB upload, 20 categorias/item, 900 categorias, 512 grupos/usuário, 20 views | tabela 2.10 | limites próprios a declarar no ADR do item | pendente | | |
| OpenAPI publicado das rotas de conteúdo | REST `/sharing/rest` documentado (DEV-*) | OpenAPI publicado (portão) | pendente | | |
| e2e criar-editar-compartilhar-excluir com captura | — | e2e (portão) | pendente | | |

---

## 4. As dez coisas em que o usuário Esri mais se irrita ao migrar (fonte, URL, data 2026-09-05)

Critério de inclusão: reclamação registrada em fonte com URL viva (Esri Community, base de conhecimento Esri, doc
oficial de migração ou doc de migração de fornecedor). A ordem é por frequência e gravidade nas fontes lidas, não por
medição de volume.

1. **IDs de item e URLs gravados dentro do JSON dos mapas e apps.** "Ao criar um item, o JSON é gravado em disco no
   portal, e cada JSON tem as URLs dos serviços e web maps codificadas"; trocar a URL do portal depois do 1º item
   "quebra o portal" e a federação (COM-urlchange, COM-migratingportal). Ao copiar Experience Builder entre portais
   "não pega todos os item IDs e URLs que precisam ser trocados", "Item does not exist" (COM-migrate, COM-migratep2).
   O ID de item "não pode ser modificado em item existente" e por isso há artigo de suporte só para reatribuir ID
   (KB-itemid); a exportação de grupo existe justamente para "manter os IDs" (E12-migrategroup). Para o desenho:
   ID de item estável, opaco e independente de host; referências entre itens por ID, nunca por URL absoluta; URL
   pública derivada do ID.
2. **"Update sharing": a caixa que muda o compartilhamento das camadas quando se compartilha o mapa.** A janela só
   dá "Cancel" ou "Update"; "Update" REBAIXA camadas públicas para o nível do mapa; "demorou demais para descobrir
   que Cancel ainda salva o mapa"; "experiência confusa quando alguém abre o mapa e não vê as camadas"
   (COM-updatesharing, COM-sharingidea). Doc: "se a camada está compartilhada só com um grupo, não carrega no mapa
   para quem não é do grupo" (E12-itemdetails). Para o desenho: ao compartilhar um mapa, mostrar a árvore de
   dependências com o nível de cada camada e oferecer "elevar para o nível do mapa" como opção explícita, nunca
   rebaixar em silêncio.
3. **Pastas de um só nível, sem subpasta, sem pasta em grupo.** Pedido com anos de vida na Ideias
   (COM-subfolders, COM-subfolders-ent, COM-nestedagol); a resposta da Esri é "use categorias" (E12-manageitems). Para o
   desenho: pasta hierárquica por inquilino desde o L0-03 (o portão já pede "criar pasta"); categorias além disso.
4. **Transferir dono é uma caça item a item, e trava em grupo shared update e em mapa com área offline.** "Quando um
   empregado sai e há muitos itens para reatribuir, perseguir cada item vira um projeto"; é preciso tirar do grupo,
   transferir, e o novo dono recompartilhar (COM-ownership); "Unable to delete member: member must not own items or
   groups" (KB-deletemember). Regras oficiais: novo dono tem de estar em todos os grupos do item e o grupo tem de
   deixá-lo contribuir (E12-manageitems). Para o desenho: transferência em massa que preserva compartilhamentos e
   pastas, com pré-checagem que lista o que vai falhar antes de executar.
5. **Não há lixeira no Enterprise; apagou, perdeu.** KB oficial: "Recycle Bin não é suportado em ArcGIS Enterprise";
   recuperação só por restaurar backup inteiro com `webgisdr`, perdendo o que veio depois (KB-recover); Ideia aberta
   "Recycle bin for Enterprise Portal" (COM-recyclebin); enquanto isso o Online ganhou lixeira com 14 dias
   (KB-recyclebin-agol, DEV-recyclebin). Para o desenho: exclusão lógica com retenção declarada e restauração pela
   tela, no L0-03 ou em sub-item.
6. **Item preso: não apaga, não edita, "double-delete-protected".** Threads longas de "Force delete an item"
   (4 páginas), itens órfãos com "Unable to delete item" sem delete protection ligada, itens padrão da Esri que não se
   apagam nem se reatribuem; contorno = parar o serviço e apagar pasta no disco (COM-forcedelete). Para o desenho:
   estado do item sempre consistente com o banco (nada em disco fora de transação); delete protection é um campo,
   não um segredo; superadmin sempre consegue apagar com registro em log.
7. **Sobrescrever camada do Pro quebra todos os mapas que a usam.** "Overwrite web layer removes layer from all web
   maps"; causa = IDs de sublayer diferentes; a doc do Pro pede "Compare" antes de sobrescrever (COM-overwrite,
   COM-overwrite-pro). Para o desenho: substituição de dado da camada mantém o ID do item e o ID das sublayers;
   checagem de esquema antes de aceitar a carga; aviso com a lista de mapas dependentes.
8. **Token: 14 dias no máximo, "Invalid Token" em app com token vencido, teto único para a organização.** "Portal só
   aceita ≤ 2 semanas", "pedi 2 semanas e expirou em 30–40 minutos", "fluxo infinito de pedidos com Invalid Token
   depois do upgrade para 11.5" (COM-tokenmax, COM-invalidtoken); doc confirma o teto e que "não é possível valor por
   membro" (E11-tokenexp). Para o desenho: `token_servico` com validade por token e por escopo, erro 401 com motivo
   legível ("expirado em …", "revogado em …"), e renovação sem derrubar o app.
9. **Busca que não acha o que se vê na frente: relevância sem peso no título, tags que não indexam.** Ideia "Portal
   Search Results" (COM-searchidea): resultados "não priorizam o item cujo nome bate", tags adicionadas por API "não
   aparecem"; doc: busca simples só em título e tags, com "related terms" ligado por padrão (E11-search). Para o
   desenho: busca com peso explícito (título > tags > resumo > descrição), índice atualizado na mesma transação da
   edição, e filtro por dono/tipo/tag que o portão já pede.
10. **Migrar serviços referenciados exige republicar tudo, e o resto do ecossistema (mapas, apps, credenciais) não
    vem junto.** Doc oficial: serviços que referenciam data store "precisam ser publicados em cada deployment"
    (E12-migration); usuário partindo para GeoServer relata "vou ter de reconstruir os serviços WMS" (COM-geoserver);
    fornecedor de campo documenta o "switching is challenging" e os passos (SLYR para estilos) (MERGIN-migrate).
    Para o desenho: importador de conteúdo Esri (item JSON + web map JSON + estilo) como sub-item de L2/L6, e tabela
    de paridade que diga o que NÃO vem (Experience Builder, Dashboards, Survey123) em vez de prometer.

---

## Riscos

- **Versão-alvo × doc viva.** "latest" já é 12.1 e a série 11.x continua publicada. O adversário pode cobrar
  capacidade 12.x (Enforce MFA, Dublin Core+) como se fosse 11.x. Este handoff separa as duas; o ADR do L0-02 deve
  citar a versão-alvo em uma linha.
- **HTTP 200 falso.** Nove nomes antigos de página respondem 200 na página inicial da doc. Toda citação neste
  handoff usa URL cuja `url_effective` é a própria página (anexo A traz o efetivo).
- **Tabela 3 é promessa, não medição.** As colunas "nós" vêm do texto do portão/hipótese e do ADR 6; nada foi
  construído. Toda linha nasce `pendente`; quem escrever `feito` sem `tests/medidas/<item>.json` viola P4.
- **Enunciado misturou tipo de usuário e papel** ("Creator, Professional" são tipos). Corrigido na seção 1.2; se o
  gerente reproduzir a lista errada em MANUAL/PARIDADE, o adversário derruba.
- **Sem Pro/AGOL reais.** Nada aqui foi visto numa organização Esri viva; é doc. Paridade com Pro/AGOL reais só quando
  o parceiro testar (P4), e fica `pendente` até lá.
- **Irritações 1–10 são qualitativas.** Fonte = threads e ideias com URL; não há contagem de votos citada porque a
  página não expõe número estável ao `curl`. Não citar "as mais votadas".

## Pendências

1. Gerente: decidir se pastas hierárquicas, favoritos, delete protection, status authoritative/deprecated e lixeira
   entram no L0-03 ou viram sub-itens `L0-03-b…` (todos "fora do portão" na tabela 3.2, mas quatro deles são
   irritações de migração).
2. Gerente/arquiteto: declarar no ADR do L0-02 os limiares de senha, lockout e expiração de sessão/token (a Esri
   tem números; os nossos precisam existir para o testador medir).
3. Arquiteto L0-03: escolher entre "link por token" (hipótese) e "público anônimo" (Esri); a refutação exige que o
   link revogado negue acesso — isso pede tabela `compartilhamento_link` com `revogado_em` e teste.
4. Cronista: `docs/PARIDADE.md` recebe as tabelas 3.1 e 3.2 quando o item entrar em construção (não antes, para não
   parecer feito).
5. Fora deste turno: paridade das seções 1.4 (grupos SAML), 1.9 (chaves de API) e 2.8 (relações formais) quando
   chegarem L2/L6.

## Para o próximo papel

- **Arquiteto (L0-02):** usar a seção 1 como lista de verificação do ADR: papéis padrão (1.2), 2FA TOTP com
  desligamento pelo admin (1.6), política de senha e lockout com números (1.7), token com `client`/`referer`/`ip` e
  teto declarado (1.8), `log_acesso` cobrindo os eventos do audit log Esri (1.11) mais a leitura por token que a Esri
  não loga.
- **Arquiteto (L0-03):** seção 2 é o espelho do Portal Content: campos do item (2.2), pastas (2.3), busca (2.4),
  compartilhamento com regra de dependência (2.9 e irritação 2), exclusão (2.6) e limites (2.10). Modelar o item com
  as propriedades REST listadas em 2.1 como referência de nome (`snippet`, `licenseInfo`, `accessInformation`,
  `contentStatus`, `protected`, `ownerFolder`), o que barateia o conector Esri do L6.
- **Backend/frontend:** os nomes de tela e de botão da Esri (Content > My content / New item / Share / Move /
  Delete; item page > Overview / Settings) estão em 1.x e 2.x com a fonte; reproduzir a semântica, não o nome.
- **Adversário:** a tabela 3 é a lista a cobrar; a seção 4 é a lista do que NÃO reproduzir; o anexo A é a lista de
  URLs para conferir por conta própria.

## Anexo A — URLs testadas (curl -sIL, 2026-09-05 12:39 UTC; código HTTP final)

| chave | URL | HTTP |
|---|---|---|
| E11-roles | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/roles.htm | 200 |
| E11-usertypes | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/user-types-orgs.htm | 200 |
| E11-priv | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/privileges-for-roles-orgs.htm | 200 |
| E11-security | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/configure-security.htm | 200 |
| E11-saml | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/configuring-a-saml-compliant-identity-provider-with-your-portal.htm | 200 |
| E11-oidc | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/openid-connect-logins.htm | 200 |
| E11-tokenexp | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/specify-the-default-token-expiration-time.htm | 200 |
| E11-audit | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/understand-audit-logs.htm | 200 |
| E11-licenses | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/manage-licenses.htm | 200 |
| E11-members | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/manage-members.htm | 200 |
| E11-manageitems | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/manage-items.htm | 200 |
| E11-usage | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/about-usage-reports.htm | 200 |
| E11-itemdetails | https://enterprise.arcgis.com/en/portal/11.4/use/item-details.htm | 200 |
| E11-configitem | https://enterprise.arcgis.com/en/portal/11.4/use/configure-item-details.htm | 200 |
| E11-share | https://enterprise.arcgis.com/en/portal/11.4/use/share-items.htm | 200 |
| E11-groups | https://enterprise.arcgis.com/en/portal/11.4/use/create-groups.htm | 200 |
| E11-search | https://enterprise.arcgis.com/en/portal/11.4/use/search.htm | 200 |
| E11-metadata | https://enterprise.arcgis.com/en/portal/11.4/use/metadata.htm | 200 |
| E11-supported | https://enterprise.arcgis.com/en/portal/11.4/use/supported-items.htm | 200 |
| E11-hosted | https://enterprise.arcgis.com/en/portal/11.4/use/hosted-web-layers.htm | 200 |
| E11-categories | https://enterprise.arcgis.com/en/portal/11.4/use/content-categories.htm | 200 |
| E11-delete | https://enterprise.arcgis.com/en/portal/11.4/use/delete-items.htm | 200 |
| E11-move | https://enterprise.arcgis.com/en/portal/11.4/use/move-items.htm | 200 |
| E11-migration | https://enterprise.arcgis.com/en/portal/11.4/administer/windows/migration-strategies.htm | 200 |
| E12-roles | https://doc.esri.com/en/arcgis-enterprise/latest/administer/member-roles.html | 200 |
| E12-usertypes | https://doc.esri.com/en/arcgis-enterprise/latest/administer/user-types-orgs.html | 200 |
| E12-priv | https://doc.esri.com/en/arcgis-enterprise/latest/administer/privileges-for-roles-orgs.html | 200 |
| E12-configroles | https://doc.esri.com/en/arcgis-enterprise/latest/administer/configure-roles.html | 200 |
| E12-security | https://doc.esri.com/en/arcgis-enterprise/latest/administer/configure-security.html | 200 |
| E12-access | https://doc.esri.com/en/arcgis-enterprise/latest/administer/managing-access-to-your-portal.html | 200 |
| E12-saml | https://doc.esri.com/en/arcgis-enterprise/latest/deploy/configuring-a-saml-compliant-identity-provider-with-your-portal.html | 200 |
| E12-oidc | https://doc.esri.com/en/arcgis-enterprise/latest/deploy/openid-connect-logins.html | 200 |
| E12-profile | https://doc.esri.com/en/arcgis-enterprise/latest/create/profile.html | 200 |
| E12-tokenexp | https://doc.esri.com/en/arcgis-enterprise/latest/administer/specify-the-default-token-expiration-time.html | 200 |
| E12-tokens | https://doc.esri.com/en/arcgis-enterprise/latest/administer/about-arcgis-tokens.html | 200 |
| E12-audit | https://doc.esri.com/en/arcgis-enterprise/latest/administer/understand-audit-logs.html | 200 |
| E12-portallogs | https://doc.esri.com/en/arcgis-enterprise/latest/plan/about-portal-logs.html | 200 |
| E12-worklogs | https://doc.esri.com/en/arcgis-enterprise/latest/administer/work-with-portal-logs.html | 200 |
| E12-usage | https://doc.esri.com/en/arcgis-enterprise/latest/administer/work-with-usage-reports.html | 200 |
| E12-licenses | https://doc.esri.com/en/arcgis-enterprise/latest/administer/manage-licenses.html | 200 |
| E12-members | https://doc.esri.com/en/arcgis-enterprise/latest/administer/manage-members.html | 200 |
| E12-manageitems | https://doc.esri.com/en/arcgis-enterprise/latest/administer/manage-items.html | 200 |
| E12-managegroups | https://doc.esri.com/en/arcgis-enterprise/latest/administer/manage-groups.html | 200 |
| E12-itemdetails | https://doc.esri.com/en/arcgis-enterprise/latest/create/item-details.html | 200 |
| E12-configitem | https://doc.esri.com/en/arcgis-enterprise/latest/share/configure-item-details.html | 200 |
| E12-share | https://doc.esri.com/en/arcgis-enterprise/latest/share/share-items.html | 200 |
| E12-groups | https://doc.esri.com/en/arcgis-enterprise/latest/share/create-groups.html | 200 |
| E12-owngroups | https://doc.esri.com/en/arcgis-enterprise/latest/share/own-groups.html | 200 |
| E12-search | https://doc.esri.com/en/arcgis-enterprise/latest/create/search.html | 200 |
| E12-advsearch | https://doc.esri.com/en/arcgis-enterprise/latest/create/advanced-search.html | 200 |
| E12-metadata | https://doc.esri.com/en/arcgis-enterprise/latest/share/metadata.html | 200 |
| E12-editmetadata | https://doc.esri.com/en/arcgis-enterprise/latest/share/edit-metadata.html | 200 |
| E12-supported | https://doc.esri.com/en/arcgis-enterprise/latest/share/supported-items.html | 200 |
| E12-hosted | https://doc.esri.com/en/arcgis-enterprise/latest/share/hosted-web-layers.html | 200 |
| E12-views | https://doc.esri.com/en/arcgis-enterprise/latest/share/create-hosted-views.html | 200 |
| E12-categories | https://doc.esri.com/en/arcgis-enterprise/latest/create/content-categories.html | 200 |
| E12-delete | https://doc.esri.com/en/arcgis-enterprise/latest/share/delete-items.html | 200 |
| E12-move | https://doc.esri.com/en/arcgis-enterprise/latest/share/move-items.html | 200 |
| E12-links | https://doc.esri.com/en/arcgis-enterprise/latest/share/link-to-items.html | 200 |
| E12-limitusage | https://doc.esri.com/en/arcgis-enterprise/latest/share/limit-usage-of-secure-services.html | 200 |
| E12-migration | https://doc.esri.com/en/arcgis-enterprise/latest/deploy/migration-strategies.html | 200 |
| E12-migrategroup | https://doc.esri.com/en/arcgis-enterprise/latest/administer/migrate-group-content.html | 200 |
| DEV-gentoken | https://developers.arcgis.com/rest/users-groups-and-items/generate-token/ | 200 |
| DEV-apikey | https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/ | 200 |
| DEV-itemtypes | https://developers.arcgis.com/rest/users-groups-and-items/items-and-item-types/ | 200 |
| DEV-relationships | https://developers.arcgis.com/rest/users-groups-and-items/relationship-types/ | 200 |
| DEV-recyclebin | https://developers.arcgis.com/rest/users-groups-and-items/recycle-bin-reference/ | 200 |
| DEV-changeowner | https://developers.arcgis.com/documentation/portal-and-data-services/portal-service/content-items/manage/change-item-ownership/ | 200 |
| KB-recover | https://support.esri.com/en-us/knowledge-base/faq-can-deleted-items-be-recovered-in-arcgis-enterprise-000031852 | 200 |
| KB-itemid | https://support.esri.com/en-us/knowledge-base/how-to-assign-portal-item-id-to-a-republished-map-servi-000030927 | 200 |
| KB-deletemember | https://support.esri.com/en-us/knowledge-base/error-unable-to-delete-member-user-name-member-must-not-000024210 | 200 |
| KB-recyclebin-agol | https://support.esri.com/en-us/knowledge-base/how-to-enable-recycle-bin-in-arcgis-online-000033615 | 200 |
| COM-migrate | https://community.esri.com/t5/arcgis-enterprise-documents/migrate-content-for-arcgis-enterprise-arcgis/ta-p/1365455 | 200 |
| COM-migratep2 | https://community.esri.com/t5/arcgis-enterprise-documents/migrate-content-for-arcgis-enterprise-arcgis/ta-p/1365455/page/2 | 200 |
| COM-recyclebin | https://community.esri.com/t5/arcgis-enterprise-ideas/recycle-bin-for-enterprise-portal/idi-p/1393071 | 200 |
| COM-forcedelete | https://community.esri.com/t5/arcgis-enterprise-portal-questions/force-delete-an-item-in-portal-for-arcgis/td-p/426737 | 200 |
| COM-updatesharing | https://community.esri.com/t5/arcgis-enterprise-portal-questions/sharing-webmap-prompts-update-sharing/td-p/1537207 | 200 |
| COM-sharingidea | https://community.esri.com/t5/arcgis-online-ideas/make-options-more-intuitive-when-sharing-a-web-map/idi-p/1236026 | 200 |
| COM-subfolders | https://community.esri.com/t5/arcgis-online-ideas/additional-folders-sub-folders-in-my-content/idi-p/969504 | 200 |
| COM-subfolders-ent | https://community.esri.com/t5/arcgis-enterprise-ideas/allow-subfolder-organization-in-portal-hosted/idi-p/1378209 | 200 |
| COM-ownership | https://community.esri.com/t5/arcgis-online-ideas/permit-changing-ownership-of-items-shared-with/idi-p/1256306 | 200 |
| COM-overwrite | https://community.esri.com/t5/arcgis-online-questions/overwrite-web-layer-now-breaks-any-maps-using-that/td-p/1165140 | 200 |
| COM-overwrite-pro | https://community.esri.com/t5/arcgis-pro-questions/can-i-really-not-overwrite-a-web-layer-from-pro/td-p/1536972 | 200 |
| COM-tokenmax | https://community.esri.com/t5/arcgis-enterprise-portal-questions/max-token-expiration-minutes-in-portal/td-p/1582494 | 200 |
| COM-invalidtoken | https://community.esri.com/t5/arcgis-enterprise-portal-questions/invalid-token-when-opening-content-in-portal/td-p/1644188 | 200 |
| COM-searchidea | https://community.esri.com/t5/arcgis-enterprise-ideas/portal-search-results-arcgis-enterprise-10-9-1/idi-p/1202276 | 200 |
| COM-urlchange | https://community.esri.com/t5/arcgis-enterprise-portal-questions/change-portal-web-adaptor-url-to-new-url/td-p/1281486 | 200 |
| COM-migratingportal | https://community.esri.com/t5/arcgis-enterprise-portal-questions/migrating-arcgis-portal/td-p/1244140 | 200 |
| COM-geoserver | https://community.esri.com/t5/publishing-and-managing-services-questions/moving-services-from-arcgis-server-to-geoserver/td-p/1172935 | 200 |
| COM-nestedagol | https://community.esri.com/t5/arcgis-online-questions/nested-content-folders-in-arcgis-online/td-p/147233 | 200 |
| BLOG-migrategroup | https://www.esri.com/arcgis-blog/products/arcgis-enterprise/data-management/migrate-group-content-across-arcgis-enterprise | 403 (não usada) |
| MERGIN-migrate | https://merginmaps.com/docs/migrate/arcgis/ | 200 |

Observação sobre `url_effective`: as 24 URLs E11 respondem 200 no próprio endereço, sem redirecionamento; as URLs
E12 respondem 200 no próprio endereço em `doc.esri.com/.../latest/` (versão 12.1); nenhuma das 92 citadas cai na
página inicial da doc.

## Resumo em 8 linhas

1. A doc "latest" da Esri já é 12.1; a série 11.4 segue publicada e foi usada como versão-alvo; 92 URLs testadas, 91 com HTTP 200, 1 (blog) 403 e descartada.
2. Identidade Esri = tipo de usuário (6) × papel (5 fixos ou personalizado com ~70 privilégios) × licença; "Creator/Professional" são tipos, não papéis.
3. Segurança built-in: senha ≥ 8 com letra e número, lockout 5/15 min, MFA TOTP opcional (obrigatória só na 12.1), SAML/OIDC/AD-LDAP com grupos do IdP; SAML/OIDC ficam fora de senha, MFA e reset do portal.
4. Token: `generateToken` com referer/IP, máximo 14 dias e padrão 120 min, teto único por organização; chaves de API desde 11.4 (2 por credencial, 100 itens, 1 ano).
5. Auditoria: audit log JSON + portal logs por código + relatórios de uso; a Esri não loga leitura REST, o nosso `log_acesso` promete isso.
6. Conteúdo: item com título, resumo (2.048 c), descrição, tags, créditos, termos, miniatura, extent, categorias, status, delete protection; pastas de um nível; busca em título e tags; sem lixeira e sem histórico de versão no Enterprise.
7. Tabelas de paridade-alvo escritas para L0-02 (16 linhas) e L0-03 (18 linhas), coluna "nós" com o que o portão promete e "fora do portão" onde não promete, tudo `pendente`.
8. Dez irritações de migração com fonte: IDs/URLs gravados no JSON, "Update sharing", pastas planas, transferência de dono, sem lixeira, item preso, sobrescrita quebra mapas, token de 14 dias, busca sem peso no título, republicar serviços referenciados.
