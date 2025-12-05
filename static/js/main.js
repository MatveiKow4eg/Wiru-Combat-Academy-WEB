function toggleMenu(){
  const nav = document.getElementById('nav');
  const overlay = document.getElementById('navOverlay');
  const body = document.body;
  const willOpen = !nav.classList.contains('open');
  // Toggle classes and harden overlay state to avoid stuck intercepts
  nav.classList.toggle('open', willOpen);
  body.classList.toggle('menu-open', willOpen);
  if(overlay){
    // Ensure overlay never blocks clicks when menu is closed
    overlay.removeAttribute('style');
    overlay.style.opacity = willOpen ? '1' : '0';
    overlay.style.pointerEvents = willOpen ? 'auto' : 'none';
  }
}

  // Mobile nav: swipe-to-close, close on ESC and link click (mobile only)
(function(){
  const nav = document.getElementById('nav');
  if(!nav) return;
  const overlay = document.getElementById('navOverlay');
  const isMobile = () => window.matchMedia('(max-width: 640px)').matches;
  // Initialize safe state (menu closed, overlay disabled)
  document.body.classList.remove('menu-open');
  nav.classList.remove('open');
  if(overlay){
    overlay.removeAttribute('style');
    overlay.style.opacity = '0';
    overlay.style.pointerEvents = 'none';
  }

  // Close on ESC
  document.addEventListener('keydown', (e) => {
    if(e.key === 'Escape' && nav.classList.contains('open')) toggleMenu();
  });

  // Close when clicking any link in the drawer (mobile only)
  nav.addEventListener('click', (e) => {
    const t = e.target;
    if(t && t.tagName === 'A' && isMobile() && nav.classList.contains('open')) {
      toggleMenu();
    }
  });

  // Swipe left to close
  let startX = 0, deltaX = 0, dragging = false;
  nav.addEventListener('touchstart', (e) => {
    if(!isMobile() || !nav.classList.contains('open')) return;
    dragging = true; startX = e.touches[0].clientX; deltaX = 0;
  }, { passive: true });

  nav.addEventListener('touchmove', (e) => {
    if(!dragging || !isMobile() || !nav.classList.contains('open')) return;
    deltaX = e.touches[0].clientX - startX;
  }, { passive: true });

  nav.addEventListener('touchend', () => {
    if(!dragging || !isMobile() || !nav.classList.contains('open')) return;
    dragging = false;
    if(deltaX < -50) toggleMenu();
  });

  // Click outside to close (mobile only)
  document.addEventListener('click', (e) => {
    if (!isMobile() || !nav.classList.contains('open')) return;
    const burger = document.querySelector('.burger');
    const insideNav = nav.contains(e.target);
    const onBurger = burger && (burger === e.target || burger.contains(e.target));
    if (!insideNav && !onBurger) {
      toggleMenu();
    }
  });

  // Ensure menu/overlay closed on desktop
  window.addEventListener('resize', () => {
    if (!isMobile()) {
      document.body.classList.remove('menu-open');
      nav.classList.remove('open');
      if(overlay){
        overlay.style.opacity = '0';
        overlay.style.pointerEvents = 'none';
      }
    }
  });
})();

  // Mobile slider for schedule (infinite)
(function(){
  const grid = document.getElementById('scheduleGrid');
  const prevBtn = document.querySelector('.schedule-arrow.prev');
  const nextBtn = document.querySelector('.schedule-arrow.next');
  if(!grid || !prevBtn || !nextBtn) return;

  let index = 1; // start on first real slide after prepended clone
  let realSlides = Array.from(grid.querySelectorAll('.schedule-card')).filter(el => !el.dataset.clone);
  let initialized = false;

  const isMobile = () => window.matchMedia('(max-width: 640px)').matches;

  function slideW(){
    const style = getComputedStyle(grid);
    const gapStr = style.gap || style.columnGap || '0';
    const gap = parseFloat(gapStr) || 0;
    const firstCard = grid.querySelector('.schedule-card');
    const w = firstCard ? firstCard.getBoundingClientRect().width : grid.parentElement.clientWidth;
    return w + gap;
  }

  function addClones(){
    if(grid.dataset.infinite === '1') return;
    const first = realSlides[0];
    const last = realSlides[realSlides.length - 1];
    if(!first || !last) return;
    const cloneLast = last.cloneNode(true); cloneLast.dataset.clone = '1';
    const cloneFirst = first.cloneNode(true); cloneFirst.dataset.clone = '1';
    grid.insertBefore(cloneLast, grid.firstChild);
    grid.appendChild(cloneFirst);
    grid.dataset.infinite = '1';
  }

  function removeClones(){
    Array.from(grid.children).forEach(el => { if(el.dataset && el.dataset.clone) el.remove(); });
    delete grid.dataset.infinite;
  }

  function update(){
    if(!isMobile()){
      grid.style.transform = '';
      grid.style.transition = '';
      return;
    }
    const offset = -index * slideW();
    grid.style.transform = `translate3d(${offset}px,0,0)`;
  }

  function go(delta){
    if(!initialized) return;
    index += delta;
    grid.style.transition = '';
    update();
  }

  function onTransitionEnd(){
    if(!isMobile()) return;
    const count = realSlides.length;
    if(index === 0){
      grid.style.transition = 'none';
      index = count;
      update();
      requestAnimationFrame(() => { grid.style.transition = ''; });
    } else if(index === count + 1){
      grid.style.transition = 'none';
      index = 1;
      update();
      requestAnimationFrame(() => { grid.style.transition = ''; });
    }
  }

  // touch swipe
  let startX = 0, deltaX = 0, dragging = false;
  function onStart(e){
    if(!isMobile() || !initialized) return;
    dragging = true; startX = e.touches[0].clientX; deltaX = 0;
    grid.style.transition = 'none';
  }
  function onMove(e){
    if(!dragging || !isMobile() || !initialized) return;
    deltaX = e.touches[0].clientX - startX;
    const offset = -index * slideW() + deltaX;
    grid.style.transform = `translate3d(${offset}px,0,0)`;
  }
  function onEnd(){
    if(!dragging || !isMobile() || !initialized) return;
    dragging = false;
    grid.style.transition = '';
    if(Math.abs(deltaX) > 50){ go(deltaX < 0 ? 1 : -1); } else { update(); }
  }

  function enable(){
    if(initialized || !isMobile()) return;
    realSlides = Array.from(grid.querySelectorAll('.schedule-card')).filter(el => !el.dataset.clone);
    addClones();
    index = 1;
    update();
    initialized = true;
  }

  function disable(){
    if(!initialized) return;
    grid.style.transition = 'none';
    grid.style.transform = '';
    removeClones();
    initialized = false;
  }

  prevBtn.addEventListener('click', () => go(-1));
  nextBtn.addEventListener('click', () => go(1));
  grid.addEventListener('transitionend', onTransitionEnd);
  grid.addEventListener('touchstart', onStart, { passive: true });
  grid.addEventListener('touchmove', onMove, { passive: true });
  grid.addEventListener('touchend', onEnd);

  function handleResize(){
    if(isMobile()) enable(); else disable();
  }
  window.addEventListener('resize', handleResize);
  handleResize();
})();

// Mobile slider for clients (infinite)
(function(){
  const grid = document.getElementById('clientsGrid');
  const prevBtn = document.querySelector('.clients-arrow.prev');
  const nextBtn = document.querySelector('.clients-arrow.next');
  if(!grid || !prevBtn || !nextBtn) return;

  let index = 1; // start on first real slide after prepended clone
  let realSlides = Array.from(grid.querySelectorAll('.client-card')).filter(el => !el.dataset.clone);
  let initialized = false;

  const isMobile = () => window.matchMedia('(max-width: 640px)').matches;

  function slideW(){
    const style = getComputedStyle(grid);
    const gapStr = style.gap || style.columnGap || '0';
    const gap = parseFloat(gapStr) || 0;
    const firstCard = grid.querySelector('.client-card');
    const w = firstCard ? firstCard.getBoundingClientRect().width : grid.parentElement.clientWidth;
    return w + gap;
  }

  function addClones(){
    if(grid.dataset.infinite === '1') return;
    const first = realSlides[0];
    const last = realSlides[realSlides.length - 1];
    if(!first || !last) return;
    const cloneLast = last.cloneNode(true); cloneLast.dataset.clone = '1';
    const cloneFirst = first.cloneNode(true); cloneFirst.dataset.clone = '1';
    grid.insertBefore(cloneLast, grid.firstChild);
    grid.appendChild(cloneFirst);
    grid.dataset.infinite = '1';
  }

  function removeClones(){
    Array.from(grid.children).forEach(el => { if(el.dataset && el.dataset.clone) el.remove(); });
    delete grid.dataset.infinite;
  }

  function update(){
    if(!isMobile()){
      grid.style.transform = '';
      grid.style.transition = '';
      return;
    }
    const offset = -index * slideW();
    grid.style.transform = `translate3d(${offset}px,0,0)`;
  }

  function go(delta){
    if(!initialized) return;
    index += delta;
    grid.style.transition = '';
    update();
  }

  function onTransitionEnd(){
    if(!isMobile()) return;
    const count = realSlides.length;
    if(index === 0){
      grid.style.transition = 'none';
      index = count;
      update();
      requestAnimationFrame(() => { grid.style.transition = ''; });
    } else if(index === count + 1){
      grid.style.transition = 'none';
      index = 1;
      update();
      requestAnimationFrame(() => { grid.style.transition = ''; });
    }
  }

  // touch swipe
  let startX = 0, deltaX = 0, dragging = false;
  function onStart(e){
    if(!isMobile() || !initialized) return;
    dragging = true; startX = e.touches[0].clientX; deltaX = 0;
    grid.style.transition = 'none';
  }
  function onMove(e){
    if(!dragging || !isMobile() || !initialized) return;
    deltaX = e.touches[0].clientX - startX;
    const offset = -index * slideW() + deltaX;
    grid.style.transform = `translate3d(${offset}px,0,0)`;
  }
  function onEnd(){
    if(!dragging || !isMobile() || !initialized) return;
    dragging = false;
    grid.style.transition = '';
    if(Math.abs(deltaX) > 50){ go(deltaX < 0 ? 1 : -1); } else { update(); }
  }

  function enable(){
    if(initialized || !isMobile()) return;
    realSlides = Array.from(grid.querySelectorAll('.client-card')).filter(el => !el.dataset.clone);
    addClones();
    index = 1;
    update();
    initialized = true;
  }

  function disable(){
    if(!initialized) return;
    grid.style.transition = 'none';
    grid.style.transform = '';
    removeClones();
    initialized = false;
  }

  prevBtn.addEventListener('click', () => go(-1));
  nextBtn.addEventListener('click', () => go(1));
  grid.addEventListener('transitionend', onTransitionEnd);
  grid.addEventListener('touchstart', onStart, { passive: true });
  grid.addEventListener('touchmove', onMove, { passive: true });
  grid.addEventListener('touchend', onEnd);

  function handleResize(){
    if(isMobile()) enable(); else disable();
  }
  window.addEventListener('resize', handleResize);
  handleResize();
})();

// Fixed header: hide on scroll down, show on scroll up
(function(){
  const header = document.querySelector('.header');
  if(!header) return;

  function setHeaderHeightVar(){
    const h = header.getBoundingClientRect().height;
    document.documentElement.style.setProperty('--header-h', h + 'px');
  }

  // keep updated on load/resize and if header size changes
  window.addEventListener('load', setHeaderHeightVar);
  window.addEventListener('resize', setHeaderHeightVar);
  if('ResizeObserver' in window){
    const ro = new ResizeObserver(setHeaderHeightVar);
    ro.observe(header);
  }

  let lastY = Math.max(window.pageYOffset || document.documentElement.scrollTop || 0, 0);
  let ticking = false;
  const DELTA = 8; // minimal scroll delta to react

  function update(){
    const y = Math.max(window.pageYOffset || document.documentElement.scrollTop || 0, 0);

    // Keep header visible while mobile nav is open
    if(document.body.classList.contains('menu-open')){
      header.classList.remove('header--hidden');
      lastY = y;
      ticking = false;
      return;
    }

    const delta = y - lastY;
    const goingDown = delta > 0;

    if(Math.abs(delta) > DELTA){
      if(goingDown){
        header.classList.add('header--hidden');
      } else {
        header.classList.remove('header--hidden');
      }
    }

    if(y <= 0){
      header.classList.remove('header--hidden');
    }

    lastY = y;
    ticking = false;
  }

  function onScroll(){
    if(!ticking){
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  window.addEventListener('scroll', onScroll, { passive: true });

  // Initial sync
  setHeaderHeightVar();
  update();
})();
