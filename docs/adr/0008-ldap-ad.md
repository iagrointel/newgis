# ADR 0008 — LDAP/Active Directory como provedor externo (item L0-08-d-ldap, filho de L0-08-sso)

Contexto: ADR 0002 seção 13 já deixou o gancho pronto (`usuario.origem` aceita `'ldap'`, `sujeito_externo`
único por `(tenant_id, origem)`, senha local `NULL` para origem externa, rota `login_externo` para conta que
não usa senha própria). Este item constrói o provedor de fato: bind contra um diretório LDAP/Active Directory
configurável por inquilino, mapeamento de grupo do diretório para um dos 4 perfis da plataforma, e
provisionamento automático no primeiro login — sem nunca gravar a senha do usuário do LDAP.

## D1. Biblioteca: `ldap3` (pure Python), não o `python-ldap`/binding sobre `libldap`

Opções: (a) `python-ldap` (binding C sobre `libldap2-dev`, exige compilar contra a biblioteca de sistema); (b)
`ldap3` (puro Python, só depende de `pyasn1`); (c) protocolo LDAP escrito à mão sobre socket.

MEDIDO nesta máquina (05/09/2026, L0_CONCEITO.md): `ldap3` está **ausente** da venv, mas `pip install ldap3`
resolve sozinho (432 kB, só depende de `pyasn1` — já presente via `python3-pyasn1` do dpkg, dependência de
outro produto da casa). Não há `libldap2-dev`/`python3-ldap` no `deploy/pacotes_apt.txt` (lista fechada, ADR
0007) e acrescentar um pacote de sistema exigiria decisão do dono; `ldap3` não exige.

Recomendação: (b). Motivo: zero dependência de sistema (só a venv, como o resto do ADR 0001 exige), suporta
StartTLS, bind simples e anônimo, busca com filtro, e paginação — o suficiente para o portão deste item. Custo
de mudar depois: baixo (a interface do módulo `app/auth/ldap.py` não vaza `ldap3` para fora dele).

## D2. Configuração do provedor: tabela própria por inquilino (`plat.provedor_ldap`), não `tenant.config`

Opções: (a) guardar url/base_dn/mapa dentro de `tenant.config.ldap` (jsonb já existente); (b) tabela própria
com RLS `FOR ALL`, mesmo padrão de `plat.papel_personalizado`/`plat.grupo`; (c) arquivo de configuração por
inquilino no disco.

Recomendação: (b). Motivo: a senha de bind de serviço (cifrada) e o mapa grupo→perfil merecem colunas tipadas
e um `CHECK` no perfil (vocabulário fechado de 4, D5 do L0_CONCEITO), não um campo solto dentro de um jsonb de
propósito geral; RLS `tenant_id = plat.tenant_atual()` cumpre o portão P6 igual a qualquer tabela nova da
linha. `UNIQUE (tenant_id)`: um provedor LDAP por inquilino nesta primeira passagem (múltiplos provedores por
inquilino, se um dia precisar, é migração aditiva, não redesenho).

## D3. Endereço do diretório: `PLAT_LDAP_URL`/`PLAT_LDAP_BASE_DN` (variáveis de ambiente) são o PADRÃO, nunca
o único lugar

O portão do item nomeia `PLAT_LDAP_URL`/`PLAT_LDAP_BASE_DN` explicitamente. Decisão: essas duas variáveis são
lidas só dentro de `app/auth/ldap.py` (nunca em `app/settings.py`; o campo é opcional e por-inquilino, não faz
sentido como chave obrigatória da aplicação inteira) e servem de **valor-padrão** quando a linha do inquilino
em `plat.provedor_ldap` não informa `url`/`base_dn` próprios. Na prática, é assim que o diretório de TESTE
desta máquina (glauth em contêiner Docker efêmero, `tests/ldap_fixture/`) "aponta" para qualquer inquilino sem
gravar `127.0.0.1:3893` no banco de produção. Um inquilino com Active Directório real sempre grava seu próprio
`url`/`base_dn` pela rota `PUT /api/org/ldap` (privilégio `org.integracoes`, já reservado pela ADR 0002 seção
3.2 para "SSO, SMTP, webhooks, CORS").

## D4. Servidor de teste: contêiner Docker `glauth` (não OpenLDAP, não mock em Python)

Confirmado antes de decidir (regra do portão): `df -h /` = 12 GiB livres, `free -h` = 1,2-2,6 GiB
disponíveis (05-06/09/2026). Opções: (a) `osixia/openldap` (slapd completo, ~200-400 MB de imagem, exige
configuração de schema); (b) `glauth/glauth` (binário Go único, config declarativa TOML, imagem 98,9 MB
medida nesta máquina); (c) mock do protocolo LDAP em Python (sem servidor real).

Recomendação: (b). Motivo: imagem pequena o bastante para o disco apertado (98,9 MB medido, `docker images`),
sobe em <1 s, cobre bind simples, bind anônimo, busca com filtro e `memberOf` sintético — o que o portão do
item precisa provar — sem gastar RAM de um `slapd` completo. (c) ficaria como alternativa se o disco não
coubesse; coube, então o item prova bind contra um LDAP DE VERDADE (protocolo real, não reimplementado à
mão), que é uma prova mais forte. Formato de DN observado (medido, `docker logs`/busca real): usuário
`cn=<nome>,ou=<grupo>,ou=users,<baseDN>`; grupo em `memberOf` como `ou=<grupo>,ou=groups,<baseDN>` (glauth usa
`ou=` para o RDN de grupo, não `cn=`) — por isso `perfil_por_grupos` (app/auth/ldap.py) casa tanto pelo DN
inteiro quanto só pelo valor do primeiro RDN, não assume o nome do atributo.

**Limitação documentada**: o contêiner de teste é efêmero, só local (`127.0.0.1:3893`, nunca exposto), com 3
usuários sintéticos (um por perfil) e uma conta de serviço; StartTLS não foi testado contra ele (glauth de
teste não tem certificado — `start_tls=false` na configuração de teste); um Active Directory real exigiria
`filtro_usuario` (`(sAMAccountName={login})` é o comum em AD, contra `(uid={login})`/`(cn={login})` do
OpenLDAP/glauth) e `atributo_grupos` ajustados pelo administrador do inquilino (ambos configuráveis pela rota,
sem precisar de deploy novo).

## D5. Mapeamento grupo→perfil e provisionamento: nunca sobrescreve conta local, sempre 4 perfis do ADR 0002

O vocabulário de perfil é o MESMO da D5 do L0_CONCEITO (admin/editor/visualizador/campo) — o LDAP não cria um
quinto perfil "federado". Quando mais de um grupo mapeado bate, vale o de maior alcance
(`app/auth/privilegios.ORDEM_PERFIL`, o mesmo vocabulário do resto da plataforma). Quando nenhum grupo mapeado
bate e não há `perfil_padrao`, a rota recusa com `403 sem_grupo_mapeado` — nunca inventa um perfil mínimo por
via das dúvidas. Provisionamento: `plat.ldap_provisionar` (SECURITY DEFINER, sem exigir contexto de sessão,
mesmo padrão de `plat.auth_login`) faz o upsert; se já existe um usuário com o MESMO login e origem `'local'`,
a função levanta `login_em_uso_local` e a rota devolve `409` — um administrador de diretório nunca assume uma
conta local homônima só por controlar o LDAP. Depois do upsert, a rota chama `plat.auth_login` de novo (mesmo
formato do login local) e **reaproveita** `app.auth.rotas_login._abrir_sessao` para criar a sessão — zero
duplicação da lógica de cookie/política/evento que o login local já tem.

## D6. Força bruta contra o bind: contador em memória por processo, reaproveitando a política do PRÓPRIO
inquilino

A refutação do item pede resistência a "1.000 binds/min". Como o alvo pode ser um login que **ainda não
existe localmente** (o contador de bloqueio do login local vive na linha de `plat.usuario`, que só existe
depois do primeiro provisionamento), a defesa não pode depender só do banco. Solução: um contador em memória
de processo, chave `(tenant_id, login)`, reaproveitando `bloqueio_tentativas`/`bloqueio_minutos` da política
do inquilino (nunca um limiar novo à parte) — a 6ª tentativa errada nos últimos `bloqueio_minutos` minutos
devolve `423` sem sequer abrir uma conexão LDAP. Custo aceito e documentado: o contador não é compartilhado
entre os `--workers 2` da unidade `plat-api` (dobra o teto efetivo na pior hipótese) nem sobrevive a um
reinício do processo — ambos aceitáveis para uma primeira passagem; um contador compartilhado (tabela ou
Redis) fica como pendência nomeada, não como promessa.

## D7. Senha vazia nunca vira bind: defesa antes do RFC, não confiança nele

RFC 4513 §5.1.2 define "unauthenticated bind" (DN válido + senha vazia) como um bind que TEM que ser
recusado por um servidor bem configurado, mas nem todo servidor recusa (é a classe de vulnerabilidade "LDAP
anonymous bind" descrita em vários avisos de segurança de produto). `app/auth/ldap.py` corta a senha vazia
ANTES de abrir qualquer conexão — nunca chega a perguntar ao servidor. Medido nesta máquina: o próprio `ldap3`
já levanta `LDAPPasswordIsMandatoryError` para bind simples sem senha (defesa adicional do lado da
biblioteca), mas o item não confia só nisso.

## Custo de mudar

Baixo–médio: a tabela `plat.provedor_ldap` e as 3 funções (`provedor_ldap_de`, `ldap_provisionar`,
`ldap_importar_lote`) são aditivas; trocar `ldap3` por outra biblioteca no futuro (ex.: por causa de LDAPS com
certificado corporativo específico) não muda o contrato das rotas `/api/login/ldap`, `/api/org/ldap`,
`/api/org/ldap/importar`. OIDC/SAML (resto do L0-08-sso) reaproveitam o mesmo desenho de tabela por provedor,
o mesmo privilégio `org.integracoes` e o mesmo caminho de `_abrir_sessao` depois de validar a credencial.
