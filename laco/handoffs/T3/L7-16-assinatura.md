# Handoff — item L7-16-assinatura-pacote (arquiteto + backend, passagem única)

**Objetivo.** Mecanismo para verificar que uma atualização do produto (tar/zip de release) não foi
adulterada antes de aplicar. Ed25519 via `cryptography` (já dependência do sistema, ADR 0002).
Portão do `estado.json`: assinar/verificar sem rede; 1 byte alterado = recusa; chave privada nunca no
git nem em argv; rotação de chave documentada com período de dupla chave (a pública nova só é aceita
depois de distribuída numa versão assinada com a antiga).

## O que fiz

1. **`scripts/plat_assinatura.py`** (novo): lógica Ed25519 (gerar par, assinar, verificar) com CLI de
   3 subcomandos. `chave_id = "k" + sha256(chave_pública_crua)[:16]` (determinístico, sem contador).
   `.sig` é JSON (`algoritmo`, `chave_id`, `assinatura_b64`, `arquivo`, `tamanho_bytes`).
2. **`scripts/assinar_pacote.sh`** (novo): gera o par de chaves na 1ª execução se
   `PLAT_CHAVE_PRIVADA` não existir (padrão `/etc/plat/chaves/…` como root, ou
   `$HOME/.config/plat/chaves/…` como usuário comum — a assinatura é tarefa de quem corta o release,
   não do appliance), registra a pública em `deploy/chaves_publicas_release.txt`, assina o arquivo.
3. **`scripts/verificar_pacote.sh`** (novo): sem rede, lê o `.sig`, busca `chave_id` no arquivo de
   confiança fixado no repositório, recusa (saída 2/3/4, causas distintas) se a chave é desconhecida,
   o algoritmo não bate, ou a assinatura não confere.
4. **`deploy/chaves_publicas_release.txt`** (novo, versionado): trust store fixo, vazio de propósito
   (nenhuma chave de demonstração comitada — o primeiro release real gera e comita a sua).
5. **`.gitignore`**: `*_priv.pem` e `chaves_privadas/` como defesa em profundidade.
6. **`tests/unit/test_assinatura_pacote.py`** (11 testes): geração de chave + registro de pública;
   pacote correto aceito; 1 byte alterado recusa (e o `.sig` continua válido depois de restaurar o
   byte); sem `.sig` recusa; chave desconhecida recusa mesmo com assinatura matematicamente válida;
   **rotação completa** (pacote assinado com chave nova é recusado por quem só conhece a antiga, e só
   passa a ser aceito depois que a pública nova entra no arquivo de confiança); chave privada nunca
   aparece em nenhum artefato produzido (stdout/stderr/.sig/arquivo de confiança); chave privada nunca
   apareceu no histórico do git (substitui `gitleaks`, indisponível como pacote apt — ver nota);
   scripts não chamam rede; caminho padrão da chave privada fica fora do repositório.
7. Documentação: ADR 0007 §2-4, MANUAL.md §11.5 (novo, comando de uso + códigos de saída),
   ARQUITETURA.md §7.1 (novo), CHANGELOG.md (entrada 0.2.x, turno 3).

## Evidência

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest -q tests/unit/test_assinatura_pacote.py
...........                                                             [100%]
11 passed
$ venv/bin/ruff check scripts/plat_assinatura.py tests/unit/test_assinatura_pacote.py tests/unit/test_pacotes_apt.py
All checks passed!
$ bash -n scripts/assinar_pacote.sh && bash -n scripts/verificar_pacote.sh && echo ok
ok
```

Exemplo manual (fora da suíte, chaves em `/tmp`, nunca no repositório):
```
$ PLAT_CHAVE_PRIVADA=/tmp/priv.pem PLAT_CHAVES_CONFIAVEIS=/tmp/confiaveis.txt bash scripts/assinar_pacote.sh /tmp/pacote.tar
== gerando par de chaves Ed25519 (primeira execução): /tmp/priv.pem
chave pública registrada em /tmp/confiaveis.txt
assinado: /tmp/pacote.tar.sig
$ PLAT_CHAVES_CONFIAVEIS=/tmp/confiaveis.txt bash scripts/verificar_pacote.sh /tmp/pacote.tar
{"aceito": true, "chave_id": "k...", "arquivo": "pacote.tar", "tamanho_bytes": ...}
$ printf '\x00' | dd of=/tmp/pacote.tar bs=1 seek=0 count=1 conv=notrunc 2>/dev/null
$ PLAT_CHAVES_CONFIAVEIS=/tmp/confiaveis.txt bash scripts/verificar_pacote.sh /tmp/pacote.tar; echo "saida=$?"
recusado: assinatura inválida para /tmp/pacote.tar (o arquivo pode ter sido alterado)
saida=4
```

**Cláusula "sem rede"**: nenhum dos 3 arquivos chama `curl`/`wget`/`requests`/`httpx`/`urllib`/`socket`
(`test_scripts_nao_chamam_rede`); a lógica é só I/O de arquivo e conta Ed25519, estruturalmente offline.

**Cláusula "chave privada nunca no git"**: `gitleaks` não é pacote apt nesta distribuição (binário Go
de release do GitHub — fora do mecanismo apt-only do item L7-14); substituí por
`test_chave_privada_nunca_apareceu_no_historico_do_git`, que roda `git log --all -p -- deploy/
scripts/` e confere ausência do cabeçalho `BEGIN … PRIVATE KEY`. Registrado como limite conhecido: a
varredura ampla de segredo/CVE no histórico inteiro é de outra trilha em andamento neste mesmo turno
(`scripts/varredura_dependencias.py`, achado ao rodar `git status`).

## Riscos

- `deploy/chaves_publicas_release.txt` vazio: até alguém cortar o primeiro release real,
  `verificar_pacote.sh` recusa TODO pacote por "chave não confiável" — comportamento seguro por
  padrão, mas exige a ação humana documentada no MANUAL §11.5 antes do primeiro uso real.
- A chave privada PEM não é cifrada com senha (PKCS8 sem `NoEncryption` seria incorreto — é
  `NoEncryption()` mesmo, de propósito, porque a proteção é o arquivo 0600 fora do repositório, não
  uma senha adicional); se o host de assinatura for comprometido, a chave vaza. Mitigação (HSM/KMS)
  fica fora do escopo desta passagem rápida.
- Não implementei revogação de chave (só "confiável"/"desconhecida"); uma chave comprometida exigiria
  remover a linha do arquivo de confiança manualmente — não há uma lista de revogação separada.

## Pendências / para o próximo papel

- Cortar o primeiro release real: rodar `scripts/assinar_pacote.sh` numa máquina de confiança, revisar
  e comitar a linha nova de `deploy/chaves_publicas_release.txt` antes de distribuir qualquer pacote.
- Integrar `scripts/verificar_pacote.sh` ao fluxo real de atualização do appliance (item
  L7-11-appliance-cliente / L7-15-processo-release) — hoje é uma ferramenta de linha de comando
  standalone, ainda não chamada por nenhum passo automático de `install.sh`/atualização.
- Revogação explícita de chave (lista separada de "confiável" vs "revogada", não só ausência de linha).
- Não editei `estado.json` nem o ledger (mesma prudência do `L7-19-segredos.md`, árvore compartilhada
  com outras trilhas ao vivo); este handoff é a fonte para quem for atualizar o item no fechamento.

## `make check`

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/ruff check app tests docs/gerar_limites.py
2 erros — 1 é E501 em app/rotas_arquivos.py (arquivo de OUTRA trilha em andamento, não tocado por
mim); o outro (E501 em test_assinatura_pacote.py) era meu e foi corrigido nesta mesma passagem.
Depois da correção: `ruff check scripts/plat_assinatura.py tests/unit/test_assinatura_pacote.py
tests/unit/test_pacotes_apt.py` → All checks passed.
$ flock ... venv/bin/python docs/gerar_limites.py --check   → exit 0
$ flock ... bash -c '! grep -rnI ... -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md'   → exit 0 (sem marcador em toda a árvore, inclusive arquivos de outras trilhas)
$ flock ... venv/bin/pytest -m "not lento" -q   → 1ª rodada terminou em tempestade de
psycopg2.OperationalError ("the database system is shutting down") nos últimos ~150 testes: outra
trilha reiniciou o Postgres durante a corrida (confirmado: `sudo -u postgres psql` também falhou no
mesmo instante, voltou sozinho 5 s depois). 2ª rodada, com o banco estável — ver nota abaixo.
```

Meus dois arquivos de teste (`test_pacotes_apt.py`, `test_assinatura_pacote.py`) não usam banco (só
arquivo/subprocesso) e passaram 100% das vezes, isolados e dentro da suíte inteira, nas duas rodadas.

## Commit

Um commit único para os dois itens (não dois): `3302f56` — "Pacotes apt da linha e assinatura de
pacote de atualização (itens L7-14 e L7-16)", 14 arquivos, 916 inserções, 10 remoções. Motivo de
juntar em vez de separar: os dois compartilham o mesmo ADR 0007 e, na hora de comitar, as mesmas 3
seções de documentação (`ARQUITETURA.md`, `MANUAL.md`, `CHANGELOG.md`) já estavam sendo editadas ao
vivo por outra trilha (L2-01-a-basemap-local-pmtiles) — isolar a MINHA parte de cada arquivo (técnica
do `L7-19-segredos.md`: reconstruir "só minha" a partir do `HEAD`, `git add`, devolver a versão mista
ao working tree) e depois cortar de novo entre L7-14 e L7-16 dentro do que já era só meu teria
multiplicado o risco de um terceiro choque por pouco ganho (ver `L7-14-apt.md` para o detalhe da
concorrência, incluindo duas sobrescritas acidentais que corrigi antes de comitar). Ver `L7-14-apt.md`
para a nota completa de `make check` e a lista de arquivos de outras trilhas que ficaram de fora do
commit de propósito.
