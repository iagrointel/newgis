# Fonte e licença dos dados de teste raster (L1-01-f)

Todos os arquivos deste diretório são SINTÉTICOS, gerados na casa por `gerar.py` (comando:
`venv/bin/python tests/dados/raster/gerar.py`), determinísticos, sem dado de terceiro e sem
restrição de licença: o conteúdo é uma grade aritmética (`(i + deslocamento) % 251` sobre uma
malha de 96 × 72 células de 10 m em SIRGAS 2000 / UTM 23S, EPSG:31983). Os binários estão
commitados para os testes rodarem sem o GDAL de linha de comando; `gerar.py` é o registro de
como cada um foi produzido e pode reconstruí-los byte a byte (com a ressalva de que JPEG 2000,
Erdas IMG, ENVI e GRIB passam por bibliotecas cuja saída pode variar entre versões — o que os
testes consomem é o comportamento do validador, não o hash destes arquivos).

Cada arquivo tem menos de 1 MB (o diretório inteiro passa de 300 KB), dentro do limite de 20 MB
por entrada do portão do item.

| arquivo | formato | como foi gerado |
|---|---|---|
| `geotiff_sintetico.tif` | GeoTIFF | rasterio, driver GTiff, 1 banda uint8 |
| `geotiff_rgb.tif` | GeoTIFF | rasterio, 3 bandas uint8 (base do RGB e do KMZ) |
| `geotiff_16bits.tif` | GeoTIFF | rasterio, 1 banda uint16 (valores até 50.000) |
| `bigtiff_sintetico.tif` | BigTIFF | rasterio com `BIGTIFF=YES` (assinatura `II+\0`) |
| `jpeg2000_sintetico.jp2` | JPEG 2000 | `gdal_translate -of JP2OpenJPEG -co REVERSIBLE=YES` |
| `jpeg2000_12bits.jp2` | JPEG 2000 > 8 bits | `gdal_translate -of JP2OpenJPEG -ot UInt16 -scale 0 255 0 4095` (refutação) |
| `erdas_sintetico.img` | Erdas Imagine (HFA) | `gdal_translate -of HFA` |
| `erdas_piramides_externas.zip` | IMG + pirâmide externa | `gdaladdo -clean` + `gdaladdo --config HFA_USE_RRD YES … 2 4`, zipado com o `.rrd` (refutação) |
| `envi_par.zip` | ENVI (.dat + .hdr) | `gdal_translate -of ENVI`, zipado com o cabeçalho irmão |
| `ascii_grid_sintetico.asc` | ASCII Grid | `gdal_translate -of AAIGrid`, sem o `.prj` irmão (sem CRS declarado) |
| `ascii_grid_virgula.asc` | ASCII Grid inválido | escrito à mão com vírgula decimal (refutação: recusa) |
| `png_world.zip` | PNG + world file | `gdal_translate -of PNG -b 1` + `.pgw` escrito à mão (convenção ESRI) |
| `jpeg_world.zip` | JPEG + world file | `gdal_translate -of JPEG -b 1` + `.jgw` escrito à mão |
| `geopdf_sintetico.pdf` | GeoPDF | `gdal_translate -of PDF` (recusa medida: sem backend de leitura) |
| `netcdf_sintetico.nc` | netCDF (NETCDF4_CLASSIC) | pacote netCDF4 com convenções CF completas (grid_mapping + GeoTransform + spatial_ref) |
| `netcdf_eixo_tempo.nc` | netCDF com eixo de tempo | netCDF4, dimensão `time` de 4 passos (refutação: recusa com a mensagem do L1-19) |
| `grib_sintetico.grb2` | GRIB2 | `gdal_translate -of GRIB` (1 mensagem) |
| `loja_zarr.zarr` | Zarr (armazém zipado) | `gdal_translate -of Zarr` num diretório, zipado preservando a estrutura interna (`armazem.zarr/…`) |
| `hdf5_sem_georref.h5` | HDF5 sem georreferência | pacote h5py, dataset `banda1` sem convenção de CRS (refutação: recusa medida) |
| `mosaico_4cenas.zip` | zip de 4 cenas contíguas | 4 GeoTIFF 2×2 contíguos (mesmo CRS/dims/dtype/res), zipados (cláusula do mosaico) |
| `mosaico_crs_diferente.zip` | zip com CRS conflitantes | cena 1 em EPSG:31983 + cena em EPSG:4326 (refutação: recusa dizendo quais) |
| `superoverlay.kmz` | KMZ superoverlay | `doc.kml` com `GroundOverlay` + PNG embutido, zipado |
| `proprietario.ecw` | recusa ECW | cópia de bytes de `geotiff_sintetico.tif` com extensão `.ecw` — prova que a recusa é pela tabela de formatos |
| `proprietario.sid` | recusa MrSID | cópia de bytes de `geotiff_sintetico.tif` com extensão `.sid` (mesma prova) |
