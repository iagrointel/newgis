"""Adversário da linha L4 rede de utilidades (rodada 2) — regressão de merge em `app/rede_utilidades/bdgd.py`
que derruba DOIS itens marcados ENTREGUE ao mesmo tempo: L4-01-g-tarefas-import-tardio e
L4-01-e-dicionario-unidades-bdgd.

Linha do tempo (lida com `git log`/`git show` neste worktree):
  - `01a7fecaa` (item L4-01-g): corrige `bdgd.py` para importar `pyogrio` tardiamente através de uma
    função `_pyogrio()`, e remove o `import pyogrio` do topo do arquivo. `tests/unit/test_dependencias.py`
    (commitado por `d34a99db7`) prova as duas metades do conserto.
  - `04f20ef8b` ("RESGATE: trabalho do agente Kimi preservado" — a própria mensagem diz "preservação,
    não entrega: o portão ainda não foi conferido") sobrescreve `bdgd.py` INTEIRO com uma versão anterior
    ao conserto de L4-01-g: `import pyogrio` de volta ao topo, sem `_pyogrio()`, e também sem a
    integração com `app.rede_utilidades.unidades` (item L4-01-e) que a versão corrigida tinha.
  - A fusão seguinte (`286200aca`, "junção: rebase sobre master, conflitos resolvidos") manteve essa
    versão regredida. `app/rede_utilidades/tarefas.py:105` já chama `bdgd._pyogrio()` — o lado que NÃO
    regrediu — então a cadeia `app.main -> app.agol.rotas -> app.jobs.servico -> app.jobs.tipos ->
    app.rede_utilidades.tarefas -> app.rede_utilidades.bdgd` quebra com `AttributeError` na primeira vez
    que alguém tenta usar essa função que `bdgd.py` não tem mais.

Confirmado ao vivo nesta rodada (`roda_teste.sh tests/unit/test_dependencias.py`, 2026-09-16 06:0x):
`test_app_main_importa_com_pyogrio_ausente` reprova com `ImportError: pyogrio ausente de proposito`
vindo de `import pyogrio` no topo de `bdgd.py`, e `test_pyogrio_vem_da_venv_quando_o_job_pede` reprova
com `AttributeError: module 'app.rede_utilidades.bdgd' has no attribute '_pyogrio'`. Esses dois testes
já existem e já são a prova certa (não são meus); não os toquei — os testes abaixo são uma segunda
prova, estática (sem subprocesso, sem banco), para o gerente confirmar sem depender da trilha.

Reprodução dos testes já existentes (não tocados aqui), para conferência:
    bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_dependencias.py -q
"""

import inspect

from app.rede_utilidades import bdgd


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# O defeito que a marca descrevia caiu em b6b7efdd6 ("fix(L4): restaura _pyogrio() e a integração de
# unidades em bdgd.py"), que desfez a reversão do merge 04f20ef8b. O teste deixa de ser previsão de
# falha e passa a ser guarda de não-regressão do item L4-01-g/L4-01-e.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_bdgd_ainda_tem_a_funcao_de_import_tardio_do_item_l4_01_g():
    """Achado: a função `_pyogrio()` que L4-01-g introduziu (commit 01a7fecaa) não existe mais em
    `bdgd.py` — foi perdida quando o RESGATE do agente Kimi (commit 04f20ef8b) sobrescreveu o arquivo
    inteiro com uma versão anterior ao conserto. `app/rede_utilidades/tarefas.py` já chama
    `bdgd._pyogrio()`, então a falta desta função quebra a importação de `app.main` (ver
    test_dependencias.py::test_pyogrio_vem_da_venv_quando_o_job_pede, que reprova com AttributeError)."""
    assert hasattr(bdgd, "_pyogrio"), (
        "bdgd.py perdeu a função _pyogrio() (import tardio de pyogrio, item L4-01-g) numa regressão de "
        "merge; o import dela voltou a ser 'import pyogrio' no topo do módulo"
    )


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# O defeito que a marca descrevia caiu em b6b7efdd6 ("fix(L4): restaura _pyogrio() e a integração de
# unidades em bdgd.py"), que desfez a reversão do merge 04f20ef8b. O teste deixa de ser previsão de
# falha e passa a ser guarda de não-regressão do item L4-01-g/L4-01-e.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_bdgd_nao_importa_pyogrio_no_topo_do_modulo():
    """Achado, metade 2: mesmo que `_pyogrio()` volte a existir, o item exige que NENHUM `import
    pyogrio` de topo permaneça (é o que prende `import app.main` a um pacote pesado). Hoje `bdgd.py`
    tem os dois ao mesmo tempo: nem topo-livre, nem `_pyogrio()`."""
    fonte = inspect.getsource(bdgd)
    corpo_antes_de_qualquer_funcao = fonte.split("\ndef ", 1)[0]
    assert "import pyogrio" not in corpo_antes_de_qualquer_funcao, (
        "bdgd.py tem 'import pyogrio' no nível do módulo (fora de qualquer função) — regressão do item "
        "L4-01-g: import app.main volta a exigir pyogrio instalado fora da venv"
    )


# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# O defeito que a marca descrevia caiu em b6b7efdd6 ("fix(L4): restaura _pyogrio() e a integração de
# unidades em bdgd.py"), que desfez a reversão do merge 04f20ef8b. O teste deixa de ser previsão de
# falha e passa a ser guarda de não-regressão do item L4-01-g/L4-01-e.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_bdgd_ainda_grava_a_unidade_detectada_na_auditoria_da_importacao():
    """Achado (item L4-01-e-dicionario-unidades-bdgd): a versão de `bdgd.py` restaurada pelo RESGATE do
    Kimi nunca importa `app.rede_utilidades.unidades` nem chama `detectar_comprimento`/
    `detectar_energia`/`consolidar` — a auditoria (`plat.rede_importacao.unidades`) fica sempre NULL
    numa importação nova, embora `app/rede_utilidades/opendss.py`, `resumos.py` e `subredes.py` já leiam
    dela (`unidades.fatores_da_rede`). Confirmado ao vivo: `roda_teste.sh
    tests/api/test_rede_unidades_bdgd.py` reprova 2 e erra 3 dos 5 testes do item nesta rodada."""
    fonte = inspect.getsource(bdgd)
    assert "unidades" in fonte.lower() and "unidades_mod" in fonte, (
        "bdgd.py não referencia mais app.rede_utilidades.unidades (detecção de unidade declarada x "
        "medida); a coluna plat.rede_importacao.unidades nunca é escrita por uma importação nova"
    )
