# OCR Subagent

## Responsabilità
- Ricevere foto di scontrini e ricevute dai canali configurati
- Estrarre dati strutturati: importo, data, fornitore, categoria
- Archiviare documento originale e dati estratti

## Input
- Immagini di scontrini/ricevute (JPEG, PNG, PDF)
- Fonte: app mobile, email, Google Drive, Google Foto

## Output
- Record strutturato: importo, data, fornitore, categoria, confidence score
- Documento originale archiviato

## Integrazioni
- Claude Vision API per OCR primario
- Tesseract come fallback
- Google Drive API / Google Photos API per recupero immagini

## Note
- Nessun transito dati su piattaforme terze non GDPR-compliant
- I dati restano su infrastruttura EU
