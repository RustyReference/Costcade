const POLL_MS = 1000; // server runs 1 real second = 1 simulated minute

const $ = (id) => document.getElementById(id);
const money = (n) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: n % 1 && n < 100 ? 2 : 0 });
const mins = (m) => `${m.toFixed(1)} min`;

const STATUS_COLOR = { green: "#2e8b57", yellow: "#e0a800", red: "#d64545", origin: "#7b1fa2" };
const cy = cytoscape({
  container: $("cy"),
  style: [
    { selector: "node", style: {
      label: "data(text)", "text-wrap": "wrap", "text-valign": "center", "text-halign": "center",
      "font-size": 11, color: "#fff", width: 92, height: 46, shape: "round-rectangle",
      "background-color": STATUS_COLOR.green } },
    ...Object.entries(STATUS_COLOR).map(([s, c]) => ({ selector: `node[status = "${s}"]`, style: { "background-color": c } })),
    { selector: 'node[status = "yellow"]', style: { color: "#1c2026" } },
    { selector: 'node[status = "origin"]', style: { "border-width": 4, "border-color": "#ff9100" } },
    { selector: "edge", style: {
      width: 2, "line-color": "#8a8f98", "target-arrow-color": "#8a8f98", "target-arrow-shape": "triangle",
      "curve-style": "bezier", label: "data(delayText)", "font-size": 10, color: "#7a8088" } },
    { selector: "edge[?soft]", style: { "line-style": "dashed" } },
  ],
});
cy.userZoomingEnabled(false);
let laidOut = false;

async function api(path, method = "GET") {
  const r = await fetch(path, { method });
  if (!r.ok) throw new Error(`${method} ${path} failed (${r.status})`);
  return r.json();
}

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

function nodeText(n) {
  const tag = { origin: "FAULT", red: "DOWN", yellow: n.eta_min != null ? mins(n.eta_min) : "", green: "" }[n.status];
  return tag ? `${n.label}\n${tag}` : n.label;
}

function drawGraph(d) {
  if (!laidOut) {
    cy.add([
      ...d.nodes.map((n) => ({ data: { id: n.id } })),
      ...d.edges.map((e) => ({ data: { id: `${e.source}->${e.target}`, source: e.source, target: e.target } })),
    ]);
    cy.layout({ name: "breadthfirst", directed: true, spacingFactor: 1.15, padding: 20 }).run();
    laidOut = true;
  }
  d.nodes.forEach((n) => cy.getElementById(n.id).data({ text: nodeText(n), status: n.status }));
  d.edges.forEach((e) => cy.getElementById(`${e.source}->${e.target}`).data({
    soft: !e.hard, delayText: e.delay_min ? `+${e.delay_min}m` : "",
  }));
}

function drawBanner(d) {
  const b = $("banner");
  const total = d.cost.total.breach_in_min;
  if (!d.nodes.some((n) => n.status === "origin")) {
    b.textContent = "All systems normal";
    b.className = "ok";
  } else if (total === null) {
    b.textContent = "Fault active: no SLA is affected";
    b.className = "warn";
  } else if (total > 0) {
    b.textContent = `Fault active: SLA credits start in ${mins(total)}`;
    b.className = "warn";
  } else {
    b.textContent = "SLA breached: credits are accruing";
    b.className = "bad";
  }
  $("clock").textContent = `Sim time ${mins(d.now_min)}`;
}

function drawCost(d) {
  const t = el("table");
  const head = el("tr");
  ["SLA", "Projected", "Accrued", "Credits in"].forEach((h) => head.append(el("th", h)));
  t.append(head);
  const row = (name, c, cls) => {
    const tr = el("tr", undefined, cls);
    tr.append(el("td", name), el("td", money(c.projected)), el("td", money(c.accrued)),
      el("td", c.breach_in_min == null ? "n/a" : c.breach_in_min > 0 ? mins(c.breach_in_min) : "now"));
    t.append(tr);
  };
  d.cost.slas.forEach((s) => row(s.id, s));
  row("Total", d.cost.total, "total");
  $("cost").replaceChildren(t);
}

function drawActions(d) {
  const faulted = d.nodes.some((n) => n.status === "origin");
  const items = d.actions.map((a) => {
    const li = el("li");
    li.append(el("strong", a.label), el("div", `${a.duration_min} min · credits after: ${money(a.cost)} · avoids ${money(a.avoided)}`, "detail"));
    li.append(el("span", a.prevents.length ? `Prevents breach: ${a.prevents.join(", ")}` : "Does not prevent a breach", `tag ${a.prevents.length ? "yes" : "no"}`));
    return li;
  });
  if (!items.length) items.push(el("li", faulted ? "No applicable action for this fault" : "No active fault", "detail"));
  $("actions").replaceChildren(...items);
}

function showError(e) {
  $("banner").textContent = `Backend problem: ${e.message}`;
  $("banner").className = "bad";
}

let latest = null;
let busy = false;
async function refresh() {
  if (busy) return;
  busy = true;
  try {
    latest = await api("/api/building");
    drawGraph(latest);
    drawBanner(latest);
    drawCost(latest);
    drawActions(latest);
  } catch (e) {
    showError(e);
  } finally {
    busy = false;
  }
}

cy.on("tap", "node", async (evt) => {
  const id = evt.target.id();
  const origin = latest && latest.nodes.find((n) => n.id === id).status === "origin";
  try {
    await api(origin ? `/api/fault/${encodeURIComponent(id)}` : `/api/fault?node_id=${encodeURIComponent(id)}`, origin ? "DELETE" : "POST");
    await refresh();
  } catch (e) {
    showError(e);
  }
});

$("clear").addEventListener("click", async () => {
  try {
    await Promise.all(latest.nodes.filter((n) => n.status === "origin").map((n) => api(`/api/fault/${encodeURIComponent(n.id)}`, "DELETE")));
    await refresh();
  } catch (e) {
    showError(e);
  }
});

refresh();
setInterval(refresh, POLL_MS);
