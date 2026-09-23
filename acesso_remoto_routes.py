"""Páginas e API do Acesso remoto São Geraldo."""
from pathlib import Path

from flask import jsonify, redirect, render_template, request, send_file, session, url_for

from acesso_remoto import (
    AcessoRemotoSessao,
    conectar,
    definir_senha,
    encerrar_sessao,
    enfileirar_comando,
    equipamento_por_token,
    formatar_numero,
    guardar_tela,
    listar_equipamentos,
    pulso,
    registrar_equipamento,
    tocar_viewer,
)

_RAIZ = Path(__file__).resolve().parent
_DOWNLOADS = _RAIZ / 'static' / 'downloads' / 'acesso_remoto'


def _exe_publicada():
    if not _DOWNLOADS.is_dir():
        return None
    versionados = sorted(_DOWNLOADS.glob('AcessoRemotoSaoGeraldo-*.exe'))
    if versionados:
        return versionados[-1]
    plain = _DOWNLOADS / 'AcessoRemotoSaoGeraldo.exe'
    return plain if plain.is_file() else None


def _exigir_login_json():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'message': 'Faça login para continuar.'}), 401
    return None


def _token_agente():
    return (request.headers.get('X-Agente-Token') or '').strip()


def _sessao_ou_404(sessao_id):
    sessao = AcessoRemotoSessao.query.get(sessao_id)
    if not sessao or not sessao.ativa:
        return None
    return sessao


def registrar_rotas_acesso_remoto(main, menu_map):
    @main.route('/acesso-remoto')
    def acesso_remoto_pagina():
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        exe = _exe_publicada()
        return render_template(
            'acesso_remoto.html',
            equipamentos=listar_equipamentos(),
            exe_disponivel=exe is not None,
            exe_nome=exe.name if exe else 'AcessoRemotoSaoGeraldo.exe',
            endereco=(request.host_url or '').rstrip('/'),
        )

    @main.route('/acesso-remoto/baixar')
    def acesso_remoto_baixar():
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        exe = _exe_publicada()
        if not exe:
            return (
                'O instalador ainda não foi gerado. Rode acesso_remoto_agente/build_exe.bat.',
                404,
                {'Content-Type': 'text/plain; charset=utf-8'},
            )
        return send_file(
            exe,
            as_attachment=True,
            download_name=exe.name,
            mimetype='application/vnd.microsoft.portable-executable',
            max_age=0,
        )

    @main.route('/api/acesso-remoto/equipamentos')
    def api_acesso_remoto_equipamentos():
        bloqueio = _exigir_login_json()
        if bloqueio:
            return bloqueio
        return jsonify({'ok': True, 'equipamentos': listar_equipamentos()})

    @main.route('/acesso-remoto/conectar', methods=['POST'])
    def acesso_remoto_conectar():
        bloqueio = _exigir_login_json()
        if bloqueio:
            return bloqueio
        data = request.get_json(silent=True) or request.form
        try:
            sessao = conectar(data.get('numero'), data.get('senha'), session.get('user_id'))
        except ValueError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 400
        return jsonify({
            'ok': True,
            'sessao_id': sessao.id,
            'url': url_for('main.acesso_remoto_sessao', sessao_id=sessao.id),
            'numero_formatado': formatar_numero(sessao.equipamento.numero),
            'nome': sessao.equipamento.nome,
        })

    @main.route('/acesso-remoto/sessao/<int:sessao_id>')
    def acesso_remoto_sessao(sessao_id):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        sessao = _sessao_ou_404(sessao_id)
        if not sessao:
            return redirect(url_for('main.acesso_remoto_pagina'))
        return render_template(
            'acesso_remoto_sessao.html',
            sessao=sessao,
            numero_formatado=formatar_numero(sessao.equipamento.numero),
        )

    @main.route('/acesso-remoto/sessao/<int:sessao_id>/tela')
    def acesso_remoto_tela(sessao_id):
        bloqueio = _exigir_login_json()
        if bloqueio:
            return bloqueio
        sessao = _sessao_ou_404(sessao_id)
        if not sessao:
            return jsonify({'ok': False, 'message': 'Sessão encerrada.'}), 404
        frame = tocar_viewer(sessao)
        if not frame:
            return '', 204
        return frame, 200, {'Content-Type': 'image/jpeg', 'Cache-Control': 'no-store'}

    @main.route('/acesso-remoto/sessao/<int:sessao_id>/comando', methods=['POST'])
    def acesso_remoto_comando(sessao_id):
        bloqueio = _exigir_login_json()
        if bloqueio:
            return bloqueio
        sessao = _sessao_ou_404(sessao_id)
        if not sessao:
            return jsonify({'ok': False, 'message': 'Sessão encerrada.'}), 404
        try:
            enfileirar_comando(sessao, request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 400
        return jsonify({'ok': True})

    @main.route('/acesso-remoto/sessao/<int:sessao_id>/encerrar', methods=['POST'])
    def acesso_remoto_encerrar(sessao_id):
        bloqueio = _exigir_login_json()
        if bloqueio:
            return bloqueio
        sessao = AcessoRemotoSessao.query.get(sessao_id)
        if sessao:
            encerrar_sessao(sessao)
        return jsonify({'ok': True})

    @main.route('/api/acesso-remoto/agente/registrar', methods=['POST'])
    def api_acesso_remoto_registrar():
        data = request.get_json(silent=True) or {}
        row, token = registrar_equipamento(data.get('nome'), _token_agente() or data.get('token'))
        return jsonify({
            'ok': True,
            'token': token,
            'numero': row.numero,
            'numero_formatado': formatar_numero(row.numero),
            'senha_definida': bool(row.senha_hash),
        })

    @main.route('/api/acesso-remoto/agente/senha', methods=['POST'])
    def api_acesso_remoto_senha():
        data = request.get_json(silent=True) or {}
        try:
            row = definir_senha(_token_agente(), data.get('senha'))
        except PermissionError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 401
        except ValueError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 400
        return jsonify({
            'ok': True,
            'numero_formatado': formatar_numero(row.numero),
        })

    @main.route('/api/acesso-remoto/agente/pulso', methods=['POST'])
    def api_acesso_remoto_pulso():
        try:
            return jsonify(pulso(_token_agente()))
        except PermissionError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 401

    @main.route('/api/acesso-remoto/agente/tela', methods=['POST'])
    def api_acesso_remoto_agente_tela():
        blob = request.get_data(cache=False) or b''
        try:
            comandos = guardar_tela(_token_agente(), request.args.get('sessao_id'), blob)
        except PermissionError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 401
        except ValueError as exc:
            return jsonify({'ok': False, 'message': str(exc)}), 400
        if comandos is False:
            return jsonify({'ok': False, 'sessao_id': None, 'comandos': []})
        row = equipamento_por_token(_token_agente())
        return jsonify({
            'ok': True,
            'sessao_id': request.args.get('sessao_id', type=int),
            'comandos': comandos,
            'numero_formatado': formatar_numero(row.numero) if row else '',
        })

    menu_map['main.acesso_remoto_pagina'] = 'acesso_remoto'
    menu_map['main.acesso_remoto_baixar'] = 'acesso_remoto'
    menu_map['main.api_acesso_remoto_equipamentos'] = 'acesso_remoto'
    menu_map['main.acesso_remoto_conectar'] = 'acesso_remoto'
    menu_map['main.acesso_remoto_sessao'] = 'acesso_remoto'
    menu_map['main.acesso_remoto_tela'] = 'acesso_remoto'
    menu_map['main.acesso_remoto_comando'] = 'acesso_remoto'
    menu_map['main.acesso_remoto_encerrar'] = 'acesso_remoto'
