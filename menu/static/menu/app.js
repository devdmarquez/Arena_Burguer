(function () {
  const DATA = JSON.parse(document.getElementById("menu-data").textContent);
  const root = document.getElementById("modal-root");

  const money = (n) => "$" + Number(n).toLocaleString("es-AR");
  const mobileCheckout = window.matchMedia('(max-width: 639px)');
  mobileCheckout.addEventListener('change', () => {
    document.getElementById('addr-form')?.dispatchEvent(new Event('checkout-layout'));
  });
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const inputCls =
    "w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm outline-none placeholder:text-white/30 focus:border-orange-500";

  // Estado del pedido en curso
  let state = null;
  let cart = DATA.cart;
  let busy = false;
  const delivery = { name: "", phone: "", fulfillment: "pickup", address: "", locality: "", reference: "" };
  const cartUrl = JSON.parse(document.getElementById("cart-url").textContent);
  const checkoutUrl = JSON.parse(document.getElementById("checkout-url").textContent);
  let submittingOrder = false;
  let suggestionsShown = false;
  const cartTotal = () => cart.total;
  let messageTimer;
  let closeTimer;
  let returnFocus;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const activeAnimations = new Set();

  function animate(element, frames, options) {
    if (reducedMotion.matches || !element.animate) return;
    const animation = element.animate(frames, options);
    activeAnimations.add(animation);
    const done = () => activeAnimations.delete(animation);
    animation.addEventListener("finish", done, { once: true });
    animation.addEventListener("cancel", done, { once: true });
  }
  reducedMotion.addEventListener("change", () => {
    if (reducedMotion.matches) activeAnimations.forEach((animation) => animation.cancel());
  });

  if ("IntersectionObserver" in window && !reducedMotion.matches) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        animate(entry.target, [{ opacity: 0, transform: "translateY(18px)" }, { opacity: 1, transform: "translateY(0)" }],
          { duration: 420, easing: "cubic-bezier(.2,.8,.2,1)" });
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08 });
    document.querySelectorAll(".burger-card, .product-card").forEach((card) => observer.observe(card));
  }

  function message(text) {
    const el = document.getElementById("cart-status");
    el.textContent = text;
    el.classList.remove("hidden");
    el.classList.remove("toast-enter");
    void el.offsetWidth;
    el.classList.add("toast-enter");
    clearTimeout(messageTimer);
    messageTimer = setTimeout(() => el.classList.add("hidden"), 5000);
  }

  function updateCount() {
    const counter = document.getElementById("cart-count");
    const changed = Number(counter.textContent) !== cart.count;
    counter.textContent = cart.count;
    if (changed) {
      animate(counter, [{ transform: "scale(1)" }, { transform: "scale(1.3)", offset: .4 }, { transform: "scale(1)" }], { duration: 300 });
      animate(document.getElementById("cart-button"), [{ boxShadow: "0 0 0 0 rgb(249 115 22 / 40%)" }, { boxShadow: "0 0 0 9px rgb(249 115 22 / 0%)" }], { duration: 430 });
    }
  }

  async function changeCart(payload) {
    if (busy) return false;
    busy = true;
    try {
      const response = await fetch(cartUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "No se pudo actualizar el carrito.");
      cart = result;
      updateCount();
      if (payload.action === "add") message("Producto agregado al carrito.");
      return true;
    } catch (error) {
      message(error.message || "No hay conexión. Intentá de nuevo.");
      return false;
    } finally {
      busy = false;
    }
  }

  async function refreshCart() {
    const response = await fetch(cartUrl, { cache: "no-store" });
    if (!response.ok) throw new Error("No se pudo consultar el carrito.");
    cart = await response.json();
    updateCount();
  }

  function openCart() {
    const rows = cart.items.map((item) => `
      <article data-cart-item="${item.id}" class="space-y-2 rounded-xl border border-white/10 p-4">
        <h4 class="font-bold">${esc(item.name)}</h4>
        ${item.available ? `
          ${item.product_type === "product" ? "" : `<p class="text-sm text-white/60">Aderezos: ${esc(item.aderezo_names.join(", ") || "Ninguno")}</p>
          <p class="text-sm text-white/60">Extras: ${esc(item.extra_names.join(", ") || "Ninguno")}</p>`}
          ${item.notes ? `<p class="text-sm text-white/60">${esc(item.notes)}</p>` : ""}
          <p data-unit-price class="text-sm text-white/60">${money(item.unit_price)} por unidad</p>
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <button type="button" data-quantity="${item.id}" data-value="${item.qty - 1}" aria-label="Restar una unidad" class="h-10 w-10 rounded-full border border-white/15" ${item.qty <= 1 ? "disabled" : ""}>−</button>
              <span data-cart-qty>${item.qty}</span>
              <button type="button" data-quantity="${item.id}" data-value="${item.qty + 1}" aria-label="Sumar una unidad" class="h-10 w-10 rounded-full border border-white/15" ${item.qty >= 99 ? "disabled" : ""}>+</button>
            </div>
            <strong data-cart-subtotal class="text-orange-500">${money(item.subtotal)}</strong>
          </div>` : `<p class="text-sm text-orange-400">${esc(item.error)} Quitá este renglón para continuar.</p>`}
        <button type="button" data-remove="${item.id}" class="text-sm text-white/60 underline">Quitar</button>
      </article>`).join("");
    shell("Tu carrito", "Revisá tu pedido o seguí eligiendo", `
      <div class="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        ${rows || '<p class="text-white/60">Tu carrito está vacío. Elegí una hamburguesa del menú.</p>'}
        ${cart.items.length ? '<button type="button" id="clear-cart" class="text-sm text-white/60 underline">Vaciar carrito</button>' : ""}
      </div>
      <div class="space-y-3 border-t border-white/10 px-6 py-4">
        <p class="flex justify-between font-bold"><span>Total de productos</span><span id="cart-total" aria-live="polite">${money(cart.total)}</span></p>
        <button type="button" id="keep-shopping" class="w-full rounded-full border border-white/15 py-3 font-semibold">Seguir eligiendo</button>
        <button type="button" id="continue-cart" class="w-full rounded-full bg-orange-500 py-3 font-bold text-black disabled:opacity-40" ${cart.can_continue ? "" : "disabled"}>Ir a pagar</button>
      </div>`);
    document.getElementById("keep-shopping").onclick = closeModal;
    root.querySelectorAll("[data-quantity]").forEach((btn) => {
      btn.onclick = async () => {
        if (busy) return;
        const panel = root.querySelector(".modal-panel");
        if (await changeCart({ action: "quantity", id: btn.dataset.quantity, qty: Number(btn.dataset.value) })) {
          // Si la persona cerró o cambió de paso mientras esperaba, no reabrirlo.
          if (root.querySelector(".modal-panel") !== panel || panel.closest(".modal-closing")) return;
          updateCartNumbers();
        }
      };
    });
    root.querySelectorAll("[data-remove]").forEach((btn) => {
      btn.onclick = async () => {
        if (await changeCart({ action: "remove", id: btn.dataset.remove })) openCart();
      };
    });
    const clear = document.getElementById("clear-cart");
    if (clear) clear.onclick = async () => {
      if (await changeCart({ action: "clear" })) openCart();
    };
    document.getElementById("continue-cart").onclick = async () => {
      try {
        await refreshCart();
        if (cart.can_continue) {
          if (!suggestionsShown && cart.suggestions.length) { suggestionsShown = true; openSuggestions(); }
          else openAddress();
        }
        else openCart();
      } catch (error) { message(error.message); }
    };
  }

  function updateCartNumbers() {
    const rows = [...root.querySelectorAll("[data-cart-item]")];
    const byId = new Map(cart.items.map((item) => [item.id, item]));
    if (rows.length !== cart.items.length || rows.some((row) => !byId.get(row.dataset.cartItem)?.available)) {
      openCart();
      return;
    }
    rows.forEach((row) => {
      const item = byId.get(row.dataset.cartItem);
      row.querySelector("[data-cart-qty]").textContent = item.qty;
      row.querySelector("[data-unit-price]").textContent = `${money(item.unit_price)} por unidad`;
      row.querySelector("[data-cart-subtotal]").textContent = money(item.subtotal);
      const [minus, plus] = row.querySelectorAll("[data-quantity]");
      minus.dataset.value = item.qty - 1;
      plus.dataset.value = item.qty + 1;
      minus.disabled = item.qty <= 1;
      plus.disabled = item.qty >= 99;
    });
    document.getElementById("cart-total").textContent = money(cart.total);
    document.getElementById("continue-cart").disabled = !cart.can_continue;
  }

  document.getElementById("cart-button").onclick = async () => {
    try { await refreshCart(); openCart(); }
    catch (error) { message(error.message); }
  };
  updateCount();

  function openSuggestions() {
    const cards = cart.suggestions.map((product) => `
      <article class="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-4">
        ${product.photo ? `<img src="${esc(product.photo)}" alt="${esc(product.name)}" class="h-20 w-20 shrink-0 rounded-xl object-cover">` : `<div class="flex h-20 w-20 shrink-0 items-center justify-center rounded-xl bg-orange-500/10 text-xs font-bold text-orange-400">${esc(product.category)}</div>`}
        <div class="min-w-0 flex-1"><h4 class="font-bold">${esc(product.name)}</h4><p class="text-xs text-white/60">${esc(product.description)}</p><p class="mt-1 font-bold text-orange-400">${product.discount_percent ? `<del class="mr-2 text-xs text-white/50">${money(product.original_price)}</del><span class="text-xs">${product.discount_percent}% OFF</span> ` : ''}${money(product.price)}</p></div>
        <button type="button" data-suggest="${product.id}" class="rounded-full bg-orange-500 px-4 py-2 text-sm font-bold text-black disabled:opacity-40" aria-label="Agregar ${esc(product.name)}">Agregar</button>
      </article>`).join("");
    shell("¿Sumamos algo más?", "Un buen acompañamiento para tu pedido", `
      <div class="flex-1 space-y-3 overflow-y-auto px-6 py-5">
        ${cards || '<p class="text-white/70">¡Listo! Ya sumaste los acompañamientos disponibles.</p>'}
        <p id="suggestion-feedback" role="status" class="text-sm text-orange-400"></p>
      </div>
      <div class="space-y-3 border-t border-white/10 px-6 py-4">
        <p class="flex justify-between font-bold"><span>Total de productos</span><span>${money(cart.total)}</span></p>
        <button type="button" id="skip-suggestions" class="w-full rounded-full bg-orange-500 py-3 font-bold text-black">Continuar con mi pedido</button>
        <button type="button" id="back-to-cart" class="w-full rounded-full border border-white/15 py-3 text-sm font-semibold">Revisar carrito</button>
      </div>`);
    root.querySelectorAll('[data-suggest]').forEach((button) => {
      button.onclick = async () => {
        if (busy) return;
        const name = cart.suggestions.find((product) => product.id === Number(button.dataset.suggest)).name;
        button.disabled = true;
        if (await changeCart({ action: "add", product_type: "product", product_id: Number(button.dataset.suggest), qty: 1 })) {
          openSuggestions();
          document.getElementById("suggestion-feedback").textContent = `${name} se agregó al carrito.`;
        } else button.disabled = false;
      };
    });
    document.getElementById("skip-suggestions").onclick = async () => {
      if (busy) return;
      try { await refreshCart(); if (cart.can_continue) openAddress(); else openCart(); }
      catch (error) { message(error.message); }
    };
    document.getElementById("back-to-cart").onclick = () => { if (!busy) openCart(); };
  }

  document.querySelectorAll('[data-product]').forEach((button) => {
    button.onclick = async () => {
      if (await changeCart({ action: "add", product_type: "product", product_id: Number(button.dataset.product), qty: 1 })) openCart();
    };
  });

  function closeModal() {
    const overlay = root.firstElementChild;
    if (!overlay || overlay.classList.contains("modal-closing")) return;
    const finish = () => {
      if (root.firstElementChild !== overlay) return;
      root.innerHTML = "";
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
      state = null;
      if (returnFocus && returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
      returnFocus = null;
    };
    if (reducedMotion.matches) finish();
    else {
      overlay.classList.add("modal-closing");
      closeTimer = setTimeout(finish, 180);
    }
  }
  function onKey(e) {
    if (e.key === "Escape") closeModal();
    if (e.key === "Tab") {
      const panel = root.querySelector(".modal-panel");
      if (!panel) return;
      const focusable = [...panel.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), a[href], select:not([disabled])')]
        .filter((el) => el.getClientRects().length);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (!first) { e.preventDefault(); return; }
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
    }
  }

  function shell(title, subtitle, body) {
    clearTimeout(closeTimer);
    const opening = !root.firstElementChild;
    if (opening) returnFocus = document.activeElement;
    root.innerHTML = `
      <div id="overlay" class="modal-overlay ${opening ? "modal-enter" : "modal-step"} fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center sm:p-4">
        <div role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1" class="modal-panel flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-3xl border border-white/10 bg-[#141a23] shadow-2xl sm:rounded-3xl">
          <div class="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-4">
            <div>
              <h3 id="modal-title" class="text-xl font-extrabold uppercase">${esc(title)}</h3>
              ${subtitle ? `<p class="text-sm text-white/60">${esc(subtitle)}</p>` : ""}
            </div>
            <button id="close-btn" aria-label="Cerrar" class="rounded-full p-2 text-white/60 hover:bg-white/10 hover:text-white">✕</button>
          </div>
          ${body}
        </div>
      </div>`;
    document.body.style.overflow = "hidden";
    root.querySelector(".modal-panel").focus({ preventScroll: true });
    document.removeEventListener("keydown", onKey);
    document.addEventListener("keydown", onKey);
    document.getElementById("close-btn").onclick = closeModal;
    document.getElementById("overlay").addEventListener("click", (e) => {
      if (e.target.id === "overlay") closeModal();
    });
  }

  const chip = (active) =>
    "flex cursor-pointer items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm transition " +
    (active ? "border-orange-500 bg-orange-500/15 text-white" : "border-white/10 bg-white/5 text-white/80 hover:border-white/30");

  /* ---------- Paso 1: aderezos y extras ---------- */
  function unitPrice() {
    const extrasTotal = DATA.extras.filter((e) => state.extras.includes(e.id)).reduce((s, e) => s + e.price, 0);
    return state.burger.price + extrasTotal;
  }
  const total = () => unitPrice() * state.qty;

  function openCustomize() {
    const b = state.burger;
    const aderezosHtml = DATA.aderezos
      .map(
        (a) => `
        <label class="${chip(state.aderezos.includes(a.id))}">
          <span>${esc(a.name)}</span>
          <input type="checkbox" class="accent-orange-500" data-aderezo="${a.id}" ${state.aderezos.includes(a.id) ? "checked" : ""}>
        </label>`
      )
      .join("");
    const extrasHtml = DATA.extras
      .map(
        (e) => `
        <label class="${chip(state.extras.includes(e.id))}">
          <span class="flex items-center gap-3">
            <input type="checkbox" class="accent-orange-500" data-extra="${e.id}" ${state.extras.includes(e.id) ? "checked" : ""}>
            ${esc(e.name)}
          </span>
          <span class="font-semibold text-orange-400">${e.discount_percent ? `<del class="block text-xs text-white/50">${money(e.original_price)}</del><span class="text-xs">${e.discount_percent}% OFF</span> ` : ''}+${money(e.price)}</span>
        </label>`
      )
      .join("");

    shell(
      b.name,
      b.desc,
      `
      <div class="flex-1 space-y-6 overflow-y-auto px-6 py-5">
        ${b.discount_percent ? `<p class="rounded-xl bg-orange-500/10 p-3 text-orange-400"><del class="mr-2 text-white/50">${money(b.original_price)}</del><strong>${money(b.price)} · ${b.discount_percent}% OFF</strong><span class="block text-xs">Precio de la hamburguesa. Los extras se suman aparte.</span></p>` : ''}
        <section>
          <h4 class="mb-1 font-bold uppercase text-orange-500">¿Querés aderezos?</h4>
          <p class="mb-3 text-xs text-white/50">Sin costo, elegí los que quieras</p>
          <div class="grid grid-cols-2 gap-2">${aderezosHtml}</div>
        </section>
        <section>
          <h4 class="mb-3 font-bold uppercase text-orange-500">¿Querés agregar algo?</h4>
          <div class="space-y-2">${extrasHtml}</div>
        </section>
        <section>
          <h4 class="mb-2 font-bold uppercase text-orange-500">Aclaraciones</h4>
          <textarea id="notes" rows="2" maxlength="500" placeholder="Ej: sin cebolla, bien cocida..." class="${inputCls}">${esc(state.notes)}</textarea>
        </section>
      </div>
      <div class="flex items-center gap-4 border-t border-white/10 px-6 py-4">
        <div class="flex items-center rounded-full border border-white/15">
          <button type="button" id="minus" class="h-10 w-10 text-xl hover:text-orange-500">−</button>
          <span id="qty" class="w-8 text-center font-bold">${state.qty}</span>
          <button type="button" id="plus" class="h-10 w-10 text-xl hover:text-orange-500">+</button>
        </div>
        <button type="button" id="confirm1" class="flex-1 rounded-full bg-orange-500 py-3 font-bold uppercase tracking-wide text-black transition hover:bg-orange-400">
          Agregar al carrito · <span id="total1">${money(total())}</span>
        </button>
      </div>`
    );

    const refresh = () => {
      document.getElementById("qty").textContent = state.qty;
      document.getElementById("total1").textContent = money(total());
    };
    const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

    root.querySelectorAll("[data-aderezo]").forEach((el) => {
      el.onchange = () => {
        state.aderezos = toggle(state.aderezos, Number(el.dataset.aderezo));
        el.closest("label").className = chip(el.checked);
      };
    });
    root.querySelectorAll("[data-extra]").forEach((el) => {
      el.onchange = () => {
        state.extras = toggle(state.extras, Number(el.dataset.extra));
        el.closest("label").className = chip(el.checked);
        refresh();
      };
    });
    document.getElementById("minus").onclick = () => {
      state.qty = Math.max(1, state.qty - 1);
      refresh();
    };
    document.getElementById("plus").onclick = () => {
      state.qty = Math.min(99, state.qty + 1);
      refresh();
    };
    document.getElementById("notes").oninput = (e) => (state.notes = e.target.value);
    document.getElementById("confirm1").onclick = async () => {
      state.notes = document.getElementById("notes").value.trim();
      const added = await changeCart({ action: "add", burger_id: state.burger.id,
        qty: state.qty, aderezos: state.aderezos, extras: state.extras, notes: state.notes });
      if (added) { state = null; openCart(); }
    };
  }

  /* ---------- Paso 2: dirección ---------- */
  function openAddress() {
    const d = delivery;
    let mobileStep = 1;
    shell(
      "Tus datos",
      "Elegí cómo recibir tu pedido",
      `
      <form id="addr-form" class="checkout-form flex min-h-0 flex-1 flex-col">
        <div id="checkout-scroll" class="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          <ol class="checkout-mobile checkout-steps" aria-label="Pasos de compra"><li data-checkout-step="1">1 · Datos</li><li data-checkout-step="2">2 · Entrega</li><li>Pago</li></ol>
          <details class="checkout-mobile checkout-summary"><summary>Tu pedido · ${money(cartTotal())}</summary><ul>${cart.items.map(item => `<li>${item.qty} × ${esc(item.name)} <strong>${money(item.subtotal)}</strong></li>`).join('')}</ul></details>
          <div id="customer-fields" class="space-y-4">
          <div>
            <label for="f-name" class="mb-1 block text-sm font-semibold">Nombre *</label>
            <input id="f-name" required maxlength="100" autocomplete="name" class="${inputCls}" placeholder="Tu nombre" value="${esc(d.name)}">
          </div>
          <div>
            <label for="f-phone" class="mb-1 block text-sm font-semibold">Teléfono *</label>
            <input id="f-phone" required type="tel" inputmode="tel" maxlength="30" autocomplete="tel" class="${inputCls}" placeholder="Con código de área" value="${esc(d.phone)}">
          </div>
          <fieldset class="space-y-2">
            <legend class="mb-2 text-sm font-semibold">¿Cómo lo recibís?</legend>
            <label class="${chip(d.fulfillment === "pickup")}"><span>Retiro en el local · Sin costo</span><input type="radio" name="fulfillment" value="pickup" class="accent-orange-500" ${d.fulfillment === "pickup" ? "checked" : ""}></label>
            <label class="${chip(d.fulfillment === "delivery")}"><span>Entrega a domicilio</span><input type="radio" name="fulfillment" value="delivery" class="accent-orange-500" ${d.fulfillment === "delivery" ? "checked" : ""}></label>
          </fieldset>
          </div>
          <div id="delivery-fields" class="space-y-4">
            <div>
              <label for="f-address" class="mb-1 block text-sm font-semibold">Dirección *</label>
              <input id="f-address" maxlength="250" autocomplete="street-address" class="${inputCls}" placeholder="Calle, número, piso/depto, barrio" value="${esc(d.address)}">
            </div>
            <div>
              <label for="f-locality" class="mb-1 block text-sm font-semibold">Localidad *</label>
              <input id="f-locality" maxlength="100" autocomplete="address-level2" class="${inputCls}" placeholder="Ej: Ingeniero Adolfo Sourdeaux" value="${esc(d.locality)}">
            </div>
            <div>
              <label for="f-ref" class="mb-1 block text-sm font-semibold">Aclaración (opcional)</label>
              <input id="f-ref" maxlength="250" class="${inputCls}" placeholder="Ej: portón negro, timbre 2B" value="${esc(d.reference)}">
            </div>
            <p class="text-sm text-white/60">Envío a domicilio: tarifa fija de ${money(DATA.shipping.fixed_fee)}.</p>
          </div>
          <div class="checkout-desktop space-y-4">
          <p class="flex justify-between font-bold"><span>Total de productos</span><span>${money(cartTotal())}</span></p>
          <p class="flex justify-between text-sm"><span>Envío</span><span id="shipping-fee"></span></p>
          <p class="flex justify-between font-bold text-orange-400"><span>Total final</span><span id="checkout-total"></span></p>
          </div>
          <p id="payment-notice" class="text-sm text-white/60">${DATA.payments_enabled ? "Continuarás en Mercado Pago para completar el pago. El pedido queda pendiente hasta que se confirme el cobro." : "Se guardará tu pedido pendiente de pago. El pago online todavía no está disponible; registrar el pedido no confirma su preparación."}</p>
          <p id="checkout-error" role="alert" class="text-sm text-orange-400"></p>
        </div>
        <div class="checkout-footer flex items-center gap-3 border-t border-white/10 px-6 py-4">
          <div class="checkout-mobile checkout-footer-total"><span>Total <small id="mobile-shipping-note"></small></span><strong id="mobile-checkout-total"></strong></div>
          <button type="button" id="back" class="rounded-full border border-white/15 px-5 py-3 text-sm font-semibold hover:bg-white/10">Volver</button>
          <button type="submit" id="pay" aria-describedby="payment-notice" class="flex-1 rounded-full bg-orange-500 py-3 font-bold uppercase tracking-wide text-black disabled:cursor-not-allowed disabled:opacity-40">
            ${DATA.payments_enabled ? "Pagar con Mercado Pago" : "Registrar pedido"}
          </button>
        </div>
      </form>`
    );

    const name = document.getElementById("f-name");
    const phone = document.getElementById("f-phone");
    const address = document.getElementById("f-address");
    const locality = document.getElementById("f-locality");
    const ref = document.getElementById("f-ref");
    document.getElementById('addr-form').addEventListener('checkout-layout', () => sync());
    const sync = () => {
      d.name = name.value;
      d.phone = phone.value;
      d.address = address.value;
      d.locality = locality.value;
      d.reference = ref.value;
      d.fulfillment = root.querySelector('[name="fulfillment"]:checked').value;
      const isDelivery = d.fulfillment === "delivery";
      if (!isDelivery) mobileStep = 1;
      const firstStep = mobileCheckout.matches && mobileStep === 1;
      document.getElementById('customer-fields').hidden = mobileCheckout.matches && mobileStep === 2;
      document.getElementById("delivery-fields").hidden = !isDelivery || firstStep;
      address.required = isDelivery && !firstStep;
      locality.required = isDelivery && !firstStep;
      root.querySelectorAll('[data-checkout-step]').forEach(el => {
        el.hidden = el.dataset.checkoutStep === '2' && !isDelivery;
        if (Number(el.dataset.checkoutStep) === mobileStep) el.setAttribute('aria-current', 'step');
        else el.removeAttribute('aria-current');
      });
      document.getElementById("shipping-fee").textContent = isDelivery ? money(DATA.shipping.fixed_fee) : "Sin costo";
      document.getElementById("checkout-total").textContent = money(cart.total + (isDelivery ? DATA.shipping.fixed_fee : 0));
      document.getElementById('mobile-checkout-total').textContent = money(cart.total + (isDelivery ? DATA.shipping.fixed_fee : 0));
      document.getElementById('mobile-shipping-note').textContent = isDelivery ? '· envío incluido' : '· retiro sin costo';
      const pay = document.getElementById('pay');
      pay.disabled = submittingOrder;
      if (!submittingOrder) pay.textContent = firstStep && isDelivery ? 'Continuar con la entrega' : (DATA.payments_enabled ? 'Pagar con Mercado Pago' : 'Registrar pedido');
      root.querySelectorAll('[name="fulfillment"]').forEach((el) => {
        el.closest("label").className = chip(el.checked);
      });
    };
    [name, phone, ref, address, locality].forEach((el) => el.addEventListener("input", sync));
    root.querySelectorAll('[name="fulfillment"]').forEach((el) => el.addEventListener("change", sync));
    sync();
    document.getElementById("back").onclick = () => {
      sync();
      if (mobileCheckout.matches && mobileStep === 2) {
        mobileStep = 1;
        sync();
        document.getElementById('checkout-scroll').scrollTop = 0;
        name.focus({preventScroll: true});
        return;
      }
      openCart();
    };
    document.getElementById("addr-form").onsubmit = async (e) => {
      e.preventDefault();
      if (submittingOrder) return;
      sync();
      if (mobileCheckout.matches && mobileStep === 1 && d.fulfillment === 'delivery') {
        if (!name.reportValidity() || !phone.reportValidity()) return;
        mobileStep = 2;
        sync();
        document.getElementById('checkout-scroll').scrollTop = 0;
        address.focus({preventScroll: true});
        return;
      }
      const button = document.getElementById("pay");
      const errorBox = document.getElementById("checkout-error");
      submittingOrder = true;
      button.disabled = true;
      button.textContent = "Guardando…";
      errorBox.textContent = "";
      try {
        const response = await fetch(checkoutUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value },
          body: JSON.stringify({ ...d, checkout_token: cart.checkout_token, products_total: cart.total }),
        });
        const result = await response.json();
        if (!response.ok) {
          const details = result.fields ? Object.values(result.fields).flat().join(" ") : "";
          throw new Error([result.error, details].filter(Boolean).join(" ") || "No se pudo guardar el pedido.");
        }
        cart = { items: [], count: 0, total: 0, can_continue: false, checkout_token: null };
        suggestionsShown = false;
        updateCount();
        shell(`Pedido #${result.number}`, "Guardado · Pendiente de pago", `
          <div class="space-y-4 overflow-y-auto px-6 py-5">
            <p>Tu pedido quedó registrado. La preparación queda pendiente de confirmar el pago.</p>
            <p class="font-bold">Productos: ${money(result.products_total)}</p>
            <p class="text-sm text-white/60">${result.delivery_fee ? `Envío: ${money(result.delivery_fee)}` : "Retiro en el local, sin costo de envío."}</p>
            <p class="font-bold text-orange-400">Total: ${money(result.total)}</p>
            ${result.payment_start_url ? '<button type="button" id="open-payment" class="w-full rounded-full bg-orange-500 py-3 font-bold text-black">Continuar en Mercado Pago</button><p id="payment-error" role="alert" class="text-sm text-orange-400"></p>' : '<p class="text-sm text-white/60">El pago online aún no está disponible.</p>'}
          </div>
          <div class="border-t border-white/10 px-6 py-4"><button type="button" id="order-done" class="w-full rounded-full bg-orange-500 py-3 font-bold text-black">Volver al menú</button></div>`);
        document.getElementById("order-done").onclick = closeModal;
        if (result.payment_start_url) {
          const launch = async () => {
            const pay = document.getElementById("open-payment");
            const error = document.getElementById("payment-error");
            pay.disabled = true;
            error.textContent = "Abriendo Mercado Pago…";
            try {
              const response = await fetch(result.payment_start_url, { method: "POST", headers: {
                "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value,
              } });
              const payment = await response.json();
              if (!response.ok) throw new Error(payment.error || "No se pudo abrir el pago.");
              window.location.assign(payment.checkout_url);
            } catch (failure) {
              if (error.isConnected) { error.textContent = failure.message; pay.disabled = false; }
            }
          };
          document.getElementById("open-payment").onclick = launch;
          launch();
        }
      } catch (error) {
        errorBox.textContent = error.message || "No hay conexión. Intentá nuevamente.";
      } finally {
        submittingOrder = false;
        if (button.isConnected) sync();
        button.textContent = DATA.payments_enabled ? "Pagar con Mercado Pago" : "Registrar pedido";
      }
    };
  }

  /* ---------- Click en una hamburguesa ---------- */
  document.querySelectorAll(".burger-card").forEach((card) => {
    card.addEventListener("click", () => {
      state = {
        burger: DATA.burgers[card.dataset.burger],
        qty: 1,
        aderezos: [],
        extras: [],
        notes: "",
      };
      openCustomize();
    });
  });
})();
