"""O vocabulário de escopo tem de conter TODO escopo que alguma rota exige.

Por que este teste existe: a fusão de ramos encolheu `app/auth/escopos.py` duas vezes. Em 10/09 a
expressão regular nasceu concatenada doze vezes; em 11/09, ao publicar a união, faltavam quatro
escopos que rotas vivas exigem — entre eles `conteudo:criar`, sem o qual `POST /api/tokens` recusa e
**o envio de arquivo inteiro fica inacessível**, sem erro nenhum do lado que implementa o envio.

O defeito é silencioso por natureza: quem escreve a rota declara o escopo e nunca descobre que ele
não existe no vocabulário. Este teste fecha o laço lendo as rotas e comparando com as três estruturas
que precisam concordar entre si.
"""
import re
from pathlib import Path

from app.auth import escopos as esc

RAIZ = Path(__file__).resolve().parents[2] / "app"
# `escopo_token="x:y"`, `cobre(..., "x:y")` e `exigir_escopo(..., "x:y")`
USO = re.compile(r'(?:escopo_token\s*=\s*|cobre\([^,]+,\s*|exigir_escopo\([^,]+,\s*)"([a-z_]+:[a-z_]+)"')


def escopos_usados_nas_rotas() -> set[str]:
    achados: set[str] = set()
    for f in RAIZ.rglob("*.py"):
        if f.name == "escopos.py":
            continue
        achados |= set(USO.findall(f.read_text(encoding="utf-8")))
    return achados


def test_toda_rota_usa_escopo_que_existe_no_vocabulario():
    usados = escopos_usados_nas_rotas()
    assert usados, "o varredor não achou escopo nenhum; o padrão de busca quebrou"
    fora = sorted(e for e in usados if not esc.valido(e))
    assert not fora, f"rotas exigem escopo que o vocabulário não tem: {fora}"


def test_as_tres_estruturas_concordam():
    """A expressão regular, a tupla sem uuid e o dicionário de descrição têm de ter o mesmo conjunto."""
    sem_regex = sorted(x for x in esc.ESCOPOS_SEM_UUID if not esc.ESCOPO.match(x))
    assert not sem_regex, f"na tupla mas recusados pela expressão regular: {sem_regex}"
    sem_descricao = sorted(x for x in esc.ESCOPOS_SEM_UUID if x not in esc.DESCRICAO)
    assert not sem_descricao, f"na tupla mas sem descrição: {sem_descricao}"
    sobrando = sorted(x for x in esc.DESCRICAO if x not in esc.ESCOPOS_SEM_UUID)
    assert not sobrando, f"descritos mas fora da tupla: {sobrando}"


def test_conteudo_criar_existe():
    """Guarda explícita do defeito de 11/09: sem ele o envio de arquivo fica inacessível."""
    assert esc.valido("conteudo:criar")
    assert "conteudo:criar" in esc.ESCOPO_EXIGE_PRIVILEGIO
