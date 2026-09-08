"""Gera os XLSForms de teste do item L2-07-b em `tests/coleta/xlsforms/` (determinístico; rode de novo para
regravar). Cinco formulários modelados nos exemplos públicos de xlsform.org (tipos básicos com dois idiomas;
relevant + constraint; calculation; cascata de três níveis por choice_filter; repeat), mais um sexto com cálculo
circular, que a importação tem de recusar. Uso: `venv/bin/python tests/coleta/gerar_xlsforms.py`."""

from pathlib import Path

import openpyxl

PASTA = Path(__file__).resolve().parent / "xlsforms"
PT, EN = "label::Português (pt)", "label::English (en)"
CAB = ["type", "name", PT, EN, "hint::Português (pt)", "required", "relevant", "constraint", "constraint_message",
       "calculation", "choice_filter", "appearance", "default"]


def _linha(tipo, nome, pt="", en="", dica="", req="", rel="", cons="", msg="", calc="", filtro="", ap="", padrao=""):
    return [tipo, nome, pt, en, dica, req, rel, cons, msg, calc, filtro, ap, padrao]


def _gravar(nome, survey, choices, titulo, idioma="Português (pt)"):
    wb = openpyxl.Workbook()
    s = wb.active
    s.title = "survey"
    s.append(CAB)
    for linha in survey:
        s.append(linha)
    c = wb.create_sheet("choices")
    colunas_extra = sorted({k for _l, _n, _pt, _en, extras in choices for k in extras})
    c.append(["list_name", "name", PT, EN, *colunas_extra])
    for lista, nome_opcao, pt, en, extras in choices:
        c.append([lista, nome_opcao, pt, en, *[extras.get(k, "") for k in colunas_extra]])
    st = wb.create_sheet("settings")
    st.append(["form_title", "form_id", "version", "default_language"])
    st.append([titulo, nome, "2026090701", idioma])
    PASTA.mkdir(parents=True, exist_ok=True)
    wb.save(PASTA / f"{nome}.xlsx")


def basico():
    survey = [
        _linha("start", "inicio"), _linha("end", "fim"), _linha("username", "usuario"),
        _linha("text", "nome", "Nome do entrevistado", "Respondent name", "Nome completo", "yes"),
        _linha("integer", "idade", "Idade", "Age", "", "yes"),
        _linha("decimal", "altura", "Altura (m)", "Height (m)"),
        _linha("date", "data_visita", "Data da visita", "Visit date", "", "yes"),
        _linha("time", "hora_visita", "Hora da visita", "Visit time"),
        _linha("dateTime", "momento", "Momento exato", "Exact moment"),
        _linha("select_one sim_nao", "aceita", "Aceita participar?", "Agrees to take part?", "", "yes"),
        _linha("select_multiple fontes", "fontes", "Fontes de água", "Water sources", "", "", "", "", "", "", "",
               "minimal"),
        _linha("note", "obrigado", "Obrigado, ${nome}.", "Thank you, ${nome}."),
    ]
    choices = [
        ("sim_nao", "sim", "Sim", "Yes", {}), ("sim_nao", "nao", "Não", "No", {}),
        ("fontes", "poco", "Poço", "Well", {}), ("fontes", "rio", "Rio", "River", {}),
        ("fontes", "rede", "Rede pública", "Public network", {}),
    ]
    _gravar("basico", survey, choices, "Formulário básico")


def regras():
    survey = [
        _linha("integer", "idade", "Idade", "Age", "", "yes", "", ". >= 0 and . < 150", "Idade entre 0 e 149"),
        _linha("select_one sim_nao", "tem_filhos", "Tem filhos?", "Has children?", "", "yes"),
        _linha("integer", "n_filhos", "Quantos filhos?", "How many children?", "", "yes",
               "selected(${tem_filhos}, 'sim')", ". > 0 and . <= 20", "Entre 1 e 20"),
        _linha("text", "email", "E-mail", "E-mail", "", "", "${idade} >= 18", "contains(., '@')",
               "Precisa ter @"),
        _linha("text", "documento", "Documento", "Document", "", "", "", "regex(., '^[0-9]{11}$')",
               "Só dígitos"),
    ]
    choices = [("sim_nao", "sim", "Sim", "Yes", {}), ("sim_nao", "nao", "Não", "No", {})]
    _gravar("regras", survey, choices, "Relevância e restrição")


def calculos():
    survey = [
        _linha("decimal", "largura", "Largura (m)", "Width (m)", "", "yes"),
        _linha("decimal", "comprimento", "Comprimento (m)", "Length (m)", "", "yes"),
        _linha("calculate", "area", "", "", "", "", "", "", "", "round(${largura} * ${comprimento}, 2)"),
        _linha("calculate", "area_ha", "", "", "", "", "", "", "", "${area} div 10000"),
        _linha("integer", "preco_m2", "Preço por m²", "Price per m2"),
        _linha("calculate", "valor", "", "", "", "", "", "", "", "if(${preco_m2} > 0, ${area} * ${preco_m2}, 0)"),
        _linha("note", "resumo", "Área: ${area} m² (${area_ha} ha), valor ${valor}", "Area: ${area}"),
        _linha("select_one faixa", "faixa", "Faixa de área", "Area band", "", "", "", "", "", "", "", "",
               ""),
        _linha("calculate", "faixa_calc", "", "", "", "", "", "", "",
               "if(${area} < 100, 'pequena', if(${area} < 1000, 'media', 'grande'))"),
    ]
    choices = [("faixa", "pequena", "Pequena", "Small", {}), ("faixa", "media", "Média", "Medium", {}),
               ("faixa", "grande", "Grande", "Large", {})]
    _gravar("calculos", survey, choices, "Cálculos")


def cascata():
    survey = [
        _linha("select_one estado", "estado", "Estado", "State", "", "yes"),
        _linha("select_one municipio", "municipio", "Município", "Municipality", "", "yes",
               "${estado} != ''", "", "", "", "estado=${estado}", "minimal"),
        _linha("select_one bairro", "bairro", "Bairro", "Neighbourhood", "", "yes", "${municipio} != ''", "",
               "", "", "municipio=${municipio}", "minimal"),
        _linha("calculate", "regiao", "", "", "", "", "", "", "",
               "pulldata('estado', 'regiao', 'name', ${estado})"),
    ]
    choices = [
        ("estado", "ba", "Bahia", "Bahia", {"regiao": "ne"}), ("estado", "sp", "São Paulo", "Sao Paulo",
                                                              {"regiao": "se"}),
        ("estado", "rs", "Rio Grande do Sul", "Rio Grande do Sul", {"regiao": "s"}),
        ("municipio", "ssa", "Salvador", "Salvador", {"estado": "ba"}),
        ("municipio", "ilh", "Ilhéus", "Ilheus", {"estado": "ba"}),
        ("municipio", "spo", "São Paulo", "Sao Paulo", {"estado": "sp"}),
        ("municipio", "cps", "Campinas", "Campinas", {"estado": "sp"}),
        ("municipio", "poa", "Porto Alegre", "Porto Alegre", {"estado": "rs"}),
        ("bairro", "ssa_pit", "Pituba", "Pituba", {"municipio": "ssa"}),
        ("bairro", "ssa_bar", "Barra", "Barra", {"municipio": "ssa"}),
        ("bairro", "ilh_pon", "Pontal", "Pontal", {"municipio": "ilh"}),
        ("bairro", "spo_pin", "Pinheiros", "Pinheiros", {"municipio": "spo"}),
        ("bairro", "cps_cam", "Cambuí", "Cambui", {"municipio": "cps"}),
        ("bairro", "poa_moi", "Moinhos de Vento", "Moinhos de Vento", {"municipio": "poa"}),
    ]
    _gravar("cascata", survey, choices, "Cascata estado, município e bairro")


def repeticao():
    survey = [
        _linha("text", "domicilio", "Identificação do domicílio", "Household id", "", "yes"),
        _linha("begin repeat", "membros", "Membros", "Members"),
        _linha("text", "nome_m", "Nome", "Name", "", "yes"),
        _linha("integer", "idade_m", "Idade", "Age", "", "yes", "", ". >= 0 and . < 150", "0 a 149"),
        _linha("select_one sim_nao", "trabalha", "Trabalha?", "Works?", "", "", "${idade_m} >= 14"),
        _linha("end repeat", ""),
        _linha("calculate", "n_membros", "", "", "", "", "", "", "", "count(${membros})"),
        _linha("calculate", "soma_idades", "", "", "", "", "", "", "", "sum(${membros}/idade_m)"),
        _linha("note", "resumo", "${n_membros} membros, soma das idades ${soma_idades}", "Summary"),
    ]
    choices = [("sim_nao", "sim", "Sim", "Yes", {}), ("sim_nao", "nao", "Não", "No", {})]
    _gravar("repeticao", survey, choices, "Domicílio com membros")


def campo_odk():
    """Sétimo formulário, do item L2-07-e: o que uma equipe coleta no ODK Collect e nós puxamos do Central —
    identificação, geopoint, foto (o binário vem por /attachments), grupo (que o OData aninha) e repetição."""
    survey = [
        _linha("start", "inicio"), _linha("end", "fim"),
        _linha("text", "ponto", "Identificação do ponto", "Point id", "", "yes"),
        _linha("geopoint", "local", "Posição", "Position"),
        _linha("begin group", "detalhe", "Detalhes", "Details"),
        _linha("integer", "arvores", "Árvores contadas", "Trees counted", "", "", "", ". >= 0", "Nunca negativo"),
        _linha("select_one estado_ponto", "estado_ponto", "Estado do ponto", "Point condition"),
        _linha("end group", ""),
        _linha("image", "foto", "Foto do ponto", "Point photo"),
        _linha("begin repeat", "amostras", "Amostras", "Samples"),
        _linha("text", "codigo_a", "Código", "Code", "", "yes"),
        _linha("decimal", "peso_a", "Peso (kg)", "Weight (kg)"),
        _linha("end repeat", ""),
    ]
    choices = [("estado_ponto", "bom", "Bom", "Good", {}), ("estado_ponto", "ruim", "Ruim", "Bad", {})]
    _gravar("campo_odk", survey, choices, "Coleta de campo (ODK)")


def circular():
    survey = [
        _linha("integer", "base", "Base", "Base"),
        _linha("calculate", "a", "", "", "", "", "", "", "", "${b} + 1"),
        _linha("calculate", "b", "", "", "", "", "", "", "", "${c} + 1"),
        _linha("calculate", "c", "", "", "", "", "", "", "", "${a} + ${base}"),
    ]
    _gravar("circular", survey, [], "Cálculo circular")


if __name__ == "__main__":
    for f in (basico, regras, calculos, cascata, repeticao, campo_odk, circular):
        f()
    print("gravados em", PASTA)
