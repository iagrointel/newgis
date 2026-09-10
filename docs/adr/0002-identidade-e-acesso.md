# ADR 0002 — Identidade e acesso (item L0-02-tenant-auth; modelo para o produto inteiro)

Estado: aceito pelo arquiteto+dados do turno T2 (05/09/2026), trilha A. Escrito ANTES de qualquer código do item;
o backend (handoff 30) e o frontend (31) codificam contra este documento em paralelo. Substitui a seção 6 do ADR 0001
onde estende (a seção 6 continua valendo para o DDL da migração 002, que é imutável).

Versão-alvo de paridade: ArcGIS Enterprise 11.4 (Portal). Onde a 12.1 acrescenta algo (Enforce MFA, reset de MFA
pelo membro) está dito. Fontes Esri: chaves `E11-*`/`E12-*`/`DEV-*` do handoff `laco/handoffs/T1/21_esri.md`, anexo A
(URLs testadas por HTTP em 05/09/2026). Nenhuma paridade abaixo foi vista numa organização Esri viva; é doc.

Entradas lidas e incorporadas (todas em 05/09/2026):

- `laco/decomposicao/L0_CONCEITO.md` (apareceu às 13:25:07 UTC, 38.682 bytes; laço de espera iniciado 13:23:07):
  decisões D1 (UUID para grupo), D5 (perfil como teto + privilégios finos + papéis personalizados), D6 (números de
  sessão, senha, 2FA e token), D7 (compartilhamento em 5 níveis, `pode_ler`), D14 (`evento` append-only), D18
  (contrato de erro da API), D19 (registro de privilégios por migração), D20 (superadmin fora de inquilino, teste
  cruzado automático). Onde este ADR diverge do conceito está marcado com "DIVERGE DO CONCEITO" e o motivo.
- `laco/decomposicao/L0.json` itens L0-02-a..g, L0-03-d/e, L0-07-b/f, L0-08-e, L0-10, L0-12, L0-14.
- `laco/handoffs/T1/21_esri.md` seções 1 e 3.1 (16 linhas de paridade-alvo).
- `laco/handoffs/T1/refutacao.json` e `32_backend_correcao.md`: as funções `SECURITY DEFINER` da 002 não checam
  inquilino e têm `EXECUTE` para `PUBLIC`. MEDIDO de novo em 05/09/2026 13:24 UTC:
  `SELECT proname, prosecdef, proacl FROM pg_proc WHERE pronamespace = 'plat'::regnamespace` devolve
  `{=X/postgres,postgres=X/postgres,plat_app=X/postgres}` para as 11 funções (o `=X` é o PUBLIC).
- `db/migracoes/002_identidade.sql` (o que EXISTE) e `app/{db,senha,settings,log,main}.py`.
- código do SIG de teste interno (fora deste repositório, só leitura): cookie, TOTP em biblioteca padrão, token com
  prefixo, rotas de 2FA. Copiado em substância, nunca editado.

Medições desta máquina usadas nas decisões (comando entre parênteses):

| grandeza | valor | comando |
|---|---|---|
| pbkdf2_sha256 600.000 iterações | mediana 117,9 ms (117,1–118,3, 5 execuções) | `venv/bin/python` com `hashlib.pbkdf2_hmac` |
| sha256 de 32 bytes | 1,21 ms por 1.000 = 0,0012 ms cada | idem |
| TOTP em biblioteca padrão contra o vetor da RFC 6238 (segredo `12345678901234567890`, T=59) | `287082` (6 dígitos do `94287082` do apêndice B da RFC) | função de 6 linhas com `hmac`/`struct`, copiada do SIG de teste interno |
| `qrcode` 8.2 (BSD) | vive em `/home/dev/.local`, **não** na venv com `PYTHONNOUSERSITE=1` (`ModuleNotFoundError`) | `PYTHONNOUSERSITE=1 venv/bin/python -c "import qrcode"` |
| `cryptography` 41.0.7 | pacote dpkg `python3-cryptography 41.0.7-4ubuntu0.4`, importa na venv com `PYTHONNOUSERSITE=1` (`AESGCM` disponível) | `dpkg -s`; import na venv |
| `pg_cron` 1.6 | `cron.database_name = iagro_sat`, 0 jobs | `SHOW cron.database_name; SELECT count(*) FROM cron.job` |
| `pgaudit` 16.1 | `pgaudit.log = none` | `SHOW pgaudit.log` |
| nginx `limit_req_zone` | módulo presente; zonas `perip` 100r/m e `authip` 10r/m já declaradas em `/etc/nginx/nginx.conf` linhas 42-43 (de outros serviços; não se reaproveitam: zona própria `plat_login`) | `grep limit_req_zone /etc/nginx/...` |
| `plat.log_acesso`, `plat.sessao` | 0 linhas; `plat.usuario` 2 (admins de demonstração) | `SELECT count(*)` |
| RAM | 3 GB disponíveis | `free -g` |

---

## 1. Resumo das decisões (uma linha cada; detalhe nas seções)

1. **Inquilino → usuário → perfil (teto) → privilégios finos → papel personalizado.** O perfil (`admin`, `editor`,
   `visualizador`, `campo`) é ao mesmo tempo o TIPO de usuário da Esri (teto de privilégios) e o papel padrão; um
   papel personalizado é um subconjunto do teto. Não existe assento, licença nem tipo separado do perfil (seção 2).
2. **Vocabulário fechado de 46 privilégios** em `plat.privilegio`, semeado pela migração 003; toda rota declara o
   privilégio que exige; `plat.tem(privilegio)` é a única forma de perguntar (seção 3).
3. **Grupos com UUID**, papéis de grupo `dono | gerente | membro`, entrada `convite | pedido | livre`, marcações
   `atualizacao_compartilhada`, `administrativo`, `protegido` (seção 4). O compartilhamento de item (privado, grupos,
   inquilino, link por token, público autorizado pelo inquilino) é contrato fixado aqui e implementado no L0-03-e
   sobre `plat.pode_ler(item)` (seção 4.3).
4. **Sessão** = cookie `plat_sessao` HttpOnly/Secure/SameSite=Lax com 32 bytes aleatórios, só o sha256 no banco;
   12 h sem uso, 7 dias no máximo, renovada a cada requisição, revogável pela tela (seção 5).
5. **Senha** ≥ 8 caracteres com letra e número (padrão; inquilino sobe até 64), ≠ login, sem as 5 últimas;
   **bloqueio** 5 falhas em 15 min → 15 min, por usuário; hash pbkdf2_sha256 600.000; tempo constante no login
   (seção 6). DIVERGE DO CONCEITO D6 (≥ 10): vale o portão congelado do item (≥ 8), que é também o padrão Esri; 10
   fica como valor configurável recomendado.
6. **2FA TOTP** RFC 6238 (SHA-1, 30 s, janela ±1, sem replay), biblioteca padrão; segredo cifrado com AES-GCM e chave
   derivada de `PLAT_SECRET`; 8 códigos de recuperação; 5 códigos errados = mesmo bloqueio; admin desliga; "exigir para
   todos" é opção do inquilino (seção 7).
7. **Token de serviço** `plat_` + 43 caracteres, sha256 no banco, escopos fechados, restrição por Referer e IP/CIDR,
   validade padrão 90 d e máxima 365 d (pedido acima = 400), revogação imediata sem cache, rotação com 24 h de
   sobreposição, 401 com motivo legível (seção 8).
8. **Log de acesso** por requisição autenticada em `plat.log_acesso` (recriada particionada por mês na 003), escrita
   só por função, retenção 12 meses por `DROP` de partição, consulta pela tela "Log" e por `GET /api/log`
   (seção 9). **Eventos de domínio** em `plat.evento` (append-only, particionada), vocabulário do D14, criada aqui
   porque login, usuário, papel, grupo e token já geram evento (seção 9.3).
9. **Superadmin** = usuário do inquilino técnico reservado `plataforma` (slug reservado, nunca suspenso, sem
   conteúdo); entra pela mesma tela de login; opera outros inquilinos só por funções `SECURITY DEFINER` que resolvem
   a sessão no banco (nunca por GUC) (seção 10).
10. **Migração 003**: recria as funções `auth_*` com checagem de inquilino, `REVOKE ... FROM PUBLIC` em todas,
    `EXECUTE` só `plat_app`, privilégio padrão futuro sem PUBLIC; tabelas novas `privilegio`, `perfil_privilegio`,
    `papel_personalizado`, `papel_privilegio`, `grupo`, `grupo_membro`, `senha_historico`, `evento`; colunas novas
    em `usuario`; `log_acesso` particionada (seção 12).
11. **Gancho de SSO** (L0-08): `usuario.origem` e `usuario.sujeito_externo`; senha, bloqueio e 2FA só para
    `origem = 'local'`; tabela de provedor e rotas ficam para o L0-08 (seção 13).
12. **Testes obrigatórios**: varredura cruzada A→B gerada do OpenAPI com cobertura 100 % como cláusula; força bruta
    de senha, de TOTP e por IP; token revogado ≤ 1 s; escopo; funções `SECURITY DEFINER` chamadas por `psql` como
    `plat_app` com contexto de outro inquilino (seção 15).

---

## 2. Inquilino, usuário e perfil

### 2.1 Inquilino (`plat.tenant`, 002, sem mudança de coluna)

`ativo = false` significa SUSPENSO: nenhum login, nenhum token, nenhuma sessão válida (todas as funções `auth_*`
já filtram `t.ativo`); a API devolve `503 {"erro": "inquilino_suspenso"}` na rota de login e `401` nas demais. Dado
intacto. `config` ganha a chave `auth` (seção 11) validada por JSON Schema em `app/auth/politica.py`; a tela de
edição é do L0-07-a.

Slugs reservados (recusados por `tenant_criar` com `409 {"erro": "slug_reservado"}`): `plataforma`, `plat`,
`public`, `admin`, `api`, `static`, `svc`, `ogc`, `tiles`, `saude`, `entrar`, `conta`. Motivo: são caminhos da URL
ou nomes de schema (`d_<slug>` do D3) que colidiriam.

### 2.2 Usuário (`plat.usuario`, 002 + colunas da 003)

Um usuário pertence a exatamente um inquilino (`UNIQUE (tenant_id, login)`); a mesma pessoa em dois inquilinos são
dois usuários (é o que a Esri faz com dois portais; colaboração entre portais está fora, anexo C do conceito).

Colunas que a 003 acrescenta e por quê:

| coluna | tipo | motivo |
|---|---|---|
| `papel_id` | `int REFERENCES plat.papel_personalizado` NULL | NULL = privilégios do perfil inteiro; preenchido = subconjunto (seção 3) |
| `origem` | `text NOT NULL DEFAULT 'local' CHECK (origem IN ('local','oidc','saml','ldap'))` | gancho L0-08; senha/bloqueio/2FA só para `local` (paridade E12-security: política de senha e MFA "não se aplicam a logins SAML") |
| `sujeito_externo` | `text` | `sub` do OIDC / `NameID` do SAML / DN do LDAP; `UNIQUE (tenant_id, origem, sujeito_externo)` parcial |
| `senha_hash` | passa a NULL permitido com `CHECK (origem <> 'local' OR senha_hash IS NOT NULL)` | conta federada não tem senha local |
| `trocar_senha` | `boolean NOT NULL DEFAULT false` | senha temporária dada pelo admin obriga troca no primeiro acesso (E12-members "reset gera senha temporária e obriga troca") |
| `falhas_desde` | `timestamptz` | janela de 15 min do bloqueio (a 002 conta falhas sem janela) |
| `totp_ultimo_passo` | `bigint` | anti-replay: só aceita passo de tempo maior que o último usado |
| `codigos_recuperacao` | `text[]` | sha256 de cada um dos 8 códigos; usado é removido |
| `desafio_2fa_hash`, `desafio_2fa_ate` | `text`, `timestamptz` | desafio de 2FA de uso único com validade de 5 min (seção 7.2) |
| `ultimo_ip` | `text` | coluna "Last login" da Esri ganha o IP; aparece na tela Usuários |

`superadmin` continua na tabela; a 003 acrescenta um gatilho que só admite `superadmin = true` quando o inquilino é
`plataforma` (seção 10).

### 2.3 Perfil = tipo de usuário = teto de privilégios

Esri separa TIPO (Viewer, Contributor, Mobile Worker, Creator, Professional, Professional Plus: teto e licença) de
PAPEL (Viewer, Data Editor, User, Publisher, Administrator: conjunto de privilégios) (E11-usertypes, E12-roles). O
tipo existe lá por causa da licença por assento. A spec da casa não tem assento nem crédito (D5, D16), logo o tipo
sobrevive só como TETO. Decisão: o perfil (`admin`, `editor`, `visualizador`, `campo`) É o teto e é também o papel
padrão. Mapa de equivalência que vai para `docs/PARIDADE.md`:

| nosso perfil | tipo Esri mais próximo | papel Esri mais próximo | o que pode (teto; lista completa na seção 3.2) |
|---|---|---|---|
| `visualizador` | Viewer | Viewer | ver o que lhe foi compartilhado, entrar em grupos, geocodificar e rotear, gerar token de leitura |
| `campo` | Mobile Worker | Data Editor | visualizador + editar feições compartilhadas, coletar em formulário, compartilhar localização |
| `editor` | Creator | Publisher | campo + criar conteúdo, publicar camadas/tiles/raster, registrar fonte, criar grupos, compartilhar, analisar, executar jobs, editar rede |
| `admin` | Creator | Administrator | tudo, inclusive os privilégios administrativos |

Não existe `Publisher` separado de `editor`: a decisão de publicar ou não é um privilégio (`conteudo.publicar_camada`)
que um papel personalizado pode retirar de um editor. Custo de mudar depois (acrescentar um 5º perfil): `ALTER TABLE
... DROP CONSTRAINT` + novo `CHECK` + linhas em `perfil_privilegio`; nenhuma rota muda porque as rotas perguntam
privilégio, nunca perfil (regra da seção 3.4).

Regras copiadas da Esri e testadas (E12-roles, E12-members): (a) pelo menos um `admin` ativo por inquilino: o último
não se desabilita, não se rebaixa, não se apaga (gatilho `plat.usuario_ultimo_admin` levanta exceção; a API traduz
para `409 {"erro": "ultimo_admin"}`); (b) mudar perfil de ou para `admin` exige que quem muda tenha perfil `admin`
(não basta o privilégio `membros.papel`); (c) só `admin` apaga `admin`; (d) rebaixar perfil de quem possui grupo ou
conteúdo é recusado com a lista do que possui (a parte "conteúdo" entra no L0-03-j; aqui vale para grupos).

---

## 3. Privilégios e papéis personalizados

### 3.1 Forma

- `plat.privilegio (nome PK, grupo, descricao, administrativo boolean)`: registro do vocabulário, semeado pela 003 e
  acrescido só por migração (D19). `administrativo = true` marca os que a Esri lista como "administrative
  privileges" (E12-priv).
- `plat.perfil_privilegio (perfil, privilegio)`: o teto de cada perfil (e o seu papel padrão). Semeado pela 003.
- `plat.papel_personalizado (id serial, tenant_id, nome ≤ 128, descricao ≤ 250, perfil_minimo, criado_por, criado_em,
  UNIQUE (tenant_id, lower(nome)))` + `plat.papel_privilegio (papel_id, privilegio)`. Limites de tamanho são os da
  Esri (E12-configroles). `perfil_minimo` é o "privilege compatibility setting" da Esri: o menor perfil cujo teto
  contém todos os privilégios do papel; calculado pelo backend na criação e recalculado na edição.
- Privilégios efetivos de um usuário: `plat.privilegios_de(usuario_id) RETURNS text[]` =
  `perfil_privilegio(perfil)` quando `papel_id IS NULL`, senão `papel_privilegio(papel) ∩ perfil_privilegio(perfil)`.
  A interseção é a regra Esri "os privilégios de um papel personalizado não podem exceder os do tipo de usuário"
  (E12-roles), aplicada no banco, não só na tela.
- `plat.tem(p_privilegio text) RETURNS boolean` (STABLE, SQL, sem SECURITY DEFINER): `p_privilegio = ANY
  (plat.privilegios_de(plat.usuario_atual()))`. Usada em políticas de RLS de itens futuros (D5) e disponível para
  `Martin`/`tipg` no mesmo contexto.
- Na API, os privilégios vêm JUNTO com a sessão (`plat.auth_sessao` devolve `privilegios text[]`): uma consulta por
  requisição, nenhuma a mais para a checagem. A dependência FastAPI `exigir("membros.gerir")` compara com a lista.

### 3.2 Vocabulário (46 nomes; grupo · nome · o que dá · administrativo · perfis que o têm por padrão)

Critério de inclusão: só o que uma linha do backlog (`estado.json` + `L0.json`/`L3L6.json`/`L5.json`) vai
implementar. Os ~70 da Esri que ficaram fora estão nomeados no fim da tabela com o motivo.

| grupo | nome | dá direito a | adm | V | C | E | A |
|---|---|---|---|---|---|---|---|
| membros | `membros.ver` | ver nome, login, perfil e último acesso dos membros do inquilino (E12: Members: View) | não | x | x | x | x |
| membros | `membros.ver_tudo` | ver e-mail, IP, sessões, tokens e 2FA de qualquer membro | sim | | | | x |
| membros | `membros.gerir` | criar, editar nome/e-mail, desabilitar/reabilitar, redefinir senha, desligar 2FA, desbloquear | sim | | | | x |
| membros | `membros.papel` | mudar perfil e papel (para/de `admin` só quem é `admin`) | sim | | | | x |
| membros | `membros.apagar` | apagar membro (só sem conteúdo e sem grupo; L0-03-j faz a transferência) | sim | | | | x |
| papeis | `papeis.gerir` | criar, editar, apagar papel personalizado (E12: Portal settings: Member roles) | sim | | | | x |
| grupos | `grupos.ver_inquilino` | ver grupos com visibilidade "inquilino" | não | x | x | x | x |
| grupos | `grupos.entrar` | pedir entrada ou entrar em grupo de entrada livre | não | x | x | x | x |
| grupos | `grupos.criar` | criar, editar e apagar os próprios grupos | não | | | x | x |
| grupos | `grupos.atualizacao_compartilhada` | criar grupo com atualização compartilhada | não | | | x | x |
| grupos | `grupos.administrativo` | criar grupo administrativo (membro não sai) | sim | | | | x |
| grupos | `grupos.gerir_todos` | editar, apagar, transferir dono e gerir membros de qualquer grupo | sim | | | | x |
| conteudo | `conteudo.ver_inquilino` | ver itens compartilhados com o inquilino | não | x | x | x | x |
| conteudo | `conteudo.criar` | criar, editar e apagar os próprios itens (mapa, app, pasta) | não | | | x | x |
| conteudo | `conteudo.publicar_camada` | publicar camada vetorial hospedada (L0-04) | não | | | x | x |
| conteudo | `conteudo.publicar_tiles` | publicar tiles vetoriais (L2-01) | não | | | x | x |
| conteudo | `conteudo.publicar_raster` | publicar imagem/raster (L1-01) | não | | | x | x |
| conteudo | `conteudo.registrar_fonte` | registrar fonte de dado externa (L0-04-i) | não | | | x | x |
| conteudo | `conteudo.categorias` | gerir categorias do inquilino (L0-03-b) | sim | | | | x |
| conteudo | `conteudo.ver_tudo` | ver qualquer item do inquilino, inclusive privado | sim | | | | x |
| conteudo | `conteudo.editar_tudo` | editar metadado e dado de qualquer item | sim | | | | x |
| conteudo | `conteudo.apagar_tudo` | apagar/restaurar qualquer item (lixeira L0-03-h) | sim | | | | x |
| conteudo | `conteudo.transferir` | mudar dono de item (L0-03-j) | sim | | | | x |
| compartilhar | `compartilhar.grupo` | compartilhar item com grupo em que pode contribuir | não | | | x | x |
| compartilhar | `compartilhar.inquilino` | compartilhar item com todo o inquilino | não | | | x | x |
| compartilhar | `compartilhar.link` | criar link por token (L0-03-e) | não | | | x | x |
| compartilhar | `compartilhar.publico` | tornar item público (só com `config.compartilhar_publico = true`, D24) | sim | | | | x |
| feicoes | `feicoes.editar` | editar feições de camada compartilhada com edição habilitada (L2-03) | não | | x | x | x |
| feicoes | `feicoes.editar_total` | editar qualquer camada, mesmo sem edição habilitada, com controle total | sim | | | | x |
| campo | `campo.coletar` | usar formulários e a PWA de campo (L2-07) | não | | x | x | x |
| campo | `campo.localizacao` | compartilhar localização/trilhas (L2-07) | não | | x | x | x |
| analise | `analise.geocodificar` | geocodificar e buscar lugar (L2-11) | não | x | x | x | x |
| analise | `analise.rotas` | rotas e isócronas (L2-11) | não | x | x | x | x |
| analise | `analise.executar` | geoprocessamento sobre dado próprio (L2-05) | não | | | x | x |
| analise | `analise.amc` | criar e executar modelo multicritério (L3) | não | | | x | x |
| analise | `analise.raster` | análise de imagem (L1-04/L1-05) | não | | | x | x |
| rede | `rede.tracar` | traçado e subrede (L4-02/L4-04) | não | | | x | x |
| rede | `rede.editar` | editar rede de utilidades (L4-03) | não | | | x | x |
| jobs | `jobs.ver` | ver a lista, o detalhe, o log e os tipos de job do inquilino (leitura) — **alterado em T2**: motivo = todas as rotas de `/api/jobs` exigiam `jobs.executar` e o perfil `visualizador` tomava 403 na tela Tarefas (achado do testador do L0-05); migração 015 | não | x | x | x | x |
| jobs | `jobs.executar` | criar, cancelar e repetir os próprios jobs, e gerir agendas (L0-05) — **alterado em T2**: motivo = a leitura saiu para `jobs.ver`; este passa a ser o privilégio de execução | não | | x | x | x |
| jobs | `jobs.gerir_todos` | ver e cancelar jobs de qualquer membro | sim | | | | x |
| tokens | `tokens.gerar` | criar e revogar os próprios tokens de serviço | não | x | x | x | x |
| tokens | `tokens.gerir_todos` | ver e revogar tokens de qualquer membro (E12: Find API key, token) | sim | | | | x |
| org | `org.configurar` | editar `tenant.config` (L0-07-a), política de senha, exigir 2FA, domínios de e-mail | sim | | | | x |
| org | `org.log_ver` | ler `log_acesso` e `evento` do inquilino, exportar CSV | sim | | | | x |
| org | `org.exportar` | exportar o inquilino (L0-06-d), relatórios (L0-07-e) | sim | | | | x |
| org | `org.integracoes` | SSO (L0-08), SMTP (L0-07-d), webhooks (L7-08), CORS | sim | | | | x |

V = visualizador · C = campo · E = editor · A = admin. Contagem: **47 privilégios** (46 em T1 + `jobs.ver` na migração 015 do T2), 18 administrativos (a contagem linha a linha dá 20; ver `tests/api/test_privilegios_declarados.py`).

Fora do vocabulário, com motivo: `Take ArcGIS Pro license offline`, `Manage licenses` (sem licença por assento);
`Publish hosted scene layers` (L2-09 decide se 3D entra e acrescenta `conteudo.publicar_cena` por migração);
`Publish hosted knowledge graphs`, `Reality Mapping`, `Publish video/livestream` (fora do produto, anexo C do
conceito); `View location tracks` (coberto por `campo.localizacao` + `membros.ver_tudo`); `Create and edit
notebooks`, `Schedule notebooks`, `Advanced notebooks` (L2-16 acrescenta `notebooks.*` se entrar); `Assign
privileges to OAuth 2.0 applications` (sem OAuth de app; token de serviço cobre); `Collaborations` (sem colaboração
entre portais); `Servers`, `Utility services` (sem federação; o operador é o superadmin).

### 3.3 Regras dos papéis personalizados (testáveis)

- `POST /api/papeis` recusa privilégio fora do teto do `perfil_minimo` informado com `422 {"erro":
  "privilegio_fora_do_teto", "detalhe": ["conteudo.publicar_camada"]}`; recusa privilégio `administrativo` quando
  `perfil_minimo <> 'admin'` (regra Esri: papel administrativo só para tipo criador; aqui só para `admin`).
- Atribuir `papel_id` a um usuário cujo perfil é menor que `perfil_minimo` do papel: `422 {"erro":
  "papel_incompativel"}` (a interseção do banco nunca deixaria passar privilégio a mais; o 422 evita papel
  silenciosamente vazio).
- Apagar papel em uso: `409 {"erro": "papel_em_uso", "detalhe": {"usuarios": n}}`.
- Papel só existe dentro do inquilino (RLS); os 4 perfis não são linhas de `papel_personalizado` e não se apagam.
- Quem cria papel precisa de `papeis.gerir`; um usuário não pode se dar privilégio que não tem (o backend compara a
  lista pedida com `privilegios_de(quem pede)`; sobra = 403 `privilegio_proprio_insuficiente`).

### 3.4 Regra transversal: rota pergunta privilégio, nunca perfil

Toda rota declara em código (`dependencies=[exigir("x")]`) o privilégio; `tests/api/test_privilegios_declarados.py`
percorre o OpenAPI e reprova rota autenticada sem privilégio declarado (as exceções são listadas no próprio teste:
`/api/eu*`, `/api/login*`, `/api/logout`, `/api/privilegios`). O `if perfil == 'admin'` aparece só nas três regras
da seção 2.3 (b)(c) e no superadmin (seção 10). Motivo: é o que permite acrescentar perfil ou papel sem tocar em rota
(custo de mudar = 0 rotas).

---

## 4. Grupos e compartilhamento

### 4.1 Grupo (`plat.grupo`, 003)

```
id uuid PK DEFAULT gen_random_uuid() · tenant_id · nome (1..128) · resumo (≤ 2048) · tags text[] (≤ 50) ·
visibilidade CHECK IN ('membros','inquilino') · entrada CHECK IN ('convite','pedido','livre') ·
contribuicao CHECK IN ('todos','dono_gerentes') · atualizacao_compartilhada boolean · administrativo boolean ·
protegido boolean · dono_id → usuario · criado_em · UNIQUE (tenant_id, lower(nome))
```

`plat.grupo_membro (grupo_id, usuario_id, papel CHECK IN ('dono','gerente','membro'), estado CHECK IN
('ativo','convidado','pedido'), convidado_por, criado_em, PRIMARY KEY (grupo_id, usuario_id))`. Um grupo tem
exatamente um `dono` (linha em `grupo_membro` com papel `dono` = `grupo.dono_id`; gatilho mantém as duas em acordo).

Decisões e origem (E12-groups, E12-owngroups, E12-managegroups):

- UUID (D1): o id vai para URL, para o pacote de exportação do inquilino e para o compartilhamento de item.
- `visibilidade`: a Esri tem "Only group members / All organization members / Everyone (public)"; "public" de grupo
  fica fora até D24 (público de item); acrescentar depois é um valor no CHECK.
- `entrada`: "By invitation / By request / By adding themselves" da Esri; grupo por atributo SAML/OIDC é do L0-08-e
  (coluna `grupo_externo text` entra nessa migração, não agora).
- `atualizacao_compartilhada` só se define na criação (a Esri também) e só com entrada `convite` ou `pedido`; exige
  `grupos.atualizacao_compartilhada`; o dono do item continua dono (regra do L0-03-e).
- `administrativo`: membro não sai (`DELETE .../membros/{eu}` = `409 grupo_administrativo`); só quem tem
  `grupos.administrativo` cria.
- `protegido`: `DELETE /api/grupos/{id}` = `409 grupo_protegido` até desligar (a Esri: "Prevent this group from
  being accidentally deleted").
- Convite é notificação interna (a Esri diz literalmente que "não é enviado como e-mail"); e-mail entra com o SMTP
  do L0-07-d. Notificação interna = linha em `plat.evento` tipo `grupos/convidar` com `alvo = usuario`; a tela "Minha
  conta" lista convites pendentes lendo `grupo_membro` com `estado = 'convidado'` (sem tabela nova).
- Limites Esri que copiamos como `app/limites.py`: 512 grupos por usuário (`GRUPOS_POR_USUARIO`), 24 itens em
  destaque (L0-03), tags ≤ 50.
- Apagar grupo remove `grupo_membro` (cascata) e os compartilhamentos de item com ele (L0-03-e); os itens ficam.
- Transferir dono: `PUT /api/grupos/{id} {"dono_id": n}` por dono ou `grupos.gerir_todos`; novo dono tem de ser
  membro ativo; se `atualizacao_compartilhada`, novo dono precisa de `grupos.atualizacao_compartilhada` (regra Esri).

RLS de `grupo`: `USING (tenant_id = plat.tenant_atual())` para escrita; para LEITURA a política acrescenta a
visibilidade: `tenant_id = plat.tenant_atual() AND (visibilidade = 'inquilino' OR plat.tem('grupos.gerir_todos') OR
EXISTS (SELECT 1 FROM plat.grupo_membro m WHERE m.grupo_id = id AND m.usuario_id = plat.usuario_atual()))`. Membro
`convidado`/`pedido` vê o grupo (precisa ver o que aceitou/pediu). É a primeira política que usa `plat.tem`, e o
padrão que o L0-03-e repete com `pode_ler`.

### 4.2 Papéis de grupo

| ação | dono | gerente | membro | não membro |
|---|---|---|---|---|
| editar nome/resumo/tags/visibilidade/entrada/contribuicao/protegido | x | x | | |
| apagar, transferir dono, ligar/desligar `administrativo` | x | | | |
| convidar, aprovar pedido, mudar papel gerente/membro, remover membro | x | x | | |
| sair | | x (vira ex-membro) | x (salvo administrativo) | |
| pedir entrada / entrar (livre) | | | | x |
| compartilhar item com o grupo (L0-03-e) | x | x | x se `contribuicao = 'todos'` | |

`grupos.gerir_todos` age como dono em qualquer grupo (é o "Groups: Update/Delete/Reassign ownership/Assign members"
administrativo da Esri).

### 4.3 Compartilhamento de item (contrato para L0-03-e; nada disto é construído no L0-02)

Níveis (D7): `privado` (só dono e quem tem `conteudo.ver_tudo`) · `grupos` (lista em `plat.item_grupo`) · `inquilino`
· `link` (token ≥ 32 hex em `plat.compartilhamento_link` com `expira_em`, `revogado_em`, `acessos`) · `publico`
(só se `tenant.config.compartilhar_publico = true`, decisão D24 do dono pendente; padrão `false`). Os níveis
combinam-se como na Esri (inquilino + grupos; público + grupos). A decisão de leitura é `plat.pode_ler(item_id)`
(SQL STABLE) usada na RLS de `item` e de toda tabela dependente; `plat.pode_editar(item_id)` = dono, ou
`conteudo.editar_tudo`, ou membro de grupo com `atualizacao_compartilhada` que contém o item. 404 para item sem
acesso (não 403). Link revogado nega em ≤ 1 s: nenhum cache de autorização. Custo de mudar: a função é uma.

O que o L0-02 entrega para isso já funcionar quando o item existir: `grupo`, `grupo_membro`, `plat.tem`,
`privilegios_de`, e o token de serviço com escopo `camada:ler:<uuid>` (seção 8.2).

---

## 5. Sessão

### 5.1 Forma

- Cookie `plat_sessao`, valor = 64 hex (32 bytes de `gen_random_bytes` gerados no banco por `auth_sessao_criar`),
  atributos `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=<sessao_max_dias em segundos>`. `Secure` sempre em
  `producao`; em `dev` segue `X-Forwarded-Proto` (o nginx manda `https`).
- Banco guarda só `sha256(valor)` (`sessao.token_hash`, 002). Um dump do banco não entrega sessão válida. Custo
  medido de um sha256: 0,0012 ms.
- Validade: `expira_em = criado_em + sessao_max_dias` (absoluta) E `ultimo_uso >= now() - sessao_ociosa_horas`
  (deslizante). `auth_sessao(p_hash, p_ociosa_horas)` faz o `UPDATE ultimo_uso = now()` só quando a sessão está
  válida pelos dois critérios e devolve a linha; caso contrário devolve 0 linhas e a API responde `401
  {"erro": "sessao_expirada"}`. A linha vencida é apagada pelo periódico `plat.sessoes_expurgar()` (L0-05-d; até lá,
  `plat sessao expurgar` na CLI e no `make`), nunca pelo caminho da requisição.
- Números (D6; ancora Esri: token padrão 120 min, máximo 14 d, E11-tokenexp): padrão 12 h ocioso, 7 dias máximo;
  por inquilino `auth.sessao_ociosa_horas ∈ [1, 24]`, `auth.sessao_max_dias ∈ [1, 30]`.
- Renovação: cada requisição autenticada com sucesso atualiza `ultimo_uso` (é o deslizamento). O cookie não é
  reemitido (o `Max-Age` já é o máximo absoluto). Não existe "lembrar-me" (a Esri também não tem).
- Uma sessão por login (várias abas partilham o cookie); vários dispositivos = várias sessões, listadas em
  `GET /api/eu/sessoes` (id exibido = 12 primeiros hex do HASH, nunca do valor) e revogáveis uma a uma ou "todas
  as outras". Troca de senha, redefinição pelo admin, desabilitação e desligamento de 2FA pelo admin apagam TODAS as
  sessões do usuário (`plat.sessoes_encerrar_usuario`).
- O que a API devolve no login: `{"ok": true, "usuario": {...igual a /api/eu...}}`; o token nunca vai no corpo.
- Logout: `DELETE FROM plat.sessao WHERE token_hash = ...` + cookie apagado + linha em `log_acesso` com
  `resultado = 'logout'` (a Esri não registra logout, E12-portallogs; aqui registra).

### 5.2 Onde o token de sessão nunca pode aparecer

Journal (`--no-access-log` já está na unidade; o middleware redige `Cookie`, `Authorization`, `senha`, `codigo`,
`desafio`, `token` de qualquer linha), `log_acesso.rota` (query redigida por `app/auth/redigir.py`), respostas JSON,
mensagens de erro, capturas do e2e (o playwright grava tela, não cabeçalho). Teste: 20 logins e `journalctl -u
plat-api --since` + `SELECT rota FROM plat.log_acesso` com 0 ocorrências do valor.

### 5.3 CSRF e origem

Defesa em duas camadas, ambas testadas: (1) `SameSite=Lax` (o navegador não manda o cookie em POST de outro site);
(2) toda rota que altera estado sob cookie exige `Content-Type: application/json` (`415` caso contrário; um `<form>`
de outro site não consegue mandar JSON sem preflight) e, quando o cabeçalho `Origin` vem, ele tem de ser igual a
`PLAT_URL_PUBLICA` (`403 {"erro": "origem_invalida"}`). Sob `Authorization: Bearer` a checagem de origem não se
aplica (cliente não é navegador). Motivo de não usar token CSRF sincronizado: exigiria estado por formulário em
telas sem framework (ADR 0001 seção 11) e o par Lax + JSON já cobre o vetor; a OWASP CSRF Prevention Cheat Sheet
(versão vigente em 2026) aceita a combinação de SameSite com verificação de origem como defesa.

### 5.4 Pendências de sessão

`auth_sessao` devolve `trocar_senha` e `totp_ativo`; o backend calcula `pendencias`: `["trocar_senha"]` quando
`usuario.trocar_senha`, `["configurar_2fa"]` quando `tenant.config.auth.exigir_2fa = true` e `totp_ativo = false`.
Com pendência, toda rota fora de `/api/eu`, `/api/eu/senha`, `/api/eu/2fa/*`, `/api/logout` responde `403
{"erro": "pendencia", "detalhe": ["trocar_senha"]}`; o front redireciona para `/conta#senha` ou `/conta#2fa`. Token
de serviço criado por usuário com pendência não funciona (`401 pendencia_do_usuario`). Isto é o "Enforce MFA" da
12.1 ("desloga na hora todo membro sem MFA") em versão que não derruba: deixa entrar só para configurar.

---

## 6. Senha e bloqueio

### 6.1 Política (padrão da plataforma; por inquilino em `tenant.config.auth`, seção 11)

| regra | padrão | faixa configurável | origem |
|---|---|---|---|
| comprimento mínimo | **8** | 8–64 | portão congelado do item ("senha ≥ 8 com letra e número") e padrão Esri (E11-security: "pelo menos oito caracteres com pelo menos uma letra e um número"). DIVERGE DO CONCEITO D6 (10, lido no SIG de teste interno): o portão não se move; 10 é o valor que a tela de política (L0-07-a) sugere ao admin |
| composição | ≥ 1 letra e ≥ 1 dígito | pode exigir maiúscula, minúscula e símbolo (Esri "Manage password policy") | E11-security |
| comprimento máximo | 128 | fixo | pbkdf2 sobre 128 bytes; evita DoS por senha de 1 MB |
| espaços | permitidos (inclusive frases) | fixo | NIST SP 800-63B §5.1.1.2 aceita todos os caracteres imprimíveis e espaço; a Esri proíbe espaço, decisão nossa a favor de frase-senha |
| igual ao login, ao slug ou ao nome | recusada | fixo | E11-security ("não pode ser igual ao username") |
| histórico | as 5 últimas não podem voltar | 0–24 | Esri "número de senhas anteriores"; `plat.senha_historico` guarda 5 hashes por usuário |
| expiração | desligada | 0 (nunca) ou 30–365 dias | Esri "dias até expirar"; vencida = pendência `trocar_senha` no login |
| lista de senhas vazadas | não conferida | — | sem base local; o item L7-03 decide se entra (custo: arquivo de 30 MB, disco a 98 %) |

Mensagens de recusa nomeiam a regra: `422 {"erro": "senha_fraca", "mensagem": "a senha precisa de 8 caracteres com
letra e número", "detalhe": {"regra": "minimo"}}`; `detalhe.regra ∈ {minimo, composicao, maximo, igual_login,
historico}`. A conferência é no servidor (`app/auth/politica.py`); o front repete a regra ao vivo só como ajuda.

Hash: `pbkdf2_sha256$600000$<salt>$<hex>` (ADR 0001 seção 6; `app/senha.py` já existe). MEDIDO: 117,9 ms por
verificação nesta máquina. Mudar o algoritmo depois = novo prefixo, re-hash no próximo login; custo baixo.

### 6.2 Bloqueio (lockout)

- **5 falhas em 15 minutos → bloqueado por 15 minutos**, por USUÁRIO (padrão Esri, E11-security: "5 tentativas
  falhas em 15 minutos → bloqueio de 15 minutos, inclusive para o administrador inicial"). Por inquilino:
  `auth.bloqueio_tentativas ∈ [3, 10]`, `auth.bloqueio_minutos ∈ [5, 60]`, `auth.bloqueio_janela_min` = 15 fixo.
- Contagem no banco (`falhas_login`, `falhas_desde`, `bloqueado_ate`), não em memória: a unidade roda 2 workers
  (`plat-api.service`, `--workers 2`) e um contador em processo deixaria passar 2× as tentativas.
- `auth_falha` (003) zera o contador quando `falhas_desde < now() - janela`; ao atingir o máximo grava
  `bloqueado_ate` e mantém o contador. Sucesso (`auth_ok`) zera tudo.
- Bloqueado: `423 {"erro": "bloqueado", "mensagem": "usuário bloqueado até <ISO>", "detalhe": {"bloqueado_ate":
  ...}}` mesmo com senha certa (a 6ª tentativa correta é o teste do portão). Senha errada ou usuário inexistente:
  `401 {"erro": "credenciais_invalidas"}` com a MESMA mensagem ("inquilino, usuário ou senha inválidos") e tempo
  constante: quando o usuário não existe, o backend verifica a senha contra um hash fixo (`HASH_FANTASMA`, gerado
  na partida) para gastar os mesmos ~118 ms; substitui o `time.sleep(0.4)` do SIG de teste interno, que denuncia o
  ramo pelo tempo.
- Falhas de TOTP e de código de recuperação contam no MESMO contador (5 códigos errados = bloqueio; refutação do
  L0-02-c). Um só relógio, uma só tela de "bloqueado até".
- Desbloqueio: pelo tempo; por `POST /api/usuarios/{id}/desbloquear` (`membros.gerir`); pela CLI
  `plat usuario desbloquear`. O último admin bloqueado por um atacante que conhece o login é um risco aceito e
  documentado (a Esri tem o mesmo): a mitigação é a camada por IP abaixo mais o segundo admin que a tela Usuários
  recomenda criar.
- Por IP, no nginx: `limit_req_zone $binary_remote_addr zone=plat_login:10m rate=10r/m;` em
  `/etc/nginx/conf.d/plat_limites.conf` (escrito pelo `install.sh`; precedente da casa: dois outros serviços já
  declaram a própria zona `limit_req` em `/etc/nginx/conf.d/`, MEDIDO por `grep`) e
  `location = /api/login { limit_req zone=plat_login burst=10 nodelay; limit_req_status 429; }` (e o mesmo em
  `/api/login/2fa`). Um IP consegue no máximo 20 tentativas no primeiro minuto e 10 por minuto depois, contra todos os
  usuários de todos os inquilinos; o bloqueio por usuário não vira negação de serviço do inquilino inteiro
  (refutação do L0-02-b: 200 logins de 200 usuários diferentes do mesmo IP → 429, o admin de outro IP entra).
- Tentativas de login com inquilino inexistente ou usuário inexistente vão para `log_acesso` com `tenant_id` NULL e
  `resultado = 'inexistente'` (sem gravar o login digitado: pode ser uma senha colada no campo errado).

### 6.3 Redefinição pelo admin e troca pelo usuário

- `POST /api/usuarios/{id}/senha` (`membros.gerir`; para alvo `admin` só quem é `admin`): gera senha temporária de
  12 caracteres (`secrets`), devolve UMA vez no JSON, grava `trocar_senha = true`, apaga sessões e desafios do alvo,
  evento `usuarios/redefinir_senha`. Sem e-mail (L0-07-d). Não há "esqueci a senha" público neste item: a Esri usa
  pergunta de segurança ou e-mail; pergunta de segurança foi rejeitada (L0-02-g) e e-mail depende do SMTP.
- `PUT /api/eu/senha {"atual", "nova"}`: exige a atual (`401 senha_atual_incorreta`), aplica a política, grava no
  histórico, limpa `trocar_senha`, apaga as OUTRAS sessões (a atual continua), evento `usuarios/trocar_senha`.
- Conta com `origem <> 'local'`: as duas rotas respondem `409 {"erro": "login_externo"}`.

---

## 7. Segundo fator (TOTP)

### 7.1 Algoritmo e armazenamento

- TOTP RFC 6238, HMAC-SHA1, 30 s, 6 dígitos, janela ±1 passo (aceita o código anterior e o próximo: tolera 30 s de
  desvio de relógio; a Esri usa app autenticador padrão, E11-security). Implementação de biblioteca padrão
  (`hmac`, `struct`, `base64`), 6 linhas copiadas do SIG de teste interno, conferida contra o vetor da RFC
  (T=59 → `287082`). `pyotp` está ausente e não se instala (regra do turno).
- Segredo: 20 bytes aleatórios → base32 sem `=` (32 caracteres). No banco, `totp_secret` guarda
  `enc:v1:<base64(nonce 12 B + AES-GCM(chave, segredo))>` com chave = `sha256(PLAT_SECRET || "totp")`. `SELECT
  totp_secret` mostra o prefixo `enc:v1:` (cláusula do L0-02-c). `cryptography` 41.0.7 é pacote dpkg
  (`python3-cryptography`), importa na venv com `PYTHONNOUSERSITE=1`, entra na lista de dpkg conferida pelo
  `install.sh` (passo f). Perder `PLAT_SECRET` = todos os segredos TOTP ilegíveis = todo mundo cai em "2FA
  indisponível, use código de recuperação ou peça ao admin"; por isso o `.env` entra no backup (L0-06-a).
- Anti-replay: `totp_ultimo_passo` guarda o passo (T = floor(t/30)) do último código aceito; só se aceita `passo >
  totp_ultimo_passo`. Código reusado nos 30 s = `401 codigo_invalido` (refutação do L0-02-c). Relógio do cliente
  adiantado 5 min = 10 passos fora da janela = recusado.
- Códigos de recuperação: 8, formato `xxxx-xxxx-xx` (10 caracteres de `[a-z2-7]`, 50 bits), mostrados uma vez na
  confirmação, guardados como sha256 em `codigos_recuperacao text[]`; usar um remove-o do vetor; regenerar exige a
  senha. Com 0 restantes, "Minha conta" avisa.
- QR: gerado no servidor como SVG por `qrcode` 8.2 (BSD, puro Python, sem Pillow para SVG). DIVERGE DO L0.json
  ("qrcode já presente"): presente só no site do usuário `dev`, que a unidade não vê. Decisão: `qrcode==8.2` entra em
  `requirements.txt` (o `install.sh` já instala o arquivo na venv; 1 pacote, 3 arquivos essenciais, sem dependência).
  O `otpauth://` e o segredo em texto aparecem ao lado do QR para digitação manual (a Esri também mostra o código de
  16 caracteres). Rótulo `otpauth://totp/plat:<slug>/<login>?secret=...&issuer=plat&digits=6&period=30`; `plat` é o
  codinome enquanto D18 (nome público) está aberta; mudar o rótulo depois não invalida segredos.

### 7.2 Fluxo de login com 2FA

1. `POST /api/login {inquilino, login, senha}` → senha certa e `totp_ativo`: o backend gera `desafio` (32 bytes
   urlsafe), grava `desafio_2fa_hash = sha256(desafio)`, `desafio_2fa_ate = now() + 5 min`, e responde `200
   {"ok": false, "exige_2fa": true, "desafio": "<valor>", "recuperacao_disponivel": true|false}`. Nenhum cookie.
   O desafio é de uso único e vive no banco (funciona com 2 workers; `PLAT_SECRET` não precisa assinar nada).
2. `POST /api/login/2fa {desafio, codigo}` ou `{desafio, codigo_recuperacao}` → confere hash e validade (`410
   desafio_expirado`), confere código (`401 codigo_invalido`, conta falha), zera o desafio, cria a sessão, cookie,
   `200 {"ok": true, "usuario": ...}`. Evento `usuarios/entrar` com `propriedades.fator = "totp" | "recuperacao"`.
3. Tela: o mesmo `login.html` troca o formulário de senha pelo de código sem recarregar.

### 7.3 Ligar, desligar, exigir

- `POST /api/eu/2fa/iniciar` (só sessão, nunca token; `409 ja_ativo` se já ligado): gera segredo, grava cifrado com
  `totp_ativo = false`, devolve `{segredo, uri, qr_svg}`.
- `POST /api/eu/2fa/confirmar {codigo}`: valida contra o segredo pendente; liga; devolve `{codigos_recuperacao: [8]}`
  uma única vez; evento `usuarios/2fa_ligar`.
- `POST /api/eu/2fa/desativar {senha, codigo}`: exige senha E código atual; se `auth.exigir_2fa = true` no inquilino,
  `409 {"erro": "2fa_obrigatorio"}`; apaga segredo e códigos; evento `usuarios/2fa_desligar`.
- `POST /api/eu/2fa/codigos {senha}`: regenera os 8.
- `POST /api/usuarios/{id}/2fa/desativar` (`membros.gerir`; alvo `admin` só por `admin`): o "Disable multifactor"
  da Esri (E12-security); apaga segredo e códigos, apaga sessões do alvo, evento `usuarios/2fa_desligar` com
  `ator ≠ alvo`. Se o inquilino exige 2FA, o alvo entra com pendência `configurar_2fa`.
- `auth.exigir_2fa` (inquilino, `org.configurar`): efeito na seção 5.4. Lista de isenção da 12.1: fora (custo:
  coluna `isento_2fa` em usuario; entra se um cliente pedir).
- Conta `origem <> 'local'`: 2FA é do provedor; rotas `/api/eu/2fa/*` respondem `409 login_externo`.

---

## 8. Token de serviço

### 8.1 Forma e ciclo de vida

- Valor: `plat_` + `secrets.token_urlsafe(32)` (43 caracteres) = 48 caracteres; `prefixo` = 12 primeiros (`plat_` +
  7) para a lista; banco guarda sha256 (002). Mostrado uma única vez (`201` da criação e da rotação).
- Dono: o usuário que criou (`usuario_id`); o token nunca tem mais que `privilegios_de(dono) ∩ escopos`; dono
  desabilitado, inquilino suspenso ou dono com pendência (seção 5.4) = token inválido na hora (`auth_token` já faz o
  JOIN com `u.ativo AND t.ativo`; a 003 acrescenta `trocar_senha = false`).
- Validade: `expira_em` obrigatória; padrão 90 dias, máximo 365 dias (D6; chave de API Esri ≤ 1 ano, DEV-apikey).
  Pedido acima do máximo → `400 {"erro": "validade_acima_do_maximo", "detalhe": {"maximo_dias": 365}}` (decisão
  escrita: a Esri recorta em silêncio e o usuário descobre pelo "Invalid Token", irritação 8). Por inquilino
  `auth.token_max_dias ∈ [1, 365]` só diminui.
- Revogação: `DELETE /api/tokens/{id}` grava `revogado_em`; sem cache: a próxima requisição (≤ 1 s) recebe
  `401 {"erro": "token_revogado", "mensagem": "token revogado em <ISO>"}`. Expirado: `401 token_expirado` com a data.
  Motivo legível é a resposta à irritação 8.
- Rotação: `POST /api/tokens/{id}/renovar` cria token novo com os mesmos escopos/restrições/validade e grava no antigo
  `expira_em = least(expira_em, now() + 24 h)`, `renovado_por = novo.id`; os dois valem por 24 h (D6). Evento
  `tokens/renovar`.
- Uso: cabeçalho `Authorization: Bearer <token>` em `/api/`, `/svc/`, `/ogc/`, `/tiles/`; parâmetro `?token=` aceito
  SÓ em `/svc/`, `/ogc/`, `/tiles/` (clientes SIG de mesa que só sabem colar URL: é o que a Esri faz com `?token=` e
  o que o SIG de teste interno faz com `/svc/<token>/`); em `/api/` o `?token=` é ignorado e a rota responde 401.
  O valor é redigido do `log_acesso.rota` e do journal.
- Quem pode: `tokens.gerar` (todos os perfis, como a Esri deixa qualquer membro gerar token); `tokens.gerir_todos`
  vê e revoga os do inquilino (`GET /api/tokens?todos=1`).
- Um token NÃO pode: criar/revogar tokens, mudar senha, mexer em 2FA, listar sessões (`403 so_sessao`). Motivo: um
  token vazado não pode se perpetuar.
- Limite: 20 tokens ativos por usuário (`app/limites.py`, `TOKENS_POR_USUARIO`; a Esri: 2 chaves por credencial,
  sem limite de credenciais; escolhemos um número que a tela lista sem paginação).

### 8.2 Escopos (vocabulário fechado, validado por expressão regular em `app/auth/escopos.py`)

| escopo | dá | quem aplica |
|---|---|---|
| `catalogo:ler` | listar e ler metadado de itens que o dono pode ler | L0-03 |
| `camada:ler` · `camada:ler:<uuid>` | ler feições/atributos de qualquer camada legível pelo dono · só a camada `<uuid>` | L2-04, L0-04-h |
| `camada:editar` · `camada:editar:<uuid>` | `applyEdits`/OGC edição (exige `feicoes.editar` no dono) | L2-03, L2-04 |
| `tiles:ler` · `tiles:ler:<uuid>` | tiles vetoriais e raster | L1-02, L2-01 |
| `jobs:executar` | criar e ler os próprios jobs (leitura exige `jobs.ver` no dono, escrita exige `jobs.executar`; **alterado em T2**, migração 015 — não há escopo novo) | L0-05 |
| `admin:inquilino` | tudo o que o dono pode fazer pela API, exceto o que a seção 8.1 proíbe | CLI L0-14, laço agêntico |

Regras: escopo sem `:<uuid>` cobre os com `<uuid>`; `admin:inquilino` só para dono `admin` (`422
escopo_fora_do_teto`); `<uuid>` tem de existir e ser legível pelo dono no momento da criação (L0-03 valida; neste
item, sem catálogo, o backend valida só o formato e a lista de escopos sem `<uuid>`). `app/auth/escopos.py` expõe
`exigir_escopo(sessao, "camada:ler", uuid)` que as linhas futuras chamam: escopo insuficiente = `403
{"erro": "escopo_insuficiente", "detalhe": {"exigido": "camada:ler:<uuid>", "token_tem": [...]}}`. Neste item o
teste de escopo usa rotas que já existem: `catalogo:ler` → `GET /api/eu` 200, `GET /api/usuarios` 403,
`POST /api/grupos` 403; `admin:inquilino` de admin → `GET /api/usuarios` 200.

### 8.3 Restrições (`restricao jsonb`, 002)

`{"referer": ["https://*.exemplo.gov.br", "https://sig.exemplo.gov.br:8443"], "ip": ["10.0.0.0/8", "203.0.113.7"]}`.
Referer: compara a ORIGEM (esquema + host + porta) do cabeçalho `Origin`, ou, na falta, `Referer` (a Esri anota que
navegadores modernos mandam só a origem, E12-limitusage); `*.` casa só subdomínios (`https://exemplo.gov.br` não casa
`https://*.exemplo.gov.br`, cláusula do L0-02-d); lista não vazia e cabeçalho ausente = `401 referer_ausente`. IP:
`ipaddress` da biblioteca padrão; o IP é `request.client.host` (uvicorn com `--proxy-headers` e
`--forwarded-allow-ips 127.0.0.1`, isto é, o `X-Forwarded-For` que o nginx local escreve). `401 ip_nao_permitido`.
Limites: 20 entradas em cada lista.

### 8.4 Latência

`auth_token` = 1 sha256 (0,0012 ms) + 1 `UPDATE ... RETURNING` com JOIN em `usuario` e `tenant` por índice único;
alvo do portão: mediana < 5 ms medida no TestClient (`tests/medidas/L0-02-tenant-auth.json`,
`latencia_auth_token_ms`). A escrita de `ultimo_uso`/`ultimo_ip` a cada uso é aceita (uma linha, índice único); se
o L7-02 medir contenção, vira escrita a cada 60 s.

---

## 9. Log de acesso e eventos

### 9.1 O que se grava em `plat.log_acesso` (uma linha por requisição autenticada ou de autenticação)

| coluna | conteúdo | origem |
|---|---|---|
| `em` | instante do fim da resposta (UTC) | middleware |
| `tenant_id`, `usuario_id`, `token_id` | resolvidos pela sessão ou pelo token; `token_id` NULL sob cookie; NULL/NULL/NULL para login com inquilino inexistente | `auth_sessao` / `auth_token` |
| `ip` | `request.client.host` (já é o IP real: `--proxy-headers` + nginx local) | uvicorn |
| `metodo`, `rota` | método; caminho + query com os parâmetros `token`, `senha`, `codigo`, `desafio` substituídos por `<redigido>`; `left(..., 500)` | `app/auth/redigir.py` |
| `status` | HTTP da resposta | middleware |
| `bytes` | bytes do CORPO enviado, contados ao envolver `body_iterator` (vale para resposta em fluxo, que não tem `Content-Length`) | middleware |
| `tempo_ms` | do início do middleware ao último byte | middleware |
| `agente` | `left(User-Agent, 200)` | cabeçalho |
| `resultado` | login: `ok | senha | bloqueado | totp | recuperacao | inexistente | externo | suspenso | desafio_expirado`; logout: `logout`; token: `revogado | expirado | escopo | referer | ip | pendencia`; demais: NULL | rota |

Rotas que NÃO geram linha (ruído do driver a cada 30 min e estático): `/saude`, `/api/versao`, `/`, `/api/docs`,
`/api/openapi.json`, `/static/*` (nem passa pela API). Tudo em `/api/`, `/svc/`, `/ogc/`, `/tiles/` gera, inclusive
401/403/404: é assim que "token de serviço aparece no log com IP/rota/bytes" (portão) e que uma varredura com token
alheio fica visível ao admin.

Escrita: `plat.log_registrar(...)` `SECURITY DEFINER` (única com INSERT; `plat_app` não tem INSERT/UPDATE/DELETE na
tabela, já na 002), chamada numa `BackgroundTask` do Starlette DEPOIS de o corpo ser enviado, com conexão própria
do pool sem contexto de inquilino (a função recebe `p_tenant` e confere `p_tenant IS NULL OR p_tenant =
plat.tenant_atual() OR plat.tenant_atual() IS NULL`; sem contexto ela aceita o `p_tenant` que a API resolveu, porque
a resolução veio de `auth_sessao`/`auth_token` na mesma requisição). Custo por requisição (1 INSERT local) é medido
pelo testador como diferença entre `GET /api/eu` com e sem log (`custo_log_acesso_ms`); se a mediana passar de 2 ms,
o L7-02 troca por lote de 100 linhas em memória com descarga a cada 1 s, sem mudar a tabela.

### 9.2 Retenção e forma física

A 002 criou `log_acesso` sem partição. MEDIDO: 0 linhas. A 003 a recria PARTICIONADA POR MÊS (`PARTITION BY RANGE
(em)`, chave primária `(id, em)`, mesmos índices por partição), com guarda de idempotência (`relkind = 'p'` já?
então não faz nada). Motivo: retenção de 12 meses (spec 17.4; conceito D14) por `DROP TABLE` da partição de 13 meses
atrás é instantânea e não deixa espaço morto; `DELETE` de milhões de linhas em disco a 98 % é o que se evita. Volume
esperado: 1 linha por requisição; 10 usuários × 1.000 requisições/dia = 300 mil/mês ≈ 60 MB/mês com índices
(estimativa a confirmar pelo testador com `pg_total_relation_size` após o e2e). Funções da 003:
`plat.log_particao_garantir(p_mes date)` (cria `log_acesso_yYYYYmMM` se não existir; a 003 cria o mês corrente e o
seguinte) e `plat.log_expurgar(p_meses int DEFAULT 12)` (derruba partições anteriores; `SECURITY DEFINER`, só
`plat_app`, chamada pelo periódico do L0-05-d e pela CLI). A criação da partição do mês seguinte é a mesma
chamada, agendada mensalmente pelo L0-05-d; até o L0-05-d existir, a 003 cria 3 meses à frente e o `install.sh`
chama `plat.log_particao_garantir` a cada execução (o driver reinstala com frequência). `pg_cron` existe na máquina
e não é usado: o produto tem de instalar em máquina sem ele (L7-11).

### 9.3 Consulta

- Tela "Log" (seção 15.6) e `GET /api/log` (`org.log_ver`): filtros `usuario_id`, `token_id`, `rota` (prefixo),
  `status` (código ou classe `4xx`), `desde`/`ate` (ISO 8601; padrão últimos 7 dias; janela máxima 92 dias por
  consulta), `limite ≤ 1000`, `deslocamento`; resposta `{total, itens:[...]}`; `formato=csv` devolve `text/csv`
  com as mesmas colunas (até 100 mil linhas; acima disso é job do L0-05). Índices da 002 (`tenant_id, em DESC` e
  `token_id, em DESC`) cobrem os dois filtros principais. `GET /api/tokens/{id}/log` é o mesmo com `token_id` fixo e
  serve à tela Tokens ("últimos acessos deste token").
- O superadmin consulta por inquilino no console (L0-07-f), com a mesma rota e `X-Plat-Inquilino` (seção 10).
- Retenção declarada na tela: "12 meses; exporte antes".

### 9.4 Eventos de domínio (`plat.evento`, criada aqui porque o L0-02 já os gera; tela e webhooks no L0-10/L7-08)

```
plat.evento (id bigserial, em timestamptz, tenant_id int, ator_id int, tipo text, alvo_tipo text, alvo_id text,
             propriedades jsonb, ip text, req_id text, PRIMARY KEY (id, em)) PARTITION BY RANGE (em)
```

Append-only: RLS `FOR SELECT` por inquilino; INSERT só por `plat.evento_registrar(p_tipo, p_alvo_tipo, p_alvo_id,
p_propriedades, p_ip, p_req_id)` `SECURITY DEFINER` que usa `plat.tenant_atual()`/`usuario_atual()` (exige contexto:
sem contexto, exceção; é o oposto do `log_registrar`, que precisa gravar antes de haver contexto); `plat_app` sem
UPDATE/DELETE. Vocabulário (D14, espelho dos gatilhos de webhook da Esri) que ESTE item usa e a 003 registra em
`plat.evento_tipo (nome PK, descricao)`: `usuarios/entrar`, `usuarios/sair`, `usuarios/falha_login` (só a que
bloqueia), `usuarios/criar`, `usuarios/atualizar`, `usuarios/desabilitar`, `usuarios/reabilitar`, `usuarios/apagar`,
`usuarios/papel`, `usuarios/redefinir_senha`, `usuarios/trocar_senha`, `usuarios/2fa_ligar`, `usuarios/2fa_desligar`,
`usuarios/desbloquear`, `papeis/criar`, `papeis/atualizar`, `papeis/apagar`, `grupos/criar`, `grupos/atualizar`,
`grupos/apagar`, `grupos/transferir`, `grupos/convidar`, `grupos/pedir`, `grupos/aprovar`, `grupos/entrar`,
`grupos/sair`, `grupos/remover`, `grupos/papel`, `tokens/criar`, `tokens/renovar`, `tokens/revogar`,
`sessoes/revogar`, `inquilinos/criar`, `inquilinos/suspender`, `inquilinos/reativar`. Tipo fora do registro =
exceção (FK). Retenção e partição: idênticas ao `log_acesso` (`plat.evento_particao_garantir`, `evento_expurgar`).
`propriedades` nunca carrega senha, token, segredo ou código; carrega o "antes/depois" de perfil, papel e `ativo`.

Teste (herdado do L0-10, já aplicável): toda rota de escrita deste item tem o evento correspondente registrado em
`tests/api/eventos_esperados.py`; rota de escrita no OpenAPI sem entrada = falha.

---

## 10. Super-admin da plataforma

Problema: RLS exige `usuario.tenant_id NOT NULL`; "fora de inquilino" não pode ser `tenant_id NULL` sem furar toda
política. A 002 semeia `superadmin = true` no admin de `demo` (linha do `install.sh`, passo g), o que mistura operador
da plataforma com cliente de demonstração.

Decisão (D20: "superadmin fora de inquilino"): o inquilino técnico reservado **`plataforma`** (slug reservado,
`ativo` sempre `true`, sem conteúdo, sem cota, não aparece nas listas de cliente) é o único que pode ter usuários com
`superadmin = true` (gatilho `plat.usuario_superadmin_so_plataforma`). Os operadores são usuários normais desse
inquilino: mesma tela de login (`/entrar?inquilino=plataforma`), mesma política de senha, 2FA OBRIGATÓRIO (o
`config.auth.exigir_2fa` de `plataforma` nasce `true` na 003 e não se desliga: `org.configurar` não vale nesse
inquilino), mesmas sessões, mesmo log. O `install.sh` passa a semear `plataforma/admin` (senha em
`tests/credenciais.txt`, por stdin como hoje) e os admins de `demo`/`demo2` nascem com `superadmin = false`.

Como o superadmin age sobre outros inquilinos, sem nunca "entrar como" ninguém:

- Funções `SECURITY DEFINER` `plat.plataforma_*` recebem `p_sessao_hash` (o sha256 do cookie, que só a API tem) e
  fazem `SELECT ... FROM plat.sessao s JOIN plat.usuario u ... WHERE s.token_hash = p_sessao_hash AND u.superadmin
  AND u.ativo AND s válida`; se não achar, exceção. Nunca decidem por `current_setting('plat.usuario_id')` (achado do
  T1: GUC forjável por quem tem o DSN). A 003 reescreve `tenant_criar` nesse formato e acrescenta `tenant_listar`,
  `tenant_suspender(id, boolean)`.
- Rotas `/api/plataforma/*` respondem `404` (não 403) para quem não é superadmin (não confirmam que existem;
  cláusula do L0-07-f). Neste item: `GET/POST /api/plataforma/inquilinos`, `POST .../{id}/suspender`,
  `POST .../{id}/reativar`. Console com tela é o L0-07-f.
- Leitura de dado de um inquilino pelo superadmin (log, usuários) sem sessão nele: cabeçalho `X-Plat-Inquilino:
  <slug>` aceito SÓ em rotas marcadas `superadmin_pode_ler` (neste item `GET /api/log`, `GET /api/usuarios`); a API
  valida o superadmin pela sessão, resolve o `tenant_id` por `plat.plataforma_tenant_id(p_sessao_hash, p_slug)` e
  abre o contexto desse inquilino SÓ para leitura (a conexão recebe `SET LOCAL default_transaction_read_only = on`).
  Cada uso gera evento `inquilinos/leitura_superadmin` no inquilino lido, com o login do operador em `propriedades`
  (o L0-07-f exige "nunca sem trilha"). Escrita em nome de inquilino: não existe; o superadmin cria o admin inicial
  e o admin faz o resto. Custo de mudar (permitir "assumir"): uma função e um evento; nada de esquema.
- Cria inquilino: `POST /api/plataforma/inquilinos {slug, nome, config, admin_login, admin_nome}` → `201 {id,
  senha_temporaria}` (mostrada uma vez; `trocar_senha = true` no admin criado). `409 slug_existente`, `409
  slug_reservado`, `422` pelo CHECK do slug.
- Superadmin não é membro de nenhum grupo de cliente, não cria token com `admin:inquilino` sobre inquilino alheio
  (não há escopo cruzado; a CLI do L0-14 usa o `.env` e as funções `plataforma_*`, nunca token).

---

## 11. Configuração por inquilino (`tenant.config.auth`, validada por JSON Schema em `app/auth/politica.py`)

| chave | padrão | faixa | usada em |
|---|---|---|---|
| `senha_min` | 10 | 8–64 | 6.1 |
| `senha_maiuscula`, `senha_minuscula`, `senha_simbolo` | false | boolean | 6.1 |
| `senha_historico` | 5 | 0–24 | 6.1 |
| `senha_expira_dias` | 0 | 0 ou 30–365 | 6.1 |
| `bloqueio_tentativas` | 5 | 3–10 | 6.2 |
| `bloqueio_minutos` | 15 | 5–60 | 6.2 |
| `sessao_ociosa_horas` | 12 | 1–24 | 5.1 |
| `sessao_max_dias` | 7 | 1–30 | 5.1 |
| `exigir_2fa` | false (`plataforma`: true, fixo) | boolean | 5.4, 7.3 |
| `token_max_dias` | 365 | 1–365 | 8.1 |
| `token_padrao_dias` | 90 | 1–`token_max_dias` | 8.1 |
| `dominios_email` | `[]` (qualquer) | ≤ 20 domínios | 2.2, tela Usuários: e-mail fora da lista = `422 email_dominio` |
| `compartilhar_publico` | false | boolean (D24 pendente) | 4.3, L0-03-e |

Valor ausente = padrão; valor fora da faixa = `422` na rota que grava (`PUT /api/inquilino/config`, L0-07-a) e, se
já estiver no banco por outro caminho, a leitura CORTA para a faixa e grava aviso no journal (nunca deixa a política
mais fraca que o piso: `senha_min = 4` no banco vale 8, e sem a chave vale o padrão 10). `app/limites.py` guarda padrões e faixas; `docs/LIMITES.md`
(L0-12) é gerado dali.

---

## 12. Migração `003_identidade_acesso.sql` (normativa; idempotente; sem BEGIN/COMMIT; aplicada como postgres)

Ordem e conteúdo. Cada bloco tem guarda de idempotência (`IF NOT EXISTS`, `CREATE OR REPLACE`, `DO $$ ... IF NOT
EXISTS`, `ON CONFLICT DO NOTHING`).

```sql
-- 12.1 privilégios e perfis
CREATE TABLE IF NOT EXISTS plat.privilegio (
  nome text PRIMARY KEY CHECK (nome ~ '^[a-z]+\.[a-z_]+$'),
  grupo text NOT NULL, descricao text NOT NULL, administrativo boolean NOT NULL DEFAULT false);
CREATE TABLE IF NOT EXISTS plat.perfil_privilegio (
  perfil text NOT NULL CHECK (perfil IN ('admin','editor','visualizador','campo')),
  privilegio text NOT NULL REFERENCES plat.privilegio(nome), PRIMARY KEY (perfil, privilegio));
INSERT INTO plat.privilegio VALUES ('membros.ver','membros','ver nome, login, perfil e último acesso',false), ...  -- 46 linhas da seção 3.2
ON CONFLICT (nome) DO UPDATE SET grupo = EXCLUDED.grupo, descricao = EXCLUDED.descricao, administrativo = EXCLUDED.administrativo;
INSERT INTO plat.perfil_privilegio ... ON CONFLICT DO NOTHING;                  -- tetos da seção 3.2 (V, C, E, A)
-- sem RLS: são tabelas de vocabulário da plataforma; plat_app só lê (REVOKE INSERT/UPDATE/DELETE)

-- 12.2 papéis personalizados
CREATE TABLE IF NOT EXISTS plat.papel_personalizado (
  id serial PRIMARY KEY, tenant_id int NOT NULL REFERENCES plat.tenant(id),
  nome text NOT NULL CHECK (length(nome) BETWEEN 1 AND 128), descricao text CHECK (length(descricao) <= 250),
  perfil_minimo text NOT NULL CHECK (perfil_minimo IN ('admin','editor','visualizador','campo')),
  criado_por int REFERENCES plat.usuario(id), criado_em timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS ux_papel_tenant_nome ON plat.papel_personalizado (tenant_id, lower(nome));
CREATE TABLE IF NOT EXISTS plat.papel_privilegio (
  papel_id int NOT NULL REFERENCES plat.papel_personalizado(id) ON DELETE CASCADE,
  privilegio text NOT NULL REFERENCES plat.privilegio(nome), PRIMARY KEY (papel_id, privilegio));
-- RLS: papel_personalizado por tenant_id; papel_privilegio por EXISTS (papel do inquilino)

-- 12.3 usuario: colunas novas (ALTER ... ADD COLUMN IF NOT EXISTS), senha_hash nullable + CHECK, papel_id FK,
--      UNIQUE parcial (tenant_id, origem, sujeito_externo) WHERE sujeito_externo IS NOT NULL
-- 12.4 senha_historico (usuario_id, senha_hash, criado_em; índice por usuario_id, criado_em DESC); RLS via usuario
-- 12.5 grupo, grupo_membro (seção 4.1) com RLS de leitura por visibilidade e de escrita por tenant_id
-- 12.6 gatilhos: usuario_ultimo_admin (BEFORE UPDATE/DELETE), usuario_superadmin_so_plataforma (BEFORE INSERT/UPDATE),
--      grupo_dono_coerente (AFTER INSERT/UPDATE em grupo e grupo_membro)
-- 12.7 evento_tipo + evento particionada + evento_registrar + evento_particao_garantir + evento_expurgar (seção 9.4)
-- 12.8 log_acesso: se relkind <> 'p' → DROP e CREATE particionada (0 linhas medidas); log_particao_garantir; log_expurgar
-- 12.9 inquilino técnico 'plataforma' (INSERT ... ON CONFLICT DO NOTHING) com config.auth.exigir_2fa = true
-- 12.10 funções de privilégio: privilegios_de(int) text[], tem(text) boolean  (SQL STABLE, sem SECURITY DEFINER)
```

Funções `SECURITY DEFINER` reescritas (todas `SET search_path = plat, public`; `CREATE OR REPLACE` mantém o nome
onde a assinatura não muda; quando muda, `DROP FUNCTION IF EXISTS` da antiga na mesma migração):

| função | mudança | checagem de inquilino |
|---|---|---|
| `auth_login(p_tenant, p_login)` | deixa de devolver `totp_secret`; devolve `origem`, `trocar_senha`, `ativo_tenant` | pré-contexto por natureza (resolve o inquilino a partir do slug); só devolve o que o login precisa; o `senha_hash` continua saindo (o pbkdf2 é conferido em Python) |
| `auth_falha(p_usuario, p_max, p_min, p_janela_min)` | ganha janela (`falhas_desde`) | `RAISE` se `plat.tenant_atual() IS DISTINCT FROM (SELECT tenant_id FROM usuario WHERE id = p_usuario)`; a rota de login abre o contexto do inquilino resolvido por `auth_login` ANTES de chamar |
| `auth_ok(p_usuario, p_ip)` | grava `ultimo_ip` | idem |
| `auth_sessao_criar(p_usuario, p_max_dias, p_ip, p_agente)` | validade em dias | idem (o ataque 4 do T1 deixa de funcionar: contexto de `demo` + usuário de `demo2` = exceção) |
| `auth_sessao(p_hash, p_ociosa_horas)` | valida ocioso + absoluto; devolve `privilegios`, `trocar_senha`, `totp_ativo`, `superadmin`, `origem`, `expira_em`, `ultimo_uso` | pré-contexto (o hash é o segredo); não escreve nada além de `ultimo_uso` |
| `auth_sessao_encerrar(p_hash)` | igual | pré-contexto |
| `sessoes_encerrar_usuario(p_usuario, p_exceto_hash)` | nova | contexto obrigatório = inquilino do usuário |
| `auth_token(p_hash, p_ip)` | devolve também `privilegios` do dono, `trocar_senha`, `expira_em`, `revogado_em` (para o 401 com motivo), `renovado_por` | pré-contexto |
| `auth_desafio_2fa_*` | nova: `criar(p_usuario)`, `resolver(p_hash)` | contexto obrigatório (criar); pré-contexto (resolver, o hash é o segredo) |
| `log_registrar(...)` | igual | `p_tenant IS NULL OR plat.tenant_atual() IS NULL OR p_tenant = plat.tenant_atual()`; se houver contexto, tem de casar |
| `evento_registrar(...)` | nova | contexto obrigatório; `tenant_id`/`ator_id` vêm do contexto, nunca de parâmetro |
| `tenant_criar(p_sessao_hash, p_slug, p_nome, p_config, p_admin_login, p_admin_nome, p_senha_hash)` | superadmin resolvido pela sessão; recusa slug reservado | nunca por GUC |
| `tenant_listar(p_sessao_hash)`, `tenant_suspender(p_sessao_hash, p_id, p_ativo)`, `plataforma_tenant_id(p_sessao_hash, p_slug)` | novas | idem; `plataforma` não se suspende |
| `log_expurgar`, `evento_expurgar`, `log_particao_garantir`, `evento_particao_garantir`, `sessoes_expurgar` | novas | sem inquilino (operação da plataforma); `EXECUTE` só `plat_app`; chamadas pela CLI e pelo periódico |

Permissões (o núcleo do achado do T1):

```sql
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA plat FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app;          -- inclui tenant_atual/usuario_atual/tem (RLS as chama como plat_app)
```

Prova (teste `tests/api/test_funcoes_seguras.py`, roda como `plat_app`): `SELECT proname FROM pg_proc WHERE pronamespace
= 'plat'::regnamespace AND proacl::text LIKE '%=X/%'` = 0 linhas; `auth_sessao_criar(usuario_de_demo2)` no contexto de
`demo` = exceção; `auth_falha` idem; `tenant_criar` com `set_config('plat.usuario_id','1')` e hash de sessão de não
superadmin = exceção; `evento_registrar` sem contexto = exceção; `plat_app` sem INSERT em `evento` e `log_acesso`.

O que a 003 NÃO faz: não altera `sessao.token_hash`, `token_servico`, `tenant` (só dado); não cria tabela de item,
compartilhamento nem provedor de SSO; não instala extensão.

Custo de reverter: as funções voltam pela 002 (`CREATE OR REPLACE` de novo em `004`); as tabelas novas caem com
`DROP`; `log_acesso` particionada não volta a plana sem cópia (aceito: 0 linhas hoje).

---

## 13. Gancho para SSO (L0-08), sem implementar

O que este item deixa pronto: `usuario.origem` e `usuario.sujeito_externo` (seção 2.2); `auth_login` devolve
`origem` e a rota de login responde `403 {"erro": "login_externo", "mensagem": "esta conta entra pelo login da
organização"}` para `origem <> 'local'`; senha, histórico, bloqueio e 2FA só se aplicam a `local` (paridade
E12-security e E12-profile: "o portal não reseta senha de login da organização", "MFA só para built-in"); `auth_sessao_criar`
não depende de senha (o L0-08 cria a sessão pelo mesmo caminho depois de validar o `id_token`/asserção); a tela de
login já tem o lugar dos botões de provedor (seção 15.1, lidos de `GET /api/login/provedores?inquilino=`, que neste
item devolve `{"provedores": []}` de verdade, sem dado fixo); `grupo` ganha no L0-08-e a coluna `grupo_externo` para o
mapeamento por atributo. O que fica para o L0-08: `plat.provedor_login` (por inquilino: tipo, issuer, client_id,
segredo cifrado como o TOTP, metadado SAML, claim de grupos, regras de provisionamento), rotas
`/api/sso/{oidc,saml}/...`, `usuario.origem` passando a aceitar os valores já previstos no CHECK. Custo de ter
decidido agora: duas colunas e um CHECK; custo de não ter decidido: `senha_hash NOT NULL` obrigaria a inventar senha
para conta federada.

---

## 14. Contrato de API

Regras gerais (D18, adiantadas do L0-12 porque este item é o primeiro com rotas de produto; `app/erros.py` é deste
item e o L0-05 o importa): toda resposta de erro é `{"erro": "<codigo_curto>", "mensagem": "<frase em português>",
"detalhe": <opcional>, "req_id": "<16 hex>"}`; códigos usados aqui: 400 (pedido inválido/validade acima do máximo),
401 (sem sessão, sessão expirada, credencial inválida, token inválido/expirado/revogado/restrito), 403 (sem
privilégio, pendência, origem inválida, escopo insuficiente, só sessão), 404 (recurso inexistente OU de outro
inquilino OU rota de superadmin para não superadmin), 409 (conflito de regra: último admin, papel em uso, grupo
protegido/administrativo, já ativo, login externo, slug), 410 (desafio expirado), 415 (corpo não JSON em escrita sob
cookie), 422 (validação de esquema, senha fraca, privilégio fora do teto, e-mail fora do domínio), 423 (bloqueado),
429 (nginx), 503 (inquilino suspenso no login; banco fora). `RequestValidationError` do FastAPI vira 422 no mesmo
formato (`detalhe` = lista do pydantic). Paginação `limite` (padrão 50, máximo 1000) e `deslocamento`, resposta
`{"total": n, "itens": [...]}`. Datas ISO 8601 UTC com `Z`. IDs: `int` para usuário/papel/token/sessão (chaves
internas, nunca expostas fora do inquilino), UUID para grupo. Português nos campos. Autenticação: cookie
`plat_sessao` OU `Authorization: Bearer`; nunca os dois ao mesmo tempo (`400 autenticacao_ambigua`).

Objeto `usuario` (o que `/api/eu` e `/api/usuarios/{id}` devolvem; `membros.ver` vê só os campos marcados V):

```
{ "id": 7 V, "login": "maria" V, "nome": "Maria" V, "email": "m@org.gov.br", "perfil": "editor" V,
  "papel": {"id": 3, "nome": "Curador"} | null V, "privilegios": ["..."] (só em /api/eu), "superadmin": false,
  "ativo": true V, "origem": "local" V, "totp_ativo": true, "trocar_senha": false, "bloqueado_ate": null,
  "ultimo_login": "2026-09-05T13:00:00Z" V, "ultimo_ip": "203.0.113.7", "criado_em": "..." V,
  "inquilino": {"slug": "demo", "nome": "Inquilino de demonstração", "config_publica": {"centro": [...], "zoom": 4}} (só em /api/eu),
  "pendencias": [] (só em /api/eu), "sessao": {"criado_em", "expira_em", "ociosa_ate", "ip"} (só em /api/eu sob cookie),
  "token": {"id", "nome", "escopos", "expira_em"} (só em /api/eu sob Bearer) }
```

Tabela de rotas (M = método; auth: `-` público, `S` sessão, `T` token, `S/T` ambos; privilégio; corpo; sucesso; erros
além dos gerais). Todas em `/api/`.

| M | rota | auth | privilégio | corpo | sucesso | erros específicos |
|---|---|---|---|---|---|---|
| GET | `/login/provedores?inquilino=` | - | | | `200 {"inquilino": {"slug","nome"}, "provedores": [], "login_local": true}` | `404 inquilino_inexistente` |
| POST | `/login` | - | | `{inquilino, login, senha}` | `200 {ok:true, usuario}` + cookie · `200 {ok:false, exige_2fa:true, desafio, recuperacao_disponivel}` | `401 credenciais_invalidas` · `423 bloqueado` · `403 login_externo` · `503 inquilino_suspenso` · `429` |
| POST | `/login/2fa` | - | | `{desafio, codigo}` ou `{desafio, codigo_recuperacao}` | `200 {ok:true, usuario}` + cookie | `401 codigo_invalido` · `410 desafio_expirado` · `423 bloqueado` · `429` |
| POST | `/logout` | S | | | `204` + cookie apagado | (sem sessão: `204` também; idempotente) |
| GET | `/eu` | S/T | | | `200 usuario` (completo) | |
| PUT | `/eu` | S | | `{nome?, email?}` (qualquer outra chave = `400 campo_nao_editavel`) | `200 usuario` | `422 email_dominio` |
| PUT | `/eu/senha` | S | | `{atual, nova}` | `204` | `401 senha_atual_incorreta` · `422 senha_fraca` · `409 login_externo` |
| GET | `/eu/sessoes` | S | | | `200 [{id, criado_em, ultimo_uso, expira_em, ip, agente, atual}]` | |
| DELETE | `/eu/sessoes/{id}` · `/eu/sessoes?outras=1` | S | | | `204` | `404` |
| POST | `/eu/2fa/iniciar` | S | | | `200 {segredo, uri, qr_svg}` | `409 ja_ativo` · `409 login_externo` |
| POST | `/eu/2fa/confirmar` | S | | `{codigo}` | `200 {codigos_recuperacao: [8]}` | `401 codigo_invalido` · `409 nao_iniciado` |
| POST | `/eu/2fa/desativar` | S | | `{senha, codigo}` | `204` | `401` · `409 2fa_obrigatorio` |
| POST | `/eu/2fa/codigos` | S | | `{senha}` | `200 {codigos_recuperacao}` | `401` · `409 nao_ativo` |
| GET | `/eu/convites` | S | | | `200 [{grupo:{id,nome}, papel, convidado_por, criado_em}]` | |
| GET | `/privilegios` | S/T | | | `200 [{nome, grupo, descricao, administrativo}]` | |
| GET | `/papeis` | S/T | | | `200 {perfis: [{perfil, privilegios}], personalizados: [{id, nome, descricao, perfil_minimo, privilegios, usuarios}]}` | |
| POST | `/papeis` | S/T | `papeis.gerir` | `{nome, descricao?, privilegios[]}` (perfil_minimo calculado) | `201 papel` | `422 privilegio_fora_do_teto` · `403 privilegio_proprio_insuficiente` · `409 nome_existente` |
| PUT | `/papeis/{id}` | S/T | `papeis.gerir` | idem | `200 papel` | idem · `404` |
| DELETE | `/papeis/{id}` | S/T | `papeis.gerir` | | `204` | `409 papel_em_uso` · `404` |
| GET | `/usuarios?perfil&ativo&q&limite&deslocamento&ordenar` | S/T | `membros.ver` (campos V) · `membros.ver_tudo` (todos) | | `200 {total, itens}` | |
| POST | `/usuarios` | S/T | `membros.gerir` (+ `membros.papel` se `perfil≠visualizador` ou `papel_id` informado — T3) | `{login, nome, email?, perfil, papel_id?}` | `201 {usuario, senha_temporaria}` | `409 login_existente` · `422 email_dominio` · `422 papel_incompativel` · `403 so_admin_cria_admin` · `403 sem_privilegio` |
| GET | `/usuarios/{id}` | S/T | `membros.ver` | | `200 usuario` | `404` |
| PUT | `/usuarios/{id}` | S/T | `membros.gerir` (nome, email, ativo) · `membros.papel` (perfil, papel_id) | `{nome?, email?, perfil?, papel_id?, ativo?}` | `200 usuario` | `409 ultimo_admin` · `403 so_admin_altera_admin` · `409 possui_grupos` (rebaixar) · `409 possui_itens {detalhe: [{id,titulo}]}` (rebaixar; item L0-07-b, T3 — regra Esri E12-members: só rebaixa quem "não possui conteúdo nem grupos") · `422` |
| POST | `/usuarios/{id}/senha` | S/T | `membros.gerir` | | `200 {senha_temporaria}` | `403 so_admin_altera_admin` · `409 login_externo` |
| POST | `/usuarios/{id}/2fa/desativar` | S/T | `membros.gerir` | | `204` | idem |
| POST | `/usuarios/{id}/desbloquear` | S/T | `membros.gerir` | | `204` | |
| DELETE | `/usuarios/{id}` | S/T | `membros.apagar` | | `204` | `409 ultimo_admin` · `409 possui_grupos {detalhe: [{id,nome}]}` · `409 possui_itens {detalhe: [{id,titulo}]}` (T3, `plat.item.dono_id` é FK sem `ON DELETE`) · `403 so_admin_apaga_admin` · `409 proprio_usuario` |
| POST | `/usuarios/lote` | S/T | `membros.gerir` / `membros.papel` | `{ids[≤100], acao: "perfil"\|"papel"\|"desabilitar"\|"reabilitar", perfil?, papel_id?}` | `200 {alterados: n, recusados: [{id, erro}]}` | `422 lote_acima_de_100` |
| GET | `/grupos?meus&q&limite&deslocamento` | S/T | (RLS de visibilidade) | | `200 {total, itens: [{id, nome, resumo, tags, visibilidade, entrada, contribuicao, atualizacao_compartilhada, administrativo, protegido, dono: {id,nome}, membros: n, meu_papel, meu_estado}]}` | |
| POST | `/grupos` | S/T | `grupos.criar` (+ `grupos.atualizacao_compartilhada` / `grupos.administrativo` conforme flags) | `{nome, resumo?, tags?, visibilidade, entrada, contribuicao, atualizacao_compartilhada?, administrativo?, protegido?}` | `201 grupo` | `409 nome_existente` · `422 atualizacao_exige_convite_ou_pedido` · `422 limite_grupos` |
| GET | `/grupos/{id}` | S/T | visível | | `200 grupo` | `404` |
| PUT | `/grupos/{id}` | S/T | dono/gerente ou `grupos.gerir_todos`; `dono_id` só dono | campos editáveis (4.2) | `200 grupo` | `409 atualizacao_so_na_criacao` · `422 novo_dono_nao_membro` · `404` |
| DELETE | `/grupos/{id}` | S/T | dono ou `grupos.gerir_todos` | | `204` | `409 grupo_protegido` · `404` |
| GET | `/grupos/{id}/membros` | S/T | membro ativo ou `grupos.gerir_todos` | | `200 [{usuario: {id, nome, login}, papel, estado, criado_em}]` | `404` |
| POST | `/grupos/{id}/membros` | S/T | dono/gerente | `{usuario_id, papel?}` (convite) | `201 {estado: "convidado"}` | `409 ja_membro` · `404 usuario_inexistente` (mesmo inquilino, RLS) |
| POST | `/grupos/{id}/entrar` | S/T | `grupos.entrar` | | `200 {estado: "ativo"}` (livre) · `202 {estado: "pedido"}` (pedido) | `403 entrada_por_convite` |
| POST | `/grupos/{id}/aceitar` · `/recusar` | S/T | convidado | | `200 {estado}` · `204` | `404 sem_convite` |
| POST | `/grupos/{id}/membros/{uid}/aprovar` | S/T | dono/gerente | | `200 {estado: "ativo"}` | `404 sem_pedido` |
| PUT | `/grupos/{id}/membros/{uid}` | S/T | dono/gerente (o gerente pode promover a gerente: a Esri deixa o manager gerir membros; `dono` só pelo `PUT /grupos/{id}`) | `{papel: "gerente"\|"membro"}` | `200` | `409 papel_dono_via_grupo` |
| DELETE | `/grupos/{id}/membros/{uid}` | S/T | o próprio (sair) ou dono/gerente (remover) | | `204` | `409 grupo_administrativo` (sair) · `409 dono_nao_sai` |
| GET | `/tokens?todos` | S | `tokens.gerar` · `todos=1` exige `tokens.gerir_todos` | | `200 [{id, nome, prefixo, escopos, restricao, criado_em, expira_em, revogado_em, ultimo_uso, ultimo_ip, dono: {id, login}, renovado_por}]` | |
| POST | `/tokens` | S | `tokens.gerar` | `{nome, escopos[], restricao?, validade_dias?}` | `201 {token (única vez), id, prefixo, escopos, expira_em}` | `400 validade_acima_do_maximo` · `422 escopo_invalido` · `422 escopo_fora_do_teto` · `422 limite_tokens` |
| GET | `/tokens/{id}` | S | dono ou `tokens.gerir_todos` | | `200 token + {acessos_30d, ultimo_status}` | `404` |
| POST | `/tokens/{id}/renovar` | S | dono | | `201 {token, id, expira_em, antigo_expira_em}` | `409 token_revogado` |
| DELETE | `/tokens/{id}` | S | dono ou `tokens.gerir_todos` | | `204` | `404` |
| GET | `/tokens/{id}/log?desde&ate&limite&deslocamento` | S | dono ou `tokens.gerir_todos` | | `200 {total, itens: [linha do log]}` | |
| GET | `/log?usuario_id&token_id&rota&status&desde&ate&limite&deslocamento&formato` | S/T | `org.log_ver` (superadmin com `X-Plat-Inquilino`) | | `200 {total, itens}` · `text/csv` | `422 janela_maior_que_92_dias` |
| GET | `/eventos?tipo&ator_id&desde&ate&limite&deslocamento` | S/T | `org.log_ver` | | `200 {total, itens: [{id, em, tipo, ator: {id, login}, alvo_tipo, alvo_id, propriedades, ip, req_id}]}` | |
| GET | `/plataforma/inquilinos` | S | superadmin | | `200 [{id, slug, nome, ativo, usuarios, criado_em, ultimo_acesso}]` | `404` (não superadmin) |
| POST | `/plataforma/inquilinos` | S | superadmin | `{slug, nome, config?, admin_login, admin_nome}` | `201 {id, slug, admin: {id, login}, senha_temporaria}` | `409 slug_existente` · `409 slug_reservado` · `422` · `404` |
| POST | `/plataforma/inquilinos/{id}/suspender` · `/reativar` | S | superadmin | | `204` | `409 plataforma_nao_suspende` · `404` |

Cabeçalhos: toda resposta da API leva `X-Req-Id` (já existe) e `Cache-Control` — **alterado em T2**: a origem é a APLICAÇÃO, não o nginx (piso `no-store, must-revalidate` no middleware, a rota que quiser outro valor declara o seu; motivo e medição no ADR 0001). Rotas de escrita
sob cookie exigem `Content-Type: application/json` (`415`). `OPTIONS`/CORS: fora deste item (L0-12: lista por
inquilino); hoje só mesma origem.

`docs/openapi.json` regenerado por `make openapi` e comitado; o teste cruzado (seção 16.1) lê esse arquivo. Toda
rota tem `response_model` (pydantic) para o OpenAPI carregar o esquema de resposta; `RequestValidationError` no
formato da seção 14.

---

## 15. Telas mínimas (wireframe em texto; estilo = `web/style.css` existente: fundo escuro, IBM Plex, painel)

Servidas pela API a partir de `web/` (mesma forma do `inicio()` em `main.py`, `Cache-Control: no-store`), registradas
em `app/paginas.py` (`PAGINAS = {"/entrar": "login.html", "/conta": "conta.html", "/admin/usuarios":
"admin/usuarios.html", "/admin/grupos": "admin/grupos.html", "/admin/tokens": "admin/tokens.html", "/admin/log":
"admin/log.html"}`; o L0-05 acrescenta `"/tarefas"` no mesmo dicionário, única colisão prevista). Módulos ES em
`web/js/auth/`. Toda tela exceto login começa por `await exigirSessao()` (`web/js/auth/sessao.js`: chama
`/api/eu`; 401 → `location = '/entrar?inquilino=<último slug em localStorage>&proximo=<caminho atual>'`; pendência →
`/conta#senha` ou `/conta#2fa`; devolve o usuário e preenche a barra). Barra superior comum (`web/js/auth/barra.js`):
`plat · <inquilino.nome>` à esquerda; à direita `<nome>` (link para `/conta`), `Usuários`, `Grupos`, `Tokens`,
`Log` (os quatro só aparecem se o privilégio correspondente está em `usuario.privilegios`; `Grupos` sempre), `Sair`.
Tudo `data-pronto="1"` no `body` quando a tela terminou de carregar (o e2e espera por isso, como hoje).

### 15.1 `/entrar` (login.html)

```
+----------------------------------------------------------+
| plat                                  análise / beta privado |
| Entrar em: [ Inquilino de demonstração ]  (lido de         |
|            /api/login/provedores?inquilino=demo; se a URL  |
|            não traz ?inquilino=, campo de texto "inquilino")|
| usuário  [__________]                                       |
| senha    [__________] (mostrar)                             |
|                                     [ Entrar ]              |
| (área dos botões de provedor: vazia enquanto provedores=[]) |
| mensagem de erro em vermelho abaixo do botão, texto da API  |
| ("inquilino, usuário ou senha inválidos" / "usuário         |
|  bloqueado até 13:52" / "esta conta entra pelo login da     |
|  organização" / "muitas tentativas; aguarde")                |
+----------------------------------------------------------+
--- após senha certa com 2FA (mesma página, sem recarregar) ---
| código do autenticador [______]   [ Confirmar ]             |
| usar código de recuperação (alterna o campo)                |
| o desafio expira em 5 min (contador)                        |
```

Depois de `ok:true`: `location = proximo` (só caminho relativo começando por `/`, sem `//`; senão `/`). Guarda
`inquilino` em `localStorage.plat_inquilino`. Sem "lembrar-me". Sem "esqueci a senha" (texto: "peça ao administrador
do seu inquilino").

### 15.2 `/conta` (conta.html) — "Minha conta"

Seções (âncoras `#dados`, `#senha`, `#2fa`, `#sessoes`, `#convites`):

```
Dados      nome [____] e-mail [____] [Salvar]    login: maria (não editável)  perfil: editor  papel: Curador
           privilégios: lista dobrável (os 46 com marca do que tem)
Senha      atual [____] nova [____] (regra ao vivo: 8+ com letra e número) [Trocar]
           aviso quando pendência trocar_senha: "sua senha é temporária; troque para continuar"
Segundo fator  estado: desligado | ligado desde <data>, 6 códigos de recuperação restantes
           [Ligar] → mostra QR (svg), o segredo em texto, campo "código" [Confirmar] → lista dos 8 códigos com
           [Copiar] e aviso "aparecem uma única vez"
           [Desligar] pede senha + código; se o inquilino exige 2FA o botão não aparece e o texto diz por quê
           [Gerar novos códigos] pede senha
Sessões    tabela: criada · último uso · IP · navegador · (atual) · [Encerrar]; botão [Encerrar as outras]
Convites   tabela: grupo · convidado por · quando · [Aceitar] [Recusar]
Tokens     link para /admin/tokens (o nome "admin" é da pasta; a tela é de qualquer usuário com tokens.gerar)
```

### 15.3 `/admin/usuarios` (usuarios.html) — exige `membros.ver`; botões de escrita só com `membros.gerir`/`membros.papel`

```
Usuários (n)   filtro: perfil [todos v] estado [ativos v] último acesso [qualquer v]  busca [____]   [Novo usuário]
[ ] login  nome  perfil  papel  2FA  último acesso  IP  estado   ...
[x] maria  Maria editor  Curador sim  05/09 13:00   203.0.113.7 ativo   [Editar] [Redefinir senha] [Desligar 2FA] [Desabilitar]
seleção em massa (até 100): [Mudar perfil v] [Desabilitar] [Reabilitar]  → resultado "3 alterados, 1 recusado: último admin"
Novo usuário (painel lateral): login · nome · e-mail (domínios permitidos: org.gov.br) · perfil · papel → ao salvar,
mostra a senha temporária uma vez com [Copiar] e "o usuário troca no primeiro acesso"
Editar: nome · e-mail · perfil · papel · ativo; mensagens exatas da API (409 ultimo_admin: "é o último administrador
ativo; nomeie outro antes")
Apagar: só com membros.apagar; recusa lista os grupos que o usuário possui
Rodapé: "recomendação: mantenha dois administradores ativos" (o bloqueio por senha vale para administradores)
```

### 15.4 `/admin/grupos` (grupos.html) — qualquer usuário; abas Meus grupos · Do inquilino

```
Grupos   [Novo grupo] (só com grupos.criar)   busca [____]
nome · resumo · membros · meu papel · entrada · visibilidade · marcações (atualização compartilhada / administrativo / protegido)
Grupo (painel): Visão geral (editar campos; transferir dono; proteger) · Membros (convidar por login com busca em
/api/usuarios?q=, aprovar pedidos, mudar papel, remover) · [Sair] · [Apagar]
Não membro em grupo do inquilino: [Pedir entrada] ou [Entrar] conforme `entrada`
```

### 15.5 `/admin/tokens` (tokens.html) — `tokens.gerar`; com `tokens.gerir_todos` aparece a caixa "todos do inquilino"

```
Tokens de serviço   [Novo token]
nome · prefixo · escopos · validade (expira em) · último uso · último IP · estado (válido / expira em 3 d / revogado) · [Renovar] [Revogar] [Acessos]
Novo token: nome · escopos (lista de caixas: catálogo ler, camadas ler, camadas editar, tiles ler, jobs executar,
administração do inquilino [só admin]) · validade em dias (padrão 90, máx 365) · Referer permitidos (um por linha) ·
IPs/CIDR permitidos → resultado: o token em uma caixa com [Copiar] e "não aparece de novo"; exemplos de uso:
`Authorization: Bearer ...` e a URL `/ogc/?token=...` (quando o L2-04 existir a URL fica ativa; até lá o texto é só o
cabeçalho, para não mostrar rota inexistente)
Acessos: tabela do /api/tokens/{id}/log (quando · IP · rota · status · bytes · ms)
```

### 15.6 `/admin/log` (log.html) — `org.log_ver`

```
Log de acesso   período [últimos 7 dias v] usuário [v] token [v] rota começa com [____] status [v]  [Filtrar] [Exportar CSV]
quando · usuário · token (prefixo) · IP · método · rota · status · bytes · ms · resultado   (paginação 50)
aba Eventos: quando · tipo · ator · alvo · propriedades (json dobrável)
rodapé: "retenção: 12 meses"
```

Sem tela neste item: console do superadmin (L0-07-f), papéis personalizados (L0-07-b; a API existe e é testada;
a tela Usuários lista os papéis existentes no seletor), política do inquilino (L0-07-a). Regra do laço: o que não
tem tela não aparece como botão.

---

## 16. Testes obrigatórios (o testador roda; o adversário repete por conta própria)

### 16.1 Varredura cruzada A→B em TODAS as rotas do OpenAPI (`tests/api/test_cruzado.py`)

- Lê `docs/openapi.json`; para cada `(método, caminho)` exige uma entrada em `tests/api/cruzado_casos.py`
  (`CASOS[(metodo, caminho)] = preparar(cliente, sessao_b) -> (url, corpo)`) que cria o recurso no inquilino B
  (`demo2`) e devolve a URL a chamar como A (`demo`). Rota sem entrada = teste falha (cobertura 100 % é cláusula;
  medida `rotas_total = rotas_cobertas` em `tests/medidas/L0-02-tenant-auth.json`).
- Para cada caso, quatro chamadas: (1) sessão de A; (2) token de A com `admin:inquilino`; (3) sessão de A com
  `X-Plat-Inquilino: demo2` (só superadmin pode; A não é); (4) sem autenticação. Aceita-se só `401`, `403`, `404`
  (ou `415`/`422` quando o corpo é rejeitado antes da autorização, mas nunca com efeito no banco). `200/201/204/202`
  = falha imediata. Verifica ainda que nada mudou em B (`SELECT` de controle antes/depois como `plat_app` no
  contexto de B).
- Rotas públicas (`/login*`, `/logout`, `/saude`, `/api/versao`) entram com caso trivial que prova que não devolvem
  dado de inquilino.
- Roda dentro de `make check` (marcador normal, não `lento`): é o P6 executável para todo item futuro (D20).

### 16.2 Funções `SECURITY DEFINER` (`tests/api/test_funcoes_seguras.py`, conexão `plat_app`)

Roteiro do adversário do T1 (`scratchpad/rls_ataque.py`, reescrito como teste): as 5 chamadas cruzadas da seção 12
levantam exceção; `proacl` sem `=X/`; `plat_app` sem INSERT/UPDATE/DELETE em `log_acesso`, `evento`, `privilegio`,
`perfil_privilegio`; `set_config('plat.usuario_id', '<id superadmin>')` + `tenant_criar` com hash de sessão
inválido = exceção.

### 16.3 Força bruta

- Senha: 5 erradas → 6ª CERTA = `423` com `bloqueado_ate`. Nenhum teste conecta como `postgres` (regra do ADR
  0001) e não há tela de política ainda, logo a passagem do tempo se prova de duas formas: (a) `POST
  /api/usuarios/{id}/desbloquear` como admin libera o usuário na hora (teste rápido); (b) teste `lento` com a
  variável `PLAT_TESTE_BLOQUEIO_MIN=1`, aceita por `settings` só em `PLAT_AMBIENTE=dev` (em `producao` é ignorada
  com aviso), que reduz o bloqueio a 1 min e prova que a 7ª tentativa certa entra depois de 60 s.
- TOTP: 5 códigos errados = `423`; código correto reusado = `401`; código com passo +10 = `401`; recuperação usada
  duas vezes = `401` na segunda.
- Por IP (nginx): teste `lento` contra a URL pública: 25 `POST /api/login` em 10 s → pelo menos um `429`; e um
  login de OUTRO usuário do mesmo inquilino, por outro caminho (TestClient, sem nginx), continua entrando.
- Journal e log sem segredo: 20 logins com senha conhecida; `journalctl -u plat-api --since` e `SELECT rota FROM
  plat.log_acesso` com 0 ocorrências da senha, do cookie e do desafio.

### 16.4 Token

- Revogado: cria, usa (`200`), revoga, usa em ≤ 1 s → `401 token_revogado` com `revogado em` na mensagem
  (medida `tempo_revogacao_s`).
- Expirado: cria com `validade_dias = 1` e ajusta... sem postgres: cria com `validade_dias = 400` → `400`; expiração
  real provada com `expira_em` no passado só via função de teste? Decisão: a 003 aceita `validade_dias = 0`
  APENAS quando `PLAT_AMBIENTE = dev` (o backend recusa em `producao`), o que gera token já expirado e prova o
  `401 token_expirado`. O `install.sh` semeia `PLAT_AMBIENTE=producao` no `.env`; a suíte roda com
  `PLAT_AMBIENTE=dev` no ambiente do processo (o `settings` deixa o ambiente vencer o `.env`).
- Escopo: `catalogo:ler` → `GET /api/eu` 200, `GET /api/usuarios` 403 `escopo_insuficiente`, `POST /api/grupos`
  403; `admin:inquilino` de admin → 200; `admin:inquilino` pedido por editor → 422.
- Restrição: `ip: ["10.0.0.0/8"]` nega `127.0.0.1` (401 `ip_nao_permitido`); `referer: ["https://*.exemplo.gov.br"]`
  aceita `Origin: https://sig.exemplo.gov.br`, nega `https://exemplo.gov.br` e ausência.
- Rotação: renovar → dois tokens válidos; antigo com `expira_em ≤ now()+24 h`.
- Log: cada chamada com token vira linha com `token_id`, `ip`, `rota`, `bytes > 0` para `GET /api/eu`; token
  nunca aparece em `rota` (`?token=` redigido em `/ogc/` quando existir; neste item o teste manda `?token=` em
  `/api/eu` e prova que foi ignorado e redigido).
- Latência: `latencia_auth_token_ms` mediana de 50 < 5 ms (TestClient).

### 16.5 Sessão, senha, usuários, grupos

- Cookie com `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`; cookie alterado em 1 caractere = 401; cookie
  reusado após logout = 401; sessão de `demo` em rota com `?inquilino=demo2` = 401/404.
- Sessão ociosa: em `dev`, `PLAT_TESTE_OCIOSA_S` permite ocioso de 2 s para provar o 401 e o expurgo.
- 12 senhas inválidas com `detalhe.regra` esperado; troca com senha da lista das 5 últimas = 422 `historico`.
- Último admin: desabilitar/rebaixar/apagar = 409; criar admin como editor com `membros.papel` = 403.
- Grupos: criar, convidar, aceitar, pedir/aprovar, sair, administrativo recusa sair, protegido recusa apagar,
  convite a usuário de outro inquilino = 404, membro comum não convida (403), gerente não vira dono por
  `/membros/{uid}` (409).
- `latencia_login_ms` mediana de 20 < 400 ms (inclui pbkdf2 ~118 ms).
- e2e (playwright, capturas `tests/e2e/capturas/L0-02-tenant-auth_<tela>.png`): login com senha; ligar 2FA lendo
  o segredo da resposta (o teste calcula o código com a mesma função de 6 linhas), sair, entrar com código; trocar
  senha; tela Usuários criar/editar/desabilitar/redefinir/mudar perfil em massa em 3 usuários/tentar desabilitar o
  último admin (mensagem exata); tela Grupos criar/convidar/aceitar; tela Tokens criar/revogar/acessos; tela Log com
  filtro por token. 0 erro de console em cada tela.

### 16.6 O que os testes NÃO provam (escrito para o adversário não cobrar como omissão escondida)

Segunda máquina real; comportamento sob 2 workers concorrentes no mesmo usuário (contador no banco é a garantia; o
L7-02 mede); SSO; escopos `camada:*:<uuid>` até haver camada (L0-03/L2-04); expiração de senha por dias (a política
aceita, o L0-07-a expõe; teste unitário só da regra); e-mail.

---

## 17. Paridade que este item entrega (para `docs/PARIDADE.md`, linhas 3.1 do handoff 21)

| capacidade Esri | nós (este item) | estado previsto |
|---|---|---|
| isolamento por organização | inquilino + RLS + funções com checagem + teste cruzado gerado do OpenAPI | feito (após testador) |
| conta interna | usuário por inquilino criado pelo admin; sem auto-cadastro | feito |
| login/logout; logout não logado na Esri | login/logout com cookie hash; logout registrado | feito (acima da Esri) |
| tipos de usuário e licença por membro | perfil = teto; sem licença/assento por decisão da spec | fora (decisão) |
| papéis padrão (5) | 4 perfis; Publisher = privilégio `conteudo.publicar_*` | parcial (declarado) |
| papéis personalizados e ~70 privilégios | 46 privilégios, papéis por inquilino pela API; tela no L0-07-b | parcial (sem tela) |
| MFA TOTP, admin desliga, exigir para todos | igual, mais códigos de recuperação e anti-replay; exigir por inquilino sem lista de isenção | feito |
| política de senha e bloqueio | ≥ 8 com letra e número, histórico 5, 5/15/15; configurável por `config` (tela no L0-07-a) | feito (tela parcial) |
| reset pelo admin com senha temporária | igual, sem e-mail | parcial (sem e-mail) |
| SAML/OIDC/LDAP | gancho (`origem`, `sujeito_externo`) | fora (L0-08) |
| token de sessão `generateToken` com expiração/referer/IP | sessão (cookie) + token de serviço com escopo, referer, IP, validade; 401 com motivo | feito |
| chave de API ≤ 1 ano, referrers, invalidação | token ≤ 365 d, rotação com sobreposição de 24 h, revogação imediata | feito |
| audit logs + portal logs | `log_acesso` (inclusive leitura por token, que a Esri não registra) + `evento` (vocabulário de webhook) + tela Log | feito (tela parcial: sem SIEM) |
| relatórios de uso | fora (L0-07-e) | fora |
| gestão de membros | criar/editar/desabilitar/redefinir/2FA/desbloquear/lote 100; apagar com transferência no L0-03-j | parcial |
| perfil do membro | nome e e-mail; foto/idioma/unidades no L0-02-g | parcial |
| ao menos um admin; só admin muda admin | gatilho + API + teste | feito |

---

## 18. Consequências e o que custa mudar

| decisão | custo de mudar depois |
|---|---|
| perfil = teto (sem tipo separado) | acrescentar `tipo` = 1 coluna + trocar `perfil_privilegio` por `tipo_privilegio`; rotas intactas (perguntam privilégio) |
| 46 privilégios em tabela semeada | acrescentar = 1 linha por migração; renomear = migração + `git grep`; remover = 409 se em papel |
| grupo com UUID | nenhum (D1) |
| cookie + hash de sessão, deslizante 12 h / 7 d | números em `config`; forma não muda |
| pbkdf2 600k | prefixo do hash versiona; re-hash no login seguinte |
| bloqueio por usuário no banco + por IP no nginx | mover para tabela própria (por login digitado, por IP na API) = 1 tabela; hoje o nginx cobre |
| TOTP em biblioteca padrão; segredo AES-GCM com chave de `PLAT_SECRET` | rotacionar `PLAT_SECRET` exige recifrar (`plat segredo rotacionar` na CLI L0-14: lê com a antiga, grava com a nova); `enc:v1:` versiona |
| `qrcode==8.2` em `requirements.txt` | trocar por SVG próprio (~80 linhas) se a dependência incomodar; contrato `qr_svg` não muda |
| token `plat_` + 43, escopos fechados | novo escopo = 1 linha na expressão + 1 linha em `docs/`; formato do token versionado pelo prefixo |
| `?token=` só fora de `/api/` | abrir em `/api/` = 1 linha; fechar em `/ogc/` quebraria clientes SIG de mesa |
| `log_acesso` particionada por mês, escrita síncrona em `BackgroundTask` | lote em memória = mudança só em `app/auth/middleware.py`; `evento` idem |
| superadmin = inquilino `plataforma` | "assumir inquilino" = 1 função + 1 evento; tenant NULL = reescrever RLS (não fazer) |
| erros `{erro, mensagem, detalhe, req_id}` | contrato do L0-12; mudar depois é alto (todo cliente) — por isso já nasce assim |
| SSO por `origem`/`sujeito_externo` | nenhum: o L0-08 só acrescenta tabela e rotas |
| páginas servidas pela API (`app/paginas.py`) | mover para `try_files` do nginx = 1 `location`; coexistem |
