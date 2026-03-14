# Agent9 — Notifier

## Responsabilità
- Inviare SMS + email 7 giorni prima di ogni scadenza fiscale
- Notificare importo esatto da pagare
- Supportare tutti i canali configurati dall'utente in Agent0
- Recapitare alert da tutti gli agenti del sistema

## Trigger di notifica

| Sorgente | Evento | Priorità | Azione |
|----------|--------|----------|--------|
| **Agent6** | Scadenza fiscale in arrivo (T-7 giorni) | Normale | SMS + email con importo esatto e codice tributo |
| **Agent8** | Scarto SDI fattura emessa (codice NS) | **Critica** | Alert immediato con codice errore + azione suggerita + deadline ri-emissione (5 giorni) |
| **Agent8** | Mancata consegna SDI (codice MC) | Alta | Alert con istruzioni: "Fattura disponibile nel cassetto fiscale del cliente, valuta invio PDF via email" |
| **Agent8** | Rifiuto committente PA (codice EC) | Alta | Alert con motivazione del rifiuto |
| **Agent1** | Scadenza consent PSD2 T-7 giorni | Normale | SMS + email con link diretto al re-consent |
| **Agent1** | Scadenza consent PSD2 T-3 giorni | Alta | SMS + email urgente con istruzioni rinnovo |
| **Agent1** | Consent PSD2 scaduto (T-0) | **Critica** | Alert: "Collegamento bancario scaduto — movimenti non aggiornati" |
| **Agent1** | Fattura ricevuta con dati anomali | Alta | Alert con dettaglio anomalia per revisione |
| **Agent3b** | Divergenza calcoli Agent3/Agent3b | **Critica** | Alert con blocco: "Calcolo fiscale bloccato — divergenza rilevata tra i due motori di calcolo. Dettaglio: [campo, valore A, valore B]" |
| **Agent4** | Soglia ricavi 70k | Informativa | "Stai crescendo bene — tieni d'occhio la soglia forfettario" |
| **Agent4** | Soglia ricavi 80k | Alta | "Ti avvicini alla soglia — valuta la pianificazione" |
| **Agent4** | Soglia ricavi 84k | **Critica** | "Considera di rinviare fatture a gennaio" |
| **Agent4** | Soglia ricavi 85k superata | **Critica** | "Esci dal forfettario dal 1° gennaio prossimo — Agent7 attivato" |
| **Agent5** | Errore trasmissione telematica | **Critica** | Alert immediato con codice errore + azione necessaria |
| **Agent7** | Raccomandazione fiscale | Informativa | Report con analisi e suggerimenti |
| **Vault** | Scadenza credenziali/certificati | Alta | Alert con istruzioni rinnovo |

## Priorità e canali

| Priorità | Canali | Retry |
|----------|--------|-------|
| Informativa | Email | No |
| Normale | Email + SMS | No |
| Alta | SMS + Email + Push | 1 retry dopo 24h se non letto |
| **Critica** | SMS + Email + Push (simultanei) | Retry ogni 4h fino a conferma lettura |

## Input
- Scadenze e importi da Agent6
- Esiti SDI da Agent8 (NS, MC, EC)
- Alert consent PSD2 da Agent1 (T-7, T-3, T-0)
- Fatture anomale da Agent1
- Alert da Agent3b (divergenza calcoli)
- Soglie ricavi da Agent4
- Errori trasmissione da Agent5
- Raccomandazioni da Agent7
- Scadenze credenziali dal Vault

## Output
- SMS inviati via Twilio
- Email inviate via SendGrid
- Push notification via app mobile
- Log di tutte le notifiche inviate nel Supervisor (con stato: inviata/letta/retry)

## Integrazioni
- Twilio API — SMS
- SendGrid API — Email
- App mobile — Push notifications
- `agents/supervisor/` — Log notifiche con stato
