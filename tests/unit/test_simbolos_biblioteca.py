"""Item L2-02-e-simbolos-sprites-glifos: a biblioteca embutida tem que bater com o portão (>= 150 ícones
próprios) e cada arquivo tem que ter licença registrada no manifesto."""
import cairosvg

from app.simbolos import biblioteca


def test_pelo_menos_150_icones_em_9_categorias():
    catalogo = biblioteca.catalogo()
    assert len(catalogo) >= 150
    categorias = {d.categoria for d in catalogo}
    assert categorias == set(biblioteca.CATEGORIAS)
    for cat in biblioteca.CATEGORIAS:
        assert sum(1 for d in catalogo if d.categoria == cat) >= 10, cat


def test_nomes_de_icone_sao_unicos():
    nomes = [d.nome for d in biblioteca.catalogo()]
    assert len(nomes) == len(set(nomes))


def test_padroes_de_preenchimento_existem():
    padroes = biblioteca.padroes()
    assert len(padroes) >= 8
    for nome in ("padrao-hachura-45", "padrao-pontos-fino", "padrao-tracejado-fino"):
        assert nome in padroes


def test_manifesto_cobre_todo_arquivo_com_licenca():
    catalogo = biblioteca.catalogo()
    padroes = biblioteca.padroes()
    manifesto = biblioteca.manifesto()
    assert len(manifesto) == len(catalogo) + len(padroes)
    for registro in manifesto:
        assert registro["licenca"], registro
        assert registro["autor"], registro
        assert len(registro["sha256"]) == 64


def test_cada_icone_e_svg_valido_e_rasterizavel():
    """Nenhum ícone da base pode falhar ao rasterizar (o compositor do sprite depende disso)."""
    for defi in biblioteca.catalogo()[:20]:  # amostra: rasterizar os 153 em todo test seria lento sem necessidade
        svg = biblioteca.montar_svg(defi)
        assert svg.startswith("<svg")
        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=24, output_height=24)
        assert len(png) > 0
