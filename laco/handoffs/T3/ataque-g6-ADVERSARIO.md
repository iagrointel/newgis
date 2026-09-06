# Ataque adversarial ao grupo G6 (operação) — laudo do adversário independente, turno 3

Data: 06/09/2026. Escopo: 7 itens de L7 que nunca tinham sido atacados por ninguém.
Base própria: `bash laco/trilha_ambiente.sh adv6` (schemas `plat_tadv6`/`plat_trabalho_tadv6`), worktree
`/home/dev/plataforma/wt/adv6` (ramo `wt/adv6`). Nenhum `systemctl restart`, nenhum `pkill`, nenhuma
escrita no schema `plat` de produção. Testes em `tests/adversario/`, todos `xfail(strict=True)`.

    $ set -a; source /home/dev/plataforma/laco/var/trilha/adv6.env; set +a
    $ PYTHONPATH=. venv/bin/pytest tests/adversario -p no:randomly
    4 passed, 30 xfailed in 5.15s

Os 4 que passam são controles do que AGUENTOU (registrados de propósito, para ninguém desfazer).
Os 30 `xfail` são as refutações medidas.

## (a) Veredito item a item

| item | estado declarado | veredito |
|---|---|---|
| L7-16-assinatura-pacote | entregue | **REFUTADO** — pacote forjado é aceito pelo caminho PADRÃO |
| L7-15-processo-release | entregue | **REFUTADO** — pacote sem `make check` nem homologação é "aprovado para produção" |
| L7-31-ambiente-homologacao | entregue | **REFUTADO** — token admin do Garage IDÊNTICO ao de produção; espaço de nomes de dado compartilhado |
| L7-19-segredos-e-certificados | entregue | **REFUTADO** — 2 segredos em claro no `.env`, 2 em claro no `garage.toml` |
| L7-03-b-antivirus-anexos | parcial | **REFUTADO** — polyglot imagem+script passa; qualquer `Content-Type` fora da tabela desliga a varredura |
| L7-14-instalacoes-apt-desta-linha | entregue | **REFUTADO** — portão nunca foi fixado; a "lista fechada" não cobre nginx/certbot/openssl/curl/psql |
| L7-03-f-dependencias-cve-log-correcoes | parcial | **REFUTADO** — 4 dos artefatos do portão não existem (tabela, `CORRECOES.md`, timer, `/status`) |

7 de 7 caem. Dois achados são de segurança real e um terceiro é de segurança em cadeia:
**S1** a assinatura de pacote não impede pacote forjado; **S2** homologação e produção compartilham a
credencial raiz do armazenamento de objetos; **S3** o processo de release aprova para produção um
pacote que ninguém verificou — os três juntos formam uma cadeia de atualização não confiável.

## (b) Suposições transversais — escritas ANTES de olhar item por item

### T1. "Variável de ambiente é detalhe de teste" — **CAIU** (derruba L7-16 e L7-15 juntos)

Os quatro scripts de operação aceitam do ambiente exatamente as decisões que deveriam ser inegociáveis:
`PLAT_CHAVES_CONFIAVEIS` (quem é confiável), `PLAT_VERIFICAR_SCRIPT` (quem verifica),
`PLAT_RELEASE_CHECK_CMD`/`PLAT_RELEASE_HOMOLOG_CMD` (o que conta como teste), `PLAT_ASSINAR_SCRIPT`,
`APP_DIR`. O comentário de `preparar_release.sh` diz "só para teste — nunca use em produção real";
um comentário não é um controle.

### T2. "Quem produz o artefato pode declarar que ele é confiável" — **CAIU**

Duas autoafirmações: `assinar_pacote.sh` escreve a própria chave pública nova no arquivo de confiança
que `verificar_pacote.sh` consulta; `preparar_release.sh` escreve `"make_check": "passou"` como texto
fixo no manifesto que `publicar_release.sh` depois lê como prova. Em ambos os casos a "prova" é
produzida por quem precisa ser provado.

### T3. "Separar por NOME separa de verdade" — **CAIU em três lugares** (derruba L7-31)

O item isola trocando strings: schema `plat`→`plat_homolog`, prefixo de bucket `plat-`→`homolog-plat-`.
Três coisas escapam da troca de nome: (i) o token admin do Garage, que não tem nome de ambiente e é o
MESMO; (ii) os schemas de dado `d_<slug>`, montados por `format()` dentro de função PL/pgSQL em tempo de
execução — texto que o reescritor nunca vê; (iii) `cursor.executemany()` e consulta em `bytes`, que não
passam pelo `execute()` da subclasse.

### T4. "A declaração do cliente define a checagem" — **CAIU** (derruba L7-03-b)

`TIPOS_PERMITIDOS.get(declarado, None)` trata "tipo declarado desconhecido" como "não examinar". Quem
escolhe o `Content-Type` é o remetente. Logo quem decide se a varredura roda é o atacante.

### T5. "O que falta virou pendência no handoff, então o item está entregue" — **CAIU**

Quatro itens estão `entregue` no `estado.json` com cláusulas do portão que nunca foram construídas:
`install.sh --ambiente homolog`, `docs/AMBIENTES.md`, `MemoryPeak` das unidades, `plat segredo
rotacionar` para 5 segredos, `docs/CORRECOES.md`, `plat.vulnerabilidade`, timer diário. O portão de
L7-14 é literalmente o texto "portão a fixar pelo arquiteto no turno em que o item que a pediu entrar"
— e o item está marcado entregue. Um portão não escrito não pode ter sido passado.

### O que aguentou (medido, não presumido)

- A conta Ed25519 em si: 1 byte alterado = saída 4; chave desconhecida = saída 3.
- O reescritor de migração: as 38 migrações atuais saem sem nenhuma ocorrência de `plat` como schema.
- `/proc/<pid>/environ` do `plat-api`: `-r--------`, 0 segredos legíveis por outro usuário.
- `grep -r` do repositório e `journalctl -u plat-api -u plat-worker` pelo `PLAT_SECRET` e pelo token
  do Garage: 0 ocorrências nos dois.
- A cláusula literal do portão de L7-03-b (script puro declarado `image/jpeg`) recusa de verdade.
- Os 7 pacotes de `deploy/pacotes_apt.txt` estão todos instalados.

---

## (c) Um bloco por item, com comando e saída real

### L7-16-assinatura-pacote — REFUTADO

**Refutação literal do item**: "adversário monta pacote assinado com chave própria e tenta instalar;
tenta substituir a chave pública embutida via variável de ambiente ou arquivo de configuração".
As duas passam.

**Achado 1 (grave, segurança): a ferramenta de assinatura torna a própria chave confiável.**
Nenhuma variável de ambiente. Só rodar o script como qualquer usuário:

    $ bash scripts/assinar_pacote.sh /tmp/.../plat-9.9.9.tar.gz
    == gerando par de chaves Ed25519 (primeira execução): .../release_ed25519_priv.pem
    {"chave_id": "kc52462da5588c2ca", ..., "registrada_agora": true}
    chave pública registrada em /home/dev/plataforma/wt/adv6/deploy/chaves_publicas_release.txt
    assinado: .../plat-9.9.9.tar.gz.sig

    $ grep -v '^#' deploy/chaves_publicas_release.txt | grep .
    kc52462da5588c2ca MooaXENtEb6ymj+0n8JSpdsZTVhhI4XGURoc3rFiiYk= gerada em 2026-09-06T15:24:22Z por dev@iagrosat-db-sp

    $ bash scripts/verificar_pacote.sh /tmp/.../plat-9.9.9.tar.gz
    {"aceito": true, "chave_id": "kc52462da5588c2ca", "arquivo": "plat-9.9.9.tar.gz", "tamanho_bytes": 169}
    saida=0

`assinar_pacote.sh` (gerar) e `verificar_pacote.sh` (conferir) leem e escrevem O MESMO arquivo. Não
existe "chave pública embutida no código": existe um arquivo de texto do repositório que a ferramenta
de assinatura sabe escrever. A distribuição prévia da chave nova, que o ADR chama de rotação segura,
é uma convenção humana ("AÇÃO NECESSÁRIA: git add ... e commit"), não um controle.

**Achado 2 (grave, segurança): `PLAT_CHAVES_CONFIAVEIS` troca a lista de confiança.** É a cláusula
literal da refutação do item.

    $ bash scripts/verificar_pacote.sh <pacote>          # lista limpa
    recusado: a chave 'kc52462da5588c2ca' não é confiável nesta versão ...
    saida=3
    $ PLAT_CHAVES_CONFIAVEIS=/tmp/.../minhas_chaves.txt bash scripts/verificar_pacote.sh <pacote>
    {"aceito": true, "chave_id": "kc52462da5588c2ca", ...}
    saida=0

`APP_DIR` tem o mesmo efeito por outro caminho (aponta a raiz inteira, inclusive `deploy/`).

**Achado 3 (médio): o `.sig` não amarra identidade nem validade do pacote.** A assinatura cobre só os
bytes do arquivo; `arquivo` e `tamanho_bytes` do JSON não são assinados e podem mentir:

    $ python3 ...  # reescreve arquivo="plat-0.0.1-inofensivo.tar.gz", tamanho_bytes=1
    $ bash scripts/verificar_pacote.sh <mesmo conteúdo, outro nome>
    {"aceito": true, ...}   saida=0

Não há versão, data, prazo de validade nem lista de revogação no `.sig`. Um pacote assinado uma vez
vale para sempre — é o que sustenta a repetição e a regressão de versão do L7-15.

**Achado 4 (baixo): a hipótese do item prometeu `scripts/empacotar.sh`, `plat-X.Y.Z.tar.zst`,
`MANIFESTO.sha256`, `MANIFESTO.sig` e o comando `plat verificar-pacote`.** Nenhum existe; o empacotador
real (`.tar.gz`, item L7-15) foi escrito por outra trilha, com outro formato.

Testes: `tests/adversario/test_g6_assinatura_pacote.py` (4 xfail + 1 controle).

---

### L7-15-processo-release — REFUTADO

**Refutação literal**: "adversário tenta instalar em produção um pacote que não passou por homologação
(o script tem de recusar)". Não recusa.

**Achado 5 (grave, segurança em cadeia): release completa sem `make check` e sem `make homolog`.**
Árvore git sintética (nunca a real; nenhuma etiqueta criada no repositório do produto):

    $ PLAT_RELEASE_CHECK_CMD=true PLAT_RELEASE_HOMOLOG_CMD=true bash scripts/preparar_release.sh 9.9.9
    == 3/7 make check (escopo verde)
    == 4/7 make homolog
    == 5/7 empacotar
    pacote: .../plat-9.9.9.tar.gz (sha256=6558136a...)
    == 6/7 assinar
    PRONTO — pacote testado em homologação com este sha: 6558136a02310dd6e22fe9b1e044489eeccda5da09497d5f97ed535a0e639028

    $ tar -xzOf var/releases/plat-9.9.9.tar.gz RELEASE_MANIFEST.json
    {"versao": "9.9.9", "commit": "341368a...", "make_check": "passou", "make_homolog": "passou"}

    $ bash scripts/publicar_release.sh var/releases/plat-9.9.9.tar.gz
    {"aceito": true, "chave_id": "k40861ebb41831a5b", ...}
    aprovado para produção: var/releases/plat-9.9.9.tar.gz (sha256=6558136a...)

A frase "PRONTO — pacote testado em homologação" e o campo `make_homolog: passou` são texto fixo escrito
pelo próprio script, sem olhar resultado nenhum. O argumento do handoff — "como a assinatura cobre o
arquivo inteiro, forjar 'passou por homologação' sem a chave privada é impossível" — cai junto com o
achado 1: a chave privada é de quem rodar o script, e ele mesmo a torna confiável.

**Achado 6 (grave, segurança): `PLAT_VERIFICAR_SCRIPT` desliga a verificação de assinatura.**

    $ bash scripts/publicar_release.sh var/releases/plat-9.9.9.tar.gz   # sem a variável
    saida=4
    $ printf '#!/bin/sh\nexit 0\n' > /tmp/.../verificador_falso.sh
    $ PLAT_VERIFICAR_SCRIPT=/tmp/.../verificador_falso.sh bash scripts/publicar_release.sh var/releases/plat-9.9.9.tar.gz
    aprovado para produção: ... (sha256=6558136a...)
    saida=0

**Achado 7 (médio): repetição e regressão de versão são aprovadas.** Com a chave legítima no arquivo de
confiança, publicando 0.2.0 e depois o 0.1.1 antigo:

    -- publica 0.2.0 (versao nova):      aprovado para produção: ... plat-0.2.0.tar.gz   saida=0
    -- DEPOIS publica o 0.1.1 ANTIGO:    aprovado para produção: ... plat-0.1.1.tar.gz   saida=0
    -- e o 0.2.0 de novo (repeticao):    aprovado para produção: ... plat-0.2.0.tar.gz   saida=0
    -- registro de publicacao em disco?  (só os artefatos gerados; nenhum registro do que foi publicado)

Não há piso de versão, nem registro do que já entrou.

**Achado 8 (médio): a etiqueta não é assinada.** A hipótese pede "etiqueta git `vX.Y.Z` assinada";
o script roda `git tag -a` (anotada).

    $ git tag -v v9.9.9
    tagger adv <a@b> ...
    release 9.9.9
    error: no signature found

**Achado 9 (médio): a conferência changelog×etiqueta é AVISO, não portão, e é vazia de conteúdo.**
A etiqueta é criada no passo 7 ANTES da conferência, e a divergência sai com saída 0:

    == 7/7 etiqueta git + conferência changelog×etiqueta
    AVISO: v9.9.9 ainda não tem seção em CHANGELOG.md — cole ... lá antes de publicar

Na árvore real do produto o conferidor passa por vacuidade:

    $ grep -cE '^## \[[0-9]+\.[0-9]+\.[0-9]+\]' CHANGELOG.md      -> 0
    $ grep -cE '^### (Adicionado|Alterado|Corrigido|Segurança)' CHANGELOG.md -> 0
    $ git tag -l 'v*' | wc -l                                     -> 0
    $ cat VERSAO                                                  -> 0.1.0
    $ bash scripts/conferir_changelog_releases.sh
    changelog e etiquetas em dia (0 etiqueta(s))                  saida=0

O portão pede "`CHANGELOG.md` tem a seção da versão com Adicionado/Alterado/Corrigido/Segurança": o
CHANGELOG do produto não usa esse formato em nenhuma linha. O conferidor nunca olha o arquivo `VERSAO`,
e `preparar_release.sh` nunca o escreve — o pacote 9.9.9 carrega `VERSAO` com `0.1.0` dentro:

    $ tar -xzOf var/releases/plat-9.9.9.tar.gz VERSAO
    0.1.0

**Achado 10 (médio): o "mesmo sha" que o portão pede não existe.** O portão manda registrar "o sha do
pacote testado em homologação e o mesmo sha instalado em produção". `make homolog` roda no passo 4,
sobre a árvore de trabalho; o pacote só é montado no passo 5. Nada foi testado a partir do pacote: o
sha impresso é o sha de um arquivo que nasceu depois do teste.

Testes: `tests/adversario/test_g6_processo_release.py` (6 xfail).

---

### L7-31-ambiente-homologacao — REFUTADO

**Refutação literal**: "adversário procura qualquer caminho pelo qual homologação alcança dado de
produção (DSN, bucket, token) e tenta abrir homolog sem a senha básica". Achei o caminho do token.

**Achado 11 (grave, segurança): o token admin do Garage é o MESMO nos dois ambientes.**
O portão diz "produção e homologação nunca compartilham banco, bucket, chave ou segredo (teste lê os
dois `.env` e confere)". Não existia esse teste; escrevi o primeiro. Medida:

    sha256 do token de PRODUCAO: e36bc0be9a6500d9
    sha256 do token de HOMOLOG : e36bc0be9a6500d9
    sha256 do token da TRILHA  : e36bc0be9a6500d9

Com o token lido de `var/homolog/homolog.env`, contra a API de administração do Garage (só leitura):

    $ curl -H "Authorization: Bearer $TOKEN_DE_HOMOLOGACAO" http://127.0.0.1:3903/v1/bucket?list
    ... "globalAliases": ["plat-demo"] ... "globalAliases": ["plat-demo2"] ...
    $ curl -H "Authorization: Bearer $TOKEN_DE_HOMOLOGACAO" ".../v1/bucket?id=<plat-demo>"
    aliases: ['plat-demo']
    objetos: 84  bytes: 127026292
    chaves com acesso: [('GKaf69...', {'read': True, 'write': True, 'owner': True}), ('GK3204...', {read-only})]

Quem tem esse token administra o armazenamento inteiro: criar chave S3 com escrita no bucket de
produção é uma chamada. O prefixo de bucket (`homolog-plat-` × `plat-`) separa o caminho, não o poder.
O handoff nomeia o compartilhamento do servidor Garage, mas trata como risco de disco; é uma
credencial raiz compartilhada, e o portão a proíbe com todas as letras.

**Achado 12 (grave): o espaço de nomes do DADO não é separado por ambiente.** As camadas vetoriais não
vivem em `plat.*`: vivem em `d_<slug>`, criado por `format('CREATE SCHEMA IF NOT EXISTS %I ...', 'd_' ||
p_slug)` DENTRO de função PL/pgSQL (`db/migracoes/029_ingestao_vetor.sql`). Esse nome nasce em tempo de
execução — o reescritor de schema nunca vê esse texto. E a homologação semeia os MESMOS slugs de
produção:

    $ sudo -u postgres psql -d iagro_sat -Atc "SELECT id||'|'||slug FROM plat.tenant"
    1|demo   2|demo2   3|plataforma
    $ ... FROM plat_tadv6.tenant
    1|demo   2|demo2   3|plataforma

    $ SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname LIKE 'd\_%'
    d_demo              | plat_app
    d_demo2             | plat_app
    d_plataforma        | plat_app
    d_zt-inq-3ddd92     | plat_tamc_app      <-- criado por ambiente de teste, no mesmo espaço
    d_zt-inq-c410ce     | plat_tgadv_app     <-- idem
    (39 linhas)

Da base de homologação/trilha, com o contexto de inquilino da app:

    -- ambiente de HOMOLOGACAO chama camada_schema_garantir('demo'):
       retornou SEM ERRO   (o schema físico já existe: é o da PRODUÇÃO)
       dono de d_demo: plat_app
    -- o papel da homologação consegue escrever lá?
       InsufficientPrivilege | permission denied for schema d_demo

Duas consequências, ambas ruins: a função de homologação **diz que preparou** um schema que pertence a
produção (falha silenciosa), e a ingestão de camada em homologação **não funciona** justamente para os
inquilinos que a homologação semeia — ou seja, o ambiente onde a release deveria ser ensaiada não
exercita L0-04. Que não vaze dado hoje é mérito do `GRANT` (o papel `plat_homolog_app` não tem USAGE em
`plat` nem em `d_demo`), não do mecanismo que o item afirma ter. Dois ambientes de teste já plantaram
schema nesse espaço compartilhado — a colisão não é hipótese.

**Achado 13 (médio): a reescrita de schema não cobre `executemany()` nem consulta em `bytes`.**
`CursorSchemaAmbiente.execute` só reescreve `isinstance(query, str)`; `cursor.executemany` do psycopg2 é
C e não passa pelo `execute()` da subclasse. Medido na base `plat_tadv6`, com uma tabela-sonda que só
existe lá:

    PLAT_SCHEMA = plat_tadv6
    -- execute() (controle):    OK  -> reescrita funcionou, gravou em plat_tadv6
    -- executemany() (mesmo SQL): ERRO: InsufficientPrivilege permission denied for schema plat
    -- execute() com bytes:       ERRO: InsufficientPrivilege permission denied for schema plat

As duas chamadas reais de `executemany` do produto são `INSERT INTO plat.papel_privilegio` em
`app/auth/rotas_usuarios.py:242` e `:285` — escrita. Num ambiente cujo papel tivesse USAGE em `plat`
(por exemplo qualquer processo que rode como `plat_app` com `PLAT_SCHEMA` apontado para outro lugar),
criar um papel personalizado em homologação gravaria privilégio na tabela de PRODUÇÃO. Também vale para
`execute_values`, que monta a consulta em `bytes`.

**Achado 14 (médio): três cláusulas do portão não têm artefato.**

    $ grep -c -- '--ambiente' install.sh          -> 0
    $ ls docs/AMBIENTES.md                        -> No such file or directory
    $ ls deploy/ | grep -i homolog                -> nginx_homolog.conf   (nenhuma unidade .service)
    $ systemctl list-units 'plat*' --all          -> plat-api, plat-worker, plat-osrm-guarulhos (sem plat-homolog)

Sem unidade systemd não existe `MemoryPeak`; o portão manda medir e registrar consumo de RAM por
unidade, e a medida gravada em `tests/medidas/L7-31-homologacao.json` não a contém. Esse mesmo arquivo
traz `"git_sha": "pendente-do-commit-deste-item"`.

**Achado 15 (médio): `make check` e e2e NÃO passam contra a URL de homologação.** A própria medida do
item registra a última rodada como "1 -> 4 passaram" de 13 testes de tela, e o handoff informa
"23 passaram, 8 falharam, 12 erro". O portão exige que passem.

**Achado 16 (médio): homologação não roda o perfil de produção.** `var/homolog/homolog.env` traz
`PLAT_AMBIENTE=dev`. Cinco pontos do código mudam de comportamento com isso
(`app/auth/comum.py:137` cookie `Secure`, `app/auth/rotas_tokens.py:81` token com validade 0,
`app/auth/sessao.py:83` limites de bloqueio/ociosidade por variável, `app/jobs/agenda.py:74` e
`app/catalogo/tarefas.py:88` relógio simulado). O ambiente que o L7-15 usa como portão antes de
produção não exercita o caminho de produção em autenticação, sessão e token.

**Senha básica**: `deploy/nginx_homolog.conf` não tem nenhuma diretiva `auth_basic`. Não há senha para
burlar; o sítio escuta só `127.0.0.1`. Registro como cláusula do portão não construída (subdomínio DNS +
senha básica), não como acesso remoto aberto.

Testes: `tests/adversario/test_g6_segredos_e_homologacao.py` (4 xfail deste item).

---

### L7-19-segredos-e-certificados — REFUTADO

**Refutação literal**: "adversário lê `/proc/<pid>/environ`, o journal, o `.env`, o `garage.toml` e o
histórico do git à procura de qualquer segredo; qualquer um em claro fora de `/run/credentials` =
refutado". Achei quatro.

**Achado 17 (grave, segurança): dois segredos em claro no `.env` de produção.**

    $ grep -E '^[A-Z_]+=' .env | (classificação por nome, valor não impresso)
      PLAT_DSN                     valor de 79 caracteres EM CLARO   (senha da role plat_app)
      PLAT_GARAGE_ADMIN_TOKEN      valor de 44 caracteres EM CLARO   (token raiz do Garage)

`PLAT_SECRET` e `PLAT_DSN_WORKER` foram migrados; estes dois não. O `PLAT_DSN` é a credencial de banco
que a API usa para tudo, e o token do Garage é a credencial raiz do armazenamento — é o mesmo do
achado 11.

**Achado 18 (grave, segurança): `garage.toml` segue em claro.** A própria hipótese do item diz "token
admin do Garage da prova está em claro em `garage.toml` — corrigir". Não foi corrigido:

    $ stat -c '%a %U:%G' /home/dev/plataforma/pipeline/garage/garage.toml
    600 dev:dev
    $ grep -nE 'admin_token|rpc_secret' garage.toml
    7:rpc_secret = <<VALOR EM CLARO>>
    14:admin_token = <<VALOR EM CLARO>>
    -- legivel por dev sem sudo? SIM

Modo 0600 não protege de nada aqui: todo processo desta máquina roda como `dev`.

**Achado 19 (médio): o credential do systemd é legível por qualquer processo do mesmo usuário.**

    $ sudo ls -la /run/credentials/plat-api.service/
    -r--r-----+ 1 root root 65 ... PLAT_SECRET
    -- leitura como 'dev' sem sudo: LEGIVEL por dev

O handoff já admite isto e o registrou em `docs/SEGURANCA.md`; registro aqui porque é a diferença entre
"segredo fora do `.env`" (verdade) e "segredo isolado" (falso). O ganho real medido é outro e é honesto:
`/proc/<pid>/environ` do `plat-api` está `-r--------` e não vaza para outro usuário, e o journal não tem
o valor.

**Achado 20 (médio): o portão pede rotação dos 5 segredos; existem 2.**

    $ grep 'uso:' scripts/rotacionar_segredo.sh
    # Uso: sudo bash scripts/rotacionar_segredo.sh <PLAT_SECRET|PLAT_DSN_WORKER>
    $ which plat            -> (nenhum executável 'plat' no PATH)

Não existe `plat segredo rotacionar` (só uma menção futura no ADR 0002), não existe
`PLAT_SECRET_ANTERIOR` (a dupla chave da hipótese), não existe rotação de chave S3 por inquilino nem do
token admin do Garage, e a cláusula "0 erro 5xx durante a rotação, medido pelo k6 curto" não tem
medida: não há nenhum arquivo com `k6` no repositório.

**Achado 21 (baixo): sem alarme de certificado e sem CA própria.** O portão/hipótese pedem alarme 14 dias
antes (blackbox exporter) e CA do cliente no appliance; existe só `certbot.timer` e conferência manual.

**Espalhamento medido**: o token do Garage está em 12 arquivos fora do repositório, todos legíveis por
`dev` (`laco/var/trilha/*.env` de 10 trilhas + `pipeline/garage/garage.toml`). Dentro do repositório e
no journal: 0 (essa parte do portão aguenta).

Testes: `tests/adversario/test_g6_segredos_e_homologacao.py` (3 xfail deste item).

---

### L7-03-b-antivirus-anexos — REFUTADO

Ataquei o portão FIXADO em 06/09 (não a hipótese antiga). Refutação literal do item: "adversário sobe
polyglot (imagem+script), zip declarado como pdf, e confere que o multipart não abre".

**Achado 22 (grave): o polyglot passa — e o módulo afirma por escrito que não passa.** O docstring de
`app/varredura_conteudo.py` diz: "Isso já cobre o polyglot óbvio do portão: um arquivo com assinatura de
imagem que também é reconhecido como HTML/script continua batendo a checagem". Medido:

    ### controle: a clausula literal do portao (script puro declarado como jpeg)
      recusado | script puro                          declarado=image/jpeg   (text/x-shellscript)
    ### POLYGLOT REAL
      ACEITO   | GIF89a + <script>alert(1)</script>    declarado=image/gif    detectado=image/gif
      ACEITO   | JPEG valido + shell script anexado    declarado=image/jpeg   detectado=image/jpeg
      ACEITO   | PNG valido + PHP anexado              declarado=image/png    detectado=image/png

Quando o arquivo COMEÇA com assinatura de imagem válida, `libmagic` devolve exatamente a família
declarada. A checagem "declarado × detectado" pega o disfarce ingênuo (só o script); não pega o
polyglot, que é o que a refutação pede.

**Achado 23 (grave): qualquer `Content-Type` fora da tabela desliga a varredura inteira.**
`TIPOS_PERMITIDOS.get(declarado, None)` devolve `None` para tipo desconhecido, e `None` significa "não
examinar". O handoff justifica isso só para `application/octet-stream`; vale para tudo:

      ACEITO   | script puro, declarado application/octet-stream  detectado=text/x-shellscript
      ACEITO   | ELF (executavel Linux), octet-stream             detectado=application/x-sharedlib
      ACEITO   | script puro, Content-Type VAZIO                  detectado=text/x-shellscript
      ACEITO   | script puro, declarado text/html                 detectado=text/x-shellscript
      ACEITO   | HTML com script, declarado text/html             detectado=text/html

Quem escolhe o `Content-Type` é o remetente (`app/rotas_arquivos.py:80` lê o cabeçalho, sem lista
branca). Logo quem decide se a varredura roda é o atacante. **Cadeia**: `GET /api/arquivos/{sha256}`
devolve o conteúdo com `media_type=r["content_type"]` (linha 173), sem `Content-Disposition:
attachment` e sem `Content-Security-Policy` no nginx — um arquivo enviado como `text/html` volta
renderizando como HTML na própria origem da aplicação. `X-Content-Type-Options: nosniff` não impede
isso: o tipo declarado É `text/html`.

**Achado 24 (médio): só os primeiros 8 KiB são examinados.**

      ACEITO   | CSV valido de 9 KiB + script no fim   declarado=text/csv   detectado=text/csv

**Achado 25 (médio): contêiner composto não é aberto.**

      ACEITO   | zip com script dentro                 declarado=kmz        detectado=application/zip

O handoff nomeia este limite; registro porque `application/zip` e `kmz` são famílias ACEITAS do portão,
então é por aí que um arquivo executável entra com tipo declarado correto.

ClamAV ausente (D21) é bloqueio declarado e não conta contra o item; os achados 22-25 são da camada que
FOI construída.

Testes: `tests/adversario/test_g6_varredura_anexos.py` (8 xfail + 1 controle).

---

### L7-14-instalacoes-apt-desta-linha — REFUTADO

**Achado 26 (processo): o portão nunca foi fixado e o item está "entregue".** O campo
`portao_de_pronto` no `estado.json` é, hoje: "portão a fixar pelo arquiteto no turno em que o item que a
pediu entrar (registrar aqui antes de construir)". A regra 7 do BRIEF diz que texto de espera reprova.
Um portão não escrito não pode ter sido passado.

**Achado 27 (real): a "lista fechada" não fecha o que `install.sh` exige.**

    $ grep -v '^#' deploy/pacotes_apt.txt | awk 'NF{print $1}'
    python3-uvicorn python3-psycopg2 python3-venv python3-cryptography gdal-bin python3-gdal python3-magic

    $ grep -oE '(nginx|certbot|openssl|curl|psql)' install.sh | sort -u
    certbot curl nginx openssl psql

    $ dpkg -S $(command -v nginx certbot openssl curl psql)
    nginx -> nginx | certbot -> certbot | openssl -> openssl | curl -> curl | psql -> postgresql-client-common

`install.sh` usa `openssl rand` para gerar os segredos (linhas 54, 126, 139, 220), `curl` para conferir
`/saude` (283, 296, 312, 327), `psql` para todas as migrações (32) e reescreve o sítio nginx e o certbot
na seção "i" (336+). Nenhum desses pacotes está na lista. Numa máquina limpa o instalador quebra depois
de já ter criado role, segredo e venv.

**Achado 28 (médio): o caminho que o item construiu nunca foi exercitado.** O handoff admite: os 7
pacotes já estavam instalados, então `apt-get install -y` nunca rodou. Não existe
`tests/medidas/L7-14-instalacoes-apt-desta-linha.json`. "Instalação idempotente" é leitura de código.

**O que aguenta**: os 7 pacotes listados estão de fato instalados (`dpkg-query -W` = install ok
installed nos 7).

Testes: `tests/adversario/test_g6_apt_e_cve.py` (2 xfail + 1 controle deste item).

---

### L7-03-f-dependencias-cve-log-correcoes — REFUTADO

O item está `parcial` com bloqueio declarado; ataquei o portão literal, que continua sendo o do
`estado.json`.

**Achado 29: quatro dos artefatos nomeados no portão não existem.**

    $ ls docs/CORRECOES.md                       -> No such file or directory
    $ SELECT count(*) ... table_name='vulnerabilidade' AND table_schema='plat'   -> 0
    $ ls deploy/*.timer                          -> No such file or directory
    $ systemctl list-timers | grep plat          -> (nenhum)
    $ grep '^check:' Makefile
    check: lint sem-marcador limites teste e2e     <- seguranca-deps fora, por decisão explícita
    $ grep -rn 'vulnerabilidade' app/ web/        -> (nada: /status não mostra ciclo nenhum)

**Achado 30: nenhuma das outras três ferramentas da hipótese existe.**

    osv-scanner  AUSENTE
    trivy        AUSENTE
    gitleaks     AUSENTE

Logo: o histórico do git não tem varredura de segredo (o teste que L7-16 escreveu procura só o cabeçalho
`BEGIN ... PRIVATE KEY` em dois diretórios), e as imagens do compose não têm varredura nenhuma.

**A refutação do item não pode nem ser executada**: "adversário instala pacote com CVE conhecida em
homologação e cronometra até aparecer" — não há timer, não há gravação e o scanner não roda em
homologação. Não há o que cronometrar. O que existe e funciona é `make seguranca-deps` chamado à mão:
1 achado real do dia (`idna==3.13`, PYSEC-2026-215, CVSS 5,3 média), que não bloqueia.

Testes: `tests/adversario/test_g6_apt_e_cve.py` (2 xfail deste item).

---

## (d) Fronteira honesta — o que NÃO foi provado

1. **Não rodei `make homolog` de verdade.** Sobe uvicorn + worker + recarrega nginx numa máquina com
   RAM apertada e outras trilhas ao vivo. As cláusulas de homologação foram medidas pelos artefatos
   (arquivos `.env` reais gravados pelo bootstrap, schemas e papéis no banco), não por uma execução
   nova. O resultado do e2e que cito é o que o próprio item gravou.
2. **Não mutei nada em produção para provar o achado 11.** Provei o alcance do token por leitura
   (`?list` e `?id=`). Criar uma chave S3 com escrita no bucket `plat-demo` é a chamada seguinte da
   mesma API com o mesmo token; não a fiz de propósito. Quem quiser a prova destrutiva precisa da
   autorização do dono.
3. **Achado 13 (executemany) não foi demonstrado gravando em `plat`**, porque o papel da trilha não tem
   USAGE lá — a prova é o erro `permission denied for schema plat`, que mostra para onde a consulta FOI.
   Não testei um papel com privilégio cruzado; seria escrever em produção.
4. **Achado 23 (cadeia até o navegador) foi provado no nível do módulo e da rota** (varredura aceita,
   `media_type` devolvido, ausência de `Content-Disposition` e de CSP), **não num navegador**. Não há
   navegador utilizável nesta máquina.
5. **Não removi pacote apt** para exercitar o caminho de instalação do L7-14 (destrutivo).
6. **Não instalei pacote com CVE em homologação** para cronometrar o L7-03-f: não existe o relógio a
   cronometrar (sem timer, sem gravação).
7. **Appliance sem internet**: não existe appliance. A cláusula "verificar funciona sem rede" foi
   conferida por leitura (nenhum dos 3 arquivos chama rede) e pela execução local, não num equipamento
   isolado de cliente.
8. **`gitleaks` no histórico**: não consegui rodar a ferramenta que o portão nomeia (não é pacote apt e
   não baixei binário). O que afirmo é que ela não existe na máquina, não que o histórico esteja limpo.
9. **Não conferi o subdomínio `homolog.plat.iagrointel.com`** (DNS/nginx público): o sítio de
   homologação escuta só loopback e não há entrada pública para testar.

## Reproduzir

    bash /home/dev/plataforma/laco/trilha_ambiente.sh adv6
    cd /home/dev/plataforma/wt/adv6 && ln -sfn /home/dev/plataforma/enterprise/venv venv
    set -a; source /home/dev/plataforma/laco/var/trilha/adv6.env; set +a
    PYTHONPATH=. venv/bin/pytest tests/adversario -p no:randomly -rxs

Limpar ao fim:

    sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tadv6 CASCADE; DROP SCHEMA plat_trabalho_tadv6 CASCADE'
