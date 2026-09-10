"""Execução do modelo sobre camadas do acervo (item L6-04-acervo-no-motor).

Fecha, para o caso do acervo, o ciclo que L3-01-a/b/c e L6-01-b deixaram pronto em peças separadas: uma
execução registrada (`plat.amc_execucao`, estado 'registrada') tem cada fator do tipo `camada.tipo = 'acervo'`
extraído pela VIEW só-leitura de `plat_acervo` (nunca uma cópia — `app.acervo.publicacao`), com
`app.amc.vetorial` fazendo a extração e uma transformação linear simples levando o valor bruto a
favorabilidade 0-100 antes da soma ponderada normalizada pelos pesos da execução.

Assinatura como porteiro do JOB, não só da rota: `app.amc.camadas._acervo` já recusa (422) a CRIAÇÃO da
execução quando o inquilino não assina a camada. Aqui, imediatamente ANTES de ler cada camada — e de novo
depois de extrair a ÚLTIMA — o job confere `plat.acervo_pode_ler` outra vez. Se a assinatura foi revogada
ENTRE essas duas checagens (durante o job, a refutação exigida pelo item), a execução vai a 'falhou' com
mensagem e NENHUMA linha de `amc_fator_bruto`/`amc_resultado` é gravada para ela: `amc_fator_bruto` e
`amc_resultado` só são escritos juntos, no bloco final, depois que cada um dos fatores do acervo confirmou a
assinatura de novo — nunca conclui com zero.

Limite honesto e deliberado deste item (não é o L3-01-e completo, combinadores/políticas alternativos):
- só fatores com `camada.tipo == 'acervo'` são extraídos aqui; fator do tipo 'item' fica de fora (fora do
  escopo do portão, que fala só do acervo) e é simplesmente ignorado na combinação;
- só os extratores de vetor com correspondência 1:1 em `app.amc.vetorial` (polígono/linha/ponto);
- a transformação (item L3-01-d, `app.amc.transformacoes`) roda os 16 tipos declarados no esquema; para
  `faixas` com quebra por quantil/intervalo_igual/quebras_naturais e para `ms_grande`/`ms_pequena` sem
  media/desvio gravados, a resolução usa a amostra dos valores brutos EXTRAÍDOS NESTA execução (as mesmas
  unidades), congelada por fator antes de transformar — outra execução com outro conjunto de unidades
  resolve de novo, e pode dar quebras diferentes;
- a camada do acervo é lida só dentro da caixa envolvente das unidades (mais uma folga), não da tabela
  inteira — necessário para não varrer camadas nacionais de milhões de linhas a cada execução; a distância
  ao mais próximo, portanto, é a mais próxima DENTRO dessa caixa, documentada aqui e no handoff."""

from app.acervo.publicacao import _ident, _schema_views
from app.amc import transformacoes

# `app.amc.vetorial` importa geopandas no topo, e geopandas NÃO está em requirements.txt nem na venv da
# unidade systemd (só no site do usuário desta máquina). Importado aqui em cima, ele derrubava o import de
# `app.main` inteiro — a aplicação não subia, e tests/unit/test_dependencias.py::
# test_app_main_importa_sem_site_do_usuario reprovava. O extrator de vetor é UM caminho do executor, então o
# import vive onde ele é usado: quem não extrai fator de vetor não paga a dependência, e quem extrai recebe
# o ModuleNotFoundError no lugar certo, dizendo o que falta instalar.
from app.amc.zonal import ErroExtracao
from app.jobs.registro import FalhaDefinitiva

# extrator do esquema do modelo (docs/esquemas/amc_modelo.v1.json) -> extrator de app.amc.vetorial (item L3-01-c)
# os dois vocabulários nasceram em ramos diferentes (L3-01-a e L3-01-c) sem se falarem; este é o tradutor.
MAPA_EXTRATOR_VETOR = {
    "poligono_fracao_area": "vetor_fracao_area",
    "poligono_area": "vetor_area",
    "poligono_contagem": "vetor_contagem",
    "poligono_atributo_ponderado": "vetor_atributo_ponderado_area",
    "linha_comprimento": "vetor_comprimento_dentro",
    "linha_distancia_mais_proxima": "vetor_distancia_mais_proxima",
    "ponto_contagem_raio": "vetor_contagem_raio",
    "ponto_densidade_kernel": "vetor_densidade_kernel",
    "ponto_distancia_mais_proximo": "vetor_distancia_mais_proxima",
    "ponto_atributo_mais_proximo": "vetor_atributo_mais_proximo",
}
FOLGA_GRAUS = 0.05  # ~5,5 km no equador; margem em volta da caixa das unidades para achar o vizinho mais próximo


class ErroExecucao(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo, self.mensagem = codigo, mensagem


def _falhar(ctx, execucao_id: str, motivo: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.amc_execucao SET estado = 'falhou', erro = %s, terminado_em = now() WHERE id = %s::uuid",
            (motivo, execucao_id),
        )
    ctx.log("ERRO", motivo)


def _envelope_4326(unidades: list[tuple[str, dict]], folga: float = FOLGA_GRAUS) -> tuple[float, float, float, float]:
    xs0, ys0, xs1, ys1 = [], [], [], []
    for _uid, g in unidades:
        for anel in _aneis(g):
            for x, y in anel:
                xs0.append(x)
                ys0.append(y)
                xs1.append(x)
                ys1.append(y)
    if not xs0:
        raise FalhaDefinitiva("conjunto de unidades sem nenhuma coordenada")
    return min(xs0) - folga, min(ys0) - folga, max(xs1) + folga, max(ys1) + folga


def _aneis(geojson: dict):
    """Coordenadas de todo anel de um Polygon/MultiPolygon GeoJSON, sem depender de shapely aqui (só bbox)."""
    tipo = geojson.get("type")
    coords = geojson.get("coordinates") or []
    if tipo == "Polygon":
        for anel in coords:
            yield anel
    elif tipo == "MultiPolygon":
        for poligono in coords:
            for anel in poligono:
                yield anel


def _acervo_pode_ler(ctx, camada_id: str) -> bool:
    with ctx.db() as cur:
        cur.execute("SELECT plat.acervo_pode_ler(%s) AS pode", (camada_id,))
        return bool(cur.fetchone()["pode"])


def _ler_camada_acervo(ctx, camada_id: str, unidades: list[tuple[str, dict]], atributo: str | None) -> list:
    """[(id, geojson 4326, atributos|None)] da view `plat_acervo.<view>` — nunca uma cópia — recortada à caixa
    envolvente das unidades (+ folga). `id` é `row_number()` da própria consulta: só precisa ser único DENTRO
    desta chamada (o agrupamento de app.amc.vetorial não exige id estável entre execuções)."""
    with ctx.db() as cur:
        cur.execute(
            "SELECT view_nome, coluna_geom, colunas FROM plat.acervo_publicacao WHERE acervo_camada_id = %s",
            (camada_id,),
        )
        pub = cur.fetchone()
        if pub is None:
            raise FalhaDefinitiva(
                f"camada do acervo {camada_id!r} está exposta no registro mas não tem view publicada em "
                f"plat_acervo (rode scripts/acervo_publicar.py); a execução não pode ler o que não foi publicado"
            )
        if atributo is not None and atributo not in pub["colunas"]:
            raise FalhaDefinitiva(
                f"o atributo {atributo!r} pedido pelo fator não está na lista branca da camada {camada_id!r}: "
                f"{sorted(pub['colunas'])}"
            )
        geom = _ident(pub["coluna_geom"])
        vista = f'{_ident(_schema_views())}.{_ident(pub["view_nome"])}'
        caixa = _envelope_4326(unidades)
        col_extra = f", {_ident(atributo)} AS _atributo" if atributo else ""
        cur.execute(
            f"SELECT row_number() OVER ()::text AS fid, ST_AsGeoJSON({geom})::json AS g{col_extra} "  # noqa: S608
            f"FROM {vista} WHERE {geom} && ST_MakeEnvelope(%s, %s, %s, %s, 4326)",
            caixa,
        )
        linhas = cur.fetchall()
    if atributo:
        return [(li["fid"], li["g"], {atributo: li["_atributo"]}) for li in linhas]
    return [(li["fid"], li["g"], None) for li in linhas]


def _resolver_transformacoes(fatores_acervo: list[dict], brutos: dict) -> dict[str, dict]:
    """Congela, por fator, a transformação com `metodo`/`media`/`desvio` já resolvidos a partir da
    amostra de valores brutos EXTRAÍDOS NESTA execução (item L3-01-d: `resolver_quebras`/
    `resolver_estatisticas`) — feito uma vez por fator, não por unidade."""
    resolvidas = {}
    for fator in fatores_acervo:
        t = fator["transformacao"]
        amostra = [r.get("valor") for r in brutos.get(fator["id"], {}).values()]
        t = transformacoes.resolver_quebras(amostra, t)
        t = transformacoes.resolver_estatisticas(amostra, t)
        resolvidas[fator["id"]] = t
    return resolvidas


def _transformar(valor, transformacao: dict) -> float | None:
    """valor bruto -> favorabilidade 0-100, delegado à biblioteca declarativa do item L3-01-d
    (`app.amc.transformacoes`, os 16 tipos do esquema — SQL e numpy equivalentes)."""
    try:
        return transformacoes.transformar_um(valor, transformacao)
    except transformacoes.ErroTransformacao as e:
        raise FalhaDefinitiva(f"transformação {transformacao.get('tipo')!r}: {e.mensagem}") from e


def _combinar(fatores_acervo: list[dict], pesos: dict, brutos: dict, uid: str,
              transformacoes_resolvidas: dict[str, dict]) -> tuple:
    """Soma ponderada normalizada (Σw·nota / Σw) sobre os fatores COM dado na unidade — o combinador padrão do
    esquema (`soma_ponderada_normalizada`), política `excluir_fator` para dado ausente (as duas são o padrão
    quando o modelo não pede outra coisa; combinadores/políticas alternativos ficam para L3-01-e)."""
    soma_peso = soma_nota = 0.0
    coberturas = []
    for fator in fatores_acervo:
        fid = fator["id"]
        peso = float(pesos.get(fid, 0.0))
        r = brutos.get(fid, {}).get(uid)
        if r is not None:
            coberturas.append(r.get("cobertura") or 0.0)
        if peso <= 0 or r is None or r.get("valor") is None:
            continue
        nota = _transformar(r["valor"], transformacoes_resolvidas[fid])
        if nota is None:
            continue
        soma_peso += peso
        soma_nota += peso * nota
    if soma_peso <= 0:
        return None, (sum(coberturas) / len(coberturas) if coberturas else 0.0), False, None
    cobertura = sum(coberturas) / len(coberturas) if coberturas else 0.0
    return round(soma_nota / soma_peso, 4), cobertura, False, None


def executar(ctx, execucao_id) -> dict:
    """Corpo do job `amc.executar`. `ctx` é o ContextoJob (ou equivalente de teste com db()/log()/progresso()/
    verificar()). Reexecução de uma execução 'falhou' recomeça do zero (apaga fator bruto/resultado parciais,
    se algum dia existirem); execução 'concluida' é imutável (gatilho do banco) e não é reprocessada."""
    eid = str(execucao_id)
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.amc_execucao WHERE id = %s::uuid", (eid,))
        exe = cur.fetchone()
        if exe is None:
            raise FalhaDefinitiva(f"execução inexistente: {eid}")
        if exe["estado"] == "concluida":
            return {"execucao_id": eid, "estado": "concluida", "reexecucao": False}
        if exe["estado"] not in ("registrada", "extraindo", "falhou"):
            raise FalhaDefinitiva(f"execução em estado {exe['estado']!r} não pode ser (re)executada")
        cur.execute(
            "SELECT definicao FROM plat.amc_modelo_versao WHERE modelo_id = %s AND versao_hash = %s",
            (exe["modelo_id"], exe["versao_hash"]),
        )
        v = cur.fetchone()
        if v is None:
            raise FalhaDefinitiva("versão do modelo desapareceu (nunca deveria: versão é imutável)")
        definicao = v["definicao"]
        cur.execute("SELECT srid_trabalho FROM plat.amc_conjunto_unidade WHERE id = %s::uuid", (exe["conjunto_id"],))
        conjunto = cur.fetchone()
        if conjunto is None:
            raise FalhaDefinitiva("conjunto de unidades desapareceu")
        srid_trabalho = conjunto["srid_trabalho"]
        cur.execute(
            "SELECT unidade_id, ST_AsGeoJSON(geom)::json AS g FROM plat.amc_unidade WHERE conjunto_id = %s::uuid "
            "ORDER BY unidade_id",
            (exe["conjunto_id"],),
        )
        unidades = [(u["unidade_id"], u["g"]) for u in cur.fetchall()]
        cur.execute("DELETE FROM plat.amc_fator_bruto WHERE execucao_id = %s::uuid", (eid,))
        cur.execute("DELETE FROM plat.amc_resultado WHERE execucao_id = %s::uuid", (eid,))
        cur.execute(
            "UPDATE plat.amc_execucao SET estado = 'extraindo', iniciado_em = coalesce(iniciado_em, now()), "
            "erro = NULL WHERE id = %s::uuid",
            (eid,),
        )
    if not unidades:
        motivo = "conjunto de unidades sem nenhuma unidade"
        _falhar(ctx, eid, motivo)
        raise FalhaDefinitiva(motivo)

    fatores = definicao.get("fatores") or []
    fatores_acervo = [f for f in fatores if isinstance(f, dict) and (f.get("camada") or {}).get("tipo") == "acervo"]
    if not fatores_acervo:
        motivo = "nenhum fator do tipo 'acervo' no modelo: este item só executa fatores do acervo (L6-04)"
        _falhar(ctx, eid, motivo)
        raise FalhaDefinitiva(motivo)

    pesos = exe["pesos"]
    brutos: dict[str, dict] = {}
    for i, fator in enumerate(fatores_acervo):
        ctx.verificar()
        camada_id = fator["camada"]["id"]
        if not _acervo_pode_ler(ctx, camada_id):
            motivo = (f"a assinatura da camada do acervo {camada_id!r} foi revogada durante a execução "
                      f"(fator {fator.get('id')!r}); a execução falha e nenhum resultado é gravado")
            _falhar(ctx, eid, motivo)
            raise FalhaDefinitiva(motivo)
        extrator = fator.get("extrator") or {}
        tipo_esquema = extrator.get("tipo")
        tipo_vetor = MAPA_EXTRATOR_VETOR.get(tipo_esquema)
        if tipo_vetor is None:
            motivo = (f"fator {fator.get('id')!r}: extrator {tipo_esquema!r} não tem extração de vetor sobre "
                      f"acervo suportada por este item (admitidos: {sorted(MAPA_EXTRATOR_VETOR)})")
            _falhar(ctx, eid, motivo)
            raise FalhaDefinitiva(motivo)
        feicoes = _ler_camada_acervo(ctx, camada_id, unidades, fator["camada"].get("atributo"))
        try:
            from app.amc import vetorial  # tardio: ver a nota do import no topo deste arquivo

            brutos[fator["id"]] = vetorial.extrair(
                unidades, feicoes, tipo_vetor, srid_trabalho, extrator.get("parametros") or {}
            )
        except ErroExtracao as e:
            motivo = f"fator {fator.get('id')!r}: {e.mensagem}"
            _falhar(ctx, eid, motivo)
            raise FalhaDefinitiva(motivo) from e
        ctx.progresso(int(10 + 70 * (i + 1) / len(fatores_acervo)), f"fator {fator.get('id')} extraído")

    # segunda checagem — a corrida que a refutação do item pede: revogar ENTRE a última extração e a gravação.
    for fator in fatores_acervo:
        camada_id = fator["camada"]["id"]
        if not _acervo_pode_ler(ctx, camada_id):
            motivo = (f"a assinatura da camada do acervo {camada_id!r} foi revogada durante a execução "
                      f"(depois de extraída, antes de gravar); a execução falha e nenhum resultado é gravado")
            _falhar(ctx, eid, motivo)
            raise FalhaDefinitiva(motivo)

    transformacoes_resolvidas = _resolver_transformacoes(fatores_acervo, brutos)
    with ctx.db() as cur:
        for fid, por_unidade in brutos.items():
            for uid, r in por_unidade.items():
                cur.execute(
                    "INSERT INTO plat.amc_fator_bruto(execucao_id, tenant_id, unidade_id, fator, valor, cobertura) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (execucao_id, unidade_id, fator) DO UPDATE SET "
                    "valor = EXCLUDED.valor, cobertura = EXCLUDED.cobertura",
                    (eid, exe["tenant_id"], uid, fid, r["valor"], r["cobertura"]),
                )
        for uid, _g in unidades:
            favorabilidade, cobertura, vetado, motivo = _combinar(
                fatores_acervo, pesos, brutos, uid, transformacoes_resolvidas
            )
            cur.execute(
                "INSERT INTO plat.amc_resultado(execucao_id, tenant_id, unidade_id, favorabilidade, vetado, motivo, "
                "cobertura) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (execucao_id, unidade_id) DO UPDATE SET favorabilidade = EXCLUDED.favorabilidade, "
                "vetado = EXCLUDED.vetado, motivo = EXCLUDED.motivo, cobertura = EXCLUDED.cobertura",
                (eid, exe["tenant_id"], uid, favorabilidade, vetado, motivo, cobertura),
            )
        cur.execute(
            "UPDATE plat.amc_execucao SET estado = 'concluida', terminado_em = now(), erro = NULL WHERE id = %s::uuid",
            (eid,),
        )
    ctx.progresso(100, "execução concluída")
    return {"execucao_id": eid, "estado": "concluida", "unidades": len(unidades), "fatores_acervo": len(fatores_acervo)}
