/* Ataque adversarial G3 ao item L0-05-c-tela-tarefas — refutação literal: "deixa a aba aberta 2 h
   (reconexão do SSE)". O servidor (app/jobs/eventos.py, DURACAO_MAX_S=1800) fecha TODA conexão aos 30 min
   mandando `event: fim` com o estado REAL do job (NÃO final) e o motivo "tempo máximo da conexão (30 min);
   reconecte". Este roteiro carrega o MÓDULO REAL web/js/jobs/eventos.js com um EventSource de mentira e
   mede o que a página faz quando esse `fim` chega. Rode: node tests/api/adversario_g3/g3_sse_reconexao.mjs */

const ouvintesPorInstancia = [];
class EventSourceFalso {
  static CONNECTING = 0; static OPEN = 1; static CLOSED = 2;
  constructor(url) { this.url = url; this.readyState = 1; this.ouvintes = {}; this.fechado = false;
    ouvintesPorInstancia.push(this); }
  addEventListener(tipo, fn) { (this.ouvintes[tipo] ||= []).push(fn); }
  close() { this.fechado = true; this.readyState = 2; }
  emitir(tipo, dados) { for (const fn of this.ouvintes[tipo] || []) fn({ data: JSON.stringify(dados) }); }
}
globalThis.EventSource = EventSourceFalso;
globalThis.window = globalThis;
globalThis.document = { addEventListener() {}, querySelectorAll: () => [], getElementById: () => null };
globalThis.fetch = async () => ({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({}) });

const eventos = await import('../../../web/js/jobs/eventos.js');

const id = '00000000-0000-4000-8000-000000000000';
const recebidos = [];
const assinou = eventos.assinar(id, (ev) => recebidos.push(ev.tipo));
const es = ouvintesPorInstancia[0];

// o servidor manda o `fim` de FIM DE CONEXÃO: estado NÃO final + motivo de reconexão (eventos.py linha final
// do laço: yield _sse("fim", {"id": jid, "estado": job["estado"], "motivo": "tempo máximo da conexão ..."}))
es.emitir('fim', { id, estado: 'rodando', motivo: 'tempo máximo da conexão (30 min); reconecte' });

const aindaAssinado = eventos.assinado(id);
const conexaoFechada = es.fechado;
const resultado = {
  assinou_no_inicio: assinou,
  eventos_entregues: recebidos,
  ainda_assinado_apos_o_fim_de_conexao: aindaAssinado,
  conexao_do_navegador_fechada: conexaoFechada,
  modo_apos_o_fim: eventos.modo(id),
  total_de_assinaturas: eventos.total(),
};
console.log(JSON.stringify(resultado, null, 2));
if (aindaAssinado) { console.log('PASSA: a página continua assinada e volta a receber progresso'); process.exit(0); }
console.log('CAI: o job segue RODANDO no servidor e a página parou de receber qualquer evento '
          + '(assinatura apagada por encerrar(), sem nenhuma reassinatura) — a tela de detalhe fica muda');
process.exit(1);
