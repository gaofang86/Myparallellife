const state = {
  decision: "",
  priority: "",
  life: null,
  directions: [],
};

if ("scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

window.addEventListener("pageshow", () => {
  window.scrollTo({ top: 0, left: 0, behavior: "instant" });
});

const screens = [...document.querySelectorAll(".screen")];
const progress = document.querySelector("#progress-fill");
const stepLabel = document.querySelector("#step-label");
const stepMap = { decision: 1, priority: 2, lives: 3, experiment: 4, journey: 5 };
const analyticsSource = new URLSearchParams(window.location.search).get("source") || "direct";
let decisionStartedCaptured = false;

function captureEvent(name, properties = {}) {
  if (!window.posthog?.capture) return;
  window.posthog.capture(name, {
    source: analyticsSource,
    ...properties,
  });
}

captureEvent("page viewed", {
  page: "public preview",
  referrer_host: document.referrer ? new URL(document.referrer).hostname : "direct",
});

const directionSets = {
  laidOff: [
    ["similar-role", "Stay in my field", "Use what you already know in a healthier role", "Speed and income continuity", "A wider reinvention", "Compare five roles with one scorecard", "Which role conditions matter enough to shape your next search?"],
    ["new-industry", "Change industries", "Carry your strongest skills into a different field", "Fresh possibility and new learning", "Seniority and familiarity", "Complete one real task from a new field", "Does the work itself create curiosity, not just escape?"],
    ["recover", "Take time to recover", "Create space before choosing from urgency", "Energy and clearer judgment", "Immediate momentum", "Track what restores your focus for seven days", "What returns when panic is no longer making the decision?"],
    ["own-path", "Build something of my own", "Use the transition to test an independent path", "Autonomy and direct learning", "Predictable income", "Offer one small idea to a real person", "Will someone engage with the smallest real version?"],
  ],
  graduate: [
    ["skill", "Follow my strongest skill", "Begin where you already have evidence of ability", "Confidence and early momentum", "Broader exploration", "Use that skill in one real work sample", "Does using this skill give you energy as well as competence?"],
    ["energy", "Explore what gives me energy", "Compare different kinds of work before choosing a title", "Self-knowledge and flexibility", "A simple career story", "Track energy across three different tasks", "Which work keeps your attention without forcing it?"],
    ["stability", "Choose stability first", "Build income and experience before making a bigger bet", "Security and practical options", "Immediate freedom", "Compare five entry roles with one scorecard", "Which stable option still leaves room to grow?"],
    ["gap", "Take a structured gap", "Use a defined period to learn, work, or explore", "Perspective and intentional exploration", "A conventional timeline", "Design one week around a clear learning goal", "Can unstructured uncertainty become purposeful exploration?"],
  ],
  relationship: [
    ["solo", "Rebuild life on my own", "Learn what daily life feels like around your own preferences", "Independence and self-trust", "Familiar companionship", "Design one day around only your preferences", "What feels alive when no one else is shaping the day?"],
    ["self", "Reconnect with myself", "Return to parts of you that had less room in the relationship", "Identity and renewed energy", "The comfort of old routines", "Return to one neglected activity", "Which part of yourself is ready to come back?"],
    ["support", "Strengthen my support", "Invest in friendships and relationships that help you feel grounded", "Belonging and perspective", "More solitary processing", "Reconnect with two grounding people", "What kind of connection helps without asking you to perform?"],
    ["intimacy", "Rethink what I want", "Use what ended to clarify what intimacy should feel like next", "Clearer boundaries and desires", "Quick certainty", "Write what you want intimacy to feel like", "Which needs are truly yours rather than inherited expectations?"],
  ],
  turning30: [
    ["deepen", "Deepen what I have", "Invest more deliberately in a life that already has value", "Compounding progress and stability", "The excitement of reinvention", "Give one priority three focused sessions", "Does deeper attention reveal enough possibility?"],
    ["dream", "Start a neglected dream", "Make room for something you keep postponing", "Aliveness and new evidence", "Comfort and spare time", "Give one postponed goal two protected hours", "Does doing the work feel better than imagining the identity?"],
    ["environment", "Change my environment", "Test whether a different place changes what feels possible", "Fresh inputs and perspective", "Familiarity and local roots", "Spend one ordinary day somewhere new", "Does the ordinary reality fit, not just the fantasy?"],
    ["timeline", "Rewrite the timeline", "Separate your real desires from borrowed deadlines", "Freedom and a more honest plan", "External validation", "Sort ten shoulds into want and do-not-want", "Which deadline disappears when no one else is watching?"],
  ],
  change: [
    ["time", "Change how I spend my time", "Protect room for what keeps asking for your attention", "Focus and visible momentum", "Some existing obligations", "Protect two hours for the recurring idea", "What becomes clearer once it receives real time?"],
    ["work", "Change the work I do", "Test whether another kind of work fits your energy and strengths", "New possibility and learning", "Familiar competence", "Try one real task from another role", "Do you want the daily work or only the change it represents?"],
    ["place", "Change where I live", "Explore whether your environment is limiting the life you want", "Fresh possibility and perspective", "Familiar support and routines", "Test one ordinary day in another place", "How does the place feel when nothing special is happening?"],
    ["priority", "Change what I prioritize", "Remove one obligation and notice what naturally returns", "Alignment and breathing room", "Approval or predictability", "Pause one low-value obligation", "What do you choose when space becomes available?"],
  ],
};

const directionColors = ["#4386d7", "#ed6857", "#8c6ed8", "#d99822"];

function makeDirections(rows) {
  return rows.map(([id, title, meaning, gain, giveUp, action, question], index) => ({
    id,
    title,
    meaning,
    gain,
    giveUp,
    action,
    question,
    color: directionColors[index],
  }));
}

const priorityLenses = {
  Stability: {
    gain: "More predictability and a clearer downside",
    giveUp: "Some speed or upside while you reduce uncertainty",
    action: "Set one downside limit before you begin.",
    question: "Does this feel safer because it fits, or only because it is familiar?",
  },
  Growth: {
    gain: "New capability and evidence about your upside",
    giveUp: "Some comfort while you learn in public",
    action: "Choose the version that teaches you something observable.",
    question: "Does the work create enough energy to justify the learning curve?",
  },
  Freedom: {
    gain: "More autonomy and room to change course",
    giveUp: "Some structure and near-term predictability",
    action: "Keep the test reversible and notice whether it creates real choice.",
    question: "Does this create real choice, or simply move uncertainty somewhere else?",
  },
};

function cleanDecision(decision) {
  return decision
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, " ")
    .replace(/[?.!]+$/, "")
    .trim();
}

function sentenceCase(text) {
  const cleaned = text.trim().replace(/^(whether|if|should i|do i|to)\s+/i, "");
  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : cleaned;
}

function shortPhrase(text, maxWords = 9) {
  const words = text.trim().split(/\s+/);
  return words.length > maxWords ? `${words.slice(0, maxWords).join(" ")}…` : words.join(" ");
}

function appendSentence(text, sentence) {
  const trimmed = text.trim();
  const punctuation = /[.!?]$/.test(trimmed) ? "" : ".";
  return `${trimmed}${punctuation} ${sentence}`;
}

function explicitOptions(decision) {
  const cleaned = cleanDecision(decision)
    .replace(/^(i am|i'm|im)\s+(deciding|trying to decide|wondering)\s+/i, "")
    .replace(/^should i\s+/i, "");
  const match = cleaned.match(/^(.{3,90}?)\s+(?:or|versus|vs\.?)\s+(.{3,90})$/i);
  if (!match) return null;
  return [sentenceCase(shortPhrase(match[1])), sentenceCase(shortPhrase(match[2]))];
}

function decisionTopic(decision) {
  const cleaned = cleanDecision(decision)
    .replace(/^(i am|i'm|im|should i|do i|can i|what if i)\s+/i, "")
    .replace(/^(deciding|trying to decide|wondering)\s+(whether|if)?\s*/i, "");
  return shortPhrase(cleaned || "this decision", 11);
}

function applyPriorityLens(rows, priority) {
  const lens = priorityLenses[priority] || priorityLenses.Growth;
  return rows.map((row, index) => {
    const next = [...row];
    next[5] = appendSentence(next[5], lens.action);
    if (index === 2) {
      next[3] = lens.gain;
      next[4] = lens.giveUp;
      next[6] = lens.question;
    } else {
      next[6] = `${next[6]} ${lens.question}`;
    }
    return next;
  });
}

function optionDirections(options, priority) {
  const [first, second] = options;
  const lens = priorityLenses[priority] || priorityLenses.Growth;
  const rows = [
    ["option-a", first, `Explore what an ordinary week on the “${first}” path would actually feel like`, `Direct evidence about “${first}”`, `Less time exploring “${second}”`, `Spend 45 minutes doing one ordinary task related to “${first}.”`, `Did the reality of “${first}” feel better than the idea of it?`],
    ["option-b", second, `Give the “${second}” path a fair test before ruling it in or out`, `Direct evidence about “${second}”`, `Less time deepening “${first}”`, `Spend 45 minutes doing one ordinary task related to “${second}.”`, `Did the reality of “${second}” create energy, resistance, or useful surprise?`],
    ["bridge", "Build a bridge between both", `Reduce the pressure to make “${first}” and “${second}” an immediate all-or-nothing choice`, lens.gain, lens.giveUp, `Design one reversible week that preserves part of “${first}” while testing one part of “${second}.”`, lens.question],
    ["criteria", "Choose from evidence, not urgency", `Compare both paths using the conditions that matter most to you now`, "A decision grounded in your real constraints", "The emotional relief of choosing immediately", `Write three must-haves, then score “${first}” and “${second}” against real examples.`, "Which option still fits when you judge the ordinary week, not the best-case story?"],
  ];
  return rows.map((row, index) => {
    const next = [...row];
    next[5] = appendSentence(next[5], lens.action);
    if (index !== 2) next[6] = `${next[6]} ${lens.question}`;
    return next;
  });
}

function contextualizeDirections(rows, decision, priority) {
  const topic = decisionTopic(decision);
  const lens = priorityLenses[priority] || priorityLenses.Growth;
  return applyPriorityLens(rows, priority).map((row, index) => {
    const next = [...row];
    if (index === 0) {
      next[2] = `${next[2]} — applied to “${topic}”`;
      next[6] = `For “${topic},” ${next[6].charAt(0).toLowerCase()}${next[6].slice(1)}`;
    }
    if (index === 1) {
      next[5] = `${next[5]} Keep it focused on “${topic}.”`;
    }
    if (index === 2) {
      next[3] = lens.gain;
      next[4] = lens.giveUp;
    }
    return next;
  });
}

function directionsForDecision(decision, priority) {
  const options = explicitOptions(decision);
  if (options) return makeDirections(optionDirections(options, priority));

  const category = decisionCategory(decision);
  const setByCategory = {
    laid_off: directionSets.laidOff,
    graduate: directionSets.graduate,
    relationship: directionSets.relationship,
    turning_30: directionSets.turning30,
    change: directionSets.change,
  };
  return makeDirections(contextualizeDirections(setByCategory[category], decision, priority));
}

function decisionCategory(decision) {
  const text = decision.toLowerCase();
  if (/laid off|layoff|lost my job|fired/.test(text)) return "laid_off";
  if (/graduat|college|university|school|degree|master'?s|phd|study/.test(text)) return "graduate";
  if (/relationship|breakup|broke up|divorc|partner/.test(text)) return "relationship";
  if (/\b30\b|turning thirty|turning 30|behind/.test(text)) return "turning_30";
  return "change";
}

const scenarioExamples = [
  {
    want: "I’m turning 30",
    fear: "Am I already behind?",
    question: "What is small enough to test today?",
    directions: [
      ["Deepen what I have", "Invest three focused sessions in one current priority."],
      ["Start a neglected dream", "Give one postponed goal two protected hours."],
      ["Change my environment", "Spend one ordinary day in a place you could move to."],
      ["Rewrite the timeline", "Separate what you want from what you think is late."],
    ],
  },
  {
    want: "I was laid off",
    fear: "What now?",
    question: "What could I test before choosing my next role?",
    directions: [
      ["Find a similar role", "Build a five-point role scorecard."],
      ["Change industries", "Complete one real task from a new field."],
      ["Take time to recover", "Track what restores your energy and focus."],
      ["Build something of my own", "Offer one small idea to a real person."],
    ],
  },
  {
    want: "I’m graduating with no direction",
    fear: "Which path is mine?",
    question: "What could I test before choosing?",
    directions: [
      ["Follow my strongest skill", "Use that skill in one real work sample."],
      ["Explore what gives me energy", "Track energy across three different tasks."],
      ["Choose stability first", "Compare five entry roles with one scorecard."],
      ["Take a structured gap", "Design one week with a clear learning goal."],
    ],
  },
  {
    want: "I want work that feels more like me",
    fear: "Grow here or start over?",
    question: "What could I test before making a leap?",
    directions: [
      ["Redesign my current role", "Remove or reshape one draining task."],
      ["Grow into the next role", "Borrow one task from that role."],
      ["Change careers", "Complete one real brief from a new field."],
      ["Create a portfolio path", "Publish one small piece of independent work."],
    ],
  },
  {
    want: "My relationship ended",
    fear: "Who am I on my own?",
    question: "What could I rediscover this week?",
    directions: [
      ["Rebuild life on my own", "Design one day around only your preferences."],
      ["Reconnect with myself", "Return to one part of life you stopped making room for."],
      ["Strengthen my support", "Reconnect with two people who make you feel grounded."],
      ["Rethink what I want", "Write what you want intimacy to feel like next time."],
    ],
  },
  {
    want: "I know I need to change",
    fear: "But where do I begin?",
    question: "What is small enough to test today?",
    directions: [
      ["Change how I spend my time", "Protect two hours for what keeps calling you."],
      ["Change the work I do", "Try one real task from a different role."],
      ["Change where I live", "Test one ordinary day in another place."],
      ["Change what I prioritize", "Remove one obligation and notice what returns."],
    ],
  },
];

const scenarioDemo = document.querySelector(".scenario-demo");
const scenarioOptions = [...document.querySelectorAll(".direction-option")];
const scenarioDots = [...document.querySelectorAll(".scenario-dots span")];
let scenarioIndex = 0;
let directionIndex = 0;

function renderScenario(index) {
  const scenario = scenarioExamples[index];
  const copy = document.querySelector(".scenario-copy");
  copy.classList.add("is-changing");
  window.setTimeout(() => {
    document.querySelector("#scenario-want").textContent = scenario.want;
    document.querySelector("#scenario-fear").textContent = scenario.fear;
    document.querySelector("#scenario-question").textContent = scenario.question;
    scenarioOptions.forEach((option, optionIndex) => {
      const [title, experiment] = scenario.directions[optionIndex];
      option.querySelector("strong").textContent = title;
      option.querySelector("small").innerHTML = `<b>7-day test:</b> ${experiment}`;
    });
    directionIndex = 0;
    updateActiveDirection();
    scenarioDots.forEach((dot, dotIndex) => dot.classList.toggle("is-active", dotIndex === index));
    copy.classList.remove("is-changing");
  }, 280);
}

function updateActiveDirection() {
  scenarioOptions.forEach((option, index) => option.classList.toggle("is-active", index === directionIndex));
}

if (scenarioDemo && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  window.setInterval(() => {
    directionIndex += 1;
    if (directionIndex >= scenarioOptions.length) {
      scenarioIndex = (scenarioIndex + 1) % scenarioExamples.length;
      renderScenario(scenarioIndex);
      return;
    }
    updateActiveDirection();
  }, 3000);
}

function showScreen(name, { scroll = true } = {}) {
  screens.forEach((screen) => screen.classList.toggle("active", screen.dataset.screen === name));
  const step = stepMap[name];
  progress.style.width = `${step * 20}%`;
  stepLabel.textContent = `Step ${step} of 5`;
  if (scroll) {
    document.querySelector("#preview").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderLives() {
  const grid = document.querySelector("#life-grid");
  document.querySelector("#lens-copy").textContent =
    `${state.priority} matters most right now · shaped around “${decisionTopic(state.decision)}”`;
  grid.innerHTML = state.directions.map((life) => `
    <article class="life-card" style="--accent:${life.color}">
      <h3>${escapeHtml(life.title)}</h3>
      <p>${escapeHtml(life.meaning)}</p>
      <div class="direction-tradeoffs">
        <span><strong>Gain</strong>${escapeHtml(life.gain)}</span>
        <span><strong>Give up</strong>${escapeHtml(life.giveUp)}</span>
      </div>
      <button class="button button-secondary" data-life="${escapeHtml(life.id)}">Explore this direction</button>
    </article>
  `).join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function selectLife(id) {
  state.life = state.directions.find((life) => life.id === id);
  document.querySelector("#experiment-title").textContent = state.life.title;
  document.querySelector("#experiment-intro").textContent =
    `You are not choosing this life forever. You are collecting one piece of evidence about whether it fits.`;
  document.querySelector("#lens-pill").textContent = `${state.priority} lens`;
  document.querySelector("#experiment-action").textContent = state.life.action;
  document.querySelector("#experiment-question").textContent = state.life.question;
  showScreen("experiment");
}

document.addEventListener("click", (event) => {
  const start = event.target.closest("[data-start]");
  if (start) {
    state.decision = "";
    state.priority = "";
    state.life = null;
    state.directions = [];
    document.querySelector("#decision-input").value = "";
    showScreen("decision");
  }

  const example = event.target.closest("[data-example]");
  if (example) document.querySelector("#decision-input").value = example.dataset.example;

  const priority = event.target.closest("[data-priority]");
  if (priority) {
    state.priority = priority.dataset.priority;
    state.directions = directionsForDecision(state.decision, state.priority);
    renderLives();
    captureEvent("directions viewed", {
      priority: state.priority,
      decision_category: decisionCategory(state.decision),
    });
    showScreen("lives");
  }

  const life = event.target.closest("[data-life]");
  if (life) {
    selectLife(life.dataset.life);
    captureEvent("direction selected", {
      direction: state.life.title,
      priority: state.priority,
      decision_category: decisionCategory(state.decision),
    });
  }

  const back = event.target.closest("[data-back]");
  if (back) showScreen(back.dataset.back);

  if (event.target.closest("[data-open-pilot]")) {
    const dialog = document.querySelector("#pilot-dialog");
    dialog.querySelector('[name="decision"]').value = state.decision;
    const priorityMap = {
      Stability: "Financial Security",
      Growth: "Career Growth",
      Freedom: "Freedom",
    };
    dialog.querySelectorAll('[name="areas"]').forEach((input) => {
      input.checked = input.value === priorityMap[state.priority];
    });
    dialog.showModal();
  }

  if (event.target.closest("[data-close-dialog]")) document.querySelector("#pilot-dialog").close();
  if (event.target.closest("[data-close-share]")) document.querySelector("#share-dialog").close();
});

document.querySelector("#decision-next").addEventListener("click", () => {
  const value = document.querySelector("#decision-input").value.trim();
  if (!value) {
    document.querySelector("#decision-input").focus();
    return;
  }
  state.decision = value;
  showScreen("priority");
});

document.querySelector("#decision-input").addEventListener("input", () => {
  if (decisionStartedCaptured) return;
  decisionStartedCaptured = true;
  captureEvent("decision started");
});

document.querySelector("#experiment-next").addEventListener("click", () => {
  document.querySelector("#review-copy").textContent =
    `While testing ${state.life.title.toLowerCase()}, pay attention to this: ${state.life.question} No conclusion has been drawn yet — your notes after the experiment become the evidence.`;
  document.querySelector("#timeline-direction").textContent = `${state.life.title} · ${state.priority} lens`;
  document.querySelector("#timeline-experiment").textContent = state.life.action;
  showScreen("journey");
});

document.querySelector("#share-demo").addEventListener("click", () => {
  document.querySelector("#share-title").textContent = `I am testing: ${state.life.title}`;
  document.querySelector("#share-decision").textContent = state.decision;
  document.querySelector("#share-action").textContent = state.life.action;
  document.querySelector("#share-dialog").showModal();
});

document.querySelector("#pilot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  const success = document.querySelector("#form-success");
  const error = document.querySelector("#form-error");
  const formData = new FormData(form);
  const data = Object.fromEntries(formData);
  data.areas = formData.getAll("areas");
  success.hidden = true;
  error.hidden = true;
  submitButton.disabled = true;
  submitButton.textContent = "Sending...";

  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) throw new Error("Form submission failed");

    captureEvent("waitlist submitted", {
      areas_count: data.areas.length,
    });
    success.hidden = false;
    form.reset();
  } catch {
    error.hidden = false;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Meet others at a crossroads";
  }
});

document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});

showScreen("decision", { scroll: false });
