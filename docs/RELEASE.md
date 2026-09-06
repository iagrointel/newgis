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
   `RELEASE_MANIFEST.json` (versão, commit, quando, `make_check`/`make_homolog` = "passou") DENTRO do próprio
   arquivo assinado — a assinatura cobre o manifesto junto com o resto, então um pacote que nunca passou pelos
   passos 1-2 não tem como ganhar um manifesto "aprovado" válido sem a chave privada do release.
4. **Ambiente de homologação validado antes de produção** — o mesmo `make homolog` do passo 2 É a validação;
   não há passo separado. O QUE FICA MANUAL: decidir que o resultado do e2e de homologação foi bom o
   suficiente para prosseguir (o script não julga qualidade de resultado, só pass/fail de exit code).
5. **Revisar e colar o changelog** — manual (rascunho pronto no passo anterior).
6. **Publicar** — `scripts/publicar_release.sh <pacote>`: confere assinatura + manifesto e, só se os dois
   baterem, aprova o pacote para produção. Não roda `install.sh` sozinho (root, domínio e a decisão de QUANDO
   tirar o site do ar por alguns segundos são sempre humanas). Recusa (saída 4/5/6, causas distintas) qualquer
   pacote que não prove ter passado pela linha inteira — inclusive um assinado à mão, fora de
   `preparar_release.sh`, sem o manifesto.

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
