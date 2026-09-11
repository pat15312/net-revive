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
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === choice));
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
    document.querySelectorAll("[data-theme-choice]").forEach(button => {
      button.addEventListener("click", () => {
        preference = button.dataset.themeChoice;
        try {
          if (preference === "system") localStorage.removeItem(key);
          else localStorage.setItem(key, preference);
        } catch {}
        apply();
      });
    });
  });
})();
