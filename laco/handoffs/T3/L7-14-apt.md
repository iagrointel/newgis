# Handoff — item L7-14-instalacoes-apt-desta-linha (arquiteto + backend, passagem única)

**Objetivo.** `install.sh` já conferia por nome (`dpkg -s`) quatro pacotes do sistema e falhava se
algum faltasse, sem instalar nada. Fechar a lista de pacotes apt que o `plat` já exige ou vai exigir
em curto prazo (varredura de `install.sh` + ADRs), consolidar numa lista única e versionada, e trocar
a conferência por instalação idempotente (`apt-get install -y` só no que faltar).

## O que fiz

1. **`deploy/pacotes_apt.txt`** (novo): lista fechada de 7 pacotes — os 4 já exigidos
   (`python3-uvicorn`, `python3-psycopg2`, `python3-venv`, `python3-cryptography`, ADR 0001 §2.1) mais
   3 achados pela varredura dos ADRs: `gdal-bin`/`python3-gdal` (o worker chama `ogrinfo` por
   subprocesso — `app/jobs/worker.py:_versao_gdal`; a venv `--system-site-packages` importa `osgeo`,
   ADR 0001 §2.1/0005) e `python3-magic` (sniff de tipo por conteúdo, ADR 0005 §0.5, item L0-04-a).
   Comentários no arquivo explicam por que `pgRouting`/`pgstac`/FDW (item `L7-14-extensoes-fdw`,
   dono próprio) e `ezdxf`/LibreDWG (decisão D23 do ADR 0005 §12.4 ainda aberta) ficam de fora.
2. **`install.sh`** novo passo "e2" (entre `pg_hba` e a criação da venv): lê a lista com
   `grep -v '^#' | awk '{print $1}'`, roda `dpkg -s` em cada pacote, chama
   `DEBIAN_FRONTEND=noninteractive apt-get install -y` só nos que faltarem, e confere de novo depois
   (falha nomeando o pacote se algum não colar). Idempotente: rodar de novo sem nada faltando não
   chama `apt-get`.
3. **`tests/unit/test_pacotes_apt.py`** (6 testes): arquivo não vazio, os 7 pacotes esperados
   presentes, sem duplicata, `pgRouting`/`pgstac` de fato fora, `install.sh` lê o arquivo de forma
   idempotente (grep no trecho do script), e — o teste que prova a cláusula pedida — cada pacote
   listado está de fato instalado nesta máquina (`dpkg-query -W`).
4. Documentação: ADR 0007 §1 (docs/adr/0007-pacotes-apt-e-assinatura-de-release.md), MANUAL.md §11.2
   (tabela de passos) e §11.5 pendente ficou só para L7-16, ARQUITETURA.md §7 (bullet do que mudou no
   turno) e CHANGELOG.md (entrada 0.2.x, turno 3).

## Evidência

```
$ dpkg-query -W -f='${Status}\n' python3-uvicorn python3-psycopg2 python3-venv python3-cryptography gdal-bin python3-gdal python3-magic
install ok installed   (7×, uma por linha)
$ bash -c 'mapfile -t P < <(grep -v "^\s*#" deploy/pacotes_apt.txt | awk "NF{print \$1}"); echo "${P[*]}"'
python3-uvicorn python3-psycopg2 python3-venv python3-cryptography gdal-bin python3-gdal python3-magic
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest -q tests/unit/test_pacotes_apt.py
......                                                                  [100%]
6 passed
$ bash -n install.sh   # sintaxe
(sem erro)
$ grep -rnI -E -f tests/marcadores.regex deploy/pacotes_apt.txt install.sh MANUAL.md ARQUITETURA.md CHANGELOG.md docs/adr/0007-*.md
(vazio — sem marcador, mesmo grep case-sensível do make check)
```

`apt-get install -y` em si não foi exercitado nesta passagem porque os 7 pacotes já estavam
instalados nesta máquina (nenhum "faltando" para instalar) — a idempotência do passo "e2" foi
provada pela leitura+`dpkg -s` (que é exatamente o que o script roda antes de decidir chamar o
`apt-get`), não por uma instalação de verdade que não havia o que fazer.

## Riscos

- Não testei o caminho "pacote realmente ausente → `apt-get install -y` instala" em execução real
  (exigiria remover um pacote do sistema para testar, destrutivo demais para esta passagem); a lógica
  é a mesma do `for pacote … dpkg -s` que já existia e que o `L0-02`/outros itens já validaram como
  padrão na casa.
- A versão anotada no comentário de cada linha é um RÓTULO (medida nesta máquina em 06/09/2026), não
  um pin do apt — uma imagem/distribuição diferente pode trazer outra revisão do mesmo pacote; isso é
  intencional (quem fixa versão de biblioteca é o `requirements.txt`, ADR 0001 §2.1) mas vale registrar.

## Pendências / para o próximo papel

- `L7-14-extensoes-fdw` continua dona de pgRouting/pgstac/FDW — este item não a toca nem a antecipa.
- Quando o L0-04-e decidir sobre `ezdxf`/LibreDWG (D23, ADR 0005 §12.4), a entrada correspondente
  entra em `deploy/pacotes_apt.txt` no mesmo commit da decisão (comentário já deixa isso escrito).
- Não editei `estado.json` nem o ledger (árvore compartilhada com outras trilhas ao vivo neste turno;
  mesma prudência do handoff `L7-19-segredos.md`) — fica para o gerente consolidar no fechamento.

## `make check` e concorrência de outras trilhas (nota importante)

A árvore foi editada ao vivo por pelo menos 2 outras trilhas durante esta passagem (L2-01-a-basemap-
local-pmtiles no mapa, e uma trilha de varredura de CVE/segredo em `scripts/varredura_dependencias.py`).
Duas vezes o meu próprio `git add`/escrita em `ARQUITETURA.md`/`MANUAL.md`/`CHANGELOG.md` sobrescreveu
por engano uma seção que a outra trilha tinha acabado de acrescentar (mesma árvore, sem worktree
separado); percebi pelas notificações de "arquivo mudou no disco" e corrigi das duas vezes com a
mesma técnica do handoff `L7-19-segredos.md`: reconstruir a versão "só minha" a partir do `HEAD` +
minha edição conhecida, `git add`, e escrever de volta a versão mista (HEAD + minha edição + a deles)
no working tree antes de seguir — confirmado depois do commit que a seção deles (`L2-01-a`) continua
intacta no working tree (`grep` conta 1-3 ocorrências nos três arquivos) e que meus testes passam
contra o `HEAD` novo. Também achei e corrigi uma regressão real minha: `tests/unit/test_instalador.py
::test_instalador_semeia_plataforma_sem_superadmin_nos_demos_e_confere_cryptography` verificava a
string `"python3-cryptography"` literalmente dentro de `install.sh` — deixou de existir aí porque a
lista virou `deploy/pacotes_apt.txt`; reescrevi a asserção para checar as duas pontas (arquivo tem a
linha, `install.sh` lê o arquivo). Durante uma rodada de `pytest` cheguei a ver ~150
`psycopg2.OperationalError` no fim da suíte porque outra trilha reiniciou o Postgres ao vivo
(`the database system is shutting down`, voltou sozinho 5 s depois) — nada meu depende de banco.

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest -q tests/unit/test_pacotes_apt.py tests/unit/test_assinatura_pacote.py tests/unit/test_instalador.py
...............................                                          [100%]
31 passed
```

Duas falhas remanescentes na suíte inteira (`test_hsts_em_todo_bloco_de_add_header_do_modelo`,
`test_referrer_policy_em_todo_bloco_de_add_header_do_modelo`) são causadas por `deploy/nginx.conf` da
trilha do mapa (nova `location` sem os cabeçalhos ainda replicados) — não toquei nesse arquivo, não é
meu escopo, e a própria trilha já estava corrigindo `test_instalador.py` (contagem 4→5) quando
verifiquei pela última vez.

## Commit

`3302f56` — "Pacotes apt da linha e assinatura de pacote de atualização (itens L7-14 e L7-16)" (um
commit único para os dois itens, ver justificativa em `L7-16-assinatura.md`); 14 arquivos, 916
inserções, 10 remoções. Isolado do trabalho concorrente de outras trilhas (confirmado por
`git status`/`git diff --cached --stat` antes do commit).
