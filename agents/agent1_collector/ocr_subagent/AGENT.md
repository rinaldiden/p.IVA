# OCR Subagent

## Responsabilità
- Ricevere foto di scontrini e ricevute da tutti i canali configurati
- Estrarre dati strutturati: importo, data, fornitore, categoria
- Archiviare documento originale e dati estratti

## Input
- Immagini di scontrini/ricevute (JPEG, PNG, PDF)
- Fonte: app mobile, WhatsApp, email, upload web

## Output
- Record strutturato: importo, data, fornitore, categoria, confidence score
- Documento originale archiviato

## Integrazioni
- Claude Vision API per OCR primario
- Tesseract come fallback
