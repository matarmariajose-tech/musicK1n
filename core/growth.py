"""K1N: local experiment ledger and evidence-based next actions."""
import argparse, csv, json, sqlite3, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, platform TEXT, track TEXT, start REAL, end REAL, hook TEXT, destination TEXT, status TEXT DEFAULT "draft", views INTEGER DEFAULT 0, engaged INTEGER DEFAULT 0, subscribers INTEGER DEFAULT 0)')
    return db

def candidates(db, catalog):
    count = 0
    for track in catalog['tracks']:
        for segment in track.get('segments', []):
            if not 0 <= segment['start'] < segment['end'] <= track['duration_seconds']:
                raise ValueError('Segmento fuera de los límites del audio')
            for variant, hook in enumerate(['Fragmento musical directo', 'Letra sobre el fragmento', 'Historia real detrás de la canción']):
                eid = f"{track['id']}-{segment['start']}-{variant}"
                count += db.execute('INSERT OR IGNORE INTO experiments (id,platform,track,start,end,hook,destination) VALUES (?,?,?,?,?,?,?)', (eid,'youtube-shorts',track['id'],segment['start'],segment['end'],hook,catalog['youtube_album'])).rowcount
    db.commit()
    return {'created': count, 'note': 'Propuestas; no se publicaron. Las historias y letras deben provenir del artista.'}

def import_metrics(db, path):
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    with db:
        for row in rows:
            values = [int(row[k]) for k in ('views','engaged','subscribers')]
            if min(values) < 0 or values[1] > values[0]:
                raise ValueError('Métricas inválidas')
            if not db.execute('UPDATE experiments SET views=?,engaged=?,subscribers=?,status="measured" WHERE id=?', (*values,row['id'])).rowcount:
                raise ValueError(f"Experimento desconocido: {row['id']}")
    return {'imported':len(rows)}

def evaluate(db):
    rows = [dict(r) for r in db.execute('SELECT * FROM experiments')]
    for row in rows:
        n, k = row['views'], row['engaged']
        # Wilson lower bound avoids promoting tiny samples with perfect ratios.
        if n:
            p, z = k/n, 1.96
            row['engagement_lower_bound'] = (p+z*z/(2*n)-z*((p*(1-p)+z*z/(4*n))/n)**.5)/(1+z*z/n)
        else:
            row['engagement_lower_bound'] = 0
        row['decision'] = 'seguir midiendo' if n < 100 else 'comparar con variantes de la misma plataforma y período'
    rows.sort(key=lambda r:r['engagement_lower_bound'], reverse=True)
    return {'experiments':rows, 'next_action': 'Agregar audios y segmentos reales' if not rows else 'Publicar borradores revisados y registrar resultados', 'paid_budget_authorized':0, 'spotify_note':'Las escuchas de Spotify se importan por separado; no se atribuyen a Shorts sin evidencia.'}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default=os.environ.get('K1N_DB_PATH', str(ROOT/'growth.sqlite')))
    sub = p.add_subparsers(dest='cmd',required=True)
    seed = sub.add_parser('plan'); seed.add_argument('--catalog',default=str(ROOT/'catalog.json'))
    metrics = sub.add_parser('import-metrics'); metrics.add_argument('csv')
    sub.add_parser('evaluate')
    args=p.parse_args(); db=connect(args.db)
    if args.cmd=='plan': result=candidates(db,json.loads(Path(args.catalog).read_text()))
    elif args.cmd=='import-metrics': result=import_metrics(db,args.csv)
    else: result=evaluate(db)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
