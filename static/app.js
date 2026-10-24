// Sloth Ledger client — typed cards, stamped verdicts, punched holes.
// No framework, no build step, no network beyond this origin.

(() => {
  const el = (id) => document.getElementById(id);
  const form = el("chore-form");
  const errorBox = el("error");
  const submit = el("submit");

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const minutes = (value) => {
    const n = Math.round(Number(value) || 0);
    if (n <= 0) return "0m";
    const h = Math.floor(n / 60);
    const m = n % 60;
    return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
  };

  const verdictLabel = (verdict) =>
    ({ automate: "Automate", delegate: "Delegate", ignore: "Ignore forever" }[verdict] || verdict);

  const plural = (n, word) => `${n} ${word}${Number(n) === 1 ? "" : "s"}`;

  function showError(message) {
    errorBox.hidden = !message;
    errorBox.textContent = message || "";
  }

  function renderMeta(snapshot) {
    const model = snapshot.lanes.find((lane) => lane !== "rules") || "rules floor";
    el("meta").innerHTML = `
      <span data-meta="store">store · ${esc(snapshot.store_lane)}</span>
      <span data-meta="model">judgement · ${esc(model)}</span>
      <span data-meta="date">${esc(new Date().toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" }))}</span>`;
    el("foot-model").textContent = model;
    el("foot-store").textContent = snapshot.store_lane;
  }

  function renderTally(daily) {
    const byDay = new Map(daily.map((row) => [String(row.day).slice(0, 10), Number(row.minutes) || 0]));
    const days = [];
    for (let i = 13; i >= 0; i -= 1) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      days.push({ key, minutes: byDay.get(key) || 0, today: i === 0 });
    }
    const filled = days.filter((d) => d.minutes > 0).length;
    const peak = Math.max(0, ...days.map((d) => d.minutes));
    el("tally").innerHTML = days
      .map(
        (d) =>
          `<span class="punch-day ${d.minutes > 0 ? "filled" : ""} ${d.today ? "today" : ""}"
             title="${d.key}: ${minutes(d.minutes)}"></span>`
      )
      .join("");
    el("tally").setAttribute(
      "aria-label",
      `${filled} of the last 14 days have booked time. Busiest day ${minutes(peak)}. Latest ${days[13].key}.`
    );
    el("tally-note").textContent = filled
      ? `${plural(filled, "day")} punched · busiest ${minutes(peak)}`
      : "Fourteen days, one punch per day with time booked.";
  }

  function choreCard(chore) {
    const booked = chore.reclaimed;
    const action = booked
      ? `<span class="stamp booked">Booked</span>
         <span class="booked-line">minutes already back</span>`
      : chore.verdict === "automate"
        ? `<button class="stamp-btn run" data-id="${chore.id}" type="button">Run it</button>`
        : `<span class="no-automation">No automation needed</span>`;

    return `
      <li class="chore-card ${booked ? "reclaimed" : ""}">
        <span class="punch" aria-hidden="true"></span>
        <div class="chore-top">
          <span class="stamp ${esc(chore.verdict)}">${esc(verdictLabel(chore.verdict))}</span>
          <span class="card-min">${minutes(chore.manual_minutes)}</span>
        </div>
        <p class="card-text">${esc(chore.description)}</p>
        <p class="card-evidence">${esc(chore.evidence || "no evidence recorded")} · via ${esc(chore.model_lane || "rules")}</p>
        <p class="card-reason">${esc(chore.reason || "")}</p>
        <div class="chore-foot">${action}</div>
      </li>`;
  }

  function renderChores(snapshot) {
    const recent = snapshot.recent;
    const filed = snapshot.ignored.reduce((total, row) => total + Number(row.times || 0), 0);
    el("empty").hidden = recent.length > 0;
    el("tray-count").textContent = recent.length
      ? `${plural(recent.length, "card")} · ${filed} filed as not worth it`
      : "";
    el("chores").innerHTML = recent.map(choreCard).join("");
  }

  function render(snapshot, { restamp = false } = {}) {
    el("week").textContent = minutes(snapshot.week_minutes);
    el("week-sub").textContent = snapshot.week_runs
      ? `${plural(snapshot.week_runs, "automation run")} booked this week`
      : "no automation has run yet";
    el("all").textContent = minutes(snapshot.all_minutes);
    el("manual").textContent = minutes(snapshot.still_manual_minutes);
    el("count").textContent = String(snapshot.chores_counted);
    el("payoff").textContent = snapshot.payoff_line;

    if (restamp) {
      el("week").classList.remove("restamp");
      void el("week").offsetWidth;
      el("week").classList.add("restamp");
    }

    renderMeta(snapshot);
    renderTally(snapshot.daily);
    renderChores(snapshot);
  }

  async function call(url, body) {
    const response = await fetch(url, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `request failed (${response.status})`);
    return data;
  }

  async function refresh() {
    try {
      render(await call("/api/summary"));
    } catch (err) {
      showError(err.message);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    const description = el("description").value.trim();
    if (description.length < 3) return showError("Describe the chore in a few words.");
    submit.disabled = true;
    submit.textContent = "Stamping…";
    try {
      const data = await call("/api/log", { description, minutes: el("minutes").value || null });
      render(data.ledger);
      el("description").value = "";
      el("minutes").value = "";
      el("payoff").textContent = `${verdictLabel(data.chore.verdict)}: ${data.chore.reason}`;
    } catch (err) {
      showError(err.message);
    } finally {
      submit.disabled = false;
      submit.textContent = "Stamp it";
    }
  });

  el("chores").addEventListener("click", async (event) => {
    const button = event.target.closest(".run");
    if (!button) return;
    button.disabled = true;
    button.textContent = "Booking…";
    try {
      const data = await call("/api/run", { id: Number(button.dataset.id) });
      render(data.ledger, { restamp: true });
    } catch (err) {
      showError(err.message);
      button.disabled = false;
      button.textContent = "Run it";
    }
  });

  refresh();
})();
