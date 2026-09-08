import json, subprocess, time, sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
def oi(path, *extra, cfg=()):
    argv = ['ogrinfo','-ro','-json','-so']
    for k,v in cfg: argv += ['--config', k, v]
    argv += list(extra) + [path]
    t=time.perf_counter(); p=subprocess.run(argv, capture_output=True, text=True, errors='replace'); dt=time.perf_counter()-t
    try: j=json.loads(p.stdout)
    except Exception: j=None
    return dt, j, p.stderr.strip()[:300], p.returncode
def resumo(nome, path, *extra, cfg=()):
    dt,j,err,rc=oi(path,*extra,cfg=cfg)
    if j is None:
        print(f"{nome}: rc={rc} {dt*1000:.0f} ms SEM JSON | {err}"); return
    print(f"{nome}: {dt*1000:.0f} ms driver={j.get('driverShortName')} camadas={len(j.get('layers',[]))}" + (f" | stderr: {err}" if err else ''))
    for L in j.get('layers',[]):
        srs = None
        for g in L.get('geometryFields',[]):
            cs = g.get('coordinateSystem') or {}
            pj = cs.get('projjson') or {}
            ident = pj.get('id') or {}
            srs = f"{ident.get('authority')}:{ident.get('code')}" if ident else (('WKT sem codigo: '+ (pj.get('name') or '')) if pj else 'AUSENTE')
        campos = [(f['name'], f['type'] + ('/'+f['subType'] if f.get('subType') and f['subType']!='None' else '')) for f in L.get('fields',[])]
        print(f"   camada={L['name']!r} n={L.get('featureCount')} geom={[g.get('type') for g in L.get('geometryFields',[])]} srs={srs} campos={campos[:9]}{'…' if len(campos)>9 else ''}")
resumo('gpkg 3 camadas','dados.gpkg')
resumo('shp zip utf8','/vsizip/municipios_shp.zip')
resumo('shp zip SEM PRJ','/vsizip/municipios_semprj.zip')
resumo('shp latin1 sem cpg','/vsizip/municipios_latin1_semcpg.zip')
resumo('shp latin1 sem cpg, ENCODING=ISO-8859-1','/vsizip/municipios_latin1_semcpg.zip','-oo','ENCODING=ISO-8859-1')
resumo('zip com 2 shapefiles','/vsizip/dois_shapefiles.zip')
resumo('kml pastas','pastas.kml'); resumo('kmz','pastas.kmz')
resumo('gml 3.2','municipios.gml'); resumo('fgb','ferrovias.fgb'); resumo('geojsonseq','heliportos.geojsonl')
resumo('xlsx','heliportos.xlsx'); resumo('gpx','heliportos.gpx'); resumo('tab zip','/vsizip/municipios_tab.zip')
resumo('geojson crs legado 31984','municipios_31984.geojson'); resumo('geojson misto','misto.geojson'); resumo('geojson gravata','gravata.geojson')
resumo('csv ; virgula decimal SEM opcoes','heliportos_pv.csv')
resumo('csv ; virgula decimal AUTODETECT','heliportos_pv.csv','-oo','AUTODETECT_TYPE=YES','-oo','X_POSSIBLE_NAMES=long,lon*,x','-oo','Y_POSSIBLE_NAMES=lat*,y')
resumo('csv WKT','municipios_wkt.csv','-oo','AUTODETECT_TYPE=YES')
resumo('txt tab latin1 sem geom','tabela_sem_geom.txt','-oo','AUTODETECT_TYPE=YES')
resumo('csv 300 col 0 lin','csv_300col_0lin.csv'); resumo('csv aspas','csv_aspas.csv'); resumo('csv dup','csv_dup.csv','-oo','AUTODETECT_TYPE=YES','-oo','X_POSSIBLE_NAMES=lon','-oo','Y_POSSIBLE_NAMES=lat')
resumo('dxf linhas','ferrovias.dxf')
resumo('dxf blocos INLINE (padrao)','blocos.dxf')
resumo('dxf blocos NAO inline','blocos.dxf',cfg=[('DXF_INLINE_BLOCKS','FALSE')])
resumo('dxf blocos inline + merge','blocos.dxf',cfg=[('DXF_MERGE_BLOCK_GEOMETRIES','FALSE')])
resumo('dxf binario','binario.dxf'); resumo('dxf polegada','polegada.dxf')
resumo('gpkg nome com controle','controle.gpkg')
# conteudo do DXF por modo
for cfg,label in (([],'inline'),([('DXF_INLINE_BLOCKS','FALSE')],'nao_inline')):
    argv=['ogrinfo','-ro','-json','-features']
    for k,v in cfg: argv+=['--config',k,v]
    j=json.loads(subprocess.run(argv+['blocos.dxf'],capture_output=True,text=True,errors='replace').stdout)
    for L in j['layers']:
        print(f"   dxf {label} camada={L['name']}: " + '; '.join(f"{f['properties'].get('Layer')}/{f['properties'].get('SubClasses')}/{f['properties'].get('BlockName')}:{(f.get('geometry') or {}).get('type')}" for f in L['features']))
# shp sem prj: o que o ogrinfo diz do SRS em texto
print(subprocess.run(['ogrinfo','-ro','-so','-al','/vsizip/municipios_semprj.zip'],capture_output=True,text=True,errors='replace').stdout.split('Layer SRS WKT:')[1][:60].replace('\n',' | '))
# latin1: nome do municipio lido sem e com ENCODING
for oo in ([],['-oo','ENCODING=ISO-8859-1']):
    j=json.loads(subprocess.run(['ogrinfo','-ro','-json','-features','-where','"Código IBG" LIKE \'2800308\''] + oo + ['/vsizip/municipios_latin1_semcpg.zip'],capture_output=True,text=True,errors='replace').stdout)
    print('   latin1', oo, [f['properties'] for f in j['layers'][0]['features']][:1])
# csv decimal: valor lido
j=json.loads(subprocess.run(['ogrinfo','-ro','-json','-features','-oo','AUTODETECT_TYPE=YES','-oo','X_POSSIBLE_NAMES=long','-oo','Y_POSSIBLE_NAMES=lat','heliportos_pv.csv'],capture_output=True,text=True,errors='replace').stdout)
f=j['layers'][0]['features'][0]; print('   csv pv 1a feicao:', f['properties'], f.get('geometry'))
