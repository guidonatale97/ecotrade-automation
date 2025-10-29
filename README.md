# 🤖 Ecotrade Automation Script

Script Python per l'automazione del download di flussi di misura (Power e Gas) dal portale reseller Ecotrade.

## 📋 Indice

- [Caratteristiche](#-caratteristiche)
- [Prerequisiti](#-prerequisiti)
- [Installazione](#-installazione)
- [Configurazione](#-configurazione)
- [Struttura Database](#-struttura-database)
- [Utilizzo](#-utilizzo)
- [Struttura File Scaricati](#-struttura-file-scaricati)
- [Troubleshooting](#-troubleshooting)
- [Sicurezza](#-sicurezza)
- [Licenza](#-licenza)

## ✨ Caratteristiche

- ✅ Login automatico al portale reseller Ecotrade
- ✅ Download automatico flussi Power e Gas:
  - STANDARD_SII
  - Curve orarie (PDO/RFO)
  - Letture non orarie (PNO/RNO)
  - Dati switching (SNM)
  - Altri flussi specifici per tipo misura
- ✅ Organizzazione automatica file per data (anno/mese/giorno)
- ✅ Gestione intelligente intervalli di download basata su esiti precedenti
- ✅ Sistema di retry automatico (max 3 tentativi configurabili)
- ✅ Invio email con esito operazioni e log allegato
- ✅ Logging dettagliato di tutte le operazioni
- ✅ Simulazione comportamento umano (anti-detection)
- ✅ Gestione multi-account e multi-reseller
- ✅ Salvataggio esiti su database MySQL

## 🔧 Prerequisiti

- Python 3.8 o superiore
- MySQL/MariaDB 5.7 o superiore
- Chromium (installato automaticamente da Playwright)
- Sistema operativo: Windows, Linux, macOS

## 📥 Installazione

### 1. Clona il repository

```bash
git clone https://github.com/tuousername/ecotrade-automation.git
cd ecotrade-automation
```

### 2. Crea un ambiente virtuale (opzionale ma consigliato)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Installa le dipendenze Python

```bash
pip install -r requirements.txt
```

### 4. Installa i browser Playwright

```bash
playwright install chromium
```

### 5. Configura il database

```bash
# Accedi a MySQL
mysql -u root -p

# Esegui lo schema
mysql -u root -p < database/schema.sql
```

## ⚙️ Configurazione

### 1. Crea il file `.env`

Copia il file di esempio e modificalo con le tue credenziali:

```bash
cp .env.example .env
```

### 2. Modifica il file `.env`

```env
# ========================================
# CONFIGURAZIONE EMAIL
# ========================================
EMAIL_SENDER=tua-email@dominio.it
EMAIL_PASSWORD=tua-password-sicura
SMTP_SERVER=smtp.tuoserver.it
SMTP_PORT=587

# ========================================
# CONFIGURAZIONE DATABASE
# ========================================
DB_HOST=localhost
DB_PORT=3306
DB_USER=tuo-utente-mysql
DB_PASSWORD=tua-password-mysql
DB_NAME=automation

# ========================================
# CONFIGURAZIONE SCRIPT (opzionale)
# ========================================
HEADLESS_BROWSER=false
MAX_RETRIES=3
DOWNLOAD_TIMEOUT=300
```

### 3. Popola il database

Inserisci i dati dei tuoi reseller e grossisti nel database:

```sql
-- Esempio inserimento reseller
INSERT INTO reseller (reseller) VALUES ('Nome Reseller');

-- Esempio inserimento email destinatari
INSERT INTO reseller_email (id_reseller, email_destinatario) 
VALUES (1, 'destinatario@email.com');

-- Esempio inserimento grossista
INSERT INTO grossisti (
    id_reseller, 
    username, 
    password, 
    tipo_misura, 
    cartella, 
    link_a_portale, 
    UDD
) VALUES (
    1,
    'username_portale',
    'password_portale',
    'Power',
    '/path/to/downloads/reseller_name/power',
    'https://resellersecotrade.enerp.biz/reseller.php',
    'ecotrade'
);
```

## 🗄️ Struttura Database

Il database è composto da 4 tabelle principali:

### `reseller`
Anagrafica dei reseller
- `id` (PK)
- `reseller` (nome)
- `created_at`, `updated_at`

### `reseller_email`
Email destinatari per ciascun reseller
- `id` (PK)
- `id_reseller` (FK)
- `email_destinatario`

### `grossisti`
Configurazione account grossisti Ecotrade
- `id` (PK)
- `id_reseller` (FK)
- `username`, `password` (credenziali portale)
- `tipo_misura` (Power/Gas)
- `cartella` (path download)
- `link_a_portale`
- `UDD` (identificativo grossista)
- `attivo` (boolean)

### `esiti`
Storico operazioni e log
- `id` (PK)
- `id_reseller`, `id_grossista` (FK)
- `data_operazione`, `data_riferimento`
- `data_inizio_ricerca`, `data_fine_ricerca`
- `tipo_misura`
- `log_contenuto` (testo completo log)
- `esito` (0=Fallito, 1=Successo)

## 🚀 Utilizzo

### Esecuzione manuale

```bash
python ecotrade_automation.py
```

### Esecuzione schedulata (Linux)

Aggiungi al crontab per esecuzione automatica:

```bash
# Modifica crontab
crontab -e

# Esegui ogni giorno alle 2:00 AM
0 2 * * * cd /path/to/ecotrade-automation && /path/to/venv/bin/python ecotrade_automation.py >> /var/log/ecotrade.log 2>&1
```

### Esecuzione schedulata (Windows)

Usa l'Utilità di pianificazione di Windows:
1. Apri "Utilità di pianificazione"
2. Crea attività base
3. Seleziona trigger (giornaliero, orario specifico)
4. Azione: Avvia programma
   - Programma: `C:\path\to\venv\Scripts\python.exe`
   - Argomenti: `ecotrade_automation.py`
   - Inizia da: `C:\path\to\ecotrade-automation`

## 📂 Struttura File Scaricati

I file vengono organizzati automaticamente in questa struttura:

```
cartella_reseller/
└── tipo_misura/
    └── anno/
        └── mese/
            └── giorno/
                └── YYYYMMDD_HHMMSS_ECOTRADE.zip
```

Esempio:

```
/downloads/
└── ResellersDemo/
    └── Power/
        └── 2025/
            └── gennaio/
                └── 15/
                    └── 20250115_143022_ECOTRADE.zip
```

I file di log `.txt` rimangono nella cartella root del reseller.

## 🔍 Troubleshooting

### Problema: "Variabili d'ambiente mancanti"

**Soluzione:** Verifica che il file `.env` esista e contenga tutte le variabili obbligatorie.

```bash
# Verifica presenza file
ls -la .env

# Verifica contenuto
cat .env
```

### Problema: Errore connessione database

**Soluzione:** Verifica credenziali e che MySQL sia in esecuzione.

```bash
# Testa connessione
mysql -h localhost -u tuo_utente -p automation

# Verifica servizio MySQL (Linux)
sudo systemctl status mysql

# Windows: verifica servizio MySQL in services.msc
```

### Problema: Browser non si apre / Playwright non funziona

**Soluzione:** Reinstalla i browser Playwright.

```bash
playwright install --force chromium
```

### Problema: Timeout durante download

**Soluzione:** Aumenta il timeout nel file `.env`.

```env
DOWNLOAD_TIMEOUT=600
```

### Problema: Email non vengono inviate

**Soluzione:** Verifica configurazione SMTP e credenziali.

```bash
# Testa connessione SMTP manualmente
python -c "import smtplib; s=smtplib.SMTP('smtp.server.it', 587); s.starttls(); s.login('user', 'pass'); print('OK')"
```

## 🔒 Sicurezza

### ⚠️ Regole Fondamentali

1. **MAI committare il file `.env`** su Git
2. **NON hardcodare mai credenziali** nel codice
3. **Usare password complesse** per database e email
4. **Rotazione password** periodica (ogni 90 giorni)
5. **Limitare permessi** file `.env` (solo lettura utente)

```bash
# Linux/macOS: imposta permessi restrittivi
chmod 600 .env
```

### Best Practices

- Usa variabili d'ambiente per tutte le credenziali
- Mantieni aggiornate le dipendenze (`pip install --upgrade`)
- Esegui lo script con utente non privilegiato
- Monitora i log per attività sospette
- Backup regolare del database

## 🐛 Log e Debugging

I log vengono salvati in due posizioni:

1. **Console** (stdout) - per monitoraggio real-time
2. **File** - nella cartella del reseller

Formato log:
```
2025-01-15 14:30:22 - INFO - Login effettuato con successo
2025-01-15 14:30:25 - INFO - Pagina Flussi caricata correttamente
2025-01-15 14:30:30 - WARNING - Nessun file presente sul server
```

Per aumentare il livello di dettaglio, modifica la riga:

```python
logger.setLevel(logging.DEBUG)  # invece di INFO
```

## 📊 Monitoraggio

### Query utili per monitorare le operazioni

```sql
-- Ultimi 10 esiti
SELECT 
    r.reseller,
    g.username,
    e.tipo_misura,
    e.data_operazione,
    CASE WHEN e.esito = 1 THEN 'Successo' ELSE 'Fallito' END as esito
FROM esiti e
JOIN grossisti g ON e.id_grossista = g.id
JOIN reseller r ON e.id_reseller = r.id
ORDER BY e.data_operazione DESC
LIMIT 10;

-- Statistiche successo/fallimento ultimi 30 giorni
SELECT 
    tipo_misura,
    COUNT(*) as totale,
    SUM(esito) as successi,
    COUNT(*) - SUM(esito) as fallimenti,
    ROUND(SUM(esito) / COUNT(*) * 100, 2) as percentuale_successo
FROM esiti
WHERE data_operazione >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY tipo_misura;
```

## 🤝 Contributi

Per contribuire al progetto:

1. Fork del repository
2. Crea un branch per la feature (`git checkout -b feature/AmazingFeature`)
3. Commit delle modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📝 Changelog

### v1.0.0 (2025-01-15)
- Release iniziale
- Supporto Power e Gas
- Gestione multi-account
- Sistema retry
- Organizzazione automatica file

## 📄 Licenza

Questo progetto è distribuito sotto licenza MIT. Vedi il file `LICENSE` per maggiori dettagli.
