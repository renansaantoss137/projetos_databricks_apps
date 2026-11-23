
    /* Theme */
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
    function toggleTheme() {
      const t = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', t);
      localStorage.setItem('theme', t);
    }

    /* Tabs */
    function switchTab(id) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById('tab-' + id).classList.add('active');
      document.getElementById('content-' + id).classList.add('active');
    }

    /* Presentation */
    let currentSlide = 1;
    const totalSlides = 8;

    function presNav(dir) {
      const next = currentSlide + dir;
      if (next < 1 || next > totalSlides) return;
      document.querySelector(`.slide[data-slide="${currentSlide}"]`).classList.remove('active');
      currentSlide = next;
      document.querySelector(`.slide[data-slide="${currentSlide}"]`).classList.add('active');
      updatePresUI();
    }

    function updatePresUI() {
      document.getElementById('presCounter').textContent = `${currentSlide} / ${totalSlides}`;
      document.getElementById('presProgress').style.width = `${(currentSlide / totalSlides) * 100}%`;
      const backBtn = document.getElementById('presBack');
      const nextBtn = document.getElementById('presNext');
      backBtn.disabled = currentSlide === 1;
      nextBtn.disabled = currentSlide === totalSlides;
      backBtn.title = (typeof t === 'function' ? t('Anterior') : 'Anterior');
      nextBtn.title = (typeof t === 'function' ? t('Próximo') : 'Próximo');
    }

    function toggleFullscreen() {
      const c = document.getElementById('presContainer');
      c.classList.toggle('fullscreen');
      const isFS = c.classList.contains('fullscreen');
      var exitTxt = (typeof t === 'function' ? t('Sair') : 'Sair');
      var fsTxt = (typeof t === 'function' ? t('Tela cheia') : 'Tela cheia');
      document.getElementById('presFS').innerHTML = isFS
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg> ' + exitTxt
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg> ' + fsTxt;
    }

    /* Keyboard navigation for presentation */
    document.addEventListener('keydown', function (e) {
      if (!document.getElementById('content-pres').classList.contains('active')) return;
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); presNav(1); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); presNav(-1); }
      if (e.key === 'Escape') {
        const c = document.getElementById('presContainer');
        if (c.classList.contains('fullscreen')) toggleFullscreen();
      }
    });

    updatePresUI();
    document.addEventListener('langChange', updatePresUI);
  