# Handoff — item L7-15-processo-release (arquiteto + backend, passagem única)

**Objetivo.** Processo de release documentado e parcialmente automatizado: semver, changelog obrigatório por
versão, checklist (testes verdes, migração aplicada em homologação primeiro — reaproveita `make homolog` do
L7-31 —, pacote assinado — reaproveita `scripts/assinar_pacote.sh` do L7-16 —, homologação validada antes de
produção). Portão do backlog nomeia o script `scripts/release.sh`; o pedido que abriu este turno pediu
`scripts/preparar_release.sh` — fiz os dois (o segundo é alias de uma linha do primeiro, nenhuma lógica
duplicada), para o nome exato do portão continuar funcionando.

## O que fiz

1. **`docs/RELEASE.md`** (novo): semver 2.0.0 com regra de congelamento de esquema por versão menor
   (MINOR só migração aditiva; MAJOR pode quebrar), changelog Keep-a-Changelog, checklist completo com o que
   é automatizado e o que fica manual, hotfix (`hotfix/X.Y.Z`), comandos.
2. **`scripts/preparar_release.sh X.Y.Z [--hotfix]`** (novo): valida semver → gera rascunho de changelog do
   `git log` desde a última etiqueta (`scripts/gerar_changelog_release.py`, heurística Adicionado/Alterado/
   Corrigido/Segurança por palavra-chave, NUNCA edita `CHANGELOG.md` sozinho) → `make check` (para com
   código 2 se falhar) → `make homolog` (para com código 3 se falhar) → empacota a árvore num tar
   determinístico (`--sort=name --mtime --owner=0 --transform` tira o prefixo `./`) **com um
   `RELEASE_MANIFEST.json` DENTRO** (versão, commit, `make_check`/`make_homolog` = "passou") → assina
   (`scripts/assinar_pacote.sh`, item L7-16) → cria a etiqueta `vX.Y.Z` → confere changelog×etiqueta → PARA
   (decisão humana: colar o changelog, publicar).
3. **`scripts/publicar_release.sh <pacote>`** (novo): a decisão humana de publicar. Verifica assinatura
   (`scripts/verificar_pacote.sh`) e exige `RELEASE_MANIFEST.json` DENTRO do próprio tar assinado com
   `make_check`/`make_homolog` aprovados — como a assinatura Ed25519 cobre o arquivo inteiro, forjar o
   manifesto sem a chave privada do release é impossível. Três causas de recusa, três códigos (4/5/6). Não
   roda `install.sh` sozinho.
4. **`scripts/conferir_changelog_releases.sh`** (novo): toda etiqueta `vX.Y.Z` tem que ter `## [X.Y.Z]` em
   `CHANGELOG.md` e vice-versa — a refutação literal do portão ("procura no CHANGELOG uma versão sem
   etiqueta git ou etiqueta sem changelog"). Chamado por `preparar_release.sh` (aviso, não bloqueia) e
   sozinho a qualquer momento.
5. **`scripts/gerar_changelog_release.py`** (novo): classificação heurística por palavra-chave da 1ª linha
   do commit; testado indiretamente pelos 3 cenários sintéticos (cada um cai na seção certa).
6. **`scripts/release.sh`** (novo, alias): `exec bash preparar_release.sh "$@"`.

## Evidência

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest -q tests/unit/test_preparar_release.py
.........                                                                [100%]
$ flock ... venv/bin/ruff check scripts/gerar_changelog_release.py tests/unit/test_preparar_release.py
All checks passed!
$ bash -n scripts/preparar_release.sh scripts/publicar_release.sh scripts/release.sh \
    scripts/conferir_changelog_releases.sh && echo ok
ok
$ ! grep -rnI -E -f tests/marcadores.regex <meus arquivos> && echo limpo
limpo
```

**3 releases sintéticas com evidência** (`test_release_patch_minor_e_hotfix_sinteticas_com_evidencia`, árvore
git ISOLADA em `tmp_path`, nunca a árvore real do produto): patch 0.1.1 sobre 0.1.0 (changelog cai em
`### Corrigido`), minor 0.2.0 (cai em `### Adicionado`), hotfix 0.2.1 no ramo `hotfix/0.2.1` a partir da tag
`v0.2.0` (cai em `### Segurança`) — as três com pacote+`.sig`+`RELEASE_MANIFEST.json` conferidos e etiqueta
git criada. `test_hotfix_fora_do_ramo_certo_e_recusado` prova que `--hotfix` sem estar no ramo certo recusa
antes de qualquer coisa.

**Refutação do portão** — as duas peças pedidas: `test_recusa_release_se_make_check_falhar` (`make check`
falho → código 2, nada empacotado, nenhuma etiqueta) É o teste literal exigido pelo item;
`test_publicar_recusa_pacote_sem_manifesto_mesmo_assinado_de_verdade` assina um tar qualquer com o script
REAL de L7-16 (fora da linha de `preparar_release.sh`, nunca rodou `make check`/`homolog`) e confere que
`publicar_release.sh` recusa mesmo com assinatura matematicamente válida (código 5);
`test_publicar_recusa_pacote_adulterado_depois_de_assinado` inverte 1 byte do pacote já preparado e confere
recusa por assinatura (código 4). `test_conferir_changelog_detecta_etiqueta_sem_secao_e_secao_sem_etiqueta`
prova a segunda peça da refutação (achar etiqueta sem changelog E changelog sem etiqueta, os dois sentidos).

## `make check`/`make homolog` de VERDADE contra esta árvore: pendência nomeada, não escondida

Os 9 testes rodam `make check`/`make homolog` de verdade, mas contra uma árvore SINTÉTICA (Makefile mínimo,
alvos controlados por arquivo-gatilho) — decisão explícita para não competir pelo `.pytest.lock`
compartilhado com as ~10 trilhas ao vivo neste turno, e para não marcar uma etiqueta de teste na árvore real
do produto a cada rodada. **Não rodei uma release real (`bash scripts/preparar_release.sh` contra o próprio
`/home/dev/plataforma/enterprise`) nesta passagem** — ficaria a primeira etiqueta `v0.1.0`/`v0.1.1` de
verdade do produto, com `make check`/`make homolog` reais (minutos, sob o mesmo flock que outras trilhas
disputavam). Fica como o passo mais valioso para quem continuar: a mecânica está provada; falta o primeiro
corte de verdade, numa janela com menos concorrência da casa.

## Riscos

- `RELEASE_MANIFEST.json` prova "make check/homolog passou" só no sentido de "o script rodou e o comando saiu
  0" — não carrega o RESULTADO (contagem de teste, cobertura). Quem quiser mais prova audita o log daquele
  `make check`/`make homolog` fora do pacote (não é o que o portão pediu).
- Congelamento de esquema por versão menor (`docs/RELEASE.md`) é uma REGRA documentada, não uma checagem
  automática (não existe hoje um "diff de esquema entre releases" na casa) — fica para quem sentir falta de
  verdade, não construído aqui por não ter sido pedido no portão.
- `scripts/verificar_pacote.sh`/`assinar_pacote.sh` (L7-16) tinham a integração com o fluxo real de release
  como pendência nomeada NO PRÓPRIO handoff daquele item (`L7-16-assinatura.md`) — esta passagem fecha essa
  pendência.

## Para o próximo papel

Rodar o primeiro corte real (`bash scripts/preparar_release.sh 0.1.0` ou a versão que o dono escolher, contra
`/home/dev/plataforma/enterprise`, numa janela tranquila) e revisar/colar o changelog gerado antes de
publicar. Adversário: tentar publicar um pacote assinado com uma chave DIFERENTE da que está em
`deploy/chaves_publicas_release.txt` (rotação, já coberto pelo teste de L7-16, não retestado aqui).

## Commit

`e2d5f91` — "Processo de release: semver, changelog e pacote assinado com prova de homologação (item
L7-15-processo-release)", 7 arquivos novos, 616 inserções. Todos os arquivos eram `??` (não rastreados) no
momento do commit — sem colisão com nenhuma outra trilha.

## Resumo (8 linhas)

`scripts/preparar_release.sh X.Y.Z` roda a linha inteira (semver → changelog → `make check` → `make homolog`
→ empacotar com `RELEASE_MANIFEST.json` embutido → assinar → etiquetar) e para no primeiro erro; falta só a
decisão humana de publicar. `scripts/publicar_release.sh` recusa qualquer pacote sem assinatura válida OU sem
o manifesto aprovado — como a assinatura cobre o arquivo inteiro, forjar "passou por homologação" sem a
chave privada é impossível. `scripts/conferir_changelog_releases.sh` audita etiqueta↔changelog. 9 testes
verdes contra árvore git sintética (3 releases reais: patch/minor/hotfix + 2 recusas do adversário + a
recusa por `make check` falho, exigida pelo portão). `docs/RELEASE.md` documenta tudo. Pendência: primeiro
corte de verdade contra o produto real, numa janela com menos concorrência de flock.
