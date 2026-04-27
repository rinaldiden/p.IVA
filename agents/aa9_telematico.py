"""
Generatore file telematico AA9/12 — Allegato B

Genera il file a record fissi (3503 caratteri/record) conforme
alle specifiche tecniche dell'Agenzia delle Entrate per l'invio
telematico della dichiarazione di inizio attivita.

Struttura: Record A (testata) + Record B (dati) + Record Z (coda)
Il file generato puo essere caricato su Fisconline tramite
"Invio documenti > Trasmissione file".

Fonte: Allegato B — Specifiche tecniche mod. AA9/12
"""

from datetime import date


RECORD_LEN = 3503  # lunghezza fissa per ogni record


def _pad_an(value: str, length: int) -> str:
    """Campo alfanumerico: allineato a sinistra, riempito con spazi."""
    return str(value).upper().ljust(length)[:length]


def _pad_nu(value, length: int) -> str:
    """Campo numerico: allineato a destra, riempito con zeri."""
    return str(value).rjust(length, '0')[:length]


def _data_ggmmaaaa(iso_date: str) -> str:
    """Converte YYYY-MM-DD in GGMMAAAA."""
    if not iso_date or len(iso_date) < 10:
        return '00000000'
    parts = iso_date.split('-')
    return parts[2] + parts[1] + parts[0]


def genera_record_a(cf_responsabile: str, data_prep: str = None) -> str:
    """Record di tipo A — testata della fornitura."""
    if data_prep is None:
        data_prep = date.today().isoformat()

    r = ' ' * RECORD_LEN  # inizializza a spazi
    r = list(r)

    # Campo 1: Tipo record (pos 1, len 1, AN)
    r[0] = 'A'

    # Campo 2: Filler (pos 2, len 6, NU) — zeri
    for i in range(1, 7):
        r[i] = '0'

    # Campo 3: Data preparazione file (pos 8, len 8, NU) — GGMMAAAA
    data = _data_ggmmaaaa(data_prep)
    for i, c in enumerate(data):
        r[7 + i] = c

    # Campo 4: Codice fornitura (pos 16, len 5, AN) — AT5VA per inizio attivita
    for i, c in enumerate('AT5VA'):
        r[15 + i] = c

    # Campo 5: Filler (pos 21, len 2, NU) — zeri
    r[20] = '0'
    r[21] = '0'

    # Campo 6: CF responsabile invio (pos 23, len 16, AN)
    cf = _pad_an(cf_responsabile, 16)
    for i, c in enumerate(cf):
        r[22 + i] = c

    # Campo 7: Filler (pos 39, len 591, AN) — spazi (gia fatto)

    # Campo 11: Filler di controllo (pos 3501, len 1, AN) — "F"
    r[3500] = 'F'

    # Campo 12: CR LF (pos 3502, len 2)
    r[3501] = '\r'
    r[3502] = '\n'

    return ''.join(r)


def genera_record_b(dati: dict) -> str:
    """
    Record di tipo B — dati della dichiarazione.

    dati = {
        'codice_fiscale': str,  # CF del titolare
        'tipo_dichiarazione': int,  # 1=inizio, 2=variazione
        'data_dichiarazione': str,  # YYYY-MM-DD
        'cognome_nome': str,  # "COGNOME NOME" o denominazione
        'codice_ateco': str,  # es. "620100"
        'volume_affari': int,  # 0 per forfettari
        'provincia_attivita': str,  # es. "SO"
        'cap_attivita': str,  # es. "23037"
        'comune_attivita': str,
        'indirizzo_attivita': str,
        'scritture_contabili_sede': int,  # 0 o 1
        'regime_agevolato': int,  # 0, 1, 2 (2=forfettario)
        'provincia_residenza': str,
        'cap_residenza': str,
        'comune_residenza': str,
        'indirizzo_residenza': str,
        'scritture_contabili_res': int,
        'data_nascita': str,  # YYYY-MM-DD
        'comune_nascita': str,
        'pec': str,
        'prefisso_tel': str,
        'numero_tel': str,
        'titolarita_immobile': str,  # P o D
        'tipo_catasto': str,  # F o T
        'tipologia_clientela': str,  # 1,2,3,4
        'luogo_pubblico': int,  # 0 o 1
        'investimenti_iniziali': str,  # 1,2,3,4
    }
    """
    r = [' '] * RECORD_LEN

    cf = dati['codice_fiscale'].upper()

    # Campo 1: Tipo record (pos 1) = "B"
    r[0] = 'B'

    # Campo 2: CF identificativo (pos 2, len 16)
    cf16 = _pad_an(cf, 16)
    for i, c in enumerate(cf16):
        r[1 + i] = c

    # Campo 3: Tipo soggetto (pos 18, len 1, NU) = 1 (mod. AA9)
    r[17] = '1'

    # === QUADRO A ===
    # Campo 4: Tipo dichiarazione (pos 19, len 1, NU) — 1=inizio
    r[18] = str(dati.get('tipo_dichiarazione', 1))

    # Campo 5: Data dichiarazione (pos 20, len 8, NU)
    data = _data_ggmmaaaa(dati.get('data_dichiarazione', date.today().isoformat()))
    for i, c in enumerate(data):
        r[19 + i] = c

    # Campo 6: CF titolare (pos 28, len 16, AN)
    for i, c in enumerate(cf16):
        r[27 + i] = c

    # Campo 7: Filler (pos 44, len 1, NU) = 0
    r[43] = '0'

    # Campo 8: Partita IVA (pos 45, len 11, NU) — vuoto per inizio
    for i in range(11):
        r[44 + i] = '0'

    # Campi 9-14: Filler vari
    r[55] = '0'  # campo 9
    r[56] = '0'  # campo 10
    for i in range(57, 65):
        r[i] = '0'  # campo 11
    for i in range(65, 68):
        r[i] = ' '  # campo 12
    for i in range(68, 77):
        r[i] = '0'  # campo 13
    for i in range(77, 79):
        r[i] = ' '  # campo 14

    # === QUADRO B ===
    # Campo 15: Denominazione/cognome e nome (pos 80, len 150, AN)
    den = _pad_an(dati.get('cognome_nome', ''), 150)
    for i, c in enumerate(den):
        r[79 + i] = c

    # Campi 16-22: Filler/soggetto non residente — spazi e zeri
    for i in range(229, 248):
        r[i] = ' '  # campo 16 (19 AN)
    for i in range(248, 253):
        r[i] = '0'  # campo 17 (5 NU)
    for i in range(253, 322):
        r[i] = ' '  # campo 18 (69 AN)
    r[322] = '0'  # campo 19
    for i in range(323, 353):
        r[i] = ' '  # campo 20 stato estero (30 AN)
    for i in range(353, 388):
        r[i] = ' '  # campo 21 indirizzo estero (35 AN)
    for i in range(388, 400):
        r[i] = ' '  # campo 22 num IVA estero (12 AN)

    # Campo 23: Codice attivita (pos 401, len 6, AN)
    ateco = _pad_an(dati.get('codice_ateco', '620100'), 6)
    for i, c in enumerate(ateco):
        r[400 + i] = c

    # Campo 24: Volume d'affari (pos 407, len 11, NU) — 0 per forfettari
    vol = _pad_nu(dati.get('volume_affari', 0), 11)
    for i, c in enumerate(vol):
        r[406 + i] = c

    # Campo 25: Acquisti intracomunitari (pos 418, len 1, NU) — 0
    r[417] = '0'

    # Campo 26: Provincia attivita (pos 419, len 2, AN)
    prov = _pad_an(dati.get('provincia_attivita', ''), 2)
    for i, c in enumerate(prov):
        r[418 + i] = c

    # Campo 27: CAP attivita (pos 421, len 5, NU)
    cap = _pad_nu(dati.get('cap_attivita', '00000'), 5)
    for i, c in enumerate(cap):
        r[420 + i] = c

    # Campo 28: Filler (pos 426, len 4, AN) — spazi
    for i in range(425, 429):
        r[i] = ' '

    # Campo 29: Comune attivita (pos 430, len 30, AN)
    comune = _pad_an(dati.get('comune_attivita', ''), 30)
    for i, c in enumerate(comune):
        r[429 + i] = c

    # Campo 30: Indirizzo attivita (pos 460, len 35, AN)
    ind = _pad_an(dati.get('indirizzo_attivita', ''), 35)
    for i, c in enumerate(ind):
        r[459 + i] = c

    # Campo 31: Scritture contabili sede (pos 495, len 1, NU) — 0
    r[494] = str(dati.get('scritture_contabili_sede', 0))

    # Campo 32: Regime fiscale agevolato (pos 496, len 1, NU) — 2=forfettario
    r[495] = str(dati.get('regime_agevolato', 2))

    # Campi 33-35: Filler
    r[496] = ' '  # campo 33
    r[497] = ' '  # campo 34
    r[498] = ' '  # campo 35

    # Campi 36-39: Sito web, ISP, cessazione commercio — spazi e zeri
    for i in range(499, 624):
        r[i] = ' '  # campo 36 sito web
    r[624] = '0'  # campo 37
    for i in range(625, 750):
        r[i] = ' '  # campo 38 ISP
    r[750] = '0'  # campo 39

    # === QUADRO C ===
    # Campo 40: Provincia residenza (pos 752, len 2, AN)
    prov_res = _pad_an(dati.get('provincia_residenza', ''), 2)
    for i, c in enumerate(prov_res):
        r[751 + i] = c

    # Campo 41: CAP residenza (pos 754, len 5, NU)
    cap_res = _pad_nu(dati.get('cap_residenza', '00000'), 5)
    for i, c in enumerate(cap_res):
        r[753 + i] = c

    # Campo 42: Filler (pos 759, len 4, AN) — spazi
    for i in range(758, 762):
        r[i] = ' '

    # Campo 43: Comune residenza (pos 763, len 30, AN)
    com_res = _pad_an(dati.get('comune_residenza', ''), 30)
    for i, c in enumerate(com_res):
        r[762 + i] = c

    # Campo 44: Indirizzo residenza (pos 793, len 35, AN)
    ind_res = _pad_an(dati.get('indirizzo_residenza', ''), 35)
    for i, c in enumerate(ind_res):
        r[792 + i] = c

    # Campo 45: Scritture contabili residenza (pos 828, len 1, NU) — 0
    r[827] = str(dati.get('scritture_contabili_res', 0))

    # === QUADRO D (Rappresentante) — vuoto ===
    r[828] = '0'  # campo 46: cessazione rappresentante
    for i in range(829, 845):
        r[i] = ' '  # campo 47: CF rappresentante
    for i in range(845, 847):
        r[i] = ' '  # campo 48: codice carica
    for i in range(847, 855):
        r[i] = '0'  # campo 49: data inizio procedimento
    for i in range(855, 866):
        r[i] = '0'  # campo 50: CF societa

    # === QUADRO E — vuoto ===
    for i in range(866, 868):
        r[i] = ' '  # campo 51
    for i in range(868, 946):
        r[i] = '0'  # campi 52-59

    # === Quadri compilati e firma ===
    # Campo 60: Quadri compilati (A) (pos 947)
    r[946] = 'A'  # campo 60: Quadro A compilato
    r[947] = 'B'  # campo 61: Quadro B compilato
    r[948] = 'C'  # campo 62: Quadro C compilato
    r[949] = ' '  # campo 63: Quadro D non compilato
    r[950] = ' '  # campo 64: Quadro E non compilato
    r[951] = ' '  # campo 65: Quadro F non compilato
    r[952] = ' '  # campo 66: Quadro G non compilato
    r[953] = ' '  # campo 67: Quadro H non compilato
    r[954] = 'I'  # campo 68: Quadro I compilato

    # Campo 69: Numero pagine (pos 956, len 3, NU)
    for i, c in enumerate(_pad_nu(4, 3)):
        r[955 + i] = c

    # Campo 70: Data presentazione (pos 959, len 8, NU)
    data_pres = _data_ggmmaaaa(date.today().isoformat())
    for i, c in enumerate(data_pres):
        r[958 + i] = c

    # Campo 71: CF dichiarante (pos 967, len 16, AN)
    for i, c in enumerate(cf16):
        r[966 + i] = c

    # Campi 72-76: Impegno intermediario — vuoto per invio diretto
    for i in range(982, 1028):
        r[i] = ' '  # vari filler

    # Campo 74: Impegno trasmissione (pos 1004, len 1, NU) — 1 (predisposta dal contribuente)
    r[1003] = '1'

    # Campo 75: Data impegno (pos 1005, len 8, NU)
    for i, c in enumerate(data_pres):
        r[1004 + i] = c

    # Campo 76: ID produttore SW (pos 1013, len 16, AN)
    sw = _pad_an('FISCALAI', 16)
    for i, c in enumerate(sw):
        r[1012 + i] = c

    # === QUADRO I ===
    # Campo 77: PEC (pos 1029, len 125, AN)
    pec = _pad_an(dati.get('pec', ''), 125)
    for i, c in enumerate(pec):
        r[1028 + i] = c

    # Campo 78: Prefisso tel (pos 1154, len 15, AN)
    pref = _pad_an(dati.get('prefisso_tel', ''), 15)
    for i, c in enumerate(pref):
        r[1153 + i] = c

    # Campo 79: Numero tel (pos 1169, len 20, AN)
    ntel = _pad_an(dati.get('numero_tel', ''), 20)
    for i, c in enumerate(ntel):
        r[1168 + i] = c

    # Campi 80-82: FAX e sito web — vuoto
    for i in range(1188, 1348):
        r[i] = ' '

    # Campo 83: Titolarita immobile (pos 1349, len 1, AN)
    r[1348] = dati.get('titolarita_immobile', 'P').upper()

    # Campo 84: Tipo catasto (pos 1350, len 1, AN)
    r[1349] = dati.get('tipo_catasto', 'F').upper()

    # Campi 85-93: Dati catastali — vuoto
    for i in range(1350, 1388):
        r[i] = ' '

    # Campi 94-95: Volumi intracomunitari — zeri
    for i in range(1388, 1410):
        r[i] = '0'

    # Campo 96: Tipologia clientela (pos 1411, len 1, AN)
    r[1410] = str(dati.get('tipologia_clientela', '1'))

    # Campo 97: Luogo aperto al pubblico (pos 1412, len 1, NU)
    r[1411] = str(dati.get('luogo_pubblico', 0))

    # Campo 98: Investimenti iniziali (pos 1413, len 1, AN)
    r[1412] = str(dati.get('investimenti_iniziali', '1'))

    # Campo 99: Filler (pos 1414, len 11, NU) — zeri
    for i in range(1413, 1424):
        r[i] = '0'

    # Campo 100: Filler (pos 1425, len 1476, AN) — spazi (gia a spazi)

    # Campi 101: Spazio produttore SW (pos 2901, len 600) — spazi

    # Ultimi 3 caratteri di controllo
    r[3500] = 'F'  # campo 102
    r[3501] = '\r'  # campo 103
    r[3502] = '\n'

    return ''.join(r)


def genera_record_z(cf: str, num_record_b: int = 1) -> str:
    """Record di tipo Z — coda della fornitura."""
    r = [' '] * RECORD_LEN

    r[0] = 'Z'

    # Filler (pos 2, len 14, AN) — spazi

    # Numero record B (pos 16, len 9, NU)
    n = _pad_nu(num_record_b, 9)
    for i, c in enumerate(n):
        r[15 + i] = c

    # Resto filler e controllo
    r[3500] = 'F'
    r[3501] = '\r'
    r[3502] = '\n'

    return ''.join(r)


def genera_file_telematico(dati: dict, output_path: str = None) -> str:
    """
    Genera il file telematico AA9/12 completo.

    dati: dict con i campi del contribuente (vedi genera_record_b)
    output_path: percorso file di output (opzionale)

    Ritorna il contenuto del file come stringa.
    """
    cf = dati['codice_fiscale'].upper()

    rec_a = genera_record_a(cf)
    rec_b = genera_record_b(dati)
    rec_z = genera_record_z(cf, 1)

    contenuto = rec_a + rec_b + rec_z

    if output_path:
        with open(output_path, 'w', encoding='ascii', errors='replace') as f:
            f.write(contenuto)

    return contenuto


if __name__ == '__main__':
    # Test con dati demo
    dati = {
        'codice_fiscale': 'RNLDNL91E03I829R',
        'tipo_dichiarazione': 1,
        'data_dichiarazione': '2026-04-27',
        'cognome_nome': 'RINALDI DANIELE',
        'codice_ateco': '620100',
        'volume_affari': 0,
        'provincia_attivita': 'SO',
        'cap_attivita': '23037',
        'comune_attivita': 'TIRANO',
        'indirizzo_attivita': 'VIA SAN CARLO 25',
        'scritture_contabili_sede': 0,
        'regime_agevolato': 2,
        'provincia_residenza': 'SO',
        'cap_residenza': '23037',
        'comune_residenza': 'TIRANO',
        'indirizzo_residenza': 'VIA SAN CARLO 25',
        'scritture_contabili_res': 0,
        'pec': 'DANIELE.RINALDI@PEC.IT',
        'prefisso_tel': '0342',
        'numero_tel': '3248845830',
        'titolarita_immobile': 'P',
        'tipo_catasto': 'F',
        'tipologia_clientela': '1',
        'luogo_pubblico': 0,
        'investimenti_iniziali': '1',
    }

    output = 'data/contribuente/AA9_12_telematico.txt'
    contenuto = genera_file_telematico(dati, output)

    print(f'File generato: {output}')
    print(f'Lunghezza totale: {len(contenuto)} caratteri')
    print(f'Record: {len(contenuto) // RECORD_LEN}')
    print(f'Lunghezza per record: {RECORD_LEN}')

    # Verifica
    records = contenuto.split('\r\n')
    for i, rec in enumerate(records):
        if rec:
            print(f'Record {i+1}: tipo={rec[0]}, len={len(rec)+2}')
