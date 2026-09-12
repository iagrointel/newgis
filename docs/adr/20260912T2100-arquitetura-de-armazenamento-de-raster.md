# Arquitetura de armazenamento de raster: o que guardar e em que codec

Data: 12/09/2026 · Estado: **medido; decisão de produto pendente no item 1**

## O problema

Cobramos por terabyte guardado. Até aqui a conversa sobre "comprimir mais" mirava o codec do perfil
visual, que é o arquivo que responde ladrilho. Medindo a composição real do que guardamos, por km²
de ortofoto a 10 cm:

| o que guardamos | MB por km² | fatia do volume cobrado |
|---|---|---|
| arquivo original, sem compressão | 308,3 | **65 %** |
| perfil científico (ZSTD + preditor) | 128,4 | 27 % |
| perfil visual (JPEG q80) | 34,7 | 8 % |

O visual é 8 % do volume. **Trocar o codec dele não move a conta.** Quem manda é o original, e ele é
redundante: o perfil científico usa ZSTD com preditor, que não descarta informação, então contém
exatamente os mesmos pixels. Guardar os dois é guardar a mesma imagem duas vezes.

## A bancada

Corpo de teste: 2.000 × 2.000 px (0,04 km² a 10 cm) recortado da ortofoto de São Paulo, 12,0 MB em
PPM. Todos os candidatos recebem os MESMOS pixels. Qualidade medida contra o original por SSIM
(1,0 = idêntico) e PSNR — sem isso, "45 % menor" não quer dizer nada, porque qualquer codec fica
menor se degradar mais.

**Sem perda — o perfil de arquivo.** Os três voltaram idênticos, conferido byte a byte:

| candidato | tamanho | razão | codificar |
|---|---|---|---|
| ZSTD + preditor 2 — **o que usamos** | 2,23 MB | 5,37× | **0,2 s** |
| WebP sem perda | 1,65 MB | 7,29× | 6,4 s |
| JPEG XL sem perda, esforço 7 | **1,45 MB** | **8,26×** | 5,0 s |

**Com perda — o perfil que serve mapa:**

| candidato | tamanho | razão | SSIM | PSNR | codificar |
|---|---|---|---|---|---|
| JPEG q80 — **o que usamos** | 1,07 MB | 11,22× | 0,8850 | 30,2 dB | 1,1 s |
| WebP q80 | 0,90 MB | 13,34× | **0,9085** | 31,5 dB | 1,0 s |
| JPEG XL distância 1 | 1,19 MB | 10,10× | 0,9348 | 33,4 dB | 0,8 s |
| JPEG XL distância 2 | 0,74 MB | 16,24× | 0,9012 | 31,5 dB | 0,8 s |
| JPEG XL distância 3 | 0,54 MB | 22,31× | 0,8788 | 30,4 dB | 0,7 s |

As comparações que valem são as de qualidade igual, não as de linha por linha:

- **WebP q80 contra JPEG q80**: 16 % menor **e melhor** (SSIM 0,9085 contra 0,8850), mesmo tempo.
  Não há troca a fazer aqui: é ganho nas duas pontas.
- **JPEG XL distância 3 contra JPEG q80**: qualidade praticamente igual (SSIM 0,8788 contra 0,8850,
  PSNR 30,4 contra 30,2 dB) e **metade dos bytes**.
- **JPEG XL distância 2 contra WebP q80**: mesmo PSNR, 18 % menor.

E dois candidatos que ficam fora:

- **LERC**, o codec da própria Esri, é o pior para fotografia em três bandas: 2,46× contra 5,79× do
  ZSTD no mesmo dado. Foi desenhado para altimetria e dado científico. Se alguém sugerir, é este o
  número.
- **AVIF** não lê PPM nas ferramentas desta máquina e não foi medido. O JXL o supera na literatura
  em imagem fotográfica de alta resolução; não é prioridade.

## ⛔ Por que JPEG XL NÃO entra agora

O prêmio é real: metade dos bytes no perfil que serve, com qualidade medida igual à de hoje, e 35 %
no perfil de arquivo. O custo é que **nenhum dos dois GDAL desta pilha tem o codec**:

    gdal_translate do sistema ...... GDAL 3.8.4   sem JXL
    rasterio do venv (serve tile) .. GDAL 3.12.1  sem JXL
      rasterio: "Cannot create TIFF file due to missing codec for JXL."

A `libjxl 0.7` está instalada na máquina, mas isso não basta. Adotar JXL exige passar a manter, em
casa, **GDAL e rasterio compilados contra libjxl**, e fazer os três serviços que leem COG usarem essa
build — a API, o trabalhador e o TiTiler, que é serviço separado com ambiente próprio. Enquanto um
deles ficar sem o codec, um COG em JXL vira arquivo ilegível para quem serve o mapa.

Isso é assumir a manutenção de uma build própria do GDAL para toda a plataforma, numa máquina que
hoje mesmo teve o Postgres de cliente morto pelo OOM. Não é meio dia de trabalho e não se decide
junto com uma troca de codec.

⚡ **Achado de lado, e é um risco por si:** a conversão usa o GDAL 3.8.4 do sistema e o serviço de
ladrilho usa o GDAL 3.12.1 que vem dentro do rasterio. **São duas versões diferentes na mesma pilha**,
uma escrevendo o COG e a outra lendo. Funciona hoje e não estava declarado em lugar nenhum. Quando
divergirem em algum padrão de criação, o defeito vai aparecer como "o ladrilho saiu errado" e ninguém
vai olhar a versão do GDAL.

## A decisão

Três mudanças, todas com codec que os dois GDAL já têm, todas medidas:

| | de | para | efeito |
|---|---|---|---|
| 1 · não guardar o original | 308,3 MB/km² | 0 | −65 % do volume |
| 2 · arquivo sem pirâmide | 128,4 | 51,9 | −58 % do arquivo |
| 3 · visual em WebP q80 | 34,7 | 27,6 | −20 % e melhor qualidade |

Resultado: **471 → 85 MB por km², 5,6 vezes menos volume cobrado.** Um terabyte passa de 2.121 para
11.774 km² a 10 cm. E a conversão fica **mais rápida** que hoje, não mais lenta, porque o item 2 tira
trabalho em vez de somar.

Justificativa de cada uma:

1. O perfil científico já é cópia sem perda do original. ⛔ **Este item é decisão de produto, não de
   engenharia**: colide com a regra da casa de guardar o arquivo como ele chegou, e o sha256 do
   original deixaria de ter bytes correspondentes guardados. O caminho intermediário é guardar o
   sha256 e a proveniência sem guardar os bytes, e oferecer a cópia do original como item cobrado à
   parte.
2. A pirâmide é 58 % do perfil científico e **ninguém serve mapa a partir dele** — quem faz isso é o
   visual, que tem pirâmide própria. O científico existe para cálculo numa área específica, não para
   navegar. Sem pirâmide ele cai de 128,4 para 51,9 MB/km² sem perder um pixel.
3. Medido: menor **e** melhor. E conserta uma escolha acidental — hoje
   `cog.converter_visual` decide entre JPEG e WebP pela presença de canal alfa, porque WebP é o único
   dos dois que aceita transparência. A escolha nunca foi por qual comprime melhor, e a ortofoto de
   três bandas caiu em JPEG por causa dessa regra.

## O que NÃO fazer

- **Não trocar o arquivo para WebP sem perda.** Ganha 26 % e custa 32 vezes o tempo de escrita
  (6,4 s contra 0,2 s no corpo de teste, o que vira ~30 h contra ~1 h para os 469 GB de uma cidade).
  Se o JXL entrar algum dia, ele ganha do WebP sem perda com uma fração do tempo, e essas 30 horas
  por cidade viram desperdício.
- **Não subir o ZSTD para o nível máximo.** Ganha 4,6 % e custa 90 vezes o tempo.
- **Não esperar que compressão mova o ponto de virada comercial.** O ponto de virada contra o ArcGIS
  Online, medido em 243 km², é fixado pelo piso de cobrança de 1 TB, não pela nossa eficiência. O que
  a eficiência compra é margem e teto de degrau. Para ganhar o cliente pequeno o que muda é criar um
  degrau de entrada menor — e com 5,6 vezes de folga, um degrau de 100 GB cobriria 1.177 km².

## Como reproduzir

    /mnt/pgdata/plat-orto/bench/qualidade.py    # tamanho, tempo e SSIM/PSNR por codec
    /mnt/pgdata/plat-orto/bench/medir.py        # os codecs do GDAL, com leitura de ladrilho
    /mnt/pgdata/plat-orto/bench/qualidade.json  # números desta ADR
