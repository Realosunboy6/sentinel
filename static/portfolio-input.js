/* Shared, framework-free portfolio editor for Analyzer and tools. */
(() => {
  const form = document.querySelector('[data-portfolio-form]');
  if (!form) return;
  let holdings;
  try {
    const seed = JSON.parse(document.getElementById('portfolio-seed').textContent);
    holdings = typeof seed === 'string' ? JSON.parse(seed) : seed;
  } catch (_) { holdings = []; }
  if (!Array.isArray(holdings) || !holdings.length) holdings = [{symbol:'', weight:''}];
  holdings = holdings.filter(h => h && typeof h === 'object').slice(0, 25);
  if (!holdings.length) holdings = [{symbol:'', weight:''}];
  const body = form.querySelector('#holdings-tbody');
  const hidden = form.querySelector('[name="holdings_json"]');
  const notice = form.querySelector('[data-portfolio-notice]');
  const weight = h => Number(h.weight) || 0;
  const sync = () => {
    form.querySelector('#total-display').textContent = holdings.reduce((s,h) => s + weight(h), 0).toFixed(2);
    hidden.value = JSON.stringify(holdings.filter(h => String(h.symbol || '').trim()).map(h => ({symbol:String(h.symbol).trim().toUpperCase(), weight:weight(h)})));
  };
  const render = () => {
    body.replaceChildren();
    holdings.forEach((holding, index) => {
      const row = document.createElement('tr');
      const symbolCell = row.insertCell();
      const symbol = document.createElement('input');
      symbol.className = 'sym-input';
      symbol.value = String(holding.symbol || '');
      symbol.maxLength = 20;
      symbol.setAttribute('aria-label', `Ticker ${index + 1}`);
      symbol.addEventListener('input', () => { holding.symbol = symbol.value.toUpperCase(); symbol.value = holding.symbol; sync(); });
      symbolCell.append(symbol);
      const weightCell = row.insertCell();
      weightCell.className = 'weight-column';
      const input = document.createElement('input');
      input.type = 'number'; input.min = '0'; input.step = 'any'; input.className = 'wt-input';
      input.value = holding.weight ?? '';
      input.setAttribute('aria-label', `Weight ${index + 1} (%)`);
      input.addEventListener('input', () => { holding.weight = input.value; sync(); });
      weightCell.append(input);
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'remove-asset'; remove.textContent = '×';
      remove.setAttribute('aria-label', `Remove asset ${index + 1}`);
      remove.disabled = holdings.length === 1;
      remove.addEventListener('click', () => { holdings.splice(index, 1); render(); });
      row.insertCell().append(remove);
      body.append(row);
    });
    form.querySelector('[data-add-asset]').disabled = holdings.length >= 25;
    sync();
  };
  form.querySelector('[data-add-asset]').addEventListener('click', () => { if (holdings.length < 25) { holdings.push({symbol:'',weight:''}); render(); } });
  form.querySelector('[data-normalize]').addEventListener('click', () => {
    const total = holdings.reduce((s,h) => s + weight(h), 0);
    if (!(total > 0)) { notice.textContent = 'Enter positive weights before normalizing.'; return; }
    holdings.forEach(h => { h.weight = Number((weight(h) / total * 100).toFixed(6)); });
    notice.textContent = 'Weights normalized to 100%.';
    render();
  });
  form.addEventListener('submit', sync);
  render();
})();
