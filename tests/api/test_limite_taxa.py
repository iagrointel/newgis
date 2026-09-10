"""Limite de taxa por inquilino/plano — item L7-03-b-rate-limit-abuso (docs/SEGURANCA.md §9; ADR desta
trilha). Cobre a camada 2 (API por inquilino, Postgres, janela deslizante) diretamente contra
`plat.limite_taxa_verificar` e, de ponta a ponta, contra rotas reais da API (dois inquilinos temporários com
teto baixo, para não depender de milhares de pedidos). As camadas 1 (nginx) e 3 (fail2ban) são provadas fora
do pytest, com nginx e fail2ban de verdade — ver `scripts/bench_limite_taxa.py` e `docs/SEGURANCA.md §9`."""

import concurrent.futures
import secrets
import time

from app import limite_taxa
from tests.api.conftest import InquilinoTemporario


def _chave() -> str:
    return f"zt-teste:{secrets.token_hex(8)}"


def test_limite_de_corta_para_a_faixa():
    padrao, minimo, maximo = 6000, 5, 500_000
    assert limite_taxa.limite_de({}, "api_por_minuto") == padrao
    assert limite_taxa.limite_de({"limites": {"api_por_minuto": 1}}, "api_por_minuto") == minimo
    assert limite_taxa.limite_de({"limites": {"api_por_minuto": 10**9}}, "api_por_minuto") == maximo
    assert limite_taxa.limite_de({"limites": {"api_por_minuto": 100}}, "api_por_minuto") == 100
    assert limite_taxa.limite_de({"limites": {"api_por_minuto": "lixo"}}, "api_por_minuto") == padrao
    assert limite_taxa.chave_tenant(42) == "tenant:42"


def test_verificar_permite_ate_o_maximo_e_recusa_depois_com_retry_after_positivo():
    chave, escopo = _chave(), "api"
    for i in range(3):
        permitido, restante, expira_em = limite_taxa.verificar(chave, escopo, maximo=3, janela_s=60)
        assert permitido is True, i
        assert restante == 2 - i
    permitido, restante, expira_em = limite_taxa.verificar(chave, escopo, maximo=3, janela_s=60)
    assert permitido is False and restante == 0
    assert expira_em is not None
    retry = limite_taxa._retry_after_s(expira_em)
    assert retry >= 1
    assert limite_taxa.contagem_atual(chave, escopo, janela_s=60) == 3


def test_janela_curta_libera_de_novo_depois_de_expirar():
    chave, escopo = _chave(), "api"
    for _ in range(2):
        assert limite_taxa.verificar(chave, escopo, maximo=2, janela_s=1)[0] is True
    assert limite_taxa.verificar(chave, escopo, maximo=2, janela_s=1)[0] is False
    time.sleep(1.2)
    assert limite_taxa.verificar(chave, escopo, maximo=2, janela_s=1)[0] is True


def test_chaves_diferentes_nunca_se_afetam_uma_esgota_a_outra_segue_livre():
    """Mesma prova que o teste de API faz por HTTP (abaixo), mas direto na função SQL: a chave de UM
    inquilino esgotada não move um bit no contador de outra chave — é o mecanismo por trás da cláusula
    'limite por inquilino não afeta outro' do portão."""
    chave_a, chave_b, escopo = _chave(), _chave(), "api"
    for _ in range(5):
        assert limite_taxa.verificar(chave_a, escopo, maximo=5, janela_s=60)[0] is True
    assert limite_taxa.verificar(chave_a, escopo, maximo=5, janela_s=60)[0] is False
    for _ in range(5):
        assert limite_taxa.verificar(chave_b, escopo, maximo=5, janela_s=60)[0] is True


def test_escopos_diferentes_da_mesma_chave_sao_contadores_independentes():
    chave = _chave()
    for _ in range(4):
        assert limite_taxa.verificar(chave, "api", maximo=4, janela_s=60)[0] is True
    assert limite_taxa.verificar(chave, "api", maximo=4, janela_s=60)[0] is False
    # "tiles" da MESMA chave não foi tocado
    assert limite_taxa.contagem_atual(chave, "tiles", janela_s=60) == 0
    assert limite_taxa.verificar(chave, "tiles", maximo=4, janela_s=60)[0] is True


def test_concorrencia_real_nunca_fura_o_teto():
    """Achado do adversário do turno (`laco/handoffs/T5/L7-03-b-rate-limit-abuso.md`): sem
    `pg_advisory_xact_lock`, duas transações concorrentes fazem o MESMO `SELECT count()` (nenhuma viu o
    `INSERT` da outra ainda) e as duas passam — o teto configurado é ultrapassado. MEDIDO pelo
    adversário: pool de 2 conexões furou 20 para 21 em 2 de 3 rodadas; pool de 8 furou para 23 em 1 de
    5. Consertado com o lock transacional por (chave, escopo) na migração. Prova aqui: 200 chamadas
    verdadeiramente concorrentes (thread pool, 60 workers) contra o MESMO par (chave, escopo) e teto 20,
    repetido 5 vezes — o teto nunca pode ser ultrapassado em NENHUMA rodada."""
    maximo = 20
    for rodada in range(5):
        chave = f"{_chave()}:{rodada}"

        def bater(_, chave=chave):
            permitido, _restante, _expira = limite_taxa.verificar(chave, "api", maximo=maximo, janela_s=60)
            return permitido

        with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
            resultados = list(ex.map(bater, range(200)))
        aceitos = sum(resultados)
        assert aceitos == maximo, (rodada, aceitos)


def test_50_ips_forjados_contra_o_mesmo_token_a_camada_de_inquilino_segura(sessao_plat):
    """Refutação do item: o adversário distribui o ataque em 50 IPs contra o MESMO token. Como a camada 2
    (aqui) conta por CHAVE DE INQUILINO — nunca por IP — rotacionar o X-Forwarded-For a cada pedido não
    devolve cota nenhuma: os 50 IPs forjados caem na MESMA chave e o teto aparece exatamente onde apareceria
    sem forjar nada. (O IP em si nem participa da chave: a prova aqui é que o cabeçalho é irrelevante.)"""
    # +1 no teto: o próprio setup do inquilino temporário (troca de senha) já gasta 1 unidade da cota antes
    # do teste começar a contar — a conta abaixo é sobre o que SOBRA depois disso.
    inq = InquilinoTemporario(sessao_plat, config={"limites": {"api_por_minuto": 7}})
    try:
        codigos = []
        for i in range(8):
            r = inq.admin.get("/api/eu", headers={"X-Forwarded-For": f"203.0.113.{i}"})
            codigos.append(r.status_code)
        assert codigos.count(200) == 6, codigos
        assert codigos.count(429) == 2, codigos
        ultima = None
        for i in range(8):
            ultima = inq.admin.get("/api/eu", headers={"X-Forwarded-For": f"198.51.100.{i}"})
        assert ultima.status_code == 429, ultima.text
        assert ultima.json()["erro"] == "limite_de_taxa"
        assert int(ultima.headers["retry-after"]) >= 1
    finally:
        inq.apagar()


def test_limite_de_um_inquilino_nao_afeta_outro_teste_cruzado(sessao_plat):
    """Cláusula literal do portão: dois inquilinos com o MESMO teto baixo; esgota o de A e confere que B
    segue servindo 200 no MESMO instante (não é só 'contadores diferentes na tabela' — é o comportamento
    observável por HTTP que o portão pede)."""
    # +1 no teto pelo mesmo motivo do teste acima (setup gasta 1 unidade antes de o teste começar).
    a = InquilinoTemporario(sessao_plat, config={"limites": {"api_por_minuto": 6}})
    b = InquilinoTemporario(sessao_plat, config={"limites": {"api_por_minuto": 6}})
    try:
        codigos_a = [a.admin.get("/api/eu").status_code for _ in range(7)]
        assert codigos_a.count(200) == 5 and codigos_a.count(429) == 2, codigos_a
        # B não tinha feito NENHUM pedido de teste ainda: os 5 primeiros dele continuam livres
        codigos_b = [b.admin.get("/api/eu").status_code for _ in range(5)]
        assert codigos_b == [200] * 5, codigos_b
    finally:
        a.apagar()
        b.apagar()


def test_limite_padrao_de_demo_e_alto_o_bastante_para_nao_atrapalhar_a_suite(sessao_a):
    """Não é uma prova de ataque: é a rede de segurança do próprio item. O padrão de produção (config vazio,
    LIMITE_TAXA_PADROES) tem de ser alto o bastante para a suíte inteira (que martela demo/demo2 com
    `sessao_a`/`sessao_b` de escopo de sessão) não esbarrar nele por acidente — 30 pedidos rápidos ao
    inquilino de demonstração, que não tem override de config, continuam todos 200."""
    codigos = [sessao_a.get("/api/eu").status_code for _ in range(30)]
    assert all(c == 200 for c in codigos), codigos


def test_retry_after_e_o_corpo_seguem_o_contrato_de_erro_do_produto(sessao_plat):
    # 1 é abaixo do mínimo (5, LIMITE_TAXA_PADROES): o corte de faixa sobe para 5 — mesma regra de
    # AUTH_PADROES, um inquilino nunca consegue configurar um teto ABAIXO do mínimo defensável.
    inq = InquilinoTemporario(sessao_plat, config={"limites": {"api_por_minuto": 1}})
    try:
        # teto real após o corte de faixa = 5 (mínimo); o setup do inquilino já gastou 1 unidade, então
        # sobram 4 antes do primeiro 429.
        respostas = [inq.admin.get("/api/eu") for _ in range(6)]
        codigos = [r.status_code for r in respostas]
        assert codigos.count(200) == 4 and codigos.count(429) == 2, codigos
        ultima = respostas[-1]
        j = ultima.json()
        assert j["erro"] == "limite_de_taxa" and "mensagem" in j and "req_id" in j
        assert j["detalhe"]["escopo"] == "api" and j["detalhe"]["maximo"] == 5  # cortado para o mínimo
        assert "retry-after" in {k.lower() for k in ultima.headers}
        assert int(ultima.headers["retry-after"]) >= 1
    finally:
        inq.apagar()


def test_nao_conta_duas_vezes_na_mesma_requisicao():
    """`limite_taxa.exigir` marca `request.state` para não bater duas vezes no banco se `resolver()` for
    chamado mais de uma vez no mesmo request (já acontece hoje: `resolver` tem cache em request.state.auth,
    mas outra rota pode chamar `sessao.autenticado()` mais de uma dependência na mesma cadeia)."""
    class FalsoState:
        pass

    class FalsoRequest:
        def __init__(self):
            self.state = FalsoState()

    req = FalsoRequest()
    # id aleatório e negativo (nunca colide com um tenant_id real, sempre positivo) — evita contaminação
    # entre execuções repetidas do teste dentro da MESMA janela de 60s (achado ao rodar duas vezes seguidas
    # com uma chave fixa: a 2ª rodada via a contagem da 1ª ainda dentro da janela deslizante).
    tenant_id = -secrets.randbelow(1_000_000_000) - 1
    config = {}
    # chama exigir() 5 vezes no MESMO objeto de requisição fake: só a 1ª deveria bater no banco
    for _ in range(5):
        limite_taxa.exigir(req, tenant_id, config, "api", "api_por_minuto")
    # confere indiretamente: a contagem real no banco (chave do tenant fake) é 1, não 5
    assert limite_taxa.contagem_atual(limite_taxa.chave_tenant(tenant_id), "api", janela_s=60) == 1
