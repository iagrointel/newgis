# Ataque adversarial independente — grupo G4 (resto da fundação)

Adversário: papel isolado, não construiu nada deste grupo. Data: 06/09/2026.
Ramo: `wt/adv4` (worktree `/home/dev/plataforma/wt/adv4`), commit **e1ff144**.
Base de teste própria: schema `plat_tadv4` / `plat_trabalho_tadv4` (`laco/trilha_ambiente.sh adv4`).
Arquivo de prova: `tests/api/test_g4_adversario.py` — **24 achados como `xfail(strict=True)`** e
**6 testes sem marca** com o que o ataque não derrubou. Resultado da rodada:

    $ set -a; source /home/dev/plataforma/laco/var/trilha/adv4.env; set +a
    $ venv/bin/pytest tests/api/test_g4_adversario.py -p no:randomly
    6 passed, 24 xfailed, 1 warning in 25.94s

O alvo medido foi a árvore de trabalho principal (`/home/dev/plataforma/enterprise`) copiada para o
worktree em 06/09 15:25 — inclui o que ainda não tem commit (convites, uploads, SMTP). Escolhi essa
cópia porque as migrações que a `trilha_ambiente.sh` aplica saem dessa mesma árvore; medir o `master`
puro mediria um banco e um código de épocas diferentes. Registro à parte: **o `master` comitado não
importa** — `app/main.py` de 90ab545 faz `from app.auth import rotas_convites`, e
`app/auth/rotas_convites.py` está sem `git add`. Quem clonar o repositório hoje não sobe a aplicação.

---

## (a) Veredito item a item

| item | estado no `estado.json` | veredito | achados |
|---|---|---|---|
| L0-07-a-configuracoes-org | parcial | **REFUTADO** | G4-04, G4-05 (elevação de cota pelo próprio inquilino), G4-17, G4-18 |
| L0-09-metadado-catalogo | parcial | **REFUTADO** (portão) | G4-20 |
| L0-10-eventos-historico | **entregue** | **REFUTADO** | G4-02, G4-03, G4-08, G4-10, G4-11, G4-12, G4-13 |
| L0-11-arquivos-objetos | **entregue** | **REFUTADO** | G4-06, G4-07, G4-08, G4-09, G4-19 |
| L0-12-contrato-api-e-limites | **entregue** | **REFUTADO** | G4-01, G4-14, G4-15, G4-16, G4-23 |
| L0-14-identidade-visual | parcial | **REFUTADO** | G4-21, G4-22 |

Três itens estão marcados `entregue` com cláusula do próprio portão por fazer, e um deles (L0-10)
entrega o seu teste central **vermelho**:

    $ venv/bin/pytest tests/api/test_org.py tests/api/test_arquivos.py tests/api/test_eventos.py \
        tests/api/test_limite_corpo.py tests/api/test_versionamento.py \
        tests/api/catalogo/test_metadado_ogc.py tests/unit/test_limites_doc.py -p no:randomly
    FAILED tests/api/test_eventos.py::test_toda_rota_de_escrita_tem_evento_declarado
    1 failed, 48 passed, 1 warning in 24.32s

Severidade dos achados:

- **Alta (segurança ou perda de dado):** G4-06, G4-07, G4-10, G4-04, G4-05.
- **Média (a garantia existe no papel e não no produto):** G4-01, G4-02, G4-08, G4-09, G4-11, G4-14,
  G4-16, G4-19, G4-23, G4-24.
- **Baixa (cláusula de portão não construída):** G4-03, G4-12, G4-13, G4-15, G4-17, G4-18, G4-20,
  G4-21, G4-22.

---

## (b) Suposições transversais — o que caiu e o que aguentou

Escrevi as cinco suposições que os seis portões compartilham antes de olhar item por item. Quatro
caíram; a que aguentou é a mais importante do produto.

### T1. "O OpenAPI comitado é o contrato" — **CAIU** (G4-01)

`docs/openapi.json` está **28 rotas atrás** do aplicativo vivo e **nenhum teste compara os dois**;
`make check` não regenera nem confere (`make openapi` só escreve o arquivo).

    rotas vivo: 196  disco: 168
    so no vivo: [('DELETE','/api/convites/{id}'), ('POST','/api/uploads'), ('PUT','/api/org/smtp'),
                 ('POST','/api/senha/redefinir/aplicar'), ('GET','/rest/services/.../suggest'), ...]
    igual byte a byte: False

Isto derruba dois guardiões de uma vez, porque os dois leem o **arquivo comitado**, não o app:
`tests/api/test_eventos.py` (cobertura de evento) e `tests/api/test_cruzado.py` (varredura A→B de
isolamento). Rota nova que ninguém regenerou é rota que nenhum dos dois testa.

### T2. "Toda rota que altera estado grava um evento; cobertura 100 %" — **CAIU** (G4-02, G4-03)

Contra o app vivo: **111 rotas de escrita, 84 declaradas, 27 faltando = 75,7 %**. Contra o arquivo
comitado (o número que o handoff cita como 100 %) faltam 10. E a medida aceita declaração com lista
**vazia**: 6 rotas estão registradas como "sem evento", entre elas `POST` e `DELETE /api/arquivos`,
que criam e destroem objeto do inquilino. "Cobertura" aqui mede declaração, não evento.

### T3. "Quem define o teto de recurso é a plataforma" — **CAIU** (G4-04, G4-05)

`OrgEntrada.cota_bytes` e `cota_usuarios` têm só piso (`ge`), sem teto, e a rota é do **admin do
inquilino**. Medido:

    GET  /api/org  -> armazenamento.cota_bytes = 21474836480 (20 GiB), usuarios.cota = 2000
    PUT  /api/org  cota_bytes=9e18, cota_usuarios=1e9  -> 200 OK
    $ psql: SELECT bucket_alias, cota_bytes FROM plat_tadv4.arquivo_bucket
      tadv4-plat-demo | 9000000000000000000

A cota escalada **chega ao bucket do Garage**. O inquilino de demonstração passa a poder encher o
disco da máquina, que está com 46 GB livres de 469 GB (91 % usado). O mesmo vale para assentos de
usuário: o teto de licenciamento é editável por quem é licenciado.

### T4. "Isolamento por inquilino basta" — **CAIU dentro do inquilino** (G4-06, G4-07)

`GET` e `DELETE /api/arquivos/{sha256}` exigem apenas `autenticado()`: nenhum privilégio, nenhuma
checagem de dono. Um usuário de perfil **visualizador** (só leitura) apagou o logotipo da
organização:

    VISUALIZADOR GET  /api/arquivos/<sha>?classe=org_logo -> 200 (815 bytes)
    VISUALIZADOR DELETE /api/arquivos/<sha>?classe=org_logo -> 204
    ADMIN GET  /api/arquivos/<sha>?classe=org_logo -> 404
    GET /api/org -> "logo": "<sha>"   (a organização continua apontando para um objeto morto)

A assimetria mostra que a intenção era outra: **sob token** o mesmo verbo exige escopo
`admin:inquilino` (`403` com `catalogo:ler`); sob cookie de sessão não exige nada.

### T5. "O rastro é append-only" — **CAIU como propriedade, PASSOU como cláusula** (G4-10)

A cláusula literal do portão passa: `plat_app` não faz `UPDATE` nem `DELETE` em `plat.evento`.

    UPDATE plat_tadv4.evento SET tipo='usuarios/sair'  -> ERROR: permission denied for table evento
    DELETE FROM plat_tadv4.evento                       -> ERROR: permission denied for table evento

Mas `plat_app` tem `EXECUTE` em `plat.evento_expurgar(int)` e `plat.log_expurgar(int)` — funções
`SECURITY DEFINER`, sem filtro de inquilino e sem validação do argumento, que fazem `DROP TABLE` na
partição. Com mês negativo o limite vai para o mês seguinte e a partição **corrente** cai:

    SELECT plat_tadv4.evento_expurgar(-1);  -> 1        (partições dropadas)
    SELECT count(*) FROM plat_tadv4.evento; -> 0        (era 7 na linha acima)
    partições restantes: evento_y2026m10, evento_y2026m11, evento_y2026m12

Isto apaga a auditoria de **todos os inquilinos**, não só a de quem chama. Hoje nenhuma rota HTTP
chama a função (ver fronteira), então não é um caminho de ataque pronto para um admin de inquilino —
é a defesa em profundidade ausente: qualquer injeção de SQL na aplicação vira apagamento total de
rastro, e o papel da aplicação não deveria ter esse poder.

### T6. "O que aguentou": isolamento ENTRE inquilinos

Ataquei por seis caminhos e nenhum abriu. Registro porque é o que sustenta o produto:

    B GET /api/arquivos/<sha de A>            -> 404
    B GET /api/itens/<id de A>/metadado.xml   -> 404
    B GET /ogc/records/collections/catalogo/items/<id de A> -> 404
    superadmin PUT /api/org com X-Plat-Inquilino: demo -> 400 cabecalho_nao_aceito
    PUT no Garage com a chave só-leitura      -> 403 AccessDenied
    DELETE no Garage com a chave só-leitura   -> 403 AccessDenied
    GET anônimo direto no Garage (:3900)      -> HTTP 403
    POST /api/arquivos?classe=../etc          -> 422 validacao

Também aguentaram: escape de XML no metadado ISO (título com `<script>`, `]]>` e `&` sai bem formado
e sem marcação crua), a recusa de apagar item protegido (`409 item_protegido`) e o escopo de token.

---

## (c) Bloco por item — comando e saída real

### L0-07-a-configuracoes-org — REFUTADO

Portão: "e2e: alterar nome, logo, cor, mapa padrão **e um bloco da página inicial**; API: config
inválida (cor sem #, **16 blocos**) = 422 com caminho; logo > 1 MB recusado; paridade contra
General, Home page, Map, **Gallery**, Security". Refutação: "injeta HTML no **banner** (saneado),
define **contato administrativo** vazio, muda config de outro inquilino por PUT".

O que existe: `GET/PUT /api/org` (nome, cor, idioma, centro/zoom/basemap/srid, cotas, política de
senha/2FA) e `POST/DELETE /api/org/logo`. O que o portão pede e **não existe como campo**: blocos de
página inicial, galeria em destaque, banner de aviso, termo de acesso, contatos administrativos.

    PUT /api/org com {"pagina_inicial": {"blocos": [...]}}
      -> 422 {"erro":"validacao","detalhe":[{"campo":"body.pagina_inicial",
              "erro":"Extra inputs are not permitted","tipo":"extra_forbidden"}]}
    PUT /api/org com {"banner": "<script>alert(1)</script>ok"}
      -> 422 ... "campo":"body.banner","erro":"Extra inputs are not permitted"

Ou seja: a cláusula "16 blocos = 422 com caminho" nunca pôde ser medida, e a refutação do banner não
é aprovada nem reprovada — não há o que atacar. **G4-17, G4-18.**

Achado próprio, que não estava previsto na refutação do item: **G4-04 e G4-05** (seção T3 acima). A
única barreira contra o inquilino se autoconceder recurso é o piso; não há teto.

O que passou: editor comum recebe 403 (`tests/api/test_org.py` verde, 48 casos do bloco), logo acima
de 1 MiB recusado, superadmin não escreve config de outro inquilino, RLS em `plat.tenant`.

### L0-09-metadado-catalogo — REFUTADO (portão não cumprido)

    from app.main import app -> caminhos com "csw": nenhum
    web/conteudo_metadado.html: não existe;  web/js/catalogo/metadado.js: não existe
    -> {'csw': False, 'tela': False}

Faltam do portão: **CSW GetRecords**, ISO 19115-3, **editor de metadado na tela**, e2e e paridade
escrita. O próprio `app/catalogo/rotas_ogc.py` registra o CSW como pendência com a justificativa.
**G4-20.**

A refutação específica do item **não derrubou o produto**: apagar item com proteção ligada é
recusado corretamente, e o "usado por" existe (`GET /api/itens/{id}/usado-por`,
`plat.item_usado_por`).

    PATCH /api/itens/<id> {"protegido": true} -> 200
    DELETE /api/itens/<id>                    -> 409 {"erro":"item_protegido", ...}

A validação ISO 19139 contra XSD oficial cacheado (`docs/xsd/cache/`, `lxml`) existe e passa
(`tests/api/catalogo/test_metadado_ogc.py`, dentro dos 48 verdes acima). Este item é o menos
frágil dos seis; o que falta é construção, não conserto.

### L0-10-eventos-historico — REFUTADO (e está marcado `entregue`)

1. **Cobertura.** Contra o app vivo, 27 rotas de escrita sem declaração; 75,7 % (G4-02). Contra o
   arquivo comitado, 10 faltando — o teste do próprio item está vermelho hoje:

       AssertionError: [('DELETE','/api/conexoes/{id}'), ('DELETE','/api/eu/foto'),
       ('DELETE','/api/importacoes/{id}'), ('PATCH','/api/conexoes/{id}'), ('POST','/api/conexoes'), ...]
       Left contains 10 more items

2. **Ação sem evento (a refutação do item, literalmente).** Apagar um objeto do inquilino não grava
   nada. Medido com o contador de `/api/eventos` antes e depois de um `DELETE /api/arquivos` que
   retornou 204: `83 -> 83`. **G4-08.** A rota está declarada "sem evento" em
   `eventos_esperados.py`, então o guardião aprova a destruição silenciosa (G4-03).

3. **Apagar o próprio rastro.** Seção T5: `plat.evento_expurgar(-1)` derruba a partição do mês
   corrente para todos os inquilinos, com o `EXECUTE` que `plat_app` tem. **G4-10.**

4. **Partição e retenção.** O portão pede "partição do mês seguinte criada pelo periódico" e a
   hipótese pede retenção de 12 meses. Nenhuma tarefa da aplicação cita
   `evento_particao_garantir`, `evento_expurgar` ou `log_expurgar`:

       AssertionError: nenhuma tarefa/periódico da aplicação chama:
       ['evento_particao_garantir', 'evento_expurgar', 'log_expurgar']

   As partições vieram de um `generate_series(0, 3)` da migração 003 (mês corrente e três à frente).
   Depois disso a criação depende do tratamento de `check_violation` dentro de `evento_registrar`, e
   a retenção de 12 meses **nunca roda**. **G4-11.**

5. **Exportação e tela.** `GET /api/eventos` não tem parâmetro `formato`; com `?formato=csv` devolve
   `application/json` e ignora o parâmetro (só `/api/log`, que é o log de acesso HTTP, exporta CSV).
   A medida "100 mil eventos em CSV ≤ 10 s" não existe. **G4-12.** E não há tela: `web/admin/` tem
   `grupos, log, organizacao, papeis, tokens, usuarios` — nenhuma `auditoria.html`. **G4-13.**

### L0-11-arquivos-objetos — REFUTADO (e está marcado `entregue`)

1. **Sem privilégio e sem dono** (G4-06, G4-07): seção T4.
2. **Órfão a cada exclusão** (G4-09). `objetos.apagar()` abre `db.db()` **sem contexto de
   inquilino**; a política `p_arquivo` (`tenant_id = plat.tenant_atual()`) casa com zero linhas e o
   `UPDATE apagado_em = now()` é engolido em silêncio. Medido fora da API, sem intermediário:

       antes:  linha viva? t
       apagar -> True
       depois: linha viva? t        (esperado: f)
       objeto ainda existe no Garage? False

   Consequência: a varredura de órfãos que o item entrega acusa **toda exclusão legítima** como
   "linha sem objeto", o que torna o sinal inútil:

       GET /api/arquivos/_varredura ->
       {"sem_linha": [], "sem_objeto": [{"classe":"org_logo","sha256":"aa6020...","chave":"demo/org_logo/aa6020....png"}],
        "objetos_no_garage": 0, "linhas_no_banco": 1}

3. **/saude não trata o Garage como obrigatório** (G4-19), como o próprio handoff avisou. Medido em
   execução, forçando a sonda a devolver erro só para o Garage:

       servicos = {'martin':'ausente','titiler':'ausente','garage':'erro','worker':'ok'}
       status = 200      (app/saude.py linha 79: 200 if banco == "ok" else 503)

4. **O que aguentou:** as três recusas do Garage (chave só-leitura não escreve nem apaga, anônimo
   403), travessia de caminho (`classe=../etc` = 422), isolamento entre inquilinos por sha256 (404),
   escopo de token no DELETE. `tests/api/test_arquivos.py` está verde nesta base.

### L0-12-contrato-api-e-limites — REFUTADO (e está marcado `entregue`)

1. **O contrato comitado não é conferido** (G4-01): seção T1.
2. **Não há limite de taxa na API** (G4-14). O portão pede "101ª requisição em 60 s = 429 com
   Retry-After":

       140 GET /api/eu em 0,8 s -> {200: 140}

   O nginx limita só `/api/login` e `/api/login/2fa`.
3. **`Retry-After` não existe no repositório** (G4-16). `docs/CONTRATO_API.md` linha 107 promete
   "429 com `Retry-After`"; `grep -rn "Retry-After" app/ deploy/ tests/` não devolve uma linha —
   `limit_req_status 429` do nginx não emite o cabeçalho. É exatamente o alvo da refutação do item:
   "limite documentado que a API não aplica".
4. **Não existe o teste do contrato** (G4-15). O portão pede "teste que provoca cada código de erro
   e confere o JSON" (12 códigos) e "lint que reprove rota nova sem esquema de resposta". Não há
   `tests/api/test_contrato*.py` nem script de lint. (Medi o lado bom: **0 rotas** sem esquema de
   resposta 2xx hoje — mas nada impede a próxima.)
5. **42501 vira 403 sobre o inquilino** (G4-23). `erro_do_banco` converte qualquer
   `InsufficientPrivilege` — `GRANT` faltando, schema errado, papel mal configurado, tudo defeito de
   servidor — em `403 sem_permissao "operação fora do inquilino da sessão"`. Capturado ao vivo:

       ### ERRO DE BANCO: InsufficientPrivilege pgcode= 42501
       ### msg: permission denied for schema plat
                LINE 1: INSERT INTO plat.papel_privilegio(papel_id, privilegio) VALU...
       -> 403 {"erro":"sem_permissao","mensagem":"operação fora do inquilino da sessão"}

   Pela própria tabela do contrato, 403 é "sem privilégio" do chamador. Aqui o servidor afirma sobre
   o inquilino do usuário um fato que não mediu, e esconde um erro de configuração — foi esse
   disfarce que escondeu o G4-24 por horas.

O que passou: erro sempre JSON com `req_id` (testei 404 de rota inexistente, 404 de uuid malformado,
422 de data fora de ISO, 401 sem sessão, 401 anônimo em `/ogc/records`; nenhum HTML, nenhum
traceback, nenhuma mensagem em inglês); `total` na paginação; `Link: rel="next"` em `/api/itens`;
sem `/v<n>/` na URL; `docs/LIMITES.md` gerado do código e conferido (`tests/unit/test_limites_doc.py`
verde); limite de corpo aplicado (`tests/api/test_limite_corpo.py` verde, 12 casos).

### L0-14-identidade-visual — REFUTADO

Cláusula (a) — "NENHUMA cor ou medida escrita à mão fora dos tokens; varredura reprova literal de
cor em css/js". Medido:

    literais de cor por arquivo (fora de web/estilo/tokens.css e web/vendor/):
      style.css 21 · mapa.css 9 · tarefas.css 9 · conteudo.css 4
      js/mapa/estilo.js 9 · js/auth/sessao.js 2 · js/auth/conta.js 1 · js/auth/login.js 1
    total fora dos tokens: 56        (tokens.css tem 48)

A varredura que o portão exige não existe em `tests/` nem no `Makefile`. **G4-21.**

Cláusulas (e) e (g) — página viva `/estilo` e as telas restiladas:

    rota /estilo no OpenAPI: False
    telas HTML do produto: 19   (o portão ainda fala em 9)
    carregam web/estilo/tokens.css: 5 (login, uploads, mapa, aceitar_convite, redefinir_senha)
    sem tokens: grupos, log, organizacao, papeis, tokens, usuarios, app.js*, compartilhado,
                conta, conteudo, conteudo_item, conteudo_lixeira, conexoes, index, tarefas

**G4-22.** Cláusula (b) é a que está de pé: par tipográfico escolhido com motivo escrito, três
papéis (exibição, texto, dado tabular com algarismo de largura fixa), vendorizado com sha256 e
licença OFL-1.1 em `web/vendor/VERSOES.txt`.

---

## (d) Fronteira honesta — o que NÃO foi provado

1. **Nada foi medido contra o schema `plat` de produção.** A regra do laço proíbe, e três trilhas já
   travaram o admin real assim. Todos os números vêm de `plat_tadv4`, criado pelas **mesmas**
   migrações. Onde o achado é de configuração de banco (G4-10: `EXECUTE` de `evento_expurgar` para
   `plat_app`), a ACL de produção precisa ser conferida por quem tem acesso — a da trilha diz
   `plat_tadv4_app=X/postgres` nas duas funções.
2. **G4-10 não tem caminho HTTP conhecido.** Varri `app/` e nenhuma rota nem tarefa chama
   `evento_expurgar`/`log_expurgar`. Não afirmo que um admin de inquilino apaga o rastro pela tela;
   afirmo que o papel da aplicação tem o poder de apagar e que a cláusula literal do portão
   ("`plat_app` não consegue UPDATE/DELETE") não cobre esse poder.
3. **Sem navegador.** `google-chrome headless` quebra nesta máquina. Logo **não medi** a cláusula
   (f) do L0-14 (contraste AA com axe-core em claro e escuro), o foco visível ao teclado, os estados
   dos 6 componentes (cláusula d), a família de ícones (cláusula c) nem qualquer captura de tela dos
   e2e exigidos por L0-07-a e L0-10. O que medi nessas telas foi estrutura de arquivo, não pixel.
4. **`install.sh` não foi executado.** A cláusula "segunda execução = 0 mudanças" do L0-11 não foi
   verificada: rodar o instalador mexeria no ambiente real.
5. **Réplica na 2ª máquina do Garage e taxa MB/s** não foram remedidas (`replication_factor = 1`
   segue sendo decisão de infraestrutura, como o handoff diz).
6. **429 do nginx não foi exercido** — não subi nginx. O que medi foi a API por `TestClient`. A
   ausência de `Retry-After`, essa sim, é do repositório inteiro.
7. **Não rodei a suíte completa** (leva mais de 10 min sob fila): rodei os arquivos dos seis itens
   (48 verdes, 1 vermelho), `test_cruzado.py` e o meu arquivo.
8. **Achado de fora do grupo, entregue ao gerente (G4-24).** `CursorSchemaAmbiente` reescreve `plat.`
   em `execute()` e `callproc()` mas **não em `executemany()`**; `app/auth/rotas_usuarios.py` usa
   `executemany` em `POST` e `PUT /api/papeis`. Efeito medido: em qualquer ambiente isolado
   (`PLAT_SCHEMA != plat` — trilha ou `make homolog`) essas rotas batem no schema de produção e
   levam 42501, disfarçado de 403 pelo G4-23. Com isso, `tests/api/test_cruzado.py` — a varredura
   A→B que prova isolamento em toda rota — termina **`1 failed, 168 errors`**, isto é, a garantia de
   isolamento não é exercida fora de produção. É a mesma família dos consertos c311aa7 (RealDictCursor
   ignorando `PLAT_SCHEMA`) e do tratamento de `bytes` que ainda está em `wt/amc`.

---

## Como reproduzir

    bash /home/dev/plataforma/laco/trilha_ambiente.sh adv4
    cd /home/dev/plataforma/wt/adv4
    set -a; source /home/dev/plataforma/laco/var/trilha/adv4.env; set +a
    venv/bin/pytest tests/api/test_g4_adversario.py -p no:randomly            # 6 passed, 24 xfailed
    venv/bin/pytest tests/api/test_g4_adversario.py -p no:randomly --runxfail # vê a falha real de cada achado
    venv/bin/pytest tests/api/test_eventos.py tests/api/test_cruzado.py -p no:randomly

Apagar a base ao fim:

    sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tadv4 CASCADE; DROP SCHEMA plat_trabalho_tadv4 CASCADE'

A base `plat_tadv4` e os buckets `tadv4-plat-*` do Garage **já foram apagados** ao fim do ataque; a
primeira linha acima recria tudo do zero em cerca de 2 minutos.

Commit deste ataque: **e1ff144** no ramo `wt/adv4`, com um arquivo só —
`tests/api/test_g4_adversario.py`. Este laudo não entrou em commit porque `laco/` não é repositório
git; ele vive em `laco/handoffs/T3/ataque-g4-ADVERSARIO.md`. Nada foi consertado, por regra do papel.

---

## O que é comum aos seis itens

Uma frase: **o guardião existe, e mede a declaração em vez do fato.** A cobertura de evento mede se
a rota está listada num dicionário, não se grava evento (e aceita lista vazia). O contrato mede um
arquivo que ninguém regenera. A cota mede o piso e esquece o teto. A auditoria mede `UPDATE` e
`DELETE` e esquece `DROP TABLE`. O apagar de objeto mede a resposta 204 e não a linha que ficou. Em
cada caso o portão foi escrito na direção certa e a verificação parou um degrau antes do lugar onde
o dano acontece.
