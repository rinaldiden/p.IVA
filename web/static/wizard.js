/* FiscalAI Wizard — step navigation, CF validation, real-time simulation */

(function() {
    'use strict';

    // ── STATE ────────────────────────────────
    let currentStep = 1;
    let totalSteps = 6;
    let wizardData = {};

    const STORAGE_KEY = 'fiscalai_wizard';

    // ── CF VALIDATION ────────────────────────
    const DISPARI = {
        '0':1,'1':0,'2':5,'3':7,'4':9,'5':13,'6':15,'7':17,'8':19,'9':21,
        'A':1,'B':0,'C':5,'D':7,'E':9,'F':13,'G':15,'H':17,'I':19,'J':21,
        'K':2,'L':4,'M':18,'N':20,'O':11,'P':3,'Q':6,'R':8,'S':12,'T':14,
        'U':16,'V':10,'W':22,'X':25,'Y':24,'Z':23
    };
    const PARI = {
        '0':0,'1':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
        'A':0,'B':1,'C':2,'D':3,'E':4,'F':5,'G':6,'H':7,'I':8,'J':9,
        'K':10,'L':11,'M':12,'N':13,'O':14,'P':15,'Q':16,'R':17,'S':18,
        'T':19,'U':20,'V':21,'W':22,'X':23,'Y':24,'Z':25
    };

    function validaCF(cf) {
        cf = cf.toUpperCase().trim();
        if (cf.length !== 16) return { valid: false, partial: cf.length < 16 };
        const re = /^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$/;
        if (!re.test(cf)) return { valid: false, partial: false };
        let sum = 0;
        for (let i = 0; i < 15; i++) {
            sum += (i % 2 === 0) ? (DISPARI[cf[i]] || 0) : (PARI[cf[i]] || 0);
        }
        const atteso = String.fromCharCode(65 + (sum % 26));
        return { valid: cf[15] === atteso, partial: false, expected: atteso };
    }

    // ── STEP NAVIGATION ──────────────────────

    function showStep(n) {
        document.querySelectorAll('.step').forEach(el => el.classList.remove('active'));
        const target = document.querySelector(`.step[data-step="${n}"]`);
        if (target) target.classList.add('active');

        currentStep = n;

        // Update progress
        const fill = document.querySelector('.progress-bar .fill');
        if (fill) fill.style.width = `${(n / totalSteps) * 100}%`;

        const stepText = document.querySelector('.step-text');
        if (stepText) stepText.textContent = `Step ${n} di ${totalSteps}`;

        const backBtn = document.querySelector('.wizard-progress .back');
        if (backBtn) {
            backBtn.classList.toggle('hidden', n === 1);
        }

        // Update next button state
        updateNextButton();

        // Scroll to top
        window.scrollTo(0, 0);

        saveState();
    }

    function nextStep() {
        if (!validateCurrentStep()) return;
        collectStepData();

        // Skip step 5 (rivalsa) if not gestione separata
        let next = currentStep + 1;
        if (next === 5 && wizardData.gestione !== 'separata') {
            next = 6;
        }

        if (next <= totalSteps) {
            showStep(next);
            if (next === 6) buildRiepilogo();
        }
    }

    function prevStep() {
        let prev = currentStep - 1;
        if (prev === 5 && wizardData.gestione !== 'separata') {
            prev = 4;
        }
        if (prev >= 1) showStep(prev);
    }

    // ── VALIDATION ───────────────────────────

    function validateCurrentStep() {
        switch (currentStep) {
            case 1: {
                const nome = val('w-nome');
                const cognome = val('w-cognome');
                const cf = val('w-cf');
                if (!nome || !cognome) return false;
                const cfResult = validaCF(cf);
                return cfResult.valid;
            }
            case 2:
                return !!wizardData.ateco;
            case 3:
                return wizardData.primo_anno !== undefined;
            case 4:
                return true; // slider always has value
            case 5:
                return true; // toggle always has value
            case 6:
                return true;
            default:
                return true;
        }
    }

    function updateNextButton() {
        const btn = document.getElementById('btn-next');
        if (!btn) return;
        btn.disabled = !validateCurrentStep();
    }

    function val(id) {
        const el = document.getElementById(id);
        return el ? el.value.trim() : '';
    }

    // ── COLLECT DATA ─────────────────────────

    function collectStepData() {
        switch (currentStep) {
            case 1:
                wizardData.nome = val('w-nome');
                wizardData.cognome = val('w-cognome');
                wizardData.cf = val('w-cf').toUpperCase();
                break;
            case 3:
                // already set by choice click
                break;
            case 4:
                wizardData.ricavi = parseInt(val('w-ricavi') || '30000');
                break;
            case 5: {
                const toggle = document.getElementById('w-rivalsa');
                wizardData.rivalsa = toggle ? toggle.checked : false;
                break;
            }
        }
    }

    // ── ATECO SUGGESTION ─────────────────────

    let atecoTimeout = null;

    function setupAtecoSearch() {
        const textarea = document.getElementById('w-attivita');
        if (!textarea) return;

        textarea.addEventListener('input', function() {
            clearTimeout(atecoTimeout);
            const text = this.value.trim();
            if (text.length < 10) {
                document.getElementById('ateco-suggestions').innerHTML = '';
                return;
            }
            atecoTimeout = setTimeout(() => fetchAtecoSuggestions(text), 800);
        });
    }

    function fetchAtecoSuggestions(query) {
        const container = document.getElementById('ateco-suggestions');
        container.innerHTML = '<p style="color:var(--text2);padding:8px 0;"><span class="spinner"></span> Sto cercando la categoria giusta...</p>';

        fetch(`/api/suggerisci-ateco?q=${encodeURIComponent(query)}`)
            .then(r => r.json())
            .then(data => {
                if (!data.length) {
                    container.innerHTML = '<p style="color:var(--text2);padding:8px 0;">Nessun risultato — prova a descrivere con altre parole</p>';
                    return;
                }
                container.innerHTML = data.map((s, i) => `
                    <div class="suggestion${wizardData.ateco === s.codice ? ' selected' : ''}"
                         onclick="window._selectAteco('${s.codice}', '${s.descrizione.replace(/'/g, "\\'")}', '${s.coefficiente}', '${s.gestione_inps || 'separata'}', this)">
                        <div class="sug-info">
                            <div class="sug-title">${s.descrizione}</div>
                            <div class="sug-desc">${s.motivazione || ''}</div>
                            <div class="sug-coeff">Coefficiente: ${Math.round(parseFloat(s.coefficiente) * 100)}% — su 1.000\u20AC incassati, il fisco ne considera ${Math.round(parseFloat(s.coefficiente) * 1000)}\u20AC come reddito</div>
                        </div>
                        <span class="sug-action">Scegli &rarr;</span>
                    </div>
                `).join('');
            })
            .catch(() => {
                // Fallback: show all ATECO from API
                fetch('/api/ateco')
                    .then(r => r.json())
                    .then(all => {
                        const q = query.toLowerCase();
                        const matches = Object.entries(all)
                            .filter(([k, v]) => v.description.toLowerCase().includes(q) || k.includes(q))
                            .slice(0, 5);
                        if (!matches.length) {
                            container.innerHTML = '<p style="color:var(--text2);padding:8px 0;">Nessun risultato trovato</p>';
                            return;
                        }
                        container.innerHTML = matches.map(([code, info]) => `
                            <div class="suggestion" onclick="window._selectAteco('${code}', '${info.description.replace(/'/g, "\\'")}', '${info.coefficient}', '${info.gestione_inps || 'separata'}', this)">
                                <div class="sug-info">
                                    <div class="sug-title">${info.description}</div>
                                    <div class="sug-coeff">Codice: ${code} — Coefficiente: ${Math.round(parseFloat(info.coefficient) * 100)}%</div>
                                </div>
                                <span class="sug-action">Scegli &rarr;</span>
                            </div>
                        `).join('');
                    });
            });
    }

    window._selectAteco = function(codice, desc, coeff, gestione, el) {
        wizardData.ateco = codice;
        wizardData.ateco_desc = desc;
        wizardData.ateco_coeff = coeff;
        wizardData.gestione = gestione || 'separata';
        document.querySelectorAll('#ateco-suggestions .suggestion').forEach(s => s.classList.remove('selected'));
        el.classList.add('selected');

        // Show gestione info
        const gestioneBox = document.getElementById('gestione-info');
        if (gestioneBox) {
            const labels = {
                'separata': { icon: '\uD83D\uDCBC', title: 'Gestione Separata INPS', desc: 'Paghi i contributi in percentuale su quello che guadagni. Se guadagni zero, paghi zero.' },
                'artigiani': { icon: '\uD83D\uDD27', title: 'Gestione Artigiani INPS', desc: 'Hai contributi fissi trimestrali (~4.200\u20AC/anno) da versare ogni 3 mesi, anche se non fatturi.' },
                'commercianti': { icon: '\uD83D\uDED2', title: 'Gestione Commercianti INPS', desc: 'Hai contributi fissi trimestrali (~4.200\u20AC/anno) da versare ogni 3 mesi, anche se non fatturi.' },
            };
            const g = labels[wizardData.gestione] || labels['separata'];
            const isFixed = wizardData.gestione !== 'separata';
            gestioneBox.innerHTML = `
                <div class="info-box ${isFixed ? 'yellow' : 'green'}" style="margin-top:16px;">
                    <p style="font-weight:600;margin-bottom:4px;">${g.icon} ${g.title}</p>
                    <p>${g.desc}</p>
                    <p style="margin-top:8px;font-size:13px;color:var(--text2);">La gestione INPS dipende dal tipo di attivita — non si sceglie.</p>
                </div>
            `;
            gestioneBox.style.display = 'block';
        }

        updateNextButton();
    };

    // ── SHOW ALL ATECO ───────────────────────

    window._showAllAteco = function() {
        const container = document.getElementById('ateco-suggestions');
        container.innerHTML = '<p style="color:var(--text2);padding:8px 0;"><span class="spinner"></span> Caricamento...</p>';

        fetch('/api/ateco')
            .then(r => r.json())
            .then(all => {
                container.innerHTML = Object.entries(all).map(([code, info]) => `
                    <div class="suggestion" onclick="window._selectAteco('${code}', '${info.description.replace(/'/g, "\\'")}', '${info.coefficient}', '${info.gestione_inps || 'separata'}', this)">
                        <div class="sug-info">
                            <div class="sug-title">${info.description}</div>
                            <div class="sug-coeff">Codice: ${code} — Coefficiente: ${Math.round(parseFloat(info.coefficient) * 100)}%</div>
                        </div>
                        <span class="sug-action">Scegli &rarr;</span>
                    </div>
                `).join('');
            });
    };

    // ── PRIMO ANNO CHOICE ────────────────────

    window._setPrimoAnno = function(value, el) {
        wizardData.primo_anno = value;
        document.querySelectorAll('#step3-choices .choice').forEach(c => c.classList.remove('selected'));
        el.classList.add('selected');

        const box = document.getElementById('primo-anno-info');
        if (box) box.style.display = value ? 'block' : 'none';

        updateNextButton();
    };

    // ── SLIDER SIMULATION ────────────────────

    let simTimeout = null;

    function setupSlider() {
        const slider = document.getElementById('w-ricavi');
        const display = document.getElementById('ricavi-display');
        const input = document.getElementById('w-ricavi-input');
        if (!slider) return;

        function sync(value) {
            const v = parseInt(value);
            if (display) display.textContent = v.toLocaleString('it-IT');
            if (slider.value != v) slider.value = v;
            if (input && input.value != v) input.value = v;
            wizardData.ricavi = v;

            clearTimeout(simTimeout);
            simTimeout = setTimeout(() => fetchSimulation(v), 300);
        }

        slider.addEventListener('input', () => sync(slider.value));
        if (input) {
            input.addEventListener('input', () => {
                const v = parseInt(input.value) || 0;
                sync(Math.min(85000, Math.max(5000, v)));
            });
        }

        // Initial
        sync(slider.value);
    }

    function getSpeseTotali() {
        let totale = 0;
        document.querySelectorAll('.spesa-input').forEach(input => {
            totale += parseInt(input.value) || 0;
        });
        return totale;
    }

    function fetchSimulation(ricavi) {
        const container = document.getElementById('sim-preview');
        if (!container) return;

        const ateco = wizardData.ateco || '62.01.00';
        const primo = wizardData.primo_anno !== undefined ? wizardData.primo_anno : true;
        const gestione = wizardData.gestione || 'separata';

        fetch(`/api/simula?ricavi=${ricavi}&ateco=${encodeURIComponent(ateco)}&primo_anno=${primo}&gestione=${gestione}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    container.innerHTML = `<p style="color:var(--error);">${data.error}</p>`;
                    return;
                }

                const imposta = parseFloat(data.imposta_sostitutiva);
                const inps = parseFloat(data.contributo_inps);
                const totale = imposta + inps;
                const mensile = parseFloat(data.rata_mensile);

                // Store simulation data for riepilogo
                wizardData._lastSim = data;

                let html = `
                    <div class="preview-box">
                        <div style="font-weight:600;margin-bottom:12px;">Situazione fiscale</div>
                        <div class="row">
                            <span class="label">Fatturato stimato</span>
                            <span class="value">${fmt(ricavi)}</span>
                        </div>
                        <div class="row">
                            <span class="label">Tasse (imposta sostitutiva)</span>
                            <span class="value">${fmt(imposta)}</span>
                        </div>
                        <div class="row">
                            <span class="label">Contributi INPS</span>
                            <span class="value">${fmt(inps)}</span>
                        </div>
                        <hr class="divider">
                        <div class="row highlight">
                            <span class="label">Da accantonare</span>
                            <span class="value">${fmt(mensile)}/mese</span>
                        </div>
                    </div>
                `;

                if (primo) {
                    html += '<div class="info-box green">Primo anno: nessun acconto da versare! Paghi tutto l\'anno prossimo.</div>';
                }
                if (ricavi > 70000) {
                    html += '<div class="info-box yellow">Attenzione: sopra 85.000\u20AC esci dal regime forfettario. Tieni d\'occhio il fatturato.</div>';
                }

                container.innerHTML = html;

                // Update spese netto preview if visible
                updateSpesePreview(ricavi, totale);
            })
            .catch(() => {
                container.innerHTML = '<p style="color:var(--text2);">Calcolo non disponibile</p>';
            });
    }

    function updateSpesePreview(ricavi, tasseInps) {
        const box = document.getElementById('spese-netto-preview');
        if (!box) return;
        const speseToggle = document.getElementById('w-spese-toggle');
        if (!speseToggle || !speseToggle.checked) { box.innerHTML = ''; return; }

        if (!ricavi) ricavi = wizardData.ricavi || 30000;
        if (!tasseInps) {
            const sim = wizardData._lastSim;
            if (sim) tasseInps = parseFloat(sim.imposta_sostitutiva) + parseFloat(sim.contributo_inps);
            else tasseInps = 0;
        }

        const spese = getSpeseTotali();
        wizardData.spese_totali = spese;
        const netto = ricavi - tasseInps - spese;
        const nettoMese = Math.round(netto / 12);

        box.innerHTML = `
            <div class="preview-box" style="margin-top:16px;background:var(--success-light);">
                <div style="font-weight:600;margin-bottom:12px;">Quello che ti resta davvero</div>
                <div class="row"><span class="label">Fatturato stimato</span><span class="value">${fmt(ricavi)}</span></div>
                <div class="row"><span class="label">Tasse + INPS</span><span class="value" style="color:var(--error);">-${fmt(tasseInps)}</span></div>
                <div class="row"><span class="label">Le tue spese di lavoro</span><span class="value" style="color:var(--error);">-${fmt(spese)}</span></div>
                <hr class="divider">
                <div class="row highlight"><span class="label">Netto reale</span><span class="value" style="color:var(--success);">${fmt(netto)}/anno</span></div>
                <div class="row highlight"><span class="label"></span><span class="value" style="color:var(--success);">${fmt(nettoMese)}/mese</span></div>
            </div>
        `;
    }

    function fmt(n) {
        return Math.round(n).toLocaleString('it-IT') + ' \u20AC';
    }

    // ── RIEPILOGO (Step 6) ───────────────────

    function buildRiepilogo() {
        collectStepData();
        const container = document.getElementById('riepilogo-content');
        if (!container) return;

        const ateco = wizardData.ateco_desc || wizardData.ateco || '';
        const ricavi = wizardData.ricavi || 30000;
        const primo = wizardData.primo_anno;
        const nome = wizardData.nome || '';
        const gestione = wizardData.gestione || 'separata';
        const spese = wizardData.spese_totali || 0;

        fetch(`/api/simula?ricavi=${ricavi}&ateco=${encodeURIComponent(wizardData.ateco || '62.01.00')}&primo_anno=${primo}&gestione=${gestione}`)
            .then(r => r.json())
            .then(data => {
                const imposta = parseFloat(data.imposta_sostitutiva || 0);
                const inps = parseFloat(data.contributo_inps || 0);
                const totale = imposta + inps;
                const mensile = parseFloat(data.rata_mensile || 0);
                const aliquota = data.aliquota ? Math.round(parseFloat(data.aliquota) * 100) : (primo ? 5 : 15);

                let speseHtml = '';
                if (spese > 0) {
                    const netto = ricavi - totale - spese;
                    const nettoMese = Math.round(netto / 12);
                    speseHtml = `
                        <h3>Quello che ti resta davvero</h3>
                        <div class="preview-box" style="margin:8px 0 16px;background:var(--success-light);">
                            <div class="row"><span class="label">Fatturato</span><span class="value">${fmt(ricavi)}</span></div>
                            <div class="row"><span class="label">Tasse + INPS</span><span class="value" style="color:var(--error);">-${fmt(totale)}</span></div>
                            <div class="row"><span class="label">Spese stimate</span><span class="value" style="color:var(--error);">-${fmt(spese)}</span></div>
                            <hr class="divider">
                            <div class="row highlight"><span class="label">Netto reale</span><span class="value" style="color:var(--success);">${fmt(nettoMese)}/mese</span></div>
                        </div>
                    `;
                } else {
                    speseHtml = `
                        <div class="info-box blue" style="margin-top:16px;">
                            <p style="font-weight:600;">Vuoi sapere quanto ti resta davvero?</p>
                            <p>Nella dashboard potrai inserire le tue spese abituali per calcolare il netto reale ogni mese.</p>
                        </div>
                    `;
                }

                container.innerHTML = `
                    <div class="riepilogo">
                        <p style="font-size:17px;">Ciao <strong>${nome}</strong>!</p>
                        <p style="color:var(--text2);margin-top:4px;">Con <strong>${ateco}</strong> e un fatturato di <strong>${ricavi.toLocaleString('it-IT')} \u20AC</strong>:</p>

                        <h3>La tua situazione fiscale</h3>
                        <div class="preview-box" style="margin:8px 0 16px;">
                            <div class="row"><span class="label">Fatturato stimato</span><span class="value">${fmt(ricavi)}</span></div>
                            <div class="row"><span class="label">Tasse (aliquota ${aliquota}%)</span><span class="value">${fmt(imposta)}</span></div>
                            <div class="row"><span class="label">Contributi INPS</span><span class="value">${fmt(inps)}</span></div>
                            <hr class="divider">
                            <div class="row highlight"><span class="label">Da accantonare</span><span class="value">${fmt(mensile)}/mese</span></div>
                        </div>

                        ${speseHtml}

                        ${data.scadenze && data.scadenze.length ? `
                        <h3>Le tue scadenze</h3>
                        <ul>${data.scadenze.map(s => `<li>${s.data} — ${s.descrizione}: <strong>${s.importo}</strong></li>`).join('')}</ul>
                        ` : ''}

                        <h3>Cosa devi fare</h3>
                        <ul>
                            <li>Emetti fattura ogni volta che incassi</li>
                            <li>Metti da parte <strong>${fmt(mensile)}</strong> ogni mese</li>
                            <li>Noi ti avvisiamo prima di ogni scadenza</li>
                        </ul>

                        <h3>Cosa NON devi fare</h3>
                        <ul>
                            <li>Non devi registrare le spese (regime forfettario)</li>
                            <li>Non devi fare la liquidazione IVA</li>
                            <li>Non devi tenere registri contabili</li>
                        </ul>
                    </div>
                `;
            })
            .catch(() => {
                container.innerHTML = '<p style="color:var(--text2);">Riepilogo non disponibile</p>';
            });
    }

    // ── SAVE / SUBMIT ────────────────────────

    window._submitWizard = function() {
        collectStepData();
        const form = document.getElementById('wizard-form');
        if (!form) return;

        // Fill hidden fields
        setHidden('h-nome', wizardData.nome);
        setHidden('h-cognome', wizardData.cognome);
        setHidden('h-cf', wizardData.cf);
        setHidden('h-ateco', wizardData.ateco);
        setHidden('h-primo-anno', wizardData.primo_anno ? '1' : '0');
        setHidden('h-ricavi', wizardData.ricavi);
        setHidden('h-gestione', wizardData.gestione || 'separata');
        // gestione is auto-determined from ATECO code, not user choice
        setHidden('h-rivalsa', wizardData.rivalsa ? '1' : '0');

        localStorage.removeItem(STORAGE_KEY);
        form.submit();
    };

    window._saveAndExit = function() {
        collectStepData();
        saveState();
        window.location.href = '/';
    };

    function setHidden(id, value) {
        const el = document.getElementById(id);
        if (el) el.value = value || '';
    }

    // ── PERSISTENCE ──────────────────────────

    function saveState() {
        wizardData._step = currentStep;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(wizardData));
    }

    function loadState() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                wizardData = JSON.parse(saved);
                if (wizardData._step) {
                    // Restore form fields
                    if (wizardData.nome) setVal('w-nome', wizardData.nome);
                    if (wizardData.cognome) setVal('w-cognome', wizardData.cognome);
                    if (wizardData.cf) setVal('w-cf', wizardData.cf);
                    if (wizardData.ricavi) setVal('w-ricavi', wizardData.ricavi);
                    return wizardData._step;
                }
            }
        } catch (e) {}
        return 1;
    }

    function setVal(id, value) {
        const el = document.getElementById(id);
        if (el) el.value = value;
    }

    // ── CF INPUT HANDLER ─────────────────────

    function setupCFValidation() {
        const input = document.getElementById('w-cf');
        if (!input) return;

        input.addEventListener('input', function() {
            this.value = this.value.toUpperCase();
            const result = validaCF(this.value);
            const hint = document.getElementById('cf-hint');

            if (this.value.length === 0) {
                this.className = '';
                if (hint) hint.innerHTML = '<span class="hint">Lo trovi sulla tessera sanitaria</span>';
            } else if (result.partial) {
                this.className = '';
                if (hint) hint.innerHTML = '<span class="hint">Lo trovi sulla tessera sanitaria</span>';
            } else if (result.valid) {
                this.className = 'valid';
                if (hint) hint.innerHTML = '<span class="hint success">&#10003; Codice fiscale valido</span>';
            } else {
                this.className = 'invalid';
                if (hint) hint.innerHTML = '<span class="hint error">&#10007; Codice fiscale non valido — controlla la tessera sanitaria</span>';
            }

            updateNextButton();
        });
    }

    // ── TOGGLE HANDLER ───────────────────────

    function setupToggle() {
        const toggle = document.getElementById('w-rivalsa');
        if (!toggle) return;

        const labelNo = document.getElementById('toggle-no');
        const labelSi = document.getElementById('toggle-si');

        function update() {
            if (labelNo) labelNo.classList.toggle('active', !toggle.checked);
            if (labelSi) labelSi.classList.toggle('active', toggle.checked);
            wizardData.rivalsa = toggle.checked;
        }

        toggle.addEventListener('change', update);
        update();
    }

    // ── APERTURA PAGE ────────────────────────

    window._runApertura = function() {
        const steps = document.querySelectorAll('.apertura-step .icon');
        const descs = document.querySelectorAll('.apertura-step .desc');
        const messages = [
            'Stai facendo la cosa giusta...',
            'Zero burocrazia da oggi...',
            'Tra pochi secondi sei operativo...',
            'Un passo alla volta...',
        ];
        let msgIndex = 0;
        const rotText = document.getElementById('rotating-text');
        const pid = document.getElementById('apertura-pid')?.value;

        function setStep(i, state) {
            if (steps[i]) {
                steps[i].classList.remove('active', 'done');
                steps[i].classList.add(state);
                steps[i].textContent = state === 'done' ? '✓' : '⏳';
            }
        }

        const msgInterval = setInterval(() => {
            msgIndex = (msgIndex + 1) % messages.length;
            if (rotText) rotText.textContent = messages[msgIndex];
        }, 2000);

        setStep(0, 'active');
        setTimeout(() => { setStep(0, 'done'); setStep(1, 'active'); }, 1500);
        setTimeout(() => { setStep(1, 'done'); setStep(2, 'active'); }, 3000);
        setTimeout(() => {
            setStep(2, 'done');
            clearInterval(msgInterval);
            if (rotText) rotText.textContent = 'Tutto pronto!';
            setTimeout(() => { window.location.href = '/dashboard/' + pid; }, 800);
        }, 4500);
    };

    // ── FATTURA LINE ITEMS ───────────────────

    window._addLine = function() {
        const container = document.getElementById('linee-container');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'line-item';
        div.innerHTML = `
            <div class="form-group"><input type="text" name="linea_desc" required placeholder="Descrizione prestazione"></div>
            <div class="form-group"><input type="text" name="linea_qty" value="1" placeholder="1"></div>
            <div class="form-group"><input type="text" name="linea_prezzo" required placeholder="0.00"></div>
        `;
        container.appendChild(div);
    };

    // ── SPESE TOGGLE ────────────────────────

    function setupSpeseToggle() {
        const toggle = document.getElementById('w-spese-toggle');
        const section = document.getElementById('spese-section');
        if (!toggle || !section) return;

        toggle.addEventListener('change', function() {
            section.style.display = this.checked ? 'block' : 'none';
            if (this.checked) updateSpesePreview();
        });

        // Listen to expense input changes
        document.querySelectorAll('.spesa-input').forEach(input => {
            input.addEventListener('input', () => updateSpesePreview());
        });
    }

    // ── INIT ─────────────────────────────────

    document.addEventListener('DOMContentLoaded', function() {
        // Wizard page
        if (document.querySelector('.step')) {
            const startStep = loadState();
            showStep(startStep);
            setupCFValidation();
            setupAtecoSearch();
            setupSlider();
            setupToggle();
            setupSpeseToggle();

            // Global next/prev
            const btnNext = document.getElementById('btn-next');
            if (btnNext) btnNext.addEventListener('click', nextStep);
            const btnBack = document.querySelector('.wizard-progress .back');
            if (btnBack) btnBack.addEventListener('click', prevStep);

            // Revalidate on any input
            document.querySelectorAll('input, textarea, select').forEach(el => {
                el.addEventListener('input', updateNextButton);
            });
        }

        // Apertura page
        if (document.getElementById('apertura-pid')) {
            window._runApertura();
        }
    });
})();
