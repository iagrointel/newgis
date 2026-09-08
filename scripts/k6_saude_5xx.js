// Item L7-19-segredos-e-certificados, cláusula "0 erro 5xx durante a rotação, medido pelo k6 curto".
// Martelo curto em /saude das unidades sob rotação: 1 VU em laço fechado (sem pausa), conta respostas
// com status >= 500 num Counter dedicado. A lista de URLs vem de K6_URLS (JSON) e a janela é a da
// rotação inteira — a prova (scripts/prova_segredos_l7_19.py) manda SIGINT quando a rotação termina.
// O resumo sai por handleSummary (API estável do k6) no caminho de K6_SAIDA. Erro de conexão NÃO
// conta aqui: a cláusula é sobre resposta 5xx; conexão recusada durante o restart já é medida pelo
// martelo interno do segredo_rotacionar.py.
import http from 'k6/http';
import { Counter } from 'k6/metrics';

const falhas5xx = new Counter('saude_5xx');
const urls = JSON.parse(__ENV.K6_URLS);

export default function () {
  for (const u of urls) {
    const r = http.get(u, { timeout: '1s' });
    if (r.status >= 500) {
      falhas5xx.add(1);
    }
  }
}

export function handleSummary(data) {
  return { [__ENV.K6_SAIDA]: JSON.stringify(data) };
}
