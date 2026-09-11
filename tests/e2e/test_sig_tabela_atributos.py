"""Gaveta: integração na rede viva e casos determinísticos no navegador, sem alterar dados da bancada."""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect

from tests.conftest import valores_env
from tests.e2e.apoio import Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]
WEB = Path(__file__).resolve().parents[2] / 'web'


@pytest.fixture(scope='session')
def base_url(request):
    # Os casos com transporte simulado não precisam de banco nem de .env; o caso vivo salta sem URL.
    return (request.config.getoption('base_url', default=None)
            or valores_env().get('PLAT_URL_PUBLICA') or 'http://tabela.invalid').rstrip('/')


@pytest.fixture
def gaveta(page, base_url):
    """DOM/CSS/módulos reais; só mapa e transporte simulados para limites e respostas atrasadas."""
    def estatico(route):
        caminho = WEB / urlparse(route.request.url).path.removeprefix('/static/')
        tipo = 'text/javascript' if caminho.suffix == '.js' else None
        route.fulfill(path=caminho, content_type=tipo)

    page.route('**/static/**', estatico)
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', (WEB / 'sig.html').read_text(), flags=re.S)
    page.route('**/tabela-harness', lambda route: route.fulfill(body=html, content_type='text/html'))
    page.goto(f'{base_url}/tabela-harness')
    page.evaluate("""async () => {
      const { carregar } = await import('/static/js/base/i18n.js'); await carregar('pt-BR');
      const modulo = await import('/static/js/mapa/tabela_atributos.js');
      const layers = new Map([['pontos', {id: 'pontos', type: 'circle', source: 'dados'}]]);
      const handlers = {};
      window.mapaTeste = {
        layers, handlers, enquadramentos: [], alvo: null,
        on: (nome, fn) => { handlers[nome] = fn; },
        getLayer: (id) => layers.get(id),
        getPaintProperty: () => 4,
        addLayer: (l) => layers.set(l.id, l), removeLayer: (id) => layers.delete(id),
        setFilter: (id, filtro) => { layers.get(id).filter = filtro; },
        getCanvas: () => document.getElementById('mapa'),
        queryRenderedFeatures: () => mapaTeste.alvo ? [mapaTeste.alvo] : [],
        fitBounds: (...args) => mapaTeste.enquadramentos.push(args),
      };
      const nomes = {elGaveta:'', elAlca:'-alca', elTitulo:'-titulo', elContagem:'-contagem',
        elFiltro:'-filtro', elAbas:'-abas', elCabecalho:'-cabecalho', elCorpo:'-corpo',
        elFechar:'-fechar', elSentinela:'-sentinela'};
      const elementos = Object.fromEntries(Object.entries(nomes).map(([k,v]) =>
        [k, document.getElementById('tabela-gaveta' + v)]));
      window.gavetaTeste = modulo.montarGaveta({...elementos, map: mapaTeste});
      window.feicoesTeste = Array.from({length: 1205}, (_, i) => ({type:'Feature',
        properties: {id:String(i), nome:'linha ' + i, valor:i === 3 ? null : String(1205-i),
          tipo:'Transformador', disciplina:'elétrica', fase_bitmask:7, _interno:'busca oculta'},
        geometry:{type:'Point', coordinates:[-46 + i*.0001, -23]}}));
      window.fonteTeste = {chave:'teste', titulo:'Teste', idCampo:'id', campos:null, abas:null,
        obterTotal:async () => feicoesTeste.length,
        obterPagina:async (offset, limite) => feicoesTeste.slice(offset, offset+limite),
        camadas:[{id:'pontos', type:'circle', source:'dados'}]};
      window.moduloTabela = modulo;
      gavetaTeste.abrir(fonteTeste);
    }""")
    expect(page.locator('#tabela-gaveta-contagem')).to_have_text('1.205 de 1.205')
    return page


def test_lotes_filtro_ordem_selecao_mapa_teclado(gaveta):
    page = gaveta
    linhas = page.locator('#tabela-gaveta-corpo tr[data-id]')
    assert linhas.count() == 200
    assert page.locator('#tabela-gaveta-cabecalho th').all_text_contents() == [
        'nome', 'valor', 'tipo', 'disciplina',
    ]
    linhas.nth(0).click()
    linhas.nth(2).click(modifiers=['Control'])
    assert page.locator('tr.selecionada').count() == 2
    linhas.nth(5).click(modifiers=['Shift'])
    assert page.locator('tr.selecionada').count() == 4
    assert page.evaluate("mapaTeste.layers.get('pontos--realce').filter[2][1]") == ['2', '3', '4', '5']
    page.locator('#tabela-gaveta-filtro').fill('busca oculta')
    expect(page.locator('#tabela-gaveta-contagem')).to_have_text('1.205 de 1.205')
    page.locator('#tabela-gaveta-filtro').fill('linha 1199')
    expect(page.locator('#tabela-gaveta-contagem')).to_have_text('1 de 1.205')
    page.evaluate("""() => {
      mapaTeste.alvo = feicoesTeste[900]; mapaTeste.handlers.click({point:{x:0,y:0}});
    }""")
    expect(page.locator('tr.selecionada')).to_have_attribute('data-id', '900')
    expect(page.locator('tr.selecionada')).to_be_in_viewport()
    assert linhas.count() >= 1000
    assert page.locator('#tabela-gaveta-filtro').input_value() == ''
    page.locator('#tabela-gaveta-cabecalho th').nth(1).click()
    expect(page.locator('#tabela-gaveta-cabecalho th').nth(1)).to_have_attribute('aria-sort', 'ascending')
    expect(linhas.first).to_have_attribute('data-id', '1204')
    page.locator('#tabela-gaveta-cabecalho th').nth(1).click()
    expect(linhas.first).to_have_attribute('data-id', '0')
    page.locator('#tabela-gaveta-cabecalho th').nth(1).click()
    expect(page.locator('#tabela-gaveta-cabecalho th').nth(1)).to_have_attribute('aria-sort', 'none')
    linhas.nth(1).focus()
    page.keyboard.press('Enter')
    expect(linhas.nth(1)).to_have_class('selecionada')
    page.evaluate("""() => {
      mapaTeste.getCanvas().style.cursor = 'crosshair'; mapaTeste.alvo = feicoesTeste[20];
      mapaTeste.handlers.click({point:{x:0,y:0}});
    }""")
    expect(linhas.nth(1)).to_have_class('selecionada')
    page.keyboard.press('Escape')
    expect(page.locator('#tabela-gaveta')).to_be_hidden()
    assert not page.evaluate("mapaTeste.layers.has('pontos--realce')")


def test_paginacao_teto_e_resposta_antiga(gaveta):
    page = gaveta
    page.evaluate("""() => {
      window.pedidos = [];
      gavetaTeste.abrir({...fonteTeste, chave:'grande', obterTotal:async () => 21001,
        obterPagina:async (offset, limite) => {
          pedidos.push([offset,limite]);
          return Array.from({length:limite}, (_,i) => ({...feicoesTeste[0],
            properties:{...feicoesTeste[0].properties, id:String(offset+i)}}));
        }});
    }""")
    expect(page.locator('#tabela-gaveta-titulo')).to_have_text('Teste — mostrando 20.000 de 21.001')
    pedidos = page.evaluate('pedidos')
    assert pedidos[0] == [0, 500]
    assert pedidos[1] == [500, 2000]
    assert pedidos[-1] == [18500, 1500]
    assert sum(limite for _, limite in pedidos) == 20000
    assert page.locator('#tabela-gaveta-corpo tr[data-id]').count() == 200
    page.evaluate("""() => {
      gavetaTeste.abrir({...fonteTeste, chave:'antiga', obterPagina:() =>
        new Promise((r) => {window.responderAntiga = r;})});
      gavetaTeste.abrir({...fonteTeste, chave:'nova', titulo:'Nova'});
      responderAntiga([{...feicoesTeste[0], properties:{id:'antiga', nome:'errada'}}]);
    }""")
    expect(page.locator('#tabela-gaveta-contagem')).to_have_text('1.205 de 1.205')
    expect(page.locator('#tabela-gaveta-titulo')).to_have_text('Nova')
    assert page.locator('tr[data-id="antiga"]').count() == 0


def test_popup_e_fontes_desligadas(gaveta):
    page = gaveta
    dados = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'id': 'uuid-1', 'tipo': 'Transformador'}, 'geometry': None},
    ]}
    chamadas = []

    def rede(route):
        chamadas.append(route.request.url)
        route.fulfill(json=dados)

    page.route('**/api/rede/rede-teste/feicoes/*.geojson', rede)
    resultado = page.evaluate("""async () => {
      const fonte = moduloTabela.fonteDeRede(mapaTeste, {id:'rede-teste', nome:'Rede'}, 'pontos');
      const [a,b,c] = await Promise.all([fonte.obterTotal(), fonte.obterPagina(0,500), fonte.obterTotal()]);
      gavetaTeste.abrir(fonte);
      const { montarConteudo, camposDestaque } = await import('/static/js/mapa/atributos.js');
      const props = Object.fromEntries(Array.from({length:9}, (_,i) => ['campo'+i, '<b>dado</b>']));
      const campos = Object.keys(props).slice(0,8).map(nome => ({nome}));
      const {caixa} = montarConteudo(new Map([['camada',[{properties:props}]]]),
        {ficha:() => ({titulo:'Popup',campos})});
      document.body.append(caixa);
      const antes = caixa.querySelectorAll('tr').length;
      caixa.querySelector('button').click();
      return {a,c,n:b.length, camadas:fonte.camadas.length, antes,
        depois:caixa.querySelectorAll('tr').length, htmlInjetado:caixa.querySelectorAll('b').length,
        destaque:camposDestaque([{nome:'a'},{nome:'b',destaque:true}],1).map(c=>c.nome)};
    }""")
    assert resultado == {'a': 1, 'c': 1, 'n': 1, 'camadas': 0, 'antes': 6,
                         'depois': 9, 'htmlInjetado': 0, 'destaque': ['b']}
    expect(page.locator('#tabela-gaveta-abas button').nth(1)).to_have_text('Linhas (1)')
    page.locator('#tabela-gaveta-abas button').nth(1).click()
    expect(page.locator('#tabela-gaveta-titulo')).to_have_text('Rede — Linhas')
    assert len(chamadas) == 2



def test_catalogo_desligado_menu_e_query(gaveta):
    page = gaveta
    pedidos = []

    def consulta(route):
        params = parse_qs(urlparse(route.request.url).query)
        pedidos.append(params)
        if params.get('returnCountOnly') == ['true']:
            route.fulfill(json={'count': 2501})
            return
        offset = int(params['resultOffset'][0])
        limite = int(params['resultRecordCount'][0])
        route.fulfill(json={'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'fid': i, 'nome': f'feição {i}'}, 'geometry': None}
            for i in range(offset, min(offset + limite, 2501))
        ]})

    page.route('**/rest/services/camada-teste/FeatureServer/0/query?*', consulta)
    page.evaluate("""async () => {
      gavetaTeste.fechar();
      const { Arvore } = await import('/static/js/camadas.js');
      const catalogo = {ativas:[], aoMudar:() => {}, idsDeEstilo:() => ['vetor'],
        ficha:() => ({id:'camada-teste', titulo:'Catálogo', campos:[{nome:'fid'},{nome:'nome'}],
          estilo:[{id:'vetor',type:'fill',source:'plat-camada-teste','source-layer':'dados'}]})};
      const raiz = document.getElementById('lista-camadas');
      const arvore = new Arvore(catalogo, mapaTeste, raiz, {aoAbrirPainel:(acao,id) => {
        gavetaTeste.abrir(moduloTabela.fonteDeCamada(catalogo,mapaTeste,id));
      }});
      raiz.append(arvore._linha({tipo:'camada',id:'camada-teste',chave:'teste'},0));
      document.getElementById('painel-camadas').hidden = false;
      window.catalogoTeste = catalogo;
    }""")
    botao = page.locator('#lista-camadas').get_by_role('button', name='mais ações')
    botao.focus()
    page.keyboard.press('Enter')
    expect(page.get_by_role('menuitem', name='Mostrar tabela')).to_be_visible()
    page.keyboard.press('Enter')
    expect(page.locator('#tabela-gaveta-contagem')).to_have_text('2.501 de 2.501')
    assert not page.locator('#lista-camadas input[type=checkbox]').is_checked()
    paginas = [p for p in pedidos if 'resultOffset' in p]
    assert [p['resultOffset'] for p in paginas] == [['0'], ['500'], ['2500']]
    assert all(p['orderByFields'] == ['fid ASC'] and p['f'] == ['geojson'] for p in paginas)
    page.evaluate("""() => {
      mapaTeste.layers.set('vetor', catalogoTeste.ficha().estilo[0]);
      document.getElementById('painel-camadas').hidden = true;
    }""")
    page.locator('#tabela-gaveta-corpo tr[data-id]').first.click()
    realce = page.evaluate("mapaTeste.layers.get('vetor--realce')")
    assert realce['type'] == 'line'
    assert realce['source-layer'] == 'dados'
    assert realce['filter'][2][1] == [0]
    page.keyboard.press('Escape')
    assert not page.evaluate("mapaTeste.layers.has('vetor--realce')")

def test_rede_viva_menu_abas_realce_e_escape(page, base_url, credenciais_demo):
    tela = Tela(page, base_url)
    tela.entrar(*credenciais_demo)
    tela.ir('/sig')
    rede = page.locator('#rede-lista > li').first
    expect(rede).to_be_visible(timeout=20000)
    caixa = rede.locator('input[type=checkbox]')
    caixa.check()
    expect(caixa).to_be_enabled(timeout=30000)
    rede.locator('.camada-titulo').click(button='right')
    page.get_by_role('menuitem', name='Mostrar tabela', exact=True).click()
    linha = page.locator('#tabela-gaveta-corpo tr[data-id]').first
    expect(linha).to_be_visible(timeout=30000)
    linha.click()
    page.wait_for_function("""() => window.plat.sig.map.getStyle().layers.some(l =>
      l.id.endsWith('--realce') && l.filter[2][1].length && l.filter[2][1][0] !== '__nenhum__')""")
    page.locator('#tabela-gaveta-abas button').nth(1).click()
    expect(page.locator('#tabela-gaveta-titulo')).to_contain_text('Linhas')
    expect(linha).to_be_visible(timeout=30000)
    linha.click()
    page.wait_for_function("""() => window.plat.sig.map.getStyle().layers.some(l =>
      l.id.endsWith('--realce') && l.type === 'line' && l.filter[2][1][0] !== '__nenhum__')""")
    page.keyboard.press('Escape')
    expect(page.locator('#tabela-gaveta')).to_be_hidden()
    assert not page.evaluate("window.plat.sig.map.getStyle().layers.some(l => l.id.endsWith('--realce'))")
    caixa.uncheck()
    rede.get_by_role('button', name='mais ações').click()
    page.get_by_role('menuitem', name='Mostrar tabela', exact=True).click()
    expect(linha).to_be_visible(timeout=30000)
    assert not caixa.is_checked()
    # A bancada pode ter tiles externos indisponíveis; erros JS da funcionalidade nunca são tolerados.
    assert not [e for e in tela.console if e.startswith('pageerror:')]
