/** Painel visual inline — monta tabelas a partir de tool_results do Apura. */
(function (global) {
  const COL_LABELS = {
    nm_urna: 'Candidato',
    nm_candidato: 'Candidato',
    qt_votos: 'Votos',
    sg_partido: 'Partido',
    nr_candidato: 'Nº',
    ds_sit_tot_turno: 'Situação',
    pct: '%',
    vr_despesa: 'Valor (R$)',
    vr_receita: 'Valor (R$)',
    ds_despesa: 'Despesa',
    ds_origem: 'Origem',
    nm_fornecedor: 'Fornecedor',
    dt_despesa: 'Data',
    sg_uf: 'UF',
    ds_cargo: 'Cargo',
    ano: 'Ano',
    titulo: 'Título',
    fonte: 'Fonte',
    resumo: 'Resumo',
    qt_familias: 'Famílias',
    qt_populacao: 'População',
    nm_municipio: 'Município',
  };

  const TOOL_LABELS = {
    consultar_votacao: 'Votação na urna',
    consultar_eleitos: 'Eleitos',
    consultar_nominata: 'Candidatos',
    consultar_despesa: 'Despesas de campanha',
    consultar_receita: 'Receitas de campanha',
    consultar_comparecimento: 'Comparecimento',
    consultar_populacao: 'População',
    consultar_cadunico: 'CadÚnico',
    consultar_bolsa_familia: 'Bolsa Família',
    consultar_deputados_casa: 'Deputados',
    consultar_proposicoes: 'Proposições',
    consultar_linha_temporal: 'Linha temporal',
    consultar_cruzamento_social: 'Social × urna',
    consultar_clima: 'Clima midiático',
    consultar_acervo: 'Acervo',
  };

  const PREFER_COLS = [
    'nm_urna', 'nm_candidato', 'qt_votos', 'sg_partido', 'vr_despesa', 'vr_receita',
    'ds_sit_tot_turno', 'pct', 'nm_fornecedor', 'ds_despesa', 'dt_despesa', 'sg_uf',
    'titulo', 'fonte', 'nm_municipio', 'qt_familias', 'ano',
  ];

  const NUM_KEYS = new Set([
    'qt_votos', 'vr_despesa', 'vr_receita', 'pct', 'qt_familias', 'qt_populacao', 'nr_candidato',
  ]);

  function flattenBlocks(dados) {
    const blocks = [];
    if (!dados || !Array.isArray(dados.tool_results)) return blocks;

    for (const tr of dados.tool_results) {
      const tool = tr.tool || '';
      const res = tr.result || {};
      if (res.status === 'fora_do_recorte') continue;

      let rows = [];
      if (Array.isArray(res.linhas)) rows = res.linhas;
      else if (Array.isArray(res.itens)) rows = res.itens;
      else if (Array.isArray(res.series)) {
        for (const s of res.series) {
          if (!s || !Array.isArray(s.linhas)) continue;
          for (const row of s.linhas) {
            rows.push({ ...row, _ano_serie: s.ano });
          }
        }
      }
      rows = rows.filter((r) => r && typeof r === 'object');
      if (rows.length) blocks.push({ tool, rows });
    }
    return blocks;
  }

  function pickColumns(rows) {
    const keys = [];
    const seen = new Set();
    for (const k of PREFER_COLS) {
      if (rows.some((r) => r[k] != null && r[k] !== '') && !seen.has(k)) {
        seen.add(k);
        keys.push(k);
      }
    }
    for (const row of rows) {
      for (const k of Object.keys(row)) {
        if (k.startsWith('_') || k.startsWith('sq_')) continue;
        if (!seen.has(k) && row[k] != null && row[k] !== '') {
          seen.add(k);
          keys.push(k);
        }
      }
    }
    return keys.slice(0, 7);
  }

  function formatCell(key, val) {
    if (val == null || val === '') return '—';
    if (NUM_KEYS.has(key) && typeof val === 'number') {
      if (key.startsWith('vr_')) {
        return val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
      }
      return val.toLocaleString('pt-BR');
    }
    return String(val);
  }

  function toolLabel(tool) {
    return TOOL_LABELS[tool] || (tool || 'Consulta').replace(/^consultar_/, '').replace(/_/g, ' ');
  }

  function toolBadgeClass(tool) {
    const t = (tool || '').toLowerCase();
    if (t.includes('acervo')) return 'painel-badge-acervo';
    if (t.includes('clima')) return 'painel-badge-clima';
    return 'painel-badge-fato';
  }

  function buildTable(rows) {
    const cols = pickColumns(rows);
    const wrap = document.createElement('div');
    wrap.className = 'painel-table-wrap';
    const table = document.createElement('table');
    table.className = 'painel-table';
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    for (const k of cols) {
      const th = document.createElement('th');
      th.textContent = COL_LABELS[k] || k;
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    const limit = Math.min(rows.length, 25);
    for (let i = 0; i < limit; i++) {
      const row = rows[i];
      const tr = document.createElement('tr');
      for (const k of cols) {
        const td = document.createElement('td');
        if (NUM_KEYS.has(k) || k === 'ano' || k === 'sg_uf' || k === 'nr_candidato') {
          td.className = (NUM_KEYS.has(k) ? 'num' : '') + ' nowrap';
        }
        td.textContent = formatCell(k, row[k]);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    if (rows.length > limit) {
      const note = document.createElement('p');
      note.className = 'painel-more';
      note.textContent = `+ ${rows.length - limit} linha(s) · exporte Excel para ver tudo`;
      wrap.appendChild(note);
    }
    return wrap;
  }

  function buildPainelElement(dados) {
    const blocks = flattenBlocks(dados);
    if (!blocks.length) return null;

    const nTools = blocks.length;
    const nRows = blocks.reduce((s, b) => s + b.rows.length, 0);

    const details = document.createElement('details');
    details.className = 'apura-painel apura-painel-collapsed';
    details.setAttribute('role', 'region');
    details.setAttribute('aria-label', 'Consultas oficiais (recolhido)');

    const summary = document.createElement('summary');
    summary.className = 'painel-cap';
    summary.textContent =
      'Consultas oficiais · ' +
      nTools +
      ' painel(is) · ' +
      nRows.toLocaleString('pt-BR') +
      ' linha(s) — abrir só se precisar do bruto';
    details.appendChild(summary);

    const note = document.createElement('p');
    note.className = 'painel-more';
    note.style.padding = '0 16px 8px';
    note.textContent =
      'A análise acima já sintetiza o que importa. Aqui ficam as consultas intermediárias do orquestrador (útil para auditoria / Excel).';
    details.appendChild(note);

    for (const block of blocks) {
      const section = document.createElement('section');
      section.className = 'painel-block';
      const head = document.createElement('div');
      head.className = 'painel-head';
      const badge = document.createElement('span');
      badge.className = 'painel-badge ' + toolBadgeClass(block.tool);
      badge.textContent = block.tool.includes('acervo') ? 'Acervo' : block.tool.includes('clima') ? 'Clima' : 'Fato';
      const title = document.createElement('strong');
      title.textContent = toolLabel(block.tool);
      const count = document.createElement('span');
      count.className = 'painel-count';
      count.textContent = block.rows.length + ' registro(s)';
      head.appendChild(badge);
      head.appendChild(title);
      head.appendChild(count);
      section.appendChild(head);
      section.appendChild(buildTable(block.rows));
      details.appendChild(section);
    }
    return details;
  }

  function parseMarkdownTables(text) {
    const lines = text.split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (line.trim().startsWith('|') && line.includes('|', 1)) {
        const tableLines = [];
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          tableLines.push(lines[i]);
          i++;
        }
        out.push(renderMdTable(tableLines));
        continue;
      }
      out.push(line);
      i++;
    }
    return out.join('\n');
  }

  function renderMdTable(tableLines) {
    const parseRow = (ln) =>
      ln.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
    if (tableLines.length < 2) return tableLines.join('\n');
    const headers = parseRow(tableLines[0]);
    let start = 1;
    if (/^[\s|:-]+$/.test(tableLines[1])) start = 2;
    const rows = tableLines.slice(start).map(parseRow);
    let html = '<div class="painel-table-wrap inline-table"><table class="painel-table"><thead><tr>';
    for (const h of headers) html += `<th>${escapeHtml(h)}</th>`;
    html += '</tr></thead><tbody>';
    for (const row of rows) {
      html += '<tr>';
      for (let c = 0; c < headers.length; c++) {
        html += `<td>${escapeHtml(row[c] || '')}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table></div>';
    return html;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  global.ApuraPainel = {
    buildPainelElement,
    flattenBlocks,
    parseMarkdownTables,
  };
})(window);
