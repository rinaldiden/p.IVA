# Vault — Auth Agent & Credential Manager

## Responsabilità
- **Custodire tutte le credenziali sensibili** in un vault dedicato (HashiCorp Vault / AWS KMS)
- Gestire credenziali firma digitale con sicurezza di livello HSM
- **Gestire sessioni SPID/CIE** per accesso al cassetto fiscale AdE e cassetto previdenziale INPS
- Effettuare login come client quando un agente ha bisogno di accedere a servizi autenticati
- Rinnovare sessioni scadute in modo trasparente
- Audit log di ogni accesso alle credenziali

## Credenziali gestite
```
vault://
├── firma-digitale/
│   └── {user-id}     → certificato + PIN firma digitale
├── spid/
│   └── {user-id}     → credenziali SPID (username + password + OTP seed)
├── psd2/
│   └── {user-id}     → consent token Open Banking
├── sdi/
│   └── {user-id}     → credenziali accesso SDI
└── intermediario/
    └── {user-id}     → credenziali deleghe intermediario abilitato
```

## Flusso di autenticazione
```
Agente (es. Agent1 vuole polling SDI)
  │
  ├──▶ Richiesta a Vault: "ho bisogno di accesso al cassetto fiscale"
  │
  Vault:
  ├── Recupera credenziali SPID dal vault
  ├── Effettua login (gestisce 2FA con OTP seed)
  ├── Ottiene session token
  ├── Restituisce session token all'agente richiedente
  └── Logga l'accesso nell'audit trail
  │
  Agente usa il session token per operare
```

## Sicurezza
- **Encryption at rest**: AES-256 per tutte le credenziali
- **Encryption in transit**: TLS 1.3 per ogni comunicazione
- **Access control**: ogni agente ha permessi specifici (Agent1 può accedere a SDI e PSD2, Agent5 può accedere a firma digitale, ecc.)
- **Rotation**: le credenziali vengono verificate e rinnovate prima della scadenza
- **Audit trail**: ogni accesso è loggato con timestamp, agente richiedente, risorsa acceduta
- **No plaintext**: le credenziali non transitano mai in chiaro fuori dal vault
- **HSM-backed**: le chiavi di firma digitale sono protette da HSM (Hardware Security Module) o equivalente cloud

## Policy di accesso per agente
| Agente | Risorse accessibili |
|--------|-------------------|
| Agent0 | Scrittura firma-digitale, spid, psd2 (onboarding) |
| Agent1 | Lettura sdi, psd2 |
| Agent5 | Lettura firma-digitale |
| Agent8 | Lettura sdi (per invio fatture) |
| Supervisor | Lettura/scrittura tutte le risorse |

## Input
- Richieste di autenticazione dagli agenti
- Credenziali iniziali da Agent0 (onboarding)
- Certificati e token da rinnovare

## Output
- Session token per accesso ai servizi
- Conferma operazioni di firma
- Alert scadenza credenziali
- Audit log completo

## Integrazioni
- HashiCorp Vault / AWS KMS / Azure Key Vault — storage sicuro
- HSM (cloud o on-premise) — protezione chiavi firma
- `agents/supervisor/` — audit trail e gestione scadenze
- `agents/agent9_notifier/` — alert scadenza credenziali

## Note
- Le credenziali SPID richiedono gestione del 2FA: il vault deve poter generare OTP se l'utente ha configurato un seed TOTP, oppure inoltrare la richiesta OTP via SMS all'utente
- La firma digitale remota (es. Aruba) richiede OTP per ogni firma: va gestito come per SPID
- Il vault è l'unico componente che tocca credenziali in chiaro — tutti gli altri agenti ricevono solo session token temporanei
