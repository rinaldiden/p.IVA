# Agent9 — Notifier

## Responsabilità
- Inviare SMS + email 7 giorni prima di ogni scadenza fiscale
- Notificare importo esatto da pagare
- Supportare tutti i canali configurati dall'utente in Agent0
- Recapitare alert da altri agenti (anomalie, soglie, divergenze calcolo, raccomandazioni)

## Input
- Scadenze e importi da Agent6
- Alert da Agent3b (divergenza calcoli)
- Alert da Agent4 (soglie ricavi con spiegazione conseguenze, marca da bollo, bollo virtuale)
- Raccomandazioni da Agent7
- Richieste di conferma utente da Agent5 (pre-invio dichiarazione) e Agent8 (pre-invio fattura, pre-pagamento F24)
- Alert errori da Agent8 (scarto SDI, fallimento pagamento PSD2)

## Output
- SMS inviati via Twilio
- Email inviate via SendGrid
- Push notification via app mobile
- Risposte di conferma/rifiuto utente verso Agent5 e Agent8
- Log di tutte le notifiche inviate nel Supervisor

## Integrazioni
- Twilio API — SMS
- SendGrid API — Email
- App mobile — Push notifications
- `agents/supervisor/` — Log notifiche
