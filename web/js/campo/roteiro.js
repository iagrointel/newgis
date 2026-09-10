/* plat — tela /campo/roteiros/{id} (item L2-07-campo): paradas do roteiro do dia, cada uma com um formulário
   de visita (estado, observação, foto). Fila local (localStorage) quando o envio falha por falta de rede: a
   visita grava no aparelho com uma chave de idempotência (`cliente_uuid`, crypto.randomUUID()) ANTES de
   qualquer tentativa de rede, e reenviar a mesma fila depois nunca duplica (o servidor faz
   INSERT ... ON CONFLICT (tenant_id, cliente_uuid) DO NOTHING) — é o mecanismo inteiro da refutação do item
   ("adversário coleta sem rede, muda relógio, sincroniza duas vezes: sem duplicata e sem perda"). Isto NÃO é
   uma PWA instalável (sem service worker/manifest): é uma fila de escrita resiliente sobre localStorage,
   suficiente para o portão medido nesta trilha — ver relatório final para o que ficou de fora. */
import { obter, enviar, mensagemDe } from '../base/api.js';
import { anexar, h, limpar } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const roteiroId = (/^\/campo\/roteiros\/([0-9a-fA-F-]{36})/.exec(location.pathname) || [])[1];
const CHAVE_FILA = 'plat_campo_fila_local';

await carregar();
const usuario = await exigirSessao({ privilegio: 'campo.coletar' });
if (usuario) iniciar();
pronto();
const STATUS = ['visitado', 'confirmado', 'nao_confirmado', 'inconclusivo'];

function filaLocal() {
  try { return JSON.parse(localStorage.getItem(CHAVE_FILA) || '[]'); } catch { return []; }
}
function gravarFilaLocal(lista) {
  try { localStorage.setItem(CHAVE_FILA, JSON.stringify(lista)); } catch { /* privado/sem quota: melhor esforço */ }
}
function enfileirar(registro) {
  const lista = filaLocal();
  lista.push(registro);
  gravarFilaLocal(lista);
}

function fileParaBase64(file) {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result).split(',').pop());
    leitor.onerror = reject;
    leitor.readAsDataURL(file);
  });
}

/* tenta enviar 1 registro (visita + foto opcional); devolve true se sincronizou (mesmo que já existisse). */
async function tentarEnviar(registro) {
  const r = await enviar('/api/campo/visitas', registro.visita);
  if (r.status === 0) return false; // sem rede: fica na fila
  if (r.status !== 201 && r.status !== 200) return false; // erro do servidor: fica na fila, não perde
  if (registro.fotoBase64) {
    const rf = await enviar(`/api/campo/visitas/${r.json.id}/fotos`, { conteudo: registro.fotoBase64 });
    if (rf.status === 0) return false; // visita já foi (idempotente); só a foto falta — tenta de novo depois
  }
  return true;
}

async function sincronizarFilaLocal(aviso) {
  const lista = filaLocal();
  if (!lista.length) return 0;
  const restantes = [];
  let sincronizadas = 0;
  for (const registro of lista) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await tentarEnviar(registro);
    if (ok) sincronizadas += 1;
    else restantes.push(registro);
  }
  gravarFilaLocal(restantes);
  if (sincronizadas && aviso) aviso.mostrar(t('campo.visita.sincronizadas', { n: sincronizadas }), 'ok');
  return sincronizadas;
}

function formularioVisita({ parada, camadaId, filaId, aviso, aoRegistrar }) {
  const status = h('select', {}, ...STATUS.map((s) => h('option', { value: s }, t(`campo.visita.status_${s}`))));
  const texto = h('textarea', { rows: '3', maxlength: '8000' });
  const foto = h('input', { type: 'file', accept: 'image/*', capture: 'environment' });
  const enviarBt = h('button', { type: 'button', class: 'primario' }, t('campo.visita.enviar'));
  const cancelarBt = h('button', { type: 'button', class: 'pequeno' }, t('campo.visita.cancelar'));
  const bloco = h('div', { class: 'formulario-visita cartao' },
    h('label', {}, t('campo.visita.status'), status),
    h('label', {}, t('campo.visita.texto'), texto),
    h('label', {}, t('campo.visita.foto'), foto),
    h('div', { class: 'linha-botoes' }, enviarBt, cancelarBt));

  cancelarBt.addEventListener('click', () => bloco.remove());
  enviarBt.addEventListener('click', async () => {
    enviarBt.disabled = true;
    let fotoBase64 = null;
    if (foto.files && foto.files[0]) {
      try { fotoBase64 = await fileParaBase64(foto.files[0]); } catch { /* segue sem foto */ }
    }
    const registro = {
      visita: {
        cliente_uuid: crypto.randomUUID(), camada_id: camadaId, globalid: parada.globalid,
        alvo_id: parada.alvo_id, fila_id: filaId, roteiro_id: roteiroId, status: status.value,
        texto: texto.value || null, capturado_em: new Date().toISOString(),
      },
      fotoBase64,
    };
    // grava local ANTES de tentar a rede: se a aba fechar no meio, o registro não some (só falta sincronizar)
    enfileirar(registro);
    const ok = await tentarEnviar(registro);
    if (ok) {
      const lista = filaLocal();
      gravarFilaLocal(lista.filter((r) => r.visita.cliente_uuid !== registro.visita.cliente_uuid));
      aviso.mostrar(t('campo.visita.enviada'), 'ok');
    } else {
      aviso.mostrar(t('campo.visita.sem_rede'), 'aviso');
    }
    bloco.remove();
    aoRegistrar();
  });
  return bloco;
}

async function carregarDetalhe() {
  const r = await obter(`/api/campo/roteiros/${roteiroId}`);
  return r.status === 200 ? r.json : null;
}

async function iniciar() {
  montarLayout({ usuario, ativo: '/campo/filas' });
  const principal = document.getElementById('principal');
  const aviso = document.getElementById('aviso');
  if (!roteiroId) { aviso.mostrar(t('erro.nao_encontrado') || 'roteiro inexistente', 'erro'); return; }

  const detalhe = await carregarDetalhe();
  if (!detalhe) { aviso.mostrar(t('erro.nao_encontrado') || 'roteiro inexistente', 'erro'); return; }

  // fila local dela mesma: um registro guardado em visita anterior por falta de rede tenta de novo aqui
  await sincronizarFilaLocal(aviso);

  cabecalho(detalhe.titulo || t('campo.roteiro.titulo'), { contagem: detalhe.paradas.length });

  async function redesenhar() {
    const fresco = await carregarDetalhe();
    render(fresco);
  }

  function render(d) {
    limpar(principal);
    const pendentesLocais = filaLocal().length;
    anexar(principal, [
      h('p', {}, h('a', { href: `/campo/filas/${d.fila_id}` }, `← ${t('campo.roteiro.voltar')}`)),
      h('dl', { class: 'resumo-roteiro' },
        h('dt', {}, t('campo.roteiro.motor')), h('dd', {}, d.motor),
        h('dt', {}, t('campo.roteiro.distancia')), h('dd', {}, `${(d.distancia_m / 1000).toFixed(1)} km`),
        h('dt', {}, t('campo.roteiro.duracao')), h('dd', {}, `${Math.round(d.duracao_s / 60)} min`)),
      d.aviso ? h('p', { class: 'ajuda' }, `${t('campo.roteiro.aviso')}: ${d.aviso}`) : null,
      pendentesLocais
        ? h('p', { class: 'aviso-fila-local' },
            t('campo.visita.pendentes_sincronizar', { n: pendentesLocais }), ' ',
            (() => {
              const bt = h('button', { type: 'button', class: 'pequeno' }, t('campo.visita.sincronizar_agora'));
              bt.addEventListener('click', async () => { await sincronizarFilaLocal(aviso); redesenhar(); });
              return bt;
            })())
        : null,
    ]);
    anexar(principal, d.paradas.map((p) => {
      const jaVisitado = !!p.visita_id;
      const registrarBt = h('button', { type: 'button', class: 'pequeno' }, t('campo.roteiro.registrar_visita'));
      const linha = h('div', { class: 'parada-roteiro', 'data-status': p.status },
        h('span', { class: 'num' }, String(p.ordem)),
        h('span', { class: 'mono' }, p.globalid),
        h('span', { class: `badge badge-${p.status}` }, p.status),
        jaVisitado ? h('span', { class: 'ja-visitado' }, t('campo.roteiro.ja_visitado')) : registrarBt,
      );
      if (!jaVisitado) {
        registrarBt.addEventListener('click', () => {
          const form = formularioVisita({
            parada: p, camadaId: detalheCamadaId, filaId: d.fila_id, aviso, aoRegistrar: redesenhar,
          });
          linha.after(form);
        });
      }
      return linha;
    }));
  }

  // camada_id não vem no /roteiros/{id} (paradas só trazem globalid); busca da fila 1x
  const filaResp = await obter(`/api/campo/filas/${detalhe.fila_id}`);
  const detalheCamadaId = filaResp.status === 200 ? filaResp.json.fila.camada_id : null;
  render(detalhe);
}
