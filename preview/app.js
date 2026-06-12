const state = {
  decision: "",
  priority: "",
  life: null,
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

const lives = [
  {
    id: "steady",
    title: "The Steady Builder",
    tag: "Protect the base",
    color: "#4386d7",
    description: "Keep the stable path while creating protected time to test the new direction.",
    tradeoff: "More security and optionality, but slower feedback and divided attention.",
    action: "Block one uninterrupted hour and complete the smallest real task from the path you are considering.",
    question: "Does direct contact with the work create enough energy to justify making more room for it?",
  },
  {
    id: "maverick",
    title: "The Full Bet",
    tag: "Commit and accelerate",
    color: "#ed6857",
    description: "Treat the new direction as the primary path and organize life around making it work.",
    tradeoff: "Faster learning and stronger momentum, with less financial and emotional buffer.",
    action: "Talk to one person who made the leap and ask for the hardest operational reality they did not anticipate.",
    question: "Do you want the daily reality of this path, or only the identity associated with it?",
  },
  {
    id: "adaptive",
    title: "The Adaptive Path",
    tag: "Prepare for change",
    color: "#8c6ed8",
    description: "Build a direction that remains useful even if the industry, timing, or plan changes.",
    tradeoff: "Greater resilience, but less certainty and a path that may be harder to explain.",
    action: "List three skills this direction requires, then test one of them in a real task for 45 minutes.",
    question: "Which part of this path remains valuable even if the original plan fails?",
  },
  {
    id: "wildcard",
    title: "The Third Option",
    tag: "Change the frame",
    color: "#d99822",
    description: "Reject the binary choice and design a smaller, more personal version of the life you want.",
    tradeoff: "More autonomy and originality, with fewer external milestones and less predictable income.",
    action: "Design and offer one tiny paid or public version of the idea to a real person.",
    question: "Can you create the freedom you want without adopting the entire imagined lifestyle?",
  },
];

const scenarioExamples = [
  {
    want: "I was laid off.",
    fear: "What now?",
    question: "What could I test before choosing my next role?",
    experiments: [
      ["Build a role scorecard", "Review ten past projects and define five conditions your next role must meet."],
      ["Compare two paths", "Use the same five questions in conversations with people from two possible fields."],
      ["Test one real task", "Complete a 90-minute work sample, then score your energy, skill, and curiosity."],
    ],
  },
  {
    want: "I’m graduating with no direction.",
    fear: "Which path is mine?",
    question: "What could I test before choosing?",
    experiments: [
      ["Map your strongest evidence", "Review five experiences and mark where ability, energy, and meaning overlapped."],
      ["Run three reality checks", "Ask three recent graduates what their work is actually like day to day."],
      ["Try two work samples", "Spend 90 minutes on one real task from each of two possible careers."],
    ],
  },
  {
    want: "I want work that feels more like me.",
    fear: "Grow here or start over?",
    question: "What could I test before making a leap?",
    experiments: [
      ["Audit your working week", "Track which tasks create energy, drain it, or make time disappear for five days."],
      ["Borrow the next role", "Take on one small task that belongs to the role you think you want."],
      ["Test the outside path", "Complete one real brief from the career you are considering."],
    ],
  },
  {
    want: "My relationship ended.",
    fear: "Who am I on my own?",
    question: "What could I rediscover this week?",
    experiments: [
      ["Recover one part of yourself", "Return to an activity, place, or person you stopped making room for."],
      ["Notice what is actually missing", "Keep a seven-day note separating loneliness, grief, relief, and desire."],
      ["Design one solo day", "Plan a day around your own preferences and record what feels alive again."],
    ],
  },
  {
    want: "I’m turning 30.",
    fear: "Am I already behind?",
    question: "What is small enough to test today?",
    experiments: [
      ["Separate desire from deadlines", "List ten things you think you should have, then mark which ones you truly want."],
      ["Choose one neglected direction", "Give one meaningful goal three protected 45-minute sessions this week."],
      ["Interview your future self", "Write two ordinary Tuesdays at 35 and compare what each life requires now."],
    ],
  },
  {
    want: "I know I need to change.",
    fear: "But where do I begin?",
    question: "What is small enough to test today?",
    experiments: [
      ["Find the recurring signal", "Review the last month and name the problem, desire, or idea that keeps returning."],
      ["Make one reversible move", "Take a step that costs under $25 and can be completed in under two hours."],
      ["Collect honest evidence", "After the step, record what gave you energy, resistance, and new information."],
    ],
  },
];

const scenarioDemo = document.querySelector(".scenario-demo");
const scenarioOptions = [...document.querySelectorAll(".experiment-option")];
const scenarioDots = [...document.querySelectorAll(".scenario-dots span")];
let scenarioIndex = 0;
let experimentIndex = 0;

function renderScenario(index) {
  const scenario = scenarioExamples[index];
  const copy = document.querySelector(".scenario-copy");
  copy.classList.add("is-changing");
  window.setTimeout(() => {
    document.querySelector("#scenario-want").textContent = scenario.want;
    document.querySelector("#scenario-fear").textContent = scenario.fear;
    document.querySelector("#scenario-question").textContent = scenario.question;
    scenarioOptions.forEach((option, optionIndex) => {
      const [title, detail] = scenario.experiments[optionIndex];
      option.querySelector("strong").textContent = title;
      option.querySelector("small").textContent = detail;
    });
    experimentIndex = 0;
    updateActiveExperiment();
    scenarioDots.forEach((dot, dotIndex) => dot.classList.toggle("is-active", dotIndex === index));
    copy.classList.remove("is-changing");
  }, 280);
}

function updateActiveExperiment() {
  scenarioOptions.forEach((option, index) => option.classList.toggle("is-active", index === experimentIndex));
}

if (scenarioDemo && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  window.setInterval(() => {
    experimentIndex += 1;
    if (experimentIndex >= scenarioOptions.length) {
      scenarioIndex = (scenarioIndex + 1) % scenarioExamples.length;
      renderScenario(scenarioIndex);
      return;
    }
    updateActiveExperiment();
  }, 2200);
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
    `You are viewing this decision through the lens of ${state.priority.toLowerCase()}. Each path gains and sacrifices something different.`;
  grid.innerHTML = lives.map((life) => `
    <article class="life-card" style="--accent:${life.color}">
      <span class="life-tag">${life.tag}</span>
      <h3>${life.title}</h3>
      <p>${life.description}</p>
      <div class="tradeoff"><strong>Trade-off:</strong> ${life.tradeoff}</div>
      <button class="button button-secondary" data-life="${life.id}">Test this direction</button>
    </article>
  `).join("");
}

function selectLife(id) {
  state.life = lives.find((life) => life.id === id);
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
    document.querySelector("#decision-input").value = "";
    showScreen("decision");
  }

  const example = event.target.closest("[data-example]");
  if (example) document.querySelector("#decision-input").value = example.dataset.example;

  const priority = event.target.closest("[data-priority]");
  if (priority) {
    state.priority = priority.dataset.priority;
    renderLives();
    showScreen("lives");
  }

  const life = event.target.closest("[data-life]");
  if (life) selectLife(life.dataset.life);

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

document.querySelector("#experiment-next").addEventListener("click", () => {
  document.querySelector("#review-copy").textContent =
    `You chose ${state.life.title.toLowerCase()} through a ${state.priority.toLowerCase()} lens. One experiment cannot settle the decision, but it can reveal whether the daily reality gives you energy or resistance.`;
  document.querySelector("#timeline-direction").textContent = `${state.life.title} · ${state.priority} lens`;
  showScreen("journey");
});

document.querySelector("#share-demo").addEventListener("click", () => {
  document.querySelector("#share-title").textContent = `I am testing: ${state.life.title}`;
  document.querySelector("#share-decision").textContent = state.decision;
  document.querySelector("#share-action").textContent = state.life.action;
  document.querySelector("#share-dialog").showModal();
});

document.querySelector("#pilot-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const data = Object.fromEntries(formData);
  data.areas = formData.getAll("areas");
  localStorage.setItem("my-parallel-lives-pilot-request", JSON.stringify({
    ...data,
    createdAt: new Date().toISOString(),
  }));
  document.querySelector("#form-success").hidden = false;
});

document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});

showScreen("decision", { scroll: false });
