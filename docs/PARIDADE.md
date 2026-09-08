# Paridade com o ArcGIS Enterprise

Tabela viva, uma linha por capacidade. A coluna "Esri" vem do papel `esri` (`laco/handoffs/T1/21_esri.md`, doc
Esri datada de 2026-09-05, referências E11-*/E12-*/DEV-* daquele arquivo); a coluna "nós" descreve o que existe no
repositório; "estado" é `feito`, `parcial` ou `fora` (fora do portão do item, com o item que o cobre). "testado por"
nomeia quem conferiu no turno; "data" é a data da conferência. Paridade contra ArcGIS Pro e ArcGIS Online reais só
quando o parceiro testar com credencial própria (decisão D20, aberta): até lá toda linha fica `pendente` nessa
coluna, nunca `feito`.

Regra: nenhuma linha vira `feito` antes do testador e do adversário do turno; a tabela é preenchida pelo cronista
depois deles.

## Identidade e acesso (item L0-02-tenant-auth, turno 2; ADR 0002 seção 17)

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| isolamento por organização | 1 portal = 1 organização; várias organizações = vários portais ou collaboration | inquilino (`tenant`) na mesma instalação; RLS `FOR ALL` com `USING`/`WITH CHECK` em toda tabela com `tenant_id` (22 de 22, inclusive partições); funções `SECURITY DEFINER` com `contexto_confere`; teste cruzado gerado do OpenAPI (74 rotas, 4 vetores, digest de B) | feito | testador (73 rotas vivas, 411 chamadas, 0 cruzado) e adversário T2 (2 rodadas, inclusive reinstalação) | 2026-09-05 | pendente (D20) |
| conta interna (built-in) | usuário/senha no identity store; criação pelo admin, convite, CSV ou auto-cadastro | `usuario` por inquilino, criado pelo administrador na tela Usuários (individual e lote de 100); sem auto-cadastro, sem convite por e-mail, sem CSV | feito (sem CSV/convite) | testador e adversário T2 | 2026-09-05 | pendente (D20) |
| login / logout | sign-in com token de sessão; logout não é registrado | login e logout pelo navegador (e2e com captura); cookie com hash no banco; logout registrado em `log_acesso` com `resultado = logout` | feito (registra logout, que a Esri não registra) | testador (e2e 9/9) e adversário T2 (login real no playwright) | 2026-09-05 | pendente (D20) |
| tipos de usuário e licença por membro | tipo define apps e teto; licença `.json` por membro | perfil (`admin`, `editor`, `visualizador`, `campo`) = teto de privilégios; não há licença nem assento por membro (decisão da spec) | fora (decisão) | — | 2026-09-05 | pendente (D20) |
| papéis padrão (Viewer, Data Editor, User, Publisher, Administrator) | 5 papéis fixos | 4 perfis; o que a Esri chama Publisher é o privilégio `conteudo.publicar_*` dentro de `editor` | parcial (declarado; sem papel Publisher separado) | testador T2 (tela Papéis: 46/26/7/11 privilégios por perfil) | 2026-09-05 | pendente (D20) |
| papéis personalizados com lista de privilégios | ~74 privilégios gerais e administrativos (seção abaixo) | 47 privilégios em vocabulário fechado (`docs/PRIVILEGIOS.md`, gerado do banco); papéis por inquilino pela API e pela tela Papéis (criar, editar, apagar; perfil mínimo calculado; papel em uso não se apaga); conferência linha a linha contra a lista Esri = seção "Privilégios e papéis personalizados" abaixo (item L0-07-b, T3) | parcial (vocabulário menor por decisão — sem notebook/OAuth app/pipeline/versionamento; ver seção abaixo) | testador T2 (e2e `test_papeis`) e T3 (`test_privilegios_matriz.py`: toda rota do OpenAPI vivo chamada sem o privilégio declarado dá 403; `test_privilegios_doc.py`: documento == banco) | 2026-09-06 | pendente (D20) |
| MFA por app TOTP; admin desliga; exigir para todos | TOTP opcional por membro; "Enforce MFA" com isenções; exige e-mail | TOTP por usuário com QR, 8 códigos de recuperação e anti-replay; admin desliga; `exigir_2fa` por inquilino vira pendência de sessão (entra só para configurar); sem lista de isenção; sem e-mail | feito (sem isenção individual) | testador (replay, passo +10, recuperação reusada = 401) e adversário T2 | 2026-09-05 | pendente (D20) |
| política de senha e bloqueio | ≥ 8 com letra e número; complexidade, expiração, histórico; lockout 5/15 min | ≥ 8 com letra e número, máximo 128, ≠ login, histórico 5, expiração opcional; bloqueio 5 falhas/15 min por usuário no banco + 10 r/min por IP no nginx; configurável em `tenant.config.auth`; tela de configuração é o L0-07-a | feito (tela de política parcial) | testador (regras nomeadas, 6ª certa = 423, inquilino com `bloqueio_tentativas = 3`) e adversário T2 | 2026-09-05 | pendente (D20) |
| reset de senha pelo admin, senha temporária, e-mail | Reset password; e-mail se SMTP | `POST /api/usuarios/{id}/senha` gera senha temporária mostrada uma vez, marca `trocar_senha`, apaga sessões; sem e-mail (L0-07-d) | parcial (sem e-mail) | testador e adversário T2 (201 com `senha_temporaria` e `trocar_senha = t`) | 2026-09-05 | pendente (D20) |
| SAML 2.0 / OpenID Connect, grupos do IdP | New SAML login / New OIDC login; grupos ligados | gancho no esquema (`origem`, `sujeito_externo`; contas externas respondem `409 login_externo` em senha e 2FA); `GET /api/login/provedores` ainda devolve lista vazia (LDAP não aparece ali — é rota própria, não SSO federado por IdP) | fora (L0-08-a/b, SAML/OIDC) | — | 2026-09-05 | pendente (D20) |
| AD-LDAP: bind, mapeamento de grupo, importação em massa | Portal Enterprise: Windows AD/LDAP como identity store; grupos do diretório mapeados por atributo, importação de membros | item L0-08-d-ldap: `POST /api/login/ldap` (`ldap3`, bind de serviço opcional → busca com filtro escapado, RFC 4515 → bind do usuário → `memberOf` mapeado para 1 dos 4 perfis por `provedor_ldap.mapa_grupo_perfil`, maior alcance quando mais de um bate) + provisionamento automático (nunca sobrescreve conta `origem='local'` homônima, `409 login_em_uso_local`) + `GET/PUT /api/org/ldap` (privilégio `org.integracoes`) + `POST /api/org/ldap/importar` (cria desabilitado, ativa no 1º login) — configurável por inquilino; senha de bind de serviço cifrada (AES-GCM sob `PLAT_SECRET`), senha do usuário do LDAP NUNCA gravada | feito | testador (14 casos em `tests/api/ldap/test_login_ldap.py`, contêiner glauth efêmero com 3 usuários sintéticos + 1 conta de serviço, `tests/ldap_fixture/`); adversário desta sessão (injeção de filtro, bind anônimo/senha vazia, 1.000 binds/min → bloqueio reaproveitando a política local, colisão com conta local, diretório fora do ar) | 2026-09-06 | pendente (D20; StartTLS e `sAMAccountName` de AD real não testados contra diretório real) |
| token de sessão `generateToken`: expiração, referer, IP, tetos | máx. 14 d, padrão 120 min; `maxTokenExpirationMinutes` | sessão por cookie (12 h ociosa, 7 d máximo; por inquilino 1-24 h e 1-30 d) + token de serviço com escopos, referer, IP e validade (90 d padrão, 365 máximo); 401 com motivo legível | feito | testador (inquilino com `sessao_max_dias = 1`) e adversário T2 (IP, escopo, revogado, `validade_acima_do_maximo`) | 2026-09-05 | pendente (D20) |
| chave de API de longa duração: ≤ 1 ano, referrers, invalidação | credencial de desenvolvedor, 2 chaves, ≤ 1 ano | token `plat_…` até 365 d, 20 por usuário, rotação com sobreposição de 24 h, revogação imediata (0,01 s até o 401), **com log de leitura (IP, rota, bytes)**, que a Esri não registra em REST | feito (acima da Esri no log) | testador (`testador_token_revogado_s` 0,02 s) e adversário T2 | 2026-09-05 | pendente (D20) |
| log de auditoria (login, membro, papel, grupo, compartilhamento, dono, item) | audit logs JSON + portal logs; consulta no Portal Admin | `log_acesso` (uma linha por requisição autenticada, inclusive por token) + `evento` (vocabulário espelhado nos gatilhos de webhook da Esri) + tela Log com filtros, CSV e aba Eventos; sem SIEM/webhook (L0-10, L7-08) | feito (tela; sem SIEM) | testador (30.876 linhas, 0 `ip`/`bytes` nulos, 0 token na rota) e adversário T2 | 2026-09-05 | pendente (D20) |
| relatórios de uso e relatório administrativo de membros | Activity Dashboard, CSV agendável | não existe | fora (L0-07-e) | — | 2026-09-05 | pendente (D20) |
| gestão de membros: adicionar, desabilitar, apagar com transferência, transferir membro | Members tab, Disable, Delete (transferir ou apagar conteúdo), Transfer member | criar, editar, desabilitar, reabilitar, redefinir senha, desligar 2FA, desbloquear, lote até 100 (mudar perfil/desabilitar/reabilitar); apagar sem transferência recusa nomeando o que falta resolver — grupos (`409 possui_grupos`) OU itens do catálogo (`409 possui_itens`, item L0-02-f, T3); transferência de conteúdo em massa é o L0-03-j (`POST /api/itens/transferir`, já `entregue`) | parcial (mecanismo completo e testado pela API e pela tela; falta só o botão único "transferir e apagar" num só fluxo — hoje são duas telas) | testador T2 (e2e `test_usuarios`, último admin = 409); testador T3 (e2e `test_usuarios_perfil_lote_2fa_desbloquear_apagar_com_grupos_e_401`: lote de perfil, 2FA, desbloqueio e 401 em 73,1 ms pela tela; api `test_apagar_com_2_itens_do_catalogo_recusa_listando_os_2`) | 2026-09-06 | pendente (D20) |
| perfil do membro: nome, foto, bio, visibilidade, idioma, unidades, página inicial | My profile / My settings | nome, e-mail, foto (recorte 200×200, sem EXIF), idioma preferido, unidades, formato de data e visibilidade (privado/inquilino) em Minha conta (`PUT /api/eu`, `POST/DELETE /api/eu/foto`); sem bio nem página inicial configurável; `idioma_preferido` grava mas a tela ainda não traduz por ele (L7-10-a); `unidades`/`formato_data` ainda não são lidos por nenhuma outra tela; `visibilidade_perfil` ainda não tem consumidor (não existe tela de "ver perfil de outro membro") | parcial (sem bio/página inicial; 3 dos 4 campos novos são preferência guardada sem consumidor ainda) | testador T3 (e2e `test_conta.py::test_perfil_nome_unidades_foto_na_barra_e_email_fora_do_dominio`, captura `L0-02-tenant-auth_perfil.png`; api `test_eu.py` — preferências válidas/inválidas, foto enviar/ler/remover, SVG recusado por não abrir no Pillow, >1 MiB recusado, escalada de acesso e domínio de e-mail do próprio inquilino continuam bloqueados) | 2026-09-06 | pendente (D20) |
| ao menos um administrador por organização; só admin muda papel de admin | regra literal | gatilho `usuario_ultimo_admin` + API (`409 ultimo_admin`, `403 so_admin_altera_admin`) + teste; superadmin só no inquilino técnico `plataforma`, por hash de sessão | feito | testador (inquilino temporário) e adversário T2 (`superadmin:true` = 422; `/api/plataforma` = 404) | 2026-09-05 | pendente (D20) |

## Privilégios e papéis personalizados (item L0-07-b-papeis-privilegios, turno 3; ADR 0002 seções 2.3, 3)

Paridade linha a linha contra a lista completa de privilégios da Esri (`laco/handoffs/T1/21_esri.md` §1.3,
fonte E12-priv, testada por HTTP em 05/09/2026) — os dois blocos "Privilégios GERAIS" e "Privilégios
ADMINISTRATIVOS" do doc, um privilégio Esri por linha. `docs/PRIVILEGIOS.md` é o vocabulário completo gerado do
banco; aqui é só o DE-PARA. Contagem: **43 gerais + 33 administrativos = 76 privilégios Esri**, um por marcador do doc; dos 47 nossos,
todos aparecem em pelo menos uma linha abaixo. Estado: **feito** (privilégio equivalente existe e a rota que o
usa está testada) · **parcial** (existe algo próximo, mais estreito ou mais largo) · **fora** (sem equivalente;
decisão consciente de escopo, não esquecimento).

### Privilégios gerais

| Esri (E12-priv) | nosso privilégio | estado | nota |
|---|---|---|---|
| Members: View | `membros.ver` | feito | |
| Members: Take ArcGIS Pro license offline | — | fora | sem licença/assento por membro (decisão da spec, D5/D16) |
| Groups: Create, update, and delete | `grupos.criar` | feito | |
| Groups: Join organizational groups | `grupos.entrar` | feito | |
| Groups: View groups shared with organization | `grupos.ver_inquilino` | feito | |
| Content: Create, update, and delete | `conteudo.criar` | feito | |
| Content: Publish hosted feature layers | `conteudo.publicar_camada` | feito | |
| Content: Publish hosted tile layers | `conteudo.publicar_tiles` | feito | |
| Content: Publish hosted scene layers | — | fora | sem camada de cena/3D (roadmap L2) |
| Content: Publish hosted dynamic imagery layers | `conteudo.publicar_raster` | parcial | publica raster; não distingue "dynamic imagery" nem exige extensão própria de análise |
| Content: Publish server-based layers | `conteudo.registrar_fonte` | parcial | registra fonte externa; não há um "ArcGIS Server" externo para publicar EM CIMA |
| Content: Publish hosted knowledge graphs | — | fora | sem grafo de conhecimento |
| Content: View content shared with organization | `conteudo.ver_inquilino` | feito | |
| Content: Register data stores | `conteudo.registrar_fonte` | feito | |
| Content: Create feature layers in bulk from a data store | — | fora | ingestão vetorial é item a item (L0-04); sem "em lote a partir de data store" |
| Content: View location tracks | — | fora | `campo.localizacao` é o PRÓPRIO usuário compartilhar a trilha, não ver a de terceiros |
| Content: Create and edit notebooks | — | fora | sem notebook (decisão de escopo) |
| Content: Schedule notebooks | — | fora | idem |
| Content: Reassign content | `conteudo.transferir` | feito | |
| Content: Receive content | `conteudo.transferir` | parcial | não há um privilégio separado para "receber"; quem transfere precisa poder editar a origem |
| Content: Create and run data pipelines | — | fora | `jobs.executar` é fila genérica, não pipeline ETL nomeado |
| Content: Publish livestream video | — | fora | sem vídeo |
| Content: Publish video | — | fora | sem vídeo |
| Content: Generate API keys | `tokens.gerar` | parcial | token de serviço com escopo cobre o uso; não é uma "API key" de app OAuth |
| Content: Assign privileges to OAuth 2.0 applications | — | fora | sem app OAuth registrável |
| Content: Create workflow item | — | fora | sem Workflow Manager |
| Sharing: Share with groups | `compartilhar.grupo` | feito | |
| Sharing: Share with portal | `compartilhar.inquilino` | feito | |
| Sharing: Share with public | `compartilhar.publico` | parcial | na Esri é geral (User+); na nossa spec é **administrativo** (só com `tenant.config.compartilhar_publico`, D24) — divergência deliberada, não lacuna |
| Sharing: Make groups visible to portal | `grupos.criar` | parcial | é campo do formulário do grupo (`visibilidade`), não um privilégio à parte |
| Sharing: Make groups visible to public | — | fora | grupo só tem visibilidade `membros`/`inquilino`, nunca `publico` |
| Content and Analysis: Geocoding | `analise.geocodificar` | feito | |
| Content and Analysis: Network Analysis | `analise.rotas` | feito | |
| Content and Analysis: Standard Feature Analysis | `analise.executar` | parcial | geoprocessamento sobre dado próprio existe; catálogo de ferramentas não replica o da Esri |
| Content and Analysis: GeoEnrichment | — | fora | sem enriquecimento demográfico |
| Content and Analysis: Imagery Analysis | `analise.raster` | feito | |
| Content and Analysis: Advanced notebooks | — | fora | |
| Content and Analysis: Run web tools | — | fora | sem geoprocessamento publicado como ferramenta web |
| Content and Analysis: Reality Mapping | — | fora | |
| Features: Edit | `feicoes.editar` | feito | |
| Features: Edit with full control | `feicoes.editar_total` | feito | |
| Version Management: Manage all | — | fora | sem versionamento de dado (branch versioning) |
| Webhooks: Feature layer | — | fora | webhook só existe amplo (`org.integracoes`), não por camada |

### Privilégios administrativos

| Esri (E12-priv) | nosso privilégio | estado | nota |
|---|---|---|---|
| Members: View all | `membros.ver_tudo` | feito | |
| Members: Update (inclui reset de senha e categorias de membro) | `membros.gerir` | feito | "categorias de membro" não existe (só categoria de CONTEÚDO, `conteudo.categorias`) |
| Members: Delete | `membros.apagar` | feito | |
| Members: Add | `membros.gerir` | feito | Esri separa Add de Update; nós usamos o mesmo privilégio para os dois |
| Members: Disable | `membros.gerir` | feito | idem |
| Members: Change roles | `membros.papel` | feito | |
| Members: Manage licenses | — | fora | sem licença/assento (mesma decisão da spec) |
| Members: Manage categories | — | fora | categoria de MEMBRO não existe (só de conteúdo) |
| Groups: View all | `grupos.gerir_todos` | parcial | não há um "ver todos" separado de "editar todos"; quem gere qualquer grupo também vê |
| Groups: Update | `grupos.gerir_todos` | feito | |
| Groups: Delete | `grupos.gerir_todos` | feito | |
| Groups: Reassign ownership | `grupos.gerir_todos` | feito | |
| Groups: Assign members | `grupos.gerir_todos` | feito | |
| Groups: Link to organization-specific group | — | fora | sem colaboração entre organizações (decisão, ver "Collaborations" abaixo) |
| Groups: Create with leaving disallowed | `grupos.administrativo` | feito | |
| Groups: Create with update capabilities | `grupos.atualizacao_compartilhada` | parcial | na Esri é administrativo por padrão; na nossa spec é liberado a partir do perfil `editor` — divergência deliberada |
| Content: View all | `conteudo.ver_tudo` | feito | |
| Content: Update (inclui editar dado de qualquer camada hospedada) | `conteudo.editar_tudo` + `feicoes.editar_total` | feito | a Esri junta metadado e dado num privilégio; nós separamos em dois nomes |
| Content: Delete | `conteudo.apagar_tudo` | feito | |
| Content: Reassign ownership | `conteudo.transferir` | feito | mesmo alvo de "Reassign content" na lista geral — o doc Esri nomeia a ação duas vezes, uma por categoria |
| Content: Manage categories | `conteudo.categorias` | feito | |
| Content: Publish web tools | — | fora | sem geoprocessamento publicável como ferramenta |
| Content: Share member content with organization | — | fora | não há "compartilhar em nome de outro membro"; só o dono do item ou quem tem `conteudo.editar_tudo` |
| Content: Share member content with public | — | fora | idem |
| Content: Create and manage administrative reports | — | fora | relatórios de uso ainda não existem (item L0-07-e) |
| Webhooks: Geoprocessing | — | fora | |
| Portal settings: Security and infrastructure | `org.configurar` | parcial | política de senha/2FA/domínio de e-mail sim; certificado/infraestrutura de rede não |
| Portal settings: Organization website | `org.configurar` | parcial | logotipo sim (item L0-07-a); branding/website completo não |
| Portal settings: Collaborations | — | fora | sem colaboração entre organizações (decisão de escopo) |
| Portal settings: Member roles | `papeis.gerir` | feito | |
| Portal settings: Servers | — | fora | sem registro de ArcGIS Server externo (pilha é própria) |
| Portal settings: Utility services | — | fora | sem geocoding/rotas de terceiro configurável como serviço utilitário |
| Portal settings: Organization webhooks | `org.integracoes` | feito | |

**Contagem**: 17 feito · 7 parcial · 19 fora (gerais, 43 linhas) + 18 feito · 4 parcial · 11 fora
(administrativos, 33 linhas) = **35 feito · 11 parcial · 30 fora de 76** (46,1% / 14,5% / 39,5%; contagem
linha a linha, `grep -c` na tabela acima antes de publicar, sem arredondar). Nenhuma linha `fora` é lacuna
acidental: cada uma é notebook, app OAuth, pipeline, versionamento de dado, colaboração entre organizações,
licença/assento, vídeo, grafo de conhecimento ou relatório de uso — todas já nomeadas como decisão de escopo em
outro item do backlog (D5/D16, L0-07-e, ou "roadmap L2/L5") antes desta conferência, nunca descobertas por ela.

### Regras testadas (refutação do item)

| regra | evidência |
|---|---|
| papel com privilégio administrativo só cabe em `perfil_minimo = admin` | `tests/api/test_usuarios.py::test_so_admin_cria_altera_e_apaga_admin` (papel com `membros.gerir` etc. calcula `perfil_minimo = admin`; atribuí-lo a um usuário `editor` é `422 papel_incompativel`) |
| ninguém concede a si mesmo privilégio que não tem | `tests/api/test_usuarios.py::test_privilegios_e_papeis` (admin restrito a `{membros.ver, papeis.gerir}` tenta criar papel com `org.log_ver` → `403 privilegio_proprio_insuficiente`) |
| apagar papel em uso é recusado | mesmo teste (`409 papel_em_uso`, com a contagem de usuários no `detalhe`) |
| rebaixar perfil de quem possui conteúdo é recusado | `tests/api/test_usuarios.py::test_rebaixar_perfil_com_itens_e_recusado` (novo nesta sessão — a rota só checava grupos; achado do adversário) |
| toda rota do OpenAPI vivo com privilégio "puro" nega 403 a quem não o tem | `tests/api/test_privilegios_matriz.py` (168 operações vivas; ~40 com privilégio de vocabulário fechado, todas testadas; exceção nomeada e testada à parte é `PUT /api/itens/{id}/compartilhamento`, cujo gate real é ownership-antes-de-privilégio) |
| `docs/PRIVILEGIOS.md` é gerado, nunca escrito à mão | `tests/api/test_privilegios_doc.py` + `docs/gerar_privilegios.py --check` |

## Fila de trabalhos (item L0-05-jobs, turno 2; ADR 0003)

A referência Esri aqui é o serviço de geoprocessamento assíncrono (job de GP: `submitJob`, `jobStatus`,
`cancel`, mensagens) e as tarefas agendadas do portal, conforme o ADR 0003 (D12). O papel `esri` não escreveu
handoff próprio para este item; a coluna "Esri" abaixo vem do ADR. O adversário do L0-05 não rodou neste turno;
"testado por" é só o testador, e o item foi devolvido a `pendente` com uma cláusula nova aberta (achado 2).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| estados do job (Submitted/Waiting, Executing, Succeeded, Failed, TimedOut, Cancelling, Cancelled) | vocabulário `esriJob*` do `jobStatus` | `pendente`, `rodando`, `concluido`, `falhou` (com `erro` "tempo esgotado" para o TimedOut), `cancelado`, `cancelar_solicitado`; tradução para `esriJob*` reservada ao `/svc/` do L2-04 | feito (vocabulário próprio; endpoint Esri-compatível fora, L2-04) | testador T2 | 2026-09-05 | pendente (D20) |
| submeter job e consultar estado e progresso | `submitJob` + `jobStatus` por consulta periódica | `POST /api/jobs` + `GET /api/jobs/{id}` + SSE `GET /api/jobs/{id}/eventos` (progresso 0-100 e mensagem em tempo real; primeiro evento em 0,022 s pela URL pública) | feito (acima: progresso empurrado, não consultado) | testador T2 (job de 5 min, 62 eventos, heartbeat ≤ 5 s) | 2026-09-05 | pendente (D20) |
| cancelar job | `cancel` no job de GP | `POST /api/jobs/{id}/cancelar`: pendente → cancelado; rodando → cooperativo em 0,426 s; tarefa que ignora → SIGTERM 30 s + SIGKILL 10 s | feito | testador T2 | 2026-09-05 | pendente (D20) |
| mensagens do job (informative, warning, error) | `messages` do `jobStatus` | `job_log` por job com níveis DEBUG/INFO/AVISO/ERRO, ao vivo pelo SSE, `baixar log` até 2.000 linhas, teto 10.000 por job | feito | testador T2 | 2026-09-05 | pendente (D20) |
| sobrevivência a reinício do servidor | não documentado como garantia | devolução e retomada do zero com `reinicios + 1` (1,0 s), ceifa por heartbeat vencido, teto de 5 reinícios → `falhou`; nunca `concluido` sem execução inteira (marcador) | feito para a unidade; **parcial** pela cláusula nova: worker homônimo fora do systemd devolve os jobs do worker vivo (correção 012/013 comitada em `9be9c6a`, sem veredito do testador e do adversário) | testador T2 (restart, `kill -9`, 5 × `kill -9`; achado 2) | 2026-09-05 | pendente (D20) |
| limite de recursos por job | limites de instância do serviço | `memoria_mb` por tipo aplicado por `RLIMIT_DATA` no filho; `timeout_s`; `MemoryMax=2G` na unidade; "1 pesado por vez" | feito | testador T2 (`prova.memoria(600)` com limite 256 → `falhou`, worker vivo) | 2026-09-05 | pendente (D20) |
| separação entre quem executa e quem muda estado | não se aplica (serviço fechado) | role `plat_worker` exclusiva para transições; `plat_app` sem `UPDATE` em `job`; gatilho `job_transicao` | feito (correção 006) | testador T2 (ataque repetido = `permission denied`) | 2026-09-05 | pendente (D20) |
| isolamento por organização na fila | jobs por usuário/serviço | RLS em `job`, `job_log`, `agenda`; 15 rotas por id com sessão de outro inquilino = 404; listas sem vazamento | feito | testador T2 | 2026-09-05 | pendente (D20) |
| tarefas agendadas (cron) | scheduled tasks do portal (notebook/workflow), limite por organização | `plat.agenda` por inquilino: cron de 5 campos + fuso IANA, intervalo mínimo 15 min, 50 por inquilino, pausar/retomar/rodar agora, 5 falhas pausam; relógio no worker | feito | testador T2 (`test_jobs_agenda.py`, `test_cron.py`, e2e agendas) | 2026-09-05 | pendente (D20) |
| tela de acompanhamento por organização | histórico de jobs no serviço de GP; sem tela de usuário final equivalente no Portal | tela Tarefas: lista ao vivo, filtros, detalhe com log, cancelar, repetir, CSV, agendas; administrador vê tudo, os demais só os próprios | feito | testador T2 (e2e 4 de 5: a prova com 1.000 jobs semeados falhou por semeadura do próprio teste, não do produto) | 2026-09-05 | pendente (D20) |
| job remoto em GPU / executor externo | GeoAnalytics/Notebook Server | só a coluna `executor`, o CHECK e a recusa na importação sem `PLAT_GPU_SSH` | fora (L1-05) | — | 2026-09-05 | pendente (D20) |
| cotas por organização | créditos e limites de serviço | `cota_jobs_simultaneos` (2), `cota_jobs_dia` (1.000, 413), `cota_agendas` (50, 413), > 200 pendentes = 429; com 1 processo a cota de simultâneos não tem efeito | parcial (serial com 1 processo) | testador T2 | 2026-09-05 | pendente (D20) |

## Acervo da casa (item L6-01-a-procedencia-acervo)

Referência Esri: Living Atlas em ArcGIS Enterprise 11.4 "referencia" conteúdo do ArcGIS Online quando há
internet e publica camadas de limites diretamente no portal quando não há (`what-is-living-atlas.htm`, 11.4);
"users are responsible for adhering to the terms of use for each item" (Business Analyst,
`understand-arcgis-living-atlas.htm`). Este item cobre só a FICHA de procedência por fonte (metadado: licença,
frescor, sha256, comando de reexecução, nº de tabelas, registros) e o "adicionar ao catálogo" que referencia a
fonte sem copiar dado; a tela de navegação (L6-01-c), a view por CAMADA de dado com RLS por assinatura
(L6-01-b) é item à parte, ainda pendente; a licença curada em vocabulário fechado (L6-01-g) tem linha própria
abaixo (parcial, 29/40).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| ficha de procedência por fonte/camada do catálogo curado | "terms of use" por item; metadado de item (licença, créditos, data) | `plat.acervo_ficha` (migração 021) + `plat.acervo_endpoint` (migração 040, item L6-01-d-ficha-fonte): view `SECURITY INVOKER` sobre `acervo.fonte`/`acervo.v_completude`/`acervo.endpoint` (376 fontes medidas; nunca escrita pela plataforma), licença, frescor, sha256, comando de reexecução, nº de tabelas e registros (estimativa, `acervo.fonte.linhas_est`), endpoints confirmados e vivos, completude "x/10" por extenso; `GET /api/acervo` (lista por domínio e busca) e `GET /api/acervo/{fonte_id}` (ficha completa); regra D17 — só fonte com `licenca IS NOT NULL` aparece (68 de 376 medido em 06/09/2026), nunca GRANT à role PUBLIC | parcial (mecanismo completo, os 10 campos + endpoints + completude conferidos campo a campo para 20 fontes; sem tela — L6-01-c; licença ainda é o texto livre de `acervo.fonte`, não o vocabulário fechado do L6-01-g) | arquiteto/backend nesta sessão (14 testes em `tests/api/test_acervo.py`, incluindo os 20-fontes e campo-ausente-nunca-fabricado); **sem adversário independente do turno** | 2026-09-06 | pendente (D20) |
| "adicionar" ao conteúdo próprio sem copiar dado | Add Item by URL / referenced content | `POST /api/acervo/{fonte_id}/adicionar` cria item `plat.item` tipo `conexao` (protocolo `acervo`, `dados.parametros.fonte_id`); 404 se a fonte não tem licença escrita (mesma resposta de "não existe", regra D17); fonte marcada `risco_pii` em `plat.acervo_lgpd` (migração 041, item L6-01-f-lgpd — curadoria manual, 1 de 68 fontes licenciadas: `onr`, matrículas) recusa com 409 `confirmacao_pii_exigida` sem `{"confirma_risco_pii": true}` no corpo, evento `acervo/adicionar_recusado_pii` registrado mesmo na recusa; RLS de `plat.item` garante que só o inquilino que chamou vê o item criado | parcial (cria a referência; não resolve tiles/FeatureServer a partir dela — isso é o L6-01-b; gate de LGPD cobre só o fluxo de "adicionar fonte", não a classificação por coluna em toda view exposta) | arquiteto/backend nesta sessão (teste cruzado A→B: dono lê, outro inquilino recebe 404; gate de LGPD com e sem confirmação); **sem adversário independente do turno** | 2026-09-06 | pendente (D20) |
| licença curada em vocabulário fechado, testada por HTTP (item L6-01-g-licenca-curada) | "terms of use" por item é texto livre digitado por quem publica, nunca reverificado pela plataforma | `plat.acervo_licenca` (migração 043): CHECK de vocabulário fechado (CC0, CC-BY, CC-BY-SA, ODbL, dado-aberto-com-termo-do-orgao, Copernicus, licenca-propria, nao-declarada); `scripts/acervo_licenca_sync.py` só grava depois de um GET/chamada de API real que ENCONTRA o termo (evidência = recorte literal da resposta, nunca escrito à mão); regra D17 — nenhuma linha para fonte sem termo escrito na origem | parcial (29/40 fontes com geometria + licença confirmada; as 11 que faltam ficam sem organização com portal CKAN/DCAT vivo ou com licença específica de dado — ver `decisoes_do_dono` D39; mecanismo ponta a ponta funciona e é reexecutável) | eu mesmo nos três papéis do item (pesquisador/dados/adversário), T3: script rodado ao vivo (29/29 OK), suíte `tests/api/test_acervo_licenca.py` (idempotência, estrutura, vocabulário, reexecução literal dos GETs), amostra adversária de 10/29 reconfirmada por `curl` independente | 2026-09-06 | pendente (D20) |

## Arquivos/objetos por inquilino (item L0-11-arquivos-objetos; ADR 0006)

Referência Esri: portal de ArcGIS Enterprise usa um "object store" (S3-compatível ou Azure Blob) para hospedar
itens grandes; o isolamento por organização é interno ao portal, sem bucket/chave expostos ao administrador.

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| isolamento físico de armazenamento por organização | interno ao portal, não exposto ao admin | 1 bucket + 2 chaves de acesso (RW/RO) por inquilino no Garage (`plat.arquivo_bucket`), criados sob demanda; MEDIDO contra o Garage real desta máquina: chave RO tentando escrever = 403; chave de um bucket lendo outro = 403 (o próprio Garage recusa, não uma checagem nossa) | feito (mais granular que o portal Esri, que não expõe isolamento físico por organização) | arquiteto/backend nesta sessão (13 testes próprios: `tests/api/test_arquivos.py`); teste cruzado A→B gerado do OpenAPI (5 rotas, `tests/api/cruzado_casos.py`); **sem adversário independente do turno** | 2026-09-06 | pendente (D20) |
| cota de armazenamento por organização | armazenamento em créditos/GB por organização | cota do bucket = `tenant.cota_bytes`, sincronizada a cada uso; recusa com mensagem clara (413) antes do Garage, que também recusaria (403 nativo) | feito | idem acima (`test_cota_estourada_recusa_com_mensagem`) | 2026-09-06 | pendente (D20) |
| nome de objeto por conteúdo (nunca sobrescreve) | não documentado como garantia | chave = sha256 do conteúdo; `HEAD` antes de `PUT`; sha256 recalculado sobre o conteúdo lido bate com o devolvido no envio | feito | idem acima (`test_salvar_ler_apagar_e_sha256_recalculado`, `test_upload_nao_sobrescreve_...`) | 2026-09-06 | pendente (D20) |
| upload grande / multipart | multipart upload em itens grandes | streaming com teto (`limites.ARQUIVO_BYTES_MAX`), multipart real no Garage acima de `ARQUIVO_BUFFER_UNICO_BYTES` (objeto temporário + cópia para a chave final por conteúdo); RAM do processo nunca passa de 1 parte, mesmo no teto | feito | idem acima (`test_multipart_real_produz_o_mesmo_sha256_que_um_put_unico`) | 2026-09-06 | pendente (D20) |
| entrega de objeto só pela API (nunca URL direta do armazenamento) | portal nunca expõe URL do object store ao navegador | `GET /api/arquivos/{sha256}` e `GET /api/objetos/{chave}` (catálogo) sempre passam pelo processo da API; chave de acesso ao Garage nunca sai do backend | feito (o custo é CPU da API proxiando bytes; sem X-Accel-Redirect ainda — pendência nomeada no ADR 0006 seção 10) | idem acima | 2026-09-06 | pendente (D20) |
| varredura de integridade (objeto órfão / metadado órfão) | não documentado como garantia | `varrer_orfaos` compara o bucket real (`ListObjectsV2`) com `plat.arquivo`; acusa objeto plantado sem linha | feito | idem acima (`test_varredura_acusa_orfao_plantado`) | 2026-09-06 | pendente (D20) |
| `/saude` aponta serviço de armazenamento obrigatório | não se aplica | **pendente**: `app/saude.py` ainda trata `garage` como informativo (não muda o HTTP 200/503); registrado como pendência explícita no ADR 0006 seção 9, não construído neste turno | parcial | — | 2026-09-06 | pendente (D20) |

## Metadado ISO e catálogo externo (item L0-09-metadado-catalogo; D17 do L0_CONCEITO)

Referência Esri: Portal for ArcGIS suporta **seis estilos de metadado** — FGDC CSDGM, INSPIRE Metadata
Directive, ISO 19139 Metadata Implementation Specification (com e sem GML 3.2), North America Profile of
ISO 19115:2003 e **ISO 19115-3 XML Schema Implementation** — um estilo por vez, escolhido pelo administrador
da organização; o download por item sai em "ArcGIS metadata format" (XML) pelo editor de metadado
(`enterprise.arcgis.com/en/portal/11.2/use/metadata.htm`, testado por HTTP 06/09/2026). O servidor de catálogo
CSW (harvest OGC) **não é do Portal base**: é capacidade do produto separado ArcGIS for INSPIRE/Geoportal Server
(`enterprise.arcgis.com/en/inspire/10.5/get-started/components-of-the-geoportal.htm`) — o Portal sozinho não
expõe CSW para descoberta externa.

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| exportação de metadado ISO por item | 6 estilos configuráveis pelo administrador (1 por vez), download XML pelo editor do item | `GET /api/itens/{id}/metadado.xml`: gera ISO 19139/GMD (o estilo que o Perfil MGB 2.0/INDE consome) a partir de `plat.item` + `dados.procedencia` (D17); validado contra o XSD oficial (`schemas.opengis.net/iso/19139/20070417`, cacheado OFFLINE em `docs/xsd/cache/` por `docs/xsd/baixar_iso19139.py`, 57 arquivos/796 KB, nunca em tempo de requisição) | feito para ISO 19139; **ISO 19115-3 fica de fora** (o Perfil MGB/INDE consome 19139; adicionar o segundo formato é 1 gerador a mais, mesmo XSD de validação diferente) | arquiteto/backend nesta sessão (9 testes próprios verdes, `tests/api/catalogo/test_metadado_ogc.py`: item completo, item mínimo só com obrigatórios, 404 item inexistente/de outro inquilino, token `catalogo:ler`); **sem adversário independente do turno** | 2026-09-06 | pendente (D20) |
| catálogo externo por protocolo padrão (descoberta) | Portal não expõe CSW; produto separado (Geoportal/INSPIRE) faz harvest CSW | **OGC API Records** (OGC 20-004r1) em `/ogc/records`: pouso, `/conformance`, coleção única `catalogo`, `/items` (GeoJSON, filtro `q`/`bbox`/`tipo`/`tags`, paginação cursor) e `/items/{id}`; sempre autenticado (`catalogo:ler`, sessão ou token de serviço do L0-02) — nunca aberto; isolamento por inquilino vem da RLS de `plat.item` (mesmo mecanismo de `GET /api/itens`), não de filtro escrito na rota | parcial (OGC API Records feito; **CSW fica de fora** desta passagem — justificativa em `app/catalogo/rotas_ogc.py`: RAM no limite, nenhuma biblioteca CSW instalada, protocolo legado; custo de mudar = médio, um roteador novo reaproveitando `listar_ids`/`carregar_varios`) | arquiteto/backend nesta sessão (9 testes próprios verdes, incluindo a refutação do item: token/sessão de um inquilino nunca lê registro nem `items/{id}` de outro); **sem adversário independente do turno** | 2026-09-06 | pendente (D20) |
| varredura cruzada A→B automática (gerada do OpenAPI) | não se aplica | **pendente**: as duas rotas novas ainda não estão em `docs/openapi.json`/`tests/api/cruzado_casos.py` — o turno tinha outras trilhas regravando esses dois arquivos ao vivo (concorrência real, não hipotética); registrado aqui para a integração final do turno somar as novas rotas de uma vez, evitando capturar estado parcial de outra trilha num `make openapi` fora de hora. A isolação por inquilino já está PROVADA pelos testes próprios acima; falta só o item na varredura genérica. | parcial | — | 2026-09-06 | pendente (D20) |

## Documento de construtor (item L5-05-documento-versoes; ADR 0011)

Referência Esri: Experience Builder liga widgets por id de widget e vista de dado (doc "Add actions to
widgets"); QuickCapture usa `dataSourceId` próprio, não índice do serviço (doc "Project JSON"); os dois nunca
reindexam por posição. StoryMaps/Dashboards guardam rascunho e publicado separados (doc "Publish, revise, and
share"). Puck (biblioteca de builder React) documenta migração de dado entre versões de esquema com quebra
("Data Migration").

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| id estável por nó, nunca por posição | id de widget/vista de dado (Experience Builder); `dataSourceId` (QuickCapture) | ULID por nó (`corpo.nos[].id`), gerado uma vez, nunca recalculado; referência entre nós só por id (`corpo.ligacoes`) | feito | esta sessão (`test_ulid_de_no_nunca_se_repete_entre_versoes`: 5 edições, nenhum id repetido em nenhuma versão) | 2026-09-06 | pendente (D20) |
| rascunho × publicado sempre distintos | StoryMaps/Dashboards: draft e published separados | `plat.item_versao` (imutável) + `plat.item.versao_publicada`; editar não move o ponteiro, só `publicar` move | feito (mecanismo genérico de L0-03, reaproveitado sem mudança) | esta sessão (`test_rascunho_nao_muda_publicado_ate_publicar_explicitamente`) | 2026-09-06 | pendente (D20) |
| migração de esquema entre versões | Puck: "Data Migration" documentado; Experience Builder migra app antigo ao abrir | `migrar_<tipo>_v<N>_v<N+1>` aplicada na LEITURA (nunca no navegador, nunca grava de volta), evento `itens/esquema_migrado` | feito | esta sessão (`test_migracao_de_esquema_na_leitura_com_evento`) | 2026-09-06 | pendente (D20) |
| esquema/contrato do documento consultável por ferramenta externa | não documentado como API pública separada | `GET /api/esquemas`, `GET /api/esquemas/{tipo}?versao=N` — o mesmo JSON Schema que valida `dados` | feito | esta sessão (cadastrado em `tests/api/cruzado_casos.py` como vocabulário) | 2026-09-06 | pendente (D20) |
| verificação de integridade de versão contra adulteração direta no banco | não se aplica (SaaS, sem acesso direto ao banco pelo cliente) | `GET /api/itens/{id}/integridade`: recomputa sha256 de cada versão a partir do `corpo` gravado e compara | feito (acima da Esri: cenário só existe porque a pilha é auto-hospedada) | esta sessão (`test_integridade_acusa_linha_de_versao_editada_direto_no_banco`, tampering via `sudo -u postgres psql`) | 2026-09-06 | pendente (D20) |
| widgets de construtor (paginas, ações configuráveis, editor de arrasto) | Experience Builder completo | fora — este item é só o documento; construtores em si são L5-01/06/07/08/09 | fora (L5-01, L5-06 a L5-09) | — | 2026-09-06 | pendente (D20) |

## Registro de camadas do acervo (item L6-01-a-registro; ADR 0012)

Referência Esri: Living Atlas em ArcGIS Enterprise 11.4 cataloga conteúdo "reliable source" com metadado por
item (`understand-arcgis-living-atlas.htm`, 11.4) — o equivalente aqui é o REGISTRO por trás da ficha (item
L6-01-a-procedencia-acervo, já entregue): uma linha por tabela canônica com geometria, nunca por fonte.

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| registro de camada candidata (schema.tabela, SRID, tipo de geometria, coluna) | metadado de item por camada no Living Atlas | `plat.acervo_camada` (migração 030 — renumerada de 028 por colisão com trilha concorrente; `scripts/acervo_sync.py`), uma linha por tabela canônica com geometria (462 candidatas medidas 06/09/2026, 270 em `public`) | feito | arquiteto/backend nesta sessão (6 testes; ver `tests/api/test_acervo_camada.py`) | 2026-09-06 | pendente (D20) |
| contagem exata, nunca estimativa | não documentado (Esri não expõe a fonte da contagem) | `COUNT(*)` com timeout de 25 s (mesmo padrão de `contagem2.py` da casa); timeout vira `linhas_exatas = NULL`, nunca 0 | feito | `test_coluna_de_contagem_nao_e_reltuples`, `test_contagem_nao_concluida_nunca_vira_zero` | 2026-09-06 | pendente (D20) |
| tabela fantasma nunca exposta | não se aplica | regra DINÂMICA (estimativa > 0 e COUNT exato = 0) → `bloqueada`, nunca por lista de nomes | feito | `test_nenhuma_tabela_fantasma_fica_exposta` (cobre as 2 fantasmas conhecidas do registro sem citar seus nomes em código) | 2026-09-06 | pendente (D20) |
| lista branca de colunas expostas | curadoria humana de item (Living Atlas) | negação por NOME exato contra lista pequena de identificador de pessoa (coarse; reforço por CONTEÚDO é L6-01-f, não construído) | parcial (rede mínima de segurança, não a checagem fina prometida no item-pai) | inspeção manual desta sessão; sem teste automatizado de conteúdo (é o item L6-01-f) | 2026-09-06 | pendente (D20) |
| execução em ≤ 5 min, idempotente | Data Pipelines: intervalo mínimo de 15 min entre tarefas (`schedule-data-pipeline-tasks.htm`, 11.4) | 274,9s e 286,0s medidos (2 rodadas completas, máquina disputada por outro job pesado da casa); ordem por "há mais tempo sem sincronizar" garante progresso entre rodadas | feito | `test_script_existe_e_e_idempotente_e_rapido`; rodada completa em `test_execucao_completa_registra_estatisticas` (marcado `lento`) | 2026-09-06 | pendente (D20) |

## Modelo de conexão externa e defesa de SSRF (item L6-02-a-modelo-conexao-e-seguranca; ADR 0012)

Referência Esri: Map Viewer 11.4 lista os tipos de camada que se adicionam por URL — "ArcGIS Server web
service, OGC WFS, OGC WMS, OGC WMTS, OGC API Features, KML, GeoRSS, GeoJSON, CSV, tile layers"
(`add-layers-mv.htm`, 11.4, testada por HTTP em 05/09/2026 no L3L6_CONCEITO.md); o Portal guarda credencial
de serviço ao adicionar item, "store credentials with service item" (`add-items.htm`, 11.4). Esta trilha
entrega só o MODELO + a segurança; os 15 conectores concretos são itens futuros (L6-02-b em diante).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| objeto de conexão com tipo fechado, config e credencial cifrada | "store credentials with service item" (Portal) | `plat.conexao` (migração 030; tenant_id+RLS): tipo em vocabulário fechado (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/PMTiles/postgres_fdw/s3/http), `config` JSONB, `credencial_cifrada` (AES-GCM, `app/conexao/credencial.py`, nunca `pgp_sym_encrypt`) | feito (modelo; conectores concretos são itens futuros) | `tests/api/test_conexoes.py` (13 testes: CRUD, RLS cruzada, unicidade de nome, tamanho de config) | 2026-09-06 | pendente (D20) |
| defesa de SSRF (IP privado/loopback/link-local, `file://`, redirecionamento interno, DNS rebinding, userinfo) | não se aplica (Esri não expõe validador próprio documentado) | `app/conexao/seguranca.py`: resolve com timeout, recusa IP privado/loopback/link-local/CGNAT/reservado/multicast, só http/https, revalida CADA redirecionamento do zero, conecta pinado no IP já validado (nunca resolve de novo) | feito | `tests/unit/test_conexao_seguranca.py` (25 testes: os 8 casos do portão, incluindo redirecionamento de host público real para `169.254.169.254` e prova de que a conexão pinada não resolve o hostname de novo) | 2026-09-06 | pendente (D20) |
| teste de saúde da conexão | não documentado como endpoint público separado | `POST /api/conexoes/{id}/testar`: `buscar_seguro` com timeout curto (conectar 3s/ler 6s), grava `saude`/`saude_mensagem`/`saude_latencia_ms`/`saude_verificada_em`; credencial decifrada só em memória, nunca na resposta | feito | `test_testar_conexao_publica_atualiza_saude` (contra IBGE, dado aberto real) | 2026-09-06 | pendente (D20) |
| credencial nunca sai na resposta nem no log | Portal não expõe a credencial de volta pela API | nenhuma rota faz `SELECT credencial_cifrada` para responder; `_json()` nunca inclui a coluna; testado com `caplog` | feito | `test_credencial_nunca_aparece_na_resposta_nem_no_log` | 2026-09-06 | pendente (D20) |
| 15 conectores concretos (WMS, WFS, WMTS, OGC API, ArcGIS REST, STAC, GeoParquet, PMTiles, bancos externos) | cada um documentado por protocolo (Map Viewer, GeoServer cascade, Data Pipelines) | fora — itens futuros L6-02-b em diante, cada um valida `config` por JSON Schema próprio | fora | — | 2026-09-06 | pendente (D20) |

## Ingestão vetorial (item L0-04-ingest-vetor, núcleo T3; ADR 0005) — reduzido a 4 formatos nesta passagem

Referência Esri: "Publish hosted feature layers" e "CSV, TXT, and GPX files" (Enterprise 11.4, citadas pelo
ADR 0005 seção 16). Esta passagem entrega o NÚCLEO do item pai (upload → inspeção → confirmação → carga →
camada no catálogo) para 4 formatos: shapefile zipado, GeoPackage, GeoJSON, CSV/TXT (lat/lon). KML/KMZ, GPX,
XLSX, DXF/DWG, FileGDB, FlatGeobuf, GML, MapInfo, GeoParquet, atualizar dados, exportação, vista de camada e
fonte registrada continuam no ADR (seções 10-15) e ficam para os itens L0-04-d completo / L0-04-e / L0-04-f /
L0-04-g / L0-04-h / L0-04-i / L0-04-j (ver `laco/handoffs/T3/L0-04-ingest-vetor.md`).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| publicar shapefile (zip) como camada hospedada | "Publish hosted feature layers" (zip com .shp/.shx/.dbf) | `POST /api/importacoes {arquivo_id, formato:"shapefile.zip"}` → `ogrinfo` via `/vsizip/` → `ogr2ogr -f PostgreSQL` com `PROMOTE_TO_MULTI`; `.prj`/`.cpg` lidos do zip, campo truncado a 10 na origem tolerado (`PRECISION=NO`) | feito | `tests/api/ingestao/test_ingestao.py::test_shapefile_zip_importa` (dado aberto: cobertura do solo OSM de Guarulhos, 80 feições) | 2026-09-06 | pendente (D20) |
| publicar GeoPackage | idem | GPKG lido direto (driver GPKG do GDAL), CRS de `gpkg_spatial_ref_sys` | feito | `test_gpkg_importa_e_publica_no_catalogo` (RLS FORCE conferida na tabela criada) | 2026-09-06 | pendente (D20) |
| publicar GeoJSON | idem | GeoJSON direto; `crs` legado (fora da RFC 7946) respeitado com aviso | feito | `test_geojson_importa` | 2026-09-06 | pendente (D20) |
| publicar CSV/TXT com lat/lon | "CSV, TXT, and GPX files" (11.4) | normalizador próprio (`app/ingestao/csv_normalizar.py`, ADR 0005 seção 11): separador `,`/`;`/tab, vírgula decimal → ponto, BOM, coluna de coordenada por nome; GDAL só recebe CSV canônico | feito | `test_csv_lat_lon_virgula_decimal_importa` (valor decimal gravado conferido byte a byte contra o CSV de origem) | 2026-09-06 | pendente (D20) |
| CRS ausente/errado nunca é assumido | a Esri assume WGS84 em CSV/shapefile sem `.prj` (comportamento não documentado, achado do ADR seção 0.3: SRID 0 em silêncio no shapefile) | proposta marca `crs.perguntar=true` com sugestão pelo extent (4674 dentro do Brasil); `confirmar` sem responder devolve `422 perguntas_pendentes`; carga usa `-a_srs` explícito, nunca `-t_srs` (nunca reprojeta) | feito | `test_shapefile_sem_prj_pergunta_crs_e_importa_apos_confirmar`, `test_crs_confirmado_pelo_usuario_nunca_e_reprojetado` | 2026-09-06 | pendente (D20) |
| geometria inválida corrigida com relatório | não documentado (a Esri publica e deixa a validação para quem consome) | amostra de validade via shapely (sem depender de dialeto SQLite do GDAL); carga roda `ST_MakeValid` (ordem: validar primeiro, `ST_ReducePrecision` depois — MEDIDO que a ordem inversa quebra em geometria real com buraco tocando o contorno) e conta corrigidas/descartadas/fids no relatório | feito | `test_geojson_poligono_autointersectado_e_corrigido_com_relatorio` (gravata: 1 de 3 corrigida) | 2026-09-06 | pendente (D20) |
| tabela de camada com RLS FORCE, colunas obrigatórias, índice espacial | camada hospedada = uma tabela por trás, sem RLS documentada (Esri usa o modelo de item, não SQL) | `plat.camada_preparar()` (SECURITY DEFINER): `globalid`/`versao`/`tenant_id`/auditoria, `UNIQUE(globalid)`, sequência de `fid` até 2³¹-1, GIST em `geom`, `ENABLE`+`FORCE ROW LEVEL SECURITY`, gatilhos `tg_tenant`/`tg_versao` | feito | `test_gpkg_importa_e_publica_no_catalogo` (`relrowsecurity AND relforcerowsecurity`), `test_dois_inquilinos_nao_veem_camada_um_do_outro` (RLS cruzada) | 2026-09-06 | pendente (D20) |
| conteúdo declarado × bytes reais | Esri não documenta verificação de conteúdo no upload | `app/ingestao/formatos.py::verificar_conteudo` (zip com trio .shp real, cabeçalho SQLite do gpkg, `{`+`"type"` do geojson) — `422 conteudo_nao_corresponde` antes de qualquer job | feito | `test_conteudo_nao_corresponde_ao_tipo_declarado` | 2026-09-06 | pendente (D20) |
| zip-bomba e caminho malicioso no upload | não documentado | `formatos.conferir_zip`: entradas ≤ 1.000, descomprimido ≤ 8 GiB, razão ≤ 100×, sem `..`/`\`/link simbólico/zip aninhado — ANTES de extrair | feito | `tests/unit` (a suíte de ataque completa do L0-04-a fica para aquele item; aqui só o caminho feliz é exercido) | 2026-09-06 | parcial (fuzzing completo é do L0-04-a) |
| cota do inquilino aplicada antes da carga | a Esri cobra por crédito, sem teto rígido de bytes por item | `tenant.uso_bytes`/`uso_reservado_bytes` (migração 029); estimativa = bytes do arquivo × 3 reservada com `FOR UPDATE` antes do `ogr2ogr`; excedida = `FalhaDefinitiva` sem criar tabela | feito | `test_cota_excedida_nao_cria_tabela` | 2026-09-06 | pendente (D20) |
| duas importações do mesmo arquivo em paralelo | não se aplica (a Esri publica um item por vez pela tela) | a chave do job é por `importacao_id` (nunca por `arquivo_id`): duas importações do mesmo arquivo rodam em paralelo, cada uma com seu `item_id`/tabela — nunca corrompem uma à outra | feito | `test_importar_o_mesmo_arquivo_duas_vezes_em_paralelo_nao_falha` | 2026-09-06 | pendente (D20) |
| invariante tabela↔item (nunca órfã) | não se aplica | falha em qualquer passo da carga faz `DROP TABLE` + `DELETE` do item na mesma exceção (`_limpar_orfao`); destruidor de `camada_vetorial` (`app/catalogo/destruidores.py`, já preparado desde antes desta trilha) apaga a tabela física quando o item é expurgado pela lixeira | feito | conferido manualmente (consulta `pg_tables` × `plat.item` sem linha órfã após a suíte); teste automatizado de morte do worker no meio (SIGKILL) fica para o L0-04-c completo | 2026-09-06 | parcial (teste de morte pendente) |
| KML/KMZ, GPX, XLSX, DXF/DWG, FileGDB, FlatGeobuf, GML, MapInfo, GeoParquet | todos suportados pela Esri (`add-layers-mv.htm`, `csv-gpx.htm`) | fora — ADR 0005 seções 10-12 já desenham cada um; ver handoff do item para o que falta por formato | fora | — | 2026-09-06 | pendente (D20) |
| atualizar dados, exportação, vista de camada, fonte registrada (postgres_fdw) | "Overwrite/Update Data", "Export Item", hosted views, "Data store items" | fora — ADR 0005 seções 13-15 (L0-04-g/h/i/j) | fora | — | 2026-09-06 | pendente (D20) |

## Linguagem de expressão (item L2-10-c-linguagem-expressao, turno 3; `docs/EXPRESSAO.md`)

A referência Esri aqui é o [Arcade function reference](https://developers.arcgis.com/arcade/function-reference/)
lido em setembro de 2026: 269 funções em 17 categorias. Uma linha por CATEGORIA; a tabela função a função,
com o estado de cada uma das 269, está na seção 10 de `docs/EXPRESSAO.md`. Os nomes nossos são em português:
paridade aqui é de capacidade, nunca promessa de executar um script Arcade sem adaptação. Totais nas 7
categorias com correspondência: 11 feito · 42 parcial · 81 fora de 134 (revisão de 06/09/2026: a linha `feito` só vale quando NÃO há diferença conhecida contra a documentação oficial e existe vetor de teste da nossa função — 18 linhas caíram de `feito` para `parcial` nessa conferência); as outras 10 categorias
(135 funções — FeatureSet, geometria, pixel, voxel, trajetória, portal, grafo, IA, depuração, empresa)
ficam inteiras de fora, cada uma com o motivo escrito.

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| funções de texto | 22 funções na referência | feito: `Lower`, `Upper`; parcial: `Concatenate`, `Count`, `Find`, `Left`, `Mid`, `Replace`, `Right`, `Split`, `Text`, `Trim` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (2 feito · 10 parcial · 10 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| funções de matemática | 26 funções na referência | feito: `Round`; parcial: `Abs`, `Average`, `Ceil`, `Floor`, `Max`, `Mean`, `Min`, `Number`, `Pow`, `Sqrt`, `Sum` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (1 feito · 11 parcial · 14 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| funções de data | 26 funções na referência | feito: `Timestamp`; parcial: `DateAdd`, `DateDiff`, `Day`, `Month`, `Now`, `Today`, `Weekday`, `Year` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (1 feito · 8 parcial · 17 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| funções de lógica | 9 funções na referência | feito: `Decode`, `IIf`; parcial: `DefaultValue`, `IsEmpty`, `When` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (2 feito · 3 parcial · 4 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| funções de lista | 26 funções na referência | feito: `Count`, `Distinct`, `First`, `Includes`; parcial: `Array`, `Back`, `DefaultValue`, `Front`, `HasValue`, `Reverse` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (4 feito · 6 parcial · 16 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| funções de dicionário | 10 funções na referência | feito: `Count`; parcial: `DefaultValue`, `HasKey` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (1 feito · 2 parcial · 7 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| funções de feição | 15 funções na referência | feito: —; parcial: `DefaultValue`, `HasKey` (equivalentes em português, tabela por função em `docs/EXPRESSAO.md` seção 10) | parcial (0 feito · 2 parcial · 13 fora) | equivalência Python × JavaScript byte a byte em `test_expressao_equivalencia.py` (vetores compartilhados) | 2026-09-06 | pendente (D20) |
| geometria, FeatureSet e consulta entre camadas | 98 funções (FeatureSet 43 + geometria 55) | não existem; a expressão não abre camada nem faz rede | fora (L2-10 cheio, L5-11) | — | 2026-09-06 | pendente (D20) |
| perfis (popup, rótulo, cálculo, restrição, validação, visibilidade, indicador) | 7 perfis, cada um com variáveis e tipo de retorno próprios | núcleo da linguagem só; nenhum perfil ligado a popup, rótulo, formulário ou regra de atributo | fora (L5-11, L5-03-b) | — | 2026-09-06 | pendente (D20) |
| limite de custo da expressão | sem limite documentado de passos ou tempo na referência | 10^5 passos, 500 ms no servidor e 50 ms no cliente, medidos sob ataque; erro nomeado `limite_passos`/`tempo_excedido` | feito (acima da Esri no que é medido) | testador T3 (`test_expressao_seguranca.py`, `test_expressao_extensao.py`) | 2026-09-06 | pendente (D20) |

## Modelo do item e registro de tipos (item L0-03-a-modelo-item, turno 3; ADR 0004 seções 2, 3, 17)

Esta seção cobre só o alicerce do catálogo (`plat.item` + `plat.tipo_item` + rotas `/api/itens` básicas); as demais
capacidades do catálogo (busca, grupos, compartilhamento, tela Conteúdo, miniatura, lixeira, dependências,
transferência, favoritos, versões) já têm linha própria nas tabelas "Metadado ISO..." acima e no restante deste
documento — construídas junto na trilha do item-pai `L0-03-catalogo` (`entregue`). O papel `esri` desta sessão
comparou contra `item-details.htm`/`configure-item-details.htm`/`items-and-item-types` (11.4).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| item com ID uuid opaco e estável, independente de host (irritação 1 da migração: URL/host gravado dentro do JSON) | ID de item imutável ("não pode ser modificado em item existente"); artigo de suporte só para reatribuir ID | `plat.item.id uuid DEFAULT gen_random_uuid()`; gatilho `tg_item_antes` recusa `id`/`tenant_id`/`tipo`/`criado_em`/`criado_por` diferentes com `campo_imutavel` (400); referências entre itens (`item_relacao`, `dados.*_id`) sempre por uuid, nunca URL absoluta | feito | `test_ciclo_crud_uuid_estavel` (uuid igual depois de PUT/PATCH/mover pasta) e `test_put_campos_imutaveis_e_dono` (`tenant_id`,`id`,`dono_id`,`criado_em`,`busca`,`apagado_em`,`tamanho_bytes`,`pontuacao` → 400 `campo_nao_editavel` nomeando o campo) em `tests/api/catalogo/test_itens_modelo.py` | 2026-09-06 | pendente (D20) |
| registro de tipo de item com ~150 tipos REST em famílias | vocabulário fixo da API REST (`DEV-itemtypes`), sem JSON Schema de validação de conteúdo por tipo | `plat.tipo_item` (14 tipos registrados nas famílias camada/raster/mapa/app/painel/formulario/fluxo/rede/arquivo/ferramenta/documento; as demais entram por migração da linha dona, D19); cada tipo carrega o JSON Schema (Draft 2020-12) do campo `dados`, que a Esri não tem | parcial (vocabulário menor que ~150, declarado; validação por schema supera a Esri) | `test_tipo_item_e_vocabulario_sem_escrita` (14 tipos, todos com `additionalProperties:false`) | 2026-09-06 | pendente (D20) |
| `tipo_item` por inquilino (hipótese original do item) | não se aplica (REST da Esri é global por instalação) | decisão do ADR 0004 §3.1: registro **global**, sem `tenant_id` — módulo do front e o esquema são código, não dado do inquilino; `plat_app` só tem `SELECT` (`REVOKE INSERT/UPDATE/DELETE`), escrita só por migração; a hipótese "RLS por inquilino" é lida como "RLS em `item`; `tipo_item` sem dado de inquilino" (texto do ADR) | feito (leitura registrada da hipótese; RLS em `item` cobre o isolamento que importa) | `test_tipo_item_e_vocabulario_sem_escrita` (INSERT/UPDATE em `tipo_item`, DELETE em `relacao_tipo` e INSERT direto em `item_versao` como `plat_app` → `InsufficientPrivilege`); consulta a `pg_class.relrowsecurity`/`information_schema.role_table_grants` nesta sessão confirma ao vivo | 2026-09-06 | pendente (D20) |
| RLS por inquilino em `item` (SELECT/INSERT/UPDATE/DELETE — a Esri não expõe RLS, é conceito da doc de portal multiorganização) | não se aplica | `plat.item` com `ENABLE ROW LEVEL SECURITY` + 4 políticas (`p_item_ler` via `plat.pode_ler`, `p_item_inserir` exige `dono_id = usuario_atual()` e privilégio, `p_item_alterar` via `plat.pode_editar`, `p_item_apagar` sempre `false` — exclusão só lógica pela função `item_lixeira`) | feito | teste cruzado A→B (`tests/api/cruzado_casos.py`, `IT = "/api/itens/{id}"`) cobre GET/PUT/PATCH/DELETE/mover/miniatura/versões/relações/compartilhamento/links do item de B contra sessão de A — todas 404/403 sem vazar existência; confirmado ao vivo (`pg_policy` desta sessão) | 2026-09-06 | pendente (D20) |
| JSON Schema do campo `dados` validado por tipo; erro de validação nomeia o campo | não existe (a Esri valida por tipo internamente, sem expor esquema) | `jsonschema.Draft202012Validator` (`app/catalogo/tipos.py`); tipo inexistente → `422 tipo_inexistente`; `dados` fora do esquema → `422 dados_invalidos` com `detalhe:[{campo: "caminho.do.campo", erro, regra}]` (caminho absoluto do validador) | feito (supera a Esri, que não expõe validação de conteúdo) | `test_criacao_recusada_com_mensagem` (14 casos parametrizados: tipo inexistente, `dados` vazio, campo extra com `additionalProperties:false`, `sha256` malformado, `campos.0.nome` não-string) em `test_itens_modelo.py` | 2026-09-06 | pendente (D20) |
| metadado básico com limite declarado (resumo, descrição, tags, créditos, termos, extent) | resumo e descrição sem teto documentado na doc de uso; extent = envelope do serviço | `resumo` ≤ 2.048 (CHECK no banco + Pydantic), `descricao`/`termos_de_uso` ≤ 65.536, `tags` ≤ 50 (cada ≤ 128, sem vírgula/quebra), `creditos` ≤ 2.048, `extent` `geometry(Polygon,4326)` com CHECK `ST_XMin>=-180 AND ST_XMax<=180 AND ST_YMin>=-90 AND ST_YMax<=90 AND ST_IsValid`; violação em qualquer um → 422 nomeando o campo (`body.resumo`, `body.extent`, `body.tags`) | feito (limites explícitos e testados, o que a doc da Esri não declara) | `test_criacao_recusada_com_mensagem` (resumo de 5.000 → 422 `body.resumo`; extent `[-200,0,1,1]` e `[10,0,1,1]` (min>max) → 422 `body.extent`; tags com vírgula e 51 tags → 422 `body.tags`) | 2026-09-06 | pendente (D20) |
| descrição em Markdown/HTML sem permitir script | editor rico de descrição (WYSIWYG), sem lista de permissão documentada publicamente | Markdown guardado como texto; HTML gerado no servidor e saneado por lista de permissão própria sobre `html.parser` (`app/catalogo/texto.py`): `script`/`style`/`iframe`/`svg`/`object`/`embed` removidos com o conteúdo; `href`/`src` só `https://`,`http://` ou `/api/`; `on*`/`style` nunca sobrevivem | feito | `test_ciclo_crud_uuid_estavel` (`# T\n<script>alert(1)</script> **b**` → `descricao_html` sem `<script` e com `<strong>b</strong>`) | 2026-09-06 | pendente (D20) |
| PUT não move o dono nem o inquilino do item | não documentado (o item REST não expõe `owner`/organização como campo de update direto; `Change Owner`/`Reassign to user` é operação separada) | `ItemEditar` (Pydantic, `extra=forbid`) nunca declara `tenant_id`/`dono_id`/`id`; `campos_json()` recusa qualquer campo fora da lista branca com `400 campo_nao_editavel`; o gatilho do banco (`tg_item_antes`) recusa a troca de `dono_id` fora do modo transferência (`campo_imutavel`/`dono_so_por_transferencia`) como segunda camada | feito (dupla barreira: API e banco) | `test_put_campos_imutaveis_e_dono` (PUT com `dono_id`, `tenant_id` → 400 nomeando o campo) | 2026-09-06 | pendente (D20) |
| paginação de lista com filtro por tipo, cursor e contagem total | `num`/`start` com `nextStart`; sem filtro de tipo isolado sem busca de texto | `GET /api/itens` com `limite`/`deslocamento` OU `cursor` opaco, `total`, `link rel="next"`, filtro `tipo=` isolado; `deslocamento` acima de 10.000 → `422 deslocamento_alto` (a paginação profunda troca por cursor) | feito | `test_lista_paginada_com_cursor_e_deslocamento` | 2026-09-06 | pendente (D20) |
| desempenho de listagem em escala (não documentado pela Esri para instalação própria) | não se aplica | corpus semeado de 10.000 itens (inquilino demo) + 1.000 (demo2); `GET /api/itens?tipo=mapa&limite=50` | feito — **p95 medido 50,8 ms (mediana 23,8 ms) contra o portão de <100 ms**, 20 execuções | `tests/api/catalogo/test_busca.py::test_lista_por_tipo_p95` (`tests/medidas/L0-03-catalogo.json`, campo `lista_tipo_p95_ms`); corpus confirmado ao vivo nesta sessão (`SELECT count(*) FROM plat.item` = 11.414 no schema de demonstração) | 2026-09-06 | pendente (D20) |
| OpenAPI publicado das rotas de conteúdo | REST `/sharing/rest` documentado | `GET/POST /api/itens`, `GET/PUT/PATCH/DELETE /api/itens/{id}`, `GET /api/tipos-item` em `docs/openapi.json` | feito | conferência desta sessão: `app.openapi()` recarregado ao vivo bate exatamente com `docs/openapi.json` para todo path `/api/itens*` e `/api/tipos-item` (uma trilha concorrente do turno mexe em `/api/eu/foto`, fora do escopo deste item — não regravado aqui para não capturar o estado parcial dela) | 2026-09-06 | pendente (D20) |

## Geocodificador (item L2-11-b-geocodificador-brasil, turno 3; ADR 0013)

A referência Esri é o `GeocodeServer` (`developers.arcgis.com/rest/services-reference/enterprise/geocode-service`,
`find-address-candidates`, `reverse-geocode`, `suggest`, `geocode-addresses`, doc datada 06/09/2026, papel
pesquisador+dados+backend+adversário deste turno). Base de dado: CNEFE 2022 do IBGE, UF instalada nesta
demo = Roraima (260.515 pontos, 15 municípios; escolhida por ser o MENOR arquivo entre as 27 UFs, medido por
`HEAD` antes de baixar). Sem ArcGIS Pro/AGOL reais para comparar (D20, aberta para toda a plataforma).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| geocodificação de endereço único (linha única ou multifield) → candidatos com localização e score | `findAddressCandidates` (`SingleLine` ou `address`/`city`/`region`/`postal`); `Match_addr`, `Addr_type`, `Score`, `location` | `POST /api/geocodificar` (nativa) e `GET/POST .../GeocodeServer/findAddressCandidates` (compatível); hierarquia de recuo com `tipo_acerto` (número exato → interpolado na face → aproximado por logradouro/bairro/CEP/município), score 0-100 por semelhança trigram menos penalidade do degrau de recuo | feito | `tests/api/geocodificador/test_geocodificador.py` (50 endereços reais do CNEFE, 3+ municípios: erro mediano **0,0 m**, acerto número/face **98,0%** — portão pede ≤30 m/≥90%) e `test_geocodificador_esri.py::test_find_address_candidates_*` | 2026-09-06 | pendente (D20) |
| ambiguidade de nome repetido entre municípios ("Rua A" em várias cidades) | vários candidatos, sem erro | sem filtro de município, `buscar()` devolve um candidato por município que casa — nunca escolhe um arbitrariamente; medido com `RUA A`, que se repete em 8 dos 15 municípios de Roraima (substituto medido de "Rua A em São Paulo": SP é o MAIOR arquivo de UF do CNEFE, fora do teto de disco D28 — nunca carregado, registrado como tal, não disfarçado) | feito | `test_ambiguidade_rua_a_devolve_varios_municipios` (10 candidatos, ≥3 municípios distintos) | 2026-09-06 | pendente (D20) |
| CEP/UF inconsistente com o município pedido | não documentado como validação explícita | `resolver_lugar()` roda antes da busca por logradouro; CEP e município (ou CEP e UF) que apontam para lugares diferentes → `422 cep_municipio_inconsistente`/`cep_uf_inconsistente`, nomeando o lugar correto do CEP | feito (supera a Esri, que não declara essa checagem) | `test_cep_de_outro_municipio_recusa_inconsistencia` | 2026-09-06 | pendente (D20) |
| geocodificação reversa (ponto → endereço) | `reverseGeocode` (`location=x,y`; `distance`) | `POST /api/reverso` e `.../GeocodeServer/reverseGeocode`; KNN por índice GiST (`geom <->`), sem teto de raio na busca (o raio só marca `fora_do_raio`, não descarta o vizinho) | feito | `test_reverso_50_pontos_logradouro_certo` (**100% de acerto do logradouro** em 50 pontos reais, portão pede ≥90%); `test_reverse_geocode`/`test_reverse_geocode_location_json` | 2026-09-06 | pendente (D20) |
| sugestão/autocomplete por prefixo | `suggest` (`text`; resposta com `magicKey` reaproveitável no findAddressCandidates) | `GET /api/sugerir` e `.../GeocodeServer/suggest`; índice GIN trigram; `chave` (equivalente ao `magicKey`) não é reconsumida no `findAddressCandidates` desta versão (gap nomeado abaixo) | parcial (`magicKey` só devolvido, ainda não aceito de volta) | `test_sugestao_p95_100ms` (**p95 33,1 ms** contra o portão de ≤100 ms, 100 chamadas) | 2026-09-06 | pendente (D20) |
| geocodificação em lote (`geocodeAddresses`) | até `SuggestedBatchSize` (500) por chamada; `Status` M/U/T | `POST .../GeocodeServer/geocodeAddresses`; JSON de corpo (não form/querystring — ver gap abaixo); `Status` M/U implementado, T (tied, múltiplos empates) não distinguido | parcial | `test_geocode_addresses_lote` (2 registros, 1 `M` 1 `U`), `test_geocode_addresses_lote_vazio_e_422` | 2026-09-06 | pendente (D20) |
| API própria em paralelo à compatível Esri | não se aplica (só REST Esri) | `/api/geocodificar`, `/api/reverso`, `/api/sugerir` — mesmo motor, nomes/campos em português | feito (a Esri não tem equivalente) | mesma suíte acima | 2026-09-06 | — |
| descritor do serviço (`?f=json` no recurso do locator) | `currentVersion`, `addressFields`, `candidateFields`, `capabilities`, `spatialReference` | `GET /rest/services/Geocodificador/GeocodeServer` sem autenticação (só metadado) | feito | `test_descritor_servico_sem_autenticacao` | 2026-09-06 | pendente (D20) |
| autenticação por `token=` na querystring (protocolo real do locator publicado) | `generateToken`/token de portal passado em `token=` | reaproveita o token de serviço do plat (escopo `geocodificar:usar`, novo) por querystring nas rotas `GeocodeServer/*`, além do `Authorization: Bearer` normal nas rotas próprias | feito | `test_find_address_candidates_singleline_por_querystring_token`, `test_escopo_errado_e_403` | 2026-09-06 | pendente (D20) |
| instalação por UF com tamanho/tempo/disco medidos antes e depois | não se aplica (a Esri não instala do zero; usa um locator já publicado) | `scripts/geocodificador_instalar_uf.py`: `HEAD` mede o zip antes (teto D28 200 MB), `COPY` em lotes; RR = 4,52 MB comprimidos, 42,05 MB de CSV, 260.515 linhas, 15 municípios, **10,4 s**, tabela final **126 MB com índices** | feito | `test_instalacao_rr_tempo_e_disco_medidos` (lê `plat.geo_instalacao`, grava em `tests/medidas/L2-11-b-geocodificador-brasil.json`) | 2026-09-06 | — |
| nenhuma coluna de dado pessoal (CNEFE não tem; cláusula literal do portão) | não se aplica | grep de `information_schema.columns` sobre `plat.geo_*` por `nome_pessoa`/`cpf`/`nome_morador`/`responsavel` — nenhuma coluna encontrada | feito | `test_cnefe_sem_coluna_de_pessoa` | 2026-09-06 | — |
| QGIS como localizador (`?f=json` do GeocodeServer configurado como serviço de locator externo) | plugin nativo "ArcGIS geocoder"/locator externo | **não medido**: esta máquina não tem QGIS instalado nem ambiente gráfico (mesma limitação do Chrome headless já registrada em `CLAUDE.md`); o protocolo foi provado por chamada HTTP direta simulando exatamente as chamadas que o QGIS faria (`findAddressCandidates`/`suggest`/`reverseGeocode` com os mesmos parâmetros e `token=`) | **pendência** (nunca "feito"; ver ADR 0013 seção 9) | testes HTTP diretos acima cobrem o protocolo, não a integração do produto QGIS | 2026-09-06 | pendente (D20) |
| `outSR`, `searchExtent`, boost por `location=`, `category`, `langCode`, paginação `search/start/num` | parâmetros documentados do `findAddressCandidates` | fora desta versão (saída sempre 4326; sem filtro geográfico nem boost de proximidade) | fora | — | 2026-09-06 | pendente (D20) |
| geocodificação em lote de planilha/CSV do usuário (upload → coluna de endereço → resultado) | não é o `GeocodeServer`; é uma ferramenta de geoprocessamento separada (`Geocode Addresses` do Pro/ArcMap) | item-irmão `L2-11-a-geocodificacao-csv`, ainda não construído (reusa `motor.buscar()`) | fora (item separado) | — | 2026-09-06 | pendente (D20) |

## Ferramentas de análise e GPServer (item L2-05-a-catalogo-ferramentas-gpserver, turno 4; ADR 20260907T2010)

Referência Esri: `gp-service`, `gp-task`, `execute-gp-task`, `submit-gp-job`, `gp-job`, `gp-result`, `cancel-gp-job`
(developers.arcgis.com/rest/services-reference/enterprise, 07/09/2026) e "Perform analysis" do Map Viewer 11.4
(doc.arcgis.com/en/arcgis-online/analyze/perform-analysis-mv.htm). Sem ArcGIS Pro/AGOL reais (D20).

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| registro de ferramenta com parâmetros tipados | Python toolbox (`.pyt`) / GP task com `dataType` GP* | `@ferramenta` + `Parametro(tipo GP*)`, validado na importação; parâmetro sem tipo = erro de build | feito | `tests/unit/test_ferramentas_registro.py` | 2026-09-07 | pendente (D20) |
| catálogo de ferramentas na API e formulário gerado | painel "Analysis" do Map Viewer | `GET /api/ferramentas` (manifesto + JSON Schema); tela `/analise` gera o formulário do manifesto | feito | `test_catalogo_lista_buffer_com_esquema_e_gpserver`; e2e `tests/e2e/test_ferramentas.py` | 2026-09-07 | pendente (D20) |
| execução como job com progresso, cancelamento, log | GP job assíncrono | `ferramentas.executar` na fila L0-05 (progresso, log, cancel); síncrono abaixo de `FERRAMENTA_SINCRONO_CUSTO_MAX` | feito | `test_buffer_por_api_propria_gpserver_execute_e_submitjob_dao_o_mesmo_resultado`, `test_custo_acima_do_teto_vira_job_e_execute_recusa_com_erro_esri` | 2026-09-07 | pendente (D20) |
| resultado como item com proveniência e relação | camada de resultado no conteúdo; sem bloco de proveniência formal | item `camada_vetorial` com `procedencia.ferramenta` {ferramenta, versão, parâmetros, entradas uuid+versão+sha256, data, autor} e relação `derivado_de`; visível na ficha | feito (supera: sha256 das entradas conferível por SQL independente) | mesmo teste acima (`sha256_independente`); e2e com captura `proveniencia` | 2026-09-07 | — |
| histórico de análises e rerodar | "Analysis history" (Map Viewer) | `GET /api/jobs?tipo=ferramentas.executar` + `POST /api/jobs/{id}/repetir` (mesmos parâmetros) | feito | `test_rerodar_do_historico_reproduz_contagem_e_sha256` (contagem e sha256 iguais) | 2026-09-07 | pendente (D20) |
| job cancelado não deixa camada órfã | não documentado | tabela apagada no cancelamento/falha após criada; item nunca gravado | feito | `test_cancelamento_apos_criar_a_tabela_nao_deixa_camada_orfa` | 2026-09-07 | — |
| camada de outro inquilino como entrada | não se aplica (um portal por organização) | 404 (RLS + `pode_ler`) na API e no GPServer | feito | `test_camada_de_outro_inquilino_e_404_na_api_e_no_gpserver`; varredura cruzada | 2026-09-07 | — |
| GPServer: descritores, execute, submitJob, jobs/{id}, results/{param}, cancel, `token=` | referência REST acima | `/rest/services/{ferramenta}/GPServer/{tarefa}/…`, estados esriJob*, erro `{error:{code,message,details}}` com código HTTP real | feito | `test_gpserver_descritores_publicos_token_obrigatorio_e_cancel` e o teste dos três caminhos | 2026-09-07 | pendente (D20) |
| GPFeatureRecordSetLayer por FeatureSet inline; jobs/{id}/inputs; uploads | referência REST | só referência por uuid/URL de FeatureServer desta instalação | parcial | — | 2026-09-07 | pendente (D20) |
| Buffer (Create Buffers) | Map Viewer 11.4 "Use proximity" | `buffer` geodésico em metros, dissolver | feito | testes acima | 2026-09-07 | pendente (D20) |
| demais ferramentas do "Perform analysis" 11.4 (Summarize, Find locations, Enrich, Analyze patterns, Manage data, Use proximity além do buffer) | Map Viewer 11.4 | itens irmãos do L2-05 (b em diante) sobre este registro | fora (itens separados) | — | 2026-09-07 | pendente (D20) |

## Ferramentas de rede: Use proximity (item L2-05-f-rede-isocrona-rota-ferramentas, turno 4)

Referência Esri: "Use proximity" do Map Viewer 11.4 — Generate Travel Areas
(doc.arcgis.com/en/arcgis-online/analyze/generate-travel-areas-mv.htm e
enterprise.arcgis.com/en/portal/11.4/use/generate-travel-areas-mv.htm), Find Nearest, Plan Routes — e a caixa
Network Analyst do ArcGIS Pro
(pro.arcgis.com/en/pro-app/latest/tool-reference/network-analyst/an-overview-of-the-network-analyst-toolbox.htm).
Do nosso lado o cálculo é do OSRM (project-osrm.org/docs/v5.24.0/api), servido pelo item L2-11-c. Sem ArcGIS
Pro/AGOL reais (D20). A diferença de fundo é o dado de rede: a Esri roda sobre um network dataset com regras de
tráfego, restrições e horário; nós rodamos sobre um recorte OSM com um perfil de carro. Onde a Esri cobra crédito
por área de serviço e por parada, o custo aqui é o do nosso próprio servidor.

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| área de serviço / isócrona | Generate Travel Areas (Map Viewer 11.4) — N pontos × M intervalos, "overlapping/dissolve", tempo ou distância | ferramenta `area_de_servico`: N pontos × M intervalos de TEMPO, `por_origem` ou `dissolver`; polígono idêntico ao de `/api/isocrona` | parcial (só intervalo de tempo; distância não) | `test_isocrona_de_30_min_e_a_mesma_do_servico_l2_11_c`, `test_isocrona_por_origem_e_dissolvida_saem_da_mesma_camada_de_entrada` | 2026-09-08 | pendente (D20) |
| modo de viagem (carro, pé, bicicleta) | vários travel modes do network dataset | só `carro`: é o único perfil carregado no OSRM de teste; o parâmetro existe e recusa o resto com 422 | parcial | `test_parametro_fora_da_faixa_e_422_nomeando_o_campo` | 2026-09-08 | pendente (D20) |
| rota por paradas com ordem otimizada | Plan Routes / Find Routes (até 25 paradas) | ferramenta `rota_paradas`: ordem de fid ou otimizada pelo `/trip` do OSRM (inserção do mais distante), até 25 paradas, um trecho por feição com instruções | feito | `test_rota_de_10_paradas_otimizada_nao_custa_mais_que_a_ordem_original` (custo otimizado ≤ custo da ordem original) | 2026-09-08 | pendente (D20) |
| matriz origem-destino | OD Cost Matrix (Network Analyst) | ferramenta `matriz_od`: N×M declarado até 1.000×1.000, partido em blocos do teto do OSRM; par sem rota fica NULL, nunca 0 | feito | `test_matriz_100x100_em_tempo_medido` (medida em `tests/medidas/L2-05-f-*.json`) | 2026-09-08 | pendente (D20) |
| K instalações mais próximas | Find Nearest / Closest Facility | ferramenta `mais_proximas`: K por tempo, com teto de tempo opcional; confere com a matriz das mesmas camadas | feito | `test_k_mais_proximas_confere_com_a_matriz_das_mesmas_camadas` | 2026-09-08 | pendente (D20) |
| conectar pontos à rede (snap) | localização de rede (`Calculate Locations`) | ferramenta `conectar_a_rede`: `/nearest` do OSRM, com deslocamento máximo; fora do alcance = geometria nula | feito | `test_ponto_fora_da_rede_sai_com_geometria_nula_e_distancia_declarada` | 2026-09-08 | pendente (D20) |
| localizar-alocar | Location-Allocation (7 tipos de problema, ótimo por solver) | ferramenta `localizar_alocar`: só cobertura máxima, por heurística gulosa DECLARADA (não é ótimo garantido) | parcial | `test_localizar_alocar_escolhe_por_ganho_decrescente_e_declara_a_cobertura` | 2026-09-08 | pendente (D20) |
| procedência do resultado de rede | não documentada | `metodo` da camada nomeia o serviço usado e a versão do grafo OSM (arquivo, data e sha256 do recorte) | feito (supera) | `test_camada_de_saida_tem_atributos_de_tempo_e_distancia_e_a_versao_do_grafo` | 2026-09-08 | — |
| tráfego por horário, barreiras, janelas de tempo, restrições de veículo | Network Analyst | não existe | fora | — | 2026-09-08 | pendente (D20) |
| área de serviço por DISTÂNCIA e Service Areas do Pro com "trim/polygon detail" | Network Analyst | não existe; a nossa isócrona é grade + casco côncavo, e satura no limite do recorte de teste | fora | — | 2026-09-08 | pendente (D20) |

## SMTP, convite de membro e redefinição de senha (item L0-07-d-smtp-convites, turno 3; ADR 0017)

| capacidade | Esri | nós | estado | testado por | data | Pro/AGOL real |
|---|---|---|---|---|---|---|
| configuração de SMTP da organização (host, porta, TLS, credencial, remetente) | `Portal Administrator Directory` → `security/config/updateEmailSettings` (host, porta, autenticação, `from`) | `.env` da instalação (`PLAT_SMTP_*`) + override por inquilino em `tenant.config->'smtp'` (`GET/PUT /api/org/smtp`, privilégio `org.integracoes`); senha do inquilino cifrada (AES-GCM, `app/correio/cifra.py`), nunca devolvida na leitura | feito | `tests/api/test_smtp_convites.py::test_smtp_ler_gravar_e_remover` | 2026-09-06 | pendente (D20) |
| testar o envio de e-mail a partir da configuração | não documentado publicamente | `POST /api/org/smtp/testar`: envio SÍNCRONO (fora da fila) com erro legível (host/porta/motivo) em texto simples, timeout curto (6 s) | feito | `test_smtp_testar_com_host_errado_devolve_erro_legivel`, `test_smtp_testar_ok_com_captura` | 2026-09-06 | pendente (D20) |
| convite de membro por e-mail (cria a conta ao aceitar) | "Invite members" por e-mail ou link; o convidado define a senha ao entrar pela primeira vez | `POST /api/convites` (job `correio.enviar`, fila do L0-05) → link com token de uso único (sha256 guardado, 7 dias) → `GET /api/convites/resolver` (mostra inquilino/e-mail/perfil) → `POST /api/convites/aceitar` (login/nome/senha escolhidos pelo convidado; cria `plat.usuario` numa única transação `SECURITY DEFINER`) | feito | `test_convite_ponta_a_ponta_chega_aceita_cria_conta` (API, worker real) + `tests/e2e/test_convite.py` (navegador, captura) | 2026-09-06 | pendente (D20) |
| convite: link de uso único, expira, e-mail imutável no aceite | token do convite Esri também de uso único | token consumido numa transação `FOR UPDATE`; usado de novo ou após 7 dias → `410` (mesmo status para os dois motivos, portão do item); o corpo de `POST .../aceitar` nunca aceita um campo `email` (`extra="forbid"`) — o e-mail da conta é sempre o do convite, nunca o que um cliente malicioso tentasse enviar | feito | `test_convite_ponta_a_ponta_chega_aceita_cria_conta` (extra `email` → 422; e-mail da conta criada conferido contra o do convite) e `test_convite_expirado_apos_7_dias_e_410` | 2026-09-06 | pendente (D20) |
| redefinição de senha por e-mail (self-service) | e-mail com link ou pergunta de segurança (a Esri built-in oferece as duas) | `POST /api/senha/redefinir/solicitar {inquilino, email}` — resposta SEMPRE genérica (`202 {"ok":true}`), token de 1 hora, uso único; `POST /api/senha/redefinir/aplicar` reusa a MESMA rotina de troca de senha/histórico/sessões de `PUT /api/eu/senha` | feito | `test_redefinicao_ponta_a_ponta_e_limite_de_taxa` | 2026-09-06 | pendente (D20) |
| limite de taxa contra flood de redefinição | não documentado | `plat.redefinicao_solicitar` (SQL `SECURITY DEFINER`): no máximo 5 pedidos por (inquilino, e-mail normalizado) a cada 15 minutos, contado mesmo quando a conta não existe (`plat.redefinicao_pedido`, sem FK) — senão o próprio limite revelaria existência | feito (refutação do item: 12 pedidos seguidos para o mesmo e-mail estouram antes do fim) | `test_redefinicao_ponta_a_ponta_e_limite_de_taxa` | 2026-09-06 | pendente (D20) |
| e-mail nunca prende a requisição nem vaza segredo em log | não se aplica (SaaS gerenciado) | e-mail sempre por job (`correio.enviar`, `somente_sistema=True` — não criável por `POST /api/jobs`, nem por admin: fecharia canhão de spam com o SMTP do inquilino); senha lida fresca do banco a cada tentativa, nunca gravada em `job.parametros`; erro de `smtplib` convertido para mensagem sem credencial | feito | `tests/unit/test_correio_cliente.py` (erro sem a senha) + `test_senha_smtp_nunca_aparece_no_log_do_worker` (grep no `journalctl` real de `plat-worker`/`plat-api`) + `test_correio_enviar_nao_e_criavel_por_post_jobs` | 2026-09-06 | pendente (D20) |
| caminho manual sem SMTP (nem instalação, nem inquilino) | não se aplica | convite devolve `link_manual` na resposta de `POST /api/convites` (mesmo padrão de "senha temporária mostrada uma vez" de `POST /api/usuarios`); redefinição por e-mail some (o pedido fica só registrado para o limite de taxa) — o usuário pede ao admin, caminho que já existia antes deste item | feito | `test_convite_expirado_apos_7_dias_e_410` (usa o `link_manual` de propósito, sem SMTP) | 2026-09-06 | pendente (D20) |
| avisos de expiração de token (90/30/7/1 dia) e notificação de grupo por e-mail | licença/certificado prestes a expirar avisa por e-mail | **fora desta passagem** (hipótese do item, não do portão literal): exigiria periódico cross-tenant, hoje só sob o inquilino técnico `plataforma` (ADR 0003 seção 7) | fora (ver ADR 0017 seção D5) | — | 2026-09-06 | pendente (D20) |
