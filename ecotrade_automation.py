import asyncio
import os
import random
import logging
import smtplib
import shutil
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from playwright.async_api import async_playwright
import pymysql
from dotenv import load_dotenv

# Carica variabili d'ambiente dal file .env
load_dotenv()

# ========================================
# CONFIGURAZIONE DA VARIABILI D'AMBIENTE
# ========================================

# Configurazione email
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtps.aruba.it")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# Configurazione database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "automation")

# Configurazione script
HEADLESS_BROWSER = os.getenv("HEADLESS_BROWSER", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", 300))

# Verifica che le variabili obbligatorie siano configurate
required_vars = {
    "EMAIL_SENDER": EMAIL_SENDER,
    "EMAIL_PASSWORD": EMAIL_PASSWORD,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD
}

missing_vars = [key for key, value in required_vars.items() if not value]
if missing_vars:
    raise EnvironmentError(
        f"Variabili d'ambiente mancanti: {', '.join(missing_vars)}\n"
        f"Crea un file .env nella root del progetto (vedi .env.example)"
    )

# ========================================
# FUNZIONI UTILITY
# ========================================

# Funzione per simulare pause tipiche di un'interazione umana
async def human_pause(min_sec=1.0, max_sec=1.5):
    """
    Simula una pausa di durata variabile per imitare il comportamento umano.
    Utile dopo aver completato un'azione e prima di iniziarne un'altra.
    """
    await asyncio.sleep(random.uniform(min_sec, max_sec))

# Funzione per simulare la digitazione umana con velocità variabile
async def slow_type(element, text):
    """
    Simula una digitazione umana digitando un carattere alla volta con pause casuali.
    Questo aiuta a evitare il rilevamento di automazione da parte del sito web.
    """
    for char in text:
        await element.type(char)
        await asyncio.sleep(random.uniform(0.1, 0.25))

# Funzione per rilevare schermate di errore ASP.NET
async def check_server_error(page):
    """
    Verifica se la pagina corrente mostra una schermata di errore ASP.NET.
    Se sì, solleva un'eccezione con i primi caratteri dell'HTML.
    """
    if await page.locator("text=Server Error in").count() > 0 or await page.locator("text=Exception Details").count() > 0:
        html = await page.content()
        raise Exception("Errore ASP.NET: rilevata pagina di errore\n\nContenuto:\n" + html[:1000])

# ========================================
# FUNZIONI DATABASE
# ========================================

# Funzione per caricare gli account dal database
def carica_account_da_db():
    '''
    Carica gli account dal database e restituisce una lista di dizionari con i dettagli degli account.
    Ogni dizionario contiene le seguenti chiavi:
    - id_grossista
    - id_reseller
    - reseller
    - email_destinatario
    - username
    - password
    - tipo_misura
    - cartella
    - link_a_portale
    '''
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = """
        SELECT 
                g.id AS id_grossista,
                r.id AS id_reseller,
                r.reseller,
                GROUP_CONCAT(e.email_destinatario SEPARATOR ',') AS email_destinatario,
                g.username,
                g.password,
                g.tipo_misura,
                g.cartella,
                g.link_a_portale
        FROM grossisti g
        JOIN reseller r ON g.id_reseller = r.id
        LEFT JOIN reseller_email e ON e.id_reseller = r.id
        WHERE g.UDD = 'ecotrade' AND g.attivo = TRUE
        GROUP BY g.id
    """
    cursor.execute(query)
    account_list = cursor.fetchall()

    # Trasforma le email da stringa separata da virgole a lista Python
    for account in account_list:
        if account['email_destinatario']:
            account['email_destinatario'] = account['email_destinatario'].split(',')
        else:
            account['email_destinatario'] = []

    conn.close()
    return account_list

# Funzione per ottenere l'intervallo di date da usare nei filtri
def get_intervallo_date(id_reseller, id_grossista, tipo_misura):
    """
    Restituisce (start_date, end_date) da usare nel filtro secondo la logica:
    - Se NON esiste una riga: start = oggi - 7gg, end = oggi
    - Se esiste una riga con esito = 0: start = data_inizio_ricerca, end = oggi
    - Se esiste una riga con esito = 1: start = oggi - 7gg, end = oggi
    """
    oggi = datetime.now().date()
    end = oggi
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT data_inizio_ricerca, esito
        FROM esiti
        WHERE id_reseller = %s AND id_grossista = %s AND tipo_misura = %s
        ORDER BY data_operazione DESC
        LIMIT 1
    """, (id_reseller, id_grossista, tipo_misura))
    
    result = cursor.fetchone()
    conn.close()

    if not result:
        start = oggi - timedelta(days=7)
    else:
        data_inizio, esito = result
        if esito == 0:
            start = data_inizio
        else:  # esito == 1
            start = oggi - timedelta(days=7)

    return start, end

# Funzione per salvare i risultati su database
def salva_su_db(id_reseller, id_grossista, data_operazione, data_riferimento, data_inizio_ricerca, data_fine_ricerca, tipo_misura, log_contenuto, esito):
    '''
    Salva i risultati dell'operazione nel database.
    '''
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO esiti (id_reseller, id_grossista, data_operazione, data_riferimento, data_inizio_ricerca, data_fine_ricerca, tipo_misura, log_contenuto, esito)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (id_reseller, id_grossista, data_operazione, data_riferimento, data_inizio_ricerca, data_fine_ricerca, tipo_misura, log_contenuto, esito))
    conn.commit()
    conn.close()

# ========================================
# FUNZIONI EMAIL
# ========================================

# Funzione per inviare email
def send_individual_email(account, result):
    '''
    Invia un'email con i dettagli dell'operazione.
    L'email include il log dell'operazione come allegato.
    '''
    if not account['email_destinatario']:
        print(f"[EMAIL] Nessun destinatario configurato per {account['reseller']}")
        return

    # Prepara l'oggetto email
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER

    # Se è una lista di email, uniscile in una stringa separata da virgole
    destinatari = ', '.join(account['email_destinatario'])
    msg['To'] = destinatari

    stato = "Completato con successo" if result['success'] else "Errore"
    msg['Subject'] = f"ECOTRADE - Esito Download {account['tipo_misura']} - {stato}"

    # Corpo dell'email
    corpo = f"""
    <html>
    <body>
        <h2>Resoconto Operazione Ecotrade</h2>
        <p><strong>Reseller:</strong> {account['reseller']}</p>
        <p><strong>Username:</strong> {account['username']}</p>
        <p><strong>Tipo Misura:</strong> {account['tipo_misura']}</p>
        <p><strong>Esito:</strong> {stato}</p>
        <p><strong>File scaricato:</strong> {result['download_path'] or 'Nessun file disponibile'}</p>
        <p>In allegato il file di log dell'operazione.</p>
        <hr>
        <p style="font-size: 12px; color: #666;">Questo è un messaggio automatico - Non rispondere</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(corpo, 'html'))

    # Allegato log
    if result['log_file'] and os.path.exists(result['log_file']):
        with open(result['log_file'], 'rb') as file:
            filename = os.path.basename(result['log_file'])
            part = MIMEApplication(file.read(), Name=filename, _subtype="txt")
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)

    try:
        # Invia l'email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[EMAIL] Inviata email a {destinatari}")
    except Exception as e:
        print(f"[EMAIL] Errore invio email a {destinatari}: {e}")

# ========================================
# FUNZIONI LOGGING
# ========================================

# Funzione per settare il logger
def setup_logger(account, tipo_misura):
    """
    Imposta il logger per l'account specifico.
    Restituisce il percorso del file di log e il logger configurato.
    """
    os.makedirs(account['cartella'], exist_ok=True)  #crea cartella se non esiste
    download_dir = account['cartella']
    log_file = os.path.join(download_dir, f"ecotrade_log_{tipo_misura}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    logger_name = f"ECOTRADE_{account['username']}_{tipo_misura}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    fh = logging.FileHandler(log_file)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
    logger.addHandler(ch)
    return log_file, logger

# ========================================
# FUNZIONI BROWSER
# ========================================

# Funzione per gestire il browser
async def setup_browser(playwright, download_dir):
    """
    Avvia il browser con un nuovo contesto e pagina.
    Ritorna browser, context, page e un evento per gestire il download.
    """
    browser = await playwright.chromium.launch(headless=HEADLESS_BROWSER)
    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()
    download_event = asyncio.Event()
    return browser, context, page, download_event

# Funzione per gestire il download
async def handle_download(download, download_event, download_dir):
    """
    Salva il file scaricato e segnala l'avvenuto download tramite l'evento.
    Rimuove file TXT non validi.
    """
    download_path = os.path.join(download_dir, download.suggested_filename)
    await download.save_as(download_path)

    # Verifica estensione del file
    if download_path.lower().endswith(".txt"):
        os.remove(download_path)
        print(f"[DOWNLOAD] File TXT ignorato: {download_path}")
        download_event.set()
        return

    download_event.set()

# ========================================
# FUNZIONI NAVIGAZIONE PORTALE
# ========================================

# Funzione per eseguire il login
async def login(page, account, logger):
    """
    Esegue il login nel portale ECOTRADE.
    """
    try:
        await human_pause()
        logger.info("Accesso alla pagina di login")
        await page.goto(account['link_a_portale'])
        await check_server_error(page)
        await slow_type(page.locator("#codcliente"), account['username'])
        await slow_type(page.locator("#password"), account['password'])
        await human_pause()
        await page.locator("#button").click()
        await page.wait_for_url("https://resellersecotrade.enerp.biz/reseller.php")
        logger.info("Login effettuato con successo")
    except Exception as e:
        raise Exception(f"Errore durante il login: {str(e)}")

# Funzione per eseguire la navigazione alla pagina "FLUSSI"
async def naviga_flussi(page, logger):
    """
    Naviga alla sezione FLUSSI del portale.
    """
    try:
        await page.locator("a:has-text('FLUSSI')").click()
        await page.wait_for_url("https://resellersecotrade.enerp.biz/reseller.php?module=reseller&page=flussi")
        await check_server_error(page)
        logger.info("Pagina Flussi caricata correttamente")
    except Exception as e:
        raise Exception(f"Errore durante la navigazione: {str(e)}")

# Funzione per selezionare il tipo di misura
async def seleziona_tipo_misura(page, tipo_misura, logger):
    """
    Seleziona il tab e i parametri corretti in base al tipo misura (Power o Gas).
    Restituisce il prefisso dei parametri per i campi successivi.
    """
    try:
        await human_pause()
        if tipo_misura == 'Power':
            # Seleziona "Energia"
            await page.locator("span:has-text('Energia')").click()
            param_prefix = "td1"
        else:
            # Seleziona "GAS"
            await page.locator("span:has-text('GAS')").click()
            param_prefix = "td2"

        await asyncio.sleep(2)  # tempo per visibilità contenuti
        await check_server_error(page)
        logger.info(f"Selezionato tipo misura: {tipo_misura}")
        return param_prefix
    except Exception as e:
        raise Exception(f"Errore durante la selezione della fornitura: {str(e)}")

# Funzione per individuare i file da scaricare in base a codici e intervallo di data
async def seleziona_checkbox_per_prima_tabella(page, logger, id_reseller, id_grossista, tipo_misura):
    """
    Seleziona tutte le checkbox nella prima tabella 'Flussi' in base al nome della cartella.
    """
    if tipo_misura.lower() == 'power':
        CODICI_DESIDERATI = [
            "STANDARD_SII",
            "Curve orarie ( flussi PDO / RFO)",
            "Letture non orarie ( flussi PNO / RNO)",
            "Dati di misura di switching ( flussi SNM)"
        ]
    elif tipo_misura.lower() == 'gas':
        CODICI_DESIDERATI = [
            "STANDARD_SII",
            "Curve orarie ( flussi PDO / RFO)",
            "Letture non orarie ( flussi PNO / RNO)",
            "Dati di misura di switching ( flussi SNM)"
        ]
    else:
        logger.warning(f"Tipo misura non gestito: {tipo_misura}")
        return False

    try:
        # Trova la tabella corretta
        tabella_flussi = (
            page.locator("#pageContainer table#listaStati")
            if tipo_misura.lower() == 'power'
            else page.locator("#pageContainerGas table#listaStati")
        )

        if await tabella_flussi.count() == 0:
            logger.info("Tabella principale non trovata, cercando tabella alternativa...")
            tabella_flussi = page.locator("table.tablesorter").last

        if await tabella_flussi.count() == 0:
            logger.error("Impossibile trovare la tabella dei flussi")
            return False

        checkboxes = tabella_flussi.locator("input[type='checkbox']")
        count = await checkboxes.count()

        logger.info(f"Trovate {count} checkbox nella prima tabella Flussi")

        selezionati = 0
        processed = 0

        for i in range(count):
            checkbox = checkboxes.nth(i)
            row = checkbox.locator("xpath=ancestor::tr")

            try:
                nome_cartella = await row.locator("td:nth-child(1)").inner_text()
                nome_cartella = nome_cartella.strip()

                # Confronto con nomi desiderati
                if any(codice in nome_cartella for codice in CODICI_DESIDERATI):
                    await checkbox.check()
                    selezionati += 1
                    logger.info(f"Selezionata: {nome_cartella}")
                else:
                    logger.debug(f"Ignorata: {nome_cartella}")
            except Exception as e:
                logger.warning(f"Errore nel processare la riga {i}: {e}")

            processed += 1

        logger.info(f"Processate {processed}/{count} righe totali")

        if selezionati == 0:
            logger.info("Nessuna checkbox selezionabile trovata.")
            return False
        else:
            logger.info(f"Selezionate {selezionati} righe.")
            return True

    except Exception as e:
        logger.error(f"Errore generale nella selezione checkbox: {str(e)}")
        return False

# Funzione per avviare il download dei flussi selezionati
async def download_file_prima_tabella(page, download_event, logger, tipo_misura):
    try:
        logger.info("Preparazione al download dei flussi della prima tabella")
        await human_pause()

        # RESET DELL'EVENTO PRIMA DEL NUOVO DOWNLOAD
        download_event.clear()
        logger.info("Evento download resettato per il nuovo download")

        try:
            logger.info("Avvio download flussi")
            if tipo_misura == 'Power':
                await page.evaluate("scarica('/');")
            elif tipo_misura == 'Gas':
                await page.evaluate("scaricaGas('/');")
            else:
                logger.error(f"Tipo misura sconosciuto: {tipo_misura}")
                return False
            logger.info("Click simulato su 'Download'")
        except Exception as e:
            logger.warning(f"Errore durante il click sul pulsante 'Download': {str(e)}")
            return False

        await asyncio.sleep(2)

        # Verifica se è apparsa la schermata "Nessun file presente"
        if "downloadFlussi" in page.url:
            contenuto = await page.content()
            if "Nessun file presente" in contenuto:
                logger.warning("File selezionati ma assenti sul server. Nessun download effettuato (ma continuo).")
                return False  # Non interrompe il processo

        return True

    except Exception as e:
        logger.error(f"Errore durante il download: {str(e)}")
        return False

    finally:
        await human_pause()
        logger.info("Pulsante di download cliccato con successo (prima tabella)")

# Funzione per gestire il download e attendere il completamento
async def gestisci_download(download_event, logger, download_dir):
    """
    Attende il completamento del download e restituisce il risultato.
    """
    try:
        await human_pause()
        logger.info("In attesa del completamento del download")
        await asyncio.wait_for(download_event.wait(), timeout=DOWNLOAD_TIMEOUT)
        logger.info("Download dati completato con successo")
        # Cerca il file più recente nella cartella
        files = os.listdir(download_dir)
        files = [os.path.join(download_dir, f) for f in files if os.path.isfile(os.path.join(download_dir, f))]
        download_path = max(files, key=os.path.getctime) if files else None
        return True, download_path
    except asyncio.TimeoutError:
        logger.warning("Timeout: download dati non completato entro il tempo previsto")
        return False, None

# Funzione per selezionare il file XML ed eseguire la ricerca già scaricati
async def inserisci_xml(page, tipo_misura, logger, id_reseller, id_grossista):
    try:
        await human_pause()

        # Recupera intervallo date dal database
        data_da, data_a = get_intervallo_date(id_reseller, id_grossista, tipo_misura)
        data_da_str = data_da.strftime("%Y-%m-%d")
        data_a_str = data_a.strftime("%Y-%m-%d")
        logger.info(f"Inserite date nel filtro: {data_da_str} -> {data_a_str}")

        if tipo_misura == 'Power':
            # Inserisci "xml" nel campo nome file
            await slow_type(page.locator("#cercaFileScaricati"), "xml")
            logger.info("XML inserito con successo per la seconda tabella")

            await human_pause()

            # Inserisci date nei campi "Data file da" e "a"
            await page.locator("#dataFileDaScaricati").fill(data_da_str)
            await page.locator("#dataFileAScaricati").fill(data_a_str)
            logger.info("Date inserite con successo nei campi data")

            await human_pause()

            # Clicca su "Cerca"
            await page.locator("//input[@type='button' and @value='Cerca' and @onclick='cercaScaricati();']").click()
            logger.info("Bottone 'Cerca' cliccato con successo")
        else:
            # Inserisci "xml" nel campo nome file GAS
            await slow_type(page.locator("#cercaFileScaricatiGas"), "xml")
            logger.info("XML inserito con successo")

            await human_pause()

            # Inserisci date anche per GAS
            await page.locator("#dataFileDaScaricatiGas").fill(data_da_str)
            await page.locator("#dataFileAScaricatiGas").fill(data_a_str)
            logger.info("Date inserite con successo nei campi data (GAS)")

            await human_pause()

            # Clicca su "Cerca"
            await page.locator("//input[@type='button' and @value='Cerca' and @onclick='cercaScaricatiGas();']").click()
            logger.info("Bottone 'Cerca' cliccato con successo")

        await asyncio.sleep(10)  # tempo per visibilità contenuti
        await check_server_error(page)

    except Exception as e:
        raise Exception(f"Errore durante la digitazione o ricerca XML: {str(e)}")

# Funzione per individuare i file da scaricare in base a codici e intervallo di data
async def seleziona_checkbox_per_codici_seconda_tabella(page, logger, id_reseller, id_grossista, tipo_misura):
    """
    Esegue nella console di sviluppo JS per selezionare le checkbox desiderate,
    in base al tipo di misura, ai codici specifici e all'intervallo di date.
    Attende che la tabella sia caricata prima di eseguire lo script.
    """
    if tipo_misura.lower() == 'power':
        CODICI_DESIDERATI = [
            "SNF", "F2G", "SOF", "SNM2G", "RFO2G", "PDO2G", "RNV2G", "SNM",
            "PNO", "VNO2G", "PNO2G", "VNO", "SMIS", "RNO2G", "RNV",
            "RNO", "RSN2G", "RSN", "PDO", "RFO", "DS2G", "DSR2G", "DS"
        ]
    elif tipo_misura.lower() == 'gas':
        CODICI_DESIDERATI = ["TML", "D01", "IGMG", "A01", "RML"]
    else:
        logger.warning(f"Tipo misura non gestito: {tipo_misura}")
        return False

    # Ottieni intervallo dal database
    start_date, end_date = get_intervallo_date(id_reseller, id_grossista, tipo_misura)
    logger.info(f"Filtro intervallo: {start_date} -> {end_date}")

    # Converti in stringa ISO per JS
    js_start = f"{start_date}T00:00:00"
    js_end = f"{end_date}T00:00:00"
    js_codici = str(CODICI_DESIDERATI)

    # Script JS da eseguire nella console del browser
    js_script = f"""
    console.log("----------- Download Flussi Misure via Script -----------");

    const startDate = new Date("{js_start}");
    const endDate = new Date("{js_end}");
    const validNames = {js_codici};
    let count = 0;

    document.querySelectorAll('table.tablesorter tbody tr').forEach(row => {{
        const nameCell = row.children[0];
        const dateCell = row.children[1];
        const checkboxCell = row.children[2];
        if (nameCell && dateCell && checkboxCell) {{
            const nameText = nameCell.textContent.trim();
            const dateText = dateCell.textContent.trim();
            const checkbox = checkboxCell.querySelector('input[type="checkbox"]');

            if (checkbox && dateText) {{
                const [d, m, y] = dateText.split(" ")[0].split("/");
                const time = "00:00:00";
                const rowDate = new Date(y + '-' + m + '-' + d + 'T' + time);

                if (rowDate >= startDate && rowDate <= endDate &&
                    validNames.some(code => nameText.includes(code))) {{
                    checkbox.checked = true;
                    count += 1;
                    console.log("✔ Selezionato: " + nameText + " (" + dateText + ")");
                }}
            }}
        }}
    }});

    console.log("Totale selezionati: " + count);
    """

    try:
        # Attendi che la tabella venga popolata con i risultati aggiornati
        await page.wait_for_function(
            """() => {
                const rows = document.querySelectorAll("#pageContainerScaricati table.tablesorter tbody tr");
                return [...rows].some(tr => tr.innerText.includes(".xml"));
            }""",
            timeout=15000
        )
        await asyncio.sleep(1)  # Piccola pausa extra

        # Esegui lo script JS
        await page.evaluate(js_script)
        logger.info("Esecuzione JavaScript completata nella console del browser.")
        return True
    except Exception as e:
        logger.error(f"Errore durante esecuzione JS in console: {str(e)}")
        return False

# Funzione per avviare il download dei flussi selezionati
async def download_file_seconda_tabella(page, download_event, logger, tipo_misura):
    try:
        logger.info("Preparazione al download dei flussi")
        await human_pause()

        # RESET DELL'EVENTO PRIMA DEL NUOVO DOWNLOAD
        download_event.clear()
        logger.info("Evento download resettato per il nuovo download")

        try:
            logger.info("Avvio download flussi")
            if tipo_misura.lower() == 'power':
                await page.evaluate("scaricaScaricati('/scaricati/');")
            elif tipo_misura.lower() == 'gas':
                await page.evaluate("scaricaScaricatiGas('/scaricati/');")
            else:
                logger.error(f"Tipo misura sconosciuto: {tipo_misura}")
                return False
            logger.info("Click simulato su 'Download'")
        except Exception as e:
            logger.warning(f"Errore durante il click sul pulsante 'Download': {str(e)}")
            return False

        await asyncio.sleep(2)

        # Controlla se si è stati rediretti alla pagina che indica assenza file
        if "downloadFlussi" in page.url:
            contenuto = await page.content()
            if "Nessun file presente" in contenuto:
                logger.warning("File selezionati ma assenti sul server. Nessun download effettuato.")
                return False

        return True  # OK, procedi al gestisci_download()

    except Exception as e:
        logger.error(f"Errore durante il download: {str(e)}")
        return False

    finally:
        await human_pause()
        logger.info("Pulsante di download cliccato con successo")

# ========================================
# FUNZIONI ORGANIZZAZIONE FILE
# ========================================

# Mappa dei nomi dei mesi in italiano
MESI_ITALIANI = {
    1: "gennaio",
    2: "febbraio",
    3: "marzo",
    4: "aprile",
    5: "maggio",
    6: "giugno",
    7: "luglio",
    8: "agosto",
    9: "settembre",
    10: "ottobre",
    11: "novembre",
    12: "dicembre"
}

def organizza_file_scaricato(download_path, account, logger):
    """
    Sposta solo i file ZIP nella struttura: reseller/misura/anno/mese/giorno/
    I file di log (.txt) restano sempre nella root account['cartella'].

    Args:
        download_path: percorso del file scaricato
        account: dizionario con i dettagli dell'account
        logger: logger per registrare le operazioni

    Returns:
        nuovo percorso del file (solo per i file spostati)
    """
    if not download_path or not os.path.exists(download_path):
        logger.error("Nessun file scaricato da organizzare")
        return None

    # Se è un file di log .txt, NON spostarlo
    if download_path.lower().endswith('.txt'):
        logger.info("File di log rilevato. Nessuno spostamento effettuato.")
        return download_path

    try:
        # Cartella base già esistente (reseller/misura)
        base_dir = account['cartella']
        
        # Ottiene la data corrente per creare la struttura delle cartelle
        now = datetime.now()
        anno = str(now.year)
        mese = MESI_ITALIANI[now.month]
        giorno = str(now.day)
        
        # Crea il percorso completo anno/mese/giorno
        anno_dir = os.path.join(base_dir, anno)
        mese_dir = os.path.join(anno_dir, mese)
        giorno_dir = os.path.join(mese_dir, giorno)
        
        # Crea le cartelle se non esistono
        os.makedirs(giorno_dir, exist_ok=True)
        logger.info(f"Struttura cartelle creata: {giorno_dir}")
        
        # Rinomina il file ZIP con timestamp e nome grossista
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        nome_grossista = 'ECOTRADE'
        nome_originale = os.path.basename(download_path)
        estensione = os.path.splitext(nome_originale)[1]
        nuovo_nome = f"{timestamp}_{nome_grossista}{estensione}"
        
        # Percorso completo del nuovo file ZIP
        nuovo_percorso = os.path.join(giorno_dir, nuovo_nome)
        
        # Sposta e rinomina il file ZIP
        shutil.move(download_path, nuovo_percorso)
        logger.info(f"File ZIP spostato e rinominato: {nuovo_percorso}")
        
        return nuovo_percorso

    except Exception as e:
        logger.error(f"Errore durante l'organizzazione del file ZIP: {str(e)}")
        return download_path  # Ritorna il percorso originale in caso di errore

# ========================================
# FUNZIONE PRINCIPALE
# ========================================

# Funzione principale che esegue l'automazione
async def run(account, data_inizio, data_fine):
    username = account['username']
    download_dir = account['cartella']
    tipo_misura = account['tipo_misura']
    id_reseller = account['id_reseller']
    id_grossista = account['id_grossista']

    os.makedirs(download_dir, exist_ok=True)
    log_file, logger = setup_logger(account, tipo_misura)

    success = False
    download_path = None

    try:
        # Fase 1: Avvio del browser
        logger.info("Avvio browser...")
        async with async_playwright() as p:
            browser, context, page, download_event = await setup_browser(p, download_dir)
            await human_pause()
            page.on("download", lambda download: asyncio.create_task(handle_download(download, download_event, download_dir)))
            await human_pause()

            # Fase 2: Login
            await login(page, account, logger)
            await human_pause()

            # Fase 3: Navigazione alla pagina FLUSSI
            await naviga_flussi(page, logger)
            await human_pause()

            # Fase 4: Selezione del tipo di misure
            await seleziona_tipo_misura(page, tipo_misura, logger)
            await human_pause()

            # Fase 5: individuare i file da scaricare 
            checkbox_trovate = await seleziona_checkbox_per_prima_tabella(page, logger, id_reseller, id_grossista, tipo_misura)
            await human_pause()

            if not checkbox_trovate:
                logger.warning("Nessuna checkbox valida trovata nella prima tabella.")
                await browser.close()
                return {
                    "username": username,
                    "success": False,
                    "log_file": log_file,
                    "download_path": None,
                    "tipo_misura": tipo_misura
                }

            # Fase 6: Download dei flussi selezionati
            download_avviato = await download_file_prima_tabella(page, download_event, logger, tipo_misura)
            await human_pause()
            if download_avviato:
                _, temp_path = await gestisci_download(download_event, logger, download_dir)
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        logger.info(f"Primo download eliminato: {temp_path}")
                    except Exception as e:
                        logger.warning(f"Errore durante l'eliminazione del primo file: {e}")
            else:
                logger.info("Nessun file scaricato nella prima tabella: torno alla pagina Flussi per procedere")

                try:
                    await page.goto("https://resellersecotrade.enerp.biz/reseller.php")
                    await check_server_error(page)
                    await human_pause()
                    logger.info("Navigato alla home del portale")
                except Exception as e:
                    logger.error(f"Errore durante la navigazione alla home del portale: {str(e)}")

            # Fase 7: nuova navigazione flussi
            await naviga_flussi(page, logger)
            await human_pause()

            # Fase 8: nuova selezione tipo misure
            await seleziona_tipo_misura(page, tipo_misura, logger)
            await human_pause()

            # Fase 9: selezionare il file XML ed eseguire la ricerca
            await inserisci_xml(page, tipo_misura, logger, id_reseller, id_grossista)
            await human_pause()

            # Fase 10: individuare i file da scaricare
            checkbox_trovate = await seleziona_checkbox_per_codici_seconda_tabella(page, logger, id_reseller, id_grossista, tipo_misura)
            await human_pause()

            if not checkbox_trovate:
                logger.error("ERRORE BLOCCANTE: Nessuna checkbox valida trovata nella seconda tabella. Terminazione forzata.")
                await browser.close()
                raise Exception("Terminazione anticipata: Nessuna checkbox selezionabile nella seconda tabella.")

            # Fase 11: Download dei flussi selezionati
            download_avviato = await download_file_seconda_tabella(page, download_event, logger, tipo_misura)
            await human_pause()
            if not download_avviato:
                logger.warning("Download non avviato nella seconda tabella.")
                await browser.close()
                return {
                    "username": username,
                    "success": False,
                    "log_file": log_file,
                    "download_path": None,
                    "tipo_misura": tipo_misura
                }

            success, download_path = await gestisci_download(download_event, logger, download_dir)

            # Fase 12: Chiusura del browser
            logger.info("Chiusura del browser")
            await human_pause(3.0, 5.0)
            await browser.close()

            # Fase 13: Organizzazione dei file scaricati in struttura anno/mese/giorno
            if success and download_path:
                logger.info("Organizzo file in struttura anno/mese/giorno")
                nuovo_percorso = organizza_file_scaricato(download_path, account, logger)
                if nuovo_percorso:
                    download_path = nuovo_percorso
                    logger.info(f"File organizzato correttamente nel percorso: {download_path}")
    except Exception as e:
        error_msg = str(e)
        if "nessuna riga da scaricare" in error_msg.lower():
            logger.warning("Interruzione anticipata: nessun flusso da scaricare per i criteri specificati.")
        else:
            logger.error(f"Errore: {error_msg}")

    finally:
        await asyncio.sleep(0.2)
        log_contenuto = ""
        try:
            with open(log_file, 'r') as f:
                log_contenuto = f.read()
        except Exception as e:
            print(f"[LOG] Errore lettura file log: {e}")

        if success:
            salva_su_db(
                id_reseller,
                id_grossista,
                datetime.now(),
                data_fine,
                data_inizio,
                data_fine,
                tipo_misura,
                log_contenuto,
                1
            )

    return {
        "username": username,
        "success": success,
        "log_file": log_file,
        "download_path": download_path,
        "tipo_misura": tipo_misura
    }

# ========================================
# ENTRYPOINT SCRIPT
# ========================================

# Avvio dello script
if __name__ == "__main__":
    async def main():
        print("=" * 60)
        print("ECOTRADE AUTOMATION SCRIPT")
        print("=" * 60)
        print(f"Database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
        print(f"Email: {EMAIL_SENDER}")
        print(f"Headless: {HEADLESS_BROWSER}")
        print(f"Max Retries: {MAX_RETRIES}")
        print("=" * 60)
        
        account_list = carica_account_da_db()
        print(f"\n[INFO] Caricati {len(account_list)} account dal database\n")
        
        FORCE_DATE = False  # imposta a True solo per test forzati con data fissa

        for acc in account_list:
            retries = 0
            success = False
            result = None

            print(f"\n{'='*60}")
            print(f"Elaborazione: {acc['reseller']} - {acc['tipo_misura']}")
            print(f"{'='*60}")

            while retries < MAX_RETRIES and not success:
                try:
                    # Determina le date
                    if FORCE_DATE:
                        data_inizio = data_fine = datetime.strptime("14/05/2025", "%d/%m/%Y").date()
                    else:
                        data_inizio, data_fine = get_intervallo_date(
                            acc['id_reseller'], acc['id_grossista'], acc['tipo_misura']
                        )

                    print(f"[INFO] Intervallo date: {data_inizio} -> {data_fine}")

                    # Esecuzione del processo per l'account
                    result = await run(acc, data_inizio, data_fine)

                    # Invio email (sia in caso di successo che fallimento)
                    send_individual_email(acc, result)

                    if result['success']:
                        success = True
                        print(f"[SUCCESS] ✓ Completato con successo")
                    else:
                        retries += 1
                        print(f"[RETRY] Tentativo {retries}/{MAX_RETRIES} fallito")
                        
                except Exception as e:
                    retries += 1
                    print(f"[ERROR] Tentativo {retries}/{MAX_RETRIES} - {type(e).__name__}: {str(e)}")
                    
            if not success:
                print(f"[FAILURE] ✗ Tutti i tentativi falliti per {acc['reseller']} - {acc['tipo_misura']}")

        print("\n" + "=" * 60)
        print("ELABORAZIONE COMPLETATA")
        print("=" * 60)

    asyncio.run(main())
