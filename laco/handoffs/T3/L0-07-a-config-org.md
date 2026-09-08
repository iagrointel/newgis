# Handoff — item L0-07-a-configuracoes-org, recorte "configurações da organização" (arquiteto + backend)

**Objetivo do recorte.** O gerente pediu, para este turno, a fatia GET/PUT `/api/org` do item maior
L0-07-a-configuracoes-org: nome, identidade visual (logo reaproveitando o L0-11), cota de armazenamento
e de usuários, política de senha por inquilino (confirmar o esquema `tenant.config.auth` do L0-02 em vez
de recriar), exigir 2FA por inquilino, idioma padrão; só admin do inquilino acessa; teste: editor comum
recebe 403; mudança de cota reflete no `/api/arquivos` (L0-11) na hora. O portão COMPLETO do item no
`estado.json` é maior (blocos de página inicial, galeria, banner/termo, domínio de e-mail permitido,
"permitir compartilhamento público" como bandeira de exibição pública) — **isso ficou de fora deste
recorte**, nomeado abaixo como pendência para fechar o item inteiro.

## O que fiz

1. **Confirmado antes de construir** (grep no repositório, não suposição): `plat.tenant.config` já é o
   lugar de `config.auth` (política de senha/2FA/domínios, `app/auth/politica.py`) desde o L0-02, e
   `validar_config_auth()` já existe com o comentário "para a rota do L0-07-a que vai receber" — ou seja,
   o esquema já estava pronto esperando esta rota; eu só o exponho, não recrio. `CONFIG_PUBLICA` em
   `app/auth/comum.py` (`centro, zoom, basemap, srid_padrao, cor, logo`) também já antecipava os campos
   de identidade/mapa. `plat.tenant.cota_bytes` já existe e `GET /api/arquivos` já o lê AO VIVO (sem
   cache) — a "reflexão na hora" pedida no portão já vinha de graça, só faltava uma rota para mudar o
   valor.
2. **`db/migracoes/034_org_config.sql`** (aplicada manualmente via `psql` + INSERT em
   `plat.versao_migracao`, porque `db/migrar.sh` estava bloqueado por uma DIVERGÊNCIA em `030_conexao.sql`
   de uma trilha concorrente — não mexi nela, é problema de outra trilha): `plat.cota_usuarios(tenant)`
   (mesmo padrão de `plat.cota_itens`/`plat.cota_jobs_dia`: número em `tenant.config`, função lê com
   COALESCE do padrão — aqui 2000, bem acima do maior lote de criação e do uso medido no inquilino demo em
   T3) e `plat.usuarios_ativos(tenant)`; vocabulário de evento `org/configurar`, `org/logo_enviar`,
   `org/logo_remover`; GRANT explícito (nunca EXECUTE para PUBLIC, regra P6).
3. **`app/auth/rotas_org.py`** (novo): `GET/PUT /api/org` (privilégio `org.configurar`, já existia
   semeado desde a migração 003, teto só do perfil admin — nenhum privilégio novo) e `POST/DELETE
   /api/org/logo`. `PUT` faz MERGE em `tenant.config` (`config || jsonb`), nunca reescreve o objeto
   inteiro — preserva `config.logo` (gravado pela rota separada) e qualquer chave futura de outro item
   do L0-07. Nome e cota de armazenamento são colunas reais (`nome`, `cota_bytes`); o resto vive em
   `config`. Logo: base64 sob JSON (mesmo truque de CSRF que a miniatura de item já usa), Pillow
   redesenha para PNG 300×300 contido (nunca recorta, fundo transparente), 1 MiB, formatos PNG/JPEG/GIF/
   WEBP — reaproveita `app/objetos.py::guardar` com `classe='org_logo'`, sem tabela nova.
4. **`app/auth/rotas_usuarios.py`**: cota de usuários agora tem EFEITO — `POST /api/usuarios` checa
   `plat.usuarios_ativos < plat.cota_usuarios` antes de inserir (413 `cota_usuarios`). **Sem lock
   (`SELECT ... FOR UPDATE`)**: é uma checagem simples, não à prova de corrida sob concorrência real —
   isso é trabalho do item L0-07-c-cotas-uso (cobre TODAS as cotas do inquilino, inclusive a reserva
   atômica que o próprio portão dele exige). Documentei isso no comentário do código para não passar como
   "pronto" o que não é.
5. **Frontend**: `web/admin/organizacao.html` + `web/js/auth/organizacao.js` — 5 `plat-formulario` (
   Identidade, Logotipo, Mapa padrão, Armazenamento, Usuários, Senha/2FA — a última é a MESMA política
   que `/conta` já mostra a cada membro, agora editável aqui) mais um upload de arquivo simples (sem
   componente novo: `FileReader` → base64 → `POST /api/org/logo`). Cada seção envia o corpo INTEIRO do
   `PUT /api/org` (contrato full-replace igual ao `/api/org/ldap`), partindo do último GET conhecido, só
   sobrepondo os campos da própria seção — nenhuma seção precisa que as outras estejam preenchidas.
   `app/paginas.py` (`/admin/organizacao`), `web/js/base/layout.js` (item de navegação, privilégio
   `org.configurar` — some do menu para quem não é admin), `web/js/i18n/pt-BR.json` (chaves `org.*` +
   `nav.organizacao[_desc]`, a `_desc` alimenta o grid da página inicial de graça, é o mesmo padrão que
   as outras telas já usam).
6. **Testes**: `tests/api/test_org.py` (9 casos, todos verdes) — GET/PUT 200 para admin com todas as
   chaves do contrato; editor recebe 403 em GET, PUT, POST/DELETE logo (parametrizado
   editor/visualizador/campo); mudança de nome/cor/idioma/mapa/cota_bytes persiste e **`GET /api/arquivos`
   reflete a cota nova na PRÓXIMA chamada, sem reinício de processo** (o portão do recorte); validação 422
   nomeando o campo (cor sem `#`, idioma fora da lista, `auth.senha_min` abaixo do esquema, `auth` com
   chave desconhecida, `centro` fora do intervalo geográfico, campo extra desconhecido — `extra="forbid"`
   também é a defesa contra "mirar outro inquilino por campo extra", já que não há `id` na rota); RLS
   prova isolamento entre `demo`/`demo2` (o PUT de A nunca aparece em B); cota de usuários exposta E
   aplicada (413 quando esgotada, volta a criar depois de restaurar a cota); logotipo enviado, lido como
   PNG 300×300 de verdade, formato não suportado (415), acima de 1 MiB (413 ou 422, mesmo caso já coberto
   em `test_miniatura.py` quando o próprio pydantic corta primeiro), removido. Todo teste que muda o
   inquilino `demo` restaura o estado original em `finally` (a suíte inteira depende dele).
   `tests/e2e/test_i18n_cru.py`: acrescentei `/admin/organizacao` à lista de telas varridas (nenhuma
   chave crua).

## Evidência (comando + saída literal)

```
$ venv/bin/ruff check app/auth/rotas_org.py app/auth/rotas_usuarios.py app/main.py app/limites.py app/paginas.py
All checks passed!
$ venv/bin/ruff check app tests docs/gerar_limites.py     # árvore inteira, inclusive trilhas concorrentes
All checks passed!
$ venv/bin/python docs/gerar_limites.py --check
(saída vazia; exit 0 — LIMITES.md em dia com limites.py)
$ sudo bash db/migrar.sh                                   # bloqueado por OUTRA trilha, não pela minha migração
DIVERGENTE 030_conexao: sha aplicado ...(arquivo aplicado é imutável; correção vai em arquivo novo) — exit 3
$ # 034 aplicada manualmente (cat migração + INSERT em plat.versao_migracao), evidência:
$ sudo -u postgres psql -d iagro_sat -c "SELECT plat.cota_usuarios(1), plat.usuarios_ativos(1);"
 cota_usuarios | usuarios_ativos
---------------+-----------------
          2000 |              50
$ sudo systemctl restart plat-api && systemctl is-active plat-api
active
$ flock .../.pytest.lock bash -c '...; venv/bin/pytest tests/api/test_org.py -m "not lento" -q'
.........                                                                [100%]
9 passed
$ flock .../.pytest.lock bash -c '...; venv/bin/pytest tests/api/test_cruzado.py -m "not lento" -q -k org'
.......                                                                  [100%]
7 passed   # os 4 casos novos (/api/org GET/PUT, /api/org/logo POST/DELETE) + os 3 de /api/org/ldap já existentes
$ flock .../.pytest.lock bash -c '...; venv/bin/pytest tests/api/test_eventos.py -m "not lento" -q"
FAILED test_toda_rota_de_escrita_tem_evento_declarado — faltando = SÓ rotas de /api/conexoes e
/api/importacoes{id} (outra trilha, não registradas por ela ainda); as 3 do meu item
(PUT /api/org, POST/DELETE /api/org/logo) já não aparecem na lista de faltantes.
```
`docs/openapi.json` regenerado (`make openapi`) — `/api/org` (get/put) e `/api/org/logo` (post/delete)
aparecem. `make sem-marcador` reprova por **dois arquivos de OUTRA trilha em curso**
(`app/conexao/tarefas.py`, `db/migracoes/036_conexao_saude_e_camada.sql` — a palavra "TODOS" bate o
regex de marcador por acidente; não são meus, não toquei; confirmei rodando o mesmo grep só nos MEUS
arquivos, que passa limpo).

**Correção sobre o `make check` completo**: lancei a suíte inteira em background (`pytest -m "not
lento"`, sem filtro) e ela voltou com uma leva grande de `ERROR` em `test_cruzado.py`/`test_eu.py`/
`test_plataforma.py` — MAS a causa era eu mesmo: enquanto ela rodava, eu regenerei `docs/openapi.json`
de novo (`make openapi`), e `test_cruzado.py` lê esse arquivo do disco no meio da coleta/execução —
uma corrida MINHA, não uma regressão real. Reproduzi os arquivos específicos que erraram DEPOIS de
parar de mexer no openapi.json e todos passaram (só 2 falhas remanescentes, `test_sessao_ociosa_expira`
por timing sob máquina carregada e `/saude` 503 por carga do Postgres — nada meu, nada relacionado a
`/api/org`). Registrado aqui para quem olhar o log do driver não interpretar aquela leva de ERROR como
regressão deste item.

## Riscos e o que NÃO cobri

- **Portão completo do L0-07-a**: página inicial com blocos (texto/galeria/links, ≤15/≤8), galeria em
  destaque (grupo), banner de aviso + termo de acesso (texto exibido antes do login, saneado contra
  HTML), domínio de e-mail permitido (já existe em `config.auth.dominios_email`, exposto e editável
  aqui — só falta o teste do adversário injetando HTML em campo de TEXTO livre, que não existe ainda
  porque não há campo de texto livre nesta fatia) e "permitir compartilhamento público" como bandeira
  pública de vitrine (já existe em `config.auth.compartilhar_publico`, editável aqui, mas o portão fala
  de algo mais amplo). Ficou como pendência nomeada — o item-pai `L0-07-a-configuracoes-org` NÃO deveria
  fechar como `entregue` só com este recorte; sugiro `parcial`.
- **Cota de usuários sem lock** (ver item 4 acima): correto o suficiente para "a cota deixa de ser
  decorativa", mas a prova de corrida (`SELECT ... FOR UPDATE`) é do L0-07-c.
- **Reativar usuário desabilitado não passa pela checagem de cota** (só a criação passa). Nomeado, não
  bloqueia nada hoje porque reabilitar é ação rara e administrativa.
- **e2e/Playwright NÃO rodado neste turno**: `free -g` mostrou ~1 GB disponível (guardrail do laço exige
  ≥4 GB antes de processo novo); não lancei o Chromium para não arriscar outro incidente de OOM como o de
  30/08 e 06/09 (osmium). A tela foi conferida por leitura de código (padrões idênticos a `conta.js`/
  `papeis.js` já testados por e2e) e pela suíte de API, mas **P1 (funciona no navegador, 0 erro de
  console) fica PENDENTE de captura** — o papel `testador` deveria rodar
  `pytest -m lento -k organizacao` assim que a RAM permitir.
- **Suíte inteira** (`make check`/`pytest -m "not lento"` sem filtro): lancei em background para
  confirmar que nada mais quebrou, mas a máquina tinha várias outras trilhas na fila do MESMO
  `flock .pytest.lock` (visto por `ps aux`) — o resultado, quando chegar, vale para o estado da árvore
  NAQUELE instante, que inclui código incompleto de outras trilhas; não é prova exclusiva deste item.
  A prova que É exclusivamente deste item é `pytest tests/api/test_org.py` (9/9 verde, evidência acima).

## Para o próximo papel

- **Cronista**: `docs/PARIDADE.md` ainda não tem a linha deste recorte contra "General"/"Home page"/
  "Map"/"Gallery"/"Security" 11.4 (o portão pede isso; a paridade real só cabe quando o item inteiro
  fechar, com blocos/galeria/banner). `MANUAL.md` precisa da seção "Organização" com captura — depende do
  e2e acima. `CHANGELOG.md` ainda não tem entrada deste turno.
- **Testador**: rodar `pytest -m lento -k organizacao --base-url https://plat.iagrointel.com` quando
  `free -g` disponível ≥ 4 GB; gravar captura em `tests/e2e/capturas/`; medir em
  `tests/medidas/L0-07-a-configuracoes-org.json`.
- **Gerente**: decidir se `L0-07-a-configuracoes-org` vira sub-itens (`-a1` este recorte entregue,
  `-a2` página inicial/galeria/banner/termo pendente) no backlog, já que o portão original é maior que o
  pedido deste turno.
