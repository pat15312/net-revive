"use strict";
const root = document.querySelector("#app");
let csrf = document.querySelector('meta[name="csrf-token"]').content;
let session,
  config,
  dashboard,
  sites = [],
  wizardStep = 0,
  historyOffset = 0;
let pageTab = location.hash.slice(1) || "general";
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const $ = (selector) => document.querySelector(selector);
const field = (label, name, value = "", type = "text", extra = "") =>
  `<label for="${name}">${label}</label><input id="${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}>`;
const check = (label, name, checked = false) =>
  `<label class="check"><input type="checkbox" name="${name}" ${checked ? "checked" : ""}> <span>${label}</span></label>`;
const formData = (form) => Object.fromEntries(new FormData(form));
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (node.hidden = true), 6500);
}
async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((e) => `${e.loc.slice(1).join(" ")}: ${e.msg}`).join(" · ")
      : typeof detail === "object"
        ? detail.message
        : detail;
    throw new Error(message || "The request could not be completed.");
  }
  if (data.csrf) csrf = data.csrf;
  return data;
}
function bindForm(id, handler) {
  const form = document.getElementById(id);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    if (submit?.disabled) return;
    if (submit) submit.disabled = true;
    form.querySelector(".error")?.remove();
    try {
      await handler(formData(form), form);
    } catch (error) {
      const message = document.createElement("p");
      message.className = "error";
      message.setAttribute("role", "alert");
      message.textContent = error.message;
      form.append(message);
    } finally {
      if (submit) submit.disabled = false;
    }
  });
}
function heading(title, description, badge = "Local & private") {
  return `<div class="page-heading"><div><p class="eyebrow">LOCAL NETWORK RECOVERY</p><h1>${esc(title)}</h1><p>${esc(description)}</p></div><span class="pill">${esc(badge)}</span></div>`;
}
function authView(firstRun) {
  root.innerHTML =
    heading(
      firstRun ? "Welcome to NetRevive" : "Administrator sign-in",
      firstRun
        ? "A little preparation. A simpler way to get connected again."
        : "Manage your local network recovery settings.",
    ) +
    `<section class="panel narrow"><span class="step-label">${firstRun ? "01 / SECURE YOUR SETTINGS" : "ADMIN ACCESS"}</span><h2>${firstRun ? "Create your administrator password" : "Welcome back"}</h2><p>${firstRun ? "Only administrators can change equipment and restart groups. People using the dashboard won’t need a password." : "Enter your administrator password to continue."}</p><form id="auth">${field("Administrator password", "password", "", "password", `required minlength="${firstRun ? 12 : 1}" maxlength="256" autocomplete="${firstRun ? "new-password" : "current-password"}"`)}${firstRun ? field("Confirm password", "repeat", "", "password", 'required autocomplete="new-password"') + '<p class="help">Use at least 12 characters. Store this password somewhere safe.</p>' : ""}<div class="actions"><button class="primary" type="submit">${firstRun ? "Create password & continue" : "Sign in"} <span aria-hidden="true">→</span></button></div></form></section>`;
  bindForm("auth", async (data) => {
    if (firstRun && data.password !== data.repeat)
      throw new Error("The passwords do not match.");
    await api(firstRun ? "/api/setup" : "/api/login", "POST", {
      password: data.password,
    });
    await boot();
  });
}
async function boot() {
  session = await api("/api/session");
  if (!session.has_password) return authView(true);
  if (!session.setup_complete || location.pathname !== "/") {
    if (!session.admin) return authView(false);
    config = await api("/api/admin/config");
    return adminView();
  }
  await refreshDashboard(true);
}
const tabs = [
  ["general", "General"],
  ["users", "Users"],
  ["unifi", "UniFi"],
  ["groups", "Restart Groups"],
  ["monitoring", "Health Monitoring"],
  ["history", "Restart History"],
];
const wizardTabs = ["general", "unifi", "groups", "users", "monitoring"];
function adminView() {
  const setup = !config.setup_complete;
  if (setup) pageTab = wizardTabs[wizardStep];
  root.innerHTML =
    heading(
      setup ? "Set up NetRevive" : "Administration",
      setup
        ? "Build a safe, simple way to restart your network equipment."
        : "Make recovery work for your network.",
    ) +
    (setup
      ? `<div class="steps" aria-label="Setup progress">${wizardTabs.map((t, i) => `<span class="${i === wizardStep ? "current" : ""}">${i + 1}. ${tabs.find((x) => x[0] === t)[1]}</span>`).join("")}</div>`
      : `<nav class="tabs" aria-label="Admin sections">${tabs.map(([id, label]) => `<a class="${pageTab === id ? "active" : ""}" href="#${id}">${label}</a>`).join("")}</nav>`) +
    '<div id="admin-content"></div>' +
    (setup
      ? `<div class="actions"><button class="secondary" id="wizard-back" ${wizardStep === 0 ? "disabled" : ""}>← Back</button><button class="primary" id="wizard-next">${wizardStep === 4 ? "Finish setup" : "Continue →"}</button><span class="help">Save your changes before continuing.</span></div>`
      : '<div class="actions"><button class="secondary small" id="logout">Sign out</button><a href="/">Back to dashboard</a></div>');
  $("#hostname").textContent = config.settings.hostname;
  if (!tabs.some((x) => x[0] === pageTab)) pageTab = "general";
  ({
    general: generalView,
    users: usersView,
    unifi: unifiView,
    groups: groupsView,
    monitoring: monitoringView,
    history: historyView,
  })[pageTab]();
  $("#logout")?.addEventListener("click", async () => {
    try {
      await api("/api/logout", "POST");
      location.href = "/";
    } catch (e) {
      toast(e.message);
    }
  });
  $("#wizard-back")?.addEventListener("click", () => {
    wizardStep--;
    adminView();
  });
  $("#wizard-next")?.addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      config = await api("/api/admin/config");
      if (
        pageTab === "unifi" &&
        (!config.settings.site_id || !config.targets.some((t) => t.available))
      )
        throw new Error(
          "Test the connection, choose a site, and discover its PoE ports first.",
        );
      if (pageTab === "groups" && !config.groups.some((g) => g.enabled))
        throw new Error("Create at least one enabled restart group first.");
      if (pageTab === "users" && !config.operators.length)
        throw new Error("Add at least one operator first.");
      if (wizardStep === 4) {
        await api("/api/admin/setup/finish", "POST");
        location.href = "/";
        return;
      }
      wizardStep++;
      adminView();
    } catch (e) {
      toast(e.message);
      event.target.disabled = false;
    }
  });
}
window.addEventListener("hashchange", () => {
  if (session?.admin && config?.setup_complete) {
    pageTab = location.hash.slice(1) || "general";
    historyOffset = 0;
    adminView();
  }
});
async function reloadConfig() {
  config = await api("/api/admin/config");
}
function generalView() {
  const s = config.settings;
  $("#admin-content").innerHTML =
    `<section class="panel"><h2>A familiar place to reconnect</h2><p>Give your dashboard a title and an easy-to-remember local address.</p><form id="general">${field("Application display title", "title", s.title, "text", 'required maxlength="80"')}${field("Friendly hostname or URL", "hostname", s.hostname, "text", 'required maxlength="253"')}${field("Display timezone", "timezone", s.timezone, "text", 'required list="timezones"')}<datalist id="timezones"><option value="Europe/London"><option value="Etc/UTC"><option value="America/New_York"><option value="America/Los_Angeles"><option value="Europe/Paris"><option value="Asia/Tokyo"><option value="Australia/Sydney"></datalist><div class="notice">Create a DNS record pointing <strong>${esc(s.hostname)}</strong> to the IP address of the NetRevive Docker host. Changing this setting does not create or modify a DNS record.</div><button class="primary" type="submit">Save general settings</button></form></section>`;
  bindForm("general", async (data) => {
    await api("/api/admin/general", "PUT", data);
    await reloadConfig();
    generalView();
    $("#hostname").textContent = config.settings.hostname;
    toast("General settings saved.");
  });
}
function usersView() {
  $("#admin-content").innerHTML =
    `<section class="panel"><h2>Who can restart equipment?</h2><p>These names identify restart activity. Operators use the dashboard without signing in.</p>${config.operators.map((u) => `<div class="list-row"><div><strong>${esc(u.name)}</strong><p>Display order: ${u.display_order}</p></div><div class="actions"><button class="secondary small" data-edit-user="${u.id}">Edit</button><button class="danger small" data-delete-user="${u.id}">Remove</button></div></div>`).join("") || '<p class="notice">Add the people who will use NetRevive.</p>'}<div id="user-editor"></div></section>`;
  userEditor();
  document
    .querySelectorAll("[data-edit-user]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          userEditor(
            config.operators.find((u) => u.id === Number(b.dataset.editUser)),
          )),
    );
  document.querySelectorAll("[data-delete-user]").forEach(
    (b) =>
      (b.onclick = () =>
        askDelete(
          "Remove operator?",
          "Their previous restart history will remain available.",
          async () => {
            await api(`/api/admin/operators/${b.dataset.deleteUser}`, "DELETE");
            await reloadConfig();
            usersView();
          },
        )),
  );
}
function userEditor(user = {}) {
  $("#user-editor").innerHTML =
    `<h3>${user.id ? "Edit operator" : "Add an operator"}</h3><form id="user-form"><div class="fields"><div>${field("Name", "name", user.name || "", "text", 'required maxlength="80"')}</div><div>${field("Display order", "display_order", user.display_order || 0, "number", 'required min="-100000" max="100000"')}</div></div><div class="actions"><button class="primary" type="submit">${user.id ? "Save operator" : "Add operator"}</button>${user.id ? '<button class="secondary" type="button" id="cancel-user">Cancel</button>' : ""}</div></form>`;
  $("#cancel-user")?.addEventListener("click", () => userEditor());
  bindForm("user-form", async (data) => {
    await api(
      "/api/admin/operators" + (user.id ? "/" + user.id : ""),
      user.id ? "PUT" : "POST",
      { name: data.name, display_order: Number(data.display_order) },
    );
    await reloadConfig();
    usersView();
    toast("Operator saved.");
  });
}
function unifiView() {
  const s = config.settings;
  $("#admin-content").innerHTML =
    `<section class="panel"><h2>Connect to UniFi</h2><p>Enter the local HTTPS address of the console or server running UniFi Network, such as https://controller.lan or https://controller.lan:8443. Keep the port if present, but remove any path after it. NetRevive connects directly to this address.</p><form id="unifi-form">${field("Controller URL", "controller_url", s.controller_url, "url", 'required placeholder="https://controller.lan"')}<label for="api_prefix">Controller type</label><select name="api_prefix" id="api_prefix"><option value="/proxy/network/integration/v1" ${s.api_prefix.includes("proxy") ? "selected" : ""}>UniFi OS console</option><option value="/integration/v1" ${!s.api_prefix.includes("proxy") ? "selected" : ""}>Self-hosted Network application</option></select>${s.api_key_from_environment ? '<p class="notice">The API key is managed through the container environment.</p>' : field(s.api_key_configured ? "Replace API key (leave blank to keep it)" : "API key", "api_key", "", "password", 'autocomplete="off" maxlength="4096"')}<p class="help">Open UniFi Network on your local controller and find Integrations for the API documentation and key setup supported by your version. The menu location varies by release. See the <a href="https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API" target="_blank" rel="noopener noreferrer">official UniFi API guide</a>. After saving, NetRevive never sends the stored key back to your browser.</p>${check("Verify the controller’s TLS certificate (recommended)", "verify_tls", s.verify_tls)}<p class="help">Self-signed certificates and certificates that do not match the Controller URL will fail verification. To keep verification enabled, use a matching address and a certificate trusted by NetRevive. Disabling verification keeps HTTPS encryption but allows controller impersonation.</p><div class="actions"><button class="primary" type="submit">Save connection</button><button class="secondary" type="button" id="test-unifi">Test UniFi connection</button></div><div id="connection-result" role="status"></div></form></section><section class="panel"><h2>Site & PoE equipment</h2><p>Select a site, then discover its switches and restartable ports.</p><form id="site-form"><label for="site">UniFi site</label><select id="site" name="site_id" required><option value="">Choose a site</option>${sites.map((site) => `<option value="${esc(site.id)}" ${site.id === s.site_id ? "selected" : ""}>${esc(site.name)}</option>`).join("")}${s.site_id && !sites.some((x) => x.id === s.site_id) ? `<option selected value="${esc(s.site_id)}">Configured site — test connection to refresh names</option>` : ""}</select><div class="actions"><button class="primary" type="submit">Save site & discover ports</button></div></form><div id="target-inventory"></div></section>`;
  const form = $("#unifi-form");
  const connectionData = () => {
    const data = Object.fromEntries(new FormData(form));
    return {
      controller_url: data.controller_url.trim().replace(/\/$/, ""),
      api_prefix: data.api_prefix,
      site_id: s.site_id,
      verify_tls: !!data.verify_tls,
      api_key: (data.api_key || "").trim(),
    };
  };
  const hasChanges = () => {
    const data = connectionData();
    return !!data.api_key || ["controller_url", "api_prefix", "verify_tls"].some(key => data[key] !== s[key]);
  };
  let revision = 0;
  form.addEventListener("input", () => {
    revision++;
    sites = [];
    $("#site").innerHTML = '<option value="">Test the connection to retrieve sites</option>';
    $("#connection-result").textContent = "";
  });
  bindForm("unifi-form", async () => {
    await api("/api/admin/unifi", "PUT", connectionData());
    await reloadConfig();
    unifiView();
    toast(sites.length ? "Connection saved. Select your UniFi site below." : "Connection saved. Test the connection to retrieve sites.");
  });
  $("#test-unifi").onclick = async (event) => {
    if (!form.reportValidity()) return;
    const testedRevision = revision;
    event.target.disabled = true;
    $("#connection-result").textContent = "Testing connection…";
    try {
      const result = await api("/api/admin/unifi/test", "POST", connectionData());
      if (revision !== testedRevision || !form.isConnected) return;
      sites = result.sites;
      $("#site").innerHTML = '<option value="">Choose a site</option>' + sites.map(site =>
        `<option value="${esc(site.id)}" ${site.id === s.site_id ? "selected" : ""}>${esc(site.name)}</option>`
      ).join("");
      $("#connection-result").innerHTML = hasChanges()
        ? '<p class="notice">Connected and authenticated. These settings have not been saved. Click Save connection to use them.</p>'
        : '<p class="notice">Connected and authenticated. Select your UniFi site below.</p>';
    } catch (e) {
      if (revision !== testedRevision || !form.isConnected) return;
      $("#connection-result").innerHTML =
        `<p class="error">${esc(e.message)}</p>`;
    } finally {
      event.target.disabled = false;
    }
  };
  bindForm("site-form", async (data) => {
    if (hasChanges()) throw new Error("Save connection before selecting a site and discovering ports.");
    await api("/api/admin/unifi", "PUT", {
      controller_url: config.settings.controller_url,
      api_prefix: config.settings.api_prefix,
      site_id: data.site_id,
      verify_tls: config.settings.verify_tls,
    });
    const result = await api("/api/admin/unifi/discover", "POST");
    await reloadConfig();
    unifiView();
    toast(`Discovery complete: ${result.target_count} PoE ports found.`);
  });
  renderInventory();
}
const expandedInventorySwitches = new Set();
function renderInventory() {
  const targets = config.targets;
  const switches = new Map();
  for (const target of targets) {
    const key = JSON.stringify([target.site_id, target.switch_id]);
    if (!switches.has(key)) switches.set(key, { name: target.switch_name, ports: [] });
    switches.get(key).ports.push(target);
  }
  const inventory = $("#target-inventory");
  inventory.innerHTML = targets.length
    ? `<div class="section-head"><h3>Discovered PoE ports</h3><span class="muted">${targets.length} ports · ${switches.size} ${switches.size === 1 ? "switch" : "switches"}</span></div>${[...switches].map(([key, device]) =>
      `<details class="inventory-switch" data-switch="${esc(key)}" ${expandedInventorySwitches.has(key) ? "open" : ""}><summary>${esc(device.name)} <span class="muted switch-count">${device.ports.length} ${device.ports.length === 1 ? "port" : "ports"}</span></summary><div class="switch-ports">${device.ports.sort((a, b) => a.port_number - b.port_number).map(t =>
        `<div class="list-row"><div><strong>${esc(t.label || t.port_name || "Port " + t.port_number)}</strong><p>Port ${t.port_number}</p><span class="badge">${!t.enabled ? "Disabled" : t.available ? "Available" : "Unavailable — check UniFi"}</span></div><button class="secondary small" data-target="${t.id}">Edit label & availability</button></div>`
      ).join("")}</div></details>`
    ).join("")}`
    : '<p class="notice">No ports discovered yet. Discovery lists PoE-capable ports with their switch names.</p>';
  inventory.querySelectorAll("[data-switch]").forEach(section => {
    section.addEventListener("toggle", () => {
      if (!section.isConnected) return;
      if (section.open) expandedInventorySwitches.add(section.dataset.switch);
      else expandedInventorySwitches.delete(section.dataset.switch);
    });
  });
  inventory.querySelectorAll("[data-target]").forEach(
    (button) =>
      (button.onclick = () => {
        const t = targets.find((t) => t.id === Number(button.dataset.target));
        const dialog = document.createElement("dialog");
        dialog.innerHTML = `<h2>Edit PoE target</h2><p>${esc(t.switch_name)} / Port ${t.port_number}</p><form id="target-form">${field("Friendly label", "label", t.label, "text", 'maxlength="100"')}${check("Enabled for restart groups", "enabled", t.enabled)}<div class="actions"><button type="submit" class="primary">Save target</button><button type="button" class="secondary" id="close-target">Cancel</button></div></form>`;
        document.body.append(dialog);
        dialog.showModal();
        dialog.addEventListener("close", () => dialog.remove());
        $("#close-target").onclick = () => dialog.close();
        bindForm("target-form", async (data) => {
          await api(`/api/admin/targets/${t.id}`, "PUT", {
            label: data.label,
            enabled: !!data.enabled,
          });
          dialog.close();
          await reloadConfig();
          renderInventory();
          inventory.querySelector(`[data-target="${t.id}"]`)?.focus({ preventScroll: true });
        });
      }),
  );
}
function groupsView() {
  $("#admin-content").innerHTML =
    `<section class="panel"><div class="section-head"><div><h2>Restart Groups</h2><p>One clear action for each set of equipment.</p></div><button class="primary small" id="add-group">+ Add group</button></div>${config.groups.map((g) => `<div class="list-row"><div><strong>${esc(g.name)}</strong><p>${esc(g.button_label)} · ${g.target_ids.length} ${g.target_ids.length === 1 ? "target" : "targets"} · ${g.enabled ? "Enabled" : "Disabled"}</p><p>Order ${g.display_order} · ${g.lockout_seconds === null ? "Default" : g.lockout_seconds + "s"} lockout · ${g.recovery_mode === "network" ? "Network health" : "No recovery monitoring"}</p></div><div class="actions"><button class="secondary small" data-edit-group="${g.id}">Edit</button><button class="danger small" data-delete-group="${g.id}">Delete</button></div></div>`).join("") || '<div class="empty"><h3>Create your first restart group</h3><p>Choose a name people recognise and assign the equipment it will restart.</p></div>'}</section><div id="group-editor"></div>`;
  $("#add-group").onclick = () => groupEditor();
  document
    .querySelectorAll("[data-edit-group]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          groupEditor(
            config.groups.find((g) => g.id === Number(b.dataset.editGroup)),
          )),
    );
  document.querySelectorAll("[data-delete-group]").forEach(
    (b) =>
      (b.onclick = () =>
        askDelete(
          "Delete restart group?",
          "Its restart history and existing equipment lockouts will be kept.",
          async () => {
            await api(`/api/admin/groups/${b.dataset.deleteGroup}`, "DELETE");
            await reloadConfig();
            groupsView();
          },
        )),
  );
  if (!config.groups.length) groupEditor();
}
function groupEditor(
  group = {
    name: "",
    button_label: "",
    description: "",
    enabled: true,
    display_order: 0,
    lockout_seconds: null,
    recovery_mode: "network",
    target_ids: [],
  },
) {
  $("#group-editor").innerHTML =
    `<section class="panel"><h2>${group.id ? "Edit restart group" : "New restart group"}</h2><form id="group-form"><div class="fields"><div>${field("Group name", "name", group.name, "text", 'required maxlength="80" placeholder="Router"')}</div><div>${field("Button label", "button_label", group.button_label, "text", 'required maxlength="80" placeholder="Restart Router"')}</div></div><label for="description">Description (optional)</label><textarea id="description" name="description" maxlength="500">${esc(group.description)}</textarea><div class="fields"><div>${field("Display order", "display_order", group.display_order, "number", 'required min="-100000" max="100000"')}</div><div>${field("Lockout in seconds (blank uses default)", "lockout_seconds", group.lockout_seconds ?? "", "number", 'min="10" max="86400"')}</div></div><label for="recovery_mode">Recovery monitoring</label><select id="recovery_mode" name="recovery_mode"><option value="network" ${group.recovery_mode === "network" ? "selected" : ""}>Network health — routers, modems & gateways</option><option value="none" ${group.recovery_mode === "none" ? "selected" : ""}>None — access points & other equipment</option></select><p class="help">Network health checks DNS and internet access from this server. It cannot confirm that an access point or another individual device is ready.</p>${check("Show this group on the dashboard", "enabled", group.enabled)}<label>Assigned PoE targets</label><div class="target-list">${config.targets.map((t) => `<label class="check"><input type="checkbox" name="target_ids" value="${t.id}" ${group.target_ids.includes(t.id) ? "checked" : ""}><span><strong>${esc(t.label || t.port_name || "Port " + t.port_number)}</strong><small>${esc(t.switch_name)} / Port ${t.port_number} ${!t.enabled ? "· Disabled" : !t.available ? "· Unavailable" : ""}</small></span></label>`).join("") || "<p>Discover your UniFi ports before creating a group.</p>"}</div><div class="notice warning">All selected PoE ports will be power-cycled when this Restart Group is triggered. Ensure every target is correct.</div>${check("I have checked and confirm all selected targets.", "confirm_targets")}<p class="help">A port may belong to several groups. Shared equipment lockouts protect every group that uses it.</p><div class="actions"><button class="primary" type="submit">Save restart group</button><button class="secondary" type="button" id="cancel-group">Cancel</button></div></form></section>`;
  $("#cancel-group").onclick = () => $("#group-editor").replaceChildren();
  bindForm("group-form", async (data, form) => {
    const payload = {
      name: data.name,
      button_label: data.button_label,
      description: data.description,
      enabled: !!data.enabled,
      display_order: Number(data.display_order),
      lockout_seconds:
        data.lockout_seconds === "" ? null : Number(data.lockout_seconds),
      recovery_mode: data.recovery_mode,
      target_ids: new FormData(form).getAll("target_ids").map(Number),
      confirm_targets: !!data.confirm_targets,
    };
    await api(
      "/api/admin/groups" + (group.id ? "/" + group.id : ""),
      group.id ? "PUT" : "POST",
      payload,
    );
    await reloadConfig();
    groupsView();
    toast("Restart group saved.");
  });
}
function monitoringView() {
  const s = config.settings;
  $("#admin-content").innerHTML =
    `<section class="panel"><h2>Health & restart protection</h2><p>Health checks run in the background, even when no one has the dashboard open.</p><form id="monitoring-form"><div class="fields">${[
      ["Default restart lockout (seconds)", "lockout_seconds", 10, 86400],
      ["Health-check interval (seconds)", "health_interval", 5, 300],
      ["Recovery timeout (seconds)", "recovery_timeout", 30, 7200],
      ["Consecutive healthy checks for recovery", "recovery_successes", 2, 20],
    ]
      .map(
        ([label, key, min, max]) =>
          `<div>${field(label, key, s[key], "number", `required min="${min}" max="${max}"`)}</div>`,
      )
      .join(
        "",
      )}</div><label for="dns_names">DNS test names (one per line)</label><textarea id="dns_names" name="dns_names" required>${esc(s.dns_names.join("\n"))}</textarea><p class="help">Uses the container’s normal DNS resolver. Multiple names reduce false alarms; upstream resolver caching may still affect results.</p><label for="internet_targets">Internet test destinations (IP address and port, one per line)</label><textarea id="internet_targets" name="internet_targets" required>${esc(s.internet_targets.map((t) => `${t.ip} ${t.port}`).join("\n"))}</textarea><p class="help">Example: 1.1.1.1 443. Connections use IP addresses directly, independently of DNS.</p>${field("Successful destinations required", "internet_threshold", s.internet_threshold, "number", 'required min="1" max="9"')}<p class="help">Use at least two destinations and allow at least one to fail. Health is advisory; a healthy network does not prevent a deliberate restart.</p><button class="primary" type="submit">Save monitoring settings</button></form></section>`;
  bindForm("monitoring-form", async (data) => {
    const payload = {};
    for (const key of [
      "lockout_seconds",
      "health_interval",
      "recovery_timeout",
      "recovery_successes",
      "internet_threshold",
    ])
      payload[key] = Number(data[key]);
    payload.dns_names = data.dns_names
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);
    payload.internet_targets = data.internet_targets
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean)
      .map((line) => {
        const [ip, port, ...extra] = line.split(/\s+/);
        if (!port || extra.length)
          throw new Error(
            "Use one IP address followed by a port on each line.",
          );
        return { ip, port: Number(port) };
      });
    await api("/api/admin/monitoring", "PUT", payload);
    await reloadConfig();
    toast("Monitoring settings saved.");
  });
}
function duration(seconds) {
  seconds = Math.max(0, Math.ceil(seconds));
  return seconds >= 60
    ? `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    : `${seconds}s`;
}
function timeLabel(timestamp, timezone) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(timestamp * 1000));
}
function resultText(event) {
  if (event.result === "dispatching") return "Sending restart requests…";
  if (event.result === "interrupted")
    return "Restart interrupted. An administrator should check the result.";
  if (event.result === "unsuccessful")
    return "No restart requests were confirmed. Check detailed history.";
  const prefix =
    event.result === "partial" ? "Some restart requests failed. " : "";
  if (event.recovery_status === "monitoring")
    return prefix + "Waiting for stable network health…";
  if (event.recovery_status === "recovered")
    return (
      prefix +
      (event.saw_unhealthy
        ? "Network recovered after "
        : "Network health confirmed after ") +
      duration(event.recovery_duration)
    );
  if (event.recovery_status === "timed_out")
    return prefix + "Network recovery was not confirmed before the timeout.";
  return (
    prefix +
    `${event.accepted_count} of ${event.target_count} power-cycle requests accepted.`
  );
}
async function historyView() {
  $("#admin-content").innerHTML =
    '<section class="panel"><h2>Restart history</h2><p role="status">Loading history…</p></section>';
  try {
    const { events } = await api(`/api/admin/history?offset=${historyOffset}`);
    if (pageTab !== "history") return;
    $("#admin-content").innerHTML =
      `<section class="panel"><h2>Restart history</h2><p>Configuration and equipment details are captured at the time of each restart.</p>${events.map((e) => `<details><summary>${esc(timeLabel(e.created_at, config.settings.timezone))} · ${esc(e.button_label)} · ${esc(e.operator)}</summary><p><span class="badge ${esc(e.result)}">${esc(e.result)}</span> ${esc(resultText(e))}</p><p>Before restart: Internet ${e.health_before.internet === true ? "working" : e.health_before.internet === false ? "unavailable" : "unknown"} · DNS ${e.health_before.dns === true ? "working" : e.health_before.dns === false ? "unavailable" : "unknown"} · UniFi ${e.health_before.unifi === true ? "working" : e.health_before.unifi === false ? "unavailable" : "unknown"}</p><div class="table-wrap"><table><thead><tr><th>Switch / port</th><th>Target</th><th>Attempted</th><th>Result</th><th>Details</th></tr></thead><tbody>${e.targets.map((t) => `<tr><td>${esc(t.snapshot.switch_name)} / ${t.snapshot.port_number}<br><small>${esc(t.snapshot.switch_id)}</small></td><td>${esc(t.snapshot.label || t.snapshot.port_name || "Port " + t.snapshot.port_number)}</td><td>${t.attempted ? "Yes" : "No"}</td><td>${esc(t.result)}</td><td>${esc(t.error || "—")}<br><small>${t.timestamp ? esc(timeLabel(t.timestamp, config.settings.timezone)) : ""}</small></td></tr>`).join("")}</tbody></table></div><details><summary>Full event snapshot</summary><pre>${esc(JSON.stringify(e, null, 2))}</pre></details></details>`).join("") || '<div class="empty"><h3>No restart activity yet</h3><p>Restart events will appear here with the results for each port.</p></div>'}<div class="actions"><button class="secondary small" id="newer" ${historyOffset === 0 ? "disabled" : ""}>Newer</button><button class="secondary small" id="older" ${events.length < 50 ? "disabled" : ""}>Older</button><button class="secondary small" id="refresh-history">Refresh</button></div></section>`;
    $("#newer").onclick = () => {
      historyOffset = Math.max(0, historyOffset - 50);
      historyView();
    };
    $("#older").onclick = () => {
      historyOffset += 50;
      historyView();
    };
    $("#refresh-history").onclick = historyView;
  } catch (e) {
    $("#admin-content").innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}
function askDelete(title, description, action) {
  const dialog = document.createElement("dialog");
  dialog.innerHTML = `<h2>${esc(title)}</h2><p>${esc(description)}</p><div class="actions"><button class="secondary" id="cancel-delete">Cancel</button><button class="danger" id="confirm-delete">Confirm</button></div>`;
  document.body.append(dialog);
  dialog.showModal();
  $("#cancel-delete").focus();
  dialog.addEventListener("close", () => dialog.remove());
  $("#cancel-delete").onclick = () => dialog.close();
  $("#confirm-delete").onclick = async (event) => {
    event.target.disabled = true;
    try {
      await action();
      dialog.close();
      toast("Change saved.");
    } catch (e) {
      toast(e.message);
      event.target.disabled = false;
    }
  };
}
function savedOperator() {
  try {
    return localStorage.getItem("netrevive.operator") || "";
  } catch {
    return "";
  }
}
let clockOffset = 0,
  lastStatusAt = 0,
  refreshing = false;
async function refreshDashboard(initial = false) {
  if (refreshing) return;
  refreshing = true;
  try {
    const data = await api("/api/status");
    dashboard = data;
    clockOffset = data.server_time - Date.now() / 1000;
    lastStatusAt = Date.now();
    if (initial || !$("#network-health")) {
      root.innerHTML =
        heading(
          data.title === "NetRevive" ? "Network overview" : data.title,
          "Check your connection. Restart equipment when you need to.",
          "Connected locally",
        ) +
        `<section class="panel"><div id="network-health" aria-live="polite"></div><div class="status-grid" id="status-grid"></div></section><div class="section-head"><h2>Restart equipment</h2></div><section class="panel operator-row"><label for="operator">Who is restarting?</label><select id="operator"><option value="">Select your name</option></select></section><div id="restart-groups" class="group-grid"></div><div class="section-head"><h2>Recent activity</h2><span class="muted" id="last-checked"></span></div><section class="panel" id="activity" aria-live="polite"></section>`;
      $("#operator").onchange = () => {
        try {
          localStorage.setItem("netrevive.operator", $("#operator").value);
        } catch {}
        updateButtons();
      };
    }
    $("#hostname").textContent = data.hostname;
    const chosen = $("#operator").value || savedOperator();
    if (JSON.stringify(data.operators) !== refreshDashboard.users) {
      $("#operator").innerHTML =
        '<option value="">Select your name</option>' +
        data.operators
          .map((u) => `<option value="${esc(u.name)}">${esc(u.name)}</option>`)
          .join("");
      $("#operator").value = chosen;
      refreshDashboard.users = JSON.stringify(data.operators);
    }
    const h = data.health;
    const guidance = {
      healthy: [
        "Your network looks healthy",
        "Internet and DNS appear to be working normally.",
      ],
      dns_problem: [
        "There may be a DNS problem",
        "Internet access is available, but normal DNS resolution is failing.",
      ],
      internet_problem: [
        "Internet connectivity is unavailable",
        "Your local recovery controls are still available.",
      ],
      recovery_problem: [
        "The recovery system needs attention",
        "NetRevive cannot verify the UniFi controller or configured equipment.",
      ],
      checking: [
        "Checking your connection",
        "Waiting for a current health check.",
      ],
    };
    const [title, description] = guidance[h.state] || guidance.checking;
    $("#network-health").innerHTML =
      `<div class="status-banner ${h.state === "healthy" ? "" : "warning"}"><span class="status-symbol" aria-hidden="true">${h.state === "healthy" ? "✓" : "!"}</span><div><h2>${title}</h2><p>${description}</p></div></div>`;
    $("#status-grid").innerHTML = [
      ["Internet", "internet"],
      ["DNS", "dns"],
      ["UniFi", "unifi"],
    ]
      .map(
        ([label, key]) =>
          `<div class="status-cell"><div class="caption">${label}</div><div class="status-value"><span class="dot ${h[key] === true ? "good" : h[key] === false ? "bad" : ""}"></span>${h[key] === true ? "Working" : h[key] === false ? "Unavailable" : "Checking"}</div></div>`,
      )
      .join("");
    $("#last-checked").textContent = h.checked_at
      ? "Checked " +
        new Intl.DateTimeFormat(undefined, {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: data.timezone,
        }).format(new Date(h.checked_at * 1000))
      : "";
    const signature = JSON.stringify(
      data.groups.map((g) => [
        g.id,
        g.name,
        g.button_label,
        g.description,
        g.recovery_mode,
      ]),
    );
    if (signature !== refreshDashboard.groups) {
      $("#restart-groups").innerHTML =
        data.groups
          .map(
            (g) =>
              `<section class="panel group-card"><div class="group-icon" aria-hidden="true">↻</div><h2>${esc(g.name)}</h2><p class="description">${esc(g.description || "Restart the equipment in this group.")}</p><button class="primary hold" data-group="${g.id}" aria-describedby="hint-${g.id}" disabled><span>${esc(g.button_label)}</span></button><p class="hint" id="hint-${g.id}">Select your name to continue.</p></section>`,
          )
          .join("") ||
        '<section class="panel empty"><h3>No restart groups available</h3><p>An administrator can configure your restart controls in Admin.</p></section>';
      document.querySelectorAll(".hold").forEach(bindHold);
      refreshDashboard.groups = signature;
    }
    $("#activity").innerHTML = data.events.length
      ? data.events
          .map(
            (e) =>
              `<article class="activity"><div><strong>${esc(e.button_label)}</strong><p>${esc(e.operator)} · ${esc(resultText(e))}</p></div><time datetime="${new Date(e.created_at * 1000).toISOString()}">${esc(timeLabel(e.created_at, data.timezone))}</time></article>`,
          )
          .join("")
      : '<div class="empty"><h3>All quiet here</h3><p>Restart activity will appear here, along with who requested it and how it went.</p></div>';
    updateButtons();
  } catch (e) {
    if (initial) throw e;
    $("#last-checked").textContent =
      "Connection to NetRevive lost. Reconnecting…";
    updateButtons();
  } finally {
    refreshing = false;
  }
}
function updateButtons() {
  if (!dashboard || !$("#operator")) return;
  const now = Date.now() / 1000 + clockOffset;
  for (const group of dashboard.groups) {
    const button = document.querySelector(`[data-group="${group.id}"]`);
    if (!button) continue;
    const remaining = group.locked_until - now,
      stale = Date.now() - lastStatusAt > 15000;
    button.disabled =
      !!button.dataset.sending ||
      stale ||
      !group.available ||
      remaining > 0 ||
      !$("#operator").value;
    if (button.disabled) button.dispatchEvent(new Event("cancelhold"));
    $("#hint-" + group.id).textContent = stale
      ? "Waiting for NetRevive to reconnect."
      : remaining > 0
        ? `${group.unavailable_reason} Available in ${duration(remaining)}.`
        : !group.available
          ? group.unavailable_reason
          : !$("#operator").value
            ? "Select your name to continue."
            : "Hold for 2 seconds to restart";
  }
}
function bindHold(button) {
  let timer = null,
    started = 0;
  const cancel = () => {
    clearTimeout(timer);
    timer = null;
    started = 0;
    button.classList.remove("holding");
  };
  const start = () => {
    if (button.disabled || timer) return;
    started = performance.now();
    button.classList.add("holding");
    timer = setTimeout(async () => {
      if (!started || performance.now() - started < 1950) return cancel();
      cancel();
      button.disabled = true;
      button.dataset.sending = "true";
      try {
        const result = await api(
          `/api/groups/${button.dataset.group}/restart`,
          "POST",
          { operator: $("#operator").value },
        );
        toast(result.message);
      } catch (e) {
        toast(e.message);
      } finally {
        delete button.dataset.sending;
        await refreshDashboard();
      }
    }, 2000);
  };
  button.addEventListener("pointerdown", (event) => {
    if (event.button === 0) {
      button.focus();
      start();
    }
  });
  for (const name of [
    "pointerup",
    "pointerleave",
    "pointercancel",
    "blur",
    "cancelhold",
  ])
    button.addEventListener(name, cancel);
  button.addEventListener("keydown", (event) => {
    if ([" ", "Enter"].includes(event.key)) {
      event.preventDefault();
      if (!event.repeat) start();
    }
  });
  button.addEventListener("keyup", (event) => {
    if ([" ", "Enter"].includes(event.key)) {
      event.preventDefault();
      cancel();
    }
  });
  button.addEventListener("click", (event) => event.preventDefault());
  button.addEventListener("contextmenu", (event) => event.preventDefault());
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancel();
  });
}
setInterval(() => {
  if (dashboard && location.pathname === "/") refreshDashboard();
}, 5000);
setInterval(updateButtons, 1000);
boot().catch((error) => {
  root.innerHTML =
    heading(
      "NetRevive is temporarily unavailable",
      "Check the local application connection and reload this page.",
    ) + `<p class="error" role="alert">${esc(error.message)}</p>`;
});
