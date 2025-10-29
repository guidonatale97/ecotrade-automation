-- ========================================
-- SCHEMA DATABASE ECOTRADE AUTOMATION
-- ========================================

CREATE DATABASE IF NOT EXISTS automation CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE automation;

-- ========================================
-- TABELLA RESELLER
-- ========================================
CREATE TABLE IF NOT EXISTS reseller (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reseller VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_reseller (reseller)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- TABELLA RESELLER EMAIL
-- ========================================
CREATE TABLE IF NOT EXISTS reseller_email (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_reseller INT NOT NULL,
    email_destinatario VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_reseller) REFERENCES reseller(id) ON DELETE CASCADE,
    INDEX idx_reseller_email (id_reseller)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- TABELLA GROSSISTI
-- ========================================
CREATE TABLE IF NOT EXISTS grossisti (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_reseller INT NOT NULL,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    tipo_misura ENUM('Power', 'Gas') NOT NULL,
    cartella VARCHAR(500) NOT NULL,
    link_a_portale VARCHAR(500) NOT NULL,
    UDD VARCHAR(100) DEFAULT 'ecotrade',
    attivo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (id_reseller) REFERENCES reseller(id) ON DELETE CASCADE,
    INDEX idx_grossisti_reseller (id_reseller),
    INDEX idx_grossisti_udd (UDD),
    INDEX idx_grossisti_tipo (tipo_misura)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- TABELLA ESITI
-- ========================================
CREATE TABLE IF NOT EXISTS esiti (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_reseller INT NOT NULL,
    id_grossista INT NOT NULL,
    data_operazione DATETIME NOT NULL,
    data_riferimento DATE,
    data_inizio_ricerca DATE NOT NULL,
    data_fine_ricerca DATE NOT NULL,
    tipo_misura ENUM('Power', 'Gas') NOT NULL,
    log_contenuto TEXT,
    esito TINYINT NOT NULL COMMENT '0=Fallito, 1=Successo',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_reseller) REFERENCES reseller(id) ON DELETE CASCADE,
    FOREIGN KEY (id_grossista) REFERENCES grossisti(id) ON DELETE CASCADE,
    INDEX idx_esiti_reseller (id_reseller),
    INDEX idx_esiti_grossista (id_grossista),
    INDEX idx_esiti_data (data_operazione),
    INDEX idx_esiti_tipo (tipo_misura),
    INDEX idx_esiti_esito (esito)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- DATI DI ESEMPIO (OPZIONALE)
-- ========================================

-- Inserisci un reseller di esempio
INSERT INTO reseller (reseller) VALUES ('Reseller Demo');

-- Inserisci email per il reseller
INSERT INTO reseller_email (id_reseller, email_destinatario) 
VALUES (1, 'admin@example.com');

-- Inserisci un grossista di esempio
INSERT INTO grossisti (id_reseller, username, password, tipo_misura, cartella, link_a_portale, UDD)
VALUES (
    1,
    'username_demo',
    'password_demo',
    'Power',
    '/path/to/downloads/reseller_demo/power',
    'https://resellersecotrade.enerp.biz/reseller.php',
    'ecotrade'
);

-- ========================================
-- QUERY UTILI PER MANUTENZIONE
-- ========================================

-- Visualizza configurazione completa
-- SELECT 
--     g.id AS id_grossista,
--     r.id AS id_reseller,
--     r.reseller,
--     GROUP_CONCAT(e.email_destinatario SEPARATOR ',') AS email_destinatario,
--     g.username,
--     g.tipo_misura,
--     g.cartella,
--     g.attivo
-- FROM grossisti g
-- JOIN reseller r ON g.id_reseller = r.id
-- LEFT JOIN reseller_email e ON e.id_reseller = r.id
-- WHERE g.UDD = 'ecotrade'
-- GROUP BY g.id;

-- Visualizza ultimi esiti
-- SELECT 
--     r.reseller,
--     g.username,
--     e.tipo_misura,
--     e.data_operazione,
--     e.esito,
--     e.data_inizio_ricerca,
--     e.data_fine_ricerca
-- FROM esiti e
-- JOIN grossisti g ON e.id_grossista = g.id
-- JOIN reseller r ON e.id_reseller = r.id
-- ORDER BY e.data_operazione DESC
-- LIMIT 20;
