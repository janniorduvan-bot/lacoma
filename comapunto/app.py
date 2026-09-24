from flask import Flask, render_template, request, url_for, redirect, flash, session, jsonify
from functools import wraps
import sqlite3
import threading
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import re
from datetime import datetime, timedelta
import random
from urllib.parse import parse_qs, urlparse


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'la_coma.sqlite3')


def normalize_sqlite_query(query: str) -> str:
    sql = query.strip()
    sql = re.sub(r'(?i)\bINSERT IGNORE\b', 'INSERT OR IGNORE', sql)
    if '%s' in sql:
        sql = sql.replace('%s', '?')

    if 'ON DUPLICATE KEY UPDATE' in sql.upper():
        pre_update = sql.split('ON DUPLICATE KEY UPDATE', 1)[0]
        update_clause = sql.split('ON DUPLICATE KEY UPDATE', 1)[1]
        assignments = []
        for part in update_clause.split(','):
            part = part.strip()
            if '=' not in part:
                continue
            column, value = [piece.strip() for piece in part.split('=', 1)]
            if value.upper().startswith('VALUES('):
                value_name = value[7:-1].strip()
                assignments.append(f'{column} = excluded.{value_name}')
            else:
                assignments.append(f'{column} = {value}')
        sql = f"{pre_update} ON CONFLICT(user_id) DO UPDATE SET {', '.join(assignments)}"

    return sql


class SQLiteConnectionProxy:
    def __init__(self, db_path):
        self.db_path = db_path
        self.local = threading.local()

    def _get_connection(self):
        if not hasattr(self.local, 'connection'):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('PRAGMA journal_mode = WAL')
            self.local.connection = conn
        return self.local.connection

    def cursor(self):
        return self._get_connection().cursor()

    def execute(self, query, params=()):
        return self._get_connection().execute(query, params)

    def commit(self):
        return self._get_connection().commit()

    def rollback(self):
        return self._get_connection().rollback()

    def __getattr__(self, name):
        return getattr(self._get_connection(), name)


class SQLiteCursor:
    def __init__(self, db_proxy):
        self._db_proxy = db_proxy
        self._cursor = None

    def execute(self, query, params=()):
        conn = self._db_proxy._get_connection()
        self._cursor = conn.cursor()
        return self._cursor.execute(normalize_sqlite_query(query), tuple(params) if params is not None else ())

    def __getattr__(self, name):
        if self._cursor is None:
            self._cursor = self._db_proxy._get_connection().cursor()
        return getattr(self._cursor, name)


# Conexión a SQLite local por hilo para evitar el problema de "SQLite objects created in a thread..."
db = SQLiteConnectionProxy(DB_PATH)
cursor = SQLiteCursor(db)

def ensure_column_exists(table, column, alter_sql):
    try:
        cursor.execute(f'PRAGMA table_info({table})')
        exists = any(row[1] == column for row in cursor.fetchall())
        if not exists:
            cursor.execute(alter_sql)
            db.commit()
    except Exception:
        pass


def ensure_usuarios_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                city TEXT,
                rol INTEGER NOT NULL DEFAULT 0,
                puntaje INTEGER NOT NULL DEFAULT 0,
                username TEXT UNIQUE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

        ensure_column_exists('usuarios', 'puntaje', "ALTER TABLE usuarios ADD COLUMN puntaje INTEGER NOT NULL DEFAULT 0")
        ensure_column_exists('usuarios', 'username', "ALTER TABLE usuarios ADD COLUMN username TEXT UNIQUE")
        ensure_column_exists('usuarios', 'city', "ALTER TABLE usuarios ADD COLUMN city TEXT")
        ensure_column_exists('usuarios', 'rol', "ALTER TABLE usuarios ADD COLUMN rol INTEGER NOT NULL DEFAULT 0")
    except Exception as exc:
        print(f'Error al preparar tabla usuarios: {exc}')


def ensure_default_admin_user():
    ensure_usuarios_table()
    try:
        cursor.execute("SELECT id, username, rol FROM usuarios WHERE email = ? LIMIT 1", ('abrileo0765@gmail.com',))
        admin = cursor.fetchone()
        if admin is None:
            cursor.execute("SELECT id, username, rol FROM usuarios WHERE username = ? LIMIT 1", ('abril',))
            admin = cursor.fetchone()
        if admin is None:
            cursor.execute(
                """
                INSERT INTO usuarios (nombre, email, password, city, rol, puntaje, username)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    'Abril',
                    'abrileo0765@gmail.com',
                    'scrypt:32768:8:1$Dtn3yj86RCCtWFPO$cc0d0462f1d2382e811a39473accc5c5eef6b40e39f811d33e8d9a5131b6dad997f06ef642a336957c77a483e40bdc2e252b6ac2faa8c02633cb628476a45bb8',
                    'bogota',
                    1,
                    0,
                    'abril',
                )
            )
        else:
            if admin[1] == 'abril' and admin[2] == 1:
                db.commit()
                return
            cursor.execute("SELECT id FROM usuarios WHERE username = ? AND id != ? LIMIT 1", ('abril', admin[0]))
            username_owner = cursor.fetchone()
            if username_owner is not None:
                cursor.execute("UPDATE usuarios SET username = 'usuario' || id WHERE id = ?", (username_owner[0],))
            cursor.execute(
                """
                UPDATE usuarios
                SET nombre = ?, email = ?, city = ?, rol = ?, username = ?
                WHERE id = ?
                """,
                (
                    'Abril',
                    'abrileo0765@gmail.com',
                    'bogota',
                    1,
                    'abril',
                    admin[0],
                )
            )
        db.commit()
    except Exception as exc:
        print(f'Error al asegurar usuario administrador: {exc}')


def initialize_sqlite_database():
    ensure_usuarios_table()
    ensure_default_admin_user()
    ensure_game_catalog()
    ensure_forum_posts_table()
    ensure_chat_messages_table()
    ensure_user_post_likes_table()
    ensure_reportes_table()
    ensure_notificaciones_table()
    ensure_user_suscripcion_table()
    ensure_payment_methods_table()
    ensure_payment_orders_table()
    ensure_facturas_table()
    ensure_membership_refunds_table()
    ensure_user_cartas_table()
    ensure_user_recompensa_table()
    ensure_user_recompensa_columns()
    ensure_user_recompensa_index()
    ensure_user_points_column()
    ensure_username_column()


app = Flask(__name__, static_folder='static', template_folder='templates')
import secrets
app.secret_key = secrets.token_hex(32)

GAME_GENRES = (
    ('terror', 'Terror'),
    ('aventura', 'Aventura'),
    ('rol', 'Rol'),
    ('accion', 'Acción'),
    ('estrategia', 'Estrategia'),
    ('deportes', 'Deportes'),
)

def validar_captcha(respuesta):
    return respuesta == 'on'


def ensure_game_catalog():
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS juego_catalogo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                imagen TEXT NOT NULL,
                foro_tabla TEXT NOT NULL UNIQUE,
                plataforma TEXT NOT NULL DEFAULT 'pc',
                trailer_url TEXT NULL,
                genero TEXT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        ensure_column_exists('juego_catalogo', 'plataforma', "ALTER TABLE juego_catalogo ADD COLUMN plataforma TEXT NOT NULL DEFAULT 'pc'")
        ensure_column_exists('juego_catalogo', 'trailer_url', "ALTER TABLE juego_catalogo ADD COLUMN trailer_url TEXT NULL")
        ensure_column_exists('juego_catalogo', 'genero', "ALTER TABLE juego_catalogo ADD COLUMN genero TEXT NULL")

        cursor.execute("""
            INSERT OR IGNORE INTO juego_catalogo (slug, nombre, descripcion, imagen, foro_tabla, plataforma)
            VALUES
                ('minecraft', 'MINECRAFT', 'Explora, construye y comparte aventuras en un mundo infinito.', 'IMG/MINECRAFT.png', 'foros_minecraft', 'pc'),
                ('valorant', 'VALORANT', 'Dispara con precisión y coordina ataques en modos competitivos.', 'IMG/VALORAND.jfif', 'foros_valorant', 'pc'),
                ('fortnite', 'FORTNITE', 'Construye, esquiva y compite en batallas llenas de acción.', 'IMG/FORNITE.jfif', 'foros_fortnite', 'pc'),
                ('rocket-league', 'ROCKET LEAGUE', 'Sube de nivel con tiros rápidos, dribles y jugadas épicas.', 'IMG/ROCKETLEAGUE.jfif', 'foros_rocket_league', 'pc'),
                ('csgo', 'CS:GO', 'Entrena tu estrategia y disfruta partidas de alto nivel.', 'IMG/CS_GO.jfif', 'foros_csgo', 'pc'),
                ('geometry-dash', 'GEOMETRY DASH', 'Salta, vuela y supera niveles con ritmo y precisión.', 'IMG/GEOMETRY_DASH.jfif', 'foros_geometry_dash', 'movil'),
                ('clash-royale', 'CLASH ROYALE', 'Combina cartas, construye defensas y domina el duelo.', 'IMG/CLASH ROYALE.jfif', 'foros_clash_royale', 'movil'),
                ('brawl-stars', 'BRAWL STARS', 'Compite en modos rápidos con personajes únicos y acción constante.', 'IMG/BRAWL STARS.jfif', 'foros_brawl_stars', 'movil'),
                ('subway-surfers', 'SUBWAY SURFERS', 'Corre, esquiva obstáculos y consigue nuevas colecciones en cada partida.', 'IMG/SUBWAY SURFERS.jfif', 'foros_subway_surfers', 'movil'),
                ('free-fire', 'FREE FIRE', 'Participa en combates intensos con estrategias rápidas y acción directa.', 'IMG/FREE FIRE.jfif', 'foros_free_fire', 'movil'),
                ('minecraft-bedrock', 'MINECRAFT BEDROCK', 'Construye mundos, sobrevive y comparte aventuras en tu dispositivo móvil.', 'IMG/MINECRAFT BEDROCK.jfif', 'foros_minecraft_bedrock', 'movil')
        """)
        db.commit()

        image_updates = [
            ('minecraft', 'IMG/MINECRAFT.png'),
            ('valorant', 'IMG/VALORAND.jfif'),
            ('fortnite', 'IMG/FORNITE.jfif'),
            ('rocket-league', 'IMG/ROCKETLEAGUE.jfif'),
            ('csgo', 'IMG/CS_GO.jfif'),
            ('geometry-dash', 'IMG/GEOMETRY_DASH.jfif'),
            ('clash-royale', 'IMG/CLASH ROYALE.jfif'),
            ('brawl-stars', 'IMG/BRAWL STARS.jfif'),
            ('subway-surfers', 'IMG/SUBWAY SURFERS.jfif'),
            ('free-fire', 'IMG/FREE FIRE.jfif'),
            ('minecraft-bedrock', 'IMG/MINECRAFT BEDROCK.jfif')
        ]

        for slug, image_path in image_updates:
            cursor.execute("UPDATE juego_catalogo SET imagen = %s WHERE slug = %s", (image_path, slug))

        genre_updates = [
            ('minecraft', 'aventura'),
            ('valorant', 'accion'),
            ('fortnite', 'accion'),
            ('rocket-league', 'deportes'),
            ('csgo', 'accion'),
            ('geometry-dash', 'accion'),
            ('clash-royale', 'estrategia'),
            ('brawl-stars', 'accion'),
            ('subway-surfers', 'aventura'),
            ('free-fire', 'accion'),
            ('minecraft-bedrock', 'aventura'),
        ]
        for slug, genre in genre_updates:
            cursor.execute("UPDATE juego_catalogo SET genero = %s WHERE slug = %s AND (genero IS NULL OR genero = '')", (genre, slug))
        db.commit()
    except Exception as e:
        print(f"Error al preparar catálogo de juegos: {e}")


def youtube_embed_url(video_url):
    if not video_url:
        return None
    parsed = urlparse(video_url.strip())
    video_id = ''
    if parsed.hostname in {'youtu.be', 'www.youtu.be'}:
        video_id = parsed.path.strip('/')
    elif parsed.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        if parsed.path == '/watch':
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        elif parsed.path.startswith('/embed/'):
            video_id = parsed.path.split('/embed/', 1)[1].split('/', 1)[0]
    if not video_id:
        return None
    return f'https://www.youtube.com/embed/{video_id}'


def ensure_forum_posts_table():
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS foro_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                juego_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                titulo TEXT NOT NULL,
                contenido TEXT NOT NULL,
                usuario TEXT NOT NULL DEFAULT 'Usuario',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                likes INTEGER NOT NULL DEFAULT 0,
                tipo_cliente TEXT DEFAULT 'ambos'
            )
        """)
        db.commit()

        ensure_column_exists('foro_posts', 'juego_id', "ALTER TABLE foro_posts ADD COLUMN juego_id INTEGER NOT NULL DEFAULT 0")
        ensure_column_exists('foro_posts', 'slug', "ALTER TABLE foro_posts ADD COLUMN slug TEXT NOT NULL DEFAULT ''")
        ensure_column_exists('foro_posts', 'likes', "ALTER TABLE foro_posts ADD COLUMN likes INTEGER NOT NULL DEFAULT 0")
        ensure_column_exists('foro_posts', 'tipo_cliente', "ALTER TABLE foro_posts ADD COLUMN tipo_cliente TEXT DEFAULT 'ambos'")
    except Exception as e:
        print(f"Error al preparar tabla compartida de foros: {e}")


def ensure_chat_messages_table():
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                juego_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                usuario TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_juego_fecha ON chat_mensajes (juego_id, fecha_creacion)")
        db.commit()
    except Exception as e:
        print(f"Error al preparar tabla de chat: {e}")


def ensure_user_post_likes_table():
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_post_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                like_count INTEGER NOT NULL DEFAULT 0,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, post_id)
            )
        """)
        db.commit()
    except Exception as e:
        print(f"Error al preparar tabla de likes por usuario: {e}")


def ensure_user_points_column():
    try:
        ensure_column_exists('usuarios', 'puntaje', "ALTER TABLE usuarios ADD COLUMN puntaje INT NOT NULL DEFAULT 0")
    except Exception as e:
        print(f"Error al asegurar columna de puntaje: {e}")


def ensure_username_column():
    ensure_column_exists('usuarios', 'username', "ALTER TABLE usuarios ADD COLUMN username VARCHAR(50) NULL UNIQUE")
    try:
        cursor.execute("UPDATE usuarios SET username = 'usuario' || id WHERE username IS NULL OR username = ''")
        db.commit()
    except Exception as e:
        print(f"Error al preparar nombres de usuario: {e}")


def ensure_forum_table(foro_tabla):
    ensure_forum_posts_table()


def get_juegos_con_destacado(plataforma=None, genero=None, search_query=None, sort_order=None):
    ensure_game_catalog()
    ensure_forum_posts_table()
    query = "SELECT j.id, j.slug, j.nombre, j.descripcion, j.imagen, j.foro_tabla, j.plataforma, j.genero, COALESCE(COUNT(p.id), 0) AS comentario_count "
    query += "FROM juego_catalogo j LEFT JOIN foro_posts p ON p.juego_id = j.id"
    params = []
    conditions = []

    if plataforma in {'pc', 'movil'}:
        conditions.append('j.plataforma = %s')
        params.append(plataforma)

    if genero in {item[0] for item in GAME_GENRES}:
        conditions.append('j.genero = %s')
        params.append(genero)

    if search_query:
        search_text = f"%{search_query}%"
        conditions.append('(j.nombre LIKE %s OR j.descripcion LIKE %s)')
        params.extend([search_text, search_text])

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY j.id, j.slug, j.nombre, j.descripcion, j.imagen, j.foro_tabla, j.plataforma, j.genero'
    if sort_order == 'destacado':
        query += ' ORDER BY comentario_count DESC, j.nombre'
    else:
        query += ' ORDER BY j.nombre'

    cursor.execute(query, tuple(params))
    juegos_raw = cursor.fetchall()
    juegos = []

    for juego in juegos_raw:
        juego_id = juego[0]
        try:
            cursor.execute(
                "SELECT id, titulo, contenido, usuario, likes FROM foro_posts WHERE juego_id = ? ORDER BY likes DESC, fecha_creacion DESC LIMIT 1",
                (juego_id,)
            )
            destacado = cursor.fetchone()
        except Exception:
            ensure_forum_posts_table()
            cursor.execute(
                "SELECT id, titulo, contenido, usuario, likes FROM foro_posts WHERE juego_id = ? ORDER BY likes DESC, fecha_creacion DESC LIMIT 1",
                (juego_id,)
            )
            destacado = cursor.fetchone()

        contenido_resumido = None
        if destacado:
            contenido = (destacado[2] or '').strip()
            if len(contenido) > 140:
                contenido = contenido[:137] + '...'
            contenido_resumido = contenido

        juegos.append({
            'id': juego[0],
            'slug': juego[1],
            'nombre': juego[2],
            'descripcion': juego[3],
            'imagen': juego[4],
            'foro_tabla': juego[5],
            'plataforma': juego[6],
            'genero': juego[7],
            'comment_count': juego[8] or 0,
            'destacado': {
                'id': destacado[0],
                'titulo': destacado[1],
                'contenido': contenido_resumido,
                'usuario': destacado[3],
                'likes': destacado[4] or 0,
            } if destacado else None,
        })

    return juegos


def ensure_user_cartas_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_cartas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                carta TEXT NOT NULL,
                fecha_desbloqueo TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Las cartas repetidas son válidas para los sobres comprados.
        try:
            cursor.execute("DROP INDEX IF EXISTS unique_user_carta")
        except Exception:
            pass
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla user_cartas: {e}")


def ensure_user_recompensa_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_recompensa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                fecha_recibido TIMESTAMP NULL,
                usuario_confirmo BOOLEAN NOT NULL DEFAULT FALSE,
                fecha_confirmacion TIMESTAMP NULL,
                UNIQUE(user_id, post_id)
            )
        ''')
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla user_recompensa: {e}")


def ensure_user_recompensa_columns():
    """Agrega las columnas comentario y numero_amigo a user_recompensa si no existen"""
    try:
        ensure_column_exists('user_recompensa', 'comentario', "ALTER TABLE user_recompensa ADD COLUMN comentario TEXT")
        ensure_column_exists('user_recompensa', 'numero_amigo', "ALTER TABLE user_recompensa ADD COLUMN numero_amigo TEXT")
        ensure_column_exists('user_recompensa', 'estado', "ALTER TABLE user_recompensa ADD COLUMN estado TEXT NOT NULL DEFAULT 'pendiente'")
        ensure_column_exists('user_recompensa', 'fecha_recibido', "ALTER TABLE user_recompensa ADD COLUMN fecha_recibido TIMESTAMP NULL")
        ensure_column_exists('user_recompensa', 'usuario_confirmo', "ALTER TABLE user_recompensa ADD COLUMN usuario_confirmo BOOLEAN NOT NULL DEFAULT FALSE")
        ensure_column_exists('user_recompensa', 'fecha_confirmacion', "ALTER TABLE user_recompensa ADD COLUMN fecha_confirmacion TIMESTAMP NULL")
    except Exception as e:
        print(f"Error al agregar columnas a user_recompensa: {e}")


def ensure_user_recompensa_index():
    try:
        cursor.execute("CREATE INDEX idx_user_recompensa_perfil ON user_recompensa (user_id, usuario_confirmo, fecha)")
        db.commit()
    except Exception:
        pass


def ensure_foro_posts_cartas_column():
    """Agrega la columna precio_cartas a foro_posts si no existe"""
    try:
        ensure_column_exists('foro_posts', 'precio_cartas', "ALTER TABLE foro_posts ADD COLUMN precio_cartas INT DEFAULT NULL")
    except Exception as e:
        print(f"Error al agregar columna precio_cartas: {e}")


def ensure_foro_posts_requisitos_column():
    try:
        ensure_column_exists('foro_posts', 'requisitos_cartas', "ALTER TABLE foro_posts ADD COLUMN requisitos_cartas TEXT NULL")
    except Exception as e:
        print(f"Error al agregar columna requisitos_cartas: {e}")


def ensure_foro_posts_destacada_column():
    try:
        ensure_column_exists('foro_posts', 'destacada', "ALTER TABLE foro_posts ADD COLUMN destacada BOOLEAN NOT NULL DEFAULT FALSE")
    except Exception as e:
        print(f"Error al agregar columna destacada: {e}")


def ensure_reportes_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reportes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NULL,
                nombre TEXT NULL,
                email TEXT NULL,
                asunto TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla reportes: {e}")


def ensure_notificaciones_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reporte_id INTEGER NULL,
                mensaje TEXT NOT NULL,
                administrador TEXT NOT NULL DEFAULT 'Administrador',
                leida BOOLEAN NOT NULL DEFAULT FALSE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla notificaciones: {e}")


def ensure_user_suscripcion_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_suscripcion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                es_plus BOOLEAN DEFAULT FALSE,
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_vencimiento TIMESTAMP NULL,
                nombre_completo TEXT,
                direccion TEXT,
                edad INTEGER,
                FOREIGN KEY (user_id) REFERENCES usuarios(id)
            )
        ''')
        # Verificar si las columnas existen, si no agregarlas
        try:
            cursor.execute("ALTER TABLE user_suscripcion ADD COLUMN nombre_completo TEXT")
            db.commit()
        except:
            pass
        try:
            cursor.execute("ALTER TABLE user_suscripcion ADD COLUMN direccion TEXT")
            db.commit()
        except:
            pass
        try:
            cursor.execute("ALTER TABLE user_suscripcion ADD COLUMN edad INTEGER")
            db.commit()
        except:
            pass
    except Exception as e:
        print(f"Error al crear tabla user_suscripcion: {e}")


def ensure_payment_methods_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                descripcion TEXT,
                icono TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

        # Insertar métodos de pago disponibles
        metodos = [
            ('Billetera Digital', 'Paga directamente desde tu billetera digital', '💳'),
            ('Daviplata', 'Paga usando Daviplata', '📱'),
            ('Nequi', 'Paga usando Nequi', '📱'),
            ('Pago Contra Entrega', 'Paga cuando recibas tu orden', '🏠'),
            ('Mercado Pago', 'Paga usando Mercado Pago', '🛒'),
            ('PayPal', 'Paga usando tu cuenta de PayPal', '🌐'),
        ]

        for nombre, descripcion, icono in metodos:
            cursor.execute(
                "INSERT OR IGNORE INTO payment_methods (nombre, descripcion, icono) VALUES (?, ?, ?)",
                (nombre, descripcion, icono)
            )
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla payment_methods: {e}")


def ensure_payment_orders_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                metodo_pago TEXT NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                referencia TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_confirmacion TIMESTAMP NULL,
                FOREIGN KEY (user_id) REFERENCES usuarios(id)
            )
        ''')
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla payment_orders: {e}")


def ensure_facturas_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS facturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                numero_factura TEXT NOT NULL UNIQUE,
                concepto TEXT NOT NULL,
                monto REAL NOT NULL,
                metodo_pago TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pagada',
                fecha_emision TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios(id)
            )
        ''')
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla facturas: {e}")


def ensure_membership_refunds_table():
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS membership_refunds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                estado TEXT DEFAULT 'pendiente',
                fecha_procesamiento TIMESTAMP NULL,
                notas TEXT,
                FOREIGN KEY (user_id) REFERENCES usuarios(id)
            )
        ''')
        db.commit()
    except Exception as e:
        print(f"Error al crear tabla membership_refunds: {e}")


def check_user_plus(user_id):
    """Verifica si un usuario tiene membresía Plus activa"""
    try:
        ensure_user_suscripcion_table()
        cursor.execute(
            "SELECT es_plus, fecha_vencimiento FROM user_suscripcion WHERE user_id = %s",
            (user_id,)
        )
        result = cursor.fetchone()
        if result:
            es_plus, fecha_vencimiento = result
            if es_plus and (fecha_vencimiento is None or fecha_vencimiento > datetime.now()):
                return True
        return False
    except Exception as e:
        print(f"Error al verificar Plus: {e}")
        return False


def add_points(user_id, base_points):
    """Agrega puntos a un usuario, aplicando multiplicador 2x si tiene Plus"""
    try:
        ensure_user_points_column()
        is_plus = check_user_plus(user_id)
        points_to_add = base_points * 2 if is_plus else base_points
        cursor.execute("UPDATE usuarios SET puntaje = puntaje + %s WHERE id = %s", (points_to_add, user_id))
        db.commit()
        return points_to_add
    except Exception as e:
        print(f"Error al agregar puntos: {e}")
        return 0


REGULAR_CARD_IMAGES = [f'IMG/carta {number}.png' for number in range(1, 5)] + [
    'IMG/carta 5.png.png',
    'IMG/carta 6.png.png',
    'IMG/carta 7.png.png',
]
PLUS_CARD_IMAGES = [
    'IMG/carta plus1.png.png',
    'IMG/carta plus2.png.png',
    'IMG/carta plus3.png.png',
]
CARD_IMAGES = REGULAR_CARD_IMAGES + PLUS_CARD_IMAGES
INITIAL_CARD_IMAGES = REGULAR_CARD_IMAGES[:2]
CARD_GAME_GROUPS = [
    ('Minecraft', REGULAR_CARD_IMAGES[:2]),
    ('Rocket League', REGULAR_CARD_IMAGES[2:4]),
    ('Clash Royale', REGULAR_CARD_IMAGES[4:5]),
    ('Geometry Dash', REGULAR_CARD_IMAGES[5:6]),
    ('Brawl Stars', REGULAR_CARD_IMAGES[6:7]),
]
CARD_REQUIREMENT_GROUPS = CARD_GAME_GROUPS + [('Cartas Plus', PLUS_CARD_IMAGES)]
CARD_GAME_IMAGES = {game_name.lower(): game_cards for game_name, game_cards in CARD_REQUIREMENT_GROUPS}
PACK_PRICE = 500
CARD_PACKS = {
    'basica': {'name': 'Sobre básico', 'price': 500, 'cards': 2, 'plus_only': False},
    'pro': {'name': 'Sobre pro', 'price': 1000, 'cards': 5, 'plus_only': False},
    'super': {'name': 'Sobre súper', 'price': 1800, 'cards': 6, 'plus_only': False},
    'plus': {'name': 'Sobre plus', 'price': 3200, 'cards': 5, 'plus_only': True},
}
REWARD_POINTS = 200


def parse_card_requirements(raw_requirements):
    requirements = {}
    for line in (raw_requirements or '').splitlines():
        if ':' not in line:
            continue
        game_name, quantity_text = line.split(':', 1)
        game_key = game_name.strip().lower()
        try:
            quantity = int(quantity_text.strip())
        except ValueError:
            continue
        if game_key in CARD_GAME_IMAGES and 1 <= quantity <= 500:
            requirements[game_key] = requirements.get(game_key, 0) + quantity
    return requirements


def format_card_requirements(requirements):
    return '\n'.join(
        f'{game_name.title()}: {quantity}'
        for game_name, quantity in requirements.items()
    )


def select_pack_cards(pack_key, amount):
    if pack_key == 'plus':
        card_pool = PLUS_CARD_IMAGES + REGULAR_CARD_IMAGES
        weights = [0.90 / len(PLUS_CARD_IMAGES)] * len(PLUS_CARD_IMAGES) + [0.10 / len(REGULAR_CARD_IMAGES)] * len(REGULAR_CARD_IMAGES)
    else:
        card_pool = REGULAR_CARD_IMAGES + PLUS_CARD_IMAGES
        weights = [0.97 / len(REGULAR_CARD_IMAGES)] * len(REGULAR_CARD_IMAGES) + [0.03 / len(PLUS_CARD_IMAGES)] * len(PLUS_CARD_IMAGES)
    return random.choices(card_pool, weights=weights, k=amount)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Necesitas iniciar sesión para ver esta página', 'warning')
            return redirect(url_for('iniciarsesion'))
        return f(*args, **kwargs)
    return decorated

def is_admin_user():
    if str(session.get('user_role')) == '1':
        return True
    username = (session.get('username') or '').strip().lower()
    return username in {'abril', 'admin', 'administrador'}


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Necesitas iniciar sesión', 'warning')
            return redirect(url_for('iniciarsesion'))
        if not is_admin_user():
            flash('No tienes permisos para acceder a esta página', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

@app.context_processor
def inject_user_points():
    points = session.get('points', 0)
    if session.get('user_id') and points == 0:
        try:
            cursor.execute("SELECT COALESCE(puntaje, 0) FROM usuarios WHERE id = %s", (session.get('user_id'),))
            row = cursor.fetchone()
            if row:
                points = row[0]
                session['points'] = points
        except Exception:
            pass
    return {'user_points': points}

@app.route('/')
def index():
    user_role = 1 if is_admin_user() else 0
    ensure_game_catalog()
    cursor.execute("SELECT id, slug, nombre, descripcion, imagen, foro_tabla FROM juego_catalogo ORDER BY id LIMIT 3")
    juegos_destacados = cursor.fetchall()
    show_welcome_guide = session.pop('show_welcome_guide', False)
    return render_template('index.html', user_role=user_role, juegos_destacados=juegos_destacados, show_welcome_guide=show_welcome_guide)

@app.route('/elpunto')
def elpunto():
    return render_template('elpunto.html')

@app.route('/foros')
@login_required
def foros():
    ensure_chat_messages_table()
    plataforma = request.args.get('plataforma', '').strip().lower()
    genero = request.args.get('genero', '').strip().lower()
    search_query = request.args.get('q', '').strip()
    sort_order = request.args.get('sort', '').strip().lower()
    juegos_list = get_juegos_con_destacado(plataforma=plataforma, genero=genero, search_query=search_query, sort_order=sort_order)
    user_role = 1 if session.get('user_role') == 1 or is_admin_user() else 0
    return render_template('foros.html', juegos=juegos_list, plataforma=plataforma, genero=genero, generos=GAME_GENRES, search_query=search_query, sort_order=sort_order, user_role=user_role)


@app.route('/api/juegos/<slug>/chat', methods=['GET', 'POST'])
@login_required
def chat_juego(slug):
    ensure_game_catalog()
    ensure_chat_messages_table()
    cursor.execute("SELECT id, nombre FROM juego_catalogo WHERE slug = %s", (slug,))
    juego = cursor.fetchone()

    if not juego:
        return jsonify({'error': 'Ese juego no existe'}), 404

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        mensaje = (data.get('mensaje') or '').strip()
        if not mensaje:
            return jsonify({'error': 'Escribe un mensaje'}), 400
        if len(mensaje) > 500:
            return jsonify({'error': 'El mensaje no puede superar 500 caracteres'}), 400

        usuario = session.get('username') or 'Usuario'
        cursor.execute(
            "INSERT INTO chat_mensajes (juego_id, user_id, usuario, mensaje) VALUES (%s, %s, %s, %s)",
            (juego[0], session.get('user_id'), usuario, mensaje)
        )
        db.commit()
        return jsonify({'ok': True})

    cursor.execute(
        "SELECT usuario, mensaje, fecha_creacion FROM chat_mensajes WHERE juego_id = %s ORDER BY fecha_creacion DESC LIMIT 30",
        (juego[0],)
    )
    mensajes = [
        {
            'usuario': row[0],
            'mensaje': row[1],
            'fecha': row[2].strftime('%H:%M') if row[2] else ''
        }
        for row in reversed(cursor.fetchall())
    ]
    return jsonify({'juego': juego[1], 'mensajes': mensajes})

@app.route('/juegos')
@login_required
def juegos():
    plataforma = request.args.get('plataforma', '').strip().lower()
    genero = request.args.get('genero', '').strip().lower()
    search_query = request.args.get('q', '').strip()
    sort_order = request.args.get('sort', '').strip().lower()
    juegos_list = get_juegos_con_destacado(plataforma=plataforma, genero=genero, search_query=search_query, sort_order=sort_order)
    user_role = 1 if session.get('user_role') == 1 or is_admin_user() else 0
    user_id = session.get('user_id')
    is_plus = check_user_plus(user_id)
    return render_template('juegos.html', juegos=juegos_list, plataforma=plataforma, genero=genero, generos=GAME_GENRES, search_query=search_query, sort_order=sort_order, user_role=user_role, is_plus=is_plus)

@app.route('/foros/<slug>', methods=['GET', 'POST'])
@login_required
def foro_juego(slug):
    ensure_game_catalog()
    cursor.execute("SELECT id, slug, nombre, descripcion, imagen, foro_tabla, trailer_url FROM juego_catalogo WHERE slug = %s", (slug,))
    juego = cursor.fetchone()

    if not juego:
        flash('Ese juego no existe', 'danger')
        return redirect(url_for('foros'))

    foro_tabla = juego[5]
    ensure_forum_posts_table()
    ensure_user_post_likes_table()

    if request.method == 'POST':
        post_type = request.form.get('post_type', 'discussion')
        titulo = request.form.get('titulo', '').strip()
        contenido = request.form.get('contenido', '').strip()
        usuario = session.get('username', 'Usuario')

        if not titulo or not contenido:
            flash('Debes completar título y descripción.', 'danger')
            return redirect(url_for('foro_juego', slug=slug))

        if post_type == 'news':
            if not is_admin_user():
                flash('No tienes permisos para publicar noticias.', 'danger')
                return redirect(url_for('foro_juego', slug=slug))
            try:
                cursor.execute(
                    "INSERT INTO foro_posts (juego_id, slug, titulo, contenido, usuario) VALUES (?, ?, ?, ?, ?)",
                    (juego[0], 'noticia', titulo, contenido, usuario)
                )
                db.commit()
            except Exception:
                db.rollback()
                flash('No se pudo publicar la noticia. Revisa la conexión con SQLite.', 'danger')
                return redirect(url_for('foro_juego', slug=slug))
            flash('Noticia publicada correctamente.', 'success')
            return redirect(url_for('foro_juego', slug=slug))

        try:
            cursor.execute(
                "INSERT INTO foro_posts (juego_id, slug, titulo, contenido, usuario) VALUES (?, ?, ?, ?, ?)",
                (juego[0], slug, titulo, contenido, usuario)
            )
            db.commit()
        except Exception:
            db.rollback()
            flash('No se pudo publicar el comentario. Revisa la conexión con SQLite.', 'danger')
            return redirect(url_for('foro_juego', slug=slug))
        user_id = session.get('user_id')
        points_added = add_points(user_id, 100)
        session['points'] = session.get('points', 0) + points_added
        flash(f'Tu mensaje se publicó en el foro y ganaste {points_added} puntos.', 'success')
        return redirect(url_for('foro_juego', slug=slug))

    try:
        cursor.execute(
            "SELECT id, titulo, contenido, usuario, fecha_creacion FROM foro_posts WHERE juego_id = ? AND slug = 'noticia' ORDER BY fecha_creacion DESC",
            (juego[0],)
        )
        news_posts = cursor.fetchall()
    except Exception:
        ensure_forum_posts_table()
        cursor.execute(
            "SELECT id, titulo, contenido, usuario, fecha_creacion FROM foro_posts WHERE juego_id = ? AND slug = 'noticia' ORDER BY fecha_creacion DESC",
            (juego[0],)
        )
        news_posts = cursor.fetchall()

    try:
        cursor.execute(
            "SELECT id, titulo, contenido, usuario, fecha_creacion, likes FROM foro_posts WHERE juego_id = ? AND (slug IS NULL OR slug != 'noticia' AND slug != 'noticia_card') ORDER BY likes DESC, fecha_creacion DESC",
            (juego[0],)
        )
        posts = cursor.fetchall()
    except Exception:
        ensure_forum_posts_table()
        cursor.execute(
            "SELECT id, titulo, contenido, usuario, fecha_creacion, likes FROM foro_posts WHERE juego_id = ? AND (slug IS NULL OR slug != 'noticia' AND slug != 'noticia_card') ORDER BY likes DESC, fecha_creacion DESC",
            (juego[0],)
        )
        posts = cursor.fetchall()

    user_like_counts = {}
    user_id = session.get('user_id')
    if user_id and posts:
        try:
            post_ids = [post[0] for post in posts]
            placeholders = ', '.join(['?'] * len(post_ids))
            cursor.execute(
                f"SELECT post_id, like_count FROM user_post_likes WHERE user_id = ? AND post_id IN ({placeholders})",
                (user_id, *post_ids)
            )
            user_like_counts = {post_id: like_count for post_id, like_count in cursor.fetchall()}
        except Exception:
            user_like_counts = {}

    return render_template(
        'foro_juego.html',
        juego=juego,
        posts=posts,
        news_posts=news_posts,
        user_role=1 if is_admin_user() else 0,
        user_like_counts=user_like_counts,
        trailer_embed_url=youtube_embed_url(juego[6]),
    )

@app.route('/foros/<slug>/posts/<int:post_id>/editar', methods=['GET', 'POST'])
@admin_required
def editar_post_admin(slug, post_id):
    ensure_game_catalog()
    cursor.execute("SELECT id, slug, nombre, descripcion, imagen, foro_tabla, trailer_url FROM juego_catalogo WHERE slug = %s", (slug,))
    juego = cursor.fetchone()
    
    if not juego:
        flash('Ese juego no existe', 'danger')
        return redirect(url_for('foros'))

    cursor.execute("SELECT id, titulo, contenido, usuario, likes FROM foro_posts WHERE id = %s AND juego_id = %s", (post_id, juego[0]))
    post = cursor.fetchone()
    if not post:
        flash('Ese comentario no existe', 'danger')
        return redirect(url_for('foro_juego', slug=slug))

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        contenido = request.form.get('contenido', '').strip()
        if not titulo or not contenido:
            flash('Debes completar título y contenido.', 'danger')
            return redirect(url_for('editar_post_admin', slug=slug, post_id=post_id))

        cursor.execute(
            "UPDATE foro_posts SET titulo = %s, contenido = %s WHERE id = %s AND juego_id = %s",
            (titulo, contenido, post_id, juego[0])
        )
        db.commit()
        flash('Comentario actualizado correctamente.', 'success')
        return redirect(url_for('foro_juego', slug=slug))

    try:
        cursor.execute(
            "SELECT id, titulo, contenido, usuario, fecha_creacion, likes FROM foro_posts WHERE juego_id = ? ORDER BY likes DESC, fecha_creacion DESC",
            (juego[0],)
        )
        posts = cursor.fetchall()
    except Exception:
        ensure_forum_posts_table()
        cursor.execute(
            "SELECT id, titulo, contenido, usuario, fecha_creacion, likes FROM foro_posts WHERE juego_id = ? ORDER BY likes DESC, fecha_creacion DESC",
            (juego[0],)
        )
        posts = cursor.fetchall()

    return render_template(
        'foro_juego.html',
        juego=juego,
        posts=posts,
        news_posts=[],
        user_like_counts={},
        user_role=session.get('user_role'),
        edit_mode=True,
        editing_post=post,
        trailer_embed_url=youtube_embed_url(juego[6]),
    )

@app.route('/foros/<slug>/posts/<int:post_id>/eliminar', methods=['POST'])
@admin_required
def eliminar_post_admin(slug, post_id):
    ensure_game_catalog()
    cursor.execute("SELECT id FROM juego_catalogo WHERE slug = %s", (slug,))
    juego = cursor.fetchone()
    if not juego:
        flash('Ese juego no existe', 'danger')
        return redirect(url_for('foros'))

    cursor.execute("DELETE FROM foro_posts WHERE id = %s AND juego_id = %s", (post_id, juego[0]))
    db.commit()
    flash('Comentario eliminado correctamente.', 'success')
    return redirect(url_for('foro_juego', slug=slug))

@app.route('/foros/<slug>/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(slug, post_id):
    ensure_game_catalog()
    ensure_forum_posts_table()
    ensure_user_post_likes_table()
    cursor.execute("SELECT id FROM juego_catalogo WHERE slug = %s", (slug,))
    juego = cursor.fetchone()

    if not juego:
        flash('Ese juego no existe', 'danger')
        return redirect(url_for('foros'))

    user_id = session.get('user_id')
    cursor.execute("SELECT like_count FROM user_post_likes WHERE user_id = %s AND post_id = %s", (user_id, post_id))
    row = cursor.fetchone()
    current_user_likes = row[0] if row else 0

    if current_user_likes >= 1:
        flash('Ya has dado tu like a este comentario.', 'warning')
        return redirect(url_for('foro_juego', slug=slug))

    if row:
        cursor.execute(
            "UPDATE user_post_likes SET like_count = 1, fecha_creacion = CURRENT_TIMESTAMP WHERE user_id = %s AND post_id = %s",
            (user_id, post_id)
        )
    else:
        cursor.execute(
            "INSERT INTO user_post_likes (user_id, post_id, like_count) VALUES (%s, %s, 1)",
            (user_id, post_id)
        )

    try:
        cursor.execute("UPDATE foro_posts SET likes = likes + 1 WHERE id = ?", (post_id,))
    except Exception:
        ensure_forum_posts_table()
        cursor.execute("UPDATE foro_posts SET likes = likes + 1 WHERE id = ?", (post_id,))
    db.commit()
    flash('¡Se añadió un like al comentario!', 'success')
    return redirect(url_for('foro_juego', slug=slug))

@app.route('/admin/juegos/nuevo', methods=['GET', 'POST'])
@admin_required
def crear_juego_admin():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        imagen = request.form.get('imagen', '').strip()
        plataforma = request.form.get('plataforma', 'pc').strip().lower()
        trailer_url = request.form.get('trailer_url', '').strip()
        genero = request.form.get('genero', '').strip().lower()

        if not nombre or not descripcion or not slug:
            flash('Completa nombre, descripción y slug.', 'danger')
            return redirect(url_for('crear_juego_admin'))

        if plataforma not in {'pc', 'movil'}:
            plataforma = 'pc'

        if genero not in {item[0] for item in GAME_GENRES}:
            genero = None

        if trailer_url and not youtube_embed_url(trailer_url):
            flash('El link del trailer debe ser un enlace válido de YouTube.', 'danger')
            return redirect(url_for('crear_juego_admin'))

        slug_sanitizado = secure_filename(slug).lower()
        if not slug_sanitizado:
            flash('El slug no es válido.', 'danger')
            return redirect(url_for('crear_juego_admin'))

        cursor.execute("SELECT id FROM juego_catalogo WHERE slug = %s", (slug_sanitizado,))
        if cursor.fetchone():
            flash('Ya existe un foro con ese slug.', 'danger')
            return redirect(url_for('crear_juego_admin'))

        cursor.execute(
            "INSERT INTO juego_catalogo (slug, nombre, descripcion, imagen, foro_tabla, plataforma, trailer_url, genero) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (slug_sanitizado, nombre.upper(), descripcion, imagen or 'IMG/default.png', f'foros_{slug_sanitizado}', plataforma, trailer_url or None, genero)
        )
        db.commit()
        flash('Se creó el nuevo foro correctamente.', 'success')
        return redirect(url_for('foros'))

    return render_template('admin_juego_form.html', juego=None, edit=False, generos=GAME_GENRES, user_role=1 if is_admin_user() else 0)


@app.route('/admin/juegos/<int:juego_id>/editar', methods=['GET', 'POST'])
@admin_required
def editar_juego_admin(juego_id):
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        imagen = request.form.get('imagen', '').strip()
        plataforma = request.form.get('plataforma', 'pc').strip().lower()
        trailer_url = request.form.get('trailer_url', '').strip()
        genero = request.form.get('genero', '').strip().lower()

        if not nombre or not descripcion or not slug:
            flash('Completa nombre, descripción y slug.', 'danger')
            return redirect(url_for('editar_juego_admin', juego_id=juego_id))

        if genero not in {item[0] for item in GAME_GENRES}:
            genero = None

        if trailer_url and not youtube_embed_url(trailer_url):
            flash('El link del trailer debe ser un enlace válido de YouTube.', 'danger')
            return redirect(url_for('editar_juego_admin', juego_id=juego_id))

        slug_sanitizado = secure_filename(slug).lower()
        cursor.execute("SELECT id FROM juego_catalogo WHERE slug = %s AND id != %s", (slug_sanitizado, juego_id))
        if cursor.fetchone():
            flash('Ya existe un foro con ese slug.', 'danger')
            return redirect(url_for('editar_juego_admin', juego_id=juego_id))

        cursor.execute(
            "UPDATE juego_catalogo SET slug = %s, nombre = %s, descripcion = %s, imagen = %s, plataforma = %s, trailer_url = %s, genero = %s WHERE id = %s",
            (slug_sanitizado, nombre.upper(), descripcion, imagen or 'IMG/default.png', plataforma if plataforma in {'pc', 'movil'} else 'pc', trailer_url or None, genero, juego_id)
        )
        db.commit()
        flash('Foro actualizado correctamente.', 'success')
        return redirect(url_for('juegos'))

    cursor.execute("SELECT id, slug, nombre, descripcion, imagen, foro_tabla, plataforma, trailer_url, genero FROM juego_catalogo WHERE id = %s", (juego_id,))
    juego = cursor.fetchone()
    if not juego:
        flash('Ese foro no existe.', 'danger')
        return redirect(url_for('juegos'))

    return render_template('admin_juego_form.html', juego=juego, edit=True, generos=GAME_GENRES, user_role=1 if is_admin_user() else 0)


@app.route('/admin/juegos/<int:juego_id>/eliminar', methods=['POST'])
@admin_required
def eliminar_juego_admin(juego_id):
    cursor.execute("SELECT foro_tabla FROM juego_catalogo WHERE id = %s", (juego_id,))
    juego = cursor.fetchone()
    if juego:
        foro_tabla = juego[0]
        if foro_tabla:
            safe_table = secure_filename(foro_tabla).lower()
            try:
                cursor.execute(f"DROP TABLE IF EXISTS `{safe_table}`")
            except Exception:
                pass
        cursor.execute("DELETE FROM foro_posts WHERE juego_id = %s", (juego_id,))
        cursor.execute("DELETE FROM juego_catalogo WHERE id = %s", (juego_id,))
        db.commit()
        flash('Foro eliminado correctamente.', 'success')
    else:
        flash('Ese foro no existe.', 'danger')
    return redirect(url_for('foros'))



@app.route('/membresia')
@login_required
def membresia():
    ensure_user_suscripcion_table()
    ensure_payment_methods_table()
    ensure_forum_posts_table()
    
    user_id = session.get('user_id')
    is_plus = check_user_plus(user_id)
    expiration_date = None
    
    if is_plus:
        cursor.execute(
            "SELECT fecha_vencimiento FROM user_suscripcion WHERE user_id = %s AND es_plus = TRUE",
            (user_id,)
        )
        result = cursor.fetchone()
        if result and result[0]:
            expiration_date = result[0].strftime('%d/%m/%Y')
    
    cursor.execute("SELECT id, nombre, descripcion, icono FROM payment_methods ORDER BY id")
    payment_methods = [{'id': row[0], 'nombre': row[1], 'descripcion': row[2], 'icono': row[3]} for row in cursor.fetchall()]
    
    # Obtener recompensas por tipo de cliente
    recompensas_premium = []
    recompensas_normal = []
    
    try:
        cursor.execute("""
            SELECT id, titulo, contenido, usuario, fecha_creacion, tipo_cliente 
            FROM foro_posts 
            WHERE slug = 'recompensa_semanal' 
            ORDER BY fecha_creacion DESC
        """)
        recompensas_raw = cursor.fetchall()
        
        for row in recompensas_raw:
            recompensa = {
                'id': row[0],
                'titulo': row[1],
                'contenido': row[2],
                'usuario': row[3],
                'fecha_creacion': row[4],
                'tipo_cliente': row[5] or 'ambos'
            }
            
            if recompensa['tipo_cliente'] == 'premium':
                recompensas_premium.append(recompensa)
            elif recompensa['tipo_cliente'] == 'normal':
                recompensas_normal.append(recompensa)
            else:
                recompensas_premium.append(recompensa)
                recompensas_normal.append(recompensa)
    except Exception as e:
        print(f"Error al obtener recompensas: {e}")
    
    return render_template('membresia.html', 
                         is_plus=is_plus, 
                         expiration_date=expiration_date, 
                         payment_methods=payment_methods,
                         recompensas_premium=recompensas_premium,
                         recompensas_normal=recompensas_normal)


@app.route('/procesar_pago/<int:method_id>', methods=['POST'])
@login_required
def procesar_pago(method_id):
    ensure_payment_methods_table()
    
    cursor.execute("SELECT nombre FROM payment_methods WHERE id = %s", (method_id,))
    result = cursor.fetchone()
    
    if not result:
        return "Método de pago inválido", 400
    
    metodo_nombre = result[0]
    user_id = session.get('user_id')
    
    # HTML específico para cada método de pago con datos reales que pide cada uno
    if metodo_nombre == 'Billetera Digital':
        html = """
        <form id="formPago" method="post" action="/confirmar_pago">
            <div class="alert alert-info alert-dismissible fade show auto-dismiss-alert" style="font-size: 0.9em; color: white; background-color: #17a2b8;">
                💳 Por favor ingresa tus datos de Billetera Digital
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Billetera Digital:</label>
                <input type="text" class="form-control" name="billetera_num" placeholder="Ej: 3001234567" maxlength="15" required>
                <small style="color: white;">Número telefónico asociado a tu billetera</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Contraseña:</label>
                <input type="password" class="form-control" name="billetera_pass" required>
                <small style="color: white;">Contraseña de acceso a tu billetera</small>
            </div>
            <div class="mb-3">
                <label class="form-label">PIN de Seguridad (4 dígitos):</label>
                <input type="password" class="form-control" name="billetera_pin" placeholder="••••" maxlength="4" pattern="[0-9]{4}" required>
                <small style="color: white;">PIN de 4 dígitos configurado en tu billetera</small>
            </div>
            <input type="hidden" name="method_id" value="%d">
            <button type="submit" class="btn btn-warning w-100">Pagar $14.999</button>
        </form>
        """ % method_id
    
    elif metodo_nombre == 'Daviplata':
        html = """
        <form id="formPago" method="post" action="/confirmar_pago">
            <div class="alert alert-info alert-dismissible fade show auto-dismiss-alert" style="font-size: 0.9em; color: white; background-color: #17a2b8;">
                📱 Ingresa tus datos de Daviplata
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Teléfono:</label>
                <input type="text" class="form-control" name="daviplata_num" placeholder="Ej: 3001234567" maxlength="10" pattern="[0-9]{10}" required>
                <small style="color: white;">Número del celular registrado en Davivienda</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Clave Daviplata:</label>
                <input type="password" class="form-control" name="daviplata_pass" required>
                <small style="color: white;">Clave de acceso a tu Daviplata</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Tarjeta (últimos 4 dígitos):</label>
                <input type="text" class="form-control" name="daviplata_tarjeta" placeholder="••••" maxlength="4" pattern="[0-9]{4}" required>
                <small style="color: white;">Últimos 4 dígitos de tu tarjeta Davivienda</small>
            </div>
            <input type="hidden" name="method_id" value="%d">
            <button type="submit" class="btn btn-warning w-100">Pagar $14.999</button>
        </form>
        """ % method_id
    
    elif metodo_nombre == 'Nequi':
        html = """
        <form id="formPago" method="post" action="/confirmar_pago">
            <div class="alert alert-info alert-dismissible fade show auto-dismiss-alert" style="font-size: 0.9em; color: white; background-color: #17a2b8;">
                📱 Ingresa tus datos de Nequi
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Teléfono Nequi:</label>
                <input type="text" class="form-control" name="nequi_num" placeholder="Ej: 3001234567" maxlength="10" pattern="[0-9]{10}" required>
                <small style="color: white;">Número del celular registrado en Nequi</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Contraseña Nequi (4 dígitos):</label>
                <input type="password" class="form-control" name="nequi_pass" placeholder="••••" maxlength="4" pattern="[0-9]{4}" required>
                <small style="color: white;">Contraseña de acceso (4 dígitos numéricos)</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Tarjeta:</label>
                <input type="text" class="form-control" name="nequi_tarjeta" placeholder="Ej: 4532123456789012" maxlength="16" pattern="[0-9]{16}" required>
                <small style="color: white;">Número completo de tu tarjeta de débito</small>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Fecha de Vencimiento:</label>
                    <input type="text" class="form-control" name="nequi_fecha" placeholder="MM/YY" maxlength="5" pattern="[0-9]{2}/[0-9]{2}" required>
                    <small style="color: white;">Formato: MM/YY</small>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">CVV:</label>
                    <input type="password" class="form-control" name="nequi_cvv" placeholder="•••" maxlength="3" pattern="[0-9]{3}" required>
                    <small style="color: white;">Código de seguridad (3 dígitos)</small>
                </div>
            </div>
            <input type="hidden" name="method_id" value="%d">
            <button type="submit" class="btn btn-warning w-100">Pagar $14.999</button>
        </form>
        """ % method_id
    
    elif metodo_nombre == 'Pago Contra Entrega':
        html = """
        <form id="formPago" method="post" action="/confirmar_pago">
            <div class="alert alert-warning alert-dismissible fade show auto-dismiss-alert" style="font-size: 0.9em; color: white; background-color: #ffc107;">
                📦 <strong>Pago Contra Entrega</strong><br>
                Se te enviará un código de activación. Pagarás cuando lo recibas.
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
            </div>
            <div class="mb-3">
                <label class="form-label">Dirección Completa de Entrega:</label>
                <input type="text" class="form-control" name="direccion_entrega" placeholder="Calle, número, apartamento, ciudad" required>
                <small style="color: white;">Ingresa la dirección donde recibirás tu código de activación</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Teléfono de Contacto:</label>
                <input type="text" class="form-control" name="telefono_entrega" placeholder="Ej: 3001234567" maxlength="10" required>
                <small style="color: white;">Número para confirmar la entrega</small>
            </div>
            <input type="hidden" name="method_id" value="%d">
            <button type="submit" class="btn btn-warning w-100">Solicitar Pago Contra Entrega</button>
        </form>
        """ % method_id
    
    elif metodo_nombre == 'Mercado Pago':
        html = """
        <form id="formPago" method="post" action="/confirmar_pago">
            <div class="alert alert-info alert-dismissible fade show auto-dismiss-alert" style="font-size: 0.9em; color: white; background-color: #17a2b8;">
                🛒 Completa tu información para Mercado Pago
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
            </div>
            <div class="mb-3">
                <label class="form-label">Correo Electrónico Mercado Pago:</label>
                <input type="email" class="form-control" name="mercadopago_email" placeholder="tu@email.com" required>
                <small style="color: white;">Email asociado a tu cuenta de Mercado Pago</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Número de Tarjeta:</label>
                <input type="text" class="form-control" name="mercadopago_tarjeta" placeholder="Ej: 4532123456789012" maxlength="16" pattern="[0-9]{16}" required>
                <small style="color: white;">Número completo de tu tarjeta de crédito/débito</small>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Fecha de Vencimiento:</label>
                    <input type="text" class="form-control" name="mercadopago_fecha" placeholder="MM/YY" maxlength="5" pattern="[0-9]{2}/[0-9]{2}" required>
                    <small style="color: white;">Formato: MM/YY</small>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">CVV:</label>
                    <input type="password" class="form-control" name="mercadopago_cvv" placeholder="•••" maxlength="3" pattern="[0-9]{3}" required>
                    <small style="color: white;">Código de seguridad (3 dígitos)</small>
                </div>
            </div>
            <input type="hidden" name="method_id" value="%d">
            <button type="submit" class="btn btn-warning w-100">Pagar $14.999</button>
        </form>
        """ % method_id
    
    elif metodo_nombre == 'PayPal':
        html = """
        <form id="formPago" method="post" action="/confirmar_pago">
            <div class="alert alert-info alert-dismissible fade show auto-dismiss-alert" style="font-size: 0.9em; color: white; background-color: #17a2b8;">
                🌐 Ingresa tus datos de PayPal
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
            </div>
            <div class="mb-3">
                <label class="form-label">Correo de PayPal:</label>
                <input type="email" class="form-control" name="paypal_email" placeholder="tu@email.com" required>
                <small style="color: white;">Email principal de tu cuenta PayPal</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Contraseña de PayPal:</label>
                <input type="password" class="form-control" name="paypal_pass" required>
                <small style="color: white;">Contraseña de tu cuenta PayPal</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Teléfono Asociado (opcional):</label>
                <input type="text" class="form-control" name="paypal_telefono" placeholder="Ej: 3001234567" maxlength="10">
                <small style="color: white;">Número de teléfono en tu perfil PayPal</small>
            </div>
            <input type="hidden" name="method_id" value="%d">
            <button type="submit" class="btn btn-warning w-100">Pagar $14.999</button>
        </form>
        """ % method_id
    
    else:
        html = "<p>Método de pago no disponible</p>"
    
    return html


@app.route('/confirmar_pago', methods=['POST'])
@login_required
def confirmar_pago():
    ensure_user_suscripcion_table()
    ensure_payment_orders_table()
    ensure_facturas_table()
    
    user_id = session.get('user_id')
    method_id = request.form.get('method_id')
    nombre_completo = request.form.get('nombre_completo', '').strip()
    direccion = request.form.get('direccion', '').strip()
    edad = request.form.get('edad', '').strip()
    
    # Se omite el paso de datos personales en la compra de membresía.
    # Si llegan vacíos, se almacenan como datos opcionales nulos.
    edad_int = None
    try:
        if edad:
            edad_int = int(edad)
            if edad_int < 13 or edad_int > 120:
                flash('La edad debe estar entre 13 y 120 años', 'danger')
                return redirect(url_for('membresia'))
    except ValueError:
        edad_int = None
    
    cursor.execute("SELECT nombre FROM payment_methods WHERE id = %s", (method_id,))
    result = cursor.fetchone()
    
    if not result:
        flash('Método de pago inválido', 'danger')
        return redirect(url_for('membresia'))
    
    metodo_nombre = result[0]
    monto = 14999
    referencia = f"PLUS-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    numero_factura = f"FAC-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    
    try:
        # Insertar orden de pago
        cursor.execute(
            "INSERT INTO payment_orders (user_id, monto, metodo_pago, referencia, estado) VALUES (%s, %s, %s, %s, 'pendiente')",
            (user_id, monto, metodo_nombre, referencia)
        )

        cursor.execute(
            "INSERT INTO facturas (user_id, numero_factura, concepto, monto, metodo_pago, estado) VALUES (%s, %s, %s, %s, %s, 'pagada')",
            (user_id, numero_factura, 'Membresía Plus por 30 días', monto, metodo_nombre)
        )
        db.commit()
        
        # Activar Plus inmediatamente (en producción sería después de confirmación de pago)
        fecha_vencimiento = datetime.now() + timedelta(days=30)
        
        cursor.execute(
            "INSERT INTO user_suscripcion (user_id, es_plus, fecha_vencimiento, nombre_completo, direccion, edad) VALUES (%s, TRUE, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE es_plus = TRUE, fecha_vencimiento = VALUES(fecha_vencimiento), nombre_completo = VALUES(nombre_completo), direccion = VALUES(direccion), edad = VALUES(edad)",
            (user_id, fecha_vencimiento, nombre_completo or None, direccion or None, edad_int)
        )
        db.commit()
        
        flash(f'¡Felicidades! Ahora eres un usuario PLUS. Ganarás 2x más puntos en todas tus actividades.', 'success')
    except Exception as e:
        print(f"Error al procesar pago: {e}")
        flash('Error al procesar el pago', 'danger')
    
    return redirect(url_for('membresia'))

@app.route('/register')
def register():
    return render_template('register.html')
@app.route('/iniciarsesion', methods=['GET', 'POST'])
def iniciarsesion():
    if request.method == 'POST':
        ensure_username_column()
        identifier = request.form.get('nombre', '').strip()
        password = request.form.get('password', '')
        if not validar_captcha(request.form.get('not_robot')):
            flash('Verificación CAPTCHA incorrecta. Inténtalo de nuevo.', 'danger')
            return render_template('login.html', identifier=identifier)
        try:
            cursor.execute(
                "SELECT id, password, rol, nombre, email, username FROM usuarios WHERE nombre = %s OR email = %s OR username = %s LIMIT 1",
                (identifier, identifier, identifier)
            )
            user = cursor.fetchone()
            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                session['username'] = user[5] or user[3]
                session['user_role'] = user[2]  # Guardar rol (0=usuario, 1=admin)
                cursor.execute("SELECT COALESCE(puntaje, 0) FROM usuarios WHERE id = %s", (user[0],))
                row = cursor.fetchone()
                session['points'] = row[0] if row else 0
                session['show_welcome_guide'] = True
                flash('Has iniciado sesión correctamente', 'success')
                return redirect(url_for('index'))
            else:
                flash('Credenciales inválidas', 'danger')
                return render_template('login.html', identifier=identifier)
        except Exception as e:
            print(f"Error en login: {e}")
            flash('Error en el proceso de inicio de sesión', 'danger')
            return render_template('login.html', identifier=identifier)
    return render_template('login.html')


@app.route('/olvido-contrasena', methods=['GET', 'POST'])
def olvido_contrasena():
    if request.method == 'POST':
        ensure_username_column()
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not email or not new_password or not confirm_password:
            flash('Completa todos los campos para recuperar tu contraseña.', 'danger')
            return redirect(url_for('olvido_contrasena'))
        if new_password != confirm_password:
            flash('Las contraseñas no coinciden.', 'danger')
            return redirect(url_for('olvido_contrasena'))
        if len(new_password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(url_for('olvido_contrasena'))

        cursor.execute("SELECT id FROM usuarios WHERE username = %s AND email = %s LIMIT 1", (username, email))
        user = cursor.fetchone()
        if not user:
            flash('El nombre de usuario y Gmail no coinciden con una cuenta.', 'danger')
            return redirect(url_for('olvido_contrasena'))

        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE usuarios SET password = %s WHERE id = %s", (hashed_password, user[0]))
        db.commit()
        flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('iniciarsesion'))

    return render_template('forgot_password.html')


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('index'))

@app.route('/usuarios')
@admin_required
def usuarios():
    try:
        cursor.execute("SELECT id, nombre, email, city, fecha_creacion, puntaje FROM usuarios")
        usuarios_list = cursor.fetchall()
        ensure_facturas_table()
        cursor.execute("SELECT id, user_id, numero_factura, concepto, monto, metodo_pago, estado, fecha_emision FROM facturas ORDER BY fecha_emision DESC")
        facturas = {}
        for factura in cursor.fetchall():
            facturas.setdefault(factura[1], []).append(factura)
        return render_template('usuarios.html', usuarios=usuarios_list, facturas=facturas)
    except Exception as e:
        print(f"Error al obtener usuarios: {e}")
        return render_template('usuarios.html', usuarios=[], facturas={})

@app.route('/usuarios/<int:id>/editar')
@admin_required
def editar_usuario(id):
    try:
        cursor.execute("SELECT id, nombre, email, city, rol FROM usuarios WHERE id = %s", (id,))
        usuario = cursor.fetchone()

        if not usuario:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('usuarios'))

        return render_template('editar_usuario.html', usuario=usuario)
    except Exception as e:
        print(f"Error al cargar usuario: {e}")
        flash('No se pudo cargar el usuario', 'danger')
        return redirect(url_for('usuarios'))

@app.route('/usuarios/<int:id>/actualizar', methods=['POST'])
@admin_required
def actualizar_usuario(id):
    try:
        nuevo_nombre = request.form.get('nuevo_nombre', '').strip()
        nuevo_email = request.form.get('nuevo_email', '').strip().lower()
        nueva_contraseña = request.form.get('nueva_contraseña', '').strip()
        nuevo_rol = request.form.get('nuevo_rol', '0').strip()

        if not nuevo_nombre or not nuevo_email:
            flash('Nombre y email son obligatorios.', 'danger')
            return redirect(url_for('editar_usuario', id=id))

        cursor.execute("SELECT id, nombre, email, password, city, rol FROM usuarios WHERE id = %s", (id,))
        usuario_actual = cursor.fetchone()

        if not usuario_actual:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('usuarios'))

        # Verificar que el email no esté en uso por otro usuario
        cursor.execute("SELECT id FROM usuarios WHERE email = %s AND id != %s", (nuevo_email, id))
        if cursor.fetchone():
            flash('Ese correo ya está registrado por otro usuario', 'danger')
            return redirect(url_for('editar_usuario', id=id))

        # Si no se escribe una nueva contraseña, se conserva la actual
        if nueva_contraseña:
            hashed_password = generate_password_hash(nueva_contraseña)
        else:
            hashed_password = usuario_actual[3]

        cursor.execute(
            "UPDATE usuarios SET nombre = %s, email = %s, password = %s, rol = %s WHERE id = %s",
            (nuevo_nombre, nuevo_email, hashed_password, nuevo_rol, id)
        )
        db.commit()
        flash('Usuario actualizado correctamente', 'success')
    except Exception as e:
        print(f"Error al actualizar usuario: {e}")
        flash('No se pudo actualizar el usuario', 'danger')

    return redirect(url_for('usuarios'))

@app.route('/usuarios/<int:id>/eliminar', methods=['POST'])
@admin_required
def eliminar_usuario(id):
    try:
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (id,))
        db.commit()
        flash('Usuario eliminado correctamente', 'success')
    except Exception as e:
        print(f"Error al eliminar usuario: {e}")
        flash('No se pudo eliminar el usuario', 'danger')

    return redirect(url_for('usuarios'))

@app.route('/registrar_usuario', methods=['POST'])
def registrar_usuario():
    try:
        ensure_username_column()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        nombre = request.form.get('nombre', '').strip()
        username = request.form.get('username', '').strip().lower()
        city = request.form.get('city', '').strip()

        if not validar_captcha(request.form.get('not_robot')):
            flash('Verificación CAPTCHA incorrecta. Inténtalo de nuevo.', 'danger')
            return redirect(url_for('register'))

        print(f"Datos recibidos: email={email}, nombre={nombre}")

        if not email or not password or not nombre or not username:
            flash('Por favor completa los campos requeridos', 'danger')
            return redirect(url_for('register'))

        cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
        if cursor.fetchone():
            flash('Ese correo ya está registrado', 'danger')
            return redirect(url_for('register'))

        cursor.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
        if cursor.fetchone():
            flash('Ese nombre de usuario ya está ocupado', 'danger')
            return redirect(url_for('register'))

        # Hashear la contraseña y asignar el rol de usuario automáticamente
        hashed_password = generate_password_hash(password)
        sql = "INSERT INTO usuarios (email, password, nombre, username, city, rol, puntaje) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        values = (email, hashed_password, nombre, username, city, 0, 0)
        cursor.execute(sql, values)
        db.commit()

        # Iniciar sesión automáticamente después del registro
        user_id = cursor.lastrowid
        session['user_id'] = user_id
        session['username'] = username
        session['user_role'] = 0
        session['points'] = 0
        session['show_welcome_guide'] = True

        print("✓ Usuario registrado exitosamente")
        flash('¡Registro exitoso! Bienvenido a LA COMA', 'success')
        return redirect(url_for('index'))

    except Exception as e:
        print(f"Error en registro: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error al registrarse: {str(e)}', 'danger')
        return redirect(url_for('register'))

@app.route('/perfil')
@login_required
def perfil():
    try:
        user_id = session.get('user_id')
        ensure_notificaciones_table()
        
        cursor.execute("""
            SELECT u.id, u.username, u.nombre, u.email, u.puntaje,
                   s.es_plus, s.fecha_vencimiento, s.fecha_inicio
            FROM usuarios u
            LEFT JOIN user_suscripcion s ON s.user_id = u.id
            WHERE u.id = %s
        """, (user_id,))
        usuario = cursor.fetchone()
        
        # Verificar membresía activa
        suscripcion = usuario[5:] if usuario else None
        
        membresia_activa = False
        membresia_fecha_vencimiento = None
        dias_para_devolucion = 0
        
        if suscripcion and suscripcion[0]:  # es_plus
            fecha_vencimiento = suscripcion[1]
            if fecha_vencimiento is None or fecha_vencimiento > datetime.now():
                membresia_activa = True
                membresia_fecha_vencimiento = fecha_vencimiento.strftime('%d/%m/%Y') if fecha_vencimiento else 'Permanente'
                
                # Calcular días desde la fecha de inicio
                if suscripcion[2]:
                    fecha_inicio = suscripcion[2]
                    dias_transcurridos = (datetime.now() - fecha_inicio).days
                    dias_para_devolucion = max(0, 15 - dias_transcurridos)
        
        # Obtener recompensas reclamadas por el usuario
        recompensas_reclamadas = []
        cursor.execute("""
            SELECT ur.id, fp.titulo, ur.fecha, ur.numero_amigo, ur.estado, ur.fecha_recibido
            FROM user_recompensa ur 
            JOIN foro_posts fp ON ur.post_id = fp.id 
            WHERE ur.user_id = %s AND ur.usuario_confirmo = FALSE
            ORDER BY ur.fecha DESC
        """, (user_id,))
        recompensas_raw = cursor.fetchall()
        for r in recompensas_raw:
            recompensas_reclamadas.append({
                'id': r[0],
                'titulo': r[1],
                'fecha': r[2],
                'numero_amigo': r[3],
                'estado': r[4],
                'fecha_recibido': r[5]
            })

        cursor.execute('''
            SELECT id, mensaje, administrador, fecha_creacion, leida
            FROM notificaciones
            WHERE user_id = %s
            ORDER BY fecha_creacion DESC
        ''', (user_id,))
        notificaciones = [
            {
                'id': n[0],
                'mensaje': n[1],
                'administrador': n[2],
                'fecha': n[3],
                'leida': n[4]
            }
            for n in cursor.fetchall()
        ]
        
        return render_template('perfil.html', 
                             usuario=usuario,
                             membresia_activa=membresia_activa,
                             membresia_fecha_vencimiento=membresia_fecha_vencimiento,
                             dias_para_devolucion=dias_para_devolucion,
                             recompensas_reclamadas=recompensas_reclamadas,
                             notificaciones=notificaciones,
                             notificaciones_no_leidas=sum(not n['leida'] for n in notificaciones),
                             es_admin=False,
                             es_perfil_propio=True)
    except Exception as e:
        print(f"Error al cargar perfil: {e}")
        flash('Error al cargar el perfil', 'danger')
        return redirect(url_for('index'))


@app.route('/notificaciones/<int:notificacion_id>/leida', methods=['POST'])
@login_required
def eliminar_notificacion(notificacion_id):
    try:
        ensure_notificaciones_table()
        cursor.execute(
            'DELETE FROM notificaciones WHERE id = %s AND user_id = %s',
            (notificacion_id, session.get('user_id'))
        )
        db.commit()
        flash('Notificación marcada como leída.', 'success')
    except Exception as e:
        print(f"Error al eliminar notificación: {e}")
        flash('No se pudo marcar la notificación como leída.', 'danger')
    return redirect(url_for('perfil'))


@app.route('/perfil/<int:user_id>')
def ver_perfil_usuario(user_id):
    try:
        ensure_username_column()
        ensure_user_recompensa_table()
        ensure_user_recompensa_columns()
        
        cursor.execute("SELECT id, username, nombre, email, puntaje FROM usuarios WHERE id = %s", (user_id,))
        usuario = cursor.fetchone()
        
        if not usuario:
            flash('Usuario no encontrado', 'danger')
            return redirect(url_for('usuarios'))
        
        # Obtener recompensas reclamadas por el usuario
        recompensas_reclamadas = []
        cursor.execute("""
            SELECT ur.id, fp.titulo, ur.fecha, ur.comentario, ur.numero_amigo, ur.estado, ur.fecha_recibido
            FROM user_recompensa ur 
            JOIN foro_posts fp ON ur.post_id = fp.id 
            WHERE ur.user_id = %s 
            ORDER BY ur.fecha DESC
        """, (user_id,))
        recompensas_raw = cursor.fetchall()
        for r in recompensas_raw:
            recompensas_reclamadas.append({
                'id': r[0],
                'titulo': r[1],
                'fecha': r[2],
                'comentario': r[3],
                'numero_amigo': r[4],
                'estado': r[5],
                'fecha_recibido': r[6]
            })
        
        return render_template('perfil.html', 
                             usuario=usuario,
                             membresia_activa=False,
                             membresia_fecha_vencimiento=None,
                             dias_para_devolucion=0,
                             recompensas_reclamadas=recompensas_reclamadas,
                             es_admin=is_admin_user(),
                             es_perfil_propio=False)
    except Exception as e:
        print(f"Error al cargar perfil de usuario: {e}")
        flash('Error al cargar el perfil', 'danger')
        return redirect(url_for('usuarios'))


@app.route('/recompensa_solicitada/<int:recompensa_id>/editar', methods=['GET', 'POST'])
@admin_required
def editar_recompensa_solicitada(recompensa_id):
    ensure_user_recompensa_table()
    ensure_user_recompensa_columns()

    if request.method == 'POST':
        comentario = request.form.get('comentario', '').strip()
        numero_amigo = request.form.get('numero_amigo', '').strip()
        estado = request.form.get('estado', 'pendiente').strip().lower()
        if estado not in {'pendiente', 'recibida'}:
            estado = 'pendiente'

        cursor.execute(
            "UPDATE user_recompensa SET comentario = %s, numero_amigo = %s, estado = %s, fecha_recibido = %s WHERE id = %s",
            (comentario or None, numero_amigo or None, estado,
             datetime.now() if estado == 'recibida' else None, recompensa_id)
        )
        db.commit()
        flash('Solicitud de recompensa actualizada.', 'success')
        return redirect(url_for('usuarios'))

    cursor.execute("""
        SELECT ur.id, ur.user_id, fp.titulo, ur.comentario, ur.numero_amigo, ur.estado
        FROM user_recompensa ur
        JOIN foro_posts fp ON fp.id = ur.post_id
        WHERE ur.id = %s
    """, (recompensa_id,))
    recompensa = cursor.fetchone()
    if not recompensa:
        flash('Solicitud de recompensa no encontrada.', 'danger')
        return redirect(url_for('usuarios'))
    return render_template('editar_recompensa_solicitada.html', recompensa=recompensa)


@app.route('/recompensa_solicitada/<int:recompensa_id>/eliminar', methods=['POST'])
@admin_required
def eliminar_recompensa_solicitada(recompensa_id):
    try:
        ensure_user_recompensa_table()
        cursor.execute("DELETE FROM user_recompensa WHERE id = %s", (recompensa_id,))
        db.commit()
        flash('Solicitud de recompensa eliminada.', 'success')
    except Exception as e:
        print(f"Error eliminando solicitud de recompensa: {e}")
        flash('No se pudo eliminar la solicitud.', 'danger')
    return redirect(url_for('usuarios'))


@app.route('/recompensa_solicitada/<int:recompensa_id>/recibida', methods=['POST'])
@admin_required
def marcar_recompensa_recibida(recompensa_id):
    try:
        ensure_user_recompensa_table()
        ensure_user_recompensa_columns()
        cursor.execute(
            "UPDATE user_recompensa SET estado = 'recibida', fecha_recibido = %s WHERE id = %s",
            (datetime.now(), recompensa_id)
        )
        db.commit()
        flash('Recompensa marcada como recibida.', 'success')
    except Exception as e:
        print(f"Error marcando recompensa como recibida: {e}")
        flash('No se pudo actualizar el estado de la recompensa.', 'danger')
    return redirect(url_for('usuarios'))


@app.route('/recompensa_solicitada/<int:recompensa_id>/confirmar', methods=['POST'])
@login_required
def confirmar_recompensa_recibida(recompensa_id):
    try:
        user_id = session.get('user_id')
        cursor.execute(
            "UPDATE user_recompensa SET usuario_confirmo = TRUE, fecha_confirmacion = %s WHERE id = %s AND user_id = %s AND estado = 'recibida'",
            (datetime.now(), recompensa_id, user_id)
        )
        db.commit()
        flash('Has confirmado la recepción de tu recompensa.', 'success')
    except Exception as e:
        print(f"Error confirmando recepción de recompensa: {e}")
        flash('No se pudo confirmar la recepción.', 'danger')
    return redirect(url_for('perfil'))


@app.route('/cambiar_contrasena', methods=['POST'])
@login_required
def cambiar_contrasena():
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        user_id = session.get('user_id')
        
        # Validaciones
        if not current_password or not new_password or not confirm_password:
            flash('Por favor completa todos los campos', 'danger')
            return redirect(url_for('perfil'))
        
        if new_password != confirm_password:
            flash('Las nuevas contraseñas no coinciden', 'danger')
            return redirect(url_for('perfil'))
        
        if len(new_password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('perfil'))
        
        # Verificar contraseña actual
        cursor.execute("SELECT password FROM usuarios WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        
        if not result or not check_password_hash(result[0], current_password):
            flash('La contraseña actual es incorrecta', 'danger')
            return redirect(url_for('perfil'))
        
        # Actualizar contraseña
        new_password_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE usuarios SET password = %s WHERE id = %s", (new_password_hash, user_id))
        db.commit()
        
        flash('¡Contraseña actualizada correctamente!', 'success')
        return redirect(url_for('perfil'))
        
    except Exception as e:
        print(f"Error al cambiar contraseña: {e}")
        flash('Error al cambiar la contraseña', 'danger')
        return redirect(url_for('perfil'))


@app.route('/solicitar_devolucion_membresia', methods=['POST'])
@login_required
def solicitar_devolucion_membresia():
    try:
        ensure_membership_refunds_table()
        user_id = session.get('user_id')
        
        # Verificar si el usuario tiene membresía activa
        cursor.execute("SELECT es_plus, fecha_inicio FROM user_suscripcion WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            flash('No tienes una membresía activa', 'danger')
            return redirect(url_for('perfil'))
        
        # Verificar si está dentro del período de 15 días
        fecha_inicio = result[1]
        dias_transcurridos = (datetime.now() - fecha_inicio).days
        
        if dias_transcurridos > 15:
            flash('El período de 15 días para solicitar devolución ha vencido', 'danger')
            return redirect(url_for('perfil'))
        
        # Verificar si ya existe una solicitud de devolución pendiente
        cursor.execute("SELECT id FROM membership_refunds WHERE user_id = %s AND estado = 'pendiente'", (user_id,))
        if cursor.fetchone():
            flash('Ya tienes una solicitud de devolución pendiente', 'warning')
            return redirect(url_for('perfil'))
        
        # Crear la solicitud de devolución
        monto = 5000  # Precio de la membresía
        cursor.execute(
            "INSERT INTO membership_refunds (user_id, monto, estado) VALUES (%s, %s, 'pendiente')",
            (user_id, monto)
        )
        db.commit()
        
        flash('¡Solicitud de devolución registrada! Se procesará en 3-5 días hábiles', 'success')
        return redirect(url_for('perfil'))
        
    except Exception as e:
        print(f"Error al solicitar devolución: {e}")
        flash('Error al solicitar la devolución', 'danger')
        return redirect(url_for('perfil'))


@app.route('/recompensas')
@login_required
def recompensas():
    try:
        ensure_user_recompensa_table()
        ensure_foro_posts_cartas_column()
        ensure_foro_posts_requisitos_column()
        ensure_foro_posts_destacada_column()
        user_id = session.get('user_id')
        is_admin = session.get('user_role') == 1 or (session.get('username') or '').lower() in {'abril', 'admin', 'administrador'}

        recompensa_posts = []
        cursor.execute("SELECT id, titulo, contenido, usuario, fecha_creacion, COALESCE(tipo_cliente, 'ambos'), COALESCE(precio_cartas, 0), requisitos_cartas, COALESCE(destacada, FALSE) FROM foro_posts WHERE slug = 'recompensa_semanal' ORDER BY destacada DESC, fecha_creacion DESC")
        raw_posts = cursor.fetchall()
        for p in raw_posts:
            post_id = p[0]
            cursor.execute("SELECT COUNT(*) FROM user_recompensa WHERE user_id = %s AND post_id = %s", (user_id, post_id))
            claimed = cursor.fetchone()[0] > 0
            requirements = json.loads(p[7]) if p[7] else {}
            recompensa_posts.append({
                'id': post_id,
                'titulo': p[1],
                'contenido': p[2],
                'usuario': p[3],
                'fecha_creacion': p[4],
                'tipo_cliente': p[5],
                'precio_cartas': p[6],
                'requisitos_cartas': format_card_requirements(requirements),
                'requisitos_lista': [
                    {'juego': game_name.title(), 'cantidad': quantity}
                    for game_name, quantity in requirements.items()
                ],
                'destacada': bool(p[8]),
                'claimed': claimed
            })

        return render_template(
            'recompensas.html',
            recompensa_posts=recompensa_posts,
            is_admin=is_admin,
            card_game_names=[game_name for game_name, _ in CARD_REQUIREMENT_GROUPS],
        )
    except Exception as e:
        print(f"Error al cargar recompensas: {e}")
        flash('No se pudo abrir la página de recompensas', 'danger')
        return redirect(url_for('cartas'))


@app.route('/cartas')
@login_required
def cartas():
    try:
        ensure_user_cartas_table()
        ensure_foro_posts_cartas_column()
        ensure_foro_posts_requisitos_column()
        ensure_foro_posts_destacada_column()
        user_id = session.get('user_id')
        cursor.execute("SELECT carta FROM user_cartas WHERE user_id = %s ORDER BY fecha_desbloqueo, carta", (user_id,))
        owned_rows = cursor.fetchall()
        owned_cards = [row[0] for row in owned_rows]
        owned_cards_by_name = {}
        for carta in owned_cards:
            owned_cards_by_name.setdefault(carta, []).append(url_for('static', filename=carta))

        album_pages = []
        for game_name, game_cards in CARD_GAME_GROUPS:
            page_cards = []
            for carta in game_cards:
                page_cards.extend(owned_cards_by_name.get(carta, []))
            album_pages.append({
                'name': game_name,
                'cards': page_cards,
                'slots': page_cards[:15] + [None] * (15 - min(len(page_cards), 15)),
                'is_plus': False,
            })

        plus_cards = []
        for carta in PLUS_CARD_IMAGES:
            plus_cards.extend(owned_cards_by_name.get(carta, []))
        album_pages.append({
            'name': 'Cartas Plus',
            'cards': plus_cards,
            'slots': plus_cards[:15] + [None] * (15 - min(len(plus_cards), 15)),
            'is_plus': True,
        })

        missing_initial = [c for c in INITIAL_CARD_IMAGES if c not in owned_cards]
        cursor.execute("SELECT id, titulo, COALESCE(precio_cartas, 0), COALESCE(requisitos_cartas, '{}'), COALESCE(destacada, 0) FROM foro_posts WHERE slug = 'recompensa_semanal' ORDER BY COALESCE(destacada, 0) DESC, fecha_creacion DESC")
        featured_rewards = []
        for reward_id, title, total_cards, requirements_json, is_featured in cursor.fetchall():
            if not is_featured:
                continue
            requirements = json.loads(requirements_json) if requirements_json else {}
            featured_rewards.append({
                'id': reward_id,
                'titulo': title,
                'total_cartas': sum(requirements.values()) if requirements else total_cards,
            })
        return render_template(
            'cartas.html',
            album_pages=album_pages,
            featured_rewards=featured_rewards,
            missing_initial=bool(missing_initial),
            card_packs=CARD_PACKS,
            is_plus=check_user_plus(user_id),
        )
    except Exception as e:
        print(f"Error al cargar cartas: {e}")
        flash('No se pudo abrir la colección de cartas', 'danger')
        return redirect(url_for('perfil'))


@app.route('/recompensa_semanal/post', methods=['POST'])
@admin_required
def crear_recompensa_post():
    titulo = request.form.get('titulo', '').strip()
    contenido = request.form.get('contenido', '').strip()
    tipo_cliente = request.form.get('tipo_cliente', 'ambos').strip().lower()
    precio_cartas_str = request.form.get('precio_cartas', '').strip()
    requisitos_cartas = parse_card_requirements(request.form.get('requisitos_cartas', ''))
    destacada = request.form.get('destacada', '').lower() in {'on', '1', 'true', 'si'}
    usuario = session.get('username', 'Admin')
    
    if tipo_cliente not in ['premium', 'normal', 'ambos']:
        tipo_cliente = 'ambos'
    
    # Validar precio_cartas (obligatorio, 1-500)
    if not precio_cartas_str:
        flash('El precio en cartas es obligatorio.', 'danger')
        return redirect(url_for('recompensas'))
    
    try:
        precio_cartas = int(precio_cartas_str)
        if precio_cartas < 1 or precio_cartas > 500:
            flash('El precio en cartas debe estar entre 1 y 500.', 'danger')
            return redirect(url_for('recompensas'))
    except ValueError:
        flash('El precio en cartas debe ser un número válido.', 'danger')
        return redirect(url_for('recompensas'))

    if requisitos_cartas and sum(requisitos_cartas.values()) != precio_cartas:
        flash('La suma de las cartas por juego debe coincidir con el precio total.', 'danger')
        return redirect(url_for('recompensas'))
    
    if not titulo or not contenido:
        flash('Debe completar título y contenido.', 'danger')
        return redirect(url_for('recompensas'))
    try:
        ensure_foro_posts_cartas_column()
        ensure_foro_posts_requisitos_column()
        ensure_foro_posts_destacada_column()
        # usar juego_id = 0 para posts globales de recompensa semanal
        cursor.execute("INSERT INTO foro_posts (juego_id, slug, titulo, contenido, usuario, tipo_cliente, precio_cartas, requisitos_cartas, destacada) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (0, 'recompensa_semanal', titulo, contenido, usuario, tipo_cliente, precio_cartas, json.dumps(requisitos_cartas), destacada))
        db.commit()
        flash('Comentario de recompensa semanal publicado.', 'success')
    except Exception as e:
        print(f"Error creando recompensa_post: {e}")
        flash(f'Error al publicar comentario: {e}', 'danger')
    return redirect(url_for('recompensas'))


@app.route('/recompensa_semanal/<int:post_id>/editar', methods=['GET', 'POST'])
@admin_required
def editar_recompensa_post(post_id):
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        contenido = request.form.get('contenido', '').strip()
        precio_cartas_str = request.form.get('precio_cartas', '').strip()
        requisitos_cartas = parse_card_requirements(request.form.get('requisitos_cartas', ''))
        destacada = request.form.get('destacada', '').lower() in {'on', '1', 'true', 'si'}
        
        # Validar precio_cartas (obligatorio, 1-500)
        if not precio_cartas_str:
            flash('El precio en cartas es obligatorio.', 'danger')
            return redirect(url_for('recompensas'))
        
        try:
            precio_cartas = int(precio_cartas_str)
            if precio_cartas < 1 or precio_cartas > 500:
                flash('El precio en cartas debe estar entre 1 y 500.', 'danger')
                return redirect(url_for('recompensas'))
        except ValueError:
            flash('El precio en cartas debe ser un número válido.', 'danger')
            return redirect(url_for('recompensas'))

        if requisitos_cartas and sum(requisitos_cartas.values()) != precio_cartas:
            flash('La suma de las cartas por juego debe coincidir con el precio total.', 'danger')
            return redirect(url_for('recompensas'))
        
        if not titulo or not contenido:
            flash('Debe completar título y contenido.', 'danger')
            return redirect(url_for('recompensas'))
        try:
            ensure_foro_posts_cartas_column()
            ensure_foro_posts_requisitos_column()
            ensure_foro_posts_destacada_column()
            cursor.execute("UPDATE foro_posts SET titulo = %s, contenido = %s, precio_cartas = %s, requisitos_cartas = %s, destacada = %s WHERE id = %s AND slug = 'recompensa_semanal'", (titulo, contenido, precio_cartas, json.dumps(requisitos_cartas), destacada, post_id))
            db.commit()
            flash('Comentario actualizado.', 'success')
        except Exception as e:
            print(f"Error editando recompensa_post: {e}")
            flash('Error al actualizar comentario', 'danger')
        return redirect(url_for('recompensas'))

    # GET: mostrar formulario de edición
    ensure_foro_posts_cartas_column()
    ensure_foro_posts_requisitos_column()
    ensure_foro_posts_destacada_column()
    cursor.execute("SELECT id, titulo, contenido, precio_cartas, requisitos_cartas, destacada FROM foro_posts WHERE id = %s AND slug = 'recompensa_semanal'", (post_id,))
    post = cursor.fetchone()
    if not post:
        flash('Comentario no encontrado', 'danger')
        return redirect(url_for('recompensas'))
    requirements = json.loads(post[4]) if post[4] else {}
    post = (*post[:4], format_card_requirements(requirements), bool(post[5]))
    return render_template(
        'editar_recompensa.html',
        post=post,
            card_game_names=[game_name for game_name, _ in CARD_REQUIREMENT_GROUPS],
        card_requirements=requirements,
    )


@app.route('/recompensa_semanal/<int:post_id>/eliminar', methods=['POST'])
@admin_required
def eliminar_recompensa_post(post_id):
    try:
        ensure_user_recompensa_table()
        cursor.execute("DELETE FROM user_recompensa WHERE post_id = %s", (post_id,))
        cursor.execute("DELETE FROM foro_posts WHERE id = %s AND slug = 'recompensa_semanal'", (post_id,))
        db.commit()
        flash('Comentario eliminado.', 'success')
    except Exception as e:
        print(f"Error eliminando recompensa_post: {e}")
        flash('Error al eliminar comentario', 'danger')
    return redirect(url_for('recompensas'))


@app.route('/recompensa_semanal/<int:post_id>/obtener', methods=['POST'])
@login_required
def obtener_recompensa(post_id):
    try:
        ensure_user_recompensa_table()
        ensure_user_recompensa_columns()
        ensure_foro_posts_cartas_column()
        user_id = session.get('user_id')
        username_input = (request.form.get('username') or '').strip()
        username_sesion = (session.get('username') or '').strip()
        comentario = (request.form.get('comentario') or '').strip()
        numero_amigo = (request.form.get('numero_amigo') or '').strip()
        
        # Validar que el número de amigo sea proporcionado
        if not numero_amigo:
            flash('El número de amigo es obligatorio.', 'danger')
            return redirect(url_for('recompensas'))
        
        # Validar que el nombre de usuario coincida
        if username_input.lower() != username_sesion.lower():
            flash('Nombre de usuario incorrecto. Inténtalo de nuevo.', 'danger')
            return redirect(url_for('recompensas'))
        
        # comprobar si ya reclamado
        cursor.execute("SELECT COUNT(*) FROM user_recompensa WHERE user_id = %s AND post_id = %s", (user_id, post_id))
        if cursor.fetchone()[0] > 0:
            flash('Ya reclamaste esta recompensa.', 'info')
            return redirect(url_for('recompensas'))
        
        # Obtener el precio_cartas de la recompensa
        ensure_foro_posts_requisitos_column()
        cursor.execute("SELECT COALESCE(precio_cartas, 0), requisitos_cartas FROM foro_posts WHERE id = %s AND slug = 'recompensa_semanal'", (post_id,))
        result = cursor.fetchone()
        precio_cartas = result[0] if result else 0
        requisitos_cartas = json.loads(result[1]) if result and result[1] else {}
        
        # Si hay precio en cartas, verificar que el usuario tenga suficientes
        if requisitos_cartas:
            faltantes = []
            for game_key, quantity in requisitos_cartas.items():
                game_images = CARD_GAME_IMAGES.get(game_key, [])
                placeholders = ', '.join(['%s'] * len(game_images))
                cursor.execute(
                    f"SELECT COUNT(*) FROM user_cartas WHERE user_id = %s AND carta IN ({placeholders})",
                    (user_id, *game_images)
                )
                available = cursor.fetchone()[0]
                if available < quantity:
                    faltantes.append(f'{game_key.title()}: necesitas {quantity}, tienes {available}')

            if faltantes:
                flash('No tienes las cartas necesarias: ' + ' | '.join(faltantes), 'danger')
                return redirect(url_for('recompensas'))

            for game_key, quantity in requisitos_cartas.items():
                game_images = CARD_GAME_IMAGES[game_key]
                placeholders = ', '.join(['%s'] * len(game_images))
                cursor.execute(
                    f"DELETE FROM user_cartas WHERE user_id = %s AND carta IN ({placeholders}) ORDER BY fecha_desbloqueo ASC LIMIT %s",
                    (user_id, *game_images, quantity)
                )
        elif precio_cartas > 0:
            cursor.execute("SELECT COUNT(*) FROM user_cartas WHERE user_id = %s", (user_id,))
            cartas_usuario = cursor.fetchone()[0]

            if cartas_usuario < precio_cartas:
                flash(f'No tienes suficientes cartas. Necesitas {precio_cartas} cartas y tienes {cartas_usuario}.', 'danger')
                return redirect(url_for('recompensas'))

            cursor.execute("DELETE FROM user_cartas WHERE user_id = %s ORDER BY fecha_desbloqueo ASC LIMIT %s", (user_id, precio_cartas))
        if requisitos_cartas or precio_cartas > 0:
            db.commit()

        # insertar marca de reclamación con comentario y número de amigo, y dar puntos
        cursor.execute("INSERT INTO user_recompensa (user_id, post_id, comentario, numero_amigo) VALUES (%s, %s, %s, %s)", (user_id, post_id, comentario if comentario else None, numero_amigo if numero_amigo else None))
        points_added = add_points(user_id, REWARD_POINTS)
        cursor.execute("SELECT COALESCE(puntaje,0) FROM usuarios WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        session['points'] = row[0] if row else session.get('points', 0)
        
        if requisitos_cartas:
            flash(f'Has obtenido la recompensa ({points_added} puntos). Se descontaron las cartas específicas solicitadas.', 'success')
        elif precio_cartas > 0:
            flash(f'Has obtenido la recompensa ({points_added} puntos). Se descontaron {precio_cartas} cartas.', 'success')
        else:
            flash(f'Has obtenido la recompensa ({points_added} puntos).', 'success')
    except Exception as e:
        print(f"Error al obtener recompensa: {e}")
        flash('Error al intentar reclamar la recompensa.', 'danger')
    return redirect(url_for('recompensas'))


@app.route('/minijuego_buscaminas/resultado', methods=['POST'])
@login_required
def minijuego_buscaminas_resultado():
    user_id = session.get('user_id')
    if not check_user_plus(user_id):
        return jsonify({'error': 'La membresía Plus es requerida para jugar el buscaminas.'}), 403

    data = request.get_json(silent=True) or {}
    difficulty = (data.get('difficulty') or '').strip().lower()
    points_by_difficulty = {
        'facil': 10,
        'medio': 50,
        'dificil': 100,
        'extremo': 300,
    }
    points_awarded = points_by_difficulty.get(difficulty, 0)

    if points_awarded <= 0:
        return jsonify({'error': 'Dificultad no válida'}), 400

    try:
        ensure_user_points_column()
        points_added = add_points(user_id, points_awarded)
        cursor.execute("SELECT COALESCE(puntaje, 0) FROM usuarios WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        total_points = row[0] if row else session.get('points', 0)
        session['points'] = total_points
        return jsonify({
            'success': True,
            'points_awarded': points_awarded,
            'total_points': total_points,
            'message': f'¡GANASTE! Recibiste {points_awarded} puntos.'
        })
    except Exception as e:
        print(f"Error al guardar resultado del buscaminas: {e}")
        return jsonify({'error': 'No se pudo guardar el resultado'}), 500


@app.route('/desbloquear_cartas', methods=['POST'])
@login_required
def desbloquear_cartas():
    try:
        ensure_user_cartas_table()
        user_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        pack_key = (data.get('pack') or 'basica').strip().lower()
        pack = CARD_PACKS.get(pack_key)
        if not pack:
            return jsonify({'message': 'La recompensa seleccionada no es válida.'}), 400

        if pack['plus_only'] and not check_user_plus(user_id):
            return jsonify({'message': 'La recompensa plus es exclusiva para miembros.'}), 403

        cursor.execute("SELECT carta FROM user_cartas WHERE user_id = %s", (user_id,))
        owned_rows = cursor.fetchall()
        owned_cards = {row[0] for row in owned_rows}

        missing_initial = [c for c in INITIAL_CARD_IMAGES if c not in owned_cards]
        if missing_initial:
            for carta in missing_initial:
                try:
                    cursor.execute("INSERT IGNORE INTO user_cartas (user_id, carta) VALUES (%s, %s)", (user_id, carta))
                except Exception:
                    pass
            db.commit()
            cursor.execute("SELECT carta FROM user_cartas WHERE user_id = %s ORDER BY fecha_desbloqueo, carta", (user_id,))
            owned_rows = cursor.fetchall()
            cards = [url_for('static', filename=row[0]) for row in owned_rows]
            return jsonify({
                'cards': cards,
                'new_cards': [url_for('static', filename=carta) for carta in missing_initial],
                'message': 'Has recibido tus primeras 2 cartas gratis.',
                'initial_grant': True,
                'points': session.get('points', 0)
            })

        cursor.execute("SELECT COALESCE(puntaje, 0) FROM usuarios WHERE id = %s", (user_id,))
        points_row = cursor.fetchone()
        current_points = points_row[0] if points_row else session.get('points', 0)
        price = pack['price']
        if current_points < price:
            cards = [url_for('static', filename=carta) for carta in owned_cards]
            return jsonify({
                'cards': cards,
                'message': f'No tienes suficientes puntos para reclamar la {pack["name"].lower()}.',
                'points': current_points
            }), 402

        selected_cards = select_pack_cards(pack_key, pack['cards'])
        cursor.execute(
            "UPDATE usuarios SET puntaje = puntaje - %s WHERE id = %s AND puntaje >= %s",
            (price, user_id, price)
        )
        if cursor.rowcount != 1:
            db.rollback()
            return jsonify({'message': 'Tus puntos cambiaron. Actualiza la página e inténtalo de nuevo.'}), 409

        for carta in selected_cards:
            cursor.execute("INSERT INTO user_cartas (user_id, carta) VALUES (%s, %s)", (user_id, carta))
        db.commit()
        cursor.execute("SELECT puntaje FROM usuarios WHERE id = %s", (user_id,))
        updated_points = cursor.fetchone()[0] or 0
        session['points'] = updated_points
        cursor.execute("SELECT carta FROM user_cartas WHERE user_id = %s ORDER BY fecha_desbloqueo, carta", (user_id,))
        owned_rows = cursor.fetchall()
        cards = [url_for('static', filename=row[0]) for row in owned_rows]
        return jsonify({
            'cards': cards,
            'new_cards': [url_for('static', filename=carta) for carta in selected_cards],
            'message': f'Reclamaste la {pack["name"].lower()} por {price} puntos y obtuviste {len(selected_cards)} cartas.',
            'points': updated_points
        })
    except Exception as e:
        print(f"Error en desbloquear_cartas: {e}")
        return jsonify({'cards': [], 'message': 'Error al intentar obtener cartas.', 'button_text': 'Intentar de nuevo', 'disabled': False}), 500

@app.route('/contacto', methods=['GET', 'POST'])
@app.route('/resenas', methods=['GET', 'POST'])
def resenas():
    if request.method == 'POST':
        asunto = request.form.get('asunto', '').strip()
        mensaje = request.form.get('mensaje', '').strip()
        user_id = session.get('user_id')
        nombre = session.get('username') or 'Visitante'
        email = None

        if user_id:
            try:
                cursor.execute('SELECT email FROM usuarios WHERE id = %s', (user_id,))
                row = cursor.fetchone()
                if row:
                    email = row[0]
            except Exception:
                email = None
        else:
            email = request.form.get('email', '').strip().lower()

        if not asunto or not mensaje:
            flash('Debes escribir un asunto y un mensaje para enviar tu reporte.', 'danger')
            return redirect(url_for('resenas'))

        if not user_id and not email:
            flash('Por favor ingresa tu correo para poder contactarte.', 'danger')
            return redirect(url_for('resenas'))

        try:
            ensure_reportes_table()
            cursor.execute(
                'INSERT INTO reportes (user_id, nombre, email, asunto, mensaje) VALUES (%s, %s, %s, %s, %s)',
                (user_id, nombre, email, asunto, mensaje)
            )
            db.commit()
            flash('Tu reporte se envió correctamente. Los administradores lo recibirán pronto.', 'success')
        except Exception as e:
            print(f"Error al guardar reporte: {e}")
            flash('Ocurrió un error al enviar tu reporte. Intenta de nuevo más tarde.', 'danger')
        return redirect(url_for('resenas'))

    return render_template('contactenos.html')

@app.route('/admin/reportes')
@admin_required
def admin_reportes():
    try:
        ensure_reportes_table()
        cursor.execute('SELECT id, user_id, nombre, email, asunto, mensaje, fecha_creacion FROM reportes ORDER BY fecha_creacion DESC')
        reportes = cursor.fetchall()
    except Exception as e:
        print(f"Error al cargar reportes: {e}")
        reportes = []
    return render_template('reportes.html', reportes=reportes)


@app.route('/admin/reportes/<int:reporte_id>/responder', methods=['POST'])
@admin_required
def responder_reporte(reporte_id):
    respuesta = request.form.get('respuesta', '').strip()

    if not respuesta:
        flash('Escribe una respuesta antes de enviarla.', 'danger')
        return redirect(url_for('admin_reportes'))

    try:
        ensure_reportes_table()
        ensure_notificaciones_table()
        cursor.execute('SELECT user_id FROM reportes WHERE id = %s', (reporte_id,))
        reporte = cursor.fetchone()

        if not reporte or not reporte[0]:
            flash('Este reporte no está asociado a un usuario registrado.', 'warning')
            return redirect(url_for('admin_reportes'))

        administrador = session.get('username') or 'Administrador'
        cursor.execute(
            'DELETE FROM notificaciones WHERE user_id = %s',
            (reporte[0],)
        )
        cursor.execute(
            '''INSERT INTO notificaciones
               (user_id, reporte_id, mensaje, administrador)
               VALUES (%s, %s, %s, %s)''',
            (reporte[0], reporte_id, respuesta, administrador)
        )
        cursor.execute('DELETE FROM reportes WHERE id = %s', (reporte_id,))
        db.commit()
        flash('Respuesta enviada y reporte retirado de la bandeja.', 'success')
    except Exception as e:
        print(f"Error al responder reporte: {e}")
        flash('No se pudo enviar la respuesta.', 'danger')

    return redirect(url_for('admin_reportes'))

# ========== RUTAS DE DEBUG (SOLO ADMIN) ==========

@app.route('/debug/usuarios')
@admin_required
def debug_usuarios():
    """Ver todos los usuarios y probar login"""
    try:
        cursor.execute("SELECT id, nombre, email, password, rol FROM usuarios")
        usuarios_list = cursor.fetchall()
        
        # Información de debug
        debug_info = {
            'usuarios': usuarios_list,
            'total': len(usuarios_list) if usuarios_list else 0
        }
        
        # Probar contraseña del primer usuario (Abril)
        test_user = None
        cursor.execute(
            "SELECT id, password, rol, nombre, email FROM usuarios WHERE nombre LIKE 'abril' OR email = %s",
            ('abrileo0765@gmail.com',)
        )
        test_user = cursor.fetchone()
        
        debug_info['test_user'] = test_user
        if test_user:
            debug_info['password_test'] = check_password_hash(test_user[1], '159842673')
        
        print("\n=== DEBUG: USUARIOS EN BD ===")
        for user in usuarios_list:
            print(f"ID: {user[0]} | Nombre: {user[1]} | Email: {user[2]} | Rol: {user[4]}")
        
        return f"""
        <h1>DEBUG - USUARIOS EN BD</h1>
        <p>Total usuarios: {debug_info['total']}</p>
        <h2>Lista de usuarios:</h2>
        <pre>
        {str(debug_info['usuarios'])}
        </pre>
        <h2>Test de login (Abril):</h2>
        <pre>si
        Usuario encontrado: {debug_info['test_user'] is not None}
        Contraseña correcta: {debug_info.get('password_test', False)}
        </pre>
        <a href="/">Volver</a>
        """
    except Exception as e:
        return f"<h1>Error: {e}</h1><a href='/'>Volver</a>"




@app.route('/admin/reset-password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    """Resetear contraseña a una contraseña por defecto"""
    try:
        nueva_password = request.form.get('password', '159842673')
        hashed_password = generate_password_hash(nueva_password)
        
        cursor.execute(
            "UPDATE usuarios SET password = %s WHERE id = %s",
            (hashed_password, user_id)
        )
        db.commit()
        
        flash(f'Contraseña del usuario reseteada a: {nueva_password}', 'success')
        print(f"✓ Contraseña reseteada para usuario ID {user_id}")
    except Exception as e:
        print(f"Error al resetear contraseña: {e}")
        flash('Error al resetear contraseña', 'danger')
    
    return redirect(url_for('usuarios'))



initialize_sqlite_database()

if __name__ == '__main__':
    # Asegurar tablas críticas al arrancar la aplicación
    try:
        ensure_game_catalog()
        ensure_forum_posts_table()
        ensure_user_cartas_table()
        ensure_user_recompensa_table()
        ensure_user_recompensa_columns()
        ensure_user_recompensa_index()
        ensure_reportes_table()
        ensure_user_points_column()
    except Exception as e:
        print(f"Error al asegurar tablas al inicio: {e}")

    app.run(debug=True, host='0.0.0.0', port=500)
