"""Fluxo de potência do alimentador como serviço da plataforma (item L4-07-fluxo-de-potencia).

O QUE ESTE MÓDULO FAZ. Pega a subrede já gravada, monta o MESMO modelo em memória que os exportadores
OpenDSS, pandapower e MATPOWER usam (`opendss.montar_da_subrede`), escreve o circuito, resolve o fluxo de
potência TRIFÁSICO DESEQUILIBRADO no OpenDSS e grava o estado elétrico por elemento. O motor é o OpenDSS
(EPRI) pela biblioteca `opendssdirect.py` — o mesmo motor que a casa já usava e o que a ANEEL adota para
cálculo de perdas técnicas no Módulo 7 do PRODIST.

Não há segunda conversão: barra, trecho, transformador, chave, carga, geração distribuída e curva de carga
são decididos uma vez só, no conversor. Se o conversor recusa (transformador sem POT_NOM, alimentador sem
TEN_NOM), a análise recusa junto — nunca se resolve um circuito que só compila porque alguém escreveu um
número inventado no lugar do que falta.

DOIS MODOS.

* `anual` (padrão) — os 864 pontos da curva do exportador: 24 horas x 3 tipos de dia (útil, sábado,
  domingo-e-feriado) x 12 meses, cada ponto valendo as horas que aquele bloco tem no ano. É a varredura
  que o Módulo 7 do PRODIST descreve, e é dela que sai a ENERGIA (perda no ano, perda de ferro no ano).
* `hora` — um ponto escolhido da mesma curva (`ponto`, de 0 a 863). Serve para responder "como está o
  alimentador nesta hora deste mês" sem pagar a varredura inteira.

O QUE FICA GRAVADO, e por quê. A varredura anda pelos 864 pontos guardando, ponto a ponto, GRANDEZAS DE
CIRCUITO: convergiu ou não, a carga total, a perda total, a perda de ferro dos transformadores e a tensão
extrema. O estado POR ELEMENTO fica gravado no PONTO CRÍTICO — o ponto de maior carga do ano, que é onde a
tensão é mínima e o carregamento máximo. Guardar cada elemento em cada um dos 864 pontos daria milhões de
linhas por alimentador e a máquina não tem disco para isso (D21). O ponto crítico está identificado no
resultado (mês, tipo de dia, hora), e quem quiser outro ponto pede `modo=hora`.

CONVERGÊNCIA, que é a regra dura do item. Toda execução grava `convergiu` e `pontos_sem_convergencia`, e
nenhuma leitura devolve resultado sem esse par ao lado. O alimentador que não fechou aparece com a marca
e é EXCLUÍDO da agregação de várias execuções (`agregar`), com o nome na lista dos excluídos. Resultado de
alimentador que não convergiu é uma leitura do solver parando, não um estado da rede.

PARÂMETROS, todos declarados e gravados junto do resultado:

* `modo` — `anual` ou `hora`;
* `ponto` — o ponto da curva quando `modo=hora` (0 a 863);
* `ano` — o ano do calendário da curva (define quantos dias úteis, sábados e domingos cada mês tem);
* `fator_de_carga` — multiplicador sobre TODA a carga do circuito (o `Loadmult` do OpenDSS). 1,0 é a carga
  que a energia do arquivo descreve; 1,2 é o mesmo alimentador com 20 % a mais;
* `modelo_de_carga` — como a carga responde à tensão: `potencia_constante` (modelo 1 do OpenDSS),
  `impedancia_constante` (2), `corrente_constante` (5) ou `zip` (8). Com `zip` é OBRIGATÓRIO declarar
  `zipv`, os 7 coeficientes do OpenDSS (%Pz %Pi %Pp %Qz %Qi %Qp Vcutoff): a casa não tem coeficiente ZIP
  medido por classe de consumo, e inventar um mudaria o resultado inteiro em silêncio;
* `tensao_da_fonte_pu` — a tensão imposta na barra da subestação, em por unidade;
* `corrente_nominal_a` — a corrente nominal do TRECHO, usada como denominador do carregamento. É
  REFERÊNCIA DECLARADA, não dado do cadastro: a BDGD não traz catálogo de condutor, e sem esse número não
  existe "carregamento" nenhum. Vem gravada ao lado de todo carregamento de trecho;
* `com_geracao_distribuida` — inclui (padrão) ou desliga a geração distribuída do circuito, para comparar
  o alimentador com e sem ela.

O QUE ESTE MÓDULO NÃO FAZ (limitações medidas, não desculpas):

1. **Impedância de condutor** é a padrão do OpenDSS (0,058 + j0,1206 ohm/km), porque o pacote de ativos não
   tem o catálogo de condutor da BDGD (SEGCON). O mesmo vale para a reatância de dispersão do
   transformador. Está escrito em `NAO_FAZ.md` do exportador e vale igual aqui: a tensão e a corrente
   ordenam trechos e apontam onde olhar; não dimensionam condutor. **Triagem: sinal, não prova.**
2. **Carregamento de trecho** é sobre a corrente nominal declarada em `corrente_nominal_a`, nunca sobre uma
   ampacidade lida do arquivo, que não existe.
3. **Regulador de tensão, banco de capacitor e comutação sob carga** não entram no circuito (o exportador
   não os converte). Num alimentador que tem regulador, a tensão calculada é a de um alimentador SEM ele.
4. **Estado por elemento fora do ponto crítico** não é gravado, pela razão de disco acima.
5. **Ponto de operação da chave** é o do cadastro: chave fechada vira barra única, chave aberta ilha o
   jusante. Não há manobra dentro do OpenDSS (limitação 3 do `NAO_FAZ.md`).

MOTOR GLOBAL, uma armadilha real. O `opendssdirect` conversa com UMA instância do motor por processo: dois
cálculos ao mesmo tempo no mesmo processo misturariam circuitos e devolveriam número de outro alimentador.
Por isso todo acesso ao motor passa por `_TRAVA_MOTOR`, e o caminho pesado (16 alimentadores) é um JOB, que
roda em processo próprio do worker.

Fontes declaradas no item: opendss.epri.com/opendss_documentation.html, dss-extensions.org,
github.com/dss-extensions/OpenDSSDirect.py e o PRODIST Módulo 7 da ANEEL (acesso 2026-09-08).
"""

import json
import math
import resource
import tempfile
import threading
import time
from pathlib import Path

from app.rede_utilidades import opendss

# uma instância do motor OpenDSS por processo: nunca dois cálculos ao mesmo tempo (ver cabeçalho)
_TRAVA_MOTOR = threading.Lock()

MODOS = ("anual", "hora")
MODELOS_DE_CARGA = {
    "potencia_constante": 1,
    "impedancia_constante": 2,
    "corrente_constante": 5,
    "zip": 8,
}
PARAMETROS_PADRAO = {
    "modo": "anual",
    "ponto": None,
    "ano": None,
    "fator_de_carga": 1.0,
    "modelo_de_carga": "potencia_constante",
    "zipv": None,
    "tensao_da_fonte_pu": 1.0,
    "corrente_nominal_a": 400.0,
    "com_geracao_distribuida": True,
}
# quantos pontos sem convergência a execução ainda nomeia um a um (o resto vira só contagem)
MAXIMO_PONTOS_LISTADOS = 50
# tensão em por unidade abaixo da qual o nó é considerado NÃO ENERGIZADO e sai de fora do extremo do
# circuito: um nó ilhado por chave aberta lê ~0 e puxaria a "tensão mínima" para zero em todo alimentador.
PU_MINIMO_ENERGIZADO = 0.01


class ErroFluxo(Exception):
    """Parâmetro que falta ou não fecha, ou motor ausente. Quem chama traduz para o erro da API."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _motor():
    """O OpenDSS, importado tarde de propósito: `app.main` não depende dele para subir, e importar o motor
    tem efeito global no processo. Sem a biblioteca, a falha é ALTA e nomeia o que falta."""
    try:
        import opendssdirect
    except ImportError as e:  # pragma: sem cobertura — a venv do produto tem a biblioteca fixada
        raise ErroFluxo(
            "motor_indisponivel",
            "opendssdirect não está instalado nesta máquina: sem o motor não há fluxo de potência",
        ) from e
    return opendssdirect


def _numero_positivo(valor, nome: str, codigo: str) -> float:
    n = opendss._numero(valor)
    if n is None:
        raise ErroFluxo(codigo, f"{nome} não é número")
    if n <= 0:
        raise ErroFluxo(codigo, f"{nome} tem de ser maior que zero (veio {n})")
    return n


def validar_parametros(pedidos: dict | None) -> dict:
    """Completa o que falta com o padrão e RECUSA o que não fecha. Parâmetro desconhecido é recusado, nunca
    ignorado em silêncio: quem escreveu `fator_carga` em vez de `fator_de_carga` tem de saber que o número
    que voltou não é o que ele pediu."""
    pedidos = dict(pedidos or {})
    sobra = sorted(set(pedidos) - set(PARAMETROS_PADRAO))
    if sobra:
        raise ErroFluxo("parametro_desconhecido",
                        f"parâmetro que este cálculo não conhece: {', '.join(sobra)}")
    p = {**PARAMETROS_PADRAO, **pedidos}

    if p["modo"] not in MODOS:
        raise ErroFluxo("modo_invalido", f"modo deve ser um de {MODOS}")
    if p["modo"] == "hora":
        if p["ponto"] is None:
            raise ErroFluxo("ponto_ausente", "com modo='hora' é preciso dizer qual ponto da curva (0 a 863)")
        try:
            ponto = int(p["ponto"])
        except (TypeError, ValueError) as e:
            raise ErroFluxo("ponto_invalido", "o ponto da curva tem de ser um inteiro") from e
        if not 0 <= ponto < opendss.PONTOS_DA_CURVA:
            raise ErroFluxo("ponto_fora_da_curva",
                            f"o ponto tem de estar entre 0 e {opendss.PONTOS_DA_CURVA - 1}")
        p["ponto"] = ponto
    else:
        p["ponto"] = None

    if p["ano"] is not None:
        try:
            ano = int(p["ano"])
        except (TypeError, ValueError) as e:
            raise ErroFluxo("ano_invalido", "o ano da curva tem de ser um inteiro") from e
        if not 1900 <= ano <= 2200:
            raise ErroFluxo("ano_invalido", "o ano da curva está fora de qualquer calendário plausível")
        p["ano"] = ano

    p["fator_de_carga"] = _numero_positivo(p["fator_de_carga"], "o fator de carga", "fator_de_carga_invalido")
    p["corrente_nominal_a"] = _numero_positivo(
        p["corrente_nominal_a"], "a corrente nominal do trecho", "corrente_nominal_invalida")
    p["tensao_da_fonte_pu"] = _numero_positivo(
        p["tensao_da_fonte_pu"], "a tensão da fonte em por unidade", "tensao_da_fonte_invalida")

    if p["modelo_de_carga"] not in MODELOS_DE_CARGA:
        raise ErroFluxo("modelo_de_carga_invalido",
                        f"modelo de carga deve ser um de {tuple(MODELOS_DE_CARGA)}")
    if p["modelo_de_carga"] == "zip":
        zipv = p["zipv"]
        if not isinstance(zipv, (list, tuple)) or len(zipv) != 7:
            raise ErroFluxo("zipv_ausente",
                            "o modelo ZIP exige os 7 coeficientes em 'zipv' (%Pz %Pi %Pp %Qz %Qi %Qp "
                            "Vcutoff): a casa não tem coeficiente medido por classe de consumo para supor")
        valores = [opendss._numero(v) for v in zipv]
        if any(v is None for v in valores):
            raise ErroFluxo("zipv_invalido", "todos os 7 coeficientes de 'zipv' têm de ser números")
        if abs(sum(valores[0:3]) - 1.0) > 1e-6 or abs(sum(valores[3:6]) - 1.0) > 1e-6:
            raise ErroFluxo("zipv_nao_soma_um",
                            "os coeficientes de potência ativa e os de reativa têm de somar 1 cada")
        p["zipv"] = valores
    elif p["zipv"] is not None:
        raise ErroFluxo("zipv_sem_modelo_zip",
                        "'zipv' só tem sentido com modelo_de_carga='zip'")
    p["com_geracao_distribuida"] = bool(p["com_geracao_distribuida"])
    return p


def descrever_ponto(indice: int) -> dict:
    """O ponto da curva de 864 traduzido para gente: mês (1-12), tipo de dia e hora (0-23). A ordem é a
    mesma que `opendss.curva_864` escreve — mês, depois tipo de dia, depois hora."""
    mes, resto = divmod(int(indice), 72)
    tipo, hora = divmod(resto, 24)
    return {"indice": int(indice), "mes": mes + 1, "tipo_de_dia": opendss.TIPOS_DE_DIA[tipo], "hora": hora}


def _pico_ram_mb() -> int:
    """Pico de memória residente deste processo, em megabytes (`ru_maxrss` vem em kilobytes no Linux)."""
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def _comandos_de_ajuste(parametros: dict) -> list[str]:
    """Os parâmetros do pedido viram comandos do OpenDSS APLICADOS DEPOIS de compilar. O texto do circuito
    fica intacto — é o mesmo que a rota de exportação entrega, e é isso que faz o resultado ser auditável
    contra o arquivo exportado."""
    comandos = [
        f"Vsource.source.pu={parametros['tensao_da_fonte_pu']:.6f}",
        f"Set Loadmult={parametros['fator_de_carga']:.6f}",
        f"BatchEdit Line..* normamps={parametros['corrente_nominal_a']:.4f}",
    ]
    modelo_num = MODELOS_DE_CARGA[parametros["modelo_de_carga"]]
    # a geração distribuída é carga NEGATIVA de corrente constante no exportador; mudar o modelo de carga
    # do consumo não pode mudar o da injeção, então o BatchEdit vale só para as cargas positivas (nome `u*`)
    comandos.append(f"BatchEdit Load.u* model={modelo_num}")
    if parametros["modelo_de_carga"] == "zip":
        vetor = " ".join(f"{v:g}" for v in parametros["zipv"])
        comandos.append(f"BatchEdit Load.u* ZIPV=({vetor})")
    if not parametros["com_geracao_distribuida"]:
        comandos.append("BatchEdit Load.g* enabled=no")
    return comandos


def _abrir_circuito(dss, modelo: dict, parametros: dict, pasta: Path) -> None:
    """Escreve os arquivos do circuito na pasta e compila. Falha alta se o OpenDSS reclamar: um circuito
    que não compila não tem resultado nenhum a devolver."""
    for nome, texto in opendss.linhas_do_circuito(modelo).items():
        (pasta / nome).write_text(texto, encoding="utf-8")
    dss.Text.Command("Clear")
    dss.Text.Command(f'Compile "{pasta / "Master.dss"}"')
    erro = dss.Error.Description()
    if erro:
        raise ErroFluxo("circuito_nao_compila", f"o OpenDSS recusou o circuito exportado: {erro}")
    for comando in _comandos_de_ajuste(parametros):
        dss.Text.Command(comando)
        erro = dss.Error.Description()
        if erro:
            raise ErroFluxo("ajuste_recusado", f"o OpenDSS recusou o ajuste '{comando}': {erro}")


def _perda_de_ferro_w(dss) -> float:
    """Perda de FERRO (a vazio) somada sobre os transformadores, em watts, no ponto resolvido. Vem de
    `Transformers.AllLossesByType`, que devolve, por transformador, seis números: total (re, im), carga
    (re, im) e vazio (re, im). É a parte que não depende do carregamento — e é ela que a conferência do
    item compara com PER_FER x horas do ano."""
    if not dss.Transformers.Count():
        return 0.0
    valores = dss.Transformers.AllLossesByType()
    return sum(valores[i] for i in range(4, len(valores), 6))


def _varrer(dss, parametros: dict, horas: list[float]) -> dict:
    """A varredura: um ponto (modo `hora`) ou os 864 (modo `anual`). Devolve, ponto a ponto, só GRANDEZAS
    DE CIRCUITO, e diz qual é o ponto de maior carga (o ponto crítico) — o estado por elemento é lido lá."""
    indices = [parametros["ponto"]] if parametros["modo"] == "hora" else list(range(len(horas)))
    nao_convergiram: list[int] = []
    energia_perda_kwh = 0.0
    energia_ferro_kwh = 0.0
    energia_carga_kwh = 0.0
    carga_maxima_kw = None
    ponto_critico = indices[0]
    pu_minimo = None
    pu_maximo = None

    for indice in indices:
        dss.Text.Command(f"Set mode=yearly stepsize=1h number=1 hour={indice}")
        dss.Solution.Solve()
        convergiu = bool(dss.Solution.Converged())
        if not convergiu:
            nao_convergiram.append(indice)
            # ponto que não fechou não entra em energia nem em extremo: seria somar a parada do solver
            continue
        horas_do_ponto = horas[indice] if parametros["modo"] == "anual" else 1.0
        perda_w = dss.Circuit.Losses()[0]
        ferro_w = _perda_de_ferro_w(dss)
        carga_kw = -dss.Circuit.TotalPower()[0]
        energia_perda_kwh += perda_w / 1000.0 * horas_do_ponto
        energia_ferro_kwh += ferro_w / 1000.0 * horas_do_ponto
        energia_carga_kwh += carga_kw * horas_do_ponto
        if carga_maxima_kw is None or carga_kw > carga_maxima_kw:
            carga_maxima_kw, ponto_critico = carga_kw, indice
        energizados = [v for v in dss.Circuit.AllBusMagPu() if v > PU_MINIMO_ENERGIZADO]
        if energizados:
            menor, maior = min(energizados), max(energizados)
            pu_minimo = menor if pu_minimo is None else min(pu_minimo, menor)
            pu_maximo = maior if pu_maximo is None else max(pu_maximo, maior)

    return {
        "pontos": len(indices),
        "pontos_sem_convergencia": len(nao_convergiram),
        "pontos_nao_convergidos": nao_convergiram[:MAXIMO_PONTOS_LISTADOS],
        "ponto_critico": ponto_critico,
        "carga_maxima_kw": carga_maxima_kw,
        "tensao_pu_minima": pu_minimo,
        "tensao_pu_maxima": pu_maximo,
        "energia_perdida_kwh": energia_perda_kwh,
        "energia_perda_de_ferro_kwh": energia_ferro_kwh,
        "energia_da_carga_kwh": energia_carga_kwh,
    }


def _elementos_no_ponto(dss, modelo: dict, parametros: dict) -> list[dict]:
    """O estado por elemento no ponto já resolvido: tensão por barra e fase, corrente/carregamento/perda por
    trecho, carregamento/perda/perda de ferro por transformador."""
    perdas_por_elemento = {}
    nomes = dss.Circuit.AllElementNames()
    valores = dss.Circuit.AllElementLosses()
    for i, nome in enumerate(nomes):
        perdas_por_elemento[nome.lower()] = valores[2 * i] / 1000.0  # W -> kW

    linhas: list[dict] = []

    # --- barras: tensão em por unidade, uma linha por fase presente na barra
    kv_por_barra = modelo["barras"]
    # `strict=True` de propósito: se o motor devolvesse listas de tamanhos diferentes, casar nó com tensão
    # pela ordem daria a tensão do vizinho a cada barra, e o mapa sairia bonito e errado.
    pu_por_no = dict(zip([n.lower() for n in dss.Circuit.AllNodeNames()], dss.Circuit.AllBusMagPu(),
                         strict=True))
    for nome_no, pu in pu_por_no.items():
        barra, _, fase = nome_no.partition(".")
        if fase not in ("1", "2", "3"):
            continue  # o neutro (nó 0) não tem tensão de fase a reportar
        linhas.append({
            "tipo": "barra", "elemento": barra, "fase": int(fase), "codigo": None,
            "no_id": _no_id(barra), "feicao_id": None,
            "kv": opendss._numero(kv_por_barra.get(barra)),
            "tensao_pu": round(pu, 6) if pu > PU_MINIMO_ENERGIZADO else None,
            "corrente_a": None, "carregamento_pc": None, "perda_kw": None,
            "perda_ferro_kw": None, "potencia_kva": None,
        })

    # --- trechos: corrente do terminal mais carregado, carregamento sobre a corrente nominal DECLARADA
    nominal = parametros["corrente_nominal_a"]
    por_nome_de_linha = {t["nome"].lower(): t for t in modelo["linhas"]}
    for nome in dss.Lines.AllNames():
        chave = nome.lower()
        trecho = por_nome_de_linha.get(chave)
        dss.Circuit.SetActiveElement(f"Line.{nome}")
        magnitudes = dss.CktElement.CurrentsMagAng()[0::2]
        corrente = max(magnitudes) if magnitudes else None
        linhas.append({
            "tipo": "trecho", "elemento": nome, "fase": None,
            "codigo": None if trecho is None else trecho.get("condutor"),
            "no_id": None, "feicao_id": None if trecho is None else trecho.get("feicao_id"),
            "kv": None, "tensao_pu": None,
            "corrente_a": None if corrente is None else round(corrente, 4),
            "carregamento_pc": None if corrente is None else round(100.0 * corrente / nominal, 4),
            "perda_kw": round(perdas_por_elemento.get(f"line.{chave}", 0.0), 6),
            "perda_ferro_kw": None,
            "potencia_kva": None,
        })

    # --- transformadores: carregamento sobre a POTÊNCIA NOMINAL do arquivo (esse dado existe)
    por_nome_de_trafo = {x["nome"].lower(): x for x in modelo["trafos"]}
    ferro_por_trafo = {}
    if dss.Transformers.Count():
        nomes_trafo = dss.Transformers.AllNames()
        todas = dss.Transformers.AllLossesByType()
        for i, nome in enumerate(nomes_trafo):
            ferro_por_trafo[nome.lower()] = todas[6 * i + 4] / 1000.0
    for nome in (dss.Transformers.AllNames() if dss.Transformers.Count() else []):
        chave = nome.lower()
        trafo = por_nome_de_trafo.get(chave)
        dss.Circuit.SetActiveElement(f"Transformer.{nome}")
        potencias = dss.CktElement.TotalPowers()
        kva = math.hypot(potencias[0], potencias[1]) if len(potencias) >= 2 else None
        nominal_kva = None if trafo is None else opendss._numero(trafo.get("kva"))
        linhas.append({
            "tipo": "trafo", "elemento": nome, "fase": None,
            "codigo": None if trafo is None else trafo.get("codigo"),
            "no_id": None, "feicao_id": None,
            "kv": None if trafo is None else opendss._numero(trafo.get("kv_at")),
            "tensao_pu": None, "corrente_a": None,
            "carregamento_pc": (None if (kva is None or not nominal_kva)
                                else round(100.0 * kva / nominal_kva, 4)),
            "perda_kw": round(perdas_por_elemento.get(f"transformer.{chave}", 0.0), 6),
            "perda_ferro_kw": round(ferro_por_trafo.get(chave, 0.0), 6),
            "potencia_kva": None if kva is None else round(kva, 4),
        })
    return linhas


def _no_id(barra: str) -> str | None:
    """`b` + identificador do nó sem hífen (regra de `opendss._barra`) desfeito, para a camada ler a
    coordenada de `plat.rede_topo_no`. Mesma função do curto-circuito, e pela mesma razão: nunca se copia
    geometria para o resultado."""
    from app.rede_utilidades import curto_circuito

    return curto_circuito._no_id(barra)


def _perda_de_ferro_declarada_kwh(modelo: dict, horas_do_ano: float) -> dict:
    """A conferência do item: a perda de ferro que o ARQUIVO declara, em quilowatt-hora no ano. É
    PER_FER (em watts, por transformador) vezes as horas do ano. O conversor escreveu esse mesmo PER_FER
    como `%noloadloss` de cada transformador, então o simulado tem de bater com isto — a menos da tensão,
    porque a perda a vazio do OpenDSS varia com o quadrado da tensão da barra e a barra não fica em 1 pu."""
    total_w = 0.0
    com_per_fer = 0
    sem_per_fer = 0
    for trafo in modelo["trafos"]:
        percentual = trafo.get("perda_ferro_pc")
        if percentual is None:
            sem_per_fer += 1
            continue
        com_per_fer += 1
        total_w += percentual / 100.0 * trafo["kva"] * 1000.0
    return {
        "perda_de_ferro_declarada_w": round(total_w, 6),
        "perda_de_ferro_declarada_kwh": round(total_w / 1000.0 * horas_do_ano, 6),
        "horas_do_ano": horas_do_ano,
        "transformadores_com_per_fer": com_per_fer,
        "transformadores_sem_per_fer": sem_per_fer,
    }


def resolver(modelo: dict, parametros: dict) -> dict:
    """Resolve o fluxo de potência do modelo e devolve convergência, resumo, energia e o estado por
    elemento no ponto crítico. Não toca banco: recebe o modelo em memória e devolve números.

    `parametros` já veio de `validar_parametros`."""
    dss = _motor()
    inicio = time.perf_counter()
    ano = parametros["ano"] if parametros["ano"] is not None else modelo["ano"]
    horas = opendss.horas_dos_pontos(ano)
    horas_do_ano = sum(horas)

    with _TRAVA_MOTOR, tempfile.TemporaryDirectory(prefix="plat-fluxo-") as tmp:
        pasta = Path(tmp)
        _abrir_circuito(dss, modelo, parametros, pasta)
        varredura = _varrer(dss, parametros, horas)
        convergiu = varredura["pontos_sem_convergencia"] < varredura["pontos"]
        elementos: list[dict] = []
        if convergiu:
            # o estado por elemento é lido no ponto crítico: resolve de novo NAQUELE ponto e lê ali
            dss.Text.Command(f"Set mode=yearly stepsize=1h number=1 hour={varredura['ponto_critico']}")
            dss.Solution.Solve()
            elementos = _elementos_no_ponto(dss, modelo, parametros)

    declarada = _perda_de_ferro_declarada_kwh(modelo, horas_do_ano)
    simulada = varredura["energia_perda_de_ferro_kwh"]
    razao = None
    if parametros["modo"] == "anual" and declarada["perda_de_ferro_declarada_kwh"] > 0:
        razao = simulada / declarada["perda_de_ferro_declarada_kwh"]

    avisos = []
    if varredura["pontos_sem_convergencia"]:
        avisos.append({
            "codigo": "pontos_sem_convergencia",
            "mensagem": "o fluxo de potência não fechou em todos os pontos da curva: o resultado destes "
                        "pontos não entra em energia nem em extremo, e o alimentador fica marcado",
            "quantidade": varredura["pontos_sem_convergencia"],
            "pontos": [descrever_ponto(i) for i in varredura["pontos_nao_convergidos"]]})
    if not convergiu:
        avisos.append({
            "codigo": "alimentador_nao_convergiu",
            "mensagem": "nenhum ponto da curva convergiu: não há estado de rede a ler, e este alimentador "
                        "fica FORA de qualquer agregação",
            "quantidade": varredura["pontos"]})
    if declarada["transformadores_sem_per_fer"]:
        avisos.append({
            "codigo": "transformador_sem_perda_de_ferro_no_arquivo",
            "mensagem": "transformador sem PER_FER no cadastro: ele não entra na perda de ferro declarada "
                        "nem na simulada, e a conferência das duas vale só para os que têm o campo",
            "quantidade": declarada["transformadores_sem_per_fer"]})
    if modelo.get("avisos"):
        avisos.append({"codigo": "avisos_da_conversao",
                       "mensagem": "o conversor contou suposições e faltas ao montar este circuito",
                       "detalhe": dict(modelo["avisos"])})

    return {
        "convergencia": {
            "convergiu": convergiu,
            "pontos": varredura["pontos"],
            "pontos_sem_convergencia": varredura["pontos_sem_convergencia"],
            "pontos_nao_convergidos": [descrever_ponto(i) for i in varredura["pontos_nao_convergidos"]],
        },
        "ponto_critico": {**descrever_ponto(varredura["ponto_critico"]),
                          "carga_kw": (None if varredura["carga_maxima_kw"] is None
                                       else round(varredura["carga_maxima_kw"], 4))},
        "energia": {
            "energia_da_carga_kwh": round(varredura["energia_da_carga_kwh"], 4),
            "energia_perdida_kwh": round(varredura["energia_perdida_kwh"], 4),
            "perda_de_ferro_simulada_kwh": round(simulada, 4),
            **declarada,
            "razao_perda_de_ferro": None if razao is None else round(razao, 6),
        },
        "resumo": {
            "barra_fonte": modelo["barra_fonte"], "kv_fonte": modelo["kv_fonte"],
            "barras": len(modelo["barras"]), "trechos": len(modelo["linhas"]),
            "transformadores": len(modelo["trafos"]), "cargas": len(modelo["cargas"]),
            "tensao_pu_minima": (None if varredura["tensao_pu_minima"] is None
                                 else round(varredura["tensao_pu_minima"], 6)),
            "tensao_pu_maxima": (None if varredura["tensao_pu_maxima"] is None
                                 else round(varredura["tensao_pu_maxima"], 6)),
            "corrente_nominal_de_referencia_a": parametros["corrente_nominal_a"],
            "impedancia": "padrão do OpenDSS (o cadastro não traz catálogo de condutor) — triagem, sinal, "
                          "não prova",
        },
        "elementos": elementos,
        "avisos": avisos,
        "parametros": dict(parametros),
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
        "pico_ram_mb": _pico_ram_mb(),
    }


def agregar(execucoes: list[dict]) -> dict:
    """Soma vários alimentadores num número só, EXCLUINDO os que não convergiram e dizendo quais foram.
    É a regra dura do item: alimentador sem convergência não entra em agregação — o número dele é a parada
    do solver, não o estado da rede."""
    dentro = [e for e in execucoes if e.get("convergiu")]
    fora = [e["subrede"] for e in execucoes if not e.get("convergiu")]
    def somar(campo: str) -> float:
        return round(sum(float((e.get("energia") or {}).get(campo) or 0.0) for e in dentro), 4)

    minimas = [e["resumo"]["tensao_pu_minima"] for e in dentro
               if (e.get("resumo") or {}).get("tensao_pu_minima") is not None]
    return {
        "alimentadores": len(execucoes),
        "alimentadores_agregados": len(dentro),
        "alimentadores_fora_por_nao_convergencia": fora,
        "energia_da_carga_kwh": somar("energia_da_carga_kwh"),
        "energia_perdida_kwh": somar("energia_perdida_kwh"),
        "perda_de_ferro_simulada_kwh": somar("perda_de_ferro_simulada_kwh"),
        "perda_de_ferro_declarada_kwh": somar("perda_de_ferro_declarada_kwh"),
        "tensao_pu_minima": min(minimas) if minimas else None,
    }


# --- leitura da subrede e gravação ----------------------------------------------------------------------

def _topologia_versao(cur, rede_id: str):
    cur.execute("SELECT construido_em FROM plat.rede_topo_resumo WHERE rede_id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    return None if r is None else r["construido_em"]


def calcular_e_gravar(cur, tenant_id: int, rede_id: str, nome: str, parametros_pedidos: dict | None,
                      tier: str | None = None, jusante: bool = False) -> dict:
    """Analisa um alimentador e grava a execução e o resultado por elemento. Análise nova da mesma subrede
    substitui a anterior (uma execução viva por subrede)."""
    from app.rede_utilidades import curto_circuito

    parametros = validar_parametros(parametros_pedidos)
    s, modelo = curto_circuito.modelo_da_subrede(cur, rede_id, nome, tier, parametros["ano"], jusante)
    saida = resolver(modelo, parametros)

    cur.execute("DELETE FROM plat.rede_fluxo_execucao WHERE subrede_id = %s::uuid", (str(s["id"]),))
    cur.execute(
        "INSERT INTO plat.rede_fluxo_execucao (tenant_id, rede_id, subrede_id, subrede_nome, parametros, "
        "topologia_versao, convergiu, pontos, pontos_sem_convergencia, ponto_critico, energia, resumo, "
        "avisos, elementos, duracao_ms, pico_ram_mb, onde_rodou) "
        "VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, "
        "%s::jsonb, %s, %s, %s, %s) RETURNING id",
        (tenant_id, rede_id, str(s["id"]), s["nome"],
         json.dumps(saida["parametros"], ensure_ascii=False),
         _topologia_versao(cur, rede_id),
         saida["convergencia"]["convergiu"], saida["convergencia"]["pontos"],
         saida["convergencia"]["pontos_sem_convergencia"],
         json.dumps(saida["ponto_critico"], ensure_ascii=False),
         json.dumps(saida["energia"], ensure_ascii=False),
         json.dumps(saida["resumo"], ensure_ascii=False),
         json.dumps(saida["avisos"], ensure_ascii=False),
         len(saida["elementos"]), saida["duracao_ms"], saida["pico_ram_mb"], "local"))
    execucao_id = str(cur.fetchone()["id"])

    if saida["elementos"]:
        cur.executemany(
            "INSERT INTO plat.rede_fluxo_resultado (tenant_id, execucao_id, tipo, elemento, fase, codigo, "
            "no_id, feicao_id, kv, tensao_pu, corrente_a, carregamento_pc, perda_kw, perda_ferro_kw, "
            "potencia_kva) VALUES (%(t)s, %(e)s::uuid, %(tipo)s, %(el)s, %(fase)s, %(cod)s, %(no)s::uuid, "
            "%(f)s::uuid, %(kv)s, %(pu)s, %(i)s, %(carr)s, %(perda)s, %(ferro)s, %(kva)s)",
            [{"t": tenant_id, "e": execucao_id, "tipo": x["tipo"], "el": x["elemento"], "fase": x["fase"],
              "cod": None if x["codigo"] is None else str(x["codigo"])[:200], "no": x["no_id"],
              "f": x["feicao_id"], "kv": x["kv"], "pu": x["tensao_pu"], "i": x["corrente_a"],
              "carr": x["carregamento_pc"], "perda": x["perda_kw"], "ferro": x["perda_ferro_kw"],
              "kva": x["potencia_kva"]} for x in saida["elementos"]])

    return {"execucao_id": execucao_id, "subrede": s["nome"], "tier": s["tier"],
            "parametros": saida["parametros"], "convergencia": saida["convergencia"],
            "convergiu": saida["convergencia"]["convergiu"],
            "ponto_critico": saida["ponto_critico"], "energia": saida["energia"],
            "resumo": saida["resumo"], "avisos": saida["avisos"],
            "elementos": len(saida["elementos"]), "duracao_ms": saida["duracao_ms"],
            "pico_ram_mb": saida["pico_ram_mb"]}


# Descrição das colunas da tabela, para o painel ligar um elemento a esta fonte sem que ninguém escreva
# rótulo à mão (mesmo padrão de `curto_circuito.COLUNAS`).
COLUNAS = [
    {"codigo": "tipo", "nome": "Tipo de elemento", "tipo": "texto", "unidade": None},
    {"codigo": "elemento", "nome": "Elemento", "tipo": "texto", "unidade": None},
    {"codigo": "fase", "nome": "Fase", "tipo": "numero", "unidade": None},
    {"codigo": "codigo", "nome": "Código no cadastro", "tipo": "texto", "unidade": None},
    {"codigo": "kv", "nome": "Tensão de base", "tipo": "numero", "unidade": "kV"},
    {"codigo": "tensao_pu", "nome": "Tensão", "tipo": "numero", "unidade": "pu"},
    {"codigo": "corrente_a", "nome": "Corrente", "tipo": "numero", "unidade": "A"},
    {"codigo": "carregamento_pc", "nome": "Carregamento", "tipo": "numero", "unidade": "%"},
    {"codigo": "perda_kw", "nome": "Perda no ponto crítico", "tipo": "numero", "unidade": "kW"},
    {"codigo": "perda_ferro_kw", "nome": "Perda de ferro", "tipo": "numero", "unidade": "kW"},
    {"codigo": "potencia_kva", "nome": "Potência aparente", "tipo": "numero", "unidade": "kVA"},
]
GRANDEZAS = ("tensao", "corrente", "carregamento")


def _execucao(cur, rede_id: str, nome: str) -> dict:
    from app.erros import ErroAPI

    cur.execute(
        "SELECT id, subrede_id, subrede_nome, parametros, topologia_versao, convergiu, pontos, "
        "       pontos_sem_convergencia, ponto_critico, energia, resumo, avisos, elementos, duracao_ms, "
        "       pico_ram_mb, onde_rodou, calculado_em "
        "FROM plat.rede_fluxo_execucao WHERE rede_id = %s::uuid AND subrede_nome = %s",
        (rede_id, nome))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "fluxo_nao_calculado",
                      "este alimentador ainda não teve o fluxo de potência calculado")
    return dict(r)


def _ficha(e: dict) -> dict:
    """A ficha do resultado: os parâmetros que o produziram, a versão da topologia sobre a qual o modelo foi
    montado e o estado de convergência. Nenhuma leitura deste módulo devolve número sem esta ficha."""
    from app.auth.sessao import iso

    return {
        "subrede": e["subrede_nome"], "execucao_id": str(e["id"]),
        "calculado_em": iso(e["calculado_em"]),
        "topologia_versao": iso(e["topologia_versao"]) if e["topologia_versao"] else None,
        "parametros": e["parametros"],
        "convergencia": {"convergiu": e["convergiu"], "pontos": e["pontos"],
                         "pontos_sem_convergencia": e["pontos_sem_convergencia"]},
        "convergiu": e["convergiu"],
        "ponto_critico": e["ponto_critico"], "energia": e["energia"], "resumo": e["resumo"],
        "avisos": e["avisos"], "duracao_ms": e["duracao_ms"], "pico_ram_mb": e["pico_ram_mb"],
        "onde_rodou": e["onde_rodou"],
    }


def tabela(cur, rede_id: str, nome: str, tipo: str | None = None, limite: int = 5000) -> dict:
    """A tabela do resultado por elemento, com a ficha ao lado. `tipo` filtra barra/trecho/trafo.
    A ordenação põe primeiro o que dói: menor tensão, maior carregamento, maior perda."""
    from app.erros import ErroAPI

    if tipo is not None and tipo not in ("barra", "trecho", "trafo"):
        raise ErroAPI(422, "tipo_invalido", "tipo deve ser barra, trecho ou trafo")
    limite = max(1, min(int(limite), 20000))
    e = _execucao(cur, rede_id, nome)
    cur.execute(
        "SELECT tipo, elemento, fase, codigo, no_id, feicao_id, kv, tensao_pu, corrente_a, "
        "       carregamento_pc, perda_kw, perda_ferro_kw, potencia_kva "
        "FROM plat.rede_fluxo_resultado WHERE execucao_id = %s::uuid "
        "  AND (%s::text IS NULL OR tipo = %s) "
        "ORDER BY tensao_pu ASC NULLS LAST, carregamento_pc DESC NULLS LAST, perda_kw DESC NULLS LAST, "
        "         tipo, elemento, fase LIMIT %s",
        (str(e["id"]), tipo, tipo, limite))
    linhas = [{k: (str(v) if k.endswith("_id") and v is not None else v) for k, v in dict(r).items()}
              for r in cur.fetchall()]
    return {**_ficha(e), "colunas": COLUNAS, "linhas": linhas, "total": e["elementos"],
            "limite": limite, "filtro_tipo": tipo}


_SQL_CAMADA_PONTO = """
SELECT r.elemento, r.fase, r.kv, r.tensao_pu, ST_X(n.geom) AS lon, ST_Y(n.geom) AS lat
FROM plat.rede_fluxo_resultado r
JOIN plat.rede_topo_no n ON n.id = r.no_id
WHERE r.execucao_id = %s::uuid AND r.tipo = 'barra' AND r.tensao_pu IS NOT NULL
ORDER BY r.elemento, r.fase
"""

_SQL_CAMADA_LINHA = """
SELECT r.elemento, r.codigo, r.corrente_a, r.carregamento_pc, r.perda_kw,
       ST_AsGeoJSON(l.geom) AS geojson
FROM plat.rede_fluxo_resultado r
JOIN plat.rede_feicao_linha l ON l.id = r.feicao_id
WHERE r.execucao_id = %s::uuid AND r.tipo = 'trecho'
ORDER BY r.elemento
"""


def camada(cur, rede_id: str, nome: str, grandeza: str) -> dict:
    """O resultado como CAMADA para o mapa, uma grandeza por vez:

      `tensao`       — um ponto por barra e fase, com a tensão em por unidade;
      `corrente`     — a linha do trecho, com a corrente em ampere;
      `carregamento` — a MESMA linha, com o carregamento em por cento da corrente nominal declarada.

    A geometria vem da topologia e da camada editável na hora da leitura, nunca de cópia gravada. Elemento
    sem geometria não vira feição — nunca um ponto (0, 0) — e a contagem do que ficou de fora sai no corpo.
    A ficha (parâmetros, versão da topologia, convergência) vem junto: camada sem o estado de convergência
    ao lado seria um mapa bonito de um alimentador que não fechou."""
    from app.erros import ErroAPI

    if grandeza not in GRANDEZAS:
        raise ErroAPI(422, "grandeza_invalida", f"grandeza deve ser uma de {GRANDEZAS}")
    e = _execucao(cur, rede_id, nome)
    feicoes = []
    if grandeza == "tensao":
        cur.execute(_SQL_CAMADA_PONTO, (str(e["id"]),))
        for r in cur.fetchall():
            d = dict(r)
            lon, lat = d.pop("lon"), d.pop("lat")
            feicoes.append({"type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                            "properties": {**d, "grandeza": "tensao", "unidade": "pu",
                                           "valor": d["tensao_pu"]}})
    else:
        cur.execute(_SQL_CAMADA_LINHA, (str(e["id"]),))
        campo = "corrente_a" if grandeza == "corrente" else "carregamento_pc"
        unidade = "A" if grandeza == "corrente" else "%"
        for r in cur.fetchall():
            d = dict(r)
            geometria = json.loads(d.pop("geojson"))
            feicoes.append({"type": "Feature", "geometry": geometria,
                            "properties": {**d, "grandeza": grandeza, "unidade": unidade,
                                           "valor": d[campo]}})
    cur.execute("SELECT count(*) AS n FROM plat.rede_fluxo_resultado WHERE execucao_id = %s::uuid "
                "AND tipo = %s", (str(e["id"]), "barra" if grandeza == "tensao" else "trecho"))
    do_tipo = int(cur.fetchone()["n"])
    return {"type": "FeatureCollection", "features": feicoes, "grandeza": grandeza,
            "elementos_do_tipo": do_tipo, "elementos_sem_geometria": do_tipo - len(feicoes),
            **_ficha(e)}
