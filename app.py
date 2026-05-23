import sqlite3
import json
import io
import os
import tempfile
import csv
from functools import wraps
from flask import Flask, render_template, request, redirect, jsonify, session, url_for, send_file, Response, has_request_context
from datetime import datetime, timedelta
from urllib.parse import urlencode
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "proyecto-gera-secret-key"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

ESTADOS_CLASE = ["programada", "realizada", "cancelada"]
ESTADOS_ASISTENCIA = ["pendiente", "presente", "ausente", "aviso", "recupera"]
MOTIVOS_CANCELACION = ["", "falto alumno", "falto profesor", "feriado", "reprogramada", "otro"]
ROLES = ["admin", "profesor", "recepcion"]
ROLE_LABELS = {
    "admin": "Administrador",
    "profesor": "Profesor",
    "recepcion": "Recepcion"
}
PERMISOS_SISTEMA = [
    ("dashboard.ver", "Dashboard", "Ver dashboard general"),
    ("dashboard.financiero", "Dashboard", "Ver indicadores financieros"),
    ("alumnos.ver", "Alumnos", "Ver alumnos y fichas"),
    ("alumnos.crear", "Alumnos", "Crear alumnos"),
    ("alumnos.editar", "Alumnos", "Editar alumnos"),
    ("alumnos.eliminar", "Alumnos", "Eliminar alumnos"),
    ("estado_cuenta.ver", "Alumnos", "Ver estado de cuenta"),
    ("estado_cuenta.exportar", "Alumnos", "Exportar estado de cuenta"),
    ("profesores.ver", "Profesores", "Ver profesores"),
    ("profesores.crear", "Profesores", "Crear profesores"),
    ("profesores.editar", "Profesores", "Editar profesores"),
    ("profesores.eliminar", "Profesores", "Eliminar profesores"),
    ("comisiones.editar", "Profesores", "Modificar comisiones"),
    ("clases.ver", "Clases", "Ver calendario"),
    ("clases.crear", "Clases", "Crear clases"),
    ("clases.editar", "Clases", "Editar/reprogramar clases"),
    ("clases.eliminar", "Clases", "Eliminar clases"),
    ("asistencia.editar", "Clases", "Cargar asistencia"),
    ("recuperos.ver", "Recuperos", "Ver recuperos"),
    ("recuperos.crear", "Recuperos", "Crear recuperos"),
    ("recuperos.editar", "Recuperos", "Editar recuperos"),
    ("caja.ver", "Caja", "Ver modulo caja"),
    ("pagos.ver", "Caja", "Ver pagos"),
    ("pagos.crear", "Caja", "Registrar cuotas y matriculas"),
    ("pagos.editar", "Caja", "Editar pagos"),
    ("pagos.exportar", "Caja", "Exportar pagos"),
    ("promociones.ver", "Caja", "Ver promociones"),
    ("promociones.crear", "Caja", "Crear promociones"),
    ("promociones.editar", "Caja", "Editar promociones"),
    ("promociones.eliminar", "Caja", "Eliminar promociones"),
    ("liquidaciones.ver", "Caja", "Ver liquidaciones"),
    ("liquidaciones.editar", "Caja", "Editar liquidaciones"),
    ("liquidaciones.pagar", "Caja", "Pagar liquidaciones"),
    ("liquidaciones.exportar", "Caja", "Exportar liquidaciones"),
    ("deudores.ver", "Caja", "Ver deudores"),
    ("ajustes.ver", "Caja", "Ver ajustes manuales"),
    ("ajustes.crear", "Caja", "Crear ajustes manuales"),
    ("ajustes.anular", "Caja", "Anular ajustes manuales"),
    ("estadisticas.ver", "Estadisticas", "Ver estadisticas completas"),
    ("estadisticas.exportar", "Estadisticas", "Exportar estadisticas"),
    ("usuarios.ver", "Usuarios", "Ver usuarios"),
    ("usuarios.crear", "Usuarios", "Crear usuarios"),
    ("usuarios.editar", "Usuarios", "Editar roles y estado"),
    ("usuarios.eliminar", "Usuarios", "Eliminar usuarios"),
    ("roles.editar", "Usuarios", "Modificar permisos por rol"),
    ("auditoria.ver", "Sistema", "Ver auditoria"),
    ("backup.descargar", "Sistema", "Descargar backup"),
    ("configuracion.editar", "Sistema", "Editar configuracion general")
]
DEFAULT_ROLE_PERMISSIONS = {
    "admin": [p[0] for p in PERMISOS_SISTEMA],
    "profesor": [
        "clases.ver", "asistencia.editar", "recuperos.ver",
        "liquidaciones.ver"
    ],
    "recepcion": [
        "dashboard.ver", "alumnos.ver", "alumnos.crear", "alumnos.editar",
        "estado_cuenta.ver", "estado_cuenta.exportar",
        "clases.ver", "clases.crear", "clases.editar", "asistencia.editar",
        "recuperos.ver", "recuperos.crear", "recuperos.editar",
        "caja.ver", "pagos.ver", "pagos.crear", "pagos.editar", "pagos.exportar",
        "promociones.ver", "promociones.crear", "promociones.editar",
        "deudores.ver"
    ]
}
TIPOS_CLASE = ["individual", "duo", "grupal"]
MOTIVOS_RECUPERO = [
    "falta_alumno",
    "falta_profesor",
    "feriado",
    "enfermedad",
    "viaje",
    "lluvia_clima",
    "evento_especial",
    "corte_luz",
    "suspension_administrativa",
    "otro"
]
TIPOS_RECUPERO = ["individual", "grupal", "parcial", "completo", "clase_extra", "reprogramacion"]
ESTADOS_RECUPERO = ["pendiente", "programado", "realizado", "vencido", "cancelado", "compensado"]
TIPOS_PROMOCION = [
    "porcentaje",
    "monto_fijo",
    "matricula_bonificada",
    "primer_mes_bonificado",
    "familiar",
    "temporal",
    "cantidad_clases",
    "personalizada",
    "manual_administrativa"
]
ANALYTICS_CACHE = {}
MODALIDADES_COMISION = [
    "porcentaje_fijo",
    "monto_fijo_clase",
    "monto_fijo_alumno",
    "porcentaje_variable_alumnos",
    "porcentaje_tipo_clase",
    "escalonada",
    "temporal",
    "manual_excepcional"
]
BASES_COMISION = [
    "monto_real",
    "monto_esperado",
    "antes_promociones",
    "despues_promociones",
    "manual"
]
ESTADOS_REGLA_COMISION = ["activa", "inactiva", "vencida", "programada", "archivada"]
TIPOS_AJUSTE_MANUAL = [
    "descuento_manual",
    "bonificacion",
    "recargo",
    "correccion_deuda",
    "saldo_a_favor",
    "devolucion",
    "anulacion_cargo",
    "compensacion_clase",
    "baja_alumno",
    "redondeo",
    "bono_profesor",
    "descuento_profesor",
    "correccion_liquidacion",
    "pago_extra_profesor",
    "clase_reconocida",
    "clase_no_reconocida",
    "compensacion_cancelacion",
    "redondeo_manual",
    "compensacion_baja",
    "diferencia_absorbida_academia",
    "correccion_administrativa_negativa",
    "perdida_absorbida_academia",
    "correccion_administrativa",
    "diferencia_promocion",
    "ajuste_contable_interno"
]
CATEGORIAS_AJUSTE_MANUAL = ["alumno", "profesor", "academia", "liquidacion", "pago"]

# ---------------- DB ----------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # PROFESORES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS profesores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_apellido TEXT,
        dni TEXT,
        telefono TEXT,
        domicilio TEXT,
        email TEXT,
        edad INTEGER,
        precio_clase REAL DEFAULT 0,
        porcentaje_grupal REAL DEFAULT 40,
        color TEXT DEFAULT '#3b82f6'
    )
    """)

    # ALUMNOS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alumnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apellido_nombre TEXT,
        dni TEXT,
        fecha_nacimiento TEXT,
        dia_inscripcion TEXT,
        edad INTEGER,
        telefono TEXT,
        direccion TEXT,
        email TEXT,
        tutor_profesor_id INTEGER
    )
    """)

    # CLASES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profesor_id INTEGER,
        fecha TEXT,
        duracion REAL,
        tipo_clase_id INTEGER DEFAULT 1,
        estado TEXT DEFAULT 'programada',
        motivo_cancelacion TEXT DEFAULT '',
        recuperacion_de INTEGER
    )
    """)

    # RELACIÓN CLASE - ALUMNOS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clase_alumnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clase_id INTEGER,
        alumno_id INTEGER,
        asistencia TEXT DEFAULT 'pendiente',
        UNIQUE(clase_id, alumno_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS recuperos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clase_original_id INTEGER,
        clase_recuperacion_id INTEGER,
        alumno_id INTEGER,
        profesor_id INTEGER,
        motivo TEXT DEFAULT 'otro',
        motivo_manual TEXT DEFAULT '',
        tipo TEXT DEFAULT 'individual',
        estado TEXT DEFAULT 'pendiente',
        fecha_creacion TEXT,
        fecha_limite TEXT,
        fecha_programada TEXT,
        fecha_realizado TEXT,
        afecta_liquidacion INTEGER DEFAULT 1,
        profesor_cobra INTEGER DEFAULT 1,
        academia_absorbe INTEGER DEFAULT 1,
        genera_deuda INTEGER DEFAULT 0,
        cuenta_asistencia INTEGER DEFAULT 1,
        consume_cupo INTEGER DEFAULT 1,
        reutilizable INTEGER DEFAULT 0,
        costo_adicional REAL DEFAULT 0,
        gratuito INTEGER DEFAULT 1,
        incluido_en_cuota INTEGER DEFAULT 1,
        promocion_id INTEGER,
        observaciones TEXT DEFAULT '',
        creado_por INTEGER,
        creado_por_nombre TEXT,
        actualizado_en TEXT,
        UNIQUE(clase_original_id, alumno_id, tipo)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS recupero_notificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recupero_id INTEGER,
        tipo TEXT,
        mensaje TEXT,
        estado TEXT DEFAULT 'pendiente',
        fecha_programada TEXT,
        fecha_creacion TEXT
    )
    """)

    # USUARIOS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE,
        password_hash TEXT,
        rol TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        nombre TEXT,
        descripcion TEXT DEFAULT '',
        sistema INTEGER DEFAULT 1,
        activo INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS permisos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        modulo TEXT,
        descripcion TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS rol_permisos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rol_codigo TEXT,
        permiso_codigo TEXT,
        UNIQUE(rol_codigo, permiso_codigo)
    )
    """)

    # PAGOS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tipos_clase (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS promociones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        descripcion TEXT,
        porcentaje_descuento REAL DEFAULT 0,
        monto_descuento REAL DEFAULT 0,
        activa INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS promocion_usos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promocion_id INTEGER,
        alumno_id INTEGER,
        pago_tipo TEXT,
        pago_id INTEGER,
        monto_original REAL DEFAULT 0,
        descuento REAL DEFAULT 0,
        monto_final REAL DEFAULT 0,
        motivo TEXT,
        usuario_id INTEGER,
        usuario_nombre TEXT,
        fecha TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pagos_alumnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        anio INTEGER,
        mes INTEGER,
        monto_normal REAL DEFAULT 0,
        descuento REAL DEFAULT 0,
        monto_pagado REAL DEFAULT 0,
        promocion_id INTEGER,
        estado TEXT DEFAULT 'pendiente',
        fecha_pago TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS matriculas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        anio INTEGER,
        monto_normal REAL DEFAULT 0,
        descuento REAL DEFAULT 0,
        monto_pagado REAL DEFAULT 0,
        promocion_id INTEGER,
        estado TEXT DEFAULT 'pendiente',
        fecha_pago TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS movimientos_cuenta (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        fecha TEXT,
        concepto TEXT,
        tipo_movimiento TEXT,
        categoria TEXT,
        debe REAL DEFAULT 0,
        haber REAL DEFAULT 0,
        saldo_acumulado REAL DEFAULT 0,
        metodo_pago TEXT DEFAULT '',
        comprobante TEXT DEFAULT '',
        observacion TEXT DEFAULT '',
        estado TEXT DEFAULT 'pendiente',
        referencia_tipo TEXT DEFAULT '',
        referencia_id INTEGER,
        usuario_creador_id INTEGER,
        usuario_creador_nombre TEXT,
        fecha_creacion TEXT,
        usuario_modificador_id INTEGER,
        usuario_modificador_nombre TEXT,
        fecha_modificacion TEXT,
        motivo_modificacion TEXT DEFAULT '',
        anulado INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimientos_cuenta_alumno
        ON movimientos_cuenta (alumno_id, fecha, id)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        usuario_id INTEGER,
        usuario_nombre TEXT,
        usuario_rol TEXT,
        modulo TEXT,
        accion TEXT,
        entidad TEXT,
        entidad_id TEXT,
        detalle TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS liquidaciones_profesores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profesor_id INTEGER,
        anio INTEGER,
        mes INTEGER,
        estado TEXT DEFAULT 'pendiente',
        fecha_pago TEXT,
        metodo_pago TEXT,
        observacion TEXT,
        UNIQUE(profesor_id, anio, mes)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS liquidacion_ajustes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        liquidacion_id INTEGER,
        tipo TEXT,
        monto REAL DEFAULT 0,
        motivo TEXT,
        usuario_id INTEGER,
        usuario_nombre TEXT,
        fecha TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ajustes_manuales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo_ajuste TEXT,
        categoria TEXT,
        monto REAL DEFAULT 0,
        signo TEXT DEFAULT 'positivo',
        motivo TEXT,
        observacion TEXT DEFAULT '',
        fecha TEXT,
        usuario_creador_id INTEGER,
        usuario_creador_nombre TEXT,
        entidad_relacionada TEXT DEFAULT '',
        alumno_id INTEGER,
        profesor_id INTEGER,
        pago_id INTEGER,
        liquidacion_id INTEGER,
        clase_id INTEGER,
        estado_cuenta_movimiento_id INTEGER,
        liquidacion_ajuste_id INTEGER,
        estado TEXT DEFAULT 'activo',
        fecha_creacion TEXT,
        fecha_anulacion TEXT,
        usuario_anulacion_id INTEGER,
        usuario_anulacion_nombre TEXT,
        motivo_anulacion TEXT DEFAULT ''
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reglas_comision (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profesor_id INTEGER,
        nombre TEXT,
        tipo_clase_id INTEGER,
        modalidad TEXT DEFAULT 'porcentaje_fijo',
        base_calculo TEXT DEFAULT 'monto_real',
        porcentaje REAL DEFAULT 0,
        monto REAL DEFAULT 0,
        min_alumnos INTEGER,
        max_alumnos INTEGER,
        min_presentes INTEGER,
        max_presentes INTEGER,
        min_clases_mes INTEGER,
        max_clases_mes INTEGER,
        min_monto REAL,
        max_monto REAL,
        aplica_recupero TEXT DEFAULT 'todos',
        requiere_promocion INTEGER DEFAULT 0,
        prioridad INTEGER DEFAULT 0,
        estado TEXT DEFAULT 'activa',
        fecha_inicio TEXT,
        fecha_fin TEXT,
        observaciones TEXT DEFAULT '',
        creado_por INTEGER,
        creado_por_nombre TEXT,
        fecha_creacion TEXT,
        actualizado_por INTEGER,
        actualizado_por_nombre TEXT,
        fecha_actualizacion TEXT,
        archivada INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reglas_comision_historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regla_id INTEGER,
        profesor_id INTEGER,
        accion TEXT,
        datos_anteriores TEXT,
        datos_nuevos TEXT,
        motivo TEXT,
        usuario_id INTEGER,
        usuario_nombre TEXT,
        fecha TEXT
    )
    """)

    colores_default = {
        "nombre_app": "Espacio Arte Academia",
        "logo_app": "logo.png",
        "color_fondo": "#f7fbfb",
        "color_texto": "#263238",
        "color_sidebar": "#ffffff",
        "color_sidebar_texto": "#263238",
        "color_tarjeta": "#ffffff",
        "color_borde": "#d8eeee",
        "color_primario": "#10aaa5",
        "color_exito": "#22c55e",
        "color_peligro": "#ef4444",
        "radio_bordes": "12",
        "comision_default_individual": "50",
        "comision_default_duo": "40",
        "comision_default_grupal": "40",
        "comision_base_default": "monto_real"
    }

    for clave, valor in colores_default.items():
        cur.execute("""
            INSERT OR IGNORE INTO configuracion (clave, valor)
            VALUES (?, ?)
        """, (clave, valor))

    cur.execute("""
        UPDATE configuracion
        SET valor = 'logo.png'
        WHERE clave = 'logo_app'
          AND valor = 'logo.jpeg'
    """)

    for tipo in TIPOS_CLASE:
        cur.execute("INSERT OR IGNORE INTO tipos_clase (nombre) VALUES (?)", (tipo,))

    columnas_clases = [col[1] for col in cur.execute("PRAGMA table_info(clases)").fetchall()]
    if "estado" not in columnas_clases:
        cur.execute("ALTER TABLE clases ADD COLUMN estado TEXT DEFAULT 'programada'")
    if "motivo_cancelacion" not in columnas_clases:
        cur.execute("ALTER TABLE clases ADD COLUMN motivo_cancelacion TEXT DEFAULT ''")
    if "recuperacion_de" not in columnas_clases:
        cur.execute("ALTER TABLE clases ADD COLUMN recuperacion_de INTEGER")
    if "tipo_clase_id" not in columnas_clases:
        cur.execute("ALTER TABLE clases ADD COLUMN tipo_clase_id INTEGER DEFAULT 1")
    for columna, definicion in [
        ("es_recupero", "INTEGER DEFAULT 0"),
        ("recupero_id", "INTEGER"),
        ("capacidad_maxima", "INTEGER DEFAULT 0"),
        ("aula", "TEXT DEFAULT ''")
    ]:
        if columna not in columnas_clases:
            cur.execute(f"ALTER TABLE clases ADD COLUMN {columna} {definicion}")

    columnas_alumnos = [col[1] for col in cur.execute("PRAGMA table_info(alumnos)").fetchall()]
    if "tutor_profesor_id" not in columnas_alumnos:
        cur.execute("ALTER TABLE alumnos ADD COLUMN tutor_profesor_id INTEGER")

    columnas_usuarios = [col[1] for col in cur.execute("PRAGMA table_info(usuarios)").fetchall()]
    for columna, definicion in [
        ("activo", "INTEGER DEFAULT 1"),
        ("profesor_id", "INTEGER")
    ]:
        if columna not in columnas_usuarios:
            cur.execute(f"ALTER TABLE usuarios ADD COLUMN {columna} {definicion}")
    cur.execute("UPDATE usuarios SET rol='recepcion' WHERE rol='comun'")
    cur.execute("UPDATE usuarios SET activo=COALESCE(activo, 1)")

    for tabla in ["pagos_alumnos", "matriculas"]:
        columnas_pago = [col[1] for col in cur.execute(f"PRAGMA table_info({tabla})").fetchall()]
        if "monto_real_pagado" not in columnas_pago:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN monto_real_pagado REAL DEFAULT 0")
        if "metodo_pago" not in columnas_pago:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN metodo_pago TEXT DEFAULT ''")
        if "comprobante" not in columnas_pago:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN comprobante TEXT DEFAULT ''")
        if "observacion_pago" not in columnas_pago:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN observacion_pago TEXT DEFAULT ''")

    columnas_promociones = [col[1] for col in cur.execute("PRAGMA table_info(promociones)").fetchall()]
    for columna, definicion in [
        ("nombre", "TEXT DEFAULT ''"),
        ("tipo", "TEXT DEFAULT 'porcentaje'"),
        ("fecha_inicio", "TEXT"),
        ("fecha_fin", "TEXT"),
        ("limite_usos", "INTEGER"),
        ("usos_actuales", "INTEGER DEFAULT 0"),
        ("automatica", "INTEGER DEFAULT 0"),
        ("acumulable", "INTEGER DEFAULT 0"),
        ("prioridad", "INTEGER DEFAULT 0"),
        ("color", "TEXT DEFAULT '#10aaa5'"),
        ("aplica_alumno_id", "INTEGER"),
        ("grupo_familiar", "TEXT DEFAULT ''"),
        ("tipo_clase_id", "INTEGER"),
        ("profesor_id", "INTEGER"),
        ("cantidad_clases_min", "INTEGER"),
        ("instrumento", "TEXT DEFAULT ''"),
        ("nuevo_alumno", "INTEGER DEFAULT 0"),
        ("alumno_activo", "INTEGER DEFAULT 1"),
        ("metodo_pago", "TEXT DEFAULT ''"),
        ("aplica_matricula", "INTEGER DEFAULT 1"),
        ("aplica_cuota", "INTEGER DEFAULT 1"),
        ("afecta_profesor", "INTEGER DEFAULT 0"),
        ("motivo", "TEXT DEFAULT ''"),
        ("eliminada", "INTEGER DEFAULT 0")
    ]:
        if columna not in columnas_promociones:
            cur.execute(f"ALTER TABLE promociones ADD COLUMN {columna} {definicion}")

    cur.execute("""
        UPDATE promociones
        SET nombre = COALESCE(NULLIF(nombre, ''), descripcion, 'Promocion'),
            tipo = COALESCE(NULLIF(tipo, ''), 'porcentaje'),
            color = COALESCE(NULLIF(color, ''), '#10aaa5'),
            aplica_alumno_id = COALESCE(aplica_alumno_id, alumno_id),
            aplica_cuota = COALESCE(aplica_cuota, 1),
            aplica_matricula = COALESCE(aplica_matricula, 1),
            eliminada = COALESCE(eliminada, 0)
    """)

    columnas_profesores = [col[1] for col in cur.execute("PRAGMA table_info(profesores)").fetchall()]
    for columna, definicion in [
        ("nombre_apellido", "TEXT"),
        ("dni", "TEXT"),
        ("telefono", "TEXT"),
        ("domicilio", "TEXT"),
        ("email", "TEXT"),
        ("edad", "INTEGER"),
        ("precio_clase", "REAL DEFAULT 0"),
        ("porcentaje_individual", "REAL DEFAULT 50"),
        ("porcentaje_duo", "REAL DEFAULT 40"),
        ("porcentaje_grupal", "REAL DEFAULT 40"),
        ("activo", "INTEGER DEFAULT 1"),
        ("observaciones_liquidacion", "TEXT DEFAULT ''"),
        ("color", "TEXT DEFAULT '#3b82f6'")
    ]:
        if columna not in columnas_profesores:
            cur.execute(f"ALTER TABLE profesores ADD COLUMN {columna} {definicion}")

    cur.execute("""
        UPDATE profesores
        SET porcentaje_individual = COALESCE(NULLIF(porcentaje_individual, 0), 50),
            porcentaje_duo = COALESCE(NULLIF(porcentaje_duo, 0), porcentaje_grupal, 40),
            porcentaje_grupal = COALESCE(NULLIF(porcentaje_grupal, 0), 40),
            activo = COALESCE(activo, 1)
    """)

    columnas_profesores = [col[1] for col in cur.execute("PRAGMA table_info(profesores)").fetchall()]
    if "nombre" in columnas_profesores:
        cur.execute("""
            UPDATE profesores
            SET nombre_apellido = COALESCE(NULLIF(nombre_apellido, ''), nombre)
            WHERE nombre IS NOT NULL
        """)
    if "valor_hora" in columnas_profesores:
        cur.execute("""
            UPDATE profesores
            SET precio_clase = COALESCE(NULLIF(precio_clase, 0), valor_hora)
            WHERE valor_hora IS NOT NULL
        """)

    columnas_liquidacion_ajustes = [col[1] for col in cur.execute("PRAGMA table_info(liquidacion_ajustes)").fetchall()]
    for columna, definicion in [
        ("ajuste_manual_id", "INTEGER"),
        ("anulado", "INTEGER DEFAULT 0")
    ]:
        if columna not in columnas_liquidacion_ajustes:
            cur.execute(f"ALTER TABLE liquidacion_ajustes ADD COLUMN {columna} {definicion}")

    usuario_inicial = cur.execute("""
        SELECT id FROM usuarios
        WHERE nombre=?
    """, ("Francisco Gonzalez",)).fetchone()

    if not usuario_inicial:
        cur.execute("""
            INSERT INTO usuarios (nombre, password_hash, rol, activo)
            VALUES (?, ?, ?, 1)
        """, (
            "Francisco Gonzalez",
            generate_password_hash("2705"),
            "admin"
        ))

    for codigo, nombre in ROLE_LABELS.items():
        cur.execute("""
            INSERT OR IGNORE INTO roles (codigo, nombre, descripcion, sistema, activo)
            VALUES (?, ?, ?, 1, 1)
        """, (codigo, nombre, f"Rol {nombre.lower()}"))

    for codigo, modulo, descripcion in PERMISOS_SISTEMA:
        cur.execute("""
            INSERT INTO permisos (codigo, modulo, descripcion)
            VALUES (?, ?, ?)
            ON CONFLICT(codigo) DO UPDATE SET modulo=excluded.modulo, descripcion=excluded.descripcion
        """, (codigo, modulo, descripcion))

    for rol_codigo, permisos in DEFAULT_ROLE_PERMISSIONS.items():
        for permiso in permisos:
            cur.execute("""
                INSERT OR IGNORE INTO rol_permisos (rol_codigo, permiso_codigo)
                VALUES (?, ?)
            """, (rol_codigo, permiso))

    cur.execute("""
        UPDATE clase_alumnos
        SET asistencia = CASE
            WHEN asistencia = 1 OR asistencia = '1' THEN 'presente'
            WHEN asistencia = 0 OR asistencia = '0' THEN 'pendiente'
            WHEN asistencia IS NULL THEN 'pendiente'
            ELSE asistencia
        END
    """)

    conn.commit()
    conn.close()

init_db()

def registrar_auditoria(conn, modulo, accion, entidad="", entidad_id="", detalle=""):
    if not session.get("usuario_id") and modulo != "seguridad":
        return

    conn.execute("""
        INSERT INTO auditoria (
            fecha, usuario_id, usuario_nombre, usuario_rol,
            modulo, accion, entidad, entidad_id, detalle
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        session.get("usuario_id"),
        session.get("usuario_nombre") or "Sistema",
        session.get("usuario_rol") or "",
        modulo,
        accion,
        entidad,
        str(entidad_id or ""),
        detalle
    ))

def agregar_alumnos_a_clase(conn, clase_id, alumnos):
    for alumno_id in alumnos:
        try:
            conn.execute("""
                INSERT INTO clase_alumnos (clase_id, alumno_id)
                VALUES (?, ?)
            """, (clase_id, alumno_id))
        except sqlite3.IntegrityError:
            pass

def redirect_clases(mensaje=None, tipo="success"):
    if not mensaje:
        return redirect("/clases")
    return redirect("/clases?" + urlencode({"mensaje": mensaje, "tipo": tipo}))

def validar_duracion(valor):
    try:
        duracion = float(valor)
    except (TypeError, ValueError):
        return None

    if duracion <= 0:
        return None

    return duracion

def validar_fecha(valor):
    return parsear_fecha(valor) is not None

def parsear_fecha(valor):
    try:
        return datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        pass

    try:
        return datetime.fromisoformat((valor or "")[:16])
    except (TypeError, ValueError):
        return None

def existe_profesor(conn, profesor_id):
    return conn.execute("SELECT id FROM profesores WHERE id=?", (profesor_id,)).fetchone() is not None

def clase_duplicada(conn, profesor_id, fecha, clase_id=None):
    params = [profesor_id, fecha]
    sql = "SELECT id FROM clases WHERE profesor_id=? AND fecha=?"

    if clase_id:
        sql += " AND id<>?"
        params.append(clase_id)

    return conn.execute(sql, params).fetchone() is not None

def obtener_intervalo(fecha, duracion):
    inicio = parsear_fecha(fecha)
    if not inicio:
        return None, None
    fin = inicio + timedelta(hours=float(duracion))
    return inicio, fin

def hay_solapamiento(conn, profesor_id, fecha, duracion, clase_id=None):
    inicio, fin = obtener_intervalo(fecha, duracion)
    if not inicio or not fin:
        return None

    clases = conn.execute("""
        SELECT id, fecha, duracion
        FROM clases
        WHERE profesor_id=? AND estado<>'cancelada'
    """, (profesor_id,)).fetchall()

    for clase in clases:
        if clase_id and int(clase["id"]) == int(clase_id):
            continue
        if not clase["fecha"] or not clase["duracion"]:
            continue

        inicio_existente, fin_existente = obtener_intervalo(clase["fecha"], clase["duracion"])
        if not inicio_existente or not fin_existente:
            continue
        if inicio < fin_existente and fin > inicio_existente:
            return clase

    return None

def normalizar_estado(valor, permitidos, defecto):
    if valor in permitidos:
        return valor
    return defecto

def normalizar_motivo(valor):
    valor = (valor or "").strip().lower()
    if valor in MOTIVOS_CANCELACION:
        return valor
    return "otro" if valor else ""

def normalizar_recuperacion(valor):
    if not valor:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None

def normalizar_motivo_recupero(valor):
    valor = (valor or "").strip()
    return valor if valor in MOTIVOS_RECUPERO else "otro"

def normalizar_tipo_recupero(valor):
    valor = (valor or "").strip()
    return valor if valor in TIPOS_RECUPERO else "individual"

def normalizar_estado_recupero(valor):
    return normalizar_estado(valor, ESTADOS_RECUPERO, "pendiente")

def validar_precio(valor):
    try:
        precio = float(valor or 0)
    except (TypeError, ValueError):
        return 0
    return max(precio, 0)

def validar_entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None

def obtener_configuracion(conn):
    filas = conn.execute("SELECT clave, valor FROM configuracion").fetchall()
    return {fila["clave"]: fila["valor"] for fila in filas}

def calcular_descuento(monto_normal, promocion):
    monto_normal = validar_precio(monto_normal)
    if not promocion:
        return 0

    porcentaje = float(promocion["porcentaje_descuento"] or 0)
    monto = float(promocion["monto_descuento"] or 0)
    descuento = monto + (monto_normal * porcentaje / 100)
    return min(descuento, monto_normal)

def calcular_monto_con_promocion(monto_normal, promocion):
    descuento = calcular_descuento(monto_normal, promocion)
    return descuento, max(validar_precio(monto_normal) - descuento, 0)

def fecha_limite_recupero(fecha_clase, dias=30):
    base = parsear_fecha(fecha_clase) or datetime.now()
    return (base + timedelta(days=dias)).strftime("%Y-%m-%d")

def actualizar_vencimientos_recuperos(conn):
    hoy = datetime.now().strftime("%Y-%m-%d")
    conn.execute("""
        UPDATE recuperos
        SET estado='vencido', actualizado_en=?
        WHERE estado IN ('pendiente', 'programado')
          AND fecha_limite IS NOT NULL
          AND fecha_limite<?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), hoy))

def crear_notificacion_recupero(conn, recupero_id, tipo, mensaje, fecha_programada=None):
    conn.execute("""
        INSERT INTO recupero_notificaciones (
            recupero_id, tipo, mensaje, estado, fecha_programada, fecha_creacion
        )
        VALUES (?, ?, ?, 'pendiente', ?, ?)
    """, (
        recupero_id,
        tipo,
        mensaje,
        fecha_programada,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

def crear_recupero_si_no_existe(conn, clase_original_id, alumno_id, motivo, tipo="individual", **opciones):
    clase = conn.execute("SELECT * FROM clases WHERE id=?", (clase_original_id,)).fetchone()
    if not clase or not alumno_id:
        return None

    existente = conn.execute("""
        SELECT *
        FROM recuperos
        WHERE clase_original_id=? AND alumno_id=? AND tipo=? AND estado<>'cancelado'
    """, (clase_original_id, alumno_id, tipo)).fetchone()
    if existente:
        return existente["id"]

    motivo = normalizar_motivo_recupero(motivo)
    tipo = normalizar_tipo_recupero(tipo)
    fecha_limite = opciones.get("fecha_limite") or fecha_limite_recupero(clase["fecha"])
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("""
        INSERT INTO recuperos (
            clase_original_id, alumno_id, profesor_id, motivo, motivo_manual, tipo,
            estado, fecha_creacion, fecha_limite, afecta_liquidacion, profesor_cobra,
            academia_absorbe, genera_deuda, cuenta_asistencia, consume_cupo,
            reutilizable, costo_adicional, gratuito, incluido_en_cuota,
            observaciones, creado_por, creado_por_nombre, actualizado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        clase_original_id,
        alumno_id,
        clase["profesor_id"],
        motivo,
        opciones.get("motivo_manual", ""),
        tipo,
        ahora,
        fecha_limite,
        1 if opciones.get("afecta_liquidacion", True) else 0,
        1 if opciones.get("profesor_cobra", True) else 0,
        1 if opciones.get("academia_absorbe", True) else 0,
        1 if opciones.get("genera_deuda", False) else 0,
        1 if opciones.get("cuenta_asistencia", True) else 0,
        1 if opciones.get("consume_cupo", True) else 0,
        1 if opciones.get("reutilizable", False) else 0,
        validar_precio(opciones.get("costo_adicional")),
        1 if opciones.get("gratuito", True) else 0,
        1 if opciones.get("incluido_en_cuota", True) else 0,
        opciones.get("observaciones", ""),
        session.get("usuario_id"),
        session.get("usuario_nombre"),
        ahora
    ))
    crear_notificacion_recupero(conn, cur.lastrowid, "creacion", "Se genero un recupero pendiente.", fecha_limite)
    registrar_auditoria(conn, "recuperos", "crear", "recupero", cur.lastrowid, f"Recupero generado para alumno #{alumno_id} por clase #{clase_original_id}")
    return cur.lastrowid

def crear_recuperos_por_clase_cancelada(conn, clase_id, motivo):
    alumnos = conn.execute("""
        SELECT alumno_id
        FROM clase_alumnos
        WHERE clase_id=?
    """, (clase_id,)).fetchall()
    creados = 0
    motivo_recupero = {
        "falto profesor": "falta_profesor",
        "feriado": "feriado",
        "reprogramada": "suspension_administrativa",
        "otro": "otro"
    }.get(motivo or "", "suspension_administrativa")

    for alumno in alumnos:
        recupero_id = crear_recupero_si_no_existe(
            conn,
            clase_id,
            alumno["alumno_id"],
            motivo_recupero,
            "completo",
            afecta_liquidacion=True,
            profesor_cobra=False if motivo == "falto profesor" else True,
            academia_absorbe=True,
            observaciones="Generado automaticamente por cancelacion de clase."
        )
        if recupero_id:
            creados += 1
    return creados

def disponibilidad_profesor(conn, profesor_id, fecha, duracion, clase_ignorar=None):
    if not validar_fecha(fecha) or not duracion:
        return False, "Fecha o duracion invalida."
    if clase_duplicada(conn, profesor_id, fecha, clase_ignorar):
        return False, "Ya existe una clase de ese profesor en ese horario."
    if hay_solapamiento(conn, profesor_id, fecha, duracion, clase_ignorar):
        return False, "Ese profesor ya tiene una clase que se cruza con ese horario."
    return True, ""

def normalizar_fecha(valor):
    valor = (valor or "").strip()
    if not valor:
        return ""
    try:
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""

def normalizar_tipo_promocion(valor):
    valor = (valor or "porcentaje").strip()
    return valor if valor in TIPOS_PROMOCION else "porcentaje"

def promocion_vigente(promocion, fecha_ref=None):
    if not promocion:
        return False
    if int(promocion["activa"] or 0) != 1 or int(promocion["eliminada"] or 0) == 1:
        return False
    fecha_ref = fecha_ref or datetime.now().strftime("%Y-%m-%d")
    if promocion["fecha_inicio"] and promocion["fecha_inicio"] > fecha_ref:
        return False
    if promocion["fecha_fin"] and promocion["fecha_fin"] < fecha_ref:
        return False
    limite = promocion["limite_usos"]
    if limite is not None and int(limite or 0) > 0 and int(promocion["usos_actuales"] or 0) >= int(limite):
        return False
    return True

def alumno_es_nuevo(conn, alumno_id, anio, mes):
    alumno = conn.execute("SELECT dia_inscripcion FROM alumnos WHERE id=?", (alumno_id,)).fetchone()
    if alumno and alumno["dia_inscripcion"]:
        try:
            fecha = datetime.strptime(alumno["dia_inscripcion"], "%Y-%m-%d")
            return fecha.year == int(anio) and fecha.month == int(mes or fecha.month)
        except ValueError:
            pass

    pagos_previos = conn.execute("""
        SELECT COUNT(*) AS total
        FROM pagos_alumnos
        WHERE alumno_id=? AND (anio < ? OR (anio=? AND mes < ?))
    """, (alumno_id, anio, anio, mes or 1)).fetchone()["total"]
    matriculas_previas = conn.execute("""
        SELECT COUNT(*) AS total
        FROM matriculas
        WHERE alumno_id=? AND anio < ?
    """, (alumno_id, anio)).fetchone()["total"]
    return int(pagos_previos or 0) == 0 and int(matriculas_previas or 0) == 0

def cantidad_clases_alumno_mes(conn, alumno_id, anio, mes, tipo_clase_id=None, profesor_id=None):
    condiciones = [
        "clase_alumnos.alumno_id=?",
        "clases.estado<>'cancelada'",
        "clases.fecha LIKE ?"
    ]
    valores = [alumno_id, f"{anio}-{int(mes):02d}-%"]
    if tipo_clase_id:
        condiciones.append("clases.tipo_clase_id=?")
        valores.append(tipo_clase_id)
    if profesor_id:
        condiciones.append("clases.profesor_id=?")
        valores.append(profesor_id)

    fila = conn.execute("""
        SELECT COUNT(*) AS total
        FROM clase_alumnos
        JOIN clases ON clase_alumnos.clase_id = clases.id
        WHERE """ + " AND ".join(condiciones), valores).fetchone()
    return int(fila["total"] or 0)

def promocion_cumple_condiciones(conn, promocion, alumno_id, pago_tipo, anio, mes, metodo_pago=""):
    if not promocion_vigente(promocion):
        return False
    if pago_tipo == "cuota" and int(promocion["aplica_cuota"] or 0) != 1:
        return False
    if pago_tipo == "matricula" and int(promocion["aplica_matricula"] or 0) != 1:
        return False

    alumno_filtro = promocion["aplica_alumno_id"] or promocion["alumno_id"]
    if alumno_filtro and int(alumno_filtro) != int(alumno_id):
        return False

    if promocion["metodo_pago"] and metodo_pago and promocion["metodo_pago"] != metodo_pago:
        return False

    if int(promocion["nuevo_alumno"] or 0) == 1 and not alumno_es_nuevo(conn, alumno_id, anio, mes or 1):
        return False

    if promocion["cantidad_clases_min"]:
        cantidad = cantidad_clases_alumno_mes(
            conn,
            alumno_id,
            anio,
            mes or datetime.now().month,
            promocion["tipo_clase_id"],
            promocion["profesor_id"]
        )
        if cantidad < int(promocion["cantidad_clases_min"] or 0):
            return False

    return True

def calcular_descuento_promocion(monto_normal, promocion, pago_tipo):
    monto_normal = validar_precio(monto_normal)
    tipo = normalizar_tipo_promocion(promocion["tipo"])
    porcentaje = validar_precio(promocion["porcentaje_descuento"])
    monto = validar_precio(promocion["monto_descuento"])

    if tipo == "matricula_bonificada":
        descuento = monto_normal if pago_tipo == "matricula" else 0
    elif tipo == "primer_mes_bonificado":
        descuento = monto_normal * ((porcentaje or 100) / 100)
    elif tipo == "monto_fijo":
        descuento = monto
    else:
        descuento = monto + (monto_normal * porcentaje / 100)

    return min(max(descuento, 0), monto_normal)

def seleccionar_promociones_aplicables(conn, alumno_id, pago_tipo, anio, mes, monto_normal, promocion_manual_id=None, metodo_pago=""):
    promociones = []
    if promocion_manual_id:
        manual = conn.execute("SELECT * FROM promociones WHERE id=?", (promocion_manual_id,)).fetchone()
        if manual and promocion_cumple_condiciones(conn, manual, alumno_id, pago_tipo, anio, mes, metodo_pago):
            promociones.append(manual)

    automaticas = conn.execute("""
        SELECT *
        FROM promociones
        WHERE automatica=1 AND eliminada=0
        ORDER BY prioridad DESC, id DESC
    """).fetchall()
    for promocion in automaticas:
        if promocion_manual_id and int(promocion["id"]) == int(promocion_manual_id):
            continue
        if promocion_cumple_condiciones(conn, promocion, alumno_id, pago_tipo, anio, mes, metodo_pago):
            promociones.append(promocion)

    aplicadas = []
    descuento_total = 0
    for promocion in promociones:
        descuento = calcular_descuento_promocion(max(monto_normal - descuento_total, 0), promocion, pago_tipo)
        if descuento <= 0:
            continue
        aplicadas.append((promocion, descuento))
        descuento_total += descuento
        if int(promocion["acumulable"] or 0) != 1:
            break
        if descuento_total >= monto_normal:
            break

    descuento_total = min(descuento_total, monto_normal)
    monto_final = max(monto_normal - descuento_total, 0)
    return {
        "aplicadas": aplicadas,
        "descuento": descuento_total,
        "monto_final": monto_final,
        "promocion_id": aplicadas[0][0]["id"] if aplicadas else None,
        "motivo": ", ".join(p[0]["nombre"] or p[0]["descripcion"] or "Promocion" for p in aplicadas)
    }

def registrar_usos_promociones(conn, aplicadas, alumno_id, pago_tipo, pago_id, monto_original, monto_final):
    for promocion, descuento in aplicadas:
        conn.execute("""
            INSERT INTO promocion_usos (
                promocion_id, alumno_id, pago_tipo, pago_id, monto_original,
                descuento, monto_final, motivo, usuario_id, usuario_nombre, fecha
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            promocion["id"],
            alumno_id,
            pago_tipo,
            pago_id,
            monto_original,
            descuento,
            monto_final,
            promocion["nombre"] or promocion["descripcion"],
            session.get("usuario_id"),
            session.get("usuario_nombre"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.execute("""
            UPDATE promociones
            SET usos_actuales = COALESCE(usos_actuales, 0) + 1
            WHERE id=?
        """, (promocion["id"],))

def registrar_movimiento_cuenta(conn, alumno_id, fecha, concepto, tipo_movimiento, categoria, debe=0, haber=0, estado="pendiente", referencia_tipo="", referencia_id=None, metodo_pago="", comprobante="", observacion="", usuario_nombre=None):
    debe = validar_precio(debe)
    haber = validar_precio(haber)
    if debe == 0 and haber == 0:
        return None

    existente = None
    if referencia_tipo and referencia_id is not None and categoria:
        existente = conn.execute("""
            SELECT id
            FROM movimientos_cuenta
            WHERE alumno_id=? AND referencia_tipo=? AND referencia_id=? AND categoria=? AND anulado=0
            LIMIT 1
        """, (alumno_id, referencia_tipo, referencia_id, categoria)).fetchone()

    datos = (
        fecha or datetime.now().strftime("%Y-%m-%d"),
        concepto,
        tipo_movimiento,
        categoria,
        debe,
        haber,
        metodo_pago or "",
        comprobante or "",
        observacion or "",
        estado,
        session.get("usuario_id") if has_request_context() else None,
        usuario_nombre or (session.get("usuario_nombre") if has_request_context() else ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    if existente:
        conn.execute("""
            UPDATE movimientos_cuenta
            SET fecha=?, concepto=?, tipo_movimiento=?, categoria=?, debe=?, haber=?,
                metodo_pago=?, comprobante=?, observacion=?, estado=?,
                usuario_modificador_id=?, usuario_modificador_nombre=?, fecha_modificacion=?
            WHERE id=?
        """, (*datos, existente["id"]))
        return existente["id"]

    cur = conn.execute("""
        INSERT INTO movimientos_cuenta (
            alumno_id, fecha, concepto, tipo_movimiento, categoria, debe, haber,
            metodo_pago, comprobante, observacion, estado, referencia_tipo,
            referencia_id, usuario_creador_id, usuario_creador_nombre, fecha_creacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        alumno_id,
        *datos[:10],
        referencia_tipo,
        referencia_id,
        datos[10],
        datos[11],
        datos[12]
    ))
    return cur.lastrowid

def recalcular_saldos_alumno(conn, alumno_id):
    movimientos = conn.execute("""
        SELECT id, debe, haber
        FROM movimientos_cuenta
        WHERE alumno_id=? AND anulado=0
        ORDER BY fecha, id
    """, (alumno_id,)).fetchall()
    saldo = 0
    for mov in movimientos:
        saldo += float(mov["debe"] or 0) - float(mov["haber"] or 0)
        conn.execute("UPDATE movimientos_cuenta SET saldo_acumulado=? WHERE id=?", (saldo, mov["id"]))
    return saldo

def sincronizar_estado_cuenta_alumno(conn, alumno_id):
    cuotas = conn.execute("""
        SELECT pagos_alumnos.*, COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) AS promo_nombre
        FROM pagos_alumnos
        LEFT JOIN promociones ON pagos_alumnos.promocion_id = promociones.id
        WHERE pagos_alumnos.alumno_id=?
    """, (alumno_id,)).fetchall()
    for cuota in cuotas:
        fecha = f"{cuota['anio']}-{int(cuota['mes']):02d}-01"
        periodo = f"{int(cuota['mes']):02d}/{cuota['anio']}"
        estado_cargo = "pagado" if cuota["estado"] == "pagado" else ("parcial" if float(cuota["monto_real_pagado"] or 0) > 0 else "pendiente")
        registrar_movimiento_cuenta(conn, alumno_id, fecha, f"Cuota mensual {periodo}", "cargo", "cuota_mensual", cuota["monto_normal"], 0, estado_cargo, "cuota", cuota["id"])
        if float(cuota["descuento"] or 0) > 0:
            registrar_movimiento_cuenta(conn, alumno_id, fecha, f"Descuento/Promocion: {cuota['promo_nombre'] or 'descuento aplicado'}", "credito", "promocion", 0, cuota["descuento"], "bonificado", "cuota", cuota["id"])
        pago_real = float(cuota["monto_real_pagado"] or 0)
        if pago_real > 0:
            registrar_movimiento_cuenta(
                conn, alumno_id, cuota["fecha_pago"] or datetime.now().strftime("%Y-%m-%d"),
                f"Pago cuota {periodo}", "credito", "pago",
                0, pago_real, "pagado", "cuota_pago", cuota["id"],
                cuota["metodo_pago"] or "", cuota["comprobante"] or "", cuota["observacion_pago"] or ""
            )

    matriculas = conn.execute("""
        SELECT matriculas.*, COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) AS promo_nombre
        FROM matriculas
        LEFT JOIN promociones ON matriculas.promocion_id = promociones.id
        WHERE matriculas.alumno_id=?
    """, (alumno_id,)).fetchall()
    for matricula in matriculas:
        fecha = f"{matricula['anio']}-01-01"
        estado_cargo = "pagado" if matricula["estado"] == "pagado" else ("parcial" if float(matricula["monto_real_pagado"] or 0) > 0 else "pendiente")
        registrar_movimiento_cuenta(conn, alumno_id, fecha, f"Matricula anual {matricula['anio']}", "cargo", "matricula_anual", matricula["monto_normal"], 0, estado_cargo, "matricula", matricula["id"])
        if float(matricula["descuento"] or 0) > 0:
            registrar_movimiento_cuenta(conn, alumno_id, fecha, f"Descuento/Promocion matricula: {matricula['promo_nombre'] or 'descuento aplicado'}", "credito", "promocion", 0, matricula["descuento"], "bonificado", "matricula", matricula["id"])
        pago_real = float(matricula["monto_real_pagado"] or 0)
        if pago_real > 0:
            registrar_movimiento_cuenta(
                conn, alumno_id, matricula["fecha_pago"] or datetime.now().strftime("%Y-%m-%d"),
                f"Pago matricula {matricula['anio']}", "credito", "pago",
                0, pago_real, "pagado", "matricula_pago", matricula["id"],
                matricula["metodo_pago"] or "", matricula["comprobante"] or "", matricula["observacion_pago"] or ""
            )

    recuperos_pago = conn.execute("""
        SELECT *
        FROM recuperos
        WHERE alumno_id=? AND costo_adicional > 0
    """, (alumno_id,)).fetchall()
    for recupero in recuperos_pago:
        fecha = (recupero["fecha_programada"] or recupero["fecha_creacion"] or datetime.now().strftime("%Y-%m-%d"))[:10]
        registrar_movimiento_cuenta(conn, alumno_id, fecha, f"Recupero pago #{recupero['id']}", "cargo", "recupero_pago", recupero["costo_adicional"], 0, recupero["estado"], "recupero", recupero["id"], observacion=recupero["observaciones"] or "")

    return recalcular_saldos_alumno(conn, alumno_id)

def sincronizar_estado_cuenta_todos(conn):
    alumnos = conn.execute("SELECT id FROM alumnos").fetchall()
    for alumno in alumnos:
        sincronizar_estado_cuenta_alumno(conn, alumno["id"])

def obtener_estado_cuenta_alumno(conn, alumno_id, filtros=None):
    sincronizar_estado_cuenta_alumno(conn, alumno_id)
    filtros = filtros or {}
    condiciones = ["alumno_id=?", "anulado=0"]
    valores = [alumno_id]
    if filtros.get("desde"):
        condiciones.append("fecha>=?")
        valores.append(filtros["desde"])
    if filtros.get("hasta"):
        condiciones.append("fecha<=?")
        valores.append(filtros["hasta"])
    if filtros.get("tipo_movimiento"):
        condiciones.append("tipo_movimiento=?")
        valores.append(filtros["tipo_movimiento"])
    if filtros.get("metodo_pago"):
        condiciones.append("metodo_pago=?")
        valores.append(filtros["metodo_pago"])
    if filtros.get("estado"):
        condiciones.append("estado=?")
        valores.append(filtros["estado"])
    if filtros.get("concepto"):
        condiciones.append("concepto LIKE ?")
        valores.append(f"%{filtros['concepto']}%")
    if filtros.get("solo") == "deudas":
        condiciones.append("debe > 0")
    elif filtros.get("solo") == "pagos":
        condiciones.append("categoria='pago'")
    elif filtros.get("solo") == "descuentos":
        condiciones.append("categoria IN ('promocion', 'bonificacion', 'ajuste_negativo')")

    movimientos = conn.execute("""
        SELECT *
        FROM movimientos_cuenta
        WHERE """ + " AND ".join(condiciones) + """
        ORDER BY fecha, id
    """, valores).fetchall()
    resumen = resumen_estado_cuenta_alumno(conn, alumno_id)
    return movimientos, resumen

def resumen_estado_cuenta_alumno(conn, alumno_id):
    sincronizar_estado_cuenta_alumno(conn, alumno_id)
    fila = conn.execute("""
        SELECT COALESCE(SUM(debe), 0) AS debe, COALESCE(SUM(haber), 0) AS haber
        FROM movimientos_cuenta
        WHERE alumno_id=? AND anulado=0
    """, (alumno_id,)).fetchone()
    saldo = float(fila["debe"] or 0) - float(fila["haber"] or 0)
    hoy = datetime.now()
    mes_inicio = hoy.strftime("%Y-%m-01")
    mes_fin = (datetime(hoy.year + (1 if hoy.month == 12 else 0), 1 if hoy.month == 12 else hoy.month + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
    pagado_mes = conn.execute("""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE alumno_id=? AND anulado=0 AND categoria='pago' AND fecha BETWEEN ? AND ?
    """, (alumno_id, mes_inicio, mes_fin)).fetchone()["total"]
    pagado_total = conn.execute("""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE alumno_id=? AND anulado=0 AND categoria='pago'
    """, (alumno_id,)).fetchone()["total"]
    cuotas_pendientes = conn.execute("""
        SELECT COUNT(*) AS total FROM pagos_alumnos WHERE alumno_id=? AND estado<>'pagado'
    """, (alumno_id,)).fetchone()["total"]
    matricula_pendiente = conn.execute("""
        SELECT COUNT(*) AS total FROM matriculas WHERE alumno_id=? AND estado<>'pagado'
    """, (alumno_id,)).fetchone()["total"]
    ultimo_pago = conn.execute("""
        SELECT *
        FROM movimientos_cuenta
        WHERE alumno_id=? AND anulado=0 AND categoria='pago'
        ORDER BY fecha DESC, id DESC
        LIMIT 1
    """, (alumno_id,)).fetchone()
    proxima_cuota = conn.execute("""
        SELECT anio, mes, monto_pagado
        FROM pagos_alumnos
        WHERE alumno_id=? AND estado<>'pagado'
        ORDER BY anio, mes
        LIMIT 1
    """, (alumno_id,)).fetchone()
    return {
        "deuda_actual": max(saldo, 0),
        "saldo_a_favor": abs(min(saldo, 0)),
        "saldo": saldo,
        "total_debe": float(fila["debe"] or 0),
        "total_haber": float(fila["haber"] or 0),
        "pagado_mes": float(pagado_mes or 0),
        "pagado_total": float(pagado_total or 0),
        "cuotas_pendientes": int(cuotas_pendientes or 0),
        "matricula_pendiente": int(matricula_pendiente or 0),
        "ultimo_pago": ultimo_pago,
        "proxima_cuota": proxima_cuota
    }

def normalizar_categoria_ajuste(valor):
    valor = (valor or "").strip()
    return valor if valor in CATEGORIAS_AJUSTE_MANUAL else "alumno"

def normalizar_tipo_ajuste(valor):
    valor = (valor or "").strip()
    return valor if valor in TIPOS_AJUSTE_MANUAL else "correccion_administrativa"

def normalizar_signo_ajuste(valor):
    return "negativo" if (valor or "").strip() == "negativo" else "positivo"

def etiqueta_ajuste(tipo):
    return (tipo or "ajuste_manual").replace("_", " ").capitalize()

def tipo_liquidacion_desde_ajuste(tipo, signo):
    if signo == "negativo":
        if tipo == "clase_no_reconocida":
            return "clase_no_reconocida"
        return "descuento_profesor"
    if tipo in ["bono_profesor", "pago_extra_profesor", "clase_reconocida", "redondeo"]:
        return tipo
    if tipo == "compensacion_cancelacion":
        return "compensacion_cancelacion"
    return "correccion_administrativa"

def crear_ajuste_manual(conn, categoria, tipo_ajuste, monto, signo, motivo, observacion="", fecha=None,
                        alumno_id=None, profesor_id=None, pago_id=None, liquidacion_id=None, clase_id=None,
                        entidad_relacionada=""):
    categoria = normalizar_categoria_ajuste(categoria)
    tipo_ajuste = normalizar_tipo_ajuste(tipo_ajuste)
    signo = normalizar_signo_ajuste(signo)
    monto = validar_precio(monto)
    motivo = (motivo or "").strip()
    observacion = (observacion or "").strip()
    fecha = normalizar_fecha(fecha) or datetime.now().strftime("%Y-%m-%d")

    if monto <= 0:
        raise ValueError("El ajuste necesita un monto mayor a cero.")
    if not motivo:
        raise ValueError("El motivo del ajuste es obligatorio.")

    if liquidacion_id and not profesor_id:
        liquidacion = conn.execute("SELECT * FROM liquidaciones_profesores WHERE id=?", (liquidacion_id,)).fetchone()
        if liquidacion:
            profesor_id = liquidacion["profesor_id"]
    if profesor_id and not liquidacion_id and categoria in ["profesor", "liquidacion"]:
        fecha_dt = parsear_fecha(fecha) or datetime.now()
        liquidacion = obtener_o_crear_liquidacion(conn, profesor_id, fecha_dt.year, fecha_dt.month)
        liquidacion_id = liquidacion["id"]

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("""
        INSERT INTO ajustes_manuales (
            tipo_ajuste, categoria, monto, signo, motivo, observacion, fecha,
            usuario_creador_id, usuario_creador_nombre, entidad_relacionada,
            alumno_id, profesor_id, pago_id, liquidacion_id, clase_id, estado,
            fecha_creacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activo', ?)
    """, (
        tipo_ajuste,
        categoria,
        monto,
        signo,
        motivo,
        observacion,
        fecha,
        session.get("usuario_id") if has_request_context() else None,
        session.get("usuario_nombre") if has_request_context() else "",
        entidad_relacionada or "",
        alumno_id,
        profesor_id,
        pago_id,
        liquidacion_id,
        clase_id,
        ahora
    ))
    ajuste_id = cur.lastrowid

    movimiento_id = None
    if alumno_id:
        tipo_movimiento = "cargo" if signo == "positivo" else "credito"
        categoria_mov = "ajuste_positivo" if signo == "positivo" else "ajuste_negativo"
        concepto = f"Ajuste manual: {etiqueta_ajuste(tipo_ajuste)}"
        movimiento_id = registrar_movimiento_cuenta(
            conn,
            alumno_id,
            fecha,
            concepto,
            tipo_movimiento,
            categoria_mov,
            monto if signo == "positivo" else 0,
            monto if signo == "negativo" else 0,
            "pendiente" if signo == "positivo" else "bonificado",
            "ajuste_manual",
            ajuste_id,
            "",
            "",
            f"{motivo}. {observacion}".strip()
        )
        conn.execute("""
            UPDATE ajustes_manuales
            SET estado_cuenta_movimiento_id=?
            WHERE id=?
        """, (movimiento_id, ajuste_id))
        recalcular_saldos_alumno(conn, alumno_id)

    liquidacion_ajuste_id = None
    if liquidacion_id:
        tipo_liq = tipo_liquidacion_desde_ajuste(tipo_ajuste, signo)
        cur_liq = conn.execute("""
            INSERT INTO liquidacion_ajustes (
                liquidacion_id, tipo, monto, motivo, usuario_id, usuario_nombre,
                fecha, ajuste_manual_id, anulado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            liquidacion_id,
            tipo_liq,
            monto,
            motivo if not observacion else f"{motivo}. {observacion}",
            session.get("usuario_id") if has_request_context() else None,
            session.get("usuario_nombre") if has_request_context() else "",
            ahora,
            ajuste_id
        ))
        liquidacion_ajuste_id = cur_liq.lastrowid
        conn.execute("""
            UPDATE ajustes_manuales
            SET liquidacion_ajuste_id=?
            WHERE id=?
        """, (liquidacion_ajuste_id, ajuste_id))

    registrar_auditoria(
        conn,
        "ajustes",
        "crear",
        "ajuste_manual",
        ajuste_id,
        f"{categoria} {tipo_ajuste} {signo} por ${monto:.2f}: {motivo}"
    )
    ANALYTICS_CACHE.clear()
    return ajuste_id

def anular_ajuste_manual(conn, ajuste_id, motivo_anulacion):
    motivo_anulacion = (motivo_anulacion or "").strip()
    if not motivo_anulacion:
        raise ValueError("El motivo de anulacion es obligatorio.")

    ajuste = conn.execute("SELECT * FROM ajustes_manuales WHERE id=?", (ajuste_id,)).fetchone()
    if not ajuste:
        raise ValueError("No se encontro el ajuste.")
    if ajuste["estado"] == "anulado":
        return ajuste

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE ajustes_manuales
        SET estado='anulado', fecha_anulacion=?, usuario_anulacion_id=?,
            usuario_anulacion_nombre=?, motivo_anulacion=?
        WHERE id=?
    """, (
        ahora,
        session.get("usuario_id") if has_request_context() else None,
        session.get("usuario_nombre") if has_request_context() else "",
        motivo_anulacion,
        ajuste_id
    ))

    if ajuste["estado_cuenta_movimiento_id"]:
        movimiento = conn.execute("SELECT * FROM movimientos_cuenta WHERE id=?", (ajuste["estado_cuenta_movimiento_id"],)).fetchone()
        if movimiento and int(movimiento["anulado"] or 0) == 0:
            debe = float(movimiento["debe"] or 0)
            haber = float(movimiento["haber"] or 0)
            registrar_movimiento_cuenta(
                conn,
                movimiento["alumno_id"],
                datetime.now().strftime("%Y-%m-%d"),
                f"Reverso de ajuste #{ajuste_id}",
                "credito" if debe > 0 else "cargo",
                "anulacion_ajuste",
                haber if haber > 0 else 0,
                debe if debe > 0 else 0,
                "anulado",
                "ajuste_anulacion",
                ajuste_id,
                movimiento["metodo_pago"] or "",
                movimiento["comprobante"] or "",
                motivo_anulacion
            )
            recalcular_saldos_alumno(conn, movimiento["alumno_id"])

    if ajuste["liquidacion_ajuste_id"]:
        conn.execute("""
            UPDATE liquidacion_ajustes
            SET anulado=1
            WHERE id=?
        """, (ajuste["liquidacion_ajuste_id"],))

    registrar_auditoria(conn, "ajustes", "anular", "ajuste_manual", ajuste_id, motivo_anulacion)
    ANALYTICS_CACHE.clear()
    return ajuste

def filtros_analytics(args):
    hoy = datetime.now()
    desde = normalizar_fecha(args.get("desde")) or f"{hoy.year}-01-01"
    hasta = normalizar_fecha(args.get("hasta")) or hoy.strftime("%Y-%m-%d")
    profesor_id = validar_entero(args.get("profesor_id"))
    alumno_id = validar_entero(args.get("alumno_id"))
    tipo_clase_id = validar_entero(args.get("tipo_clase_id"))
    metodo_pago = (args.get("metodo_pago") or "").strip()
    estado = (args.get("estado") or "").strip()
    promocion_id = validar_entero(args.get("promocion_id"))

    if desde > hasta:
        desde, hasta = hasta, desde

    return {
        "desde": desde,
        "hasta": hasta,
        "profesor_id": profesor_id,
        "alumno_id": alumno_id,
        "tipo_clase_id": tipo_clase_id,
        "metodo_pago": metodo_pago,
        "estado": estado,
        "promocion_id": promocion_id
    }

def periodo_anterior(desde, hasta):
    inicio = datetime.strptime(desde, "%Y-%m-%d")
    fin = datetime.strptime(hasta, "%Y-%m-%d")
    dias = (fin - inicio).days + 1
    anterior_fin = inicio - timedelta(days=1)
    anterior_inicio = anterior_fin - timedelta(days=dias - 1)
    return anterior_inicio.strftime("%Y-%m-%d"), anterior_fin.strftime("%Y-%m-%d")

def variacion_porcentual(actual, anterior):
    actual = float(actual or 0)
    anterior = float(anterior or 0)
    if anterior == 0:
        return 100 if actual > 0 else 0
    return ((actual - anterior) / anterior) * 100

def filas_dict(filas):
    return [dict(fila) for fila in filas]

def analytics_cache_key(filtros):
    return json.dumps(filtros, sort_keys=True)

def calcular_analytics(conn, filtros):
    sincronizar_estado_cuenta_todos(conn)
    cache_key = analytics_cache_key(filtros)
    ahora = datetime.now()
    cache = ANALYTICS_CACHE.get(cache_key)
    if cache and (ahora - cache["fecha"]).total_seconds() < 60:
        return cache["datos"]

    desde = filtros["desde"]
    hasta = filtros["hasta"]
    anterior_desde, anterior_hasta = periodo_anterior(desde, hasta)

    filtro_mov = ["fecha BETWEEN ? AND ?", "anulado=0"]
    valores_mov = [desde, hasta]
    if filtros["alumno_id"]:
        filtro_mov.append("alumno_id=?")
        valores_mov.append(filtros["alumno_id"])
    if filtros["metodo_pago"]:
        filtro_mov.append("metodo_pago=?")
        valores_mov.append(filtros["metodo_pago"])
    where_mov = " AND ".join(filtro_mov)

    ingresos = conn.execute(f"""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE {where_mov} AND categoria='pago'
    """, valores_mov).fetchone()["total"]
    descuentos = conn.execute(f"""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE {where_mov} AND categoria IN ('promocion', 'bonificacion', 'ajuste_negativo')
    """, valores_mov).fetchone()["total"]
    ajustes_alumnos = conn.execute(f"""
        SELECT
            COALESCE(SUM(CASE WHEN categoria='ajuste_positivo' THEN debe ELSE 0 END), 0) AS cargos,
            COALESCE(SUM(CASE WHEN categoria='ajuste_negativo' THEN haber ELSE 0 END), 0) AS creditos
        FROM movimientos_cuenta
        WHERE {where_mov} AND categoria IN ('ajuste_positivo', 'ajuste_negativo', 'anulacion_ajuste')
    """, valores_mov).fetchone()
    ajustes_manuales = filas_dict(conn.execute("""
        SELECT categoria, signo, COUNT(*) AS cantidad, COALESCE(SUM(monto), 0) AS total
        FROM ajustes_manuales
        WHERE estado='activo' AND fecha BETWEEN ? AND ?
        GROUP BY categoria, signo
        ORDER BY total DESC
    """, (desde, hasta)).fetchall())
    ajustes_por_usuario = filas_dict(conn.execute("""
        SELECT COALESCE(NULLIF(usuario_creador_nombre, ''), 'Sin usuario') AS usuario,
               COUNT(*) AS cantidad,
               COALESCE(SUM(CASE WHEN signo='positivo' THEN monto ELSE -monto END), 0) AS impacto
        FROM ajustes_manuales
        WHERE estado='activo' AND fecha BETWEEN ? AND ?
        GROUP BY COALESCE(NULLIF(usuario_creador_nombre, ''), 'Sin usuario')
        ORDER BY ABS(impacto) DESC
        LIMIT 8
    """, (desde, hasta)).fetchall())
    deuda_total = conn.execute("""
        SELECT COALESCE(SUM(saldo), 0) AS total
        FROM (
            SELECT alumno_id, SUM(debe) - SUM(haber) AS saldo
            FROM movimientos_cuenta
            WHERE anulado=0
            GROUP BY alumno_id
            HAVING saldo > 0
        )
    """).fetchone()["total"]
    saldo_favor = conn.execute("""
        SELECT COALESCE(SUM(-saldo), 0) AS total
        FROM (
            SELECT alumno_id, SUM(debe) - SUM(haber) AS saldo
            FROM movimientos_cuenta
            WHERE anulado=0
            GROUP BY alumno_id
            HAVING saldo < 0
        )
    """).fetchone()["total"]
    deudores = conn.execute("""
        SELECT COUNT(*) AS total
        FROM (
            SELECT alumno_id, SUM(debe) - SUM(haber) AS saldo
            FROM movimientos_cuenta
            WHERE anulado=0
            GROUP BY alumno_id
            HAVING saldo > 0
        )
    """).fetchone()["total"]

    ingresos_anterior = conn.execute("""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE anulado=0 AND categoria='pago' AND fecha BETWEEN ? AND ?
    """, (anterior_desde, anterior_hasta)).fetchone()["total"]

    filtro_clases = ["date(clases.fecha) BETWEEN ? AND ?"]
    valores_clases = [desde, hasta]
    if filtros["profesor_id"]:
        filtro_clases.append("clases.profesor_id=?")
        valores_clases.append(filtros["profesor_id"])
    if filtros["tipo_clase_id"]:
        filtro_clases.append("clases.tipo_clase_id=?")
        valores_clases.append(filtros["tipo_clase_id"])
    if filtros["estado"]:
        filtro_clases.append("clases.estado=?")
        valores_clases.append(filtros["estado"])
    where_clases = " AND ".join(filtro_clases)

    clases_resumen = conn.execute(f"""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN clases.estado='cancelada' THEN 1 END) AS canceladas,
            COUNT(CASE WHEN clases.es_recupero=1 THEN 1 END) AS recuperos
        FROM clases
        WHERE {where_clases}
    """, valores_clases).fetchone()

    asistencia = conn.execute(f"""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN clase_alumnos.asistencia='presente' THEN 1 END) AS presentes,
            COUNT(CASE WHEN clase_alumnos.asistencia='ausente' THEN 1 END) AS ausentes,
            COUNT(CASE WHEN clase_alumnos.asistencia='recupera' THEN 1 END) AS recupera
        FROM clase_alumnos
        JOIN clases ON clase_alumnos.clase_id = clases.id
        WHERE {where_clases}
    """, valores_clases).fetchone()

    alumnos_activos = conn.execute("""
        SELECT COUNT(DISTINCT alumno_id) AS total
        FROM clase_alumnos
        JOIN clases ON clase_alumnos.clase_id = clases.id
        WHERE date(clases.fecha) BETWEEN ? AND ? AND clases.estado<>'cancelada'
    """, (desde, hasta)).fetchone()["total"]
    nuevos_alumnos = conn.execute("""
        SELECT COUNT(*) AS total
        FROM alumnos
        WHERE dia_inscripcion BETWEEN ? AND ?
    """, (desde, hasta)).fetchone()["total"]

    ingresos_mes = filas_dict(conn.execute(f"""
        SELECT substr(fecha, 1, 7) AS periodo, COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE {where_mov} AND categoria='pago'
        GROUP BY substr(fecha, 1, 7)
        ORDER BY periodo
    """, valores_mov).fetchall())
    deuda_mes = filas_dict(conn.execute("""
        SELECT substr(fecha, 1, 7) AS periodo, COALESCE(SUM(debe - haber), 0) AS total
        FROM movimientos_cuenta
        WHERE anulado=0 AND fecha BETWEEN ? AND ? AND estado<>'pagado'
        GROUP BY substr(fecha, 1, 7)
        ORDER BY periodo
    """, (desde, hasta)).fetchall())
    ingresos_metodo = filas_dict(conn.execute(f"""
        SELECT COALESCE(NULLIF(metodo_pago, ''), 'Sin definir') AS metodo, COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE {where_mov} AND categoria='pago'
        GROUP BY COALESCE(NULLIF(metodo_pago, ''), 'Sin definir')
        ORDER BY total DESC
    """, valores_mov).fetchall())

    clases_tipo = filas_dict(conn.execute(f"""
        SELECT tipos_clase.nombre AS tipo, COUNT(*) AS total
        FROM clases
        LEFT JOIN tipos_clase ON clases.tipo_clase_id = tipos_clase.id
        WHERE {where_clases}
        GROUP BY tipos_clase.nombre
        ORDER BY total DESC
    """, valores_clases).fetchall())
    actividad_dia = filas_dict(conn.execute(f"""
        SELECT strftime('%w', clases.fecha) AS dia, COUNT(*) AS total
        FROM clases
        WHERE {where_clases}
        GROUP BY strftime('%w', clases.fecha)
        ORDER BY dia
    """, valores_clases).fetchall())
    actividad_hora = filas_dict(conn.execute(f"""
        SELECT substr(clases.fecha, 12, 2) AS hora, COUNT(*) AS total
        FROM clases
        WHERE {where_clases}
        GROUP BY substr(clases.fecha, 12, 2)
        ORDER BY total DESC
        LIMIT 8
    """, valores_clases).fetchall())

    profesores = filas_dict(conn.execute("""
        SELECT profesores.id, profesores.nombre_apellido,
               COUNT(DISTINCT clases.id) AS clases,
               COUNT(DISTINCT clase_alumnos.alumno_id) AS alumnos,
               COUNT(CASE WHEN clases.estado='cancelada' THEN 1 END) AS canceladas,
               COUNT(CASE WHEN clases.es_recupero=1 THEN 1 END) AS recuperos,
               COUNT(CASE WHEN clase_alumnos.asistencia='presente' THEN 1 END) AS presentes,
               COUNT(clase_alumnos.id) AS asistencias
        FROM profesores
        LEFT JOIN clases ON clases.profesor_id = profesores.id AND date(clases.fecha) BETWEEN ? AND ?
        LEFT JOIN clase_alumnos ON clase_alumnos.clase_id = clases.id
        GROUP BY profesores.id
        ORDER BY clases DESC, alumnos DESC
    """, (desde, hasta)).fetchall())

    ingresos_profesor = filas_dict(conn.execute("""
        SELECT profesores.id, profesores.nombre_apellido,
               COALESCE(SUM(movimientos_cuenta.haber), 0) AS ingresos
        FROM profesores
        LEFT JOIN alumnos ON alumnos.tutor_profesor_id = profesores.id
        LEFT JOIN movimientos_cuenta ON movimientos_cuenta.alumno_id = alumnos.id
             AND movimientos_cuenta.categoria='pago'
             AND movimientos_cuenta.anulado=0
             AND movimientos_cuenta.fecha BETWEEN ? AND ?
        GROUP BY profesores.id
        ORDER BY ingresos DESC
        LIMIT 10
    """, (desde, hasta)).fetchall())

    promociones = filas_dict(conn.execute("""
        SELECT promociones.nombre,
               COUNT(promocion_usos.id) AS usos,
               COALESCE(SUM(promocion_usos.descuento), 0) AS impacto
        FROM promociones
        LEFT JOIN promocion_usos ON promocion_usos.promocion_id = promociones.id
             AND date(promocion_usos.fecha) BETWEEN ? AND ?
        WHERE promociones.eliminada=0
        GROUP BY promociones.id
        ORDER BY usos DESC, impacto DESC
        LIMIT 10
    """, (desde, hasta)).fetchall())
    promos_estado = conn.execute("""
        SELECT
            COUNT(CASE WHEN activa=1 AND eliminada=0 THEN 1 END) AS activas,
            COUNT(CASE WHEN fecha_fin IS NOT NULL AND fecha_fin<>'' AND fecha_fin<? AND eliminada=0 THEN 1 END) AS vencidas
        FROM promociones
    """, (datetime.now().strftime("%Y-%m-%d"),)).fetchone()

    recuperos = conn.execute("""
        SELECT
            COUNT(CASE WHEN estado='pendiente' THEN 1 END) AS pendientes,
            COUNT(CASE WHEN estado='realizado' THEN 1 END) AS realizados,
            COUNT(CASE WHEN estado='vencido' THEN 1 END) AS vencidos,
            COUNT(CASE WHEN gratuito=1 THEN 1 END) AS gratuitos,
            COUNT(CASE WHEN gratuito=0 THEN 1 END) AS pagos,
            COALESCE(SUM(costo_adicional), 0) AS impacto
        FROM recuperos
        WHERE date(fecha_creacion) BETWEEN ? AND ?
    """, (desde, hasta)).fetchone()
    recuperos_profesor = filas_dict(conn.execute("""
        SELECT profesores.nombre_apellido, COUNT(recuperos.id) AS total
        FROM recuperos
        LEFT JOIN profesores ON recuperos.profesor_id = profesores.id
        WHERE date(recuperos.fecha_creacion) BETWEEN ? AND ?
        GROUP BY profesores.id
        ORDER BY total DESC
        LIMIT 10
    """, (desde, hasta)).fetchall())
    reglas_comision_metricas = conn.execute("""
        SELECT
            COUNT(CASE WHEN estado='activa' AND archivada=0 THEN 1 END) AS activas,
            COUNT(*) AS total,
            COALESCE(AVG(NULLIF(porcentaje, 0)), 0) AS porcentaje_promedio
        FROM reglas_comision
        WHERE archivada=0
    """).fetchone()

    total_alumnos = conn.execute("SELECT COUNT(*) AS total FROM alumnos").fetchone()["total"]
    ticket_promedio = float(ingresos or 0) / max(int(alumnos_activos or 0), 1)
    asistencia_total = int(asistencia["total"] or 0)
    tasa_asistencia = (int(asistencia["presentes"] or 0) / asistencia_total * 100) if asistencia_total else 0
    tasa_mora = (int(deudores or 0) / max(int(total_alumnos or 0), 1)) * 100
    mrr = conn.execute("""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE anulado=0 AND categoria='pago' AND substr(fecha, 1, 7)=?
    """, (datetime.now().strftime("%Y-%m"),)).fetchone()["total"]

    ganancias_brutas = float(ingresos or 0)
    pagos_profesores = sum(
        calcular_liquidacion_profesor(conn, profesor, datetime.strptime(hasta, "%Y-%m-%d").year, datetime.strptime(hasta, "%Y-%m-%d").month)["totales"]["pago_profesor_final"]
        for profesor in conn.execute("SELECT * FROM profesores WHERE activo=1 OR activo IS NULL").fetchall()
    )
    ganancias_netas = ganancias_brutas - float(pagos_profesores or 0)

    alertas = []
    variacion_ingresos = variacion_porcentual(ingresos, ingresos_anterior)
    if variacion_ingresos < -15:
        alertas.append({"tipo": "danger", "titulo": "Caida de ingresos", "detalle": f"Los ingresos bajaron {abs(variacion_ingresos):.1f}% vs periodo anterior."})
    if tasa_mora > 25:
        alertas.append({"tipo": "warning", "titulo": "Morosidad alta", "detalle": f"{tasa_mora:.1f}% de los alumnos tienen saldo deudor."})
    if int(recuperos["pendientes"] or 0) > 10:
        alertas.append({"tipo": "warning", "titulo": "Muchos recuperos pendientes", "detalle": f"Hay {recuperos['pendientes']} recuperos pendientes."})
    if float(descuentos or 0) > float(ingresos or 0) * 0.2 and float(ingresos or 0) > 0:
        alertas.append({"tipo": "warning", "titulo": "Descuentos elevados", "detalle": "Los descuentos superan el 20% de lo cobrado."})
    if not alertas:
        alertas.append({"tipo": "success", "titulo": "Indicadores estables", "detalle": "No se detectaron alertas criticas en el periodo."})

    datos = {
        "filtros": filtros,
        "comparativa": {
            "anterior_desde": anterior_desde,
            "anterior_hasta": anterior_hasta,
            "ingresos_anterior": float(ingresos_anterior or 0),
            "variacion_ingresos": variacion_ingresos
        },
        "kpis": {
            "ingresos": float(ingresos or 0),
            "ingresos_anuales": float(conn.execute("SELECT COALESCE(SUM(haber), 0) AS total FROM movimientos_cuenta WHERE anulado=0 AND categoria='pago' AND substr(fecha, 1, 4)=?", (desde[:4],)).fetchone()["total"] or 0),
            "ganancias_brutas": ganancias_brutas,
            "ganancias_netas": ganancias_netas,
            "pagos_profesores": float(pagos_profesores or 0),
            "descuentos": float(descuentos or 0),
            "ajustes_manuales": float((ajustes_alumnos["cargos"] or 0) - (ajustes_alumnos["creditos"] or 0)),
            "ajustes_cargos": float(ajustes_alumnos["cargos"] or 0),
            "ajustes_creditos": float(ajustes_alumnos["creditos"] or 0),
            "deuda_total": float(deuda_total or 0),
            "saldo_favor": float(saldo_favor or 0),
            "morosidad": tasa_mora,
            "mrr": float(mrr or 0),
            "ticket_promedio": ticket_promedio,
            "ingreso_promedio_profesor": float(ingresos or 0) / max(len(profesores), 1),
            "alumnos_activos": int(alumnos_activos or 0),
            "nuevos_alumnos": int(nuevos_alumnos or 0),
            "tasa_asistencia": tasa_asistencia,
            "clases": int(clases_resumen["total"] or 0),
            "canceladas": int(clases_resumen["canceladas"] or 0),
            "recuperos": int(clases_resumen["recuperos"] or 0)
        },
        "series": {
            "ingresos_mes": ingresos_mes,
            "deuda_mes": deuda_mes,
            "ingresos_metodo": ingresos_metodo,
            "clases_tipo": clases_tipo,
            "actividad_dia": actividad_dia,
            "actividad_hora": actividad_hora
        },
        "profesores": profesores,
        "ingresos_profesor": ingresos_profesor,
        "promociones": promociones,
        "promos_estado": dict(promos_estado),
        "recuperos": dict(recuperos),
        "recuperos_profesor": recuperos_profesor,
        "comisiones": dict(reglas_comision_metricas),
        "ajustes": ajustes_manuales,
        "ajustes_por_usuario": ajustes_por_usuario,
        "alertas": alertas
    }
    ANALYTICS_CACHE[cache_key] = {"fecha": ahora, "datos": datos}
    return datos

def calcular_pago_profesor_clase(clase):
    precio_normal = float(clase["precio_clase"] or 0)
    tipo = clase["tipo_clase"] or "individual"

    if tipo == "individual":
        porcentaje = float(clase["porcentaje_individual"] or 50)
    elif tipo == "duo":
        porcentaje = float(clase["porcentaje_duo"] or clase["porcentaje_grupal"] or 40)
    else:
        porcentaje = float(clase["porcentaje_grupal"] or 40)

    pago_profesor = precio_normal * porcentaje / 100
    ganancia = precio_normal - pago_profesor

    return {
        "precio_normal": precio_normal,
        "porcentaje": porcentaje,
        "pago_profesor": pago_profesor,
        "ganancia": ganancia
    }

def porcentaje_profesor_por_tipo(profesor, tipo_clase):
    tipo = (tipo_clase or "individual").lower()
    if tipo == "individual":
        return float(profesor["porcentaje_individual"] or 50)
    if tipo == "duo":
        return float(profesor["porcentaje_duo"] or profesor["porcentaje_grupal"] or 40)
    return float(profesor["porcentaje_grupal"] or 40)

def normalizar_modalidad_comision(valor):
    valor = (valor or "porcentaje_fijo").strip()
    return valor if valor in MODALIDADES_COMISION else "porcentaje_fijo"

def normalizar_base_comision(valor):
    valor = (valor or "monto_real").strip()
    return valor if valor in BASES_COMISION else "monto_real"

def normalizar_estado_regla_comision(valor):
    valor = (valor or "activa").strip()
    return valor if valor in ESTADOS_REGLA_COMISION else "activa"

def normalizar_aplica_recupero(valor):
    valor = (valor or "todos").strip()
    return valor if valor in ["todos", "solo_recupero", "no_recupero"] else "todos"

def regla_comision_vigente(regla, fecha_ref):
    if not regla or int(regla["archivada"] or 0) == 1:
        return False
    estado = normalizar_estado_regla_comision(regla["estado"])
    if estado in ["inactiva", "archivada", "vencida"]:
        return False
    fecha_ref = (fecha_ref or datetime.now().strftime("%Y-%m-%d"))[:10]
    if regla["fecha_inicio"] and regla["fecha_inicio"] > fecha_ref:
        return False
    if regla["fecha_fin"] and regla["fecha_fin"] < fecha_ref:
        return False
    return True

def cantidad_clases_profesor_mes(conn, profesor_id, anio, mes):
    fila = conn.execute("""
        SELECT COUNT(*) AS total
        FROM clases
        WHERE profesor_id=? AND estado<>'cancelada' AND fecha LIKE ?
    """, (profesor_id, f"{anio}-{mes:02d}-%")).fetchone()
    return int(fila["total"] or 0)

def regla_comision_coincide(regla, contexto):
    if regla["tipo_clase_id"] and int(regla["tipo_clase_id"]) != int(contexto.get("tipo_clase_id") or 0):
        return False
    alumnos = int(contexto.get("alumnos") or 0)
    presentes = int(contexto.get("presentes") or 0)
    monto_real = float(contexto.get("ingreso_real") or 0)
    if regla["min_alumnos"] is not None and alumnos < int(regla["min_alumnos"] or 0):
        return False
    if regla["max_alumnos"] is not None and alumnos > int(regla["max_alumnos"] or 0):
        return False
    if regla["min_presentes"] is not None and presentes < int(regla["min_presentes"] or 0):
        return False
    if regla["max_presentes"] is not None and presentes > int(regla["max_presentes"] or 0):
        return False
    if regla["min_clases_mes"] is not None and int(contexto.get("clases_mes") or 0) < int(regla["min_clases_mes"] or 0):
        return False
    if regla["max_clases_mes"] is not None and int(contexto.get("clases_mes") or 0) > int(regla["max_clases_mes"] or 0):
        return False
    if regla["min_monto"] is not None and monto_real < float(regla["min_monto"] or 0):
        return False
    if regla["max_monto"] is not None and monto_real > float(regla["max_monto"] or 0):
        return False
    aplica_recupero = normalizar_aplica_recupero(regla["aplica_recupero"])
    es_recupero = bool(contexto.get("es_recupero"))
    if aplica_recupero == "solo_recupero" and not es_recupero:
        return False
    if aplica_recupero == "no_recupero" and es_recupero:
        return False
    if int(regla["requiere_promocion"] or 0) == 1 and not contexto.get("tiene_promocion"):
        return False
    return True

def prioridad_tipo_regla(regla):
    modalidad = normalizar_modalidad_comision(regla["modalidad"])
    if modalidad == "manual_excepcional":
        return 500
    if regla["fecha_fin"] or modalidad == "temporal":
        return 400
    if regla["tipo_clase_id"]:
        return 300
    if regla["profesor_id"]:
        return 200
    return 100

def obtener_regla_comision(conn, profesor, contexto):
    fecha_ref = contexto.get("fecha", datetime.now().strftime("%Y-%m-%d"))[:10]
    reglas = conn.execute("""
        SELECT *
        FROM reglas_comision
        WHERE archivada=0
          AND (profesor_id=? OR profesor_id IS NULL)
        ORDER BY prioridad DESC, id DESC
    """, (profesor["id"],)).fetchall()
    candidatas = [
        regla for regla in reglas
        if regla_comision_vigente(regla, fecha_ref) and regla_comision_coincide(regla, contexto)
    ]
    if candidatas:
        candidatas.sort(key=lambda r: (prioridad_tipo_regla(r), int(r["prioridad"] or 0), int(r["id"] or 0)), reverse=True)
        return candidatas[0]
    return None

def base_comision_por_tipo(base_calculo, contexto):
    base_calculo = normalizar_base_comision(base_calculo)
    if base_calculo == "monto_esperado":
        return float(contexto.get("ingreso_esperado") or 0)
    if base_calculo == "antes_promociones":
        return float(contexto.get("ingreso_esperado") or 0)
    if base_calculo == "despues_promociones":
        return float(contexto.get("ingreso_real") or 0)
    if base_calculo == "manual":
        return float(contexto.get("base_manual") or contexto.get("ingreso_real") or 0)
    return float(contexto.get("base_profesor") if contexto.get("base_profesor") is not None else contexto.get("ingreso_real") or 0)

def fallback_regla_comision(conn, profesor, contexto):
    config = obtener_configuracion(conn)
    tipo = (contexto.get("tipo_clase") or "individual").lower()
    if tipo == "individual":
        porcentaje = validar_precio(config.get("comision_default_individual") or profesor["porcentaje_individual"] or 50)
    elif tipo == "duo":
        porcentaje = validar_precio(config.get("comision_default_duo") or profesor["porcentaje_duo"] or 40)
    else:
        porcentaje = validar_precio(config.get("comision_default_grupal") or profesor["porcentaje_grupal"] or 40)
    return {
        "id": None,
        "nombre": f"Default {tipo}",
        "modalidad": "porcentaje_fijo",
        "base_calculo": config.get("comision_base_default") or "monto_real",
        "porcentaje": porcentaje,
        "monto": 0,
        "observaciones": "Regla global por defecto"
    }

def calcular_comision_profesor(conn, profesor, contexto):
    regla = obtener_regla_comision(conn, profesor, contexto)
    regla_usada = regla if regla else fallback_regla_comision(conn, profesor, contexto)
    modalidad = normalizar_modalidad_comision(regla_usada["modalidad"])
    base = base_comision_por_tipo(regla_usada["base_calculo"], contexto)
    porcentaje = min(validar_precio(regla_usada["porcentaje"]), 100)
    monto = validar_precio(regla_usada["monto"])
    alumnos = int(contexto.get("alumnos") or 0)
    presentes = int(contexto.get("presentes") or alumnos or 0)

    if contexto.get("es_recupero") and not contexto.get("recupero_profesor_cobra", True):
        pago = 0
        motivo = "Recupero configurado sin pago al profesor"
    elif modalidad == "monto_fijo_clase":
        pago = monto
        motivo = f"Monto fijo por clase ${monto:.2f}"
    elif modalidad == "monto_fijo_alumno":
        pago = monto * max(presentes, alumnos, 1)
        motivo = f"Monto fijo por alumno ${monto:.2f}"
    elif modalidad in ["porcentaje_variable_alumnos", "porcentaje_tipo_clase", "escalonada", "temporal", "manual_excepcional", "porcentaje_fijo"]:
        pago = base * porcentaje / 100
        motivo = f"{porcentaje:.2f}% sobre {regla_usada['base_calculo']}"
    else:
        pago = base * porcentaje / 100
        motivo = f"{porcentaje:.2f}% sobre {regla_usada['base_calculo']}"

    return {
        "regla_id": regla_usada["id"],
        "regla_nombre": regla_usada["nombre"],
        "modalidad": modalidad,
        "base_calculo": regla_usada["base_calculo"],
        "base": base,
        "porcentaje": porcentaje,
        "monto": monto,
        "pago_profesor": max(pago, 0),
        "motivo": motivo,
        "observaciones": regla_usada["observaciones"] if "observaciones" in regla_usada.keys() else ""
    }

def obtener_o_crear_liquidacion(conn, profesor_id, anio, mes):
    existente = conn.execute("""
        SELECT *
        FROM liquidaciones_profesores
        WHERE profesor_id=? AND anio=? AND mes=?
    """, (profesor_id, anio, mes)).fetchone()

    if existente:
        return existente

    conn.execute("""
        INSERT OR IGNORE INTO liquidaciones_profesores (profesor_id, anio, mes, estado)
        VALUES (?, ?, ?, 'pendiente')
    """, (profesor_id, anio, mes))

    return conn.execute("""
        SELECT *
        FROM liquidaciones_profesores
        WHERE profesor_id=? AND anio=? AND mes=?
    """, (profesor_id, anio, mes)).fetchone()

def signo_ajuste(tipo):
    if tipo in ["descuento_profesor", "correccion_administrativa_negativa", "clase_no_reconocida"]:
        return -1
    return 1

def contar_clases_alumno_mes(conn, alumno_id, anio, mes):
    fila = conn.execute("""
        SELECT COUNT(*) AS total
        FROM clase_alumnos
        JOIN clases ON clase_alumnos.clase_id = clases.id
        WHERE clase_alumnos.alumno_id=?
          AND clases.estado<>'cancelada'
          AND clases.fecha LIKE ?
    """, (alumno_id, f"{anio}-{mes:02d}-%")).fetchone()
    return max(int(fila["total"] or 0), 1)

def calcular_liquidacion_profesor(conn, profesor, anio, mes, tipo_clase=""):
    liquidacion = obtener_o_crear_liquidacion(conn, profesor["id"], anio, mes)
    condiciones = [
        "clases.profesor_id=?",
        "clases.fecha LIKE ?"
    ]
    valores = [profesor["id"], f"{anio}-{mes:02d}-%"]

    if tipo_clase:
        condiciones.append("tipos_clase.nombre=?")
        valores.append(tipo_clase)

    clases = conn.execute("""
        SELECT clases.*, tipos_clase.nombre AS tipo_clase,
               recuperos.afecta_liquidacion AS recupero_afecta_liquidacion,
               recuperos.profesor_cobra AS recupero_profesor_cobra,
               recuperos.costo_adicional AS recupero_costo_adicional
        FROM clases
        LEFT JOIN tipos_clase ON clases.tipo_clase_id = tipos_clase.id
        LEFT JOIN recuperos ON clases.recupero_id = recuperos.id
        WHERE """ + " AND ".join(condiciones) + """
        ORDER BY clases.fecha
    """, valores).fetchall()

    detalle_clases = []
    total_ingreso_real = 0
    total_ingreso_esperado = 0
    total_profesor = 0
    total_academia = 0
    total_presentes = 0
    total_ausentes = 0
    total_pagaron = 0
    total_deben = 0

    for clase in clases:
        alumnos = conn.execute("""
            SELECT alumnos.id, alumnos.apellido_nombre, clase_alumnos.asistencia
            FROM clase_alumnos
            JOIN alumnos ON clase_alumnos.alumno_id = alumnos.id
            WHERE clase_alumnos.clase_id=?
            ORDER BY alumnos.apellido_nombre
        """, (clase["id"],)).fetchall()

        porcentaje = porcentaje_profesor_por_tipo(profesor, clase["tipo_clase"])
        ingreso_real = 0
        ingreso_esperado = 0
        base_profesor = 0
        pagaron = 0
        deben = 0
        presentes = 0
        ausentes = 0
        alumnos_deben = []
        tiene_promocion = False

        if clase["estado"] == "cancelada":
            detalle_clases.append({
                "id": clase["id"],
                "fecha": clase["fecha"],
                "tipo_clase": clase["tipo_clase"],
                "estado": clase["estado"],
                "porcentaje": porcentaje,
                "alumnos": len(alumnos),
                "presentes": 0,
                "ausentes": 0,
                "pagaron": 0,
                "deben": 0,
                "ingreso_real": 0,
                "base_comision": 0,
                "ingreso_esperado": 0,
                "diferencia": 0,
                "pago_profesor": 0,
                "ganancia_academia": 0,
                "regla_comision": "Sin liquidar",
                "regla_comision_id": None,
                "modalidad_comision": "",
                "base_calculo_comision": "",
                "motivo_comision": "Clase cancelada",
                "alumnos_deben": []
            })
            continue

        for alumno in alumnos:
            asistencia = alumno["asistencia"] or "pendiente"
            if asistencia in ["presente", "recupera"]:
                presentes += 1
            elif asistencia == "ausente":
                ausentes += 1

            cuota = conn.execute("""
                SELECT pagos_alumnos.*, promociones.afecta_profesor AS promo_afecta_profesor
                FROM pagos_alumnos
                LEFT JOIN promociones ON pagos_alumnos.promocion_id = promociones.id
                WHERE pagos_alumnos.alumno_id=? AND anio=? AND mes=?
                ORDER BY pagos_alumnos.id DESC
                LIMIT 1
            """, (alumno["id"], anio, mes)).fetchone()

            divisor = contar_clases_alumno_mes(conn, alumno["id"], anio, mes)
            if cuota:
                if cuota["promocion_id"]:
                    tiene_promocion = True
                esperado_parcial = float(cuota["monto_normal"] or 0) / divisor
                ingreso_esperado += esperado_parcial
                monto_real_pagado = float(cuota["monto_real_pagado"] or 0)
                if cuota["estado"] == "pagado":
                    real_parcial = (monto_real_pagado or float(cuota["monto_pagado"] or 0)) / divisor
                    ingreso_real += real_parcial
                    base_profesor += esperado_parcial if int(cuota["promo_afecta_profesor"] or 0) == 0 and float(cuota["descuento"] or 0) > 0 else real_parcial
                    pagaron += 1
                elif monto_real_pagado > 0:
                    real_parcial = monto_real_pagado / divisor
                    ingreso_real += real_parcial
                    base_profesor += esperado_parcial if int(cuota["promo_afecta_profesor"] or 0) == 0 and float(cuota["descuento"] or 0) > 0 else real_parcial
                    deben += 1
                    alumnos_deben.append(alumno["apellido_nombre"])
                else:
                    deben += 1
                    alumnos_deben.append(alumno["apellido_nombre"])
            else:
                deben += 1
                alumnos_deben.append(alumno["apellido_nombre"])

        if int(clase["es_recupero"] or 0) == 1 and int(clase["recupero_afecta_liquidacion"] or 1) == 0:
            base_profesor = 0
        elif int(clase["es_recupero"] or 0) == 1 and int(clase["recupero_profesor_cobra"] or 0) == 1:
            base_profesor = max(base_profesor, float(profesor["precio_clase"] or 0), float(clase["recupero_costo_adicional"] or 0))

        contexto_comision = {
            "fecha": clase["fecha"],
            "tipo_clase": clase["tipo_clase"],
            "tipo_clase_id": clase["tipo_clase_id"],
            "alumnos": len(alumnos),
            "presentes": presentes,
            "ingreso_real": ingreso_real,
            "ingreso_esperado": ingreso_esperado,
            "base_profesor": base_profesor,
            "tiene_promocion": tiene_promocion,
            "es_recupero": int(clase["es_recupero"] or 0) == 1,
            "recupero_profesor_cobra": int(clase["recupero_profesor_cobra"] or 1) == 1,
            "clases_mes": cantidad_clases_profesor_mes(conn, profesor["id"], anio, mes)
        }
        comision = calcular_comision_profesor(conn, profesor, contexto_comision)
        porcentaje = comision["porcentaje"]
        pago_profesor = comision["pago_profesor"]
        ganancia_academia = ingreso_real - pago_profesor
        diferencia = ingreso_esperado - ingreso_real

        total_ingreso_real += ingreso_real
        total_ingreso_esperado += ingreso_esperado
        total_profesor += pago_profesor
        total_academia += ganancia_academia
        total_presentes += presentes
        total_ausentes += ausentes
        total_pagaron += pagaron
        total_deben += deben

        detalle_clases.append({
            "id": clase["id"],
            "fecha": clase["fecha"],
            "tipo_clase": clase["tipo_clase"],
            "estado": clase["estado"],
            "porcentaje": porcentaje,
            "alumnos": len(alumnos),
            "presentes": presentes,
            "ausentes": ausentes,
            "pagaron": pagaron,
            "deben": deben,
            "ingreso_real": ingreso_real,
            "base_profesor": base_profesor,
            "base_comision": comision["base"],
            "regla_comision": comision["regla_nombre"],
            "regla_comision_id": comision["regla_id"],
            "modalidad_comision": comision["modalidad"],
            "base_calculo_comision": comision["base_calculo"],
            "motivo_comision": comision["motivo"],
            "ingreso_esperado": ingreso_esperado,
            "diferencia": diferencia,
            "pago_profesor": pago_profesor,
            "ganancia_academia": ganancia_academia,
            "alumnos_deben": alumnos_deben
        })

    ajustes = conn.execute("""
        SELECT *
        FROM liquidacion_ajustes
        WHERE liquidacion_id=? AND COALESCE(anulado, 0)=0
        ORDER BY fecha DESC, id DESC
    """, (liquidacion["id"],)).fetchall()

    total_ajustes = sum(signo_ajuste(a["tipo"]) * float(a["monto"] or 0) for a in ajustes)
    total_profesor_final = total_profesor + total_ajustes

    return {
        "liquidacion": liquidacion,
        "profesor": profesor,
        "clases": detalle_clases,
        "ajustes": ajustes,
        "totales": {
            "clases": len(detalle_clases),
            "presentes": total_presentes,
            "ausentes": total_ausentes,
            "pagaron": total_pagaron,
            "deben": total_deben,
            "ingreso_real": total_ingreso_real,
            "ingreso_esperado": total_ingreso_esperado,
            "diferencia": total_ingreso_esperado - total_ingreso_real,
            "pago_profesor": total_profesor,
            "ajustes": total_ajustes,
            "pago_profesor_final": total_profesor_final,
            "ganancia_academia": total_academia - total_ajustes
        }
    }

def resumen_financiero(conn):
    sincronizar_estado_cuenta_todos(conn)
    ingresos_cuotas = conn.execute("""
        SELECT COALESCE(SUM(haber), 0) as total
        FROM movimientos_cuenta
        WHERE categoria='pago' AND anulado=0
    """).fetchone()["total"]

    ingresos_matriculas = conn.execute("""
        SELECT COALESCE(SUM(debe), 0) as total
        FROM movimientos_cuenta
        WHERE categoria='matricula_anual' AND anulado=0
    """).fetchone()["total"]

    clases = conn.execute("""
        SELECT clases.*, profesores.precio_clase, profesores.porcentaje_individual,
               profesores.porcentaje_duo, profesores.porcentaje_grupal,
               tipos_clase.nombre as tipo_clase
        FROM clases
        LEFT JOIN profesores ON clases.profesor_id = profesores.id
        LEFT JOIN tipos_clase ON clases.tipo_clase_id = tipos_clase.id
        WHERE clases.estado<>'cancelada'
    """).fetchall()

    pagos_profesores = sum(calcular_pago_profesor_clase(c)["pago_profesor"] for c in clases)
    ingresos = float(ingresos_cuotas or 0)
    deudores = conn.execute("""
        SELECT COUNT(*) AS total
        FROM (
            SELECT alumno_id, SUM(debe) - SUM(haber) AS saldo
            FROM movimientos_cuenta
            WHERE anulado=0
            GROUP BY alumno_id
            HAVING saldo > 0
        )
    """).fetchone()["total"]
    deuda_total = conn.execute("""
        SELECT COALESCE(SUM(saldo), 0) AS total
        FROM (
            SELECT alumno_id, SUM(debe) - SUM(haber) AS saldo
            FROM movimientos_cuenta
            WHERE anulado=0
            GROUP BY alumno_id
            HAVING saldo > 0
        )
    """).fetchone()["total"]
    saldo_favor = conn.execute("""
        SELECT COALESCE(SUM(-saldo), 0) AS total
        FROM (
            SELECT alumno_id, SUM(debe) - SUM(haber) AS saldo
            FROM movimientos_cuenta
            WHERE anulado=0
            GROUP BY alumno_id
            HAVING saldo < 0
        )
    """).fetchone()["total"]
    descuentos = conn.execute("""
        SELECT COALESCE(SUM(haber), 0) AS total
        FROM movimientos_cuenta
        WHERE categoria IN ('promocion', 'bonificacion', 'ajuste_negativo') AND anulado=0
    """).fetchone()["total"]
    ajustes_manuales = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN categoria='ajuste_positivo' THEN debe ELSE 0 END), 0) AS cargos,
            COALESCE(SUM(CASE WHEN categoria='ajuste_negativo' THEN haber ELSE 0 END), 0) AS creditos
        FROM movimientos_cuenta
        WHERE categoria IN ('ajuste_positivo', 'ajuste_negativo') AND anulado=0
    """).fetchone()

    return {
        "total_clases": len(clases),
        "ingresos": ingresos,
        "ingresos_cuotas": float(ingresos_cuotas or 0),
        "ingresos_matriculas": float(ingresos_matriculas or 0),
        "pagos_profesores": pagos_profesores,
        "ganancia": ingresos - pagos_profesores,
        "alumnos_deudores": deudores,
        "deuda_total": float(deuda_total or 0),
        "saldo_a_favor_total": float(saldo_favor or 0),
        "descuentos": float(descuentos or 0),
        "ajustes_manuales": float((ajustes_manuales["cargos"] or 0) - (ajustes_manuales["creditos"] or 0))
    }

def alertas_dashboard(conn):
    actualizar_vencimientos_recuperos(conn)
    sincronizar_estado_cuenta_todos(conn)
    hoy = datetime.now()
    anio_actual = hoy.year
    mes_actual = hoy.month

    cuotas_vencidas = conn.execute("""
        SELECT COUNT(*) AS cantidad, COALESCE(SUM(debe - haber), 0) AS total
        FROM movimientos_cuenta
        WHERE anulado=0
          AND categoria IN ('cuota_mensual', 'recupero_pago', 'ajuste_positivo')
          AND estado<>'pagado'
          AND fecha <= ?
    """, (hoy.strftime("%Y-%m-%d"),)).fetchone()

    matriculas_pendientes = conn.execute("""
        SELECT COUNT(*) AS cantidad, COALESCE(SUM(debe - haber), 0) AS total
        FROM movimientos_cuenta
        WHERE anulado=0
          AND categoria='matricula_anual'
          AND estado<>'pagado'
          AND fecha <= ?
    """, (hoy.strftime("%Y-%m-%d"),)).fetchone()

    clases_por_recuperar = conn.execute("""
        SELECT COUNT(*) AS cantidad
        FROM recuperos
        WHERE estado IN ('pendiente', 'programado')
    """).fetchone()

    asistencia_pendiente = conn.execute("""
        SELECT COUNT(*) AS cantidad
        FROM clase_alumnos
        JOIN clases ON clase_alumnos.clase_id = clases.id
        WHERE clases.fecha <= ?
          AND clases.estado<>'cancelada'
          AND (clase_alumnos.asistencia='pendiente' OR clase_alumnos.asistencia IS NULL)
    """, (hoy.strftime("%Y-%m-%dT%H:%M"),)).fetchone()

    profesores_con_clases = conn.execute("""
        SELECT COUNT(DISTINCT profesores.id) AS cantidad
        FROM profesores
        JOIN clases ON clases.profesor_id = profesores.id
        WHERE clases.estado<>'cancelada'
    """).fetchone()

    return {
        "cuotas_vencidas": {
            "cantidad": cuotas_vencidas["cantidad"] or 0,
            "total": float(cuotas_vencidas["total"] or 0)
        },
        "matriculas_pendientes": {
            "cantidad": matriculas_pendientes["cantidad"] or 0,
            "total": float(matriculas_pendientes["total"] or 0)
        },
        "clases_por_recuperar": clases_por_recuperar["cantidad"] or 0,
        "asistencia_pendiente": asistencia_pendiente["cantidad"] or 0,
        "profesores_con_pagos": profesores_con_clases["cantidad"] or 0
    }

def filtros_reporte_pagos(args):
    anio = validar_entero(args.get("anio"))
    mes = validar_entero(args.get("mes"))
    alumno_id = validar_entero(args.get("alumno_id"))
    estado = args.get("estado") if args.get("estado") in ["pagado", "pendiente", "parcial"] else ""

    if mes and (mes < 1 or mes > 12):
        mes = None

    return {
        "anio": anio,
        "mes": mes,
        "alumno_id": alumno_id,
        "estado": estado
    }

def obtener_reporte_pagos(conn, filtros):
    condiciones_cuotas = []
    valores_cuotas = []
    condiciones_matriculas = []
    valores_matriculas = []

    if filtros["anio"]:
        condiciones_cuotas.append("pagos_alumnos.anio=?")
        valores_cuotas.append(filtros["anio"])
        condiciones_matriculas.append("matriculas.anio=?")
        valores_matriculas.append(filtros["anio"])

    if filtros["mes"]:
        condiciones_cuotas.append("pagos_alumnos.mes=?")
        valores_cuotas.append(filtros["mes"])

    if filtros["alumno_id"]:
        condiciones_cuotas.append("pagos_alumnos.alumno_id=?")
        valores_cuotas.append(filtros["alumno_id"])
        condiciones_matriculas.append("matriculas.alumno_id=?")
        valores_matriculas.append(filtros["alumno_id"])

    if filtros["estado"]:
        condiciones_cuotas.append("pagos_alumnos.estado=?")
        valores_cuotas.append(filtros["estado"])
        condiciones_matriculas.append("matriculas.estado=?")
        valores_matriculas.append(filtros["estado"])

    where_cuotas = "WHERE " + " AND ".join(condiciones_cuotas) if condiciones_cuotas else ""
    where_matriculas = "WHERE " + " AND ".join(condiciones_matriculas) if condiciones_matriculas else ""

    cuotas = conn.execute(f"""
        SELECT pagos_alumnos.*, alumnos.apellido_nombre,
               COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) as promocion
        FROM pagos_alumnos
        LEFT JOIN alumnos ON pagos_alumnos.alumno_id = alumnos.id
        LEFT JOIN promociones ON pagos_alumnos.promocion_id = promociones.id
        {where_cuotas}
        ORDER BY pagos_alumnos.anio DESC, pagos_alumnos.mes DESC, alumnos.apellido_nombre
    """, valores_cuotas).fetchall()

    matriculas = conn.execute(f"""
        SELECT matriculas.*, alumnos.apellido_nombre,
               COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) as promocion
        FROM matriculas
        LEFT JOIN alumnos ON matriculas.alumno_id = alumnos.id
        LEFT JOIN promociones ON matriculas.promocion_id = promociones.id
        {where_matriculas}
        ORDER BY matriculas.anio DESC, alumnos.apellido_nombre
    """, valores_matriculas).fetchall()

    total_ingresado = sum(float(p["monto_pagado"] or 0) for p in cuotas if p["estado"] == "pagado")
    total_ingresado += sum(float(m["monto_pagado"] or 0) for m in matriculas if m["estado"] == "pagado")
    total_pendiente = sum(float(p["monto_pagado"] or 0) for p in cuotas if p["estado"] != "pagado")
    total_pendiente += sum(float(m["monto_pagado"] or 0) for m in matriculas if m["estado"] != "pagado")
    total_descuentos = sum(float(p["descuento"] or 0) for p in cuotas)
    total_descuentos += sum(float(m["descuento"] or 0) for m in matriculas)

    return {
        "cuotas": cuotas,
        "matriculas": matriculas,
        "resumen": {
            "total_ingresado": total_ingresado,
            "total_pendiente": total_pendiente,
            "total_descuentos": total_descuentos,
            "cantidad_cuotas": len(cuotas),
            "cantidad_matriculas": len(matriculas)
        }
    }

def condiciones_fecha_clases(filtros):
    condiciones = []
    valores = []

    if filtros["anio"] and filtros["mes"]:
        condiciones.append("clases.fecha LIKE ?")
        valores.append(f"{filtros['anio']}-{filtros['mes']:02d}-%")
    elif filtros["anio"]:
        condiciones.append("clases.fecha LIKE ?")
        valores.append(f"{filtros['anio']}-%")

    return condiciones, valores

def normalizar_rol(valor):
    valor = (valor or "").strip().lower()
    if valor in ["comun", "administrativo", "recepción"]:
        return "recepcion"
    return valor if valor in ROLES else "recepcion"

def usuario_actual():
    if not session.get("usuario_id"):
        return None
    return {
        "id": session["usuario_id"],
        "nombre": session["usuario_nombre"],
        "rol": normalizar_rol(session["usuario_rol"]),
        "rol_nombre": ROLE_LABELS.get(normalizar_rol(session["usuario_rol"]), session["usuario_rol"]),
        "profesor_id": session.get("profesor_id")
    }

def permisos_usuario_actual():
    if not session.get("usuario_id"):
        return set()
    rol = normalizar_rol(session.get("usuario_rol"))
    try:
        conn = get_conn()
        usuario = conn.execute("SELECT activo, rol FROM usuarios WHERE id=?", (session["usuario_id"],)).fetchone()
        if not usuario or int(usuario["activo"] or 0) == 0:
            conn.close()
            return set()
        rol = normalizar_rol(usuario["rol"])
        permisos = {
            fila["permiso_codigo"]
            for fila in conn.execute("""
                SELECT permiso_codigo
                FROM rol_permisos
                WHERE rol_codigo=?
            """, (rol,)).fetchall()
        }
        conn.close()
        return permisos
    except sqlite3.Error:
        return set(DEFAULT_ROLE_PERMISSIONS.get(rol, []))

def tiene_permiso(permiso):
    return permiso in permisos_usuario_actual()

def puede(permiso):
    return tiene_permiso(permiso)

def profesor_id_usuario_actual(conn=None):
    if normalizar_rol(session.get("usuario_rol")) != "profesor":
        return None
    profesor_id = validar_entero(session.get("profesor_id"))
    if profesor_id:
        return profesor_id
    cerrar = False
    if conn is None:
        conn = get_conn()
        cerrar = True
    profesor = conn.execute("""
        SELECT id
        FROM profesores
        WHERE lower(nombre_apellido)=lower(?)
        LIMIT 1
    """, (session.get("usuario_nombre") or "",)).fetchone()
    if cerrar:
        conn.close()
    return profesor["id"] if profesor else None

def puede_modificar_asistencia_clase(conn, clase_id):
    if not tiene_permiso("asistencia.editar"):
        return False, "Sin permiso"
    if normalizar_rol(session.get("usuario_rol")) != "profesor":
        return True, ""
    profesor_id = profesor_id_usuario_actual(conn)
    clase = conn.execute("SELECT profesor_id, fecha FROM clases WHERE id=?", (clase_id,)).fetchone()
    if not clase or not profesor_id or int(clase["profesor_id"] or 0) != int(profesor_id):
        return False, "La clase no pertenece a tu calendario."
    fecha_clase = (clase["fecha"] or "")[:10]
    if fecha_clase != datetime.now().strftime("%Y-%m-%d"):
        return False, "Los profesores solo pueden modificar asistencia del dia actual."
    return True, ""

def puede_gestionar_clases():
    return tiene_permiso("clases.crear") or tiene_permiso("clases.editar")

def puede_ver_pagos():
    return tiene_permiso("caja.ver")

def puede_cambiar_asistencia():
    return tiene_permiso("asistencia.editar")

def ruta_inicio_por_rol(rol):
    rol = normalizar_rol(rol)
    if rol == "admin":
        return "/"
    if rol == "recepcion":
        return "/caja"
    if rol == "profesor":
        return "/clases"
    return "/login"

ENDPOINT_PERMISSIONS = {
    "dashboard": "dashboard.ver",
    "caja": "caja.ver",
    "estadisticas": "estadisticas.ver",
    "exportar_estadisticas_csv": "estadisticas.exportar",
    "reporte_estadisticas": "estadisticas.exportar",
    "backup_base_datos": "backup.descargar",
    "auditoria": "auditoria.ver",
    "usuarios": "usuarios.ver",
    "agregar_usuario": "usuarios.crear",
    "eliminar_usuario": "usuarios.eliminar",
    "cambiar_rol_usuario": "usuarios.editar",
    "bloquear_usuario": "usuarios.editar",
    "guardar_permisos_rol": "roles.editar",
    "profesores": "profesores.ver",
    "agregar_profesor": "profesores.crear",
    "editar_profesor": "profesores.editar",
    "eliminar_profesor": "profesores.eliminar",
    "guardar_comisiones_globales": "comisiones.editar",
    "guardar_regla_comision": "comisiones.editar",
    "cambiar_estado_regla_comision": "comisiones.editar",
    "archivar_regla_comision": "comisiones.editar",
    "simular_comision": "comisiones.editar",
    "pagos": "pagos.ver",
    "registrar_cuota": "pagos.crear",
    "registrar_matricula": "pagos.crear",
    "marcar_pago_alumno": "pagos.editar",
    "exportar_pagos": "pagos.exportar",
    "actualizar_precio_clase": "comisiones.editar",
    "agregar_promocion": "promociones.crear",
    "promociones": "promociones.ver",
    "guardar_promocion": "promociones.crear",
    "toggle_promocion": "promociones.editar",
    "eliminar_promocion": "promociones.eliminar",
    "liquidaciones": "liquidaciones.ver",
    "cambiar_estado_liquidacion": "liquidaciones.pagar",
    "agregar_ajuste_liquidacion": "liquidaciones.editar",
    "exportar_liquidaciones": "liquidaciones.exportar",
    "deudores": "deudores.ver",
    "ajustes_manuales": "ajustes.ver",
    "guardar_ajuste_manual": "ajustes.crear",
    "anular_ajuste_manual_route": "ajustes.anular",
    "exportar_ajustes_csv": "ajustes.ver",
    "recuperos": "recuperos.ver",
    "guardar_recupero": "recuperos.crear",
    "programar_recupero": "recuperos.editar",
    "cambiar_estado_recupero": "recuperos.editar",
    "alumnos": "alumnos.ver",
    "ficha_alumno": "alumnos.ver",
    "agregar_alumno": "alumnos.crear",
    "editar_alumno": "alumnos.editar",
    "eliminar_alumno": "alumnos.eliminar",
    "agregar_movimiento_cuenta": "ajustes.crear",
    "anular_movimiento_cuenta": "ajustes.anular",
    "exportar_estado_cuenta_csv": "estado_cuenta.exportar",
    "estado_cuenta_pdf": "estado_cuenta.exportar",
    "clases": "clases.ver",
    "agregar_clase": "clases.crear",
    "editar_clase": "clases.editar",
    "clases_repetidas": "clases.crear",
    "toggle_asistencia": "asistencia.editar",
    "cambiar_asistencia": "asistencia.editar",
    "mover_clase": "clases.editar",
    "cambiar_estado_clase": "clases.editar",
    "cancelar_clase": "clases.editar",
    "eliminar_alumno_clase": "clases.editar",
    "eliminar_clase": "clases.eliminar",
    "agregar_alumnos_clase": "clases.editar",
    "guardar_colores": "configuracion.editar"
}

def registrar_acceso_denegado(permiso):
    try:
        conn = get_conn()
        registrar_auditoria(conn, "seguridad", "acceso_denegado", "permiso", permiso, f"Intento denegado en {request.path}")
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass

def acceso_denegado(permiso):
    registrar_acceso_denegado(permiso)
    if request.is_json or request.path.startswith(("/toggle_", "/cambiar_", "/mover_", "/cancelar_", "/eliminar_")):
        return jsonify({"ok": False, "error": "No tenes permiso para realizar esta accion."}), 403
    return redirect(ruta_inicio_por_rol(session.get("usuario_rol")))

def permission_required(permiso):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("usuario_id"):
                return redirect(url_for("login"))
            if not tiene_permiso(permiso):
                return acceso_denegado(permiso)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("login"))
        permiso = ENDPOINT_PERMISSIONS.get(request.endpoint)
        if permiso and not tiene_permiso(permiso):
            return acceso_denegado(permiso)
        return fn(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("usuario_id"):
                return redirect(url_for("login"))
            permiso = ENDPOINT_PERMISSIONS.get(request.endpoint)
            if permiso and not tiene_permiso(permiso):
                return acceso_denegado(permiso)
            roles_normalizados = [normalizar_rol(r) for r in roles]
            if not permiso and normalizar_rol(session.get("usuario_rol")) not in roles_normalizados:
                return redirect(ruta_inicio_por_rol(session.get("usuario_rol")))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@app.context_processor
def contexto_usuario():
    conn = get_conn()
    configuracion = obtener_configuracion(conn)
    conn.commit()
    conn.commit()
    conn.close()

    return {
        "usuario_actual": usuario_actual(),
        "puede_gestionar_clases": puede_gestionar_clases(),
        "puede_ver_pagos": puede_ver_pagos(),
        "puede": puede,
        "configuracion": configuracion
    }

# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]

        conn = get_conn()
        usuario = conn.execute("""
            SELECT * FROM usuarios
            WHERE nombre=?
        """, (nombre,)).fetchone()
        if usuario and int(usuario["activo"] or 1) == 0:
            registrar_auditoria(conn, "seguridad", "login_bloqueado", "usuario", usuario["id"], f"Intento de login de usuario bloqueado: {nombre}")
            conn.commit()
            conn.close()
            return render_template("login.html", error="El usuario esta bloqueado.")

        if usuario and check_password_hash(usuario["password_hash"], password):
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["usuario_nombre"] = usuario["nombre"]
            session["usuario_rol"] = normalizar_rol(usuario["rol"])
            session["profesor_id"] = usuario["profesor_id"] if "profesor_id" in usuario.keys() else None
            if normalizar_rol(usuario["rol"]) != usuario["rol"]:
                conn.execute("UPDATE usuarios SET rol=? WHERE id=?", (normalizar_rol(usuario["rol"]), usuario["id"]))
            registrar_auditoria(conn, "seguridad", "login", "usuario", usuario["id"], f"Inicio de sesion: {usuario['nombre']}")
            conn.commit()
            conn.close()
            return redirect(ruta_inicio_por_rol(usuario["rol"]))

        error = "Usuario o contraseña incorrectos."

        if usuario:
            registrar_auditoria(conn, "seguridad", "login_fallido", "usuario", usuario["id"], f"Password incorrecta para {nombre}")
            conn.commit()
        conn.close()

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    if session.get("usuario_id"):
        conn = get_conn()
        registrar_auditoria(conn, "seguridad", "logout", "usuario", session.get("usuario_id"), f"Cierre de sesion: {session.get('usuario_nombre')}")
        conn.commit()
        conn.close()
    session.clear()
    return redirect("/login")

# ---------------- USUARIOS ----------------

@app.route("/usuarios")
@roles_required("admin")
def usuarios():
    conn = get_conn()
    usuarios = conn.execute("""
        SELECT usuarios.id, usuarios.nombre, usuarios.rol, usuarios.activo,
               usuarios.profesor_id, profesores.nombre_apellido AS profesor
        FROM usuarios
        LEFT JOIN profesores ON usuarios.profesor_id = profesores.id
        ORDER BY usuarios.nombre
    """).fetchall()
    roles = conn.execute("SELECT * FROM roles WHERE activo=1 ORDER BY nombre").fetchall()
    permisos = conn.execute("SELECT * FROM permisos ORDER BY modulo, descripcion").fetchall()
    rol_permisos = conn.execute("SELECT rol_codigo, permiso_codigo FROM rol_permisos").fetchall()
    profesores = conn.execute("""
        SELECT id, nombre_apellido
        FROM profesores
        WHERE activo=1 OR activo IS NULL
        ORDER BY nombre_apellido
    """).fetchall()
    permisos_por_rol = {}
    for fila in rol_permisos:
        permisos_por_rol.setdefault(fila["rol_codigo"], set()).add(fila["permiso_codigo"])
    conn.close()

    return render_template(
        "usuarios.html",
        usuarios=usuarios,
        roles=roles,
        permisos=permisos,
        permisos_por_rol=permisos_por_rol,
        profesores=profesores,
        role_labels=ROLE_LABELS
    )

@app.route("/agregar_usuario", methods=["POST"])
@roles_required("admin")
def agregar_usuario():
    nombre = request.form["nombre"].strip()
    password = request.form["password"]
    rol = normalizar_rol(request.form["rol"])
    profesor_id = validar_entero(request.form.get("profesor_id"))

    if not nombre or not password:
        return redirect("/usuarios?" + urlencode({
            "mensaje": "El nombre y la contrasena son obligatorios.",
            "tipo": "warning"
        }))

    conn = get_conn()
    existente = conn.execute("""
        SELECT id FROM usuarios
        WHERE nombre=?
    """, (nombre,)).fetchone()

    if existente:
        conn.close()
        return redirect("/usuarios?" + urlencode({
            "mensaje": "Ya existe un usuario con ese nombre.",
            "tipo": "warning"
        }))

    cur = conn.execute("""
        INSERT INTO usuarios (nombre, password_hash, rol, activo, profesor_id)
        VALUES (?, ?, ?, 1, ?)
    """, (
        nombre,
        generate_password_hash(password),
        rol,
        profesor_id if rol == "profesor" else None
    ))
    registrar_auditoria(conn, "usuarios", "crear", "usuario", cur.lastrowid, f"Usuario creado: {nombre} ({rol})")
    conn.commit()
    conn.close()
    return redirect("/usuarios")

@app.route("/usuarios/cambiar_rol", methods=["POST"])
@permission_required("usuarios.editar")
def cambiar_rol_usuario():
    usuario_id = validar_entero(request.form.get("usuario_id"))
    rol = normalizar_rol(request.form.get("rol"))
    profesor_id = validar_entero(request.form.get("profesor_id"))
    if not usuario_id:
        return redirect("/usuarios")
    if usuario_id == session.get("usuario_id") and rol != "admin":
        return redirect("/usuarios?" + urlencode({"mensaje": "No podes quitarte tu propio rol administrador.", "tipo": "warning"}))

    conn = get_conn()
    usuario = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if not usuario:
        conn.close()
        return redirect("/usuarios")
    if normalizar_rol(usuario["rol"]) == "admin" and rol != "admin":
        admins = conn.execute("SELECT COUNT(*) AS total FROM usuarios WHERE rol='admin' AND activo=1").fetchone()["total"]
        if admins <= 1:
            conn.close()
            return redirect("/usuarios?" + urlencode({"mensaje": "No podes quitar el ultimo administrador activo.", "tipo": "warning"}))
    conn.execute("UPDATE usuarios SET rol=?, profesor_id=? WHERE id=?", (rol, profesor_id if rol == "profesor" else None, usuario_id))
    registrar_auditoria(conn, "usuarios", "editar", "usuario", usuario_id, f"Rol actualizado a {rol}")
    conn.commit()
    conn.close()
    return redirect("/usuarios")

@app.route("/usuarios/bloquear", methods=["POST"])
@permission_required("usuarios.editar")
def bloquear_usuario():
    usuario_id = validar_entero(request.form.get("usuario_id"))
    activo = 1 if request.form.get("activo") == "1" else 0
    if not usuario_id:
        return redirect("/usuarios")
    if usuario_id == session.get("usuario_id") and activo == 0:
        return redirect("/usuarios?" + urlencode({"mensaje": "No podes bloquear tu propio usuario.", "tipo": "warning"}))

    conn = get_conn()
    usuario = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if usuario and normalizar_rol(usuario["rol"]) == "admin" and activo == 0:
        admins = conn.execute("SELECT COUNT(*) AS total FROM usuarios WHERE rol='admin' AND activo=1").fetchone()["total"]
        if admins <= 1:
            conn.close()
            return redirect("/usuarios?" + urlencode({"mensaje": "No podes bloquear el ultimo administrador activo.", "tipo": "warning"}))
    conn.execute("UPDATE usuarios SET activo=? WHERE id=?", (activo, usuario_id))
    registrar_auditoria(conn, "usuarios", "estado", "usuario", usuario_id, "Usuario activado" if activo else "Usuario bloqueado")
    conn.commit()
    conn.close()
    return redirect("/usuarios")

@app.route("/roles/permisos", methods=["POST"])
@permission_required("roles.editar")
def guardar_permisos_rol():
    rol = normalizar_rol(request.form.get("rol"))
    permisos = set(request.form.getlist("permisos"))
    permisos_validos = {p[0] for p in PERMISOS_SISTEMA}
    permisos = permisos & permisos_validos
    if rol == "admin":
        permisos = permisos_validos

    conn = get_conn()
    conn.execute("DELETE FROM rol_permisos WHERE rol_codigo=?", (rol,))
    for permiso in sorted(permisos):
        conn.execute("INSERT OR IGNORE INTO rol_permisos (rol_codigo, permiso_codigo) VALUES (?, ?)", (rol, permiso))
    registrar_auditoria(conn, "usuarios", "permisos", "rol", rol, f"Permisos actualizados: {len(permisos)}")
    conn.commit()
    conn.close()
    return redirect("/usuarios?" + urlencode({"mensaje": "Permisos actualizados.", "tipo": "success"}))

@app.route("/eliminar_usuario/<int:id>")
@roles_required("admin")
def eliminar_usuario(id):
    if session.get("usuario_id") == id:
        return redirect("/usuarios?" + urlencode({
            "mensaje": "No podes eliminar el usuario con el que estas conectado.",
            "tipo": "warning"
        }))

    conn = get_conn()
    usuario = conn.execute("SELECT rol FROM usuarios WHERE id=?", (id,)).fetchone()

    if usuario and normalizar_rol(usuario["rol"]) == "admin":
        admins = conn.execute("SELECT COUNT(*) AS total FROM usuarios WHERE rol='admin' AND activo=1").fetchone()["total"]
        if admins <= 1:
            conn.close()
            return redirect("/usuarios?" + urlencode({
                "mensaje": "No podes eliminar el ultimo administrador del sistema.",
                "tipo": "warning"
            }))

    detalle = f"Usuario eliminado: #{id}"
    conn.execute("UPDATE usuarios SET activo=0 WHERE id=?", (id,))
    registrar_auditoria(conn, "usuarios", "eliminar", "usuario", id, detalle)
    conn.commit()
    conn.close()
    return redirect("/usuarios")

# ---------------- DASHBOARD ----------------

@app.route("/")
@roles_required("admin")
def dashboard():
    conn = get_conn()
    resumen = resumen_financiero(conn)
    alertas = alertas_dashboard(conn)

    conn.commit()
    conn.close()

    return render_template(
        "dashboard.html",
        total_clases=resumen["total_clases"],
        ingresos=round(resumen["ingresos"], 2),
        pagos=round(resumen["pagos_profesores"], 2),
        ganancia=round(resumen["ganancia"], 2),
        alumnos_deudores=resumen["alumnos_deudores"],
        deuda_total=round(resumen["deuda_total"], 2),
        saldo_a_favor_total=round(resumen["saldo_a_favor_total"], 2),
        descuentos=round(resumen["descuentos"], 2),
        ajustes_manuales=round(resumen["ajustes_manuales"], 2),
        alertas=alertas
    )

@app.route("/caja")
@roles_required("admin", "comun")
def caja():
    conn = get_conn()
    resumen = resumen_financiero(conn)
    alertas = alertas_dashboard(conn)
    conn.commit()
    conn.close()
    return render_template(
        "caja.html",
        resumen=resumen,
        alertas=alertas
    )

@app.route("/estadisticas")
@roles_required("admin")
def estadisticas():
    conn = get_conn()
    filtros = filtros_analytics(request.args)
    datos = calcular_analytics(conn, filtros)
    profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()
    alumnos = conn.execute("SELECT * FROM alumnos ORDER BY apellido_nombre").fetchall()
    tipos_clase = conn.execute("SELECT * FROM tipos_clase ORDER BY id").fetchall()
    promociones = conn.execute("SELECT * FROM promociones WHERE eliminada=0 ORDER BY nombre").fetchall()
    conn.commit()
    conn.close()
    registrar_conn = get_conn()
    registrar_auditoria(registrar_conn, "estadisticas", "ver", "reporte", "", f"Consulta analytics {filtros['desde']} a {filtros['hasta']}")
    registrar_conn.commit()
    registrar_conn.close()

    return render_template(
        "estadisticas.html",
        datos=datos,
        filtros=filtros,
        profesores=profesores,
        alumnos=alumnos,
        tipos_clase=tipos_clase,
        promociones=promociones
    )

@app.route("/estadisticas/exportar_csv")
@roles_required("admin")
def exportar_estadisticas_csv():
    conn = get_conn()
    filtros = filtros_analytics(request.args)
    datos = calcular_analytics(conn, filtros)
    conn.commit()
    conn.close()

    salida = io.StringIO()
    salida.write("\ufeff")
    writer = csv.writer(salida)
    writer.writerow(["Reporte", "Desde", filtros["desde"], "Hasta", filtros["hasta"]])
    writer.writerow([])
    writer.writerow(["KPI", "Valor"])
    for clave, valor in datos["kpis"].items():
        writer.writerow([clave, valor])
    writer.writerow([])
    writer.writerow(["Ingresos por mes"])
    writer.writerow(["Periodo", "Total"])
    for fila in datos["series"]["ingresos_mes"]:
        writer.writerow([fila["periodo"], fila["total"]])
    writer.writerow([])
    writer.writerow(["Profesores"])
    writer.writerow(["Profesor", "Clases", "Alumnos", "Canceladas", "Recuperos", "Asistencia %"])
    for prof in datos["profesores"]:
        asistencia = (float(prof["presentes"] or 0) / max(float(prof["asistencias"] or 0), 1)) * 100
        writer.writerow([prof["nombre_apellido"], prof["clases"], prof["alumnos"], prof["canceladas"], prof["recuperos"], f"{asistencia:.2f}"])

    registrar_conn = get_conn()
    registrar_auditoria(registrar_conn, "estadisticas", "exportar", "csv", "", f"Exportacion analytics {filtros['desde']} a {filtros['hasta']}")
    registrar_conn.commit()
    registrar_conn.close()

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Response(
        salida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=estadisticas_{fecha}.csv"}
    )

@app.route("/estadisticas/reporte")
@roles_required("admin")
def reporte_estadisticas():
    conn = get_conn()
    filtros = filtros_analytics(request.args)
    datos = calcular_analytics(conn, filtros)
    configuracion = obtener_configuracion(conn)
    conn.commit()
    conn.close()
    return render_template(
        "estadisticas_reporte.html",
        datos=datos,
        filtros=filtros,
        configuracion=configuracion,
        fecha=datetime.now().strftime("%Y-%m-%d")
    )

@app.route("/backup_base_datos")
@roles_required("admin")
def backup_base_datos():
    temporal = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temporal.close()
    origen = None
    destino = None

    try:
        origen = sqlite3.connect("database.db")
        destino = sqlite3.connect(temporal.name)
        origen.backup(destino)

        with open(temporal.name, "rb") as archivo:
            datos = io.BytesIO(archivo.read())
        datos.seek(0)
    finally:
        if destino:
            destino.close()
        if origen:
            origen.close()
        if os.path.exists(temporal.name):
            os.unlink(temporal.name)

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M")
    conn_auditoria = get_conn()
    registrar_auditoria(conn_auditoria, "seguridad", "backup", "database", "database.db", "Descarga de copia de seguridad")
    conn_auditoria.commit()
    conn_auditoria.close()

    return send_file(
        datos,
        as_attachment=True,
        download_name=f"backup_espacio_arte_{fecha}.db",
        mimetype="application/octet-stream"
    )

@app.route("/auditoria")
@roles_required("admin")
def auditoria():
    modulo = (request.args.get("modulo") or "").strip()
    accion = (request.args.get("accion") or "").strip()

    condiciones = []
    valores = []

    if modulo:
        condiciones.append("modulo=?")
        valores.append(modulo)
    if accion:
        condiciones.append("accion=?")
        valores.append(accion)

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    conn = get_conn()
    registros = conn.execute(f"""
        SELECT *
        FROM auditoria
        {where}
        ORDER BY fecha DESC, id DESC
        LIMIT 300
    """, valores).fetchall()
    modulos = conn.execute("SELECT DISTINCT modulo FROM auditoria ORDER BY modulo").fetchall()
    acciones = conn.execute("SELECT DISTINCT accion FROM auditoria ORDER BY accion").fetchall()
    conn.close()

    return render_template(
        "auditoria.html",
        registros=registros,
        modulos=modulos,
        acciones=acciones,
        filtro_modulo=modulo,
        filtro_accion=accion
    )

# ---------------- PROFESORES ----------------

@app.route("/profesores")
@roles_required("admin")
def profesores():
    conn = get_conn()
    profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()
    reglas = conn.execute("""
        SELECT reglas_comision.*, profesores.nombre_apellido AS profesor_nombre,
               tipos_clase.nombre AS tipo_clase_nombre
        FROM reglas_comision
        LEFT JOIN profesores ON reglas_comision.profesor_id = profesores.id
        LEFT JOIN tipos_clase ON reglas_comision.tipo_clase_id = tipos_clase.id
        WHERE reglas_comision.archivada=0
        ORDER BY reglas_comision.profesor_id, reglas_comision.prioridad DESC, reglas_comision.id DESC
    """).fetchall()
    tipos_clase = conn.execute("SELECT * FROM tipos_clase ORDER BY id").fetchall()
    configuracion = obtener_configuracion(conn)
    conn.close()
    return render_template(
        "profesores.html",
        profesores=profesores,
        reglas_comision=reglas,
        tipos_clase=tipos_clase,
        modalidades_comision=MODALIDADES_COMISION,
        bases_comision=BASES_COMISION,
        estados_regla_comision=ESTADOS_REGLA_COMISION,
        configuracion=configuracion
    )

@app.route("/guardar_comisiones_globales", methods=["POST"])
@roles_required("admin")
def guardar_comisiones_globales():
    conn = get_conn()
    valores = {
        "comision_default_individual": min(validar_precio(request.form.get("comision_default_individual")), 100),
        "comision_default_duo": min(validar_precio(request.form.get("comision_default_duo")), 100),
        "comision_default_grupal": min(validar_precio(request.form.get("comision_default_grupal")), 100),
        "comision_base_default": normalizar_base_comision(request.form.get("comision_base_default"))
    }
    for clave, valor in valores.items():
        conn.execute("""
            INSERT INTO configuracion (clave, valor)
            VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
        """, (clave, str(valor)))
    registrar_auditoria(conn, "comisiones", "editar", "configuracion", "global", "Defaults globales de comision actualizados")
    conn.commit()
    conn.close()
    return redirect("/profesores")

def datos_regla_comision_form():
    porcentaje = min(validar_precio(request.form.get("porcentaje")), 100)
    monto = validar_precio(request.form.get("monto"))
    prioridad = validar_entero(request.form.get("prioridad"))
    return {
        "profesor_id": request.form.get("profesor_id") or None,
        "nombre": request.form.get("nombre", "").strip(),
        "tipo_clase_id": request.form.get("tipo_clase_id") or None,
        "modalidad": normalizar_modalidad_comision(request.form.get("modalidad")),
        "base_calculo": normalizar_base_comision(request.form.get("base_calculo")),
        "porcentaje": porcentaje,
        "monto": monto,
        "min_alumnos": validar_entero(request.form.get("min_alumnos")),
        "max_alumnos": validar_entero(request.form.get("max_alumnos")),
        "min_presentes": validar_entero(request.form.get("min_presentes")),
        "max_presentes": validar_entero(request.form.get("max_presentes")),
        "min_clases_mes": validar_entero(request.form.get("min_clases_mes")),
        "max_clases_mes": validar_entero(request.form.get("max_clases_mes")),
        "min_monto": validar_precio(request.form.get("min_monto")) if request.form.get("min_monto") else None,
        "max_monto": validar_precio(request.form.get("max_monto")) if request.form.get("max_monto") else None,
        "aplica_recupero": normalizar_aplica_recupero(request.form.get("aplica_recupero")),
        "requiere_promocion": 1 if request.form.get("requiere_promocion") == "1" else 0,
        "prioridad": prioridad if prioridad is not None else 0,
        "estado": normalizar_estado_regla_comision(request.form.get("estado")),
        "fecha_inicio": normalizar_fecha(request.form.get("fecha_inicio")),
        "fecha_fin": normalizar_fecha(request.form.get("fecha_fin")),
        "observaciones": request.form.get("observaciones", "").strip()
    }

@app.route("/guardar_regla_comision", methods=["POST"])
@roles_required("admin")
def guardar_regla_comision():
    conn = get_conn()
    regla_id = request.form.get("id")
    datos = datos_regla_comision_form()
    motivo = request.form.get("motivo_cambio", "").strip()

    if not datos["nombre"]:
        conn.close()
        return redirect("/profesores?" + urlencode({"mensaje": "La regla necesita nombre.", "tipo": "warning"}))
    if datos["fecha_inicio"] and datos["fecha_fin"] and datos["fecha_inicio"] > datos["fecha_fin"]:
        conn.close()
        return redirect("/profesores?" + urlencode({"mensaje": "La fecha de inicio no puede ser posterior al fin.", "tipo": "warning"}))
    if datos["modalidad"].startswith("porcentaje") and datos["porcentaje"] <= 0:
        conn.close()
        return redirect("/profesores?" + urlencode({"mensaje": "La regla porcentual necesita un porcentaje mayor a cero.", "tipo": "warning"}))
    if datos["modalidad"].startswith("monto") and datos["monto"] <= 0:
        conn.close()
        return redirect("/profesores?" + urlencode({"mensaje": "La regla de monto fijo necesita un monto mayor a cero.", "tipo": "warning"}))

    anterior = None
    if regla_id:
        anterior = conn.execute("SELECT * FROM reglas_comision WHERE id=?", (regla_id,)).fetchone()
        if not anterior:
            conn.close()
            return redirect("/profesores")
        conn.execute("""
            UPDATE reglas_comision
            SET profesor_id=?, nombre=?, tipo_clase_id=?, modalidad=?, base_calculo=?,
                porcentaje=?, monto=?, min_alumnos=?, max_alumnos=?, min_presentes=?,
                max_presentes=?, min_clases_mes=?, max_clases_mes=?, min_monto=?,
                max_monto=?, aplica_recupero=?, requiere_promocion=?, prioridad=?,
                estado=?, fecha_inicio=?, fecha_fin=?, observaciones=?,
                actualizado_por=?, actualizado_por_nombre=?, fecha_actualizacion=?
            WHERE id=?
        """, (
            datos["profesor_id"], datos["nombre"], datos["tipo_clase_id"], datos["modalidad"], datos["base_calculo"],
            datos["porcentaje"], datos["monto"], datos["min_alumnos"], datos["max_alumnos"], datos["min_presentes"],
            datos["max_presentes"], datos["min_clases_mes"], datos["max_clases_mes"], datos["min_monto"],
            datos["max_monto"], datos["aplica_recupero"], datos["requiere_promocion"], datos["prioridad"],
            datos["estado"], datos["fecha_inicio"], datos["fecha_fin"], datos["observaciones"],
            session.get("usuario_id"), session.get("usuario_nombre"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            regla_id
        ))
        conn.execute("""
            INSERT INTO reglas_comision_historial (
                regla_id, profesor_id, accion, datos_anteriores, datos_nuevos,
                motivo, usuario_id, usuario_nombre, fecha
            )
            VALUES (?, ?, 'editar', ?, ?, ?, ?, ?, ?)
        """, (
            regla_id,
            datos["profesor_id"],
            json.dumps(dict(anterior)),
            json.dumps(datos),
            motivo,
            session.get("usuario_id"),
            session.get("usuario_nombre"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        registrar_auditoria(conn, "comisiones", "editar", "regla", regla_id, f"Regla editada: {datos['nombre']}")
    else:
        cur = conn.execute("""
            INSERT INTO reglas_comision (
                profesor_id, nombre, tipo_clase_id, modalidad, base_calculo,
                porcentaje, monto, min_alumnos, max_alumnos, min_presentes,
                max_presentes, min_clases_mes, max_clases_mes, min_monto,
                max_monto, aplica_recupero, requiere_promocion, prioridad,
                estado, fecha_inicio, fecha_fin, observaciones,
                creado_por, creado_por_nombre, fecha_creacion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datos["profesor_id"], datos["nombre"], datos["tipo_clase_id"], datos["modalidad"], datos["base_calculo"],
            datos["porcentaje"], datos["monto"], datos["min_alumnos"], datos["max_alumnos"], datos["min_presentes"],
            datos["max_presentes"], datos["min_clases_mes"], datos["max_clases_mes"], datos["min_monto"],
            datos["max_monto"], datos["aplica_recupero"], datos["requiere_promocion"], datos["prioridad"],
            datos["estado"], datos["fecha_inicio"], datos["fecha_fin"], datos["observaciones"],
            session.get("usuario_id"), session.get("usuario_nombre"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.execute("""
            INSERT INTO reglas_comision_historial (
                regla_id, profesor_id, accion, datos_nuevos, motivo, usuario_id, usuario_nombre, fecha
            )
            VALUES (?, ?, 'crear', ?, ?, ?, ?, ?)
        """, (
            cur.lastrowid,
            datos["profesor_id"],
            json.dumps(datos),
            motivo,
            session.get("usuario_id"),
            session.get("usuario_nombre"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        registrar_auditoria(conn, "comisiones", "crear", "regla", cur.lastrowid, f"Regla creada: {datos['nombre']}")

    conn.commit()
    conn.close()
    return redirect("/profesores")

@app.route("/regla_comision/estado", methods=["POST"])
@roles_required("admin")
def cambiar_estado_regla_comision():
    regla_id = request.form["id"]
    estado = normalizar_estado_regla_comision(request.form.get("estado"))
    conn = get_conn()
    regla = conn.execute("SELECT * FROM reglas_comision WHERE id=?", (regla_id,)).fetchone()
    if regla:
        conn.execute("""
            UPDATE reglas_comision
            SET estado=?, actualizado_por=?, actualizado_por_nombre=?, fecha_actualizacion=?
            WHERE id=?
        """, (estado, session.get("usuario_id"), session.get("usuario_nombre"), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), regla_id))
        conn.execute("""
            INSERT INTO reglas_comision_historial (
                regla_id, profesor_id, accion, datos_anteriores, datos_nuevos,
                usuario_id, usuario_nombre, fecha
            )
            VALUES (?, ?, 'estado', ?, ?, ?, ?, ?)
        """, (regla_id, regla["profesor_id"], json.dumps(dict(regla)), json.dumps({"estado": estado}), session.get("usuario_id"), session.get("usuario_nombre"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        registrar_auditoria(conn, "comisiones", "estado", "regla", regla_id, f"Regla marcada como {estado}")
        conn.commit()
    conn.close()
    return redirect("/profesores")

@app.route("/regla_comision/archivar", methods=["POST"])
@roles_required("admin")
def archivar_regla_comision():
    regla_id = request.form["id"]
    conn = get_conn()
    regla = conn.execute("SELECT * FROM reglas_comision WHERE id=?", (regla_id,)).fetchone()
    if regla:
        conn.execute("UPDATE reglas_comision SET archivada=1, estado='archivada' WHERE id=?", (regla_id,))
        conn.execute("""
            INSERT INTO reglas_comision_historial (
                regla_id, profesor_id, accion, datos_anteriores, motivo,
                usuario_id, usuario_nombre, fecha
            )
            VALUES (?, ?, 'archivar', ?, ?, ?, ?, ?)
        """, (regla_id, regla["profesor_id"], json.dumps(dict(regla)), request.form.get("motivo", ""), session.get("usuario_id"), session.get("usuario_nombre"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        registrar_auditoria(conn, "comisiones", "archivar", "regla", regla_id, f"Regla archivada: {regla['nombre']}")
        conn.commit()
    conn.close()
    return redirect("/profesores")

@app.route("/simular_comision", methods=["POST"])
@roles_required("admin")
def simular_comision():
    data = request.json or {}
    conn = get_conn()
    profesor = conn.execute("SELECT * FROM profesores WHERE id=?", (data.get("profesor_id"),)).fetchone()
    if not profesor:
        conn.close()
        return jsonify({"ok": False, "error": "Profesor invalido"}), 400
    contexto = {
        "fecha": data.get("fecha") or datetime.now().strftime("%Y-%m-%d"),
        "tipo_clase": data.get("tipo_clase") or "individual",
        "tipo_clase_id": validar_entero(data.get("tipo_clase_id")) or 1,
        "alumnos": validar_entero(data.get("alumnos")) or 1,
        "presentes": validar_entero(data.get("presentes")) or validar_entero(data.get("alumnos")) or 1,
        "ingreso_real": validar_precio(data.get("monto_real")),
        "ingreso_esperado": validar_precio(data.get("monto_esperado") or data.get("monto_real")),
        "base_profesor": validar_precio(data.get("base_profesor") or data.get("monto_real")),
        "tiene_promocion": bool(data.get("tiene_promocion")),
        "es_recupero": bool(data.get("es_recupero")),
        "recupero_profesor_cobra": not bool(data.get("recupero_no_paga")),
        "clases_mes": validar_entero(data.get("clases_mes")) or 1
    }
    resultado = calcular_comision_profesor(conn, profesor, contexto)
    registrar_auditoria(conn, "comisiones", "simular", "profesor", profesor["id"], f"Simulacion regla {resultado['regla_nombre']}")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, **resultado, "ganancia_academia": contexto["ingreso_real"] - resultado["pago_profesor"]})

@app.route("/agregar_profesor", methods=["POST"])
@roles_required("admin")
def agregar_profesor():
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO profesores (
            nombre_apellido, dni, telefono, domicilio, email, edad,
            precio_clase, porcentaje_individual, porcentaje_duo, porcentaje_grupal,
            activo, observaciones_liquidacion, color
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["nombre_apellido"],
        request.form["dni"],
        request.form["telefono"],
        request.form["domicilio"],
        request.form["email"],
        request.form["edad"],
        validar_precio(request.form.get("precio_clase")),
        validar_precio(request.form.get("porcentaje_individual") or 50),
        validar_precio(request.form.get("porcentaje_duo") or 40),
        validar_precio(request.form.get("porcentaje_grupal") or 40),
        1 if request.form.get("activo") else 0,
        request.form.get("observaciones_liquidacion", ""),
        request.form["color"]
    ))
    registrar_auditoria(conn, "profesores", "crear", "profesor", cur.lastrowid, f"Profesor creado: {request.form['nombre_apellido']}")
    conn.commit()
    conn.close()
    return redirect("/profesores")

@app.route("/editar_profesor", methods=["POST"])
@roles_required("admin")
def editar_profesor():
    conn = get_conn()
    conn.execute("""
        UPDATE profesores
        SET nombre_apellido=?, dni=?, telefono=?, domicilio=?, email=?, edad=?,
            precio_clase=?, porcentaje_individual=?, porcentaje_duo=?, porcentaje_grupal=?,
            activo=?, observaciones_liquidacion=?, color=?
        WHERE id=?
    """, (
        request.form["nombre_apellido"],
        request.form["dni"],
        request.form["telefono"],
        request.form["domicilio"],
        request.form["email"],
        request.form["edad"],
        validar_precio(request.form.get("precio_clase")),
        validar_precio(request.form.get("porcentaje_individual") or 50),
        validar_precio(request.form.get("porcentaje_duo") or 40),
        validar_precio(request.form.get("porcentaje_grupal") or 40),
        1 if request.form.get("activo") else 0,
        request.form.get("observaciones_liquidacion", ""),
        request.form["color"],
        request.form["id"]
    ))
    registrar_auditoria(conn, "profesores", "editar", "profesor", request.form["id"], f"Profesor editado: {request.form['nombre_apellido']}")
    conn.commit()
    conn.close()
    return redirect("/profesores")

@app.route("/eliminar_profesor/<int:id>")
@roles_required("admin")
def eliminar_profesor(id):
    conn = get_conn()
    profesor = conn.execute("SELECT nombre_apellido FROM profesores WHERE id=?", (id,)).fetchone()
    conn.execute("DELETE FROM profesores WHERE id=?", (id,))
    registrar_auditoria(conn, "profesores", "eliminar", "profesor", id, f"Profesor eliminado: {profesor['nombre_apellido'] if profesor else id}")
    conn.commit()
    conn.close()
    return redirect("/profesores")

# ---------------- PAGOS ----------------

@app.route("/pagos")
@roles_required("admin", "comun")
def pagos():
    conn = get_conn()
    filtros = filtros_reporte_pagos(request.args)
    reporte = obtener_reporte_pagos(conn, filtros)

    alumnos = conn.execute("SELECT * FROM alumnos ORDER BY apellido_nombre").fetchall()
    promociones = conn.execute("""
        SELECT promociones.*, alumnos.apellido_nombre
        FROM promociones
        LEFT JOIN alumnos ON COALESCE(promociones.aplica_alumno_id, promociones.alumno_id) = alumnos.id
        WHERE promociones.activa=1 AND promociones.eliminada=0
        ORDER BY promociones.prioridad DESC, promociones.nombre
    """).fetchall()

    profesores = conn.execute("""
        SELECT *
        FROM profesores
        ORDER BY nombre_apellido
    """).fetchall()

    pagos_profesores = []
    total_pagos = 0

    for profesor in profesores:
        condiciones_fecha, valores_fecha = condiciones_fecha_clases(filtros)
        condiciones_profesor = ["clases.profesor_id=?", "clases.estado<>'cancelada'"] + condiciones_fecha
        clases_profesor = conn.execute("""
            SELECT clases.*, profesores.precio_clase, profesores.porcentaje_individual,
                   profesores.porcentaje_duo, profesores.porcentaje_grupal,
                   tipos_clase.nombre as tipo_clase
            FROM clases
            LEFT JOIN profesores ON clases.profesor_id = profesores.id
            LEFT JOIN tipos_clase ON clases.tipo_clase_id = tipos_clase.id
            WHERE """ + " AND ".join(condiciones_profesor) + """
        """, [profesor["id"], *valores_fecha]).fetchall()

        precio = float(profesor["precio_clase"] or 0)
        subtotal = sum(calcular_pago_profesor_clase(c)["pago_profesor"] for c in clases_profesor)
        total_pagos += subtotal

        pagos_profesores.append({
            "id": profesor["id"],
            "nombre_apellido": profesor["nombre_apellido"],
            "precio_clase": precio,
            "porcentaje_grupal": float(profesor["porcentaje_grupal"] or 40),
            "total_clases": len(clases_profesor),
            "subtotal": subtotal
        })

    resumen = resumen_financiero(conn)
    conn.close()

    return render_template(
        "pagos.html",
        alumnos=alumnos,
        promociones=promociones,
        cuotas=reporte["cuotas"],
        matriculas=reporte["matriculas"],
        pagos_profesores=pagos_profesores,
        total_pagos=total_pagos,
        resumen=resumen,
        resumen_reporte=reporte["resumen"],
        filtros=filtros
    )

@app.route("/exportar_pagos")
@roles_required("admin", "comun")
def exportar_pagos():
    conn = get_conn()
    filtros = filtros_reporte_pagos(request.args)
    reporte = obtener_reporte_pagos(conn, filtros)
    conn.close()

    salida = io.StringIO()
    salida.write("\ufeff")
    writer = csv.writer(salida)
    writer.writerow([
        "Tipo",
        "Alumno",
        "Periodo",
        "Monto normal",
        "Descuento",
        "A pagar",
        "Estado",
        "Fecha pago",
        "Promocion"
    ])

    for cuota in reporte["cuotas"]:
        writer.writerow([
            "Cuota",
            cuota["apellido_nombre"] or "",
            f"{cuota['mes']}/{cuota['anio']}",
            cuota["monto_normal"],
            cuota["descuento"],
            cuota["monto_pagado"],
            cuota["estado"],
            cuota["fecha_pago"] or "",
            cuota["promocion"] or ""
        ])

    for matricula in reporte["matriculas"]:
        writer.writerow([
            "Matricula",
            matricula["apellido_nombre"] or "",
            matricula["anio"],
            matricula["monto_normal"],
            matricula["descuento"],
            matricula["monto_pagado"],
            matricula["estado"],
            matricula["fecha_pago"] or "",
            matricula["promocion"] or ""
        ])

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Response(
        salida.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=reporte_pagos_{fecha}.csv"
        }
    )

@app.route("/promociones")
@roles_required("admin")
def promociones():
    conn = get_conn()
    estado = request.args.get("estado") or ""
    tipo = request.args.get("tipo") or ""
    condiciones = ["promociones.eliminada=0"]
    valores = []
    hoy = datetime.now().strftime("%Y-%m-%d")

    if estado == "activas":
        condiciones.append("promociones.activa=1 AND (promociones.fecha_fin IS NULL OR promociones.fecha_fin='' OR promociones.fecha_fin>=?)")
        valores.append(hoy)
    elif estado == "vencidas":
        condiciones.append("promociones.fecha_fin IS NOT NULL AND promociones.fecha_fin<>'' AND promociones.fecha_fin<?")
        valores.append(hoy)
    elif estado == "inactivas":
        condiciones.append("promociones.activa=0")

    if tipo in TIPOS_PROMOCION:
        condiciones.append("promociones.tipo=?")
        valores.append(tipo)

    promociones_lista = conn.execute("""
        SELECT promociones.*, alumnos.apellido_nombre, profesores.nombre_apellido AS profesor_nombre,
               tipos_clase.nombre AS tipo_clase_nombre
        FROM promociones
        LEFT JOIN alumnos ON COALESCE(promociones.aplica_alumno_id, promociones.alumno_id) = alumnos.id
        LEFT JOIN profesores ON promociones.profesor_id = profesores.id
        LEFT JOIN tipos_clase ON promociones.tipo_clase_id = tipos_clase.id
        WHERE """ + " AND ".join(condiciones) + """
        ORDER BY promociones.activa DESC, promociones.prioridad DESC, promociones.id DESC
    """, valores).fetchall()

    usos = conn.execute("""
        SELECT promocion_usos.*, promociones.nombre, alumnos.apellido_nombre
        FROM promocion_usos
        LEFT JOIN promociones ON promocion_usos.promocion_id = promociones.id
        LEFT JOIN alumnos ON promocion_usos.alumno_id = alumnos.id
        ORDER BY promocion_usos.fecha DESC, promocion_usos.id DESC
        LIMIT 60
    """).fetchall()

    estadisticas = conn.execute("""
        SELECT
            COUNT(CASE WHEN activa=1 AND eliminada=0 THEN 1 END) AS activas,
            COUNT(CASE WHEN automatica=1 AND eliminada=0 THEN 1 END) AS automaticas,
            COUNT(CASE WHEN fecha_fin IS NOT NULL AND fecha_fin<>'' AND fecha_fin<? AND eliminada=0 THEN 1 END) AS vencidas,
            COALESCE(SUM(usos_actuales), 0) AS usos
        FROM promociones
    """, (hoy,)).fetchone()
    impacto = conn.execute("""
        SELECT COALESCE(SUM(descuento), 0) AS descuentos,
               COALESCE(SUM(monto_final), 0) AS facturado
        FROM promocion_usos
    """).fetchone()
    ranking = conn.execute("""
        SELECT promociones.nombre, COUNT(promocion_usos.id) AS usos,
               COALESCE(SUM(promocion_usos.descuento), 0) AS impacto
        FROM promociones
        LEFT JOIN promocion_usos ON promociones.id = promocion_usos.promocion_id
        WHERE promociones.eliminada=0
        GROUP BY promociones.id
        ORDER BY usos DESC, impacto DESC
        LIMIT 5
    """).fetchall()

    alumnos = conn.execute("SELECT * FROM alumnos ORDER BY apellido_nombre").fetchall()
    profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()
    tipos_clase = conn.execute("SELECT * FROM tipos_clase ORDER BY id").fetchall()
    conn.close()

    return render_template(
        "promociones.html",
        promociones=promociones_lista,
        usos=usos,
        alumnos=alumnos,
        profesores=profesores,
        tipos_clase=tipos_clase,
        tipos_promocion=TIPOS_PROMOCION,
        filtros={"estado": estado, "tipo": tipo},
        estadisticas=estadisticas,
        impacto=impacto,
        ranking=ranking
    )

@app.route("/guardar_promocion", methods=["POST"])
@roles_required("admin")
def guardar_promocion():
    conn = get_conn()
    promocion_id = request.form.get("id")
    nombre = request.form.get("nombre", "").strip()
    tipo = normalizar_tipo_promocion(request.form.get("tipo"))
    porcentaje = validar_precio(request.form.get("porcentaje_descuento"))
    monto = validar_precio(request.form.get("monto_descuento"))
    limite = validar_entero(request.form.get("limite_usos"))
    prioridad = validar_entero(request.form.get("prioridad")) or 0
    cantidad_min = validar_entero(request.form.get("cantidad_clases_min"))

    if not nombre:
        conn.close()
        return redirect("/promociones?mensaje=La promocion necesita nombre&tipo=warning")
    if porcentaje > 100:
        porcentaje = 100
    if not porcentaje and not monto and tipo not in ["matricula_bonificada", "primer_mes_bonificado"]:
        conn.close()
        return redirect("/promociones?mensaje=Agrega porcentaje, monto o una bonificacion&tipo=warning")

    valores = (
        request.form.get("aplica_alumno_id") or None,
        nombre,
        request.form.get("descripcion", "").strip(),
        tipo,
        porcentaje,
        monto,
        normalizar_fecha(request.form.get("fecha_inicio")),
        normalizar_fecha(request.form.get("fecha_fin")),
        limite,
        1 if request.form.get("activa") == "1" else 0,
        1 if request.form.get("automatica") == "1" else 0,
        1 if request.form.get("acumulable") == "1" else 0,
        prioridad,
        request.form.get("color") or "#10aaa5",
        request.form.get("grupo_familiar", "").strip(),
        request.form.get("tipo_clase_id") or None,
        request.form.get("profesor_id") or None,
        cantidad_min,
        request.form.get("instrumento", "").strip(),
        1 if request.form.get("nuevo_alumno") == "1" else 0,
        1 if request.form.get("alumno_activo") == "1" else 0,
        request.form.get("metodo_pago", "").strip(),
        1 if request.form.get("aplica_cuota") == "1" else 0,
        1 if request.form.get("aplica_matricula") == "1" else 0,
        1 if request.form.get("afecta_profesor") == "1" else 0,
        request.form.get("motivo", "").strip()
    )

    if promocion_id:
        conn.execute("""
            UPDATE promociones
            SET aplica_alumno_id=?, alumno_id=?, nombre=?, descripcion=?, tipo=?,
                porcentaje_descuento=?, monto_descuento=?, fecha_inicio=?, fecha_fin=?,
                limite_usos=?, activa=?, automatica=?, acumulable=?, prioridad=?,
                color=?, grupo_familiar=?, tipo_clase_id=?, profesor_id=?,
                cantidad_clases_min=?, instrumento=?, nuevo_alumno=?, alumno_activo=?,
                metodo_pago=?, aplica_cuota=?, aplica_matricula=?, afecta_profesor=?, motivo=?
            WHERE id=?
        """, (valores[0], valores[0], *valores[1:], promocion_id))
        registrar_auditoria(conn, "promociones", "editar", "promocion", promocion_id, f"Promocion editada: {nombre}")
    else:
        cur = conn.execute("""
            INSERT INTO promociones (
                aplica_alumno_id, alumno_id, nombre, descripcion, tipo,
                porcentaje_descuento, monto_descuento, fecha_inicio, fecha_fin,
                limite_usos, activa, automatica, acumulable, prioridad,
                color, grupo_familiar, tipo_clase_id, profesor_id,
                cantidad_clases_min, instrumento, nuevo_alumno, alumno_activo,
                metodo_pago, aplica_cuota, aplica_matricula, afecta_profesor, motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (valores[0], valores[0], *valores[1:]))
        registrar_auditoria(conn, "promociones", "crear", "promocion", cur.lastrowid, f"Promocion creada: {nombre}")

    conn.commit()
    conn.close()
    return redirect("/promociones")

@app.route("/promociones/toggle/<int:id>", methods=["POST"])
@roles_required("admin")
def toggle_promocion(id):
    conn = get_conn()
    promocion = conn.execute("SELECT * FROM promociones WHERE id=?", (id,)).fetchone()
    if promocion:
        nueva = 0 if int(promocion["activa"] or 0) == 1 else 1
        conn.execute("UPDATE promociones SET activa=? WHERE id=?", (nueva, id))
        registrar_auditoria(conn, "promociones", "estado", "promocion", id, f"Promocion {'activada' if nueva else 'desactivada'}: {promocion['nombre']}")
        conn.commit()
    conn.close()
    return redirect("/promociones")

@app.route("/promociones/eliminar/<int:id>", methods=["POST"])
@roles_required("admin")
def eliminar_promocion(id):
    conn = get_conn()
    promocion = conn.execute("SELECT * FROM promociones WHERE id=?", (id,)).fetchone()
    if promocion:
        conn.execute("UPDATE promociones SET eliminada=1, activa=0 WHERE id=?", (id,))
        registrar_auditoria(conn, "promociones", "eliminar", "promocion", id, f"Promocion eliminada: {promocion['nombre']}")
        conn.commit()
    conn.close()
    return redirect("/promociones")

@app.route("/liquidaciones")
@roles_required("admin", "comun")
def liquidaciones():
    hoy = datetime.now()
    anio = validar_entero(request.args.get("anio")) or hoy.year
    mes = validar_entero(request.args.get("mes")) or hoy.month
    profesor_id = validar_entero(request.args.get("profesor_id"))
    tipo_clase = request.args.get("tipo_clase") or ""

    if mes < 1 or mes > 12:
        mes = hoy.month

    conn = get_conn()
    profesor_actual_id = profesor_id_usuario_actual(conn)
    if profesor_actual_id:
        profesor_id = profesor_actual_id
    profesores = conn.execute("""
        SELECT *
        FROM profesores
        WHERE activo=1 OR ? IS NOT NULL
        ORDER BY nombre_apellido
    """, (profesor_id,)).fetchall()
    tipos_clase = conn.execute("SELECT * FROM tipos_clase ORDER BY id").fetchall()

    if profesor_id:
        profesores_liquidar = [p for p in profesores if p["id"] == profesor_id]
    else:
        profesores_liquidar = profesores

    liquidaciones_calculadas = [
        calcular_liquidacion_profesor(conn, profesor, anio, mes, tipo_clase)
        for profesor in profesores_liquidar
    ]
    conn.commit()
    conn.close()

    totales = {
        "ingreso_real": sum(l["totales"]["ingreso_real"] for l in liquidaciones_calculadas),
        "pago_profesor": sum(l["totales"]["pago_profesor_final"] for l in liquidaciones_calculadas),
        "ganancia_academia": sum(l["totales"]["ganancia_academia"] for l in liquidaciones_calculadas),
        "deben": sum(l["totales"]["deben"] for l in liquidaciones_calculadas),
        "clases": sum(l["totales"]["clases"] for l in liquidaciones_calculadas)
    }

    return render_template(
        "liquidaciones.html",
        liquidaciones=liquidaciones_calculadas,
        profesores=profesores,
        tipos_clase=tipos_clase,
        filtros={
            "anio": anio,
            "mes": mes,
            "profesor_id": profesor_id,
            "tipo_clase": tipo_clase
        },
        totales=totales,
        tipos_ajuste=[
            "bono_profesor",
            "descuento_profesor",
            "correccion_administrativa",
            "redondeo_manual",
            "compensacion_baja",
            "diferencia_absorbida_academia"
        ]
    )

@app.route("/liquidaciones/estado", methods=["POST"])
@roles_required("admin", "comun")
def cambiar_estado_liquidacion():
    estado = normalizar_estado(request.form.get("estado"), ["pendiente", "revisada", "pagada", "anulada"], "pendiente")
    liquidacion_id = request.form["liquidacion_id"]
    metodo_pago = request.form.get("metodo_pago", "").strip()
    observacion = request.form.get("observacion", "").strip()
    fecha_pago = datetime.now().strftime("%Y-%m-%d") if estado == "pagada" else None

    conn = get_conn()
    liquidacion = conn.execute("SELECT * FROM liquidaciones_profesores WHERE id=?", (liquidacion_id,)).fetchone()
    if not liquidacion:
        conn.close()
        return redirect("/liquidaciones")

    if liquidacion["estado"] == "pagada" and request.form.get("confirmar_modificacion") != "1":
        conn.close()
        return redirect("/liquidaciones?" + urlencode({
            "anio": liquidacion["anio"],
            "mes": liquidacion["mes"],
            "profesor_id": liquidacion["profesor_id"],
            "mensaje": "La liquidacion ya estaba pagada. Confirma la modificacion para cambiarla.",
            "tipo": "warning"
        }))

    conn.execute("""
        UPDATE liquidaciones_profesores
        SET estado=?, fecha_pago=?, metodo_pago=?, observacion=?
        WHERE id=?
    """, (estado, fecha_pago, metodo_pago, observacion, liquidacion_id))
    registrar_auditoria(conn, "liquidaciones", "estado", "liquidacion", liquidacion_id, f"Liquidacion marcada como {estado}")
    conn.commit()
    conn.close()

    return redirect("/liquidaciones?" + urlencode({
        "anio": liquidacion["anio"],
        "mes": liquidacion["mes"],
        "profesor_id": liquidacion["profesor_id"]
    }))

@app.route("/liquidaciones/ajuste", methods=["POST"])
@roles_required("admin")
def agregar_ajuste_liquidacion():
    liquidacion_id = request.form["liquidacion_id"]
    tipo = request.form.get("tipo")
    tipos_validos = [
        "bono_profesor",
        "descuento_profesor",
        "correccion_administrativa",
        "redondeo_manual",
        "compensacion_baja",
        "diferencia_absorbida_academia"
    ]
    if tipo not in tipos_validos:
        tipo = "correccion_administrativa"

    monto = validar_precio(request.form.get("monto"))
    motivo = request.form.get("motivo", "").strip()
    signo = "negativo" if tipo in ["descuento_profesor", "clase_no_reconocida"] else "positivo"

    conn = get_conn()
    liquidacion = conn.execute("SELECT * FROM liquidaciones_profesores WHERE id=?", (liquidacion_id,)).fetchone()
    if not liquidacion:
        conn.close()
        return redirect("/liquidaciones")

    if liquidacion["estado"] == "pagada" and request.form.get("confirmar_modificacion") != "1":
        conn.close()
        return redirect("/liquidaciones?" + urlencode({
            "anio": liquidacion["anio"],
            "mes": liquidacion["mes"],
            "profesor_id": liquidacion["profesor_id"],
            "mensaje": "La liquidacion esta pagada. Confirma antes de agregar ajustes.",
            "tipo": "warning"
        }))

    try:
        crear_ajuste_manual(
            conn,
            "liquidacion",
            tipo,
            monto,
            signo,
            motivo,
            request.form.get("observacion", "").strip(),
            datetime.now().strftime("%Y-%m-%d"),
            profesor_id=liquidacion["profesor_id"],
            liquidacion_id=liquidacion_id,
            entidad_relacionada=f"liquidacion:{liquidacion_id}"
        )
        conn.commit()
    except ValueError as exc:
        conn.close()
        return redirect("/liquidaciones?" + urlencode({
            "anio": liquidacion["anio"],
            "mes": liquidacion["mes"],
            "profesor_id": liquidacion["profesor_id"],
            "mensaje": str(exc),
            "tipo": "warning"
        }))
    finally:
        conn.close()

    return redirect("/liquidaciones?" + urlencode({
        "anio": liquidacion["anio"],
        "mes": liquidacion["mes"],
        "profesor_id": liquidacion["profesor_id"]
    }))

@app.route("/exportar_liquidaciones")
@roles_required("admin", "comun")
def exportar_liquidaciones():
    hoy = datetime.now()
    anio = validar_entero(request.args.get("anio")) or hoy.year
    mes = validar_entero(request.args.get("mes")) or hoy.month
    profesor_id = validar_entero(request.args.get("profesor_id"))
    tipo_clase = request.args.get("tipo_clase") or ""

    conn = get_conn()
    profesor_actual_id = profesor_id_usuario_actual(conn)
    if profesor_actual_id:
        profesor_id = profesor_actual_id
    profesores = conn.execute("""
        SELECT *
        FROM profesores
        WHERE (? IS NULL OR id=?)
        ORDER BY nombre_apellido
    """, (profesor_id, profesor_id)).fetchall()
    liquidaciones_calculadas = [
        calcular_liquidacion_profesor(conn, profesor, anio, mes, tipo_clase)
        for profesor in profesores
    ]
    conn.commit()
    conn.close()

    salida = io.StringIO()
    salida.write("\ufeff")
    writer = csv.writer(salida)
    writer.writerow([
        "Profesor", "Periodo", "Estado", "Clase", "Fecha", "Tipo",
        "Presentes", "Ausentes", "Pagaron", "Deben", "Ingreso esperado",
        "Ingreso real", "Diferencia", "Regla comision", "Base comision",
        "Porcentaje", "Pago profesor",
        "Ganancia academia", "Alumnos que deben"
    ])

    for liquidacion in liquidaciones_calculadas:
        profesor = liquidacion["profesor"]
        estado = liquidacion["liquidacion"]["estado"]
        for clase in liquidacion["clases"]:
            writer.writerow([
                profesor["nombre_apellido"],
                f"{mes}/{anio}",
                estado,
                clase["id"],
                clase["fecha"],
                clase["tipo_clase"],
                clase["presentes"],
                clase["ausentes"],
                clase["pagaron"],
                clase["deben"],
                f"{clase['ingreso_esperado']:.2f}",
                f"{clase['ingreso_real']:.2f}",
                f"{clase['diferencia']:.2f}",
                clase.get("regla_comision") or "",
                f"{clase.get('base_comision') or 0:.2f}",
                f"{clase['porcentaje']:.2f}",
                f"{clase['pago_profesor']:.2f}",
                f"{clase['ganancia_academia']:.2f}",
                "; ".join(clase["alumnos_deben"])
            ])

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Response(
        salida.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=liquidaciones_{fecha}.csv"
        }
    )

@app.route("/actualizar_precio_clase", methods=["POST"])
@roles_required("admin", "comun")
def actualizar_precio_clase():
    conn = get_conn()
    conn.execute("""
        UPDATE profesores
        SET precio_clase=?, porcentaje_grupal=?
        WHERE id=?
    """, (
        validar_precio(request.form["precio_clase"]),
        validar_precio(request.form.get("porcentaje_grupal") or 40),
        request.form["profesor_id"]
    ))
    registrar_auditoria(conn, "pagos", "editar", "profesor", request.form["profesor_id"], "Actualizacion de precio por clase y porcentaje grupal")
    conn.commit()
    conn.close()
    return redirect("/pagos")

@app.route("/registrar_cuota", methods=["POST"])
@roles_required("admin", "comun")
def registrar_cuota():
    conn = get_conn()
    promocion_id = request.form.get("promocion_id") or None
    alumno_id = request.form["alumno_id"]
    anio = int(request.form["anio"])
    mes = int(request.form["mes"])
    metodo_pago = request.form.get("metodo_pago", "").strip()
    monto_normal = validar_precio(request.form["monto_normal"])
    resultado = seleccionar_promociones_aplicables(conn, alumno_id, "cuota", anio, mes, monto_normal, promocion_id, metodo_pago)

    cur = conn.execute("""
        INSERT INTO pagos_alumnos (
            alumno_id, anio, mes, monto_normal, descuento,
            monto_pagado, promocion_id, estado, metodo_pago
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)
    """, (
        alumno_id,
        anio,
        mes,
        monto_normal,
        resultado["descuento"],
        resultado["monto_final"],
        resultado["promocion_id"],
        metodo_pago
    ))
    registrar_usos_promociones(conn, resultado["aplicadas"], alumno_id, "cuota", cur.lastrowid, monto_normal, resultado["monto_final"])
    sincronizar_estado_cuenta_alumno(conn, alumno_id)
    registrar_auditoria(conn, "pagos", "crear", "cuota", cur.lastrowid, f"Cuota {mes}/{anio} registrada por ${resultado['monto_final']:.2f}. Descuento: ${resultado['descuento']:.2f}")
    conn.commit()
    conn.close()
    return redirect("/pagos")

@app.route("/registrar_matricula", methods=["POST"])
@roles_required("admin", "comun")
def registrar_matricula():
    conn = get_conn()
    promocion_id = request.form.get("promocion_id") or None
    alumno_id = request.form["alumno_id"]
    anio = int(request.form["anio"])
    metodo_pago = request.form.get("metodo_pago", "").strip()
    monto_normal = validar_precio(request.form["monto_normal"])
    resultado = seleccionar_promociones_aplicables(conn, alumno_id, "matricula", anio, 1, monto_normal, promocion_id, metodo_pago)

    cur = conn.execute("""
        INSERT INTO matriculas (
            alumno_id, anio, monto_normal, descuento,
            monto_pagado, promocion_id, estado, metodo_pago
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pendiente', ?)
    """, (
        alumno_id,
        anio,
        monto_normal,
        resultado["descuento"],
        resultado["monto_final"],
        resultado["promocion_id"],
        metodo_pago
    ))
    registrar_usos_promociones(conn, resultado["aplicadas"], alumno_id, "matricula", cur.lastrowid, monto_normal, resultado["monto_final"])
    sincronizar_estado_cuenta_alumno(conn, alumno_id)
    registrar_auditoria(conn, "pagos", "crear", "matricula", cur.lastrowid, f"Matricula {anio} registrada por ${resultado['monto_final']:.2f}. Descuento: ${resultado['descuento']:.2f}")
    conn.commit()
    conn.close()
    return redirect("/pagos")

@app.route("/agregar_promocion", methods=["POST"])
@roles_required("admin", "comun")
def agregar_promocion():
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO promociones (
            alumno_id, aplica_alumno_id, nombre, descripcion, tipo,
            porcentaje_descuento, monto_descuento, activa,
            automatica, aplica_cuota, aplica_matricula
        )
        VALUES (?, ?, ?, ?, 'personalizada', ?, ?, 1, 0, 1, 1)
    """, (
        request.form["alumno_id"],
        request.form["alumno_id"],
        request.form["descripcion"],
        request.form["descripcion"],
        validar_precio(request.form.get("porcentaje_descuento")),
        validar_precio(request.form.get("monto_descuento"))
    ))
    registrar_auditoria(conn, "pagos", "crear", "promocion", cur.lastrowid, f"Promocion creada: {request.form['descripcion']}")
    conn.commit()
    conn.close()
    return redirect("/pagos")

@app.route("/marcar_pago_alumno", methods=["POST"])
@roles_required("admin", "comun")
def marcar_pago_alumno():
    data = request.json
    tabla = "matriculas" if data.get("tipo") == "matricula" else "pagos_alumnos"
    estado = "pendiente" if data.get("estado") == "pendiente" else "pagado"
    fecha_pago = datetime.today().strftime("%Y-%m-%d") if estado == "pagado" else None
    conn = get_conn()
    pago = conn.execute(f"SELECT * FROM {tabla} WHERE id=?", (data["id"],)).fetchone()
    monto_real_pagado = validar_precio(data.get("monto_real_pagado")) if data.get("monto_real_pagado") is not None else None
    if estado == "pagado" and monto_real_pagado is None:
        monto_real_pagado = float(pago["monto_pagado"] or 0) if pago else 0
    if estado == "pendiente" and monto_real_pagado is None:
        monto_real_pagado = 0
    if estado == "pagado" and pago and monto_real_pagado < float(pago["monto_pagado"] or 0):
        estado = "parcial"
    conn.execute(f"""
        UPDATE {tabla}
        SET estado=?, fecha_pago=?, monto_real_pagado=?, metodo_pago=?, comprobante=?, observacion_pago=?
        WHERE id=?
    """, (
        estado,
        fecha_pago,
        monto_real_pagado,
        data.get("metodo_pago") or (pago["metodo_pago"] if pago else ""),
        data.get("comprobante") or (pago["comprobante"] if pago else ""),
        data.get("observacion") or (pago["observacion_pago"] if pago else ""),
        data["id"]
    ))
    if pago:
        sincronizar_estado_cuenta_alumno(conn, pago["alumno_id"])
    registrar_auditoria(conn, "pagos", "editar", data.get("tipo") or "cuota", data["id"], f"Pago marcado como {estado}")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "estado": estado, "fecha_pago": fecha_pago})

@app.route("/guardar_colores", methods=["POST"])
@roles_required("admin")
def guardar_colores():
    campos = [
        "nombre_app",
        "color_fondo",
        "color_texto",
        "color_sidebar",
        "color_sidebar_texto",
        "color_tarjeta",
        "color_borde",
        "color_primario",
        "color_exito",
        "color_peligro",
        "radio_bordes"
    ]
    conn = get_conn()
    for campo in campos:
        conn.execute("""
            INSERT INTO configuracion (clave, valor)
            VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
        """, (campo, request.form[campo]))
    registrar_auditoria(conn, "configuracion", "editar", "apariencia", "", "Apariencia del sistema actualizada")
    conn.commit()
    conn.close()
    return redirect(request.referrer or "/")

@app.route("/deudores")
@roles_required("admin", "comun")
def deudores():
    conn = get_conn()
    sincronizar_estado_cuenta_todos(conn)
    deudores_lista = conn.execute("""
        SELECT alumnos.id AS alumno_id, alumnos.apellido_nombre,
               SUM(movimientos_cuenta.debe) - SUM(movimientos_cuenta.haber) AS saldo,
               MIN(CASE WHEN movimientos_cuenta.estado<>'pagado' AND movimientos_cuenta.debe>0 THEN movimientos_cuenta.fecha END) AS deuda_desde,
               MAX(CASE WHEN movimientos_cuenta.categoria='pago' THEN movimientos_cuenta.fecha END) AS ultimo_pago
        FROM alumnos
        JOIN movimientos_cuenta ON movimientos_cuenta.alumno_id = alumnos.id
        WHERE movimientos_cuenta.anulado=0
        GROUP BY alumnos.id
        HAVING saldo > 0
        ORDER BY saldo DESC, alumnos.apellido_nombre
    """).fetchall()
    conceptos_pendientes = conn.execute("""
        SELECT movimientos_cuenta.*, alumnos.apellido_nombre
        FROM movimientos_cuenta
        LEFT JOIN alumnos ON movimientos_cuenta.alumno_id = alumnos.id
        WHERE movimientos_cuenta.anulado=0
          AND movimientos_cuenta.debe > 0
          AND movimientos_cuenta.estado<>'pagado'
        ORDER BY movimientos_cuenta.fecha, alumnos.apellido_nombre
    """).fetchall()
    conn.commit()
    conn.close()
    return render_template(
        "deudores.html",
        deudores_lista=deudores_lista,
        conceptos_pendientes=conceptos_pendientes
    )

# ---------------- AJUSTES MANUALES ----------------

@app.route("/ajustes")
@roles_required("admin")
def ajustes_manuales():
    conn = get_conn()
    filtros = {
        "desde": normalizar_fecha(request.args.get("desde")) or "",
        "hasta": normalizar_fecha(request.args.get("hasta")) or "",
        "categoria": normalizar_categoria_ajuste(request.args.get("categoria")) if request.args.get("categoria") else "",
        "estado": request.args.get("estado") if request.args.get("estado") in ["activo", "anulado"] else "",
        "tipo_ajuste": normalizar_tipo_ajuste(request.args.get("tipo_ajuste")) if request.args.get("tipo_ajuste") else "",
        "alumno_id": validar_entero(request.args.get("alumno_id")),
        "profesor_id": validar_entero(request.args.get("profesor_id"))
    }
    condiciones = []
    valores = []
    if filtros["desde"]:
        condiciones.append("ajustes_manuales.fecha>=?")
        valores.append(filtros["desde"])
    if filtros["hasta"]:
        condiciones.append("ajustes_manuales.fecha<=?")
        valores.append(filtros["hasta"])
    if filtros["categoria"]:
        condiciones.append("ajustes_manuales.categoria=?")
        valores.append(filtros["categoria"])
    if filtros["estado"]:
        condiciones.append("ajustes_manuales.estado=?")
        valores.append(filtros["estado"])
    if filtros["tipo_ajuste"]:
        condiciones.append("ajustes_manuales.tipo_ajuste=?")
        valores.append(filtros["tipo_ajuste"])
    if filtros["alumno_id"]:
        condiciones.append("ajustes_manuales.alumno_id=?")
        valores.append(filtros["alumno_id"])
    if filtros["profesor_id"]:
        condiciones.append("ajustes_manuales.profesor_id=?")
        valores.append(filtros["profesor_id"])
    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    ajustes = conn.execute("""
        SELECT ajustes_manuales.*, alumnos.apellido_nombre AS alumno,
               profesores.nombre_apellido AS profesor
        FROM ajustes_manuales
        LEFT JOIN alumnos ON ajustes_manuales.alumno_id = alumnos.id
        LEFT JOIN profesores ON ajustes_manuales.profesor_id = profesores.id
        """ + where + """
        ORDER BY ajustes_manuales.fecha DESC, ajustes_manuales.id DESC
    """, valores).fetchall()
    resumen = conn.execute("""
        SELECT
            COUNT(*) AS cantidad,
            COALESCE(SUM(CASE WHEN estado='activo' AND signo='positivo' THEN monto ELSE 0 END), 0) AS positivos,
            COALESCE(SUM(CASE WHEN estado='activo' AND signo='negativo' THEN monto ELSE 0 END), 0) AS negativos,
            COUNT(CASE WHEN estado='anulado' THEN 1 END) AS anulados
        FROM ajustes_manuales
    """).fetchone()
    alumnos = conn.execute("SELECT * FROM alumnos ORDER BY apellido_nombre").fetchall()
    profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()
    conn.close()
    return render_template(
        "ajustes.html",
        ajustes=ajustes,
        resumen=resumen,
        filtros=filtros,
        alumnos=alumnos,
        profesores=profesores,
        tipos_ajuste=TIPOS_AJUSTE_MANUAL,
        categorias_ajuste=CATEGORIAS_AJUSTE_MANUAL
    )

@app.route("/guardar_ajuste_manual", methods=["POST"])
@roles_required("admin")
def guardar_ajuste_manual():
    conn = get_conn()
    destino = request.form.get("redirect_to") or "/ajustes"
    try:
        crear_ajuste_manual(
            conn,
            request.form.get("categoria"),
            request.form.get("tipo_ajuste"),
            request.form.get("monto"),
            request.form.get("signo"),
            request.form.get("motivo"),
            request.form.get("observacion"),
            request.form.get("fecha"),
            alumno_id=validar_entero(request.form.get("alumno_id")),
            profesor_id=validar_entero(request.form.get("profesor_id")),
            pago_id=validar_entero(request.form.get("pago_id")),
            liquidacion_id=validar_entero(request.form.get("liquidacion_id")),
            clase_id=validar_entero(request.form.get("clase_id")),
            entidad_relacionada=request.form.get("entidad_relacionada", "").strip()
        )
        conn.commit()
        mensaje = "Ajuste manual registrado correctamente."
        tipo = "success"
    except ValueError as exc:
        mensaje = str(exc)
        tipo = "warning"
    finally:
        conn.close()

    separador = "&" if "?" in destino else "?"
    return redirect(destino + separador + urlencode({"mensaje": mensaje, "tipo": tipo}))

@app.route("/anular_ajuste_manual", methods=["POST"])
@roles_required("admin")
def anular_ajuste_manual_route():
    conn = get_conn()
    destino = request.form.get("redirect_to") or "/ajustes"
    try:
        anular_ajuste_manual(conn, request.form.get("ajuste_id"), request.form.get("motivo_anulacion"))
        conn.commit()
        mensaje = "Ajuste anulado y reversado correctamente."
        tipo = "success"
    except ValueError as exc:
        mensaje = str(exc)
        tipo = "warning"
    finally:
        conn.close()
    separador = "&" if "?" in destino else "?"
    return redirect(destino + separador + urlencode({"mensaje": mensaje, "tipo": tipo}))

@app.route("/ajustes/exportar_csv")
@roles_required("admin")
def exportar_ajustes_csv():
    conn = get_conn()
    ajustes = conn.execute("""
        SELECT ajustes_manuales.*, alumnos.apellido_nombre AS alumno,
               profesores.nombre_apellido AS profesor
        FROM ajustes_manuales
        LEFT JOIN alumnos ON ajustes_manuales.alumno_id = alumnos.id
        LEFT JOIN profesores ON ajustes_manuales.profesor_id = profesores.id
        ORDER BY ajustes_manuales.fecha DESC, ajustes_manuales.id DESC
    """).fetchall()
    registrar_auditoria(conn, "ajustes", "exportar", "csv", "", "Exportacion de ajustes manuales")
    conn.commit()
    conn.close()

    salida = io.StringIO()
    salida.write("\ufeff")
    writer = csv.writer(salida)
    writer.writerow(["Fecha", "Categoria", "Tipo", "Signo", "Monto", "Alumno", "Profesor", "Motivo", "Observacion", "Estado", "Usuario", "Anulacion"])
    for ajuste in ajustes:
        writer.writerow([
            ajuste["fecha"],
            ajuste["categoria"],
            ajuste["tipo_ajuste"],
            ajuste["signo"],
            f"{float(ajuste['monto'] or 0):.2f}",
            ajuste["alumno"] or "",
            ajuste["profesor"] or "",
            ajuste["motivo"],
            ajuste["observacion"],
            ajuste["estado"],
            ajuste["usuario_creador_nombre"],
            ajuste["motivo_anulacion"] or ""
        ])

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Response(
        salida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ajustes_manuales_{fecha}.csv"}
    )

# ---------------- RECUPEROS ----------------

@app.route("/recuperos")
@roles_required("admin", "comun")
def recuperos():
    conn = get_conn()
    actualizar_vencimientos_recuperos(conn)
    alumno_id = validar_entero(request.args.get("alumno_id"))
    profesor_id = validar_entero(request.args.get("profesor_id"))
    estado = request.args.get("estado") if request.args.get("estado") in ESTADOS_RECUPERO else ""
    tipo_recupero = request.args.get("tipo") if request.args.get("tipo") in TIPOS_RECUPERO else ""
    vencidos = request.args.get("vencidos") == "1"

    condiciones = []
    valores = []
    if alumno_id:
        condiciones.append("recuperos.alumno_id=?")
        valores.append(alumno_id)
    if profesor_id:
        condiciones.append("recuperos.profesor_id=?")
        valores.append(profesor_id)
    if estado:
        condiciones.append("recuperos.estado=?")
        valores.append(estado)
    if tipo_recupero:
        condiciones.append("recuperos.tipo=?")
        valores.append(tipo_recupero)
    if vencidos:
        condiciones.append("recuperos.fecha_limite < ? AND recuperos.estado IN ('pendiente', 'programado', 'vencido')")
        valores.append(datetime.now().strftime("%Y-%m-%d"))

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    recuperos_lista = conn.execute("""
        SELECT recuperos.*, alumnos.apellido_nombre AS alumno,
               profesores.nombre_apellido AS profesor,
               original.fecha AS fecha_original,
               recuperacion.fecha AS fecha_recuperacion,
               tipos_clase.nombre AS tipo_clase
        FROM recuperos
        LEFT JOIN alumnos ON recuperos.alumno_id = alumnos.id
        LEFT JOIN profesores ON recuperos.profesor_id = profesores.id
        LEFT JOIN clases original ON recuperos.clase_original_id = original.id
        LEFT JOIN clases recuperacion ON recuperos.clase_recuperacion_id = recuperacion.id
        LEFT JOIN tipos_clase ON original.tipo_clase_id = tipos_clase.id
        """ + where + """
        ORDER BY
            CASE recuperos.estado
                WHEN 'pendiente' THEN 1
                WHEN 'programado' THEN 2
                WHEN 'vencido' THEN 3
                ELSE 4
            END,
            recuperos.fecha_limite,
            recuperos.id DESC
    """, valores).fetchall()

    estadisticas = conn.execute("""
        SELECT
            COUNT(CASE WHEN estado='pendiente' THEN 1 END) AS pendientes,
            COUNT(CASE WHEN estado='programado' THEN 1 END) AS programados,
            COUNT(CASE WHEN estado='realizado' THEN 1 END) AS realizados,
            COUNT(CASE WHEN estado='vencido' THEN 1 END) AS vencidos,
            COALESCE(SUM(costo_adicional), 0) AS costo_adicional
        FROM recuperos
    """).fetchone()
    clases_originales = conn.execute("""
        SELECT clases.id, clases.fecha, profesores.nombre_apellido AS profesor
        FROM clases
        LEFT JOIN profesores ON clases.profesor_id = profesores.id
        ORDER BY clases.fecha DESC
        LIMIT 120
    """).fetchall()
    alumnos = conn.execute("SELECT * FROM alumnos ORDER BY apellido_nombre").fetchall()
    profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()
    tipos_clase = conn.execute("SELECT * FROM tipos_clase ORDER BY id").fetchall()
    conn.commit()
    conn.close()

    return render_template(
        "recuperos.html",
        recuperos=recuperos_lista,
        alumnos=alumnos,
        profesores=profesores,
        tipos_clase=tipos_clase,
        clases_originales=clases_originales,
        estados_recupero=ESTADOS_RECUPERO,
        motivos_recupero=MOTIVOS_RECUPERO,
        tipos_recupero=TIPOS_RECUPERO,
        estadisticas=estadisticas,
        filtros={
            "alumno_id": alumno_id,
            "profesor_id": profesor_id,
            "estado": estado,
            "tipo": tipo_recupero,
            "vencidos": vencidos
        }
    )

@app.route("/guardar_recupero", methods=["POST"])
@roles_required("admin", "comun")
def guardar_recupero():
    conn = get_conn()
    recupero_id = request.form.get("id")
    clase_original_id = validar_entero(request.form.get("clase_original_id"))
    alumno_id = validar_entero(request.form.get("alumno_id"))
    profesor_id = validar_entero(request.form.get("profesor_id"))
    motivo = normalizar_motivo_recupero(request.form.get("motivo"))
    tipo = normalizar_tipo_recupero(request.form.get("tipo"))
    estado = normalizar_estado_recupero(request.form.get("estado"))

    if not alumno_id or not profesor_id:
        conn.close()
        return redirect("/recuperos?" + urlencode({"mensaje": "Selecciona alumno y profesor.", "tipo": "warning"}))

    valores = (
        clase_original_id,
        alumno_id,
        profesor_id,
        motivo,
        request.form.get("motivo_manual", "").strip(),
        tipo,
        estado,
        normalizar_fecha(request.form.get("fecha_limite")),
        1 if request.form.get("afecta_liquidacion") == "1" else 0,
        1 if request.form.get("profesor_cobra") == "1" else 0,
        1 if request.form.get("academia_absorbe") == "1" else 0,
        1 if request.form.get("genera_deuda") == "1" else 0,
        1 if request.form.get("cuenta_asistencia") == "1" else 0,
        1 if request.form.get("consume_cupo") == "1" else 0,
        1 if request.form.get("reutilizable") == "1" else 0,
        validar_precio(request.form.get("costo_adicional")),
        1 if request.form.get("gratuito") == "1" else 0,
        1 if request.form.get("incluido_en_cuota") == "1" else 0,
        request.form.get("observaciones", "").strip(),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    if recupero_id:
        conn.execute("""
            UPDATE recuperos
            SET clase_original_id=?, alumno_id=?, profesor_id=?, motivo=?, motivo_manual=?,
                tipo=?, estado=?, fecha_limite=?, afecta_liquidacion=?, profesor_cobra=?,
                academia_absorbe=?, genera_deuda=?, cuenta_asistencia=?, consume_cupo=?,
                reutilizable=?, costo_adicional=?, gratuito=?, incluido_en_cuota=?,
                observaciones=?, actualizado_en=?
            WHERE id=?
        """, (*valores, recupero_id))
        registrar_auditoria(conn, "recuperos", "editar", "recupero", recupero_id, f"Recupero editado para alumno #{alumno_id}")
    else:
        cur = conn.execute("""
            INSERT INTO recuperos (
                clase_original_id, alumno_id, profesor_id, motivo, motivo_manual,
                tipo, estado, fecha_creacion, fecha_limite, afecta_liquidacion,
                profesor_cobra, academia_absorbe, genera_deuda, cuenta_asistencia,
                consume_cupo, reutilizable, costo_adicional, gratuito, incluido_en_cuota,
                observaciones, creado_por, creado_por_nombre, actualizado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            valores[0], valores[1], valores[2], valores[3], valores[4],
            valores[5], valores[6], valores[19], valores[7], valores[8],
            valores[9], valores[10], valores[11], valores[12], valores[13],
            valores[14], valores[15], valores[16], valores[17], valores[18],
            session.get("usuario_id"), session.get("usuario_nombre"), valores[19]
        ))
        crear_notificacion_recupero(conn, cur.lastrowid, "creacion", "Recupero creado manualmente.", valores[7])
        registrar_auditoria(conn, "recuperos", "crear", "recupero", cur.lastrowid, f"Recupero manual creado para alumno #{alumno_id}")

    conn.commit()
    conn.close()
    return redirect("/recuperos")

@app.route("/programar_recupero", methods=["POST"])
@roles_required("admin", "comun")
def programar_recupero():
    conn = get_conn()
    recupero_id = request.form["recupero_id"]
    recupero = conn.execute("SELECT * FROM recuperos WHERE id=?", (recupero_id,)).fetchone()
    if not recupero:
        conn.close()
        return redirect("/recuperos")

    profesor = request.form.get("profesor_id") or recupero["profesor_id"]
    fecha = request.form.get("fecha")
    duracion = validar_duracion(request.form.get("duracion")) or 1
    tipo_clase_id = request.form.get("tipo_clase_id") or 1
    capacidad = validar_entero(request.form.get("capacidad_maxima")) or 0
    costo_adicional = validar_precio(request.form.get("costo_adicional"))

    ok, error = disponibilidad_profesor(conn, profesor, fecha, duracion)
    if not ok:
        conn.close()
        return redirect("/recuperos?" + urlencode({"mensaje": error, "tipo": "warning"}))

    cur = conn.execute("""
        INSERT INTO clases (
            profesor_id, fecha, duracion, tipo_clase_id, estado, recuperacion_de,
            es_recupero, recupero_id, capacidad_maxima
        )
        VALUES (?, ?, ?, ?, 'programada', ?, 1, ?, ?)
    """, (
        profesor,
        fecha,
        duracion,
        tipo_clase_id,
        recupero["clase_original_id"],
        recupero_id,
        capacidad
    ))
    agregar_alumnos_a_clase(conn, cur.lastrowid, [recupero["alumno_id"]])

    genera_deuda = costo_adicional > 0
    conn.execute("""
        UPDATE recuperos
        SET clase_recuperacion_id=?, profesor_id=?, fecha_programada=?, estado='programado',
            costo_adicional=?, genera_deuda=?, gratuito=?, actualizado_en=?
        WHERE id=?
    """, (
        cur.lastrowid,
        profesor,
        fecha,
        costo_adicional,
        1 if genera_deuda else 0,
        0 if genera_deuda else 1,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        recupero_id
    ))
    if genera_deuda:
        fecha_dt = parsear_fecha(fecha) or datetime.now()
        resultado_promo = seleccionar_promociones_aplicables(
            conn,
            recupero["alumno_id"],
            "cuota",
            fecha_dt.year,
            fecha_dt.month,
            costo_adicional,
            None,
            ""
        )
        pago = conn.execute("""
            INSERT INTO pagos_alumnos (
                alumno_id, anio, mes, monto_normal, descuento,
                monto_pagado, promocion_id, estado, observacion_pago
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)
        """, (
            recupero["alumno_id"],
            fecha_dt.year,
            fecha_dt.month,
            costo_adicional,
            resultado_promo["descuento"],
            resultado_promo["monto_final"],
            resultado_promo["promocion_id"],
            f"Cargo generado por recupero #{recupero_id}"
        ))
        registrar_usos_promociones(conn, resultado_promo["aplicadas"], recupero["alumno_id"], "cuota", pago.lastrowid, costo_adicional, resultado_promo["monto_final"])
        sincronizar_estado_cuenta_alumno(conn, recupero["alumno_id"])
        registrar_auditoria(conn, "pagos", "crear", "recupero", pago.lastrowid, f"Deuda por recupero #{recupero_id}: ${resultado_promo['monto_final']:.2f}")
    crear_notificacion_recupero(conn, recupero_id, "programacion", f"Recupero programado para {fecha}.", fecha)
    registrar_auditoria(conn, "recuperos", "programar", "recupero", recupero_id, f"Recupero programado en clase #{cur.lastrowid} para {fecha}")
    conn.commit()
    conn.close()
    return redirect("/recuperos")

@app.route("/cambiar_estado_recupero", methods=["POST"])
@roles_required("admin", "comun")
def cambiar_estado_recupero():
    conn = get_conn()
    recupero_id = request.form["recupero_id"]
    estado = normalizar_estado_recupero(request.form.get("estado"))
    fecha_realizado = datetime.now().strftime("%Y-%m-%d") if estado == "realizado" else None
    conn.execute("""
        UPDATE recuperos
        SET estado=?, fecha_realizado=COALESCE(?, fecha_realizado), actualizado_en=?
        WHERE id=?
    """, (estado, fecha_realizado, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), recupero_id))
    registrar_auditoria(conn, "recuperos", "estado", "recupero", recupero_id, f"Recupero marcado como {estado}")
    conn.commit()
    conn.close()
    return redirect("/recuperos")

# ---------------- ALUMNOS ----------------

@app.route("/alumnos")
@roles_required("admin")
def alumnos():
    conn = get_conn()

    alumnos = conn.execute("""
        SELECT alumnos.*, profesores.nombre_apellido as tutor_nombre
        FROM alumnos
        LEFT JOIN profesores ON alumnos.tutor_profesor_id = profesores.id
        ORDER BY alumnos.apellido_nombre
    """).fetchall()
    profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()

    conn.close()

    return render_template(
        "alumnos.html",
        alumnos=alumnos,
        profesores=profesores
    )

@app.route("/alumnos/<int:id>")
@roles_required("admin")
def ficha_alumno(id):
    conn = get_conn()

    alumno = conn.execute("""
        SELECT alumnos.*, profesores.nombre_apellido AS tutor_nombre
        FROM alumnos
        LEFT JOIN profesores ON alumnos.tutor_profesor_id = profesores.id
        WHERE alumnos.id=?
    """, (id,)).fetchone()

    if not alumno:
        conn.close()
        return redirect("/alumnos?" + urlencode({
            "mensaje": "No se encontro el alumno solicitado.",
            "tipo": "warning"
        }))

    clases_alumno = conn.execute("""
        SELECT clases.id, clases.fecha, clases.duracion, clases.estado,
               clases.motivo_cancelacion, clase_alumnos.asistencia,
               profesores.nombre_apellido AS profesor,
               tipos_clase.nombre AS tipo_clase
        FROM clase_alumnos
        JOIN clases ON clase_alumnos.clase_id = clases.id
        LEFT JOIN profesores ON clases.profesor_id = profesores.id
        LEFT JOIN tipos_clase ON clases.tipo_clase_id = tipos_clase.id
        WHERE clase_alumnos.alumno_id=?
        ORDER BY clases.fecha DESC
        LIMIT 20
    """, (id,)).fetchall()

    resumen_asistencia = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN asistencia='presente' THEN 1 ELSE 0 END) AS presentes,
            SUM(CASE WHEN asistencia='ausente' THEN 1 ELSE 0 END) AS ausentes,
            SUM(CASE WHEN asistencia='aviso' THEN 1 ELSE 0 END) AS avisos,
            SUM(CASE WHEN asistencia='recupera' THEN 1 ELSE 0 END) AS recuperaciones,
            SUM(CASE WHEN asistencia='pendiente' OR asistencia IS NULL THEN 1 ELSE 0 END) AS pendientes
        FROM clase_alumnos
        WHERE alumno_id=?
    """, (id,)).fetchone()

    cuotas = conn.execute("""
        SELECT pagos_alumnos.*, COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) AS promocion
        FROM pagos_alumnos
        LEFT JOIN promociones ON pagos_alumnos.promocion_id = promociones.id
        WHERE pagos_alumnos.alumno_id=?
        ORDER BY pagos_alumnos.anio DESC, pagos_alumnos.mes DESC
    """, (id,)).fetchall()

    matriculas = conn.execute("""
        SELECT matriculas.*, COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) AS promocion
        FROM matriculas
        LEFT JOIN promociones ON matriculas.promocion_id = promociones.id
        WHERE matriculas.alumno_id=?
        ORDER BY matriculas.anio DESC
    """, (id,)).fetchall()

    promociones = conn.execute("""
        SELECT *
        FROM promociones
        WHERE (alumno_id=? OR aplica_alumno_id=?) AND eliminada=0
        ORDER BY activa DESC, id DESC
    """, (id, id)).fetchall()

    promociones_usadas = conn.execute("""
        SELECT promocion_usos.*, COALESCE(NULLIF(promociones.nombre, ''), promociones.descripcion) AS promocion
        FROM promocion_usos
        LEFT JOIN promociones ON promocion_usos.promocion_id = promociones.id
        WHERE promocion_usos.alumno_id=?
        ORDER BY promocion_usos.fecha DESC, promocion_usos.id DESC
    """, (id,)).fetchall()

    recuperos_alumno = conn.execute("""
        SELECT recuperos.*, profesores.nombre_apellido AS profesor,
               original.fecha AS fecha_original,
               recuperacion.fecha AS fecha_recuperacion
        FROM recuperos
        LEFT JOIN profesores ON recuperos.profesor_id = profesores.id
        LEFT JOIN clases original ON recuperos.clase_original_id = original.id
        LEFT JOIN clases recuperacion ON recuperos.clase_recuperacion_id = recuperacion.id
        WHERE recuperos.alumno_id=?
        ORDER BY recuperos.fecha_creacion DESC, recuperos.id DESC
    """, (id,)).fetchall()

    filtros_cuenta = {
        "desde": normalizar_fecha(request.args.get("cuenta_desde")),
        "hasta": normalizar_fecha(request.args.get("cuenta_hasta")),
        "tipo_movimiento": request.args.get("cuenta_tipo") if request.args.get("cuenta_tipo") in ["cargo", "credito"] else "",
        "metodo_pago": request.args.get("cuenta_metodo", "").strip(),
        "estado": request.args.get("cuenta_estado", "").strip(),
        "concepto": request.args.get("cuenta_concepto", "").strip(),
        "solo": request.args.get("cuenta_solo", "").strip()
    }
    movimientos_cuenta, resumen_cuenta = obtener_estado_cuenta_alumno(conn, id, filtros_cuenta)
    ajustes_alumno = conn.execute("""
        SELECT *
        FROM ajustes_manuales
        WHERE alumno_id=?
        ORDER BY fecha DESC, id DESC
        LIMIT 30
    """, (id,)).fetchall()

    deuda_cuotas = conn.execute("""
        SELECT COALESCE(SUM(monto_pagado), 0) AS total
        FROM pagos_alumnos
        WHERE alumno_id=? AND estado<>'pagado'
    """, (id,)).fetchone()["total"]

    deuda_matriculas = conn.execute("""
        SELECT COALESCE(SUM(monto_pagado), 0) AS total
        FROM matriculas
        WHERE alumno_id=? AND estado<>'pagado'
    """, (id,)).fetchone()["total"]

    conn.commit()
    conn.close()

    asistencia = {
        "total": resumen_asistencia["total"] or 0,
        "presentes": resumen_asistencia["presentes"] or 0,
        "ausentes": resumen_asistencia["ausentes"] or 0,
        "avisos": resumen_asistencia["avisos"] or 0,
        "recuperaciones": resumen_asistencia["recuperaciones"] or 0,
        "pendientes": resumen_asistencia["pendientes"] or 0
    }
    asistencia["porcentaje"] = round((asistencia["presentes"] / asistencia["total"]) * 100, 1) if asistencia["total"] else 0

    return render_template(
        "alumno_ficha.html",
        alumno=alumno,
        clases_alumno=clases_alumno,
        asistencia=asistencia,
        cuotas=cuotas,
        matriculas=matriculas,
        promociones=promociones,
        promociones_usadas=promociones_usadas,
        recuperos_alumno=recuperos_alumno,
        movimientos_cuenta=movimientos_cuenta,
        resumen_cuenta=resumen_cuenta,
        ajustes_alumno=ajustes_alumno,
        filtros_cuenta=filtros_cuenta,
        deuda_total=round(float(deuda_cuotas or 0) + float(deuda_matriculas or 0), 2)
    )

@app.route("/alumnos/<int:id>/movimiento_cuenta", methods=["POST"])
@roles_required("admin")
def agregar_movimiento_cuenta(id):
    conn = get_conn()
    alumno = conn.execute("SELECT id FROM alumnos WHERE id=?", (id,)).fetchone()
    if not alumno:
        conn.close()
        return redirect("/alumnos")

    tipo_movimiento = request.form.get("tipo_movimiento") if request.form.get("tipo_movimiento") in ["cargo", "credito"] else "cargo"
    monto = validar_precio(request.form.get("monto"))
    if monto <= 0:
        conn.close()
        return redirect(f"/alumnos/{id}?" + urlencode({"mensaje": "El movimiento necesita un monto mayor a cero.", "tipo": "warning"}))

    try:
        crear_ajuste_manual(
            conn,
            "alumno",
            request.form.get("tipo_ajuste") or request.form.get("categoria"),
            monto,
            "positivo" if tipo_movimiento == "cargo" else "negativo",
            request.form.get("concepto", "").strip() or request.form.get("motivo", "").strip(),
            request.form.get("observacion", "").strip(),
            request.form.get("fecha"),
            alumno_id=id,
            entidad_relacionada=f"alumno:{id}"
        )
        conn.commit()
    except ValueError as exc:
        conn.close()
        return redirect(f"/alumnos/{id}?" + urlencode({"mensaje": str(exc), "tipo": "warning"}))
    conn.close()
    return redirect(f"/alumnos/{id}")

@app.route("/movimiento_cuenta/anular", methods=["POST"])
@roles_required("admin")
def anular_movimiento_cuenta():
    movimiento_id = request.form["movimiento_id"]
    motivo = request.form.get("motivo", "").strip()
    conn = get_conn()
    movimiento = conn.execute("SELECT * FROM movimientos_cuenta WHERE id=?", (movimiento_id,)).fetchone()
    if movimiento:
        conn.execute("""
            UPDATE movimientos_cuenta
            SET anulado=1, estado='anulado', usuario_modificador_id=?,
                usuario_modificador_nombre=?, fecha_modificacion=?, motivo_modificacion=?
            WHERE id=?
        """, (
            session.get("usuario_id"),
            session.get("usuario_nombre"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            motivo,
            movimiento_id
        ))
        recalcular_saldos_alumno(conn, movimiento["alumno_id"])
        registrar_auditoria(conn, "estado_cuenta", "anular", "movimiento", movimiento_id, motivo or "Movimiento anulado")
        alumno_id = movimiento["alumno_id"]
    else:
        alumno_id = ""
    conn.commit()
    conn.close()
    return redirect(f"/alumnos/{alumno_id}" if alumno_id else "/alumnos")

@app.route("/alumnos/<int:id>/estado_cuenta_csv")
@roles_required("admin", "comun")
def exportar_estado_cuenta_csv(id):
    conn = get_conn()
    alumno = conn.execute("SELECT * FROM alumnos WHERE id=?", (id,)).fetchone()
    if not alumno:
        conn.close()
        return redirect("/alumnos")
    movimientos, resumen = obtener_estado_cuenta_alumno(conn, id, {})
    conn.commit()
    conn.close()

    salida = io.StringIO()
    salida.write("\ufeff")
    writer = csv.writer(salida)
    writer.writerow(["Fecha", "Concepto", "Tipo", "Debe", "Haber", "Saldo", "Metodo", "Comprobante", "Estado", "Observacion", "Usuario"])
    for mov in movimientos:
        writer.writerow([
            mov["fecha"],
            mov["concepto"],
            mov["tipo_movimiento"],
            f"{float(mov['debe'] or 0):.2f}",
            f"{float(mov['haber'] or 0):.2f}",
            f"{float(mov['saldo_acumulado'] or 0):.2f}",
            mov["metodo_pago"] or "",
            mov["comprobante"] or "",
            mov["estado"] or "",
            mov["observacion"] or "",
            mov["usuario_creador_nombre"] or ""
        ])

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Response(
        salida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=estado_cuenta_{alumno['id']}_{fecha}.csv"}
    )

@app.route("/alumnos/<int:id>/estado_cuenta_pdf")
@roles_required("admin", "comun")
def estado_cuenta_pdf(id):
    conn = get_conn()
    alumno = conn.execute("SELECT * FROM alumnos WHERE id=?", (id,)).fetchone()
    if not alumno:
        conn.close()
        return redirect("/alumnos")
    movimientos, resumen = obtener_estado_cuenta_alumno(conn, id, {})
    configuracion = obtener_configuracion(conn)
    conn.commit()
    conn.close()
    return render_template(
        "estado_cuenta_pdf.html",
        alumno=alumno,
        movimientos=movimientos,
        resumen=resumen,
        configuracion=configuracion,
        fecha=datetime.now().strftime("%Y-%m-%d")
    )

@app.route("/agregar_alumno", methods=["POST"])
@roles_required("admin")
def agregar_alumno():
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO alumnos (
            apellido_nombre, dni, fecha_nacimiento, dia_inscripcion,
            edad, telefono, direccion, email, tutor_profesor_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["apellido_nombre"],
        request.form["dni"],
        request.form["fecha_nacimiento"],
        request.form["dia_inscripcion"],
        request.form["edad"],
        request.form["telefono"],
        request.form["direccion"],
        request.form["email"],
        request.form.get("tutor_profesor_id") or None
    ))
    registrar_auditoria(conn, "alumnos", "crear", "alumno", cur.lastrowid, f"Alumno creado: {request.form['apellido_nombre']}")
    conn.commit()
    conn.close()
    return redirect("/alumnos")

@app.route("/editar_alumno", methods=["POST"])
@roles_required("admin")
def editar_alumno():
    conn = get_conn()
    conn.execute("""
        UPDATE alumnos
        SET apellido_nombre=?, dni=?, fecha_nacimiento=?, dia_inscripcion=?,
            edad=?, telefono=?, direccion=?, email=?, tutor_profesor_id=?
        WHERE id=?
    """, (
        request.form["apellido_nombre"],
        request.form["dni"],
        request.form["fecha_nacimiento"],
        request.form["dia_inscripcion"],
        request.form["edad"],
        request.form["telefono"],
        request.form["direccion"],
        request.form["email"],
        request.form.get("tutor_profesor_id") or None,
        request.form["id"]
    ))
    registrar_auditoria(conn, "alumnos", "editar", "alumno", request.form["id"], f"Alumno editado: {request.form['apellido_nombre']}")
    conn.commit()
    conn.close()
    return redirect("/alumnos")

@app.route("/eliminar_alumno/<int:id>")
@roles_required("admin")
def eliminar_alumno(id):
    conn = get_conn()
    alumno = conn.execute("SELECT apellido_nombre FROM alumnos WHERE id=?", (id,)).fetchone()
    conn.execute("DELETE FROM alumnos WHERE id=?", (id,))
    registrar_auditoria(conn, "alumnos", "eliminar", "alumno", id, f"Alumno eliminado: {alumno['apellido_nombre'] if alumno else id}")
    conn.commit()
    conn.close()
    return redirect("/alumnos")

# ---------------- CLASES ----------------

@app.route("/clases")
@login_required
def clases():
    conn = get_conn()

    actualizar_vencimientos_recuperos(conn)
    profesor_actual_id = profesor_id_usuario_actual(conn)
    filtro_profesor_sql = "WHERE clases.profesor_id=?" if profesor_actual_id else ""
    filtro_profesor_valores = [profesor_actual_id] if profesor_actual_id else []
    clases_db = conn.execute("""
        SELECT clases.*, profesores.nombre_apellido as profesor,
               profesores.color as color, tipos_clase.nombre as tipo_clase,
               recuperos.estado AS recupero_estado,
               recuperos.motivo AS recupero_motivo,
               recuperos.profesor_cobra AS recupero_profesor_cobra,
               recuperos.afecta_liquidacion AS recupero_afecta_liquidacion
        FROM clases
        LEFT JOIN profesores ON clases.profesor_id = profesores.id
        LEFT JOIN tipos_clase ON clases.tipo_clase_id = tipos_clase.id
        LEFT JOIN recuperos ON clases.recupero_id = recuperos.id
        """ + filtro_profesor_sql + """
    """, filtro_profesor_valores).fetchall()

    if profesor_actual_id:
        alumnos = conn.execute("""
            SELECT DISTINCT alumnos.*
            FROM alumnos
            JOIN clase_alumnos ON clase_alumnos.alumno_id = alumnos.id
            JOIN clases ON clase_alumnos.clase_id = clases.id
            WHERE clases.profesor_id=?
            ORDER BY alumnos.apellido_nombre
        """, (profesor_actual_id,)).fetchall()
        profesores = conn.execute("SELECT * FROM profesores WHERE id=? ORDER BY nombre_apellido", (profesor_actual_id,)).fetchall()
    else:
        alumnos = conn.execute("SELECT * FROM alumnos ORDER BY apellido_nombre").fetchall()
        profesores = conn.execute("SELECT * FROM profesores ORDER BY nombre_apellido").fetchall()
    tipos_clase = conn.execute("SELECT * FROM tipos_clase ORDER BY id").fetchall()
    clases_recuperables = conn.execute("""
        SELECT clases.id, clases.fecha, clases.estado, profesores.nombre_apellido as profesor
        FROM clases
        LEFT JOIN profesores ON clases.profesor_id = profesores.id
        WHERE clases.estado='cancelada'
          AND (? IS NULL OR clases.profesor_id=?)
        ORDER BY clases.fecha DESC
    """, (profesor_actual_id, profesor_actual_id)).fetchall()
    recuperos_pendientes = conn.execute("""
        SELECT recuperos.*, alumnos.apellido_nombre AS alumno,
               profesores.nombre_apellido AS profesor,
               original.fecha AS fecha_original
        FROM recuperos
        LEFT JOIN alumnos ON recuperos.alumno_id = alumnos.id
        LEFT JOIN profesores ON recuperos.profesor_id = profesores.id
        LEFT JOIN clases original ON recuperos.clase_original_id = original.id
        WHERE recuperos.estado IN ('pendiente', 'programado', 'vencido')
          AND (? IS NULL OR recuperos.profesor_id=?)
        ORDER BY recuperos.fecha_limite, recuperos.id DESC
        LIMIT 20
    """, (profesor_actual_id, profesor_actual_id)).fetchall()

    eventos = []

    for c in clases_db:

        alumnos_clase = conn.execute("""
            SELECT alumnos.id, alumnos.apellido_nombre, clase_alumnos.asistencia
            FROM clase_alumnos
            JOIN alumnos ON clase_alumnos.alumno_id = alumnos.id
            WHERE clase_alumnos.clase_id = ?
        """, (c["id"],)).fetchall()

        lista = []
        for a in alumnos_clase:
            lista.append({
                "id": a["id"],
                "nombre": a["apellido_nombre"],
                "asistencia": a["asistencia"] or "pendiente"
            })

        cantidad_alumnos = len(lista)
        texto_alumnos = "alumno" if cantidad_alumnos == 1 else "alumnos"
        profesor = c["profesor"] or "Sin profesor"
        fecha_fin = None
        fecha_inicio = parsear_fecha(c["fecha"]) if c["fecha"] else None
        fecha_inicio_texto = c["fecha"]

        if fecha_inicio:
            fecha_inicio_texto = fecha_inicio.isoformat(timespec="minutes")

        if fecha_inicio and c["duracion"]:
            fecha_fin = (fecha_inicio + timedelta(hours=float(c["duracion"]))).isoformat(timespec="minutes")

        eventos.append({
            "id": c["id"],
            "title": f"{profesor} ({cantidad_alumnos} {texto_alumnos})",
            "start": fecha_inicio_texto,
            "end": fecha_fin,
            "color": c["color"],
            "profesor_id": c["profesor_id"],
            "profesor": profesor,
            "duracion": c["duracion"],
            "tipo_clase_id": c["tipo_clase_id"] or 1,
            "tipo_clase": c["tipo_clase"] or "individual",
            "estado": c["estado"] or "programada",
            "motivo_cancelacion": c["motivo_cancelacion"] or "",
            "recuperacion_de": c["recuperacion_de"],
            "es_recupero": int(c["es_recupero"] or 0),
            "recupero_id": c["recupero_id"],
            "recupero_estado": c["recupero_estado"],
            "recupero_motivo": c["recupero_motivo"],
            "cantidad_alumnos": cantidad_alumnos,
            "alumnos": lista
        })

    conn.close()

    return render_template(
        "clases.html",
        alumnos=alumnos,
        profesores=profesores,
        tipos_clase=tipos_clase,
        clases_recuperables=clases_recuperables,
        recuperos_pendientes=recuperos_pendientes,
        eventos_json=json.dumps(eventos),
        mensaje=request.args.get("mensaje"),
        tipo=request.args.get("tipo", "success"),
        estados_clase=ESTADOS_CLASE,
        estados_asistencia=ESTADOS_ASISTENCIA,
        motivos_cancelacion=MOTIVOS_CANCELACION
    )

# ---------------- CREAR CLASE ----------------

@app.route("/agregar_clase", methods=["POST"])
@roles_required("admin", "comun")
def agregar_clase():
    conn = get_conn()

    profesor = request.form["profesor"]
    fecha = request.form["fecha"]
    duracion = validar_duracion(request.form["duracion"])
    tipo_clase_id = request.form.get("tipo_clase_id") or 1
    estado = normalizar_estado(request.form.get("estado"), ESTADOS_CLASE, "programada")
    motivo_cancelacion = normalizar_motivo(request.form.get("motivo_cancelacion"))
    recuperacion_de = normalizar_recuperacion(request.form.get("recuperacion_de"))

    if not existe_profesor(conn, profesor):
        conn.close()
        return redirect_clases("Selecciona un profesor valido.", "danger")

    if not validar_fecha(fecha) or not duracion:
        conn.close()
        return redirect_clases("Revisa la fecha y la duracion de la clase.", "danger")

    if estado != "cancelada" and clase_duplicada(conn, profesor, fecha):
        conn.close()
        return redirect_clases("Ya existe una clase de ese profesor en ese horario.", "warning")

    conflicto = hay_solapamiento(conn, profesor, fecha, duracion) if estado != "cancelada" else None
    if conflicto:
        conn.close()
        return redirect_clases("Ese profesor ya tiene una clase que se cruza con ese horario.", "warning")

    cur = conn.execute("""
        INSERT INTO clases (profesor_id, fecha, duracion, tipo_clase_id, estado, motivo_cancelacion, recuperacion_de)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        profesor,
        fecha,
        duracion,
        tipo_clase_id,
        estado,
        motivo_cancelacion if estado == "cancelada" else "",
        recuperacion_de
    ))
    alumnos_seleccionados = request.form.getlist("alumnos")
    agregar_alumnos_a_clase(conn, cur.lastrowid, alumnos_seleccionados)
    if recuperacion_de and alumnos_seleccionados:
        conn.execute("""
            UPDATE clases
            SET es_recupero=1
            WHERE id=?
        """, (cur.lastrowid,))
        for alumno_id in alumnos_seleccionados:
            recupero_id = crear_recupero_si_no_existe(
                conn,
                recuperacion_de,
                alumno_id,
                "suspension_administrativa",
                "reprogramacion",
                observaciones="Vinculado desde la creacion de una clase recuperatoria."
            )
            conn.execute("""
                UPDATE recuperos
                SET clase_recuperacion_id=?, fecha_programada=?, estado='programado', actualizado_en=?
                WHERE id=?
            """, (cur.lastrowid, fecha, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), recupero_id))
            conn.execute("UPDATE clases SET recupero_id=? WHERE id=?", (recupero_id, cur.lastrowid))
    registrar_auditoria(conn, "clases", "crear", "clase", cur.lastrowid, f"Clase creada para profesor #{profesor} el {fecha}")
    conn.commit()
    conn.close()
    return redirect_clases("Clase creada correctamente.")

@app.route("/editar_clase", methods=["POST"])
@roles_required("admin", "comun")
def editar_clase():
    conn = get_conn()
    clase_id = request.form["clase_id"]
    profesor = request.form["profesor"]
    fecha = request.form["fecha"]
    duracion = validar_duracion(request.form["duracion"])
    tipo_clase_id = request.form.get("tipo_clase_id") or 1
    estado = normalizar_estado(request.form.get("estado"), ESTADOS_CLASE, "programada")
    motivo_cancelacion = normalizar_motivo(request.form.get("motivo_cancelacion"))
    recuperacion_de = normalizar_recuperacion(request.form.get("recuperacion_de"))

    if not existe_profesor(conn, profesor):
        conn.close()
        return redirect_clases("Selecciona un profesor valido.", "danger")

    if not validar_fecha(fecha) or not duracion:
        conn.close()
        return redirect_clases("Revisa la fecha y la duracion de la clase.", "danger")

    if estado != "cancelada" and clase_duplicada(conn, profesor, fecha, clase_id):
        conn.close()
        return redirect_clases("Ya existe otra clase de ese profesor en ese horario.", "warning")

    conflicto = hay_solapamiento(conn, profesor, fecha, duracion, clase_id) if estado != "cancelada" else None
    if conflicto:
        conn.close()
        return redirect_clases("Ese profesor ya tiene otra clase que se cruza con ese horario.", "warning")

    conn.execute("""
        UPDATE clases
        SET profesor_id=?, fecha=?, duracion=?, tipo_clase_id=?, estado=?, motivo_cancelacion=?, recuperacion_de=?
        WHERE id=?
    """, (
        profesor,
        fecha,
        duracion,
        tipo_clase_id,
        estado,
        motivo_cancelacion if estado == "cancelada" else "",
        recuperacion_de,
        clase_id
    ))

    conn.execute("DELETE FROM clase_alumnos WHERE clase_id=?", (clase_id,))
    agregar_alumnos_a_clase(conn, clase_id, request.form.getlist("alumnos"))
    registrar_auditoria(conn, "clases", "editar", "clase", clase_id, f"Clase editada para profesor #{profesor} el {fecha}")

    conn.commit()
    conn.close()
    return redirect_clases("Clase actualizada correctamente.")

# ---------------- CLASES AUTOMÁTICAS ----------------

@app.route("/clases_repetidas", methods=["POST"])
@roles_required("admin", "comun")
def clases_repetidas():
    conn = get_conn()

    profesor = request.form["profesor"]
    duracion = validar_duracion(request.form["duracion"])
    tipo_clase_id = request.form.get("tipo_clase_id") or 1
    dia = int(request.form["dia"])
    hora = request.form["hora"]
    inicio_form = request.form.get("inicio")
    fin_form = request.form.get("fin")
    cada_semana = int(request.form.get("cada_semana") or 1)
    alumnos = request.form.getlist("alumnos")

    if not existe_profesor(conn, profesor) or not duracion or not hora:
        conn.close()
        return redirect_clases("Revisa profesor, hora y duracion para crear clases automaticas.", "danger")

    if cada_semana < 1:
        cada_semana = 1

    hoy = datetime.today().date()
    inicio = datetime.fromisoformat(inicio_form).date() if inicio_form else hoy
    fin = datetime.fromisoformat(fin_form).date() if fin_form else hoy + timedelta(days=30)

    if fin < inicio:
        conn.close()
        return redirect_clases("La fecha de fin no puede ser anterior al inicio.", "danger")

    fecha = inicio
    creadas = 0
    omitidas = 0
    cruzadas = 0

    while fecha <= fin:
        semanas = (fecha - inicio).days // 7
        if fecha.weekday() == dia and semanas % cada_semana == 0:
            fecha_str = fecha.strftime("%Y-%m-%d") + "T" + hora

            existe = conn.execute("""
                SELECT id FROM clases
                WHERE profesor_id=? AND fecha=?
            """, (profesor, fecha_str)).fetchone()

            conflicto = hay_solapamiento(conn, profesor, fecha_str, duracion)

            if not existe and not conflicto:
                cur = conn.execute("""
                    INSERT INTO clases (profesor_id, fecha, duracion, tipo_clase_id)
                    VALUES (?, ?, ?, ?)
                """, (profesor, fecha_str, duracion, tipo_clase_id))
                agregar_alumnos_a_clase(conn, cur.lastrowid, alumnos)
                creadas += 1
            elif conflicto:
                cruzadas += 1
            else:
                omitidas += 1

        fecha += timedelta(days=1)

    conn.commit()
    registrar_auditoria(conn, "clases", "crear", "clases", "", f"Clases automaticas creadas: {creadas}. Duplicadas: {omitidas}. Cruces: {cruzadas}")
    conn.commit()
    conn.close()
    return redirect_clases(f"Clases creadas: {creadas}. Duplicadas omitidas: {omitidas}. Cruces omitidos: {cruzadas}.")

# ---------------- AJAX ----------------

@app.route("/toggle_asistencia", methods=["POST"])
@login_required
def toggle_asistencia():
    data = request.json
    conn = get_conn()
    ok_permiso, error_permiso = puede_modificar_asistencia_clase(conn, data["clase"])
    if not ok_permiso:
        conn.close()
        return jsonify({"ok": False, "error": error_permiso}), 403

    actual = conn.execute("""
        SELECT asistencia FROM clase_alumnos
        WHERE clase_id=? AND alumno_id=?
    """, (data["clase"], data["alumno"])).fetchone()

    if not actual:
        conn.close()
        return jsonify({"ok": False, "error": "Alumno no asignado a la clase"}), 404

    actual_valor = actual["asistencia"] or "pendiente"
    nuevo = "pendiente" if actual_valor == "presente" else "presente"

    conn.execute("""
        UPDATE clase_alumnos
        SET asistencia=?
        WHERE clase_id=? AND alumno_id=?
    """, (nuevo, data["clase"], data["alumno"]))
    registrar_auditoria(conn, "clases", "asistencia", "clase", data["clase"], f"Alumno #{data['alumno']} marcado como {nuevo}")

    conn.commit()
    conn.close()

    return jsonify({"nuevo": nuevo})

@app.route("/cambiar_asistencia", methods=["POST"])
@login_required
def cambiar_asistencia():
    data = request.json
    estado = normalizar_estado(data.get("estado"), ESTADOS_ASISTENCIA, "pendiente")
    conn = get_conn()
    ok_permiso, error_permiso = puede_modificar_asistencia_clase(conn, data["clase"])
    if not ok_permiso:
        conn.close()
        return jsonify({"ok": False, "error": error_permiso}), 403

    conn.execute("""
        UPDATE clase_alumnos
        SET asistencia=?
        WHERE clase_id=? AND alumno_id=?
    """, (estado, data["clase"], data["alumno"]))
    registrar_auditoria(conn, "clases", "asistencia", "clase", data["clase"], f"Alumno #{data['alumno']} marcado como {estado}")
    if estado in ["ausente", "aviso"]:
        crear_recupero_si_no_existe(
            conn,
            data["clase"],
            data["alumno"],
            "falta_alumno",
            "individual",
            profesor_cobra=True,
            academia_absorbe=True,
            observaciones="Sugerido automaticamente por asistencia ausente/con aviso."
        )

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "estado": estado})

@app.route("/mover_clase", methods=["POST"])
@roles_required("admin", "comun")
def mover_clase():
    data = request.json
    conn = get_conn()

    clase = conn.execute("""
        SELECT id, profesor_id, duracion, estado FROM clases
        WHERE id=?
    """, (data["clase"],)).fetchone()

    nueva_fecha = data.get("fecha")

    if not clase or not validar_fecha(nueva_fecha):
        conn.close()
        return jsonify({"ok": False, "error": "Fecha invalida"}), 400

    if clase["estado"] != "cancelada" and clase_duplicada(conn, clase["profesor_id"], nueva_fecha, clase["id"]):
        conn.close()
        return jsonify({"ok": False, "error": "Ya existe una clase de ese profesor en ese horario"}), 409

    conflicto = hay_solapamiento(conn, clase["profesor_id"], nueva_fecha, clase["duracion"], clase["id"]) if clase["estado"] != "cancelada" else None
    if conflicto:
        conn.close()
        return jsonify({"ok": False, "error": "Ese profesor ya tiene una clase que se cruza con ese horario"}), 409

    conn.execute("""
        UPDATE clases
        SET fecha=?
        WHERE id=?
    """, (nueva_fecha, clase["id"]))
    registrar_auditoria(conn, "clases", "mover", "clase", clase["id"], f"Clase movida a {nueva_fecha}")

    conn.commit()
    conn.close()

    return jsonify({"ok": True})

@app.route("/cambiar_estado_clase", methods=["POST"])
@roles_required("admin", "comun")
def cambiar_estado_clase():
    data = request.json
    estado = normalizar_estado(data.get("estado"), ESTADOS_CLASE, "programada")
    conn = get_conn()

    conn.execute("""
        UPDATE clases
        SET estado=?
        WHERE id=?
    """, (estado, data["clase"]))
    registrar_auditoria(conn, "clases", "editar", "clase", data["clase"], f"Estado cambiado a {estado}")

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "estado": estado})

@app.route("/cancelar_clase", methods=["POST"])
@roles_required("admin", "comun")
def cancelar_clase():
    data = request.json
    motivo = normalizar_motivo(data.get("motivo"))
    conn = get_conn()

    conn.execute("""
        UPDATE clases
        SET estado='cancelada', motivo_cancelacion=?
        WHERE id=?
    """, (motivo, data["clase"]))
    recuperos_creados = crear_recuperos_por_clase_cancelada(conn, data["clase"], motivo)
    registrar_auditoria(conn, "clases", "cancelar", "clase", data["clase"], f"Clase cancelada. Motivo: {motivo or 'sin motivo'}")

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "estado": "cancelada", "motivo": motivo, "recuperos": recuperos_creados})

@app.route("/eliminar_alumno_clase", methods=["POST"])
@roles_required("admin", "comun")
def eliminar_alumno_clase():
    data = request.json
    conn = get_conn()

    conn.execute("""
        DELETE FROM clase_alumnos
        WHERE clase_id=? AND alumno_id=?
    """, (data["clase"], data["alumno"]))
    registrar_auditoria(conn, "clases", "editar", "clase", data["clase"], f"Alumno #{data['alumno']} quitado de la clase")

    conn.commit()
    conn.close()

    return jsonify({"ok": True})

@app.route("/eliminar_clase", methods=["POST"])
@roles_required("admin", "comun")
def eliminar_clase():
    data = request.json
    conn = get_conn()

    conn.execute("DELETE FROM clases WHERE id=?", (data["clase"],))
    conn.execute("DELETE FROM clase_alumnos WHERE clase_id=?", (data["clase"],))
    registrar_auditoria(conn, "clases", "eliminar", "clase", data["clase"], "Clase eliminada")

    conn.commit()
    conn.close()

    return jsonify({"ok": True})

@app.route("/agregar_alumnos_clase", methods=["POST"])
@roles_required("admin", "comun")
def agregar_alumnos_clase():
    conn = get_conn()

    clase_id = request.form["clase_id"]
    alumnos = request.form.getlist("alumnos")
    agregar_alumnos_a_clase(conn, clase_id, alumnos)
    registrar_auditoria(conn, "clases", "editar", "clase", clase_id, f"Alumnos agregados: {len(alumnos)}")

    conn.commit()
    conn.close()

    return jsonify({"ok": True})

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
    
    
