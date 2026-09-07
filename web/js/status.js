/* Página /status (item L0-06-e-status): lê GET /api/status e desenha. Sem sessão, sem token — a rota é aberta
   e devolve só agregado. A página recarrega sozinha a cada 60 s (o retrato do servidor tem cache de 30 s, então
   pedir mais que isso não traz número novo). */

const ESTADOS = { ok: "no ar", degradado: "degradado", erro: "fora do ar", ausente: "não se aplica" };
const RECARGA_MS = 60000;

function texto(el, valor) { el.textContent = valor; }

function classeEstado(estado) { return "status-estado status-estado-" + (estado || "ausente"); }

function bytesLegiveis(n) {
  if (n === null || n === undefined) return "—";
  const u = ["B", "KiB", "MiB", "GiB", "TiB"];
  let v = Number(n), i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i += 1; }
  return v.toFixed(v >= 100 || i === 0 ? 0 : 1) + " " + u[i];
}

function dataLegivel(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function linhaServico(nome, servico, disponibilidade) {
  const tr = document.createElement("tr");
  const d = disponibilidade[nome];
  const pct = d && d.pct !== null && d.pct !== undefined ? d.pct.toFixed(3) + " %" : "sem amostra";
  const celulas = [
    nome,
    ESTADOS[servico.estado] || servico.estado,
    servico.tempo_ms === undefined ? "—" : String(servico.tempo_ms),
    pct + (d ? " (" + d.ok + " de " + d.amostras + " amostras)" : ""),
  ];
  celulas.forEach((valor, i) => {
    const td = document.createElement("td");
    if (i === 1) td.className = classeEstado(servico.estado);
    texto(td, valor);
    tr.appendChild(td);
  });
  return tr;
}

function faixa(dias) {
  const div = document.createElement("div");
  div.className = "faixa";
  dias.forEach((d) => {
    const col = document.createElement("div");
    const proporcao = d.amostras > 0 ? d.ok / d.amostras : 0;
    col.className = "dia" + (d.amostras === 0 ? "" : proporcao === 1 ? "" : proporcao > 0 ? " parcial" : " caiu");
    col.title = d.dia + ": " + d.ok + " de " + d.amostras + " amostras no ar";
    const barra = document.createElement("span");
    barra.style.height = Math.round((d.amostras > 0 ? proporcao : 0) * 100) + "%";
    col.appendChild(barra);
    div.appendChild(col);
  });
  return div;
}

function numeros(j) {
  const itens = [
    ["na fila", j.fila.na_fila],
    ["executando", j.fila.executando],
    ["falhas em 24 h", j.fila.falhas_24h],
    ["migrações aplicadas", j.migracoes.aplicadas],
    ["migrações pendentes", j.migracoes.pendentes],
    ["última cópia de segurança", dataLegivel(j.backup.ultimo_em) + (j.backup.esquemas ? " · " + j.backup.esquemas + " esquemas · " + bytesLegiveis(j.backup.bytes) : "")],
    ["último ensaio de restauração", j.ensaio_restauracao.indisponivel
      ? j.ensaio_restauracao.indisponivel
      : dataLegivel(j.ensaio_restauracao.ultimo_em) + (j.ensaio_restauracao.ultimo_em ? (j.ensaio_restauracao.ok ? " · passou" : " · falhou") + " · " + (j.ensaio_restauracao.divergencias || 0) + " divergências" : "")],
    ["espaço livre em disco", j.disco.menor_livre_pct === null ? "—" : j.disco.menor_livre_pct + " % (menor volume)"],
    ["espaço usado no armazenamento de objetos", j.bucket.estado === "ok"
      ? bytesLegiveis(j.bucket.bytes_aprox) + " em " + j.bucket.objetos + " objetos e " + j.bucket.buckets + " buckets"
      : (j.bucket.motivo || j.bucket.estado)],
    ["espaço livre no armazenamento de objetos", j.bucket.estado === "ok"
      ? bytesLegiveis(j.bucket.livre_bytes_aprox) + " (estimativa do próprio armazenamento)"
      : "—"],
    ["certificado TLS", j.certificado.dias_restantes === null || j.certificado.dias_restantes === undefined
      ? "não verificável nesta topologia" : j.certificado.dias_restantes + " dias restantes"],
  ];
  const dl = document.getElementById("numeros");
  dl.replaceChildren();
  itens.forEach(([rotulo, valor]) => {
    const par = document.createElement("div");
    par.className = "numero";
    const dt = document.createElement("dt");
    texto(dt, rotulo);
    const dd = document.createElement("dd");
    texto(dd, valor === null || valor === undefined ? "—" : String(valor));
    par.appendChild(dt);
    par.appendChild(dd);
    dl.appendChild(par);
  });
}

function desenhar(j) {
  texto(document.getElementById("geral-texto"), "estado geral: " + (ESTADOS[j.estado] || j.estado));

  const corpo = document.querySelector("#tabela-servicos tbody");
  corpo.replaceChildren();
  const disp = (j.disponibilidade_mes && j.disponibilidade_mes.servicos) || {};
  Object.entries(j.servicos).forEach(([nome, s]) => corpo.appendChild(linhaServico(nome, s, disp)));
  texto(document.getElementById("nota-disponibilidade"),
    "percentual calculado das amostras gravadas desde " + dataLegivel(j.disponibilidade_mes.desde) +
    "; amostra 'não se aplica' fica fora da conta.");

  const hist = document.getElementById("historico");
  hist.replaceChildren();
  Object.entries(j.historico.servicos).forEach(([nome, dias]) => {
    const h = document.createElement("h3");
    texto(h, nome);
    hist.appendChild(h);
    hist.appendChild(faixa(dias));
  });
  if (!Object.keys(j.historico.servicos).length) {
    const p = document.createElement("p");
    texto(p, "ainda sem amostra gravada: a primeira verificação periódica ainda não rodou.");
    p.className = "nota";
    hist.appendChild(p);
  }

  numeros(j);

  const ul = document.getElementById("correcoes");
  ul.replaceChildren();
  j.correcoes.forEach((c) => {
    const li = document.createElement("li");
    texto(li, (c.secao ? c.secao + " — " : "") + c.texto);
    ul.appendChild(li);
  });
  if (!j.correcoes.length) {
    const li = document.createElement("li");
    texto(li, "nenhuma correção registrada no CHANGELOG.");
    ul.appendChild(li);
  }

  texto(document.getElementById("rodape"),
    "retrato de " + dataLegivel(j.em) + " · recalculado no máximo a cada " + j.cache_s + " s · " + j.tempo_ms + " ms");
}

async function carregar() {
  try {
    const r = await fetch("/api/status", { headers: { accept: "application/json" } });
    desenhar(await r.json());
    document.body.dataset.pronto = "1";  // marca de "primeira carga terminada" que os e2e da casa esperam
  } catch (e) {
    texto(document.getElementById("geral-texto"), "não foi possível ler /api/status: " + e.message);
  }
}

carregar();
setInterval(carregar, RECARGA_MS);
