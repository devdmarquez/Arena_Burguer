(() => {
  const toggle = document.getElementById('auto-refresh');
  const feedback = document.getElementById('board-feedback');
  const fullscreen = document.getElementById('fullscreen');
  if (!toggle || !feedback) return;
  let refreshing = false;
  let refreshController;
  let keyboardNavigation = false;
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Tab') keyboardNavigation = true;
  });
  document.addEventListener('pointerdown', () => { keyboardNavigation = false; });
  const hasDetail = () => !!document.querySelector('.order-dialog[open]');
  const editing = () => !!document.querySelector('.filters:focus-within') ||
    (keyboardNavigation && !!document.querySelector('.orders:focus-within'));
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-order-dialog]');
    if (trigger) {
      // No reemplazar las tarjetas mientras el usuario abre un detalle.
      refreshController?.abort();
      document.getElementById(trigger.dataset.orderDialog)?.showModal();
    }
    const close = event.target.closest('[data-close-dialog]');
    if (close) close.closest('dialog').close();
    if (event.target.matches('.order-dialog')) {
      const rect = event.target.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close();
    }
  });
  fullscreen.hidden = !document.fullscreenEnabled;
  fullscreen.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch { feedback.textContent = 'No se pudo activar pantalla completa. Podés usar F11 en la computadora.'; }
  });
  document.addEventListener('fullscreenchange', () => {
    fullscreen.textContent = document.fullscreenElement ? 'Salir de pantalla completa' : 'Pantalla completa';
  });
  toggle.addEventListener('change', () => {
    if (!toggle.checked) refreshController?.abort();
    feedback.textContent = toggle.checked ? 'Actualización automática activa.' : 'Actualización automática pausada.';
  });
  async function refreshBoard() {
    // Evitar interrumpir consultas, formularios, selección o navegación por teclado.
    if (!toggle.checked || refreshing || document.hidden || hasDetail() || editing() || window.getSelection()?.toString()) return;
    refreshing = true;
    refreshController = new AbortController();
    const timeout = setTimeout(() => refreshController.abort(), 12000);
    try {
      const response = await fetch(window.location.href, {cache: 'no-store', signal: refreshController.signal});
      if (response.redirected) {
        toggle.checked = false;
        feedback.textContent = 'La sesión puede haber vencido. Actualizá la página para ingresar de nuevo.';
        return;
      }
      if (!response.ok) throw new Error('refresh');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      const grid = page.querySelector('.orders');
      if (!grid) throw new Error('refresh');
      if (hasDetail() || !toggle.checked || editing()) return;
      document.querySelector('.orders').replaceWith(grid);
      document.querySelector('.tabs').replaceWith(page.querySelector('.tabs'));
      document.querySelector('.pagination')?.remove();
      const pagination = page.querySelector('.pagination');
      if (pagination) document.querySelector('.orders').after(pagination);
      feedback.textContent = `Pedidos actualizados a las ${new Date().toLocaleTimeString('es-AR', {hour: '2-digit', minute: '2-digit', second: '2-digit'})}.`;
    } catch (error) {
      if (error.name !== 'AbortError') feedback.textContent = 'No se pudo actualizar. Se conservan los pedidos visibles; volveremos a intentar.';
    } finally {
      clearTimeout(timeout);
      refreshing = false;
    }
  }
  setInterval(refreshBoard, 20000);
})();
