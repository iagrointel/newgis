/* plat — seção "Convidar por e-mail" da tela /admin/usuarios (item L0-07-d-smtp-convites): POST /api/convites
   (com ou sem SMTP — sem SMTP, o link aparece na própria lista para o admin repassar manualmente, MESMO
   caminho de "senha temporária mostrada uma vez"), GET /api/convites (pendentes) e DELETE para cancelar.
   Módulo independente de web/js/auth/usuarios.js (mesma página, elementos próprios) para não colidir com o
   que aquele arquivo já controla. */
import { obter, enviar, apagar, mensagemDe } from '../base/api.js';
import { h, limpar } from '../base/dom.js';
import { carregar, t, formatarData } from '../base/i18n.js';

await carregar();

const form = document.getElementById('form-convite');
const lista = document.getElementById('lista-convites');
const aviso = document.getElementById('convite-aviso');

function linkManualEl(link) {
  const campo = h('input', { type: 'text', readonly: true, value: link, class: 'link-manual', onclick: (e) => e.target.select() });
  return h('div', { class: 'convite-link' }, h('span', { class: 'fraco' }, t('convite.sem_smtp')), campo);
}

function itemConvite(c) {
  const botaoCancelar = h('button', { type: 'button', class: 'pequeno perigo' }, t('convite.cancelar'));
  botaoCancelar.addEventListener('click', async () => {
    botaoCancelar.disabled = true;
    const r = await apagar(`/api/convites/${c.id}`);
    if (r.status !== 204) { aviso.erro(mensagemDe(r)); botaoCancelar.disabled = false; return; }
    await carregarLista();
  });
  return h('li', { class: 'convite-item' },
    h('span', { class: 'convite-email' }, c.email),
    h('span', { class: 'marcador' }, c.perfil),
    h('span', { class: 'fraco' }, t('convite.expira_em', { quando: formatarData(c.expira_em) })),
    c.link_manual ? linkManualEl(c.link_manual) : null,
    botaoCancelar);
}

async function carregarLista() {
  const r = await obter('/api/convites');
  if (r.status !== 200) { aviso.erro(mensagemDe(r)); return; }
  limpar(lista);
  if (!r.json.length) { lista.append(h('li', { class: 'fraco' }, t('convite.nenhum'))); return; }
  for (const c of r.json) lista.append(itemConvite(c));
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  aviso.limpar();
  const email = document.getElementById('convite-email').value.trim();
  const perfil = document.getElementById('convite-perfil').value;
  if (!email) return;
  const botao = form.querySelector('button[type=submit]');
  botao.disabled = true;
  const r = await enviar('/api/convites', { email, perfil });
  botao.disabled = false;
  if (r.status !== 201) { aviso.erro(mensagemDe(r)); return; }
  document.getElementById('convite-email').value = '';
  aviso.ok(r.json.link_manual ? t('convite.criado_sem_smtp') : t('convite.criado'));
  await carregarLista();
});

await carregarLista();
