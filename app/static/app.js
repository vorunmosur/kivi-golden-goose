const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>'"]/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
}[c]));

document.querySelectorAll('.tab').forEach(button => {
    button.onclick = () => {
        document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));

        button.classList.add('active');
        $('#' + button.dataset.tab).classList.add('active');

        if (button.dataset.tab === 'memory') loadMemories();
        if (button.dataset.tab === 'trace') loadTrace();
    };
});

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json();

    if (!response.ok) {
        throw Error(data.detail || 'Something went wrong.');
    }

    return data;
}

function options(body, method = 'POST') {
    return {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    };
}

$('#dictationExample').onclick = () => {
    $('#app').value = 'Slack';
    $('#style').value = 'work messaging';
    $('#raw').value = 'rajeevs my manager';
    $('#formatted').value = 'Rajeev is my manager.';
    $('#raw').focus();
};

document.querySelectorAll('.chip').forEach(chip => {
    chip.onclick = () => {
        $('#query').value = chip.dataset.query;
        $('#query').focus();
    };
});

$('#ingestBtn').onclick = async () => {
    const button = $('#ingestBtn');
    button.disabled = true;
    button.textContent = 'Kivi is learning…';

    $('#learnResult').className = '';
    $('#learnResult').innerHTML = `
    <div class="empty-state">
      <strong>Kivi is deciding what matters…</strong>
      <span>Interpreting the interaction and checking existing memory.</span>
    </div>
  `;

    try {
        const data = await request('/api/interactions', options({
            raw_asr: $('#raw').value,
            formatted_text: $('#formatted').value,
            app_context: $('#app').value,
            style_context: $('#style').value,
            hide_mode: $('#hide').checked,
            session_id: 'replay-' + Date.now()
        }));

        if (!data.actions.length) {
            $('#learnResult').innerHTML = `
        <div class="decision-item">
          <strong>Not remembered</strong>
          <span class="muted">Kivi found no durable information worth storing.</span>
        </div>
      `;
            return;
        }

        $('#learnResult').innerHTML = data.actions.map(action => `
      <div class="decision-item">
        <span class="section-kicker">${esc(actionLabel(action.action))}</span>
        <strong>${esc(actionHeadline(action))}</strong>
        <span class="muted">${esc(action.reason)}</span>
      </div>
    `).join('');

    } catch (error) {
        $('#learnResult').innerHTML = `
      <div class="decision-item">
        <strong>Couldn't process this dictation.</strong>
        <span class="muted">${esc(error.message)}</span>
      </div>
    `;
    } finally {
        button.disabled = false;
        button.textContent = 'Process dictation';
    }
};

$('#askBtn').onclick = async () => {
    const button = $('#askBtn');
    button.disabled = true;
    button.textContent = 'Kivi is thinking…';

    $('#askResult').className = '';
    $('#askResult').innerHTML = `
    <div class="empty-state">
      <strong>Looking through your history…</strong>
      <span>Kivi will answer only from evidence it can support.</span>
    </div>
  `;

    try {
        const data = await request('/api/hey-kivi', options({
            query: $('#query').value,
            session_id: 'fresh-' + Date.now()
        }));

        const memories = data.memories || [];
        const history = data.history_evidence || [];

        $('#askResult').innerHTML = `
      <p class="answer-main">${esc(data.response)}</p>

      <div class="evidence">
        <strong>
          ${memories.length || history.length
                ? `Grounded in ${memories.length + history.length} piece${memories.length + history.length === 1 ? '' : 's'} of evidence`
                : 'No supporting memory retrieved'}
        </strong>

        <p class="muted small">${esc(data.reason || '')}</p>

        ${(memories.length || history.length) ? `
          <details>
            <summary>See evidence</summary>

            ${memories.map(memory => `
              <p>
                <strong>${esc(memory.canonical_text)}</strong><br>
                <span class="muted">
                  ${esc(stateLabel(memory.status))}
                  ${(memory.source_evidence || []).map(e =>
                    ` · Source ${e.interaction_id}: “${esc(e.excerpt)}”`
                ).join('')}
                </span>
              </p>
            `).join('')}

            ${history.map(item => `
              <p>
                <strong>${esc(item.formatted_text)}</strong><br>
                <span class="muted">
                  Source ${item.interaction_id} · ${esc(item.app)} · ${esc(item.occurred_at)}
                </span>
              </p>
            `).join('')}
          </details>
        ` : ''}
      </div>
    `;

    } catch (error) {
        $('#askResult').innerHTML = `
      <div class="decision-item">
        <strong>Hey Kivi couldn't answer.</strong>
        <span class="muted">${esc(error.message)}</span>
      </div>
    `;
    } finally {
        button.disabled = false;
        button.textContent = 'Ask Hey Kivi';
    }
};

$('#importBtn').onclick = async () => {
    const file = $('#corpusFile').files[0];
    if (!file) return;

    const button = $('#importBtn');
    button.disabled = true;
    button.textContent = 'Learning…';

    $('#learnResult').textContent =
        'Learning from history. This may take several minutes…';

    try {
        const body = new FormData();
        body.append('file', file);

        const data = await request('/api/import', {
            method: 'POST',
            body
        });

        $('#learnResult').innerHTML = `
      <div class="decision-item">
        <strong>History processed</strong>
        <span class="muted">
          ${data.processed} interactions processed · ${data.failed} failed
        </span>
      </div>
    `;
    } catch (error) {
        $('#learnResult').textContent = error.message;
    } finally {
        button.disabled = false;
        button.textContent = 'Learn from history';
    }
};

let resetPending = false;

$('#resetBtn').onclick = async () => {
    if (!resetPending) {
        resetPending = true;
        $('#resetBtn').textContent = 'Confirm reset';
        $('#cancelReset').hidden = false;
        return;
    }

    try {
        await request('/api/reset', { method: 'POST' });

        $('#learnResult').innerHTML = `
      <div class="empty-state">
        <strong>State reset.</strong>
        <span>Kivi has no learned state in this demo database.</span>
      </div>
    `;

        $('#askResult').innerHTML = `
      <div class="empty-state">
        <strong>State reset.</strong>
        <span>Teach Kivi something before asking about it.</span>
      </div>
    `;

        $('#resetBtn').textContent = 'Reset state';
        $('#cancelReset').hidden = true;
        resetPending = false;

        loadMemories();
    } catch (error) {
        $('#learnResult').textContent = error.message;
    }
};

$('#cancelReset').onclick = () => {
    resetPending = false;
    $('#resetBtn').textContent = 'Reset state';
    $('#cancelReset').hidden = true;
};

$('#refreshMemory').onclick = loadMemories;

async function loadMemories() {
    try {
        const rows = await request('/api/memories');

        $('#memoryList').innerHTML = rows.length
            ? rows.map(memory => `
        <div class="memory">
          <div>
            <span class="pill">${esc(memory.memory_type)}</span>
            <span class="pill">${esc(scopeLabel(memory.scope))}</span>
            <span class="pill">${esc(stateLabel(memory.status))}</span>

            <h3>${esc(memory.canonical_text)}</h3>

            <p>
              ${esc(certaintyLabel(memory.certainty))}
              · confidence ${Number(memory.confidence).toFixed(2)}
            </p>

            <details>
              <summary>Source & provenance</summary>
              ${(memory.source_evidence || []).map(e => `
                <p>
                  Interaction ${e.interaction_id}: “${esc(e.excerpt)}”
                </p>
              `).join('') || '<p class="muted">No source evidence shown.</p>'}
            </details>
          </div>

          <div>
            <div class="memory-actions">
              <button class="ghost" onclick="correct(${memory.id})">Correct</button>
              <button class="ghost danger" onclick="forget(${memory.id})">Forget</button>
            </div>
            <div id="edit-${memory.id}"></div>
          </div>
        </div>
      `).join('')
            : `
        <div class="empty-state">
          <strong>Nothing learned yet.</strong>
          <span>Use Dictation first and Kivi's useful memories will appear here.</span>
        </div>
      `;
    } catch (error) {
        $('#memoryList').innerHTML =
            `<p class="muted">${esc(error.message)}</p>`;
    }
}

async function forget(id) {
    try {
        await request('/api/memories/' + id, { method: 'DELETE' });
        loadMemories();
    } catch (error) {
        alert(error.message);
    }
}

async function loadTrace() {
    try {
        const decisions = await request('/api/decisions');

        $('#decisionList').innerHTML = decisions.length
            ? decisions.map(item => `
        <div class="trace">
          <strong>
            ${esc(actionLabel(item.action))}
            · interaction ${item.interaction_id}
          </strong>

          ${esc(item.reason)}

          <br>
          <span class="muted">
            ${esc(item.candidate?.canonical_text || item.candidate?.value || '')}
          </span>
        </div>
      `).join('')
            : `
        <div class="empty-state">
          <strong>No memory decisions yet.</strong>
          <span>Process a dictation to see why Kivi learns or ignores it.</span>
        </div>
      `;

        const traces = await request('/api/traces');

        $('#traceList').innerHTML = traces.length
            ? traces.map(item => `
        <div class="trace">
          <strong>${esc(item.query)}</strong>
          ${esc(item.response)}
          <br>
          <span class="muted">
            memories ${item.retrieved_memory_ids.join(', ') || 'none'}
            · ${Number(item.end_to_end_latency_ms).toFixed(1)} ms
          </span>
          <details>
            <summary>Why this answer?</summary>
            <p>${esc(item.reason)}</p>
            <p class="muted">
              Source interactions:
              ${item.source_interaction_ids.join(', ') || 'none'}
            </p>
          </details>
        </div>
      `).join('')
            : `
        <div class="empty-state">
          <strong>No answer traces yet.</strong>
          <span>Ask Hey Kivi something to inspect its retrieval path.</span>
        </div>
      `;
    } catch (error) {
        $('#decisionList').textContent = error.message;
    }
}

async function correct(id) {
    const slot = document.querySelector('#edit-' + id);

    try {
        const rows = await request('/api/memories');
        const value = rows.find(memory => memory.id === id)?.value || '';

        slot.innerHTML = `
      <label for="correct-${id}">Correct this memory</label>
      <input id="correct-${id}" value="${esc(value)}" />
      <div class="memory-actions">
        <button onclick="saveCorrection(${id})">Save</button>
        <button class="ghost" onclick="cancelCorrection(${id})">Cancel</button>
      </div>
      <p id="edit-status-${id}"></p>
    `;

        document.querySelector('#correct-' + id).focus();
    } catch (error) {
        slot.textContent = error.message;
    }
}

function cancelCorrection(id) {
    document.querySelector('#edit-' + id).innerHTML = '';
}

async function saveCorrection(id) {
    const value = document.querySelector('#correct-' + id).value.trim();
    if (!value) return;

    try {
        await request(
            '/api/memories/' + id,
            options({ value }, 'PATCH')
        );

        loadMemories();
    } catch (error) {
        document.querySelector('#edit-status-' + id).textContent =
            error.message;
    }
}

function actionLabel(action) {
    return {
        create: 'Remembered',
        update: 'Updated',
        reinforce: 'Reinforced',
        ignore: 'Ignored',
        delete: 'Forgotten',
        supersede: 'Replaced',
        clarify: 'Needs clarification',
        reject: 'Not stored'
    }[action] || action;
}

function actionHeadline(action) {
    const candidate = action.candidate || {};
    return candidate.canonical_text ||
        candidate.value ||
        actionLabel(action.action);
}

function certaintyLabel(certainty) {
    return {
        confirmed: 'Confirmed',
        reported: 'Reported',
        tentative: 'Tentative',
        inferred: 'Inferred'
    }[certainty] || certainty || 'Recorded';
}

function scopeLabel(scope) {
    try {
        if (scope && scope.startsWith('{')) {
            const values = Object.values(JSON.parse(scope)).filter(Boolean);
            return values.join(' · ') || 'General';
        }
    } catch (_) { }

    return scope === 'global'
        ? 'General'
        : String(scope || 'General').replaceAll(':', ' · ');
}

function stateLabel(state) {
    return {
        active: 'Current',
        tentative: 'Possibility',
        future: 'Future',
        historical: 'Earlier',
        superseded: 'Replaced',
        deleted: 'Forgotten',
        expired: 'Expired',
        pending: 'Needs confirmation'
    }[state] || state;
}