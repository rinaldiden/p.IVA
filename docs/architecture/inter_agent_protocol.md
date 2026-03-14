# Protocollo Inter-Agente — Decision Log

## Decisione: Redis Streams come message bus

**Data**: 2026-03-14
**Stato**: Approvata

### Motivazione
- Già presente nello stack (docker-compose) — nessuna dipendenza aggiuntiva
- Gestisce nativamente i casi di fallimento (Agent3b che blocca il flusso)
- Consumer groups per garantire exactly-once processing
- Persistenza dei messaggi per audit trail
- Bassa latenza, alta throughput
- Supporta replay dei messaggi per debug e recovery

### Pattern di comunicazione

Ogni agente pubblica eventi su stream Redis dedicati:

```
fiscalai:agent0:onboarding_completed
fiscalai:agent1:documents_collected
fiscalai:agent2:categorization_done
fiscalai:agent3:calculation_done
fiscalai:agent3b:validation_result
fiscalai:agent4:compliance_check
fiscalai:agent5:declaration_ready
fiscalai:agent6:payment_scheduled
fiscalai:agent8:invoice_sent
fiscalai:agent8:sdi_outcome_received
fiscalai:agent9:notification_sent
fiscalai:supervisor:profile_updated
```

### Formato messaggio standard

Ogni messaggio pubblicato sugli stream ha questa struttura:

```json
{
  "event_id": "uuid-v4",
  "timestamp": "2026-03-14T10:30:00Z",
  "agent_id": "agent3_calculator",
  "contribuente_id": "uuid-v4",
  "event_type": "calculation_done",
  "payload": {
    "reddito_imponibile": 23450.00,
    "imposta_dovuta": 1172.50,
    "dettaglio": {}
  },
  "correlation_id": "uuid-v4"
}
```

Campi:
- `event_id`: identificativo univoco dell'evento
- `timestamp`: ISO 8601 UTC
- `agent_id`: agente che ha pubblicato l'evento
- `contribuente_id`: a quale contribuente si riferisce
- `event_type`: tipo di evento (usato per routing)
- `payload`: dati specifici dell'evento (schema varia per tipo)
- `correlation_id`: stesso UUID per tutta la catena di eventi di un ciclo fiscale — permette di tracciare il flusso end-to-end

### Consumer groups

Ogni agente downstream è un consumer group Redis:

```
Stream: fiscalai:agent1:documents_collected
  └── Consumer group: agent2_categorizer (exactly-once)

Stream: fiscalai:agent2:categorization_done
  └── Consumer group: agent3_calculator (exactly-once)

Stream: fiscalai:agent3:calculation_done
  └── Consumer group: agent3b_validator (exactly-once)

Stream: fiscalai:agent3b:validation_result
  ├── Consumer group: agent6_scheduler (se validation_ok=true)
  └── Consumer group: agent9_notifier (se validation_ok=false → alert)

Stream: fiscalai:agent8:invoice_sent
  ├── Consumer group: agent2_categorizer (classificazione ricavo)
  └── Consumer group: agent1_collector (conservazione sostitutiva)

Stream: fiscalai:agent8:sdi_outcome_received
  └── Consumer group: agent9_notifier (alert se MC/NS/EC rifiutato)
```

### Regola blocco Agent3b

Quando Agent3b pubblica `validation_result` con `blocco: true`:

1. Il Supervisor legge l'evento e aggiorna lo stato del contribuente a `BLOCKED`
2. **Nessun agente downstream** (Agent5, Agent6) processa eventi con quel `contribuente_id` fino a risoluzione
3. Agent9 invia notifica critica con dettaglio divergenza
4. Il blocco viene rimosso solo quando:
   - Il bug viene identificato e corretto in Agent3 o Agent3b
   - Un nuovo `validation_result` con `blocco: false` viene pubblicato
   - Il Supervisor aggiorna lo stato a `ACTIVE`

```
Agent3b pubblica:
{
  "event_type": "validation_result",
  "payload": {
    "blocco": true,
    "divergenze": [
      {
        "campo": "imposta_sostitutiva",
        "agent3_value": 1172.50,
        "agent3b_value": 1173.00,
        "delta": 0.50
      }
    ]
  }
}

→ Supervisor: stato = BLOCKED
→ Agent9: notifica critica
→ Agent5, Agent6: ignorano eventi per questo contribuente_id
```

### Chiamate sincrone (eccezioni al bus)

Due componenti NON usano il message bus e vengono chiamati in modo sincrono diretto:

1. **Vault**: sempre chiamata diretta sincrona — le credenziali servono immediatamente e non devono transitare su stream persistenti per motivi di sicurezza
2. **Agent3 → Agent3b**: chiamata diretta sincrona — la validazione è bloccante, Agent3 aspetta il risultato di Agent3b prima di pubblicare qualsiasi evento

### Retry e dead letter

- Se un consumer fallisce nel processare un messaggio, Redis Streams gestisce il `XACK` mancante
- Dopo 3 tentativi falliti, il messaggio viene spostato in uno stream dead-letter: `fiscalai:dead_letter`
- Agent9 viene notificato di ogni messaggio in dead-letter
- Il Supervisor logga il fallimento nell'audit trail
