"""
Baixa fotos faciais dos equipamentos Control iD e associa aos colaboradores/visitantes.

Uso:
  python scripts/importar_fotos_equipamentos.py
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FOTOS_DIR = ROOT / 'static' / 'acesso_fotos'
# credenciais típicas do dump Sollus (sobrescritas pelo cadastro local se houver)
DEFAULT_DEVICES = [
    {'ip': '192.168.0.237', 'usuario': 'admin', 'senha': '000123', 'nome': 'Recepção'},
    {'ip': '192.168.0.234', 'usuario': 'admin', 'senha': 'admin', 'nome': 'Fabrica'},
    {'ip': '192.168.0.247', 'usuario': 'admin', 'senha': 'admin', 'nome': 'Escritorio'},
]


def _post_json(url: str, payload: dict | None = None, timeout: float = 12):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        ctype = (resp.headers.get('Content-Type') or '').lower()
        return ctype, body


def login(ip: str, user: str, password: str) -> str | None:
    try:
        _, body = _post_json(f'http://{ip}/login.fcgi', {'login': user, 'password': password})
        return json.loads(body.decode()).get('session')
    except Exception as exc:
        print(f'  [{ip}] login falhou: {exc}')
        return None


def list_user_ids(ip: str, session: str) -> list[str]:
    try:
        _, body = _post_json(f'http://{ip}/user_list_images.fcgi?session={session}', {})
        data = json.loads(body.decode())
        ids = data.get('user_ids') or data.get('users') or []
        out = []
        for uid in ids:
            if isinstance(uid, dict):
                uid = uid.get('user_id') or uid.get('id')
            if uid is not None:
                out.append(str(uid))
        return out
    except Exception as exc:
        print(f'  [{ip}] list_images falhou: {exc}')
        return []


def get_image(ip: str, session: str, user_id: str) -> bytes | None:
    # Control iD aceita user_id numérico ou string
    payload_variants = [
        {'user_id': int(user_id) if str(user_id).isdigit() else user_id},
        {'user_id': str(user_id)},
    ]
    for payload in payload_variants:
        try:
            ctype, body = _post_json(
                f'http://{ip}/user_get_image.fcgi?session={session}',
                payload,
                timeout=20,
            )
            if body.startswith(b'\xff\xd8') or 'image' in ctype:
                return body
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
    return None


def devices_from_db():
    from app import create_app
    from models_acesso import AcessoEquipamento
    app = create_app()
    out = []
    with app.app_context():
        for eq in AcessoEquipamento.query.filter_by(ativo=True).all():
            if not eq.ip:
                continue
            out.append({
                'ip': eq.ip,
                'usuario': eq.usuario_disp or 'admin',
                'senha': eq.senha_disp or 'admin',
                'nome': eq.nome,
            })
    return out or DEFAULT_DEVICES


def main():
    from app import create_app
    from models import db
    from models_acesso import AcessoPessoa, AcessoVisitante

    FOTOS_DIR.mkdir(parents=True, exist_ok=True)
    devices = devices_from_db()
    # merge defaults for missing passwords
    by_ip = {d['ip']: d for d in DEFAULT_DEVICES}
    for d in devices:
        if not d.get('senha') and d['ip'] in by_ip:
            d['senha'] = by_ip[d['ip']]['senha']
            d['usuario'] = d.get('usuario') or by_ip[d['ip']]['usuario']

    print('Equipamentos:', ', '.join(f"{d['nome']}({d['ip']})" for d in devices))

    # user_id -> jpeg bytes (primeira fonte que responder)
    photos: dict[str, bytes] = {}
    for dev in devices:
        ip = dev['ip']
        print(f'\n== {dev["nome"]} {ip}')
        sess = login(ip, dev['usuario'], dev['senha'] or 'admin')
        if not sess:
            # tenta senha alternativa do dump
            for alt in ('000123', 'admin'):
                if alt == (dev.get('senha') or ''):
                    continue
                sess = login(ip, dev.get('usuario') or 'admin', alt)
                if sess:
                    break
        if not sess:
            continue
        uids = list_user_ids(ip, sess)
        print(f'  {len(uids)} fotos no equipamento')
        for i, uid in enumerate(uids, 1):
            if uid in photos:
                continue
            img = get_image(ip, sess, uid)
            if img:
                photos[uid] = img
            if i % 50 == 0:
                print(f'  baixadas {len(photos)}...')
        print(f'  acumulado: {len(photos)} fotos')

    if not photos:
        print('Nenhuma foto obtida dos equipamentos.')
        sys.exit(1)

    app = create_app()
    stats = {'pessoas': 0, 'visitantes': 0, 'arquivos': 0, 'sem_cadastro': 0}
    with app.app_context():
        for uid, jpeg in photos.items():
            fname = f'{uid}.jpg'
            path = FOTOS_DIR / fname
            path.write_bytes(jpeg)
            stats['arquivos'] += 1
            web_path = f'/static/acesso_fotos/{fname}'

            pessoa = AcessoPessoa.query.filter_by(matricula=str(uid)).first()
            if pessoa:
                pessoa.foto = web_path
                stats['pessoas'] += 1
                continue
            vis = AcessoVisitante.query.filter_by(visitor_id=str(uid)).first()
            if vis:
                vis.foto = web_path
                stats['visitantes'] += 1
                continue
            # tenta data-url fallback já no cadastro inexistente — só conta
            stats['sem_cadastro'] += 1

        db.session.commit()

    print('\nConcluído:')
    for k, v in stats.items():
        print(f'  {k}: {v}')
    print(f'  pasta: {FOTOS_DIR}')


if __name__ == '__main__':
    main()
