"""app/catalogo/narrativa.py (item L5-04-a-blocos-de-conteudo): o que o servidor recusa ao publicar uma narrativa
— imagem sem texto alternativo (portão), endereço de mídia/embed fora do próprio servidor sem https, bloco de
tipo desconhecido, vista de mapa incompleta — e as relações extraídas (mapa e app citados), sem banco."""

from app.catalogo import narrativa
from app.catalogo.documento import gerar_ulid


def _doc(*blocos):
    nos = [{"id": gerar_ulid(), "tipo": t, "propriedades": p, "largura_colunas": 12} for t, p in blocos]
    return {"tipo": "narrativa", "esquema_versao": 1, "corpo": {"nos": nos, "ligacoes": []}}


def test_narrativa_completa_publica():
    d = _doc(("capa", {"titulo": "Título"}), ("texto", {"markdown": "# Olá"}),
             ("imagem", {"url": "/api/objetos/x.png", "alternativo": "uma casa"}),
             ("video", {"url": "https://www.youtube.com/watch?v=abc123def"}), ("audio", {"url": "/api/objetos/a.mp3"}),
             ("mapa", {"vista": {"bbox": [-47, -16, -46, -15], "centro": [-46.5, -15.5], "zoom": 9, "proporcao": 0.6}}),
             ("tabela", {"cabecalho": "a | b", "linhas": "1 | 2"}), ("botao", {"rotulo": "Ir", "url": "https://x.org"}),
             ("separador", {}), ("incorporar", {"url": "https://x.org/e", "titulo": "quadro"}),
             ("aplicativo", {"item_id": "0b7e6a4e-1a0b-4c6e-9d2f-0f1e2d3c4b5a"}))
    assert narrativa.problemas_para_publicar(d) == []


def test_imagem_sem_texto_alternativo_bloqueia_com_mensagem():
    d = _doc(("imagem", {"url": "/api/objetos/x.png", "alternativo": "   "}),
             ("capa", {"titulo": "T", "imagem": "https://x.org/c.jpg"}))
    problemas = narrativa.problemas_para_publicar(d)
    assert [p["campo"] for p in problemas] == ["alternativo", "alternativo"]
    assert "texto alternativo" in problemas[0]["erro"] and problemas[0]["bloco"] == d["corpo"]["nos"][0]["id"]


def test_enderecos_inseguros_e_tipos_desconhecidos_nao_publicam():
    d = _doc(("imagem", {"url": "javascript:alert(1)", "alternativo": "x"}),
             ("video", {"url": "http://inseguro.org/v.mp4"}), ("audio", {"url": "https://fora.org/a.mp3"}),
             ("incorporar", {"url": "http://x.org", "titulo": "t"}), ("botao", {"rotulo": "", "url": "ftp://x"}),
             ("script", {"html": "<script>"}),
             ("mapa", {"vista": {"bbox": [1, 2, 0, 3], "centro": [0, 0], "zoom": 5, "proporcao": 0.5}}),
             ("aplicativo", {"item_id": "nao-uuid"}))
    campos = [(p["tipo"], p["campo"]) for p in narrativa.problemas_para_publicar(d)]
    assert campos == [("imagem", "url"), ("video", "url"), ("audio", "url"), ("incorporar", "url"), ("botao", "url"),
                      ("botao", "rotulo"), ("script", "tipo"), ("mapa", "vista"), ("aplicativo", "item_id")]


def test_relacoes_extraem_mapa_e_aplicativo_na_ordem_dos_blocos():
    mapa = "0b7e6a4e-1a0b-4c6e-9d2f-0f1e2d3c4b5a"
    app = "1c8f7b5f-2b1c-4d7f-8e3a-1a2b3c4d5e6f"
    d = _doc(("texto", {"markdown": "x"}), ("mapa", {"mapa_id": mapa}), ("aplicativo", {"item_id": app}),
             ("mapa", {"mapa_id": mapa}), ("mapa", {}))
    assert narrativa.relacoes(d["corpo"] and d) == [(mapa, "mapa_de_narrativa", 1), (app, "app_de_narrativa", 2)]


def test_corpo_ausente_ou_malformado_nao_quebra():
    assert narrativa.problemas_para_publicar(None) == []
    assert narrativa.problemas_para_publicar({"corpo": {"nos": ["texto", 3, None]}}) == []
    assert narrativa.relacoes({"corpo": {}}) == []
