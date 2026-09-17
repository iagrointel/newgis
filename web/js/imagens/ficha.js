/* plat — tela /imagens/{id}/ficha (item L1-27): editor da ficha de metadado e licença da imagem.
   A lista de licenças NUNCA é escrita aqui: vem de GET /api/imagens/licencas, que devolve a tabela única de
   app/imagens/ficha.py. O cartão de cima mostra a licença vigente, a atribuição obrigatória, se a licença
   autoriza redistribuição e se o item pode sair por link público; o aviso da regra D17 (item sem licença
   escrita é auditável, não vendável) aparece ali, não em rodapé. */
import { obter, alterar } from '../base/api.js';
import { carregar, t } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const ITEM_ID = decodeURIComponent(location.pathname.split('/')[2] || '');

await carregar();
const usuario = await exigirSessao();
if (usuario) iniciar();
pronto();

function texto(id, valor) { document.getElementById(id).textContent = valor; }

function camposDe(licencas, ficha, padraoLicenca) {
  const f = ficha || {};
  return [
    { nome: 'plataforma', rotulo: t('ficha.plataforma'), tipo: 'texto', obrigatorio: true, padrao: f.plataforma || '', ajuda: t('ficha.plataforma_ajuda') },
    { nome: 'instrumentos', rotulo: t('ficha.instrumentos'), tipo: 'texto', obrigatorio: true, padrao: (f.instrumentos || []).join(', '), ajuda: t('ficha.instrumentos_ajuda') },
    { nome: 'constelacao', rotulo: t('ficha.constelacao'), tipo: 'texto', padrao: f.constelacao || '' },
    { nome: 'gsd', rotulo: t('ficha.gsd'), tipo: 'numero', obrigatorio: true, padrao: f.gsd ?? '', atributos: { step: 'any', min: 0.001 } },
    { nome: 'data_aquisicao', rotulo: t('ficha.data_aquisicao'), tipo: 'texto', obrigatorio: true, padrao: f.data_aquisicao || '', ajuda: t('ficha.data_ajuda') },
    { nome: 'data_aquisicao_fim', rotulo: t('ficha.data_aquisicao_fim'), tipo: 'texto', padrao: f.data_aquisicao_fim || '', ajuda: t('ficha.data_fim_ajuda') },
    { nome: 'nuvem_pct', rotulo: t('ficha.nuvem'), tipo: 'numero', padrao: f.nuvem_pct ?? '', atributos: { step: 'any', min: 0, max: 100 } },
    { nome: 'angulo_off_nadir', rotulo: t('ficha.off_nadir'), tipo: 'numero', padrao: f.angulo_off_nadir ?? '', atributos: { step: 'any', min: 0, max: 90 } },
    { nome: 'angulo_incidencia', rotulo: t('ficha.incidencia'), tipo: 'numero', padrao: f.angulo_incidencia ?? '', atributos: { step: 'any', min: 0, max: 90 } },
    { nome: 'sol_azimute', rotulo: t('ficha.sol_azimute'), tipo: 'numero', padrao: f.sol_azimute ?? '', atributos: { step: 'any', min: 0, max: 360 } },
    { nome: 'sol_elevacao', rotulo: t('ficha.sol_elevacao'), tipo: 'numero', padrao: f.sol_elevacao ?? '', atributos: { step: 'any', min: -90, max: 90 } },
    { nome: 'orbita_estado', rotulo: t('ficha.orbita_estado'), tipo: 'select', padrao: f.orbita_estado || '',
      opcoes: [{ valor: '', rotulo: '—' }, { valor: 'ascending', rotulo: 'ascending' }, { valor: 'descending', rotulo: 'descending' }, { valor: 'geostationary', rotulo: 'geostationary' }] },
    { nome: 'orbita_relativa', rotulo: t('ficha.orbita_relativa'), tipo: 'numero', padrao: f.orbita_relativa ?? '', atributos: { step: 1, min: 0 } },
    { nome: 'fornecedor', rotulo: t('ficha.fornecedor'), tipo: 'texto', obrigatorio: true, padrao: f.fornecedor || '' },
    { nome: 'fonte', rotulo: t('ficha.fonte'), tipo: 'select', obrigatorio: true, padrao: f.fonte || 'upload',
      opcoes: [{ valor: 'upload', rotulo: t('ficha.fonte_upload') }, { valor: 'conector', rotulo: t('ficha.fonte_conector') }] },
    { nome: 'licenca', rotulo: t('ficha.licenca'), tipo: 'select', obrigatorio: true, padrao: f.licenca || padraoLicenca,
      opcoes: licencas.map((l) => ({ valor: l.codigo, rotulo: l.rotulo })), ajuda: t('ficha.licenca_ajuda') },
    { nome: 'atribuicao', rotulo: t('ficha.atribuicao'), tipo: 'texto', padrao: f.atribuicao || '', ajuda: t('ficha.atribuicao_ajuda') },
    { nome: 'observacao', rotulo: t('ficha.observacao'), tipo: 'area', padrao: f.observacao || '', linhas: 3 },
  ];
}

function corpoDosValores(v) {
  const numero = (x) => (x === '' || x === null || x === undefined ? null : Number(x));
  return {
    plataforma: (v.plataforma || '').trim(),
    instrumentos: String(v.instrumentos || '').split(',').map((s) => s.trim()).filter(Boolean),
    constelacao: (v.constelacao || '').trim() || null,
    gsd: numero(v.gsd),
    data_aquisicao: (v.data_aquisicao || '').trim(),
    data_aquisicao_fim: (v.data_aquisicao_fim || '').trim() || null,
    nuvem_pct: numero(v.nuvem_pct),
    angulo_off_nadir: numero(v.angulo_off_nadir),
    angulo_incidencia: numero(v.angulo_incidencia),
    sol_azimute: numero(v.sol_azimute),
    sol_elevacao: numero(v.sol_elevacao),
    orbita_estado: v.orbita_estado || null,
    orbita_relativa: numero(v.orbita_relativa),
    fornecedor: (v.fornecedor || '').trim(),
    fonte: v.fonte || 'upload',
    licenca: v.licenca,
    atribuicao: (v.atribuicao || '').trim() || null,
    observacao: (v.observacao || '').trim() || null,
  };
}

function mostrarFicha(corpo) {
  texto('ficha-item', corpo.titulo || '');
  texto('ficha-licenca-rotulo', corpo.licenca.rotulo);
  texto('ficha-atribuicao', corpo.atribuicao || t('ficha.sem_atribuicao'));
  texto('ficha-redistribuicao', corpo.licenca.redistribuicao === 'livre' ? t('ficha.redistribuicao_livre') : t('ficha.redistribuicao_restrita'));
  texto('ficha-link-publico', corpo.permite_link_publico ? t('ficha.link_publico_sim') : t('ficha.link_publico_nao'));
  document.getElementById('ficha-iso').href = corpo.metadado_iso_url;
  document.getElementById('ficha-iso').hidden = !corpo.ficha;
  const av = document.getElementById('aviso-licenca');
  av.limpar();
  if (corpo.avisos.length) av.mostrar(corpo.avisos.join(' '), 'atencao');
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/conteudo' });
  cabecalho(t('ficha.titulo'));
  const aviso = document.getElementById('aviso');
  const form = document.getElementById('form-ficha');

  const [rLic, rFicha] = await Promise.all([obter('/api/imagens/licencas'), obter(`/api/imagens/${ITEM_ID}/ficha`)]);
  if (rFicha.status !== 200) { aviso.mostrar(rFicha.json.mensagem, 'erro'); return; }
  if (rLic.status !== 200) { aviso.mostrar(rLic.json.mensagem, 'erro'); return; }
  const licencas = rLic.json.licencas;
  mostrarFicha(rFicha.json);

  form.campos = camposDe(licencas, rFicha.json.ficha, rLic.json.padrao);
  form.botoes = [{ id: 'gravar', rotulo: t('ficha.gravar'), tipo: 'submit' }];
  form.addEventListener('enviar', async (e) => {
    form.ocupado = true;
    const r = await alterar(`/api/imagens/${ITEM_ID}/ficha`, corpoDosValores(e.detail.valores));
    form.ocupado = false;
    if (r.status === 200) { mostrarFicha(r.json); form.mensagem(t('ficha.gravada'), 'ok'); return; }
    const campo = r.json.detalhe && r.json.detalhe.campo;
    if (campo) form.erro(campo, r.json.mensagem);
    form.mensagem(r.json.mensagem, 'erro');
  });
}

export { camposDe, corpoDosValores };
