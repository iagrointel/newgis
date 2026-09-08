/* plat · tarefas — formatação: datas relativas, durações, estados com símbolo e texto, números, CSV.
   Sem DOM e sem rede; os textos vêm do dicionário (tarefas.*) e o número segue o idioma da tela (UX-05). */
import { idiomaAtual, t } from '../base/i18n.js';

export const ESTADOS = {
  pendente: { simbolo: '○', chave: 'tarefas.estado_pendente', classe: 'pendente' },
  rodando: { simbolo: '●', chave: 'tarefas.estado_rodando', classe: 'rodando' },
  concluido: { simbolo: '✓', chave: 'tarefas.estado_concluido', classe: 'concluido' },
  falhou: { simbolo: '✗', chave: 'tarefas.estado_falhou', classe: 'falhou' },
  cancelado: { simbolo: '—', chave: 'tarefas.estado_cancelado', classe: 'cancelado' },
};
export const FINAIS = new Set(['concluido', 'falhou', 'cancelado']);
export const NIVEIS = ['DEBUG', 'INFO', 'AVISO', 'ERRO'];

const dois = (n) => String(n).padStart(2, '0');

export function estado(nome) {
  const e = ESTADOS[nome];
  return e ? { simbolo: e.simbolo, rotulo: t(e.chave), classe: e.classe } : { simbolo: '?', rotulo: nome || '—', classe: 'desconhecido' };
}

export function numero(n) {
  return n == null || Number.isNaN(Number(n)) ? '—' : new Intl.NumberFormat(idiomaAtual() || 'pt-BR').format(Number(n));
}

function mesmoDia(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/* "hoje 14:02" · "ontem 18:11" · "05/09 03:30" · "05/09/2025 03:30" (ano diferente). */
export function data(iso, agora = new Date()) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const hm = `${dois(d.getHours())}:${dois(d.getMinutes())}`;
  const ontem = new Date(agora);
  ontem.setDate(agora.getDate() - 1);
  if (mesmoDia(d, agora)) return t('tarefas.hoje', { hora: hm });
  if (mesmoDia(d, ontem)) return t('tarefas.ontem', { hora: hm });
  const dm = `${dois(d.getDate())}/${dois(d.getMonth() + 1)}`;
  return d.getFullYear() === agora.getFullYear() ? `${dm} ${hm}` : `${dm}/${d.getFullYear()} ${hm}`;
}

/* "05/09/2026 14:02:10" */
export function dataHora(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()} `
    + `${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`;
}

/* "14:02:10" */
export function hora(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`;
}

/* segundos → "mm:ss" ou "h:mm:ss" */
export function duracao(segundos) {
  if (segundos == null || Number.isNaN(Number(segundos)) || segundos < 0) return '—';
  const s = Math.floor(Number(segundos));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h > 0 ? `${h}:${dois(m)}:${dois(r)}` : `${dois(m)}:${dois(r)}`;
}

/* duração de um job em segundos: terminado − iniciado; rodando = agora − iniciado; sem início = null. */
export function duracaoJob(job, agora = Date.now()) {
  if (!job || !job.iniciado_em) return null;
  const inicio = new Date(job.iniciado_em).getTime();
  if (Number.isNaN(inicio)) return null;
  if (job.terminado_em) return (new Date(job.terminado_em).getTime() - inicio) / 1000;
  if (FINAIS.has(job.estado) && job.duracao_s != null) return Number(job.duracao_s);
  return (agora - inicio) / 1000;
}

export function linhasLog(n) {
  const v = Number(n || 0);
  return v === 1 ? t('tarefas.log_linha_uma') : t('tarefas.log_linhas', { n: numero(v) });
}

/* texto curto da coluna "progresso" conforme o estado */
export function textoProgresso(job) {
  switch (job.estado) {
    case 'pendente':
      return job.cancelar_solicitado ? t('tarefas.cancelando') : (job.agendado_para && new Date(job.agendado_para) > new Date()
        ? t('tarefas.na_fila_ate', { quando: data(job.agendado_para) }) : t('tarefas.na_fila'));
    case 'rodando':
      return `${job.progresso ?? 0} %${job.mensagem ? ` · ${job.mensagem}` : ''}${job.cancelar_solicitado ? ` · ${t('tarefas.cancelando')}` : ''}`;
    case 'concluido':
      return '100 %';
    case 'falhou':
      return job.erro || t('tarefas.estado_falhou');
    case 'cancelado':
      return job.cancelado_por != null ? t('tarefas.cancelado_pelo_usuario') : t('tarefas.estado_cancelado');
    default:
      return '';
  }
}

/* quem pediu: login do usuário; sem usuário = job de agenda ou periódico da plataforma */
export function quem(job) {
  if (job.usuario_login) return job.usuario_login;
  if (job.usuario_id != null) return t('tarefas.quem_usuario', { id: job.usuario_id });
  return job.agenda_id ? t('tarefas.quem_agenda') : t('tarefas.quem_plataforma');
}

/* CSV RFC 4180 (separador ";" como o Excel em pt-BR espera; aspas dobradas) */
export function csv(cabecalho, linhas) {
  const cel = (v) => {
    const s = v == null ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
    return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cabecalho, ...linhas].map((l) => l.map(cel).join(';')).join('\r\n') + '\r\n';
}

/* "0 3 * * *" tem 5 campos separados por espaço; a validação de valores é do servidor (croniter) */
export function cronTemCincoCampos(expr) {
  return typeof expr === 'string' && expr.trim().split(/\s+/).length === 5;
}

export function fusoValido(nome) {
  if (!nome) return false;
  try {
    new Intl.DateTimeFormat('pt-BR', { timeZone: nome });
    return true;
  } catch {
    return false;
  }
}
