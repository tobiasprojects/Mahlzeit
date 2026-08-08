"use strict";

const STALE_MS = 4 * 24 * 60 * 60 * 1000;

const state = {
  menu: null,
  weekKey: null,
  veggie: false,
};

const freshnessEl = document.getElementById("freshness");
const staleEl = document.getElementById("stale-warning");
const weekNavEl = document.getElementById("week-nav");
const columnsEl = document.getElementById("columns");
const veggieFilterEl = document.getElementById("veggie-filter");

function pad2(n) {
  return String(n).padStart(2, "0");
}

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function deDate(date) {
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.${date.getFullYear()}`;
}

function deTime(date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function formatGerman(iso) {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function shortWeekLabel(from, to) {
  const f = from.split("-");
  const t = to.split("-");
  return `${f[2]}.${f[1]}. – ${t[2]}.${t[1]}.${t[0]}`;
}

function relativeAge(date) {
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "gerade eben";
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `vor ${hours} Std.`;
  const days = Math.round(hours / 24);
  return `vor ${days} Tagen`;
}

function allWeekKeys(menu) {
  const keys = new Set();
  for (const restaurant of menu.restaurants) {
    for (const week of restaurant.weeks) keys.add(week.from);
  }
  return [...keys].sort();
}

function weekToForKey(menu, key) {
  let maxTo = null;
  for (const restaurant of menu.restaurants) {
    for (const week of restaurant.weeks) {
      if (week.from === key && (maxTo === null || week.to > maxTo)) maxTo = week.to;
    }
  }
  return maxTo;
}

function weekOf(restaurant, key) {
  return (restaurant.weeks || []).find((week) => week.from === key) || null;
}

function isExpired(to) {
  return to < todayISO();
}

function defaultWeekKey(menu) {
  const keys = allWeekKeys(menu);
  if (!keys.length) return null;
  const today = todayISO();
  const current = keys.find((key) => key <= today && weekToForKey(menu, key) >= today);
  if (current) return current;
  const upcoming = keys.find((key) => key > today);
  if (upcoming) return upcoming;
  return keys[keys.length - 1];
}

function mealMatchesFilter(meal) {
  if (!state.veggie) return true;
  return meal.vegan === true || meal.type === "Menü 2";
}

function formatPrice(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(2).replace(".", ",");
}

function priceText(meal) {
  const internal = meal.price_internal == null ? null : formatPrice(meal.price_internal);
  const external = meal.price_external == null ? null : formatPrice(meal.price_external);
  if (internal === null && external === null) return null;
  if (internal !== null && internal === external) return `${internal} €`;
  if (internal !== null && external === null) return `${internal} €`;
  if (external !== null && internal === null) return `${external} €`;
  return `${internal} € intern · ${external} € extern`;
}

function emptyLine(text) {
  const p = document.createElement("p");
  p.className = "meal-none";
  p.textContent = text;
  return p;
}

function renderFreshness() {
  const menu = state.menu;
  if (!menu || !menu.generated_at) {
    freshnessEl.textContent = "";
    return;
  }
  const generated = new Date(menu.generated_at);
  if (Number.isNaN(generated.getTime())) {
    freshnessEl.textContent = "Zuletzt aktualisiert: unbekannt";
    return;
  }
  freshnessEl.textContent =
    `Zuletzt aktualisiert: ${deDate(generated)}, ${deTime(generated)} Uhr (${relativeAge(generated)})`;
  const stale = Date.now() - generated.getTime() > STALE_MS;
  staleEl.classList.toggle("hidden", !stale);
  if (stale) {
    staleEl.textContent =
      "Die Daten sind veraltet — seit mehreren Tagen wurde kein Menüplan aktualisiert.";
  }
}

function renderWeekNav() {
  weekNavEl.textContent = "";
  const menu = state.menu;
  const keys = allWeekKeys(menu);

  const todayBtn = document.createElement("button");
  todayBtn.type = "button";
  todayBtn.className = "today-btn";
  todayBtn.textContent = "Heute";
  todayBtn.addEventListener("click", () => {
    state.weekKey = defaultWeekKey(menu);
    renderWeekNav();
    renderColumns();
  });
  weekNavEl.append(todayBtn);

  for (const key of keys) {
    const to = weekToForKey(menu, key);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = shortWeekLabel(key, to);
    btn.classList.toggle("active", key === state.weekKey);
    btn.classList.toggle("expired", isExpired(to));
    btn.addEventListener("click", () => {
      state.weekKey = key;
      renderWeekNav();
      renderColumns();
    });
    weekNavEl.append(btn);
  }
}

function renderMeal(meal) {
  const li = document.createElement("li");
  li.className = "meal";

  const name = document.createElement("span");
  name.className = "meal-name";
  name.textContent = meal.name || "–";
  li.append(name);

  const badges = [];
  if (meal.vegan === true) badges.push({ text: "vegan", cls: "vegan" });
  else if (meal.type === "Menü 2") badges.push({ text: "vegetarisch", cls: "vegan" });
  if (meal.sonderessen) badges.push({ text: "Sonderessen", cls: "sonderessen" });
  if (badges.length) {
    const tagsEl = document.createElement("span");
    tagsEl.className = "meal-tags";
    for (const badge of badges) {
      const span = document.createElement("span");
      span.className = `badge ${badge.cls}`;
      span.textContent = badge.text;
      tagsEl.append(span);
    }
    li.append(tagsEl);
  }

  const price = priceText(meal);
  if (price) {
    const priceEl = document.createElement("span");
    priceEl.className = "meal-price";
    priceEl.textContent = price;
    li.append(priceEl);
  }

  if (meal.allergens) {
    const allergensEl = document.createElement("span");
    allergensEl.className = "meal-allergens";
    allergensEl.textContent = `Allergene: ${meal.allergens}`;
    li.append(allergensEl);
  }

  return li;
}

function renderDay(day) {
  const div = document.createElement("div");
  div.className = "day";
  if (day.date === todayISO()) div.classList.add("today");

  const head = document.createElement("div");
  head.className = "day-head";
  const weekdayEl = document.createElement("span");
  weekdayEl.className = "weekday";
  weekdayEl.textContent = day.weekday || formatGerman(day.date);
  const dateEl = document.createElement("span");
  dateEl.className = "date";
  dateEl.textContent = formatGerman(day.date);
  head.append(weekdayEl, dateEl);
  div.append(head);

  const mealsEl = document.createElement("ul");
  mealsEl.className = "meals";
  const filtered = (day.meals || []).filter(mealMatchesFilter);
  if (!filtered.length) {
    mealsEl.append(emptyLine("–"));
  } else {
    for (const meal of filtered) mealsEl.append(renderMeal(meal));
  }
  div.append(mealsEl);
  return div;
}

function renderRestaurant(restaurant) {
  const section = document.createElement("section");
  section.className = "restaurant";

  const heading = document.createElement("h2");
  heading.className = "restaurant-name";
  const link = document.createElement("a");
  link.href = restaurant.source_url || "#";
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = restaurant.name || restaurant.id;
  heading.append(link, " ↗");
  section.append(heading);

  const meta = document.createElement("p");
  meta.className = "restaurant-meta";

  const week = weekOf(restaurant, state.weekKey);
  if (week) {
    const range = document.createElement("span");
    range.className = "week-range";
    range.textContent = shortWeekLabel(week.from, week.to);
    meta.append(range);
    if (isExpired(week.to)) {
      section.classList.add("expired");
      const note = document.createElement("span");
      note.className = "expired-note";
      note.textContent = "abgelaufen";
      meta.append(note);
    }
  } else {
    const note = document.createElement("span");
    note.className = "expired-note";
    note.textContent = "keine Daten für diese Woche";
    meta.append(note);
  }
  section.append(meta);

  const daysEl = document.createElement("div");
  daysEl.className = "days";
  if (week) {
    const days = [...week.days].sort((a, b) => (a.date < b.date ? -1 : 1));
    if (!days.length) {
      daysEl.append(emptyLine("Keine Gerichte für diese Woche."));
    } else {
      for (const day of days) daysEl.append(renderDay(day));
    }
  } else {
    daysEl.append(emptyLine("–"));
  }
  section.append(daysEl);
  return section;
}

function renderColumns() {
  columnsEl.textContent = "";
  const menu = state.menu;
  if (!menu || !menu.restaurants || !menu.restaurants.length) {
    columnsEl.append(emptyLine("Keine Restaurants in den Daten."));
    return;
  }
  for (const restaurant of menu.restaurants) {
    columnsEl.append(renderRestaurant(restaurant));
  }
}

function render() {
  renderFreshness();
  renderWeekNav();
  renderColumns();
}

async function load() {
  try {
    const response = await fetch("data/menus.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const menu = await response.json();
    state.menu = menu;
    state.weekKey = defaultWeekKey(menu);
    render();
  } catch (err) {
    columnsEl.textContent = "";
    const box = document.createElement("p");
    box.className = "error-state";
    box.textContent =
      `Konnte data/menus.json nicht laden (${err.message}). ` +
      "Bitte zuerst `mahlzeit refresh` ausführen und den Server starten.";
    columnsEl.append(box);
  }
}

veggieFilterEl.addEventListener("change", () => {
  state.veggie = veggieFilterEl.checked;
  renderColumns();
});

load();
