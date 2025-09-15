(() => {
  const line = document.querySelector('.title-line');
  const row  = line?.querySelector('.title-row');
  if (!row) return;

  const WORD = (line.dataset.word || 'COMBAT').trim();
  const SEP  = (line.dataset.sep  || '✦').trim();

  const makeWord = (cls) => {
    const el = document.createElement('span');
    el.className = 'title-word' + (cls ? ' ' + cls : '');
    el.textContent = WORD;
    return el;
  };

  const makeSep = () => {
    const el = document.createElement('span');
    el.className = 'title-sep';
    el.textContent = SEP;
    return el;
  };

  function build() {
    row.innerHTML = '';
    const vw = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
    // приблизительная ширина одного «WORD + SEP»
    let count = Math.max(7, Math.ceil(vw / 220) * 2 + 1); // нечётное, чтобы центр был красным
    const mid = Math.floor(count / 2);

    for (let i = 0; i < count; i++) {
      row.appendChild(makeWord(i === mid ? 'main' : ''));
      if (i !== count - 1) row.appendChild(makeSep());
    }
  }

  build();

  let t;
  window.addEventListener('resize', () => {
    clearTimeout(t);
    t = setTimeout(build, 120);
  });
})();
