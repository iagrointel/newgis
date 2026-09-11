/* plat — tela /admin/backup (item L0-06-backup-status): lista de backups e ensaios de restauração deste
   inquilino (GET /api/backup/backups, GET /api/backup/ensaios) com o veredito do último ensaio em
   destaque. "fazer backup agora" e "ensaiar restauração agora" usam a fila genérica (POST /api/jobs com
   tipo backup.executar / backup.ensaio_restauracao — a mesma porta que qualquer outra tarefa, que já
   recusa quem não é admin do inquilino pelo perfil_minimo registrado em app/backup/tarefas.py) e esperam a
   conclusão com um poll curto antes de recarregar as duas listas. */
import { obter, enviar, mensagemDe, consulta } from '../base/api.js';
import { h, marcador } from '../base/dom.js';
import { carregar, t, formatarData, formatarNumero } from '../base/i18n.js';
import '../base/componentes.js';
import { montarLayout, cabecalho, pronto } from '../base/layout.js';
import { exigirSessao } from '../auth/sessao.js';

const LIMITE = 50;
const POLL_INTERVALO_MS = 1500;
const POLL_TETO = 120; // ~3 min (backup.dump/ensaio no schema de demonstração é rápido; teto folgado p/ um maior)

await carregar();
const usuario = await exigirSessao({ privilegio: 'org.configurar' });
if (usuario) await iniciar();
pronto();

async function iniciar() {
  montarLayout({ usuario, ativo: '/admin/backup' });
  const btEnsaio = h('button', { type: 'button', id: 'bt-ensaio' }, t('backup.ensaiar_agora'));
  const btBackup = h('button', { type: 'button', class: 'primario', id: 'bt-backup' }, t('backup.fazer_agora'));
  btBackup.addEventListener('click', () => disparar('backup.executar', btBackup, t('backup.rodando_backup')));
  btEnsaio.addEventListener('click', () => disparar('backup.ensaio_restauracao', btEnsaio, t('backup.rodando_ensaio')));
  cabecalho(t('backup.titulo'), { botoes: [btEnsaio, btBackup] });
  montarTabelas();
  await Promise.all([carregarResumo(), carregarBackups(), carregarEnsaios()]);
}

function bytesFmt(n) {
  if (n === null || n === undefined) return '';
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function shaCurto(s) {
  return s ? `${s.slice(0, 12)}…` : '';
}

function duracaoFmt(v) {
  return v === null || v === undefined ? '' : `${Number(v).toFixed(1)} s`;
}

function montarTabelas() {
  const tb = document.getElementById('tabela-backups');
  tb.colunas = [
    { chave: 'criado_em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'esquema', titulo: t('backup.esquema'), classe: 'mono' },
    { chave: 'bytes', titulo: t('backup.tamanho'), classe: 'num', formatar: bytesFmt },
    { chave: 'tabelas', titulo: t('backup.tabelas'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'tempo_dump_s', titulo: t('backup.duracao'), classe: 'num', formatar: duracaoFmt },
    { chave: 'sha256', titulo: 'sha256', classe: 'mono', formatar: shaCurto },
    { chave: 'origem', titulo: t('backup.origem'), formatar: (v) => marcador(v, v === 'periodico' ? 'ok' : '') },
  ];
  tb.vazio = t('backup.sem_backups');

  const te = document.getElementById('tabela-ensaios');
  te.colunas = [
    { chave: 'criado_em', titulo: t('campo.quando'), formatar: (v) => formatarData(v) },
    { chave: 'ok', titulo: t('backup.veredito'),
      formatar: (v) => marcador(v ? t('backup.ok') : t('backup.reprovado'), v ? 'ok' : 'falha') },
    { chave: 'tabelas', titulo: t('backup.tabelas'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'linhas', titulo: t('backup.linhas'), classe: 'num', formatar: (v) => formatarNumero(v) },
    { chave: 'duracao_drill_s', titulo: t('backup.duracao'), classe: 'num', formatar: duracaoFmt },
    { chave: 'mensagem', titulo: t('backup.mensagem'), formatar: (v) => v || '' },
    { chave: 'schema_ensaio', titulo: t('backup.schema_ensaio'), classe: 'mono', formatar: (v) => v || '' },
  ];
  te.vazio = t('backup.sem_ensaios');
}

async function carregarResumo() {
  const corpo = document.getElementById('resumo-corpo');
  const r = await obter('/api/backup/ensaios?limite=1');
  if (r.status !== 200) { corpo.textContent = mensagemDe(r); return; }
  const item = (r.json.itens || [])[0];
  if (!item) { corpo.textContent = t('backup.sem_ensaios'); return; }
  const linhas = [
    marcador(item.ok ? t('backup.ok') : t('backup.reprovado'), item.ok ? 'ok' : 'falha'),
    document.createTextNode(
      ` · ${formatarData(item.criado_em)} · ${formatarNumero(item.tabelas)} ${t('backup.tabelas')}, `
      + `${formatarNumero(item.linhas)} ${t('backup.linhas')}, ${duracaoFmt(item.duracao_drill_s)}`,
    ),
  ];
  if (item.mensagem) linhas.push(h('div', { class: 'fraco' }, item.mensagem));
  corpo.replaceChildren(...linhas);
}

async function carregarBackups() {
  const tb = document.getElementById('tabela-backups');
  const r = await obter(`/api/backup/backups${consulta({ limite: LIMITE })}`);
  if (r.status !== 200) {
    document.getElementById('aviso').erro(`${t('erro.carregar')}: ${mensagemDe(r)}`);
    return;
  }
  tb.linhas = r.json.itens || [];
  document.getElementById('backups-total').textContent = `(${formatarNumero(r.json.total)})`;
}

async function carregarEnsaios() {
  const te = document.getElementById('tabela-ensaios');
  const r = await obter(`/api/backup/ensaios${consulta({ limite: LIMITE })}`);
  if (r.status !== 200) {
    document.getElementById('aviso').erro(`${t('erro.carregar')}: ${mensagemDe(r)}`);
    return;
  }
  te.linhas = r.json.itens || [];
  document.getElementById('ensaios-total').textContent = `(${formatarNumero(r.json.total)})`;
}

async function esperarJob(jobId) {
  for (let i = 0; i < POLL_TETO; i += 1) {
    const r = await obter(`/api/jobs/${jobId}`);
    if (r.status === 200 && ['concluido', 'falhou', 'cancelado'].includes(r.json.estado)) return r.json;
    await new Promise((resolve) => { setTimeout(resolve, POLL_INTERVALO_MS); });
  }
  return null;
}

async function disparar(tipo, botao, mensagemEspera) {
  const aviso = document.getElementById('aviso');
  botao.disabled = true;
  aviso.mostrar(mensagemEspera, 'info');
  const r = await enviar('/api/jobs', { tipo, parametros: {} });
  if (r.status !== 201) {
    aviso.erro(mensagemDe(r));
    botao.disabled = false;
    return;
  }
  const final = await esperarJob(r.json.id);
  botao.disabled = false;
  if (final === null) {
    aviso.erro(t('backup.tempo_esgotado'));
  } else if (final.estado === 'concluido') {
    aviso.ok(t('backup.concluido'));
  } else {
    aviso.erro(`${t('backup.falhou')}: ${final.mensagem || final.estado}`);
  }
  await Promise.all([carregarResumo(), carregarBackups(), carregarEnsaios()]);
}
