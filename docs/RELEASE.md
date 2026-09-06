# Processo de release (item L7-15-processo-release)

Versionamento [SemVer 2.0.0](https://semver.org/lang/pt-BR/): `MAJOR.MINOR.PATCH` em `VERSAO` (uma linha,
lida por `app/versao.py::versao()`, exposta no `/saude` e no rodapé de `MANUAL.md`).

- **MAJOR**: quebra de contrato — rota removida/renomeada, campo obrigatório novo sem default, mudança de
  significado de um campo existente, JSON Schema de tipo de item que deixa de aceitar documento antigo sem
  migração (`docs/esquemas/`), coluna/tabela removida sem view de compatibilidade.
- **MINOR**: capacidade nova, compatível — rota nova, campo opcional novo, tipo de item novo, migração só
  ADITIVA (`db/migracoes/NNN_*.sql` que só cria/acrescenta, nunca remove/renomeia o que já existia).
- **PATCH**: correção sem mudar contrato — bug, desempenho, segurança, documentação.
- **Congelamento de esquema por versão menor**: dentro da mesma `MAJOR.MINOR`, nenhuma migração pode alterar
  o SIGNIFICADO de uma coluna/campo já lançado (renomear, mudar tipo incompatível, apertar uma restrição que
  rejeita dado que antes era aceito); isso é sempre MAJOR. Migrações em `db/migracoes/` já são imutáveis por
  convenção da casa (`db/migrar.sh`: sha divergente do aplicado para com código 3) — o congelamento por versão
  é a MESMA disciplina, olhando para o release, não para o arquivo isolado.

## Changelog

Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/): uma seção `## [X.Y.Z] - AAAA-MM-DD` por
versão publicada, com subseções `### Adicionado` / `### Alterado` / `### Corrigido` / `### Segurança` (só as
que tiverem conteúdo). Vive em `CHANGELOG.md`, no TOPO do arquivo do laço (mais recente primeiro) — as
entradas de release e as entradas "por turno do laço" (convenção anterior, ainda em uso enquanto o produto não
tem release externo) convivem no mesmo arquivo; uma seção de release nunca substitui a entrada de turno que a
originou, só resume o que dela é EXTERNAMENTE relevante (linguagem de changelog de produto, não de laço).

`scripts/gerar_changelog_release.py` gera o RASCUNHO da seção a partir do `git log` desde a última etiqueta
`vX.Y.Z` (classificação Adicionado/Alterado/Corrigido/Segurança por palavra-chave — heurística, revisão
humana obrigatória antes de colar). Nunca edita `CHANGELOG.md` sozinho.

`scripts/conferir_changelog_releases.sh` audita a correspondência etiqueta↔seção: toda etiqueta `vX.Y.Z` tem
que ter `## [X.Y.Z]` no changelog, e vice-versa — a checagem que a refutação deste item pede explicitamente
("adversário procura no CHANGELOG uma versão sem etiqueta git ou etiqueta sem changelog").

## Checklist de release (o que `scripts/preparar_release.sh` cobre, e o que fica manual)

1. **Testes verdes** — `make check` (escopo verde: lint + `docs/gerar_limites.py --check` + sem-marcador +
   suíte `not lento` + e2e). Automatizado; PARA a release em caso de falha.
2. **Migração aplicada em homologação primeiro** — `make homolog` (item L7-31): schema `plat_homolog`
   separado no mesmo Postgres recebe as MESMAS migrações de forma independente, sobe API+worker temporários e
   roda o e2e isolado contra eles. Automatizado; PARA a release em caso de falha. Regra dura: nenhuma versão
   vai para produção sem ter passado por homologação **com o mesmo pacote** (mesmo sha256) — é por isso que o
   pacote só é montado DEPOIS do `make homolog` passar, nunca antes.
3. **Pacote assinado** — `scripts/assinar_pacote.sh` (item L7-16, Ed25519). Automatizado. O pacote carrega
   `RELEASE_MANIFEST.json` DENTRO do próprio arquivo assinado, e desde 06/09/2026 esse manifesto é EVIDÊNCIA,
   não declaração: para cada etapa (`check`, `homolog`) grava o comando que rodou de verdade, o código de
   saída, quantos testes a saída contou, a duração e o sha256 do log (`var/releases/<versao>.<etapa>.log`).
   Antes os campos eram o texto fixo `"passou"`, escrito sem olhar resultado nenhum: bastava
   `PLAT_RELEASE_CHECK_CMD=true` para um pacote que nunca rodou teste sair "aprovado para produção" (medido
   pelo adversário, achado 5 do laudo `laco/handoffs/T3/ataque-g6-ADVERSARIO.md`).
4. **Ambiente de homologação validado antes de produção** — o mesmo `make homolog` do passo 2 É a validação;
   não há passo separado. O QUE FICA MANUAL: decidir que o resultado do e2e de homologação foi bom o
   suficiente para prosseguir (o script não julga qualidade de resultado, só pass/fail de exit code).
5. **Revisar e colar o changelog** — manual (rascunho pronto no passo anterior).
6. **Publicar** — `scripts/publicar_release.sh <pacote>`: confere assinatura + evidência do manifesto +
   piso de versão e, só se os três baterem, aprova o pacote para produção. Não roda `install.sh` sozinho
   (root, domínio e a decisão de QUANDO tirar o site do ar por alguns segundos são sempre humanas). Saídas:
   `4` assinatura (pacote alterado, RENOMEADO ou chave não confiável) · `5` sem `RELEASE_MANIFEST.json` ·
   `6` manifesto sem prova (comando substituído, código != 0, nenhum teste contado, ou formato antigo) ·
   `7` versão repetida ou menor que a última publicada. Cada aprovação é anexada a
   `var/releases_publicados.jsonl` — é esse registro que faz repetição e regressão de versão serem recusadas.

## Hotfix

Ramo `hotfix/X.Y.Z+1` a partir da última tag de produção (nunca da `main` em andamento — um hotfix não carrega
o que ainda está sendo construído). `scripts/preparar_release.sh X.Y.Z+1 --hotfix` recusa rodar fora de um
ramo com esse nome exato. Muda só `PATCH` (a correção não pode mudar contrato — se mudar, não é hotfix, é
release normal na fila).

## Comandos

```
bash scripts/preparar_release.sh 1.2.3            # release normal
bash scripts/preparar_release.sh 1.2.4 --hotfix   # exige estar no ramo hotfix/1.2.4
bash scripts/publicar_release.sh var/releases/plat-1.2.3.tar.gz
bash scripts/conferir_changelog_releases.sh       # auditoria isolada, a qualquer momento
```

`scripts/release.sh` é o mesmo comando que `preparar_release.sh` (alias — nome do portão original do item no
backlog do laço).

```
bash scripts/confiar_chave_release.sh k<16hex> <publica_b64> "nota" --confirmo   # rotação de chave
```

## Cadeia de confiança da atualização (endurecimento de 06/09/2026)

O adversário independente do turno 3 derrubou os três elos. O que vale agora:

| elo | antes (medido pelo adversário) | agora |
|---|---|---|
| quem é confiável | `assinar_pacote.sh` escrevia a própria chave pública em `deploy/chaves_publicas_release.txt`, o mesmo arquivo que a verificação lê | assinar NUNCA escreve na lista com âncora; confiar é o ato explícito de `confiar_chave_release.sh --confirmo`, commitado e revisado |
| lista de confiança | trocável por `PLAT_CHAVES_CONFIAVEIS` ou por `APP_DIR` | dado de instalação, versionado; a variável só ACRESCENTA em ambiente declarado `dev`/`teste`/`homolog`, sempre com aviso em stderr; em produção é ignorada, também com aviso; `APP_DIR` não a alcança |
| o que a assinatura cobre | só os bytes do pacote (o nome e o tamanho no `.sig` podiam mentir) | uma declaração canônica com nome, tamanho, sha256, versão e data; o `.sig` recusa campo fora do formato |
| quem verifica | `PLAT_VERIFICAR_SCRIPT` trocava o verificador por `/bin/true` | a variável não existe mais |
| prova de teste | texto fixo `"passou"` | comando, código de saída, testes contados e sha256 do log |
| repetição/regressão | aceitas, sem registro | recusadas contra `var/releases_publicados.jsonl` (saída 7) |
| etiqueta git | `git tag -a` (anotada); `git tag -v` respondia "no signature found" | `git tag -s` com assinatura SSH derivada da MESMA chave Ed25519 do release, conferida contra `var/releases/allowed_signers`, gerado da lista de confiança |

**A âncora inicial é a única exceção**: numa instalação cuja lista esteja SEM NENHUMA chave, a primeira é
registrada com aviso em stderr — senão não haveria como começar. O repositório do produto ships com a âncora
preenchida e `tests/unit/test_release_seguranca.py` reprova se ela sumir, então em produção esse caminho
nunca está aberto.

**Rotação de chave** (procedimento, não convenção): na máquina que corta o release, gere a chave nova
(`scripts/assinar_pacote.sh` gera na primeira execução, ou `plat_assinatura.py gerar-chave`); leve só o par
`chave_id`/`publica_b64` para o repositório; rode `scripts/confiar_chave_release.sh <id> <publica> --confirmo`;
`git add deploy/chaves_publicas_release.txt && git commit`; distribua ESSA versão assinada com a chave
ANTIGA; só então corte um release com a nova. A chave privada nunca sai da máquina de release.

## Três releases sintéticas (prova do mecanismo)

`tests/unit/test_preparar_release.py` roda os três cenários do portão numa árvore git SINTÉTICA isolada
(nunca na árvore real do produto — evita marcar etiqueta/tag no repositório de verdade a cada rodada de
teste): **patch** (0.1.1 sobre 0.1.0), **minor** (0.2.0), **hotfix** (0.1.2 no ramo `hotfix/0.1.2`), além de
recusa por `make check` falho e recusa de `publicar_release.sh` sobre um pacote sem manifesto. `PLAT_RELEASE_
CHECK_CMD`/`PLAT_RELEASE_HOMOLOG_CMD` trocam `make check`/`make homolog` por comandos rápidos e determinísticos
dentro do teste (a árvore sintética tem seu próprio `Makefile` mínimo) — os comandos REAIS (`make check`,
`make homolog`) são os que o script chama por padrão contra esta árvore de verdade; não fazem parte do teste
automatizado por custarem minutos e disputarem o mesmo `flock` que outras trilhas do laço usam ao mesmo tempo
(ver pendência no handoff do item).
