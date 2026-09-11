"use strict";
(() => {
  const key = "netrevive.theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference;
  try { preference = localStorage.getItem(key); } catch {}
  const apply = () => {
    const dark = preference === "dark" || (preference !== "light" && system.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const choice = ["light", "dark"].includes(preference) ? preference : "system";
    document.querySelectorAll("[data-theme-choice]").forEach(button => {
      const active = button.dataset.themeChoice === choice;
      button.setAttribute("aria-pressed", String(active));
      const trigger = document.getElementById("theme-trigger");
      if (active && trigger) {
        trigger.replaceChildren(button.querySelector("svg").cloneNode(true));
        const label = `Appearance: ${button.querySelector("span").textContent}`;
        trigger.setAttribute("aria-label", label);
        trigger.title = label;
      }
    });
  };
  apply();
  system.addEventListener("change", apply);
  window.addEventListener("storage", event => {
    if (event.key === key || event.key === null) {
      preference = event.newValue;
      apply();
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    const control = document.querySelector(".theme-control");
    const trigger = document.getElementById("theme-trigger");
    const options = document.getElementById("theme-options");
    const buttons = [...options.querySelectorAll("[data-theme-choice]")];
    const close = (restoreFocus = false) => {
      options.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      if (restoreFocus) trigger.focus();
    };
    const open = (focusChoice = false) => {
      options.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      if (focusChoice) options.querySelector('[aria-pressed="true"]').focus();
    };
    trigger.addEventListener("click", () => options.hidden ? open() : close());
    trigger.addEventListener("keydown", event => {
      if (event.key === "ArrowDown") { event.preventDefault(); event.stopPropagation(); open(true); }
    });
    control.addEventListener("keydown", event => {
      if (event.key === "Escape") { event.preventDefault(); close(true); }
      if (!options.hidden && buttons.includes(document.activeElement)) {
        const index = buttons.indexOf(document.activeElement);
        const next = {ArrowDown:(index+1)%3, ArrowUp:(index+2)%3, Home:0, End:2}[event.key];
        if (next !== undefined) { event.preventDefault(); buttons[next].focus(); }
      }
    });
    control.addEventListener("focusout", event => {
      if (event.relatedTarget && !control.contains(event.relatedTarget)) close();
    });
    document.addEventListener("click", event => {
      if (!control.contains(event.target)) close();
    });
    buttons.forEach(button => {
      button.addEventListener("click", () => {
        preference = button.dataset.themeChoice;
        try {
          if (preference === "system") localStorage.removeItem(key);
          else localStorage.setItem(key, preference);
        } catch {}
        apply();
        close(true);
      });
    });
  });
})();
