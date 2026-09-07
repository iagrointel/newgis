/* plat · mapa — escritor de PDF mínimo (item L2-01-mapa-web).

   Por que escrever em vez de trazer biblioteca: o PDF que a impressão do mapa precisa é UMA página com
   UMA imagem e algumas linhas de texto. O formato para esse caso cabe em 100 linhas — um objeto de
   imagem com `/Filter /DCTDecode` (que é exatamente um JPEG colado dentro do arquivo, sem
   recodificar), um fluxo de conteúdo e a tabela xref. Trazer uma biblioteca de PDF completa para isso
   custaria centenas de kB no navegador, mais uma linha em VERSOES.txt com sha256 e mais uma dependência
   de terceiro para auditar. A prova de que o arquivo é válido não é a nossa palavra: o e2e do item
   converte o PDF gerado com `pdftoppm` (Poppler) e confere que a página tem desenho.

   Limites declarados: uma página, uma imagem JPEG, fontes só as 14 padrão do PDF (Helvetica), sem
   transparência, sem anotação, sem metadado XMP. Texto vai em WinAnsi; caracteres fora dele viram '?'
   (não há incorporação de fonte). */

const CABECALHO = '%PDF-1.4\n';

function bytesDeTexto(texto) {
  const saida = new Uint8Array(texto.length);
  for (let i = 0; i < texto.length; i += 1) saida[i] = texto.charCodeAt(i) & 0xff;
  return saida;
}

export function escaparTexto(s) {
  /* WinAnsi aproximado: acento comum é rebaixado, o resto vira '?'; ( ) \ são escapados */
  const semAcento = String(s).normalize('NFD').replace(/[̀-ͯ]/g, '');
  return semAcento.replace(/[^\x20-\x7e]/g, '?').replace(/([()\\])/g, '\\$1');
}

/* páginaPdf({jpeg, largura, altura, textos, tamanhoPagina}) -> Blob
   - jpeg: Uint8Array com o JPEG inteiro (canvas.toBlob('image/jpeg') -> arrayBuffer)
   - largura/altura: pixels da imagem
   - textos: [{texto, x, y, tamanho}] em pontos, origem no canto inferior esquerdo
   - tamanhoPagina: [largura, altura] em pontos (1 pt = 1/72 pol) */
export function paginaPdf({ jpeg, largura, altura, textos = [], tamanhoPagina, margemInferior = 46 }) {
  const [pw, ph] = tamanhoPagina;
  const areaAltura = ph - margemInferior;
  const escala = Math.min(pw / largura, areaAltura / altura);
  const iw = largura * escala;
  const ih = altura * escala;
  const ix = (pw - iw) / 2;
  const iy = margemInferior + (areaAltura - ih) / 2;

  const conteudo = [
    'q',
    `${iw.toFixed(2)} 0 0 ${ih.toFixed(2)} ${ix.toFixed(2)} ${iy.toFixed(2)} cm`,
    '/Im0 Do',
    'Q',
    'BT',
    ...textos.flatMap((t) => [
      `/F1 ${t.tamanho || 9} Tf`,
      `1 0 0 1 ${(t.x || 24).toFixed(2)} ${(t.y || 20).toFixed(2)} Tm`,
      `(${escaparTexto(t.texto)}) Tj`,
    ]),
    'ET',
  ].join('\n');

  const objetos = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw} ${ph}] /Resources << /XObject << /Im0 4 0 R >> `
      + '/Font << /F1 6 0 R >> >> /Contents 5 0 R >>',
    null, // 4: imagem, montado abaixo (tem corpo binário)
    null, // 5: conteúdo
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
  ];

  const pedacos = [];
  const deslocamentos = [];
  let posicao = 0;
  const push = (u8) => { pedacos.push(u8); posicao += u8.length; };
  push(bytesDeTexto(CABECALHO));

  for (let i = 0; i < objetos.length; i += 1) {
    deslocamentos[i] = posicao;
    const n = i + 1;
    if (n === 4) {
      push(bytesDeTexto(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${largura} /Height ${altura} `
        + `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`));
      push(jpeg);
      push(bytesDeTexto('\nendstream\nendobj\n'));
    } else if (n === 5) {
      const corpo = bytesDeTexto(conteudo);
      push(bytesDeTexto(`5 0 obj\n<< /Length ${corpo.length} >>\nstream\n`));
      push(corpo);
      push(bytesDeTexto('\nendstream\nendobj\n'));
    } else {
      push(bytesDeTexto(`${n} 0 obj\n${objetos[i]}\nendobj\n`));
    }
  }

  const inicioXref = posicao;
  let xref = `xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n`;
  for (let i = 0; i < objetos.length; i += 1) {
    xref += `${String(deslocamentos[i]).padStart(10, '0')} 00000 n \n`;
  }
  xref += `trailer\n<< /Size ${objetos.length + 1} /Root 1 0 R >>\nstartxref\n${inicioXref}\n%%EOF\n`;
  push(bytesDeTexto(xref));

  return new Blob(pedacos, { type: 'application/pdf' });
}

export const A4_PAISAGEM = [841.89, 595.28];
export const A4_RETRATO = [595.28, 841.89];
