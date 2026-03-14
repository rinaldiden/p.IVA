# Agent9 — Notifier

## Responsabilità
- Inviare SMS + email 7 giorni prima di ogni scadenza fiscale
- Notificare importo esatto da pagare
- Supportare tutti i canali configurati dall'utente in Agent0
- Recapitare alert da altri agenti (anomalie, soglie, divergenze calcolo, raccomandazioni)

## Input
- Scadenze e importi da Agent6
- Alert da Agent3b (divergenza calcoli)
- Alert da Agent4 (soglie ricavi con spiegazione conseguenze)
- Raccomandazioni da Agent7

## Output
- SMS inviati via Twilio
- Email inviate via SendGrid
- Push notification via app mobile
- Log di tutte le notifiche inviate nel Supervisor

## Integrazioni
- Twilio API — SMS
- SendGrid API — Email
- App mobile — Push notifications
- `agents/supervisor/` — Log notifiche
