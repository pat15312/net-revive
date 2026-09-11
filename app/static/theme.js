"use strict";
(() => {
  const key = "netrevive.theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference;
  try { preference = localStorage.getItem(key); } catch {}
  const apply = () => {
    const dark = preference === "dark" || (preference !== "light" && system.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const select = document.getElementById("theme-select");
    if (select) select.value = ["light", "dark"].includes(preference) ? preference : "system";
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
    document.getElementById("theme-select").addEventListener("change", event => {
      preference = event.target.value;
      try {
        if (preference === "system") localStorage.removeItem(key);
        else localStorage.setItem(key, preference);
      } catch {}
      apply();
    });
  });
})();
