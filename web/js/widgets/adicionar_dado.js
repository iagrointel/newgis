import { PlatWidget, definir } from './base.js';
import { normalizarLista, deduzirCampos } from '../app/fontes.js';

export const contrato = Object.freeze({ eventos: ['dado_adicionado', 'adicionar.carregado', 'adicionar.erro'], acoes: ['adicionar.carregar'] });

/* Adicionar dado em tempo de execução (L5-01-c): GeoJSON de um arquivo do usuário ou de um caminho do próprio
   servidor entra na fonte da vista alvo como dado TEMPORÁRIO (`fonte.adicionar` -> evento `dado_adicionado`;
   o documento do app não muda e nada é gravado). Só fonte em memória aceita (embutida/arquivo/url); fonte de
   camada (servidor) recusa com mensagem — dado novo numa camada é edição (L5-03/L2-03), não isto. */
class PlatAdicionarDado extends PlatWidget {
  renderizar(mudanca = null) {
    if (mudanca) return;
    const form = document.createElement('form'); form.className = 'adicionar-form';
    const arquivo = document.createElement('input'); arquivo.type = 'file'; arquivo.accept = '.geojson,.json,application/geo+json,application/json'; arquivo.className = 'adicionar-arquivo'; arquivo.setAttribute('aria-label', 'arquivo GeoJSON');
    const url = document.createElement('input'); url.type = 'text'; url.className = 'adicionar-url'; url.setAttribute('aria-label', 'caminho no servidor'); url.title = 'caminho no mesmo domínio, por exemplo /api/arquivos/<sha256>?classe=arquivo';
    const bt = document.createElement('button'); bt.type = 'submit'; bt.className = 'adicionar-carregar'; bt.textContent = this.configuracao.rotulo || 'Adicionar dado';
    const out = document.createElement('output'); out.className = 'adicionar-estado';
    form.append(arquivo, this.configuracao.aceitar_url === false ? '' : url, bt, out);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        let bruto;
        if (arquivo.files && arquivo.files[0]) bruto = JSON.parse(await arquivo.files[0].text());
        else if (url.value) bruto = await lerCaminho(url.value);
        else throw new Error('escolha um arquivo ou informe um caminho');
        await this.acao_adicionar_carregar({ dados: bruto, nome: arquivo.files?.[0]?.name || url.value });
      } catch (err) { out.textContent = err.message; this.dataset.erro = err.message; this.emitir('adicionar.erro', { mensagem: err.message }); }
    });
    this.replaceChildren(form);
  }

  async acao_adicionar_carregar(detalhe) {
    if (!this.vista) throw new Error('widget sem vista alvo');
    const fonte = this.vista.fonte;
    if (fonte.modo === 'servidor') throw new Error('fonte de camada não aceita dado temporário; use a edição da camada');
    const lista = normalizarLista(detalhe.dados);
    if (!lista.length) throw new Error('nenhuma feição no dado');
    const base = fonte.feicoes.length;
    const usados = new Set(fonte.feicoes.map((f) => f.id));
    lista.forEach((f, i) => { if (usados.has(f.id)) { f.id = `tmp-${base + i}`; f.propriedades.__id = f.id; } });
    if (!fonte.campos.length) fonte.campos = deduzirCampos(lista);
    fonte.adicionar(lista);
    delete this.dataset.erro;
    this.dataset.adicionados = String(lista.length);
    const out = this.querySelector('.adicionar-estado'); if (out) out.textContent = `${lista.length} feição(ões) adicionada(s) (temporário)`;
    this.emitir('adicionar.carregado', { n: lista.length, nome: detalhe.nome || '' });
    return lista.length;
  }
}

async function lerCaminho(caminho) {
  if (!caminho.startsWith('/')) throw new Error('só caminho do próprio servidor (começa com /)');
  const r = await fetch(caminho, { credentials: 'same-origin', headers: { Accept: 'application/geo+json, application/json' } });
  if (!r.ok) throw new Error(`${caminho}: HTTP ${r.status}`);
  return r.json();
}

definir('plat-adicionar-dado', PlatAdicionarDado);
