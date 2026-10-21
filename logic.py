# -*- coding: utf-8 -*-
"""
Toolteach (versión Android) - Lógica de datos.

Este módulo NO contiene interfaz gráfica: solo la base de datos, la seguridad, los cálculos
y la exportación/importación. Es la misma lógica del programa de escritorio (Tkinter), para que
los archivos exportados de un lado se puedan importar del otro.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import string
import struct
import tempfile
import time
import unicodedata
import zipfile
from contextlib import contextmanager
from datetime import date, datetime
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------------------
MUNICIPIOS_CAMAGUEY = [
    "Camagüey", "Carlos Manuel de Céspedes", "Esmeralda", "Florida", "Guáimaro",
    "Jimaguayú", "Minas", "Najasa", "Nuevitas", "Santa Cruz del Sur",
    "Sibanicú", "Sierra de Cubitas", "Vertientes"
]
SEXOS = ["Masculino", "Femenino"]
ANNOS_CARRERA = ["1ro", "2do", "3ro", "4to"]
NOTAS = ["2", "3", "4", "5"]
AUSENCIAS = [str(i) for i in range(101)]
ASISTENCIA_OPCIONES = ["Presente", "Ausente"]

# Misma frase que el programa de escritorio: así los respaldos (.db cifrados) son intercambiables.
_FRASE_SECRETA_CIFRADO = b"Toolteach-Clave-Secreta-2026-Cambiar-Si-Se-Desea"
CLAVE_CIFRADO_BD = base64.urlsafe_b64encode(hashlib.sha256(_FRASE_SECRETA_CIFRADO).digest())

DB_PATH = 'estudiantes.db'


class ErrorApp(Exception):
    """Error de validación o de uso con un mensaje listo para mostrar al usuario."""


def set_db_path(ruta):
    global DB_PATH
    DB_PATH = ruta


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------------------
# Cifrado compatible con Fernet (AES-128-CBC + HMAC-SHA256), sin depender de "cryptography"
# --------------------------------------------------------------------------------------
def _construir_tablas_aes():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09
        q &= 0xFF

        def rotl8(x, n):
            return ((x << n) | (x >> (8 - n))) & 0xFF
        sbox[p] = (q ^ rotl8(q, 1) ^ rotl8(q, 2) ^ rotl8(q, 3) ^ rotl8(q, 4) ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i

    def mul(a, b):
        r = 0
        while b:
            if b & 1:
                r ^= a
            a = ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF
            b >>= 1
        return r

    def ror8(w):
        return ((w >> 8) | ((w & 0xFF) << 24)) & 0xFFFFFFFF

    te0, td0 = [], []
    for x in range(256):
        s = sbox[x]
        te0.append((mul(s, 2) << 24) | (s << 16) | (s << 8) | mul(s, 3))
        si = inv[x]
        td0.append((mul(si, 14) << 24) | (mul(si, 9) << 16) | (mul(si, 13) << 8) | mul(si, 11))
    te1 = [ror8(w) for w in te0]
    te2 = [ror8(w) for w in te1]
    te3 = [ror8(w) for w in te2]
    td1 = [ror8(w) for w in td0]
    td2 = [ror8(w) for w in td1]
    td3 = [ror8(w) for w in td2]
    return sbox, inv, (te0, te1, te2, te3), (td0, td1, td2, td3)


_SBOX, _INV_SBOX, _TE, _TD = _construir_tablas_aes()


def _expandir_clave_128(clave):
    w = list(struct.unpack('>4I', clave))
    rcon = 1
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = ((_SBOX[t >> 24] << 24) | (_SBOX[(t >> 16) & 255] << 16) |
                 (_SBOX[(t >> 8) & 255] << 8) | _SBOX[t & 255])
            t ^= rcon << 24
            rcon = ((rcon << 1) ^ (0x11B if rcon & 0x80 else 0)) & 0xFF
        w.append(w[i - 4] ^ t)
    return w


def _clave_descifrado(w):
    td0, td1, td2, td3 = _TD
    dk = []
    for r in range(10, -1, -1):
        bloque = w[4 * r:4 * r + 4]
        if 0 < r < 10:
            bloque = [td0[_SBOX[x >> 24]] ^ td1[_SBOX[(x >> 16) & 255]] ^
                      td2[_SBOX[(x >> 8) & 255]] ^ td3[_SBOX[x & 255]] for x in bloque]
        dk.extend(bloque)
    return dk


def _aes_cbc(clave, iv, datos, cifrar):
    if len(datos) % 16:
        raise ValueError("Longitud de datos inválida")
    w = _expandir_clave_128(clave)
    n = len(datos) // 4
    palabras = struct.unpack('>%dI' % n, datos)
    previo = list(struct.unpack('>4I', iv))
    salida = []
    S, IS = _SBOX, _INV_SBOX
    if cifrar:
        te0, te1, te2, te3 = _TE
        for b in range(0, n, 4):
            s0 = palabras[b] ^ previo[0] ^ w[0]
            s1 = palabras[b + 1] ^ previo[1] ^ w[1]
            s2 = palabras[b + 2] ^ previo[2] ^ w[2]
            s3 = palabras[b + 3] ^ previo[3] ^ w[3]
            k = 4
            for _ in range(9):
                t0 = te0[s0 >> 24] ^ te1[(s1 >> 16) & 255] ^ te2[(s2 >> 8) & 255] ^ te3[s3 & 255] ^ w[k]
                t1 = te0[s1 >> 24] ^ te1[(s2 >> 16) & 255] ^ te2[(s3 >> 8) & 255] ^ te3[s0 & 255] ^ w[k + 1]
                t2 = te0[s2 >> 24] ^ te1[(s3 >> 16) & 255] ^ te2[(s0 >> 8) & 255] ^ te3[s1 & 255] ^ w[k + 2]
                t3 = te0[s3 >> 24] ^ te1[(s0 >> 16) & 255] ^ te2[(s1 >> 8) & 255] ^ te3[s2 & 255] ^ w[k + 3]
                s0, s1, s2, s3 = t0, t1, t2, t3
                k += 4
            c0 = ((S[s0 >> 24] << 24) | (S[(s1 >> 16) & 255] << 16) | (S[(s2 >> 8) & 255] << 8) | S[s3 & 255]) ^ w[40]
            c1 = ((S[s1 >> 24] << 24) | (S[(s2 >> 16) & 255] << 16) | (S[(s3 >> 8) & 255] << 8) | S[s0 & 255]) ^ w[41]
            c2 = ((S[s2 >> 24] << 24) | (S[(s3 >> 16) & 255] << 16) | (S[(s0 >> 8) & 255] << 8) | S[s1 & 255]) ^ w[42]
            c3 = ((S[s3 >> 24] << 24) | (S[(s0 >> 16) & 255] << 16) | (S[(s1 >> 8) & 255] << 8) | S[s2 & 255]) ^ w[43]
            previo = [c0, c1, c2, c3]
            salida.extend(previo)
    else:
        dk = _clave_descifrado(w)
        td0, td1, td2, td3 = _TD
        for b in range(0, n, 4):
            c = palabras[b:b + 4]
            s0 = c[0] ^ dk[0]
            s1 = c[1] ^ dk[1]
            s2 = c[2] ^ dk[2]
            s3 = c[3] ^ dk[3]
            k = 4
            for _ in range(9):
                t0 = td0[s0 >> 24] ^ td1[(s3 >> 16) & 255] ^ td2[(s2 >> 8) & 255] ^ td3[s1 & 255] ^ dk[k]
                t1 = td0[s1 >> 24] ^ td1[(s0 >> 16) & 255] ^ td2[(s3 >> 8) & 255] ^ td3[s2 & 255] ^ dk[k + 1]
                t2 = td0[s2 >> 24] ^ td1[(s1 >> 16) & 255] ^ td2[(s0 >> 8) & 255] ^ td3[s3 & 255] ^ dk[k + 2]
                t3 = td0[s3 >> 24] ^ td1[(s2 >> 16) & 255] ^ td2[(s1 >> 8) & 255] ^ td3[s0 & 255] ^ dk[k + 3]
                s0, s1, s2, s3 = t0, t1, t2, t3
                k += 4
            p0 = ((IS[s0 >> 24] << 24) | (IS[(s3 >> 16) & 255] << 16) | (IS[(s2 >> 8) & 255] << 8) | IS[s1 & 255]) ^ dk[40]
            p1 = ((IS[s1 >> 24] << 24) | (IS[(s0 >> 16) & 255] << 16) | (IS[(s3 >> 8) & 255] << 8) | IS[s2 & 255]) ^ dk[41]
            p2 = ((IS[s2 >> 24] << 24) | (IS[(s1 >> 16) & 255] << 16) | (IS[(s0 >> 8) & 255] << 8) | IS[s3 & 255]) ^ dk[42]
            p3 = ((IS[s3 >> 24] << 24) | (IS[(s2 >> 16) & 255] << 16) | (IS[(s1 >> 8) & 255] << 8) | IS[s0 & 255]) ^ dk[43]
            salida.extend((p0 ^ previo[0], p1 ^ previo[1], p2 ^ previo[2], p3 ^ previo[3]))
            previo = list(c)
    return struct.pack('>%dI' % len(salida), *salida)


class TokenInvalido(Exception):
    """El archivo no es un token Fernet válido para nuestra clave (o fue modificado)."""


class FernetCompat:
    """Implementación de Fernet (formato estándar) para poder abrir/crear los mismos respaldos que el programa de escritorio."""

    def __init__(self, clave_b64):
        crudo = base64.urlsafe_b64decode(clave_b64)
        if len(crudo) != 32:
            raise ValueError("Clave inválida")
        self._firma = crudo[:16]
        self._cifrado = crudo[16:]

    def encrypt(self, datos):
        iv = os.urandom(16)
        relleno = 16 - (len(datos) % 16)
        datos = datos + bytes([relleno]) * relleno
        cifrado = _aes_cbc(self._cifrado, iv, datos, True)
        base = b'\x80' + struct.pack('>Q', int(time.time())) + iv + cifrado
        firma = hmac.new(self._firma, base, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(base + firma)

    def decrypt(self, token):
        try:
            crudo = base64.urlsafe_b64decode(token.strip())
        except Exception:
            raise TokenInvalido()
        if len(crudo) < 73 or crudo[0] != 0x80:
            raise TokenInvalido()
        base, firma = crudo[:-32], crudo[-32:]
        esperada = hmac.new(self._firma, base, hashlib.sha256).digest()
        if not hmac.compare_digest(firma, esperada):
            raise TokenInvalido()
        iv = base[9:25]
        cifrado = base[25:]
        if not cifrado or len(cifrado) % 16:
            raise TokenInvalido()
        plano = _aes_cbc(self._cifrado, iv, cifrado, False)
        relleno = plano[-1]
        if relleno < 1 or relleno > 16 or plano[-relleno:] != bytes([relleno]) * relleno:
            raise TokenInvalido()
        return plano[:-relleno]


fernet = FernetCompat(CLAVE_CIFRADO_BD)


# --------------------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------------------
def init_db():
    with _db() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS estudiantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                primer_apellido TEXT NOT NULL,
                segundo_apellido TEXT,
                anno_carrera INTEGER NOT NULL,
                carnet_identidad TEXT,
                municipio TEXT,
                sexo TEXT
            )''')
        cols = [f[1] for f in c.execute("PRAGMA table_info(estudiantes)").fetchall()]
        for col in ('carnet_identidad', 'municipio', 'sexo'):
            if col not in cols:
                c.execute("ALTER TABLE estudiantes ADD COLUMN %s TEXT" % col)
        c.execute('''
            CREATE TABLE IF NOT EXISTS profesores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                es_admin INTEGER NOT NULL DEFAULT 0,
                codigo_recuperacion_hash TEXT
            )''')
        cols = [f[1] for f in c.execute("PRAGMA table_info(profesores)").fetchall()]
        if 'es_admin' not in cols:
            c.execute("ALTER TABLE profesores ADD COLUMN es_admin INTEGER NOT NULL DEFAULT 0")
        if 'codigo_recuperacion_hash' not in cols:
            c.execute("ALTER TABLE profesores ADD COLUMN codigo_recuperacion_hash TEXT")
        c.execute('''
            CREATE TABLE IF NOT EXISTS asignaturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                anno_carrera INTEGER NOT NULL
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS extraescolares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                fecha TEXT
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS participaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_estudiante INTEGER,
                id_extraescolares INTEGER,
                participacion TEXT,
                FOREIGN KEY (id_estudiante) REFERENCES estudiantes(id),
                FOREIGN KEY (id_extraescolares) REFERENCES extraescolares(id)
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS evaluaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_estudiante INTEGER,
                id_asignatura INTEGER,
                fecha_evaluacion TEXT,
                nota REAL,
                ausencias REAL,
                FOREIGN KEY (id_estudiante) REFERENCES estudiantes(id),
                FOREIGN KEY (id_asignatura) REFERENCES asignaturas(id)
            )''')


# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------
def hash_password(contrasena):
    return hashlib.sha256(contrasena.encode('utf-8')).hexdigest()


def generar_codigo_recuperacion():
    alfabeto = (string.ascii_uppercase + string.digits).translate(str.maketrans('', '', '0OIL1'))
    grupos = [''.join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(4)]
    return '-'.join(grupos)


def normalizar_texto(texto):
    if texto is None:
        return ''
    sin_acentos = ''.join(c for c in unicodedata.normalize('NFKD', str(texto)) if not unicodedata.combining(c))
    return sin_acentos.lower()


def carnet_es_valido(carnet):
    return carnet.isdigit() and len(carnet) == 11


def extraer_id_estudiante_de_texto(valor):
    if valor is None:
        return None
    primer_token = str(valor).strip().split(' - ')[0].strip()
    try:
        return int(primer_token)
    except (ValueError, TypeError):
        return None


MESES_ES = {
    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04', 'mayo': '05', 'junio': '06',
    'julio': '07', 'agosto': '08', 'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
}
NOMBRES_MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
                 'septiembre', 'octubre', 'noviembre', 'diciembre']


def extraer_mes(fecha_str):
    """'2026-07-18' -> '2026-07'; '18 de julio de 2026' -> '2026-07'."""
    if not fecha_str:
        return None
    fecha_str = str(fecha_str)
    if '-' in fecha_str and len(fecha_str) >= 7:
        return fecha_str[:7]
    m = re.search(r'(\d+)\s+de\s+([a-zA-Z]+)\s+de\s+(\d+)', fecha_str.lower())
    if m:
        return "%s-%s" % (m.group(3), MESES_ES.get(m.group(2), '00'))
    return None


def fmt_num(valor):
    """4.0 -> '4'; 12.5 -> '12.5'."""
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return str(int(f)) if f == int(f) else str(f)


def texto_estudiante(id_est, nombre, ap1, ap2, anno):
    # Mismo formato que usa el programa de escritorio para referenciar al estudiante en evaluaciones y asistencia
    return "%s - %s - %s - %s - %s " % (id_est, nombre, ap1, ap2 or '', anno)


def texto_asignatura(nombre, anno):
    return "%s - %s" % (nombre, anno)


def texto_actividad(nombre, fecha):
    return "%s - %s" % (nombre, fecha)


def fecha_a_iso(f):
    return f.strftime('%Y-%m-%d')


def _fecha_no_futura(f):
    return f <= datetime.now().date()


# --------------------------------------------------------------------------------------
# Renumeración de IDs (igual que el programa de escritorio)
# --------------------------------------------------------------------------------------
def compactar_ids_simple(nombre_tabla):
    with _db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM %s ORDER BY id" % nombre_tabla)
        nuevo = 1
        for (actual,) in c.fetchall():
            if actual != nuevo:
                c.execute("UPDATE %s SET id=? WHERE id=?" % nombre_tabla, (nuevo, actual))
            nuevo += 1
        c.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (nuevo - 1, nombre_tabla))


def compactar_ids_estudiantes():
    with _db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM estudiantes ORDER BY id")
        mapa = {}
        nuevo = 1
        for (actual,) in c.fetchall():
            if actual != nuevo:
                mapa[actual] = nuevo
            nuevo += 1
        for viejo, nuevo_id in mapa.items():
            c.execute("UPDATE estudiantes SET id=? WHERE id=?", (nuevo_id, viejo))
        c.execute("UPDATE sqlite_sequence SET seq=? WHERE name='estudiantes'", (nuevo - 1,))
        if mapa:
            for tabla in ('evaluaciones', 'participaciones'):
                c.execute("SELECT id, id_estudiante FROM %s" % tabla)
                for fila_id, texto in c.fetchall():
                    partes = str(texto).strip().split(' - ', 1)
                    try:
                        viejo = int(partes[0].strip())
                    except (ValueError, IndexError):
                        continue
                    if viejo in mapa:
                        resto = partes[1] if len(partes) > 1 else ''
                        nuevo_texto = "%s - %s" % (mapa[viejo], resto) if resto else str(mapa[viejo])
                        c.execute("UPDATE %s SET id_estudiante=? WHERE id=?" % tabla, (nuevo_texto, fila_id))


# --------------------------------------------------------------------------------------
# Estudiantes
# --------------------------------------------------------------------------------------
COLUMNAS_ESTUDIANTES = ("ID", "Carnet de Identidad", "Nombre", "Primer Apellido", "Segundo Apellido",
                        "Sexo", "Municipio", "Año de Carrera")


def validar_estudiante(carnet, nombre, ap1, ap2, sexo, municipio, anno):
    carnet = (carnet or '').strip()
    nombre = (nombre or '').strip()
    ap1 = (ap1 or '').strip()
    ap2 = (ap2 or '').strip()
    if not carnet_es_valido(carnet):
        raise ErrorApp("El carnet de identidad es obligatorio y debe tener exactamente 11 dígitos numéricos")
    if not nombre or not ap1:
        raise ErrorApp("El nombre y el primer apellido son obligatorios")
    if sexo not in SEXOS:
        raise ErrorApp("Seleccione el sexo del estudiante")
    if municipio not in MUNICIPIOS_CAMAGUEY:
        raise ErrorApp("Seleccione el municipio del estudiante")
    if anno not in ANNOS_CARRERA:
        raise ErrorApp("Seleccione el año de carrera")
    return (carnet, nombre, ap1, ap2, sexo, municipio, anno)


def carnet_existe(carnet, excepto_id=None):
    with _db() as conn:
        if excepto_id is None:
            f = conn.execute("SELECT 1 FROM estudiantes WHERE carnet_identidad=?", (carnet,)).fetchone()
        else:
            f = conn.execute("SELECT 1 FROM estudiantes WHERE carnet_identidad=? AND id<>?", (carnet, excepto_id)).fetchone()
    return f is not None


def guardar_estudiantes(filas):
    """filas: lista de (carnet, nombre, ap1, ap2, sexo, municipio, anno) ya validadas."""
    if not filas:
        raise ErrorApp("Agregue al menos un estudiante a la lista antes de guardar")
    with _db() as conn:
        for carnet, nombre, ap1, ap2, sexo, municipio, anno in filas:
            conn.execute(
                '''INSERT INTO estudiantes (nombre, primer_apellido, segundo_apellido, anno_carrera, carnet_identidad, municipio, sexo)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''', (nombre, ap1, ap2, anno, carnet, municipio, sexo))
    return len(filas)


def listar_estudiantes():
    with _db() as conn:
        return conn.execute(
            "SELECT id, carnet_identidad, nombre, primer_apellido, segundo_apellido, sexo, municipio, anno_carrera FROM estudiantes"
        ).fetchall()


def buscar_estudiantes(criterio):
    criterio = (criterio or '').strip()
    if not criterio:
        raise ErrorApp("Escriba un nombre, apellido, ID o año de carrera para buscar")
    with _db() as conn:
        todos = conn.execute(
            """SELECT id, carnet_identidad, nombre, primer_apellido, segundo_apellido, sexo, municipio, anno_carrera
               FROM estudiantes ORDER BY nombre, primer_apellido""").fetchall()
    crit = normalizar_texto(criterio)
    resultados = []
    for fila in todos:
        id_est, carnet, nombre, ap1, ap2, sexo, municipio, anno = fila
        completo = "%s %s %s" % (nombre, ap1, ap2 or '')
        campos = [str(id_est), carnet, nombre, ap1, ap2, sexo, municipio, str(anno), completo]
        if any(crit in normalizar_texto(c) for c in campos if c):
            resultados.append(fila)
    return resultados


def obtener_estudiante(id_est):
    with _db() as conn:
        return conn.execute(
            "SELECT id, carnet_identidad, nombre, primer_apellido, segundo_apellido, sexo, municipio, anno_carrera FROM estudiantes WHERE id=?",
            (id_est,)).fetchone()


def editar_estudiante(id_est, carnet, nombre, ap1, ap2, sexo, municipio, anno):
    datos = validar_estudiante(carnet, nombre, ap1, ap2, sexo, municipio, anno)
    carnet, nombre, ap1, ap2, sexo, municipio, anno = datos
    if carnet_existe(carnet, excepto_id=id_est):
        raise ErrorApp("Ya existe otro estudiante con ese carnet de identidad")
    with _db() as conn:
        c = conn.cursor()
        c.execute("UPDATE estudiantes SET nombre=?, primer_apellido=?, segundo_apellido=?, anno_carrera=?, carnet_identidad=?, municipio=?, sexo=? WHERE id=?",
                  (nombre, ap1, ap2, anno, carnet, municipio, sexo, id_est))
        # Mantiene al día el texto "ID - Nombre - Apellidos - Año" guardado en evaluaciones y asistencia
        nuevo = texto_estudiante(id_est, nombre, ap1, ap2, anno)
        for tabla in ('evaluaciones', 'participaciones'):
            c.execute("SELECT id, id_estudiante FROM %s" % tabla)
            for fila_id, texto in c.fetchall():
                if extraer_id_estudiante_de_texto(texto) == id_est:
                    c.execute("UPDATE %s SET id_estudiante=? WHERE id=?" % tabla, (nuevo, fila_id))


def eliminar_estudiantes(ids):
    """Elimina estudiantes y todas sus evaluaciones y asistencias. Renumera los IDs."""
    ids = {str(i) for i in ids}
    if not ids:
        raise ErrorApp("Seleccione un estudiante")
    with _db() as conn:
        c = conn.cursor()
        for tabla in ('evaluaciones', 'participaciones'):
            c.execute("SELECT id, id_estudiante FROM %s" % tabla)
            for fila_id, texto in c.fetchall():
                if str(texto).strip().split(' - ')[0].strip() in ids:
                    c.execute("DELETE FROM %s WHERE id=?" % tabla, (fila_id,))
        for i in ids:
            c.execute("DELETE FROM estudiantes WHERE id=?", (int(i),))
    compactar_ids_estudiantes()
    compactar_ids_simple('evaluaciones')
    compactar_ids_simple('participaciones')
    return len(ids)


def opciones_estudiantes():
    """[(texto_para_mostrar_y_guardar, id)]"""
    with _db() as conn:
        filas = conn.execute("SELECT id, nombre, primer_apellido, segundo_apellido, anno_carrera FROM estudiantes ORDER BY id").fetchall()
    return [texto_estudiante(*f) for f in filas]


# --------------------------------------------------------------------------------------
# Asignaturas
# --------------------------------------------------------------------------------------
def validar_asignatura(nombre, anno):
    nombre = (nombre or '').strip()
    if not nombre:
        raise ErrorApp("Escriba el nombre de la asignatura")
    if anno not in ANNOS_CARRERA:
        raise ErrorApp("Seleccione el año")
    return (nombre, anno)


def guardar_asignaturas(filas):
    if not filas:
        raise ErrorApp("Agregue al menos una asignatura a la lista antes de guardar")
    with _db() as conn:
        for nombre, anno in filas:
            conn.execute("INSERT INTO asignaturas (nombre, anno_carrera) VALUES (?, ?)", (nombre, anno))
    return len(filas)


def listar_asignaturas():
    with _db() as conn:
        return conn.execute("SELECT id, nombre, anno_carrera FROM asignaturas").fetchall()


def editar_asignatura(id_asig, nombre, anno):
    nombre, anno = validar_asignatura(nombre, anno)
    with _db() as conn:
        c = conn.cursor()
        viejo = c.execute("SELECT nombre, anno_carrera FROM asignaturas WHERE id=?", (id_asig,)).fetchone()
        c.execute("UPDATE asignaturas SET nombre=?, anno_carrera=? WHERE id=?", (nombre, anno, id_asig))
        if viejo:
            c.execute("UPDATE evaluaciones SET id_asignatura=? WHERE id_asignatura=?",
                      (texto_asignatura(nombre, anno), texto_asignatura(*viejo)))


def eliminar_asignaturas(ids):
    if not ids:
        raise ErrorApp("Seleccione una asignatura")
    with _db() as conn:
        for i in ids:
            conn.execute("DELETE FROM asignaturas WHERE id=?", (i,))
    compactar_ids_simple('asignaturas')


def opciones_asignaturas():
    with _db() as conn:
        filas = conn.execute("SELECT nombre, anno_carrera FROM asignaturas ORDER BY id").fetchall()
    return [texto_asignatura(*f) for f in filas]


# --------------------------------------------------------------------------------------
# Actividades extraescolares
# --------------------------------------------------------------------------------------
def validar_actividad(nombre, fecha):
    nombre = (nombre or '').strip()
    if not nombre:
        raise ErrorApp("Escriba el nombre de la actividad")
    if fecha is None:
        raise ErrorApp("Seleccione la fecha de la actividad")
    return (nombre, fecha_a_iso(fecha))


def guardar_actividades(filas):
    if not filas:
        raise ErrorApp("Agregue al menos una actividad a la lista antes de guardar")
    with _db() as conn:
        for nombre, fecha in filas:
            conn.execute("INSERT INTO extraescolares (nombre, fecha) VALUES (?, ?)", (nombre, fecha))
    return len(filas)


def listar_actividades():
    with _db() as conn:
        return conn.execute("SELECT id, nombre, fecha FROM extraescolares").fetchall()


def editar_actividad(id_act, nombre):
    nombre = (nombre or '').strip()
    if not nombre:
        raise ErrorApp("Por favor, complete todos los campos antes de guardar la actividad.")
    with _db() as conn:
        c = conn.cursor()
        viejo = c.execute("SELECT nombre, fecha FROM extraescolares WHERE id=?", (id_act,)).fetchone()
        c.execute("UPDATE extraescolares SET nombre=? WHERE id=?", (nombre, id_act))
        if viejo:
            c.execute("UPDATE participaciones SET id_extraescolares=? WHERE id_extraescolares=?",
                      (texto_actividad(nombre, viejo[1]), texto_actividad(*viejo)))


def eliminar_actividades(ids):
    if not ids:
        raise ErrorApp("Seleccione una actividad")
    with _db() as conn:
        for i in ids:
            conn.execute("DELETE FROM extraescolares WHERE id=?", (i,))
    compactar_ids_simple('extraescolares')


def opciones_actividades():
    """[(texto 'nombre - fecha', fecha)]"""
    with _db() as conn:
        filas = conn.execute("SELECT nombre, fecha FROM extraescolares ORDER BY id").fetchall()
    return [(texto_actividad(n, f), f) for n, f in filas]


def actividad_es_futura(fecha_texto):
    if not fecha_texto:
        return False
    try:
        return datetime.strptime(fecha_texto, '%Y-%m-%d').date() > datetime.now().date()
    except ValueError:
        return False


# --------------------------------------------------------------------------------------
# Evaluaciones
# --------------------------------------------------------------------------------------
def validar_evaluacion(estudiante, asignatura, fecha, nota, ausencias):
    if not estudiante:
        raise ErrorApp("Seleccione un estudiante")
    if not asignatura:
        raise ErrorApp("Seleccione una asignatura")
    if nota not in NOTAS:
        raise ErrorApp("Seleccione una nota")
    if ausencias not in AUSENCIAS:
        raise ErrorApp("Seleccione el porcentaje de ausencias")
    if fecha is None:
        raise ErrorApp("Seleccione la fecha de la evaluación")
    if not _fecha_no_futura(fecha):
        raise ErrorApp("No se pueden registrar evaluaciones con fecha futura. Seleccione una fecha pasada o el día de hoy.")
    return (estudiante, asignatura, fecha_a_iso(fecha), int(nota), int(ausencias))


def guardar_evaluaciones(filas):
    if not filas:
        raise ErrorApp("Agregue al menos una evaluación a la lista antes de guardar")
    with _db() as conn:
        for est, asig, fecha, nota, aus in filas:
            conn.execute("INSERT INTO evaluaciones(id_estudiante, id_asignatura, fecha_evaluacion, nota, ausencias) VALUES(?, ?, ?, ?, ?)",
                         (est, asig, fecha, nota, aus))
    return len(filas)


def hay_estudiantes():
    with _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM estudiantes").fetchone()[0] > 0


def hay_asignaturas():
    with _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM asignaturas").fetchone()[0] > 0


def hay_actividades():
    with _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM extraescolares").fetchone()[0] > 0


COLUMNAS_EVALUACIONES = ("ID", "Estudiante", "Asignatura", "Fecha", "Nota", "Ausencias")


def listar_evaluaciones():
    with _db() as conn:
        filas = conn.execute("SELECT id, id_estudiante, id_asignatura, fecha_evaluacion, nota, ausencias FROM evaluaciones").fetchall()
    return [(f[0], f[1], f[2], f[3], fmt_num(f[4]), "%s%%" % fmt_num(f[5])) for f in filas]


def editar_evaluacion(id_eval, estudiante, asignatura, fecha, nota, ausencias):
    est, asig, fecha_iso, nota, aus = validar_evaluacion(estudiante, asignatura, fecha, nota, ausencias)
    with _db() as conn:
        conn.execute("UPDATE evaluaciones SET id_estudiante=?, id_asignatura=?, fecha_evaluacion=?, nota=?, ausencias=? WHERE id=?",
                     (est, asig, fecha_iso, nota, aus, id_eval))


def obtener_evaluacion(id_eval):
    with _db() as conn:
        return conn.execute("SELECT id, id_estudiante, id_asignatura, fecha_evaluacion, nota, ausencias FROM evaluaciones WHERE id=?", (id_eval,)).fetchone()


def eliminar_evaluaciones(ids):
    if not ids:
        raise ErrorApp("Seleccione una evaluación")
    with _db() as conn:
        for i in ids:
            conn.execute("DELETE FROM evaluaciones WHERE id=?", (i,))
    compactar_ids_simple('evaluaciones')


def texto_a_fecha(texto):
    """Convierte 'YYYY-MM-DD' o '18 de julio de 2026' a date (o None)."""
    if not texto:
        return None
    texto = str(texto).strip()
    try:
        return datetime.strptime(texto[:10], '%Y-%m-%d').date()
    except ValueError:
        pass
    m = re.search(r'(\d+)\s+de\s+([a-zA-Z]+)\s+de\s+(\d+)', texto.lower())
    if m and m.group(2) in MESES_ES:
        try:
            return date(int(m.group(3)), int(MESES_ES[m.group(2)]), int(m.group(1)))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------------------
# Asistencia (participaciones)
# --------------------------------------------------------------------------------------
COLUMNAS_PARTICIPACION = ("ID", "Estudiante", "Actividad", "Participación")


def validar_actividad_asistencia(actividad):
    if not actividad:
        raise ErrorApp("Seleccione la actividad primero")
    fecha = dict(opciones_actividades()).get(actividad)
    if actividad_es_futura(fecha):
        raise ErrorApp("No se puede tomar asistencia de una actividad con fecha futura. Solo se permite para actividades pasadas o de hoy.")


def validar_asistencia(actividad, estudiante, participacion):
    validar_actividad_asistencia(actividad)
    if not estudiante:
        raise ErrorApp("Seleccione un estudiante")
    if participacion not in ASISTENCIA_OPCIONES:
        raise ErrorApp("Seleccione si estuvo Presente o Ausente")
    return (actividad, estudiante, participacion)


def guardar_asistencias(filas):
    """filas: (actividad_texto, estudiante_texto, participacion)"""
    if not filas:
        raise ErrorApp("Agregue al menos un estudiante a la lista antes de guardar")
    with _db() as conn:
        for actividad, estudiante, participacion in filas:
            conn.execute("INSERT INTO participaciones(id_estudiante, id_extraescolares, participacion) VALUES(?, ?, ?)",
                         (estudiante, actividad, participacion))
    return len(filas)


def listar_participaciones():
    with _db() as conn:
        return conn.execute("SELECT id, id_estudiante, id_extraescolares, participacion FROM participaciones").fetchall()


def obtener_participacion(id_part):
    with _db() as conn:
        return conn.execute("SELECT id, id_estudiante, id_extraescolares, participacion FROM participaciones WHERE id=?", (id_part,)).fetchone()


def editar_participacion(id_part, estudiante, actividad, participacion):
    validar_asistencia(actividad, estudiante, participacion)
    with _db() as conn:
        conn.execute("UPDATE participaciones SET id_estudiante=?, id_extraescolares=?, participacion=? WHERE id=?",
                     (estudiante, actividad, participacion, id_part))


def eliminar_participaciones(ids):
    if not ids:
        raise ErrorApp("Seleccione lo que desea eliminar")
    with _db() as conn:
        for i in ids:
            conn.execute("DELETE FROM participaciones WHERE id=?", (i,))
    compactar_ids_simple('participaciones')


# --------------------------------------------------------------------------------------
# Evaluación mensual (Aprobado / Riesgo de Deserción)
# --------------------------------------------------------------------------------------
COLUMNAS_MENSUAL = ('ID', 'Nombre y Apellidos', 'Mes', 'Evaluación', 'Motivo de la Evaluación')


def evaluacion_mensual(id_estudiante=None):
    """
    Devuelve una lista de tuplas (id, nombre_completo, mes, evaluacion, motivo, etiqueta) con la etiqueta
    'bien' (Aprobado) o 'mal' (Riesgo de Deserción). Si se indica id_estudiante, solo de ese estudiante.
    """
    with _db() as conn:
        c = conn.cursor()
        estudiantes = {r[0]: ("%s %s %s" % (r[1], r[2], r[3] if r[3] else '')).strip()
                       for r in c.execute("SELECT id, nombre, primer_apellido, segundo_apellido FROM estudiantes ORDER BY id").fetchall()}
        evaluaciones = c.execute("SELECT id_estudiante, fecha_evaluacion, nota, ausencias FROM evaluaciones").fetchall()
        actividades_raw = c.execute("SELECT id, nombre, fecha FROM extraescolares").fetchall()
        participaciones = c.execute("SELECT id_estudiante, id_extraescolares, participacion FROM participaciones").fetchall()

    actividades = {r[0]: extraer_mes(r[2]) for r in actividades_raw}
    texto_a_id = {"%s - %s" % (r[1], r[2]): r[0] for r in actividades_raw}
    total_por_mes = {}
    for mes in actividades.values():
        if mes:
            total_por_mes[mes] = total_por_mes.get(mes, 0) + 1

    data = {e_id: {} for e_id in estudiantes}

    def nuevo():
        return {'notas': [], 'ausencias': [], 'presentes': 0, 'registradas': 0}

    for e_raw, fecha, nota, aus in evaluaciones:
        e_id = extraer_id_estudiante_de_texto(e_raw)
        mes = extraer_mes(fecha)
        if not mes or e_id not in data:
            continue
        d = data[e_id].setdefault(mes, nuevo())
        try:
            d['notas'].append(float(nota))
        except (TypeError, ValueError):
            pass
        try:
            d['ausencias'].append(float(str(aus).replace('%', '')))
        except (TypeError, ValueError):
            pass

    for e_raw, a_raw, part in participaciones:
        e_id = extraer_id_estudiante_de_texto(e_raw)
        a_id = texto_a_id.get(str(a_raw).strip())
        if a_id is None:
            try:
                a_id = int(a_raw)
            except (ValueError, TypeError):
                a_id = None
        mes = actividades.get(a_id)
        if not mes or e_id not in data:
            continue
        d = data[e_id].setdefault(mes, nuevo())
        d['registradas'] += 1
        if str(part).strip().lower() == 'presente':
            d['presentes'] += 1

    meses = set(total_por_mes.keys())
    for e_id in data:
        meses.update(data[e_id].keys())

    filas = []
    for mes in sorted(meses):
        for e_id, nombre in estudiantes.items():
            if id_estudiante is not None and e_id != id_estudiante:
                continue
            d = data[e_id].get(mes)
            if not d or (not d['notas'] and d['registradas'] == 0):
                continue
            notas, aus = d['notas'], d['ausencias']
            total_act = total_por_mes.get(mes, 0)
            prom_nota = sum(notas) / len(notas) if notas else None
            prom_aus = sum(aus) / len(aus) if aus else None
            prom_part = 100
            if total_act > 0:
                prom_part = (d['presentes'] / total_act) * 100
            detalles = [
                "Notas: %.2f" % prom_nota if prom_nota is not None else "Notas: N/A",
                "Ausencias: %.2f%%" % prom_aus if prom_aus is not None else "Ausencias: N/A",
                "Participación extraescolar: %.2f%%" % prom_part,
            ]
            motivos = []
            if prom_nota is not None and not (3 <= prom_nota <= 5):
                motivos.append("Promedio de notas fuera de rango (3-5)")
            if prom_aus is not None and prom_aus > 20:
                motivos.append("Ausencias > 20%")
            if total_act > 0 and prom_part < 50:
                motivos.append("Participación < 50%")
            if motivos:
                evaluacion, motivo, etiqueta = "Riesgo de Deserción", ", ".join(detalles) + " -> " + ", ".join(motivos), 'mal'
            else:
                evaluacion, motivo, etiqueta = "Aprobado", ", ".join(detalles) + " -> Cumple todos los requisitos", 'bien'
            filas.append((e_id, nombre, mes, evaluacion, motivo, etiqueta))
    return filas


# --------------------------------------------------------------------------------------
# Exportar / Importar / Restaurar
# --------------------------------------------------------------------------------------
def exportar_cifrado(ruta_destino):
    """Guarda toda la información (SIN las cuentas de profesores) en un archivo cifrado compatible con el programa de escritorio."""
    fd, temporal = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        origen = sqlite3.connect(DB_PATH)
        copia = sqlite3.connect(temporal)
        try:
            origen.backup(copia)
            copia.execute("DELETE FROM profesores")
            copia.commit()
        finally:
            copia.close()
            origen.close()
        with open(temporal, 'rb') as f:
            contenido = f.read()
        cifrado = fernet.encrypt(contenido)
        with open(ruta_destino, 'wb') as f:
            f.write(cifrado)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def fusionar_informacion_importada(ruta_origen):
    resumen = {'estudiantes': 0, 'asignaturas': 0, 'extraescolares': 0, 'evaluaciones': 0, 'participaciones': 0}
    conn_o = sqlite3.connect(ruta_origen)
    cur_o = conn_o.cursor()
    conn_d = sqlite3.connect(DB_PATH)
    cur_d = conn_d.cursor()
    try:
        cur_d.execute("SELECT id, carnet_identidad FROM estudiantes")
        carnet_a_id = {carnet: i for i, carnet in cur_d.fetchall() if carnet}
        cur_o.execute("SELECT id, nombre, primer_apellido, segundo_apellido, anno_carrera, carnet_identidad, municipio, sexo FROM estudiantes")
        mapa = {}
        for id_o, nombre, ap1, ap2, anno, carnet, municipio, sexo in cur_o.fetchall():
            if carnet and carnet in carnet_a_id:
                mapa[id_o] = carnet_a_id[carnet]
                continue
            cur_d.execute('''INSERT INTO estudiantes (nombre, primer_apellido, segundo_apellido, anno_carrera, carnet_identidad, municipio, sexo)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''', (nombre, ap1, ap2, anno, carnet, municipio, sexo))
            mapa[id_o] = cur_d.lastrowid
            if carnet:
                carnet_a_id[carnet] = cur_d.lastrowid
            resumen['estudiantes'] += 1
        conn_d.commit()

        cur_d.execute("SELECT nombre, anno_carrera FROM asignaturas")
        existentes = {(n, a) for n, a in cur_d.fetchall()}
        cur_o.execute("SELECT nombre, anno_carrera FROM asignaturas")
        for nombre, anno in cur_o.fetchall():
            if (nombre, anno) in existentes:
                continue
            cur_d.execute("INSERT INTO asignaturas (nombre, anno_carrera) VALUES (?, ?)", (nombre, anno))
            existentes.add((nombre, anno))
            resumen['asignaturas'] += 1
        conn_d.commit()

        cur_d.execute("SELECT nombre, fecha FROM extraescolares")
        existentes = {(n, f) for n, f in cur_d.fetchall()}
        cur_o.execute("SELECT nombre, fecha FROM extraescolares")
        for nombre, fecha in cur_o.fetchall():
            if (nombre, fecha) in existentes:
                continue
            cur_d.execute("INSERT INTO extraescolares (nombre, fecha) VALUES (?, ?)", (nombre, fecha))
            existentes.add((nombre, fecha))
            resumen['extraescolares'] += 1
        conn_d.commit()

        cur_d.execute("SELECT id_estudiante, id_asignatura, fecha_evaluacion, nota, ausencias FROM evaluaciones")
        existentes = {(extraer_id_estudiante_de_texto(t), a, f, n, au) for t, a, f, n, au in cur_d.fetchall()}
        cur_o.execute("SELECT id_estudiante, id_asignatura, fecha_evaluacion, nota, ausencias FROM evaluaciones")
        for texto, asig, fecha, nota, aus in cur_o.fetchall():
            id_o = extraer_id_estudiante_de_texto(texto)
            if id_o not in mapa:
                continue
            id_d = mapa[id_o]
            clave = (id_d, asig, fecha, nota, aus)
            if clave in existentes:
                continue
            partes = str(texto).strip().split(' - ', 1)
            nuevo = "%s - %s" % (id_d, partes[1]) if len(partes) > 1 else str(id_d)
            cur_d.execute("INSERT INTO evaluaciones (id_estudiante, id_asignatura, fecha_evaluacion, nota, ausencias) VALUES (?, ?, ?, ?, ?)",
                          (nuevo, asig, fecha, nota, aus))
            existentes.add(clave)
            resumen['evaluaciones'] += 1
        conn_d.commit()

        cur_d.execute("SELECT id_estudiante, id_extraescolares, participacion FROM participaciones")
        existentes = {(extraer_id_estudiante_de_texto(t), a) for t, a, p in cur_d.fetchall()}
        cur_o.execute("SELECT id_estudiante, id_extraescolares, participacion FROM participaciones")
        for texto, act, part in cur_o.fetchall():
            id_o = extraer_id_estudiante_de_texto(texto)
            if id_o not in mapa:
                continue
            id_d = mapa[id_o]
            clave = (id_d, act)
            if clave in existentes:
                continue
            partes = str(texto).strip().split(' - ', 1)
            nuevo = "%s - %s" % (id_d, partes[1]) if len(partes) > 1 else str(id_d)
            cur_d.execute("INSERT INTO participaciones (id_estudiante, id_extraescolares, participacion) VALUES (?, ?, ?)",
                          (nuevo, act, part))
            existentes.add(clave)
            resumen['participaciones'] += 1
        conn_d.commit()
    finally:
        conn_o.close()
        conn_d.close()
    return resumen


def importar_cifrado(ruta):
    """Importa un respaldo cifrado de Toolteach. Devuelve el resumen de lo agregado."""
    with open(ruta, 'rb') as f:
        contenido = f.read()
    try:
        plano = fernet.decrypt(contenido)
    except TokenInvalido:
        raise ErrorApp("Ese archivo no se pudo reconocer como una exportación cifrada de Toolteach (o fue modificado). "
                       "Solo se pueden importar archivos generados con \"Datos\" > \"Exportar\" de este programa.")
    fd, temporal = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        with open(temporal, 'wb') as f:
            f.write(plano)
        return fusionar_informacion_importada(temporal)
    except sqlite3.DatabaseError:
        raise ErrorApp("El archivo no contiene una base de datos válida de Toolteach.")
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def restaurar_de_fabrica():
    with _db() as conn:
        for tabla in ['estudiantes', 'evaluaciones', 'asignaturas', 'extraescolares', 'participaciones']:
            conn.execute("DELETE FROM %s" % tabla)
            conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (tabla,))


# --------------------------------------------------------------------------------------
# Profesores y acceso
# --------------------------------------------------------------------------------------
def _validar_usuario_y_clave(usuario, contrasena, confirmar):
    if not usuario or not contrasena:
        raise ErrorApp("El usuario y la contraseña son obligatorios")
    if len(contrasena) < 4:
        raise ErrorApp("La contraseña debe tener al menos 4 caracteres")
    if contrasena != confirmar:
        raise ErrorApp("Las contraseñas no coinciden")


def _solo_admin(es_admin, accion):
    if not es_admin:
        raise ErrorApp("Acceso denegado: solo el Administrador puede %s." % accion)


def hay_profesores():
    with _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM profesores").fetchone()[0] > 0


def iniciar_sesion(usuario, contrasena):
    usuario = (usuario or '').strip()
    if not usuario or not contrasena:
        raise ErrorApp("Escriba su usuario y contraseña")
    with _db() as conn:
        fila = conn.execute("SELECT password_hash, es_admin FROM profesores WHERE usuario=?", (usuario,)).fetchone()
    if fila is None or fila[0] != hash_password(contrasena):
        raise ErrorApp("Usuario o contraseña incorrectos")
    return usuario, bool(fila[1])


def crear_primer_admin(usuario, contrasena, confirmar):
    usuario = (usuario or '').strip()
    _validar_usuario_y_clave(usuario, contrasena, confirmar)
    if hay_profesores():
        raise ErrorApp("Ya existe una cuenta de Administrador")
    codigo = generar_codigo_recuperacion()
    with _db() as conn:
        conn.execute("INSERT INTO profesores (usuario, password_hash, es_admin, codigo_recuperacion_hash) VALUES (?, ?, 1, ?)",
                     (usuario, hash_password(contrasena), hash_password(codigo)))
    return codigo


def agregar_profesor(es_admin, usuario, contrasena, confirmar):
    _solo_admin(es_admin, "agregar profesores")
    usuario = (usuario or '').strip()
    _validar_usuario_y_clave(usuario, contrasena, confirmar)
    try:
        with _db() as conn:
            conn.execute("INSERT INTO profesores (usuario, password_hash, es_admin) VALUES (?, ?, 0)", (usuario, hash_password(contrasena)))
    except sqlite3.IntegrityError:
        raise ErrorApp("Ese nombre de usuario ya existe. Elija otro.")


def listar_profesores():
    with _db() as conn:
        filas = conn.execute("SELECT id, usuario, es_admin FROM profesores ORDER BY id").fetchall()
    return [(i, u, "Administrador" if a else "Profesor") for i, u, a in filas]


def eliminar_profesor(es_admin, id_prof):
    _solo_admin(es_admin, "gestionar los profesores")
    with _db() as conn:
        fila = conn.execute("SELECT es_admin FROM profesores WHERE id=?", (id_prof,)).fetchone()
        if fila is None:
            raise ErrorApp("Ese profesor ya no existe")
        if fila[0]:
            raise ErrorApp("No se puede eliminar la cuenta de Administrador.")
        conn.execute("DELETE FROM profesores WHERE id=?", (id_prof,))
    compactar_ids_simple('profesores')


def cambiar_mi_cuenta(usuario_actual, es_admin, contrasena_actual, nuevo_usuario, nueva, confirmar):
    """Devuelve (usuario_final, codigo_recuperacion_nuevo_o_None)."""
    nuevo_usuario = (nuevo_usuario or '').strip()
    if not contrasena_actual:
        raise ErrorApp("Escriba su contraseña actual para confirmar los cambios")
    if not nuevo_usuario:
        raise ErrorApp("El usuario no puede quedar vacío")
    with _db() as conn:
        fila = conn.execute("SELECT password_hash, codigo_recuperacion_hash FROM profesores WHERE usuario=?", (usuario_actual,)).fetchone()
        if fila is None or fila[0] != hash_password(contrasena_actual):
            raise ErrorApp("La contraseña actual es incorrecta")
        nuevo_hash = fila[0]
        cambio = False
        if nueva or confirmar:
            if len(nueva) < 4:
                raise ErrorApp("La nueva contraseña debe tener al menos 4 caracteres")
            if nueva != confirmar:
                raise ErrorApp("Las contraseñas nuevas no coinciden")
            nuevo_hash = hash_password(nueva)
            cambio = True
        codigo = generar_codigo_recuperacion() if (es_admin and (cambio or not fila[1])) else None
        try:
            if codigo:
                conn.execute("UPDATE profesores SET usuario=?, password_hash=?, codigo_recuperacion_hash=? WHERE usuario=?",
                             (nuevo_usuario, nuevo_hash, hash_password(codigo), usuario_actual))
            else:
                conn.execute("UPDATE profesores SET usuario=?, password_hash=? WHERE usuario=?", (nuevo_usuario, nuevo_hash, usuario_actual))
        except sqlite3.IntegrityError:
            raise ErrorApp("Ese nombre de usuario ya está en uso por otra cuenta")
    return nuevo_usuario, codigo


def candidatos_admin():
    with _db() as conn:
        return [f[0] for f in conn.execute("SELECT usuario FROM profesores WHERE es_admin=0 ORDER BY usuario").fetchall()]


def promover_admin(es_admin, usuario_actual, nuevo_admin):
    _solo_admin(es_admin, "cambiar de administrador")
    with _db() as conn:
        conn.execute("UPDATE profesores SET es_admin=0 WHERE usuario=?", (usuario_actual,))
        conn.execute("UPDATE profesores SET es_admin=1 WHERE usuario=?", (nuevo_admin,))


def registrar_nuevo_admin(es_admin, usuario_actual, usuario, contrasena, confirmar):
    _solo_admin(es_admin, "cambiar de administrador")
    usuario = (usuario or '').strip()
    _validar_usuario_y_clave(usuario, contrasena, confirmar)
    codigo = generar_codigo_recuperacion()
    try:
        with _db() as conn:
            conn.execute("INSERT INTO profesores (usuario, password_hash, es_admin, codigo_recuperacion_hash) VALUES (?, ?, 1, ?)",
                         (usuario, hash_password(contrasena), hash_password(codigo)))
            conn.execute("UPDATE profesores SET es_admin=0 WHERE usuario=?", (usuario_actual,))
    except sqlite3.IntegrityError:
        raise ErrorApp("Ese nombre de usuario ya existe. Elija otro.")
    return codigo


def recuperacion_paso_usuario(usuario):
    """Devuelve el hash del código de recuperación si el usuario puede recuperar su contraseña por este medio."""
    usuario = (usuario or '').strip()
    if not usuario:
        raise ErrorApp("Escriba su usuario")
    with _db() as conn:
        fila = conn.execute("SELECT es_admin, codigo_recuperacion_hash FROM profesores WHERE usuario=?", (usuario,)).fetchone()
    if fila is None:
        raise ErrorApp("Ese usuario no existe")
    if not fila[0]:
        raise ErrorApp("Solo el Administrador puede recuperar su contraseña así. Pida a su Administrador que le cree una cuenta nueva.")
    if not fila[1]:
        raise ErrorApp("Esta cuenta no tiene un código de recuperación configurado")
    return usuario, fila[1]


def verificar_codigo_recuperacion(codigo_hash, ingresado):
    if hash_password((ingresado or '').strip().upper()) != codigo_hash:
        raise ErrorApp("El código ingresado no es correcto")


def establecer_nueva_contrasena(usuario, contrasena, confirmar):
    if len(contrasena) < 4:
        raise ErrorApp("La contraseña debe tener al menos 4 caracteres")
    if contrasena != confirmar:
        raise ErrorApp("Las contraseñas no coinciden")
    codigo = generar_codigo_recuperacion()
    with _db() as conn:
        conn.execute("UPDATE profesores SET password_hash=?, codigo_recuperacion_hash=? WHERE usuario=?",
                     (hash_password(contrasena), hash_password(codigo), usuario))
    return codigo


# --------------------------------------------------------------------------------------
# Excel (.xlsx) sin dependencias externas
# --------------------------------------------------------------------------------------
_XML_ILEGAL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _col_letra(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def escribir_xlsx(ruta, titulo_hoja, encabezados, filas):
    titulo = re.sub(r'[\[\]:*?/\\]', ' ', titulo_hoja)[:31] or 'Hoja1'
    todas = [list(encabezados)] + [list(f) for f in filas]
    anchos = [0] * len(encabezados)
    partes_filas = []
    for r, fila in enumerate(todas, start=1):
        celdas = []
        for c, valor in enumerate(fila, start=1):
            ref = "%s%d" % (_col_letra(c), r)
            estilo = ' s="1"' if r == 1 else ''
            if isinstance(valor, bool) or valor is None:
                texto = '' if valor is None else str(valor)
                celdas.append('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, estilo, escape(_XML_ILEGAL.sub('', texto))))
            elif isinstance(valor, (int, float)):
                texto = str(valor)
                celdas.append('<c r="%s"%s><v>%s</v></c>' % (ref, estilo, texto))
            else:
                texto = _XML_ILEGAL.sub('', str(valor))
                celdas.append('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, estilo, escape(texto)))
            if c <= len(anchos):
                anchos[c - 1] = max(anchos[c - 1], len(str(valor if valor is not None else '')))
        partes_filas.append('<row r="%d">%s</row>' % (r, ''.join(celdas)))
    cols = ''.join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i, i, min(max(a + 3, 8), 100))
                   for i, a in enumerate(anchos, start=1))
    hoja = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<cols>%s</cols><sheetData>%s</sheetData></worksheet>') % (cols, ''.join(partes_filas))
    contenidos = {
        '[Content_Types].xml':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>',
        '_rels/.rels':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        'xl/workbook.xml':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>' % escape(titulo, {'"': '&quot;'}),
        'xl/_rels/workbook.xml.rels':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>',
        'xl/styles.xml':
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>',
        'xl/worksheets/sheet1.xml': hoja,
    }
    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in contenidos.items():
            z.writestr(nombre, contenido)
