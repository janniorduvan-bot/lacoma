-- ============================================================
-- BASE DE DATOS: registro
-- Archivo SQL para importar en phpMyAdmin
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 1. CREAR BASE DE DATOS
-- ============================================================

DROP DATABASE IF EXISTS ELPUNTO;
CREATE DATABASE ELPUNTO
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE ELPUNTO;

-- ============================================================
-- 2. CREAR USUARIO Y ASIGNAR PRIVILEGIOS
-- ============================================================

DROP USER IF EXISTS 'rooty'@'localhost';

CREATE USER 'rooty'@'localhost'
    IDENTIFIED BY '123456';

GRANT ALL PRIVILEGES ON ELPUNTO.* TO 'rooty'@'localhost';

FLUSH PRIVILEGES;




CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    city VARCHAR(100),
    rol TINYINT NOT NULL DEFAULT 0,  -- 0 = usuario, 1 = administrador
    puntaje INT NOT NULL DEFAULT 0,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facturas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    numero_factura VARCHAR(100) NOT NULL UNIQUE,
    concepto VARCHAR(150) NOT NULL,
    monto DECIMAL(10, 2) NOT NULL,
    metodo_pago VARCHAR(50) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pagada',
    fecha_emision TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS notificaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    reporte_id INT NULL,
    mensaje TEXT NOT NULL,
    administrador VARCHAR(100) NOT NULL DEFAULT 'Administrador',
    leida BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usuario Administrador
CREATE TABLE IF NOT EXISTS juego_catalogo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255) NOT NULL,
    imagen VARCHAR(255) NOT NULL,
    foro_tabla VARCHAR(100) NOT NULL UNIQUE,
    plataforma VARCHAR(20) NOT NULL DEFAULT 'pc',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS foro_posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    juego_id INT NOT NULL,
    slug VARCHAR(100) NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    contenido TEXT NOT NULL,
    usuario VARCHAR(100) NOT NULL DEFAULT 'Usuario',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    likes INT NOT NULL DEFAULT 0,
    destacada BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS user_recompensa (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    post_id INT NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    comentario TEXT,
    numero_amigo VARCHAR(50),
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    fecha_recibido TIMESTAMP NULL,
    usuario_confirmo BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_confirmacion TIMESTAMP NULL,
    UNIQUE KEY unique_user_post (user_id, post_id),
    KEY idx_user_recompensa_perfil (user_id, usuario_confirmo, fecha),
    FOREIGN KEY (user_id) REFERENCES usuarios(id),
    FOREIGN KEY (post_id) REFERENCES foro_posts(id)
);

ALTER TABLE juego_catalogo ADD COLUMN IF NOT EXISTS trailer_url VARCHAR(500) NULL;
ALTER TABLE juego_catalogo ADD COLUMN IF NOT EXISTS genero VARCHAR(30) NULL;

INSERT IGNORE INTO juego_catalogo (slug, nombre, descripcion, imagen, foro_tabla, plataforma, trailer_url) VALUES
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
('minecraft-bedrock', 'MINECRAFT BEDROCK', 'Construye mundos, sobrevive y comparte aventuras en tu dispositivo móvil.', 'IMG/MINECRAFT BEDROCK.jfif', 'foros_minecraft_bedrock', 'movil');

INSERT IGNORE INTO usuarios (nombre, email, password, city, rol) VALUES
('Abril', 'abrileo0765@gmail.com', 'scrypt:32768:8:1$Dtn3yj86RCCtWFPO$cc0d0462f1d2382e811a39473accc5c5eef6b40e39f811d33e8d9a5131b6dad997f06ef642a336957c77a483e40bdc2e252b6ac2faa8c02633cb628476a45bb8', 'bogota', 1);