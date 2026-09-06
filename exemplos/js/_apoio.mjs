// Apoio dos exemplos em JavaScript: variáveis de ambiente e uma chamada HTTP com o fetch nativo do Node.
export const URL_BASE = (process.env.PLAT_URL || "http://127.0.0.1:8153").replace(/\/$/, "");
export const CHAVE = process.env.PLAT_CHAVE || "";

export async function chamar(caminho, { metodo = "GET", corpo = null, chave = null } = {}) {
  const cabecalhos = { Accept: "application/json" };
  const valor = chave === null ? CHAVE : chave;
  if (valor) cabecalhos.Authorization = "Bearer " + valor;
  if (corpo !== null) cabecalhos["Content-Type"] = "application/json";
  const r = await fetch(URL_BASE + caminho, {
    method: metodo,
    headers: cabecalhos,
    body: corpo === null ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  let objeto = null;
  try {
    objeto = texto ? JSON.parse(texto) : null;
  } catch {
    objeto = { corpo_nao_json: texto.slice(0, 200) };
  }
  return { status: r.status, cabecalhos: r.headers, objeto };
}

export function exigir(condicao, mensagem) {
  if (!condicao) {
    console.error("FALHOU: " + mensagem);
    process.exit(1);
  }
}

export function exigirChave() {
  exigir(CHAVE.startsWith("plat_"), "defina PLAT_CHAVE com uma chave de API do plat (plat_...)");
}
