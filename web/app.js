"use strict";

const STALE_MS = 4 * 24 * 60 * 60 * 1000;

const state = {
  menu: null,
  view: "daily",
  weekKey: null,
  dayDate: null,
  veggie: false,
};

const freshnessEl = document.getElementById("freshness");
const staleEl = document.getElementById("stale-warning");
const viewTabsEl = document.getElementById("view-tabs");
const weekNavEl = document.getElementById("week-nav");
const dayNavEl = document.getElementById("day-nav");
const dailyViewEl = document.getElementById("daily-view");
const columnsEl = document.getElementById("columns");
const veggieFilterEl = document.getElementById("veggie-filter");

const STORAGE_KEY = "mahlzeit-theme";
const themeToggleEl = document.getElementById("theme-toggle");
const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function setTheme(theme, persist) {
  document.documentElement.dataset.theme = theme;
  if (colorSchemeMeta) colorSchemeMeta.content = theme;
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (_) {}
  }
  const dark = theme === "dark";
  themeToggleEl.textContent = dark ? "Hellmodus" : "Dunkelmodus";
  themeToggleEl.setAttribute("aria-pressed", String(dark));
}

themeToggleEl.addEventListener("click", () => {
  setTheme(currentTheme() === "dark" ? "light" : "dark", true);
});

systemDark.addEventListener("change", (e) => {
  let saved = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch (_) {}
  if (!saved) setTheme(e.matches ? "dark" : "light", false);
});

setTheme(currentTheme(), false);

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

function allDayDates(menu) {
  const dates = new Set();
  for (const restaurant of menu.restaurants) {
    for (const week of restaurant.weeks || []) {
      for (const day of week.days) dates.add(day.date);
    }
  }
  return [...dates].sort();
}

function defaultDayDate(menu) {
  const dates = allDayDates(menu);
  if (!dates.length) return null;
  const today = todayISO();
  if (dates.includes(today)) return today;
  const upcoming = dates.find((date) => date > today);
  if (upcoming) return upcoming;
  return dates[dates.length - 1];
}

function dayOf(restaurant, date) {
  for (const week of restaurant.weeks || []) {
    const day = (week.days || []).find((d) => d.date === date);
    if (day) return day;
  }
  return null;
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

function buildBadges(meal) {
  const badges = [];
  if (meal.vegan === true) badges.push({ text: "vegan", cls: "vegan" });
  else if (meal.type === "Menü 2") badges.push({ text: "vegetarisch", cls: "vegan" });
  if (meal.sonderessen) badges.push({ text: "Sonderessen", cls: "sonderessen" });

  const tagsEl = document.createElement("span");
  tagsEl.className = "meal-tags";
  for (const badge of badges) {
    const span = document.createElement("span");
    span.className = `badge ${badge.cls}`;
    span.textContent = badge.text;
    tagsEl.append(span);
  }
  return tagsEl;
}

function renderMeal(meal) {
  const li = document.createElement("li");
  li.className = "meal";

  const text = document.createElement("span");
  text.className = "meal-text";
  const name = document.createElement("span");
  name.className = "meal-name";
  name.textContent = meal.name || "–";
  text.append(name, buildBadges(meal));
  li.append(text);

  const price = priceText(meal);
  if (price) {
    const priceEl = document.createElement("span");
    priceEl.className = "meal-price";
    priceEl.textContent = price;
    li.append(priceEl);
  }

  return li;
}

function renderMealTile(meal, restaurant, accent) {
  const article = document.createElement("article");
  article.className = `meal-tile ${accent}`;

  const label = document.createElement("a");
  label.className = "tile-restaurant";
  label.href = restaurant.source_url || "#";
  label.target = "_blank";
  label.rel = "noopener";
  label.textContent = restaurant.name || restaurant.id;
  article.append(label);

  const name = document.createElement("span");
  name.className = "meal-name";
  name.textContent = meal.name || "–";
  article.append(name, buildBadges(meal));

  const price = priceText(meal);
  if (price) {
    const priceEl = document.createElement("span");
    priceEl.className = "meal-price";
    priceEl.textContent = price;
    article.append(priceEl);
  }

  return article;
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
    mealsEl.append(emptyLine("Keine Gerichte für diesen Tag."));
  } else {
    for (const meal of filtered) mealsEl.append(renderMeal(meal));
  }
  div.append(mealsEl);
  return div;
}

function accentOf(index) {
  return index % 2 === 0 ? "green" : "orange";
}

const ICONS = ["🌿", "🍴"];
const KICKERS = ["Kantine A", "Kantine B"];

function renderCard(restaurant, days, accent, opts = {}) {
  const section = document.createElement("section");
  section.className = `canteen-card ${accent}`;
  if (opts.expired) section.classList.add("expired");

  const head = document.createElement("div");
  head.className = "card-head";

  const icon = document.createElement("div");
  icon.className = `card-icon ${accent}`;
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = ICONS[accent === "green" ? 0 : 1];

  const title = document.createElement("div");
  title.className = "card-title";
  const kicker = document.createElement("span");
  kicker.className = "card-kicker";
  kicker.textContent = KICKERS[accent === "green" ? 0 : 1];
  const name = document.createElement("h2");
  name.className = "card-name";
  const link = document.createElement("a");
  link.href = restaurant.source_url || "#";
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = restaurant.name || restaurant.id;
  name.append(link);
  title.append(kicker, name);

  head.append(icon, title);

  if (opts.expired) {
    const status = document.createElement("span");
    status.className = "card-status expired";
    status.textContent = "Abgelaufen";
    head.append(status);
  }
  section.append(head);

  section.append(Object.assign(document.createElement("hr"), { className: "card-divider" }));

  const daysEl = document.createElement("div");
  daysEl.className = "card-days";
  if (!days.length) {
    daysEl.append(emptyLine(opts.emptyText || "–"));
  } else {
    for (const day of days) daysEl.append(renderDay(day));
  }
  section.append(daysEl);

  section.append(Object.assign(document.createElement("hr"), { className: "card-divider" }));

  const foot = document.createElement("div");
  foot.className = "card-foot";
  const button = document.createElement("a");
  button.className = "btn";
  button.href = restaurant.source_url || "#";
  button.target = "_blank";
  button.rel = "noopener";
  button.textContent = "Details ansehen →";
  foot.append(button);
  section.append(foot);

  return section;
}

function renderColumns() {
  columnsEl.textContent = "";
  const menu = state.menu;
  if (!menu || !menu.restaurants || !menu.restaurants.length) {
    columnsEl.append(emptyLine("Keine Restaurants in den Daten."));
    return;
  }
  const cards = document.createElement("div");
  cards.className = "cards";
  for (const [index, restaurant] of menu.restaurants.entries()) {
    const week = weekOf(restaurant, state.weekKey);
    if (!week) {
      cards.append(
        renderCard(restaurant, [], accentOf(index), {
          expired: false,
          emptyText: "Keine Daten für diese Woche.",
        })
      );
      continue;
    }
    const days = [...week.days].sort((a, b) => (a.date < b.date ? -1 : 1));
    cards.append(
      renderCard(restaurant, days, accentOf(index), { expired: isExpired(week.to) })
    );
  }
  columnsEl.append(cards);
}

function renderDaily() {
  dailyViewEl.textContent = "";
  const menu = state.menu;
  if (!menu || !menu.restaurants || !menu.restaurants.length) {
    dailyViewEl.append(emptyLine("Keine Restaurants in den Daten."));
    return;
  }
  if (!state.dayDate) state.dayDate = defaultDayDate(menu);

  dayNavEl.textContent = "";
  dayNavEl.append(renderDailyNav());

  const tilesEl = document.createElement("div");
  tilesEl.className = "meal-tiles";
  for (const [index, restaurant] of menu.restaurants.entries()) {
    const day = dayOf(restaurant, state.dayDate);
    if (!day) continue;
    const filtered = (day.meals || []).filter(mealMatchesFilter);
    for (const meal of filtered) {
      tilesEl.append(renderMealTile(meal, restaurant, accentOf(index)));
    }
  }
  if (!tilesEl.children.length) {
    tilesEl.append(emptyLine("Keine Gerichte für diesen Tag."));
  }
  dailyViewEl.append(tilesEl);
}

function renderDayLabel() {
  let weekday = "";
  for (const restaurant of state.menu.restaurants) {
    const day = dayOf(restaurant, state.dayDate);
    if (day && day.weekday) {
      weekday = day.weekday;
      break;
    }
  }
  return [weekday, formatGerman(state.dayDate)].filter(Boolean).join(", ");
}

function renderDailyNav() {
  const frag = document.createDocumentFragment();

  const dates = allDayDates(state.menu);
  const index = dates.indexOf(state.dayDate);

  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "day-arrow";
  prev.setAttribute("aria-label", "Vorheriger Tag");
  prev.textContent = "←";
  prev.disabled = index <= 0;
  prev.addEventListener("click", () => {
    state.dayDate = dates[index - 1];
    renderDaily();
  });

  const today = document.createElement("button");
  today.type = "button";
  today.className = "today-btn";
  today.textContent = "Heute";
  today.disabled = state.dayDate === todayISO();
  today.addEventListener("click", () => {
    state.dayDate = defaultDayDate(state.menu);
    renderDaily();
  });

  const label = document.createElement("span");
  label.className = "day-label";
  label.textContent = renderDayLabel();

  const center = document.createElement("div");
  center.className = "day-center";
  center.append(today, label);

  const next = document.createElement("button");
  next.type = "button";
  next.className = "day-arrow";
  next.setAttribute("aria-label", "Nächster Tag");
  next.textContent = "→";
  next.disabled = index < 0 || index >= dates.length - 1;
  next.addEventListener("click", () => {
    state.dayDate = dates[index + 1];
    renderDaily();
  });

  frag.append(prev, center, next);
  return frag;
}

function renderViewTabs() {
  for (const btn of viewTabsEl.querySelectorAll("button[data-view]")) {
    const active = btn.dataset.view === state.view;
    btn.setAttribute("aria-pressed", String(active));
  }
  weekNavEl.classList.toggle("hidden", state.view !== "weekly");
  dayNavEl.classList.toggle("hidden", state.view !== "daily");
  dailyViewEl.classList.toggle("hidden", state.view !== "daily");
  columnsEl.classList.toggle("hidden", state.view !== "weekly");
}

function renderView() {
  if (state.view === "daily") renderDaily();
  else renderColumns();
}

function render() {
  renderFreshness();
  renderViewTabs();
  renderWeekNav();
  renderView();
}

async function load() {
  try {
    const response = await fetch("data/menus.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const menu = await response.json();
    state.menu = menu;
    state.weekKey = defaultWeekKey(menu);
    state.dayDate = defaultDayDate(menu);
    render();
  } catch (err) {
    dailyViewEl.textContent = "";
    columnsEl.textContent = "";
    const box = document.createElement("p");
    box.className = "error-state";
    box.textContent =
      `Konnte data/menus.json nicht laden (${err.message}). ` +
      "Bitte zuerst `mahlzeit refresh` ausführen und den Server starten.";
    dailyViewEl.append(box);
    columnsEl.append(box);
  }
}

viewTabsEl.addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-view]");
  if (!btn || btn.dataset.view === state.view) return;
  state.view = btn.dataset.view;
  render();
});

veggieFilterEl.addEventListener("change", () => {
  state.veggie = veggieFilterEl.checked;
  renderView();
});

load();
