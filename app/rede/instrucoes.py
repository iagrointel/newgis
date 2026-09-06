"""Resumo em português dos passos (`steps`) que o OSRM devolve no serviço de rota (doc testada
05/09/2026: https://project-osrm.org/docs/v5.24.0/api/#route-service, vocabulário fechado de
`maneuver.type`/`maneuver.modifier`). Item L2-11-c-rota-matriz-isocrona."""

MODIFICADOR_PT = {
    "uturn": "faça o retorno",
    "sharp right": "vire fortemente à direita",
    "right": "vire à direita",
    "slight right": "mantenha-se levemente à direita",
    "straight": "siga em frente",
    "slight left": "mantenha-se levemente à esquerda",
    "left": "vire à esquerda",
    "sharp left": "vire fortemente à esquerda",
}


def _nome_via(step: dict) -> str:
    nome = (step.get("name") or "").strip()
    ref = (step.get("ref") or "").strip()
    if nome and ref and ref not in nome:
        return f"{nome} ({ref})"
    return nome or ref or "via sem nome"


def _distancia_pt(metros: float) -> str:
    if metros < 1000:
        return f"{metros:.0f} m"
    return f"{metros / 1000:.1f} km"


def resumir_passo(step: dict) -> str:
    """Uma frase curta por passo; não é o turn-by-turn completo do OSRM (bearing, lanes, intersections
    ficam de fora deste resumo — portão do item pede só instrução resumida)."""
    m = step.get("maneuver") or {}
    tipo = m.get("type")
    modificador = m.get("modifier")
    via = _nome_via(step)
    dist = _distancia_pt(step.get("distance") or 0.0)

    if tipo == "depart":
        return f"Siga por {via} por {dist}"
    if tipo == "arrive":
        if not modificador or modificador == "straight":
            return "Chegou ao destino"
        return f"Chegou ao destino, {MODIFICADOR_PT.get(modificador, modificador)}"
    if tipo == "roundabout" or tipo == "rotary":
        saida = m.get("exit")
        base = f"Entre na rotatória e saia na {saida}ª saída" if saida else "Entre na rotatória"
        return f"{base}, em {via}, por {dist}" if via != "via sem nome" else f"{base} ({dist})"
    if tipo in ("exit roundabout", "exit rotary"):
        return f"Saia da rotatória em {via}, siga por {dist}"
    if tipo == "roundabout turn":
        return f"Na rotatória, {MODIFICADOR_PT.get(modificador, 'continue')}, {via} ({dist})"
    if tipo == "fork":
        return f"Na bifurcação, {MODIFICADOR_PT.get(modificador, 'siga')}, em direção a {via} ({dist})"
    if tipo == "end of road":
        return f"No fim da via, {MODIFICADOR_PT.get(modificador, 'siga')}, em {via} ({dist})"
    if tipo == "merge":
        return f"Incorpore-se em {via}, {dist}"
    if tipo in ("on ramp", "off ramp", "ramp"):
        return f"Entre na rampa para {via}, {dist}"
    if tipo == "new name":
        return f"Continue, a via passa a se chamar {via}, por {dist}"
    if tipo == "continue":
        if not modificador or modificador == "straight":
            return f"Continue por {via}, por {dist}"
        return f"{MODIFICADOR_PT.get(modificador, 'continue')} em {via}, por {dist}"
    if tipo == "turn":
        return f"{MODIFICADOR_PT.get(modificador, 'Vire')} em {via}, siga por {dist}"
    if tipo == "notification":
        return f"Continue por {via}, por {dist}"
    return f"Siga por {via}, por {dist}"


def resumir_rota(steps: list[dict]) -> list[dict]:
    return [
        {
            "texto": resumir_passo(step),
            "distancia_m": step.get("distance"),
            "duracao_s": step.get("duration"),
            "tipo_osrm": (step.get("maneuver") or {}).get("type"),
        }
        for step in steps
    ]
