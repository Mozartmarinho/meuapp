"""PDF e Excel do Controle de Pesagem, sem biblioteca extra."""
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape


def _pdf_text(value):
    raw = str(value if value is not None else '')
    encoded = raw.encode('latin-1', 'replace').decode('latin-1')
    return encoded.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _text_width(text, size):
    # Helvetica: dígitos ~0.56 em; letras um pouco menos. Serve para alinhar coluna.
    return len(str(text or '')) * size * 0.52


def _clip(text, width, size):
    text = str(text if text is not None else '')
    if width <= 8:
        return ''
    while text and _text_width(text, size) > width - 4:
        text = text[:-1]
    return text


def _pdf_document(streams, page_w, page_h):
    n = len(streams)
    font_id = 3
    page_ids = [4 + i for i in range(n)]
    content_ids = [4 + n + i for i in range(n)]
    total = 3 + 2 * n
    bodies = [None] * (total + 1)
    bodies[1] = b'<< /Type /Catalog /Pages 2 0 R >>'
    kids = ' '.join('%d 0 R' % pid for pid in page_ids)
    bodies[2] = ('<< /Type /Pages /Count %d /Kids [%s] >>' % (n, kids)).encode('ascii')
    bodies[3] = (
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>'
    )
    for i, stream in enumerate(streams):
        bodies[content_ids[i]] = (
            b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream'
        )
        bodies[page_ids[i]] = (
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] '
            '/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>'
            % (page_w, page_h, content_ids[i], font_id)
        ).encode('ascii')

    out = BytesIO()
    out.write(b'%PDF-1.4\n')
    offsets = [0]
    for num in range(1, total + 1):
        offsets.append(out.tell())
        out.write(b'%d 0 obj\n' % num)
        out.write(bodies[num])
        out.write(b'\nendobj\n')
    xref = out.tell()
    out.write(b'xref\n0 %d\n' % (total + 1))
    out.write(b'0000000000 65535 f \n')
    for off in offsets[1:]:
        out.write(b'%010d 00000 n \n' % off)
    out.write(b'trailer\n<< /Size %d /Root 1 0 R >>\n' % (total + 1))
    out.write(b'startxref\n%d\n%%%%EOF\n' % xref)
    return out.getvalue()


class _Pagina:
    def __init__(self):
        self.ops = []

    def retangulo(self, x, y, w, h, r, g, b):
        self.ops.append(
            '%.3f %.3f %.3f rg %.1f %.1f %.1f %.1f re f' % (r, g, b, x, y, w, h)
        )

    def texto(self, x, y, tamanho, valor, align='L', largura=None):
        bruto = _clip(valor, largura or 2000, tamanho)
        if align == 'R' and largura:
            x = x + largura - _text_width(bruto, tamanho) - 3
        self.ops.append(
            'BT /F1 %d Tf 1 0 0 1 %.1f %.1f Tm (' % (tamanho, x, y)
            + _pdf_text(bruto)
            + ') Tj ET'
        )

    def bytes(self):
        return ('\n'.join(self.ops) + '\n').encode('latin-1', 'replace')


def gerar_pdf(titulo, metas, colunas, linhas, rodape='', paisagem=False):
    """Tabela simples. colunas: (titulo, peso, 'L'|'R')."""
    page_w, page_h = (842, 595) if paisagem else (595, 842)
    margem = 36
    util = page_w - margem * 2
    pesos = [max(int(c[1]), 1) for c in colunas]
    soma = float(sum(pesos)) or 1.0
    larguras = [util * p / soma for p in pesos]
    tamanho = 8
    altura = 14
    paginas = []

    def nova():
        pag = _Pagina()
        paginas.append(pag)
        return pag

    def cabecalho(pag, y):
        y_base = y - 11
        pag.retangulo(margem, y - altura, util, altura, 0.91, 0.93, 0.96)
        x = margem
        for col, larg in zip(colunas, larguras):
            pag.texto(x + 3, y_base, tamanho, col[0], col[2] if len(col) > 2 else 'L', larg - 4)
            x += larg
        return y - altura

    pag = nova()
    y = page_h - margem
    pag.texto(margem, y - 4, 14, titulo)
    y -= 20
    for meta in metas or []:
        pag.texto(margem, y - 2, 9, meta)
        y -= 12
    y -= 6
    y = cabecalho(pag, y)

    for linha in linhas or []:
        if y - altura < 40:
            pag = nova()
            y = page_h - margem
            y = cabecalho(pag, y)
        y_base = y - 11
        if y_base % 2 == 0:
            pag.retangulo(margem, y - altura, util, altura, 0.97, 0.98, 0.99)
        x = margem
        for col, larg, valor in zip(colunas, larguras, linha):
            align = col[2] if len(col) > 2 else 'L'
            pag.texto(x + 3, y_base, tamanho, valor, align, larg - 4)
            x += larg
        y -= altura

    if not linhas:
        pag.texto(margem + 3, y - 12, tamanho, 'Nenhum registro neste filtro.')
        y -= 18

    if rodape:
        pag.texto(margem, 24, 8, rodape)

    if not paginas:
        paginas.append(_Pagina())
    return _pdf_document([p.bytes() for p in paginas], page_w, page_h)


def _coluna_xlsx(n):
    letras = ''
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _celula_xlsx(ref, valor):
    if isinstance(valor, bool):
        valor = 'Sim' if valor else 'Não'
    if isinstance(valor, float):
        num = ('%.3f' % valor).rstrip('0').rstrip('.')
        if num in ('', '-'):
            num = '0'
        return '<c r="%s"><v>%s</v></c>' % (ref, num)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return '<c r="%s"><v>%d</v></c>' % (ref, valor)
    texto = escape(str(valor if valor is not None else ''))
    return '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, texto)


def gerar_xlsx(cabecalhos, linhas, aba='Pesagem'):
    nome = (aba or 'Pesagem')[:31]
    for ch in (':', '\\', '/', '?', '*', '[', ']'):
        nome = nome.replace(ch, ' ')
    todas = [list(cabecalhos)] + [list(row) for row in linhas]
    xml_rows = []
    for r_idx, row in enumerate(todas, start=1):
        cells = []
        for c_idx, valor in enumerate(row, start=1):
            cells.append(_celula_xlsx('%s%d' % (_coluna_xlsx(c_idx), r_idx), valor))
        xml_rows.append('<row r="%d">%s</row>' % (r_idx, ''.join(cells)))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>%s</sheetData></worksheet>' % ''.join(xml_rows)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>'
        % escape(nome)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr('[Content_Types].xml', content_types)
        zipped.writestr('_rels/.rels', rels)
        zipped.writestr('xl/workbook.xml', workbook)
        zipped.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        zipped.writestr('xl/worksheets/sheet1.xml', sheet)
    return buf.getvalue()
