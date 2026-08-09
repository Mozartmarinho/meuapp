# Dietas do cadastro legado (foto) — nome, categoria, ativo
DIETAS_FOTO_SEED = [
    ('BRANDA COM SAL', 'basica', True),
    ('BRANDA CONST COM SAL', 'basica', True),
    ('BRANDA CONST SEM SAL', 'basica', True),
    ('BRANDA DB CONST', 'basica', True),
    ('BRANDA DB CONST SEM SAL', 'basica', True),
    ('BRANDA DB LAX', 'basica', True),
    ('BRANDA DB LAX SEM SAL', 'basica', True),
    ('BRANDA HIOL COM SAL', 'basica', True),
    ('BRANDA HIOL SEM SAL', 'basica', True),
    ('BRANDA LAX COM SAL', 'basica', True),
    ('BRANDA LAX SEM SAL', 'basica', True),
    ('BRANDA SEM SAL', 'basica', True),
    ('LIQUIDA COM SAL', 'basica', True),
    ('LIQUIDA CONST COM SAL', 'basica', True),
    ('LIQUIDA CONST SEM SAL', 'basica', True),
    ('LIQUIDA ESPESSADA', 'basica', True),
    ('LIQUIDA ESPESSADA DB', 'basica', True),
    ('LIQUIDA RESTRITA SEM SAL', 'basica', True),
    ('LIQUIDA SEM SAL', 'basica', True),
    ('PASTOSA COM SAL', 'basica', True),
    ('PASTOSA DB CONST COM SAL', 'basica', True),
    ('PASTOSA DB CONST SEM SAL', 'basica', True),
    ('PASTOSA DB LAX COM SAL', 'basica', True),
    ('PASTOSA DB LAX SEM SAL', 'basica', True),
    ('PASTOSA HIOL COM SAL', 'basica', False),
    ('PASTOSA HIOL SEM SAL', 'basica', False),
    ('PASTOSA SEM SAL', 'basica', True),
    ('SELETIVA', 'basica', True),
]

# Complementares (enterais / fórmulas / suplementos)
DIETAS_EXTRA_SEED = [
    ('NORMOCALORICA E NORMOPROTEICA - NUTRI ENTERAL 1L', 'enteral', True),
    ('NORMOCALORICA E HIPERPROTEICA - NUTRI ENTERAL 1L', 'enteral', True),
    ('HIPERCALORICA 1.5 E HIPERPROTEICA - NUTRI ENTERAL 1L', 'enteral', True),
    ('FORMULA INFANTIL HIPOALERGENICA 1:25 - NAN HA', 'formula', True),
    ('FORMULA INFANTIL A BASE DE SOJA 1:30 - NAN SOY', 'formula', True),
    ('FORTIDRINK BAUNILHA 200 ML', 'suplemento', True),
]

DIETAS_SEED = DIETAS_FOTO_SEED + DIETAS_EXTRA_SEED
