# Handoff — item L7-03-f-dependencias-cve-log-correcoes (arquiteto + backend, passagem única)

**Objetivo.** Pedido do dono (hoje, escopo reduzido e explícito, não a hipótese inteira do `estado.json`):
scanner de dependência com CVE conhecido rodando sobre `requirements.txt`; `make seguranca-deps` roda o
scanner e falha se achar CVE crítico/alto sem exceção documentada; `docs/SEGURANCA.md` ganha seção "log de
correções" (tabela vazia, formato pronto); alvo novo no `Makefile`, registrado como `check` opcional (**não**
bloqueia o `check` principal ainda).

## Ferramenta escolhida: `pip-audit`, não `safety`

Justificativa medida em 06/09/2026, documentada em `docs/SEGURANCA.md` §7.1: `pip-audit` é PyPA/Apache-2.0,
consulta OSV.dev (aberto, sem chave); `safety` (CLI atual) exige login/API key para o banco de vulnerabilidade
completo (o comando antigo sem conta, `safety check`, está descontinuado pelo próprio projeto). Um scanner que
para de funcionar sem conta paga reprovaria `make seguranca-deps` por motivo errado numa máquina que nunca
cadastrou nada.

## O que fiz

1. **`scripts/varredura_dependencias.py`** (novo): roda `pip-audit -r requirements.txt --format json`; dedup
   de achado duplicado (pip-audit às vezes repete o mesmo id vindo de fontes combinadas); classifica cada
   achado por severidade — 1ª tentativa: rótulo pronto `database_specific.severity` do registro OSV.dev do
   próprio id ou de qualquer alias `GHSA-*` (testado contra o caso real do dia: `PYSEC-2026-215`/idna só tem
   o rótulo no alias GHSA, `"MODERATE"`); sem rótulo, calcula a nota CVSS v3.1 do vetor (fórmula oficial do
   FIRST, implementada e testada contra 3 vetores publicados, inclusive o vetor exato do Log4Shell = 10.0) e
   mapeia ≥9,0 crítica / ≥7,0 alta / ≥4,0 média / abaixo baixa. Sem rótulo E sem CVSS → "desconhecida", tratada
   como grave por padrão-seguro (nunca passa em silêncio). Cache local em `var/cache/osv/<id>.json`
   (gitignorado) evita bater a rede duas vezes pelo mesmo achado.
2. **Exceções**: `docs/excecoes_cve.json` (novo, formato pronto, `excecoes: []`) — uma exceção viva
   (`cve`+`pacote` batendo, `prazo` no futuro) suspende o bloqueio; depois do prazo some sozinha, sem editar
   nada.
3. **`Makefile`**: alvo `seguranca-deps` (novo, adicionado ao `.PHONY`) chama o script e grava
   `var/seguranca/ultima_varredura.json`. **Não** entra em `check`/`check-rapido` nesta passagem — decisão
   explícita registrada em `docs/SEGURANCA.md` §7.4 (rodar `pip-audit` depende de OSV.dev; ligar isso ao
   `check` de todo mundo é o próximo passo natural do item, não deste turno).
4. **`docs/SEGURANCA.md` §7** (novo): justificativa da ferramenta, mecânica da severidade, formato da
   exceção, e §7.5 "log de correções" — tabela vazia (CVE/pacote/versão corrigida/data/quem aplicou), pronta
   para a primeira correção real.
5. **`requirements.txt`**: `pip-audit==2.10.1` + toda a árvore transitiva que ele instalou DENTRO da venv
   (cyclonedx-python-lib, pip-requirements-parser, pip-api, packageurl-python, py-serializable,
   license-expression, boolean.py, CacheControl, defusedxml, filelock, msgpack, platformdirs,
   sortedcontainers, tomli, tomli_w, Markdown) — testado com reinstalação limpa numa venv temporária
   (`/tmp/venv_check_reqs`, apagada depois). `rich`/`requests`/`pygments` (dependências de `pip-audit` que
   ele NÃO instalou na venv) vêm do dpkg já presente nesta máquina (`python3-rich`, `python3-requests`,
   `python3-pygments`) — confirmado que a venv com `PYTHONNOUSERSITE=1` resolve os três em
   `/usr/lib/python3/dist-packages`/`/usr/local/lib/.../dist-packages`, nunca em `~/.local` (checado
   explicitamente, achado que reforça a cláusula "máquina que nunca viu o repo" de `tests/unit/
   test_dependencias.py`).
6. **`tests/unit/test_varredura_dependencias.py`** (novo, 13 testes, todos offline exceto 1 marcado `lento`):
   3 vetores CVSS conhecidos, rótulo pronto via alias GHSA, severidade desconhecida sem dado, exceção
   expirada/viva/pacote-errado, `avaliar()` fim-a-fim com `pip-audit` dublado (a "CVE sintética" do portão —
   um pacote antigo colocado de propósito, sem precisar instalar nada de verdade na venv): reprova sem
   exceção, passa com exceção viva, some do log quando "corrigido" (achado desaparece), severidade
   desconhecida bloqueia. O teste `lento` roda o `pip-audit` de verdade contra o `requirements.txt` do repo.

## Achado real do dia (não bloqueia)

`idna==3.13` tem `PYSEC-2026-215`/`CVE-2026-45409` (DoS por processamento de entrada longa em
`idna.encode()`), corrigido em 3.15. CVSS 3.1 `AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L` = **5,3 (média)** —
confirmado pelo rótulo `"MODERATE"` do GHSA-65pc-fj4g-8rjx. Não crítico/alto: `make seguranca-deps` passa
sem exceção. Registrado aqui, não como correção aplicada (a tabela do §7.5 continua vazia até alguém
efetivamente subir a versão).

## Evidência

```
$ venv/bin/python scripts/varredura_dependencias.py
[      media] idna==3.13  PYSEC-2026-215  fix=['3.15']  (cvss:PYSEC-2026-215=5.3)  ok
varredura_dependencias: nenhum achado grave sem exceção — ok
$ echo $?
0
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_varredura_dependencias.py -m "not lento" -v
...12 passed in 0.04s
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/unit/test_varredura_dependencias.py -m lento -v
...1 passed in 5.72s
$ venv/bin/ruff check scripts/varredura_dependencias.py tests/unit/test_varredura_dependencias.py
All checks passed!
$ flock .../.pytest.lock make check-rapido      # suíte inteira do repositório, com o trabalho concorrente de outras trilhas
lint + sem-marcador + limites + teste: 742 passed, 28 deselected (208.38s)
```

Reinstalação limpa (P5) confirmada numa venv temporária fora do repositório:
```
$ python3 -m venv --system-site-packages /tmp/venv_check_reqs
$ PYTHONNOUSERSITE=1 /tmp/venv_check_reqs/bin/pip install -q -r requirements.txt   # 0 erro
$ /tmp/venv_check_reqs/bin/pip-audit --version   # pip-audit 2.10.1
$ /tmp/venv_check_reqs/bin/pip check              # No broken requirements found.
```

## Riscos e o que fica de fora (não esquecido)

- `make seguranca-deps` ainda não bloqueia `make check`/`check-rapido` (decisão explícita desta passagem,
  §7.4) — depende de rede (OSV.dev); ligar isso é o próximo passo natural.
- A hipótese completa do `estado.json` (osv-scanner, trivy nas imagens do compose, gitleaks no histórico do
  git, tabela `plat.vulnerabilidade`, `docs/CORRECOES.md` separado, timer diário) é maior que o pedido de
  hoje — **gitleaks** já foi coberto por outra trilha (L7-16, varredura própria do histórico do git, sem
  pacote apt nesta distribuição); trivy/osv-scanner ficam para quando o item voltar à fila maior.
- Severidade "desconhecida" trata como grave por padrão-seguro; isso pode um dia bloquear por falta de dado
  do OSV (rede fora), não por CVE real — documentado, não escondido (§7 do doc).
- Não criei ADR novo (seguido o precedente do L7-19: extensão de `docs/SEGURANCA.md`, sem ADR novo para item
  pequeno).
- **Não toquei `CHANGELOG.md`/`ARQUITETURA.md`/`MANUAL.md`**: quando comecei havia outra trilha (L7-14/L7-16,
  mesmo turno) com edições STAGED não comitadas nesses três arquivos; editá-los agora arriscava misturar os
  dois trabalhos num commit só. Ficou só em `docs/SEGURANCA.md` (que nenhuma outra trilha tocou — conferido
  por `git diff --stat` antes de escrever). A outra trilha comitou sozinha como `3302f56` enquanto eu ainda
  trabalhava; meu commit (`d69f417`, `git add` explícito de 12 arquivos, nunca `-A`) ficou limpo, sem
  misturar. Reconciliar CHANGELOG/ARQUITETURA/MANUAL do turno 3 com esta passagem é trabalho do
  gerente/cronista.

## Para o próximo turno

- Ligar `seguranca-deps` ao `check` (ou a um `check-completo` novo) quando o dono aceitar a dependência de
  rede em toda passagem.
- Timer systemd diário (a hipótese original pedia) — nenhum criado nesta passagem (fora do pedido de hoje).
- Se `idna` subir para 3.15 (ou mais), a tabela do §7.5 ganha a primeira linha real.
