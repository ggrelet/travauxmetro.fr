  function copyUrl(url, btn) {
    if (btn.disabled) return;
    btn.disabled = true;
    const orig = btn.innerHTML;
    btn.style.width = btn.offsetWidth + 'px';
    btn.style.height = btn.offsetHeight + 'px';
    const done = () => {
      btn.classList.add('copied');
      btn.innerHTML = '✓ Copié !';
      setTimeout(() => {
        btn.innerHTML = orig;
        btn.classList.remove('copied');
        btn.style.width = '';
        btn.style.height = '';
        btn.disabled = false;
      }, 3000);
    };
    const fallback = () => {
      const ta = Object.assign(document.createElement('textarea'), {
        value: url, style: 'position:fixed;opacity:0'
      });
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      try { document.execCommand('copy'); } catch(e) {}
      document.body.removeChild(ta);
      done();
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(done).catch(fallback);
    } else {
      fallback();
    }
  }
  document.querySelectorAll('.dis-dialog').forEach(dlg => {
    document.body.insertBefore(dlg, document.body.firstChild);
  });
  document.querySelectorAll('.dis-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const sw = window.innerWidth - document.documentElement.clientWidth;
      if (sw) document.body.style.paddingRight = sw + 'px';
      document.documentElement.style.overflow = 'hidden';
      const siv = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = () => {};
      document.getElementById(btn.dataset.dialog).showModal();
      Element.prototype.scrollIntoView = siv;
    });
  });
  document.querySelectorAll('.dis-dialog').forEach(dlg => {
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener('close', () => {
      document.documentElement.style.overflow = '';
      document.body.style.paddingRight = '';
    });
  });
  document.addEventListener('touchmove', function(e) {
    if (e.scale !== 1) e.preventDefault();
  }, { passive: false });
  document.addEventListener('gesturestart', function(e) { e.preventDefault(); });
  document.addEventListener('gesturechange', function(e) { e.preventDefault(); });
