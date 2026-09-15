import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    """Conexión a PostgreSQL con cursor tipo diccionario."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id              SERIAL PRIMARY KEY,
        username        TEXT UNIQUE NOT NULL,
        password_hash   TEXT NOT NULL,
        rol             TEXT NOT NULL DEFAULT 'operador',
        creado_en       TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
    );

    CREATE TABLE IF NOT EXISTS proveedores (
        codigo      TEXT PRIMARY KEY,
        nombre      TEXT NOT NULL,
        direccion   TEXT,
        contacto    TEXT,
        email       TEXT,
        telefono    TEXT
    );

    CREATE TABLE IF NOT EXISTS piezas (
        numero_pieza    TEXT PRIMARY KEY,
        descripcion     TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pn_proveedores (
        id                SERIAL PRIMARY KEY,
        numero_pieza      TEXT NOT NULL,
        proveedor_codigo  TEXT,
        proveedor_nombre  TEXT NOT NULL,
        UNIQUE(numero_pieza, proveedor_nombre)
    );

    CREATE TABLE IF NOT EXISTS riai (
        id              SERIAL PRIMARY KEY,
        fecha           TEXT,
        idioma          TEXT DEFAULT 'es',
        unidad_long     TEXT DEFAULT 'mm',
        unidad_peso     TEXT DEFAULT 'kg',

        proveedor_codigo    TEXT,
        proveedor_nombre    TEXT,
        proveedor_direccion TEXT,
        proveedor_contacto  TEXT,
        proveedor_email     TEXT,
        proveedor_telefono  TEXT,

        numero_pieza    TEXT,
        descripcion     TEXT,
        largo           REAL,
        ancho           REAL,
        alto            REAL,
        peso            REAL,
        moq             INTEGER,
        proyecto        TEXT,

        emb_identico    INTEGER DEFAULT 0,
        colocacion      TEXT DEFAULT 'pallet',

        p1_tipo         TEXT,
        p1_retornable   TEXT,
        p1_material     TEXT,
        p1_descripcion  TEXT,
        p1_largo        REAL,
        p1_ancho        REAL,
        p1_alto         REAL,
        p1_peso_emb     REAL,
        p1_capacidad    INTEGER,
        p1_peso_bruto   REAL,
        p1_cajas_capa   INTEGER,
        p1_capas        INTEGER,

        p2_tipo         TEXT,
        p2_retornable   TEXT,
        p2_material     TEXT,
        p2_descripcion  TEXT,
        p2_largo        REAL,
        p2_ancho        REAL,
        p2_alto         REAL,
        p2_peso_emb     REAL,
        p2_capacidad    INTEGER,
        p2_peso_bruto   REAL,

        accesorios      TEXT,

        img_caja        TEXT,
        img_abierta     TEXT,
        img_embalada    TEXT,
        img_paletizado  TEXT,

        ap_elaborado_nombre TEXT,
        ap_elaborado_fecha  TEXT,
        ap_revisado_nombre  TEXT,
        ap_revisado_fecha   TEXT,
        ap_aprobado_nombre  TEXT,
        ap_aprobado_fecha   TEXT,

        estado          TEXT DEFAULT 'Borrador',
        creado_en       TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
        actualizado_en  TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
    );

    CREATE TABLE IF NOT EXISTS control (
        id              SERIAL PRIMARY KEY,
        fecha           TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD')),
        proveedor_nombre TEXT,
        proveedor_codigo TEXT,

        emb_identico    INTEGER DEFAULT 1,

        emb_tipo        TEXT,
        emb_tipo_otro   TEXT,
        emb_largo       REAL,
        emb_ancho       REAL,
        emb_alto        REAL,
        img_cerrada     TEXT,
        img_abierta     TEXT,
        img_etiqueta    TEXT,
        saturacion      INTEGER,

        notas           TEXT,
        creado_en       TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
    );

    CREATE TABLE IF NOT EXISTS control_lineas (
        id              SERIAL PRIMARY KEY,
        control_id      INTEGER NOT NULL REFERENCES control(id) ON DELETE CASCADE,
        numero_pieza    TEXT NOT NULL,
        cantidad        INTEGER,
        tipo            TEXT,
        largo           REAL,
        ancho           REAL,
        alto            REAL,
        img_foto1       TEXT,
        img_foto2       TEXT,
        saturacion      INTEGER,
        orden           INTEGER DEFAULT 0
    );
    """)
    conn.commit()

    c.execute("SELECT COUNT(*) as cnt FROM proveedores")
    if c.fetchone()["cnt"] == 0:
        c.executemany(
            "INSERT INTO proveedores VALUES (%s,%s,%s,%s,%s,%s)",
            [
                ("AGN001","Agromaq S.A.","Av. Industria 1200, Córdoba","Juan Pérez","jperez@agromaq.com.ar","+54 351 400-1234"),
                ("MET002","Metales del Centro S.R.L.","Ruta 9 Km 12, Villa María","Laura Gómez","lgomez@metalesc.com.ar","+54 353 422-5678"),
                ("PLT003","Plásticos Tecno S.A.","Parque Industrial Oeste, Córdoba","Mario Silva","msilva@plasticoste.com.ar","+54 351 480-9012"),
                ("HID004","Hidráulica Córdoba S.A.","Av. Fuerza Aérea 3500, Córdoba","Ana Torres","atorres@hidraulicacba.com.ar","+54 351 460-3456"),
            ]
        )
        conn.commit()

    c.execute("SELECT COUNT(*) as cnt FROM piezas")
    if c.fetchone()["cnt"] == 0:
        c.executemany(
            "INSERT INTO piezas VALUES (%s,%s)",
            [
                ("84567890","BRACKET SOPORTE MOTOR"),
                ("47891234","TUBO HIDRAULICO RETORNO"),
                ("63210987","PALANCA CAMBIOS COMPLETA"),
                ("29876543","SELLO GOMA 45MM"),
                ("11234567","FILTRO ACEITE TRANSMISION"),
            ]
        )
        conn.commit()

    # Migraciones: agregar columnas nuevas a tablas ya existentes, sin perder datos
    def add_column_if_missing(table, column, coltype):
        c.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name=%s AND column_name=%s
        """, (table, column))
        if not c.fetchone():
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            conn.commit()

    add_column_if_missing("control", "img_cerrada", "TEXT")
    add_column_if_missing("control", "img_abierta", "TEXT")
    add_column_if_missing("control", "img_etiqueta", "TEXT")
    add_column_if_missing("control_lineas", "img_foto1", "TEXT")
    add_column_if_missing("control_lineas", "img_foto2", "TEXT")

    c.execute("CREATE INDEX IF NOT EXISTS idx_pn_proveedores_pn ON pn_proveedores(numero_pieza)")
    conn.commit()

    c.close()
    conn.close()
