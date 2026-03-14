# Agent10 — NormativeWatcher

Monitora automaticamente le modifiche alla normativa fiscale italiana rilevante per il regime forfettario e aggiorna i parametri del sistema dalla data di efficacia della norma, non dalla data di pubblicazione.

## Principio fondamentale

Le norme fiscali italiane hanno spesso:
- **Data di pubblicazione** in Gazzetta Ufficiale
- **Data di entrata in vigore** (spesso 1° gennaio anno successivo)
- **Data di efficacia retroattiva** (rara ma esiste)

Agent10 distingue sempre queste tre date e aggiorna i parametri del sistema SOLO alla data di efficacia corretta.

## Fonti monitorate

| Fonte | Frequenza | Orario |
|-------|-----------|--------|
| Gazzetta Ufficiale (RSS) | Giornaliera | 06:00 |
| Agenzia delle Entrate | Giornaliera | 06:30 |
| INPS Circolari | Giornaliera | 07:00 |
| Normattiva (testi consolidati) | Settimanale (dom) | 03:00 |

## Parametri monitorati

- `shared/ateco_coefficients.json` — coefficienti redditività
- `shared/inps_rates.json` — aliquote INPS, contributi fissi, minimali/massimali
- `shared/tax_calendar.json` — scadenze fiscali
- `shared/forfettario_limits.json` — soglie ricavi, aliquote, durata agevolazione
- `shared/f24_tax_codes.json` — codici tributo

## Flusso

1. **Fetch** → filtra per keyword → scarta già processati
2. **Rilevanza** (Claude API) → il documento modifica parametri monitorati?
3. **Estrazione** (Claude API) → valori numerici precisi + data efficacia + certezza
4. **Diff** → confronta con valori attuali in shared/
5. **Schedule** → applica subito se già efficace, schedula se futuro
6. **Audit** → append-only in `audit/changes.jsonl`

## Regole di sicurezza

- **Certezza bassa** → NON applicare, metti in `normative_review_queue.jsonl`
- **Variazione anomala** (> 5% del valore precedente) → human review
- **Audit immutabile** → ogni modifica registrata, mai sovrascritta
- **Git auto-commit** (se `GIT_AUTO_COMMIT=true`) con messaggio tracciabile

## Evento Redis

Stream: `fiscalai:agent10:events`

Tipi:
- `normative_update_applied` — parametro aggiornato
- `review_needed` — cambio con certezza bassa, richiede review umana

## File

- `watcher.py` — orchestratore principale (7 step)
- `sources.py` — connettori GU, AdE, INPS, Normattiva
- `parser.py` — estrazione parametri via Claude API
- `diff_engine.py` — confronto nuovi vs attuali
- `updater.py` — applica modifiche a shared/, audit trail, git commit
- `scheduler.py` — schedule check periodici e aggiornamenti futuri
- `models.py` — NormativeUpdate, ParameterChange, SourceResult
- `redis_publisher.py` — eventi Redis
- `audit/changes.jsonl` — storico immutabile
