"""Motor de validação/cálculo do formulário (item L5-03-form-builder) — a metade SERVIDORA do "um só
motor": o desenho (jsonb grupo->campo) usa a MESMA linguagem de expressão do item
L2-10-c-linguagem-expressao (`app/expressao/avaliador_py.py`) que `web/js/formulario/motor.js` usa no
navegador, byte a byte. Este módulo tem duas metades:

  1. `compilar(desenho)` — roda em `publicar_versao` (servico.py), projeta o desenho num formato
     ENXUTO que vira `plat.item.dados` da camada: `regras_campo` (obrigatório estático e domínio,
     MESMA chave que `app/edicao/servico.py::validar_atributos` já lê desde o item L2-03-a — nenhuma
     mudança de esquema aí) mais duas chaves NOVAS, `form_condicionais` e `form_calculados`, lidas
     pelo mesmo `validar_atributos` sem mudar a assinatura (só quando presentes).
  2. `avaliar_condicionais`/`calcular_campos` — o avaliador em si (`avaliar_texto`), chamado tanto por
     `app/edicao/servico.py` (a partir das chaves compiladas acima) quanto por
     `app/campo/servico.py`/`validar_dados_livre` (a partir do DESENHO ao vivo, sem compilar — a
     visita de campo grava `dados` livre, não uma linha de tabela com colunas fixas).

Nenhuma das duas metades faz I/O; quem chama resolve `cur`/tabela antes."""

from __future__ import annotations

from typing import Any

from app.erros import ErroAPI
from app.expressao.avaliador_py import ErroExpressao, analisar, avaliar_texto

WIDGETS = {"texto", "area_texto", "numero", "inteiro", "booleano", "data", "selecao"}


def _avaliar(expressao: str, contexto: dict, onde: str) -> Any:
    try:
        return avaliar_texto(expressao, contexto)
    except ErroExpressao as e:
        raise ErroAPI(
            409, "formulario_expressao_invalida", f"expressão do formulário inválida ({onde}): {e.mensagem}",
            {"expressao": expressao, "onde": onde, "codigo": e.codigo},
        ) from e


def calcular_campos(contexto: dict[str, Any], calculados: dict[str, str], onde: str = "camada") -> dict[str, Any]:
    """{campo: valor} recomputado no servidor — SEMPRE substitui o que o cliente mandou (cláusula 4 do
    portão: "o navegador não é a trava"; um campo calculado nunca é gravado com o valor do cliente)."""
    return {campo: _avaliar(expr, contexto, onde) for campo, expr in (calculados or {}).items()}


def avaliar_condicionais(contexto: dict[str, Any], condicionais: list[dict], onde: str = "camada") -> dict[str, dict]:
    """{campo: {"visivel": bool, "obrigatorio": bool}}. `visivel_se`/`obrigatorio_se` que não avaliam para
    booleano (nulo, erro de tipo por campo ainda vazio) tomam o lado SEGURO: visível e não-obrigatório —
    nunca trava a gravação por causa de uma condição que ainda não tem dado suficiente para decidir."""
    estado: dict[str, dict] = {}
    for c in condicionais or []:
        campo = c["campo"]
        visivel = True
        if c.get("visivel_se"):
            v = _avaliar(c["visivel_se"], contexto, onde)
            visivel = v if isinstance(v, bool) else True
        obrigatorio = bool(c.get("obrigatorio_base")) and visivel
        if c.get("obrigatorio_se"):
            v = _avaliar(c["obrigatorio_se"], contexto, onde)
            obrigatorio = v if isinstance(v, bool) else False
        elif not visivel:
            obrigatorio = False
        estado[campo] = {"visivel": visivel, "obrigatorio": obrigatorio}
    return estado


def compilar(desenho: dict) -> dict:
    """desenho -> {"regras_campo", "form_condicionais", "form_calculados"} (ver cabeçalho do módulo)."""
    regras_campo: dict[str, dict] = {}
    condicionais: list[dict] = []
    calculados: dict[str, str] = {}
    for grupo in desenho.get("grupos") or []:
        for c in grupo.get("campos") or []:
            campo = c.get("campo")
            if not campo or c.get("persistido") is False:
                continue
            regra = regras_campo.setdefault(campo, {})
            tem_condicional = bool(c.get("visivel_se") or c.get("obrigatorio_se"))
            if c.get("obrigatorio") and not tem_condicional:
                regra["obrigatorio"] = True
            if c.get("somente_leitura") or c.get("calculo"):
                regra["somente_leitura"] = True
            dominio = c.get("dominio") or {}
            if dominio.get("valores"):
                regra["dominio_valores"] = dominio["valores"]
            if dominio.get("min") is not None:
                regra["dominio_min"] = dominio["min"]
            if dominio.get("max") is not None:
                regra["dominio_max"] = dominio["max"]
            if tem_condicional:
                condicionais.append({
                    "campo": campo, "visivel_se": c.get("visivel_se"), "obrigatorio_se": c.get("obrigatorio_se"),
                    "obrigatorio_base": bool(c.get("obrigatorio")),
                })
            if c.get("calculo"):
                calculados[campo] = c["calculo"]
    return {"regras_campo": regras_campo, "form_condicionais": condicionais, "form_calculados": calculados}


def validar_desenho(desenho: dict, campos_validos: dict[str, dict]) -> None:
    """422 `formulario_invalido`/`formulario_campo_inexistente`/`formulario_expressao_invalida` — chamado
    ao SALVAR rascunho e de novo ao PUBLICAR (o rascunho pode ficar quebrado enquanto se desenha; publicar
    não pode). `campos_validos` é `{nome: {"nome","tipo","alias"}}`, o mesmo dict que
    `app/edicao/servico.py::validar_atributos` monta de `dados.campos` da camada."""
    if not isinstance(desenho, dict) or not isinstance(desenho.get("grupos"), list):
        raise ErroAPI(422, "formulario_invalido", "desenho precisa ter 'grupos': lista")
    ids_vistos: set[str] = set()
    campos_vistos: set[str] = set()
    for grupo in desenho["grupos"]:
        if not isinstance(grupo, dict) or not grupo.get("id") or not isinstance(grupo.get("campos"), list):
            raise ErroAPI(422, "formulario_invalido", "grupo precisa de 'id' e 'campos': lista")
        if grupo["id"] in ids_vistos:
            raise ErroAPI(422, "formulario_invalido", f"id de grupo repetido: {grupo['id']}")
        ids_vistos.add(grupo["id"])
        for c in grupo["campos"]:
            if not isinstance(c, dict) or not c.get("id"):
                raise ErroAPI(422, "formulario_invalido", "campo do desenho sem 'id'")
            cid = c["id"]
            if cid in ids_vistos:
                raise ErroAPI(422, "formulario_invalido", f"id de campo repetido: {cid}")
            ids_vistos.add(cid)
            if c.get("widget") not in WIDGETS:
                raise ErroAPI(
                    422, "formulario_invalido", f"widget desconhecido: {c.get('widget')!r}", {"campo": cid},
                )
            campo = c.get("campo")
            if not campo or not isinstance(campo, str):
                raise ErroAPI(422, "formulario_invalido", f"campo {cid} sem nome de atributo", {"campo": cid})
            persistido = c.get("persistido", True)
            if persistido:
                if campo not in campos_validos:
                    raise ErroAPI(
                        422, "formulario_campo_inexistente", f"atributo inexistente nesta camada: {campo}",
                        {"campo": campo},
                    )
                if campo in campos_vistos:
                    raise ErroAPI(
                        422, "formulario_invalido", f"atributo repetido no desenho: {campo}", {"campo": campo},
                    )
                campos_vistos.add(campo)
            for chave in ("visivel_se", "obrigatorio_se", "calculo"):
                expr = c.get(chave)
                if expr:
                    try:
                        analisar(expr)
                    except ErroExpressao as e:
                        raise ErroAPI(
                            422, "formulario_expressao_invalida",
                            f"expressão inválida em {cid}.{chave}: {e.mensagem}",
                            {"campo": cid, "propriedade": chave, "expressao": expr, "codigo": e.codigo},
                        ) from e


def validar_dados_livre(desenho: dict, valores: dict[str, Any]) -> tuple[dict, list[str]]:
    """Validação server-side do caminho de CAMPO (`app/campo/servico.py::visita_criar`): `valores` é
    `VisitaCriar.dados`, um jsonb livre (não colunas de tabela) — aqui não há `campos_validos` de camada
    para conferir tipo Postgres, então o contrato é mais simples que `app/edicao/servico.py`: tipo do
    WIDGET (não da coluna), obrigatório/domínio/condicional/cálculo. É o mecanismo que fecha a mesma
    refutação do item ("adversário define campo obrigatório e submete sem ele pela API") para a rota de
    campo, que antes deste item não validava `dados` nenhuma."""
    campos: dict[str, dict] = {}
    for grupo in desenho.get("grupos") or []:
        for c in grupo.get("campos") or []:
            if c.get("campo"):
                campos[c["campo"]] = c
    contexto = {nome: valores.get(nome) for nome in campos}
    limpos: dict[str, Any] = {}
    avisos: list[str] = []
    for nome, c in campos.items():
        valor = contexto.get(nome)
        if c.get("calculo"):
            continue  # recomputado abaixo, cliente nunca decide
        if valor is not None:
            limpos[nome] = valor
    calculados = {nome: c["calculo"] for nome, c in campos.items() if c.get("calculo")}
    if calculados:
        for nome, valor in calcular_campos(contexto, calculados, onde="campo").items():
            limpos[nome] = valor
            contexto[nome] = valor
    condicionais = [
        {"campo": nome, "visivel_se": c.get("visivel_se"), "obrigatorio_se": c.get("obrigatorio_se"),
         "obrigatorio_base": bool(c.get("obrigatorio"))}
        for nome, c in campos.items() if c.get("visivel_se") or c.get("obrigatorio_se")
    ]
    estado = avaliar_condicionais(contexto, condicionais, onde="campo") if condicionais else {}
    for nome, c in campos.items():
        dominio = c.get("dominio") or {}
        valor = limpos.get(nome)
        if valor is not None:
            valores_dominio = dominio.get("valores")
            if valores_dominio is not None and valor not in valores_dominio:
                raise ErroAPI(
                    422, "fora_do_dominio", f"valor fora do domínio do campo {nome}: {valor!r}",
                    {"campo": nome, "valor": valor},
                )
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                if dominio.get("min") is not None and valor < dominio["min"]:
                    raise ErroAPI(422, "fora_do_dominio", f"valor abaixo do domínio do campo {nome}", {"campo": nome})
                if dominio.get("max") is not None and valor > dominio["max"]:
                    raise ErroAPI(422, "fora_do_dominio", f"valor acima do domínio do campo {nome}", {"campo": nome})
        obrigatorio = bool(c.get("obrigatorio")) and nome not in estado
        if nome in estado:
            obrigatorio = estado[nome]["obrigatorio"]
        if obrigatorio and (nome not in limpos or limpos[nome] is None):
            raise ErroAPI(422, "campo_obrigatorio", f"campo obrigatório ausente: {nome}", {"campo": nome})
    for nome in valores:
        if nome not in campos:
            avisos.append(f"campo fora do formulário ignorado: {nome}")
    return limpos, avisos


__all__ = [
    "WIDGETS", "compilar", "validar_desenho", "validar_dados_livre", "avaliar_condicionais", "calcular_campos",
]
