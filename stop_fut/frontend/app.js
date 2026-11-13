// StopFut - Client Game Controller

const API_BASE = (window.location.protocol.startsWith("http") && window.location.port !== "9297") 
  ? window.location.origin 
  : "http://localhost:8080";

let state = {
  round: 1,
  totalScore: 0,
  currentLetter: "",
  categories: [],
  timeLeft: 60,
  timerId: null,
  isEnding: false
};

// Elementos DOM
const startScreen = document.getElementById("start-screen");
const gameScreen = document.getElementById("game-screen");
const resultsModal = document.getElementById("results-modal");

const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");
const btnNextRound = document.getElementById("btn-next-round");

const roundNumEl = document.getElementById("round-num");
const totalScoreEl = document.getElementById("total-score");
const currentLetterEl = document.getElementById("current-letter");
const timerValEl = document.getElementById("timer-val");
const timerCircle = document.querySelector(".timer-circle");
const categoriesContainer = document.getElementById("categories-container");
const resultsList = document.getElementById("results-list");
const roundPointsEarnedEl = document.getElementById("round-points-earned");
const roundSummaryTextEl = document.getElementById("round-summary-text");

// Event Listeners
btnStart.addEventListener("click", startRound);
btnStop.addEventListener("click", endRound);
btnNextRound.addEventListener("click", startNextRound);

async function startRound() {
  btnStart.disabled = true;
  btnStart.textContent = "Sorteando Letra...";

  try {
    const res = await fetch(`${API_BASE}/api/round`);
    const data = await res.json();

    state.currentLetter = data.letter;
    state.categories = data.categories;
    state.timeLeft = data.round_time || 60;
    state.isEnding = false;

    // Atualiza UI
    currentLetterEl.textContent = state.currentLetter;
    renderCategories(state.categories, state.currentLetter);

    startScreen.classList.add("hidden");
    gameScreen.classList.remove("hidden");
    resultsModal.classList.add("hidden");

    // Foca no primeiro input
    setTimeout(() => {
      const firstInput = document.querySelector(".category-input");
      if (firstInput) firstInput.focus();
    }, 100);

    // Inicia Timer
    startTimer();
  } catch (err) {
    alert("Erro ao conectar à API do StopFut em " + API_BASE + ". Verifique se o servidor backend está rodando!");
    console.error(err);
  } finally {
    btnStart.disabled = false;
    btnStart.textContent = "INICIAR PARTIDA ⚽";
  }
}

function renderCategories(categories, letter) {
  categoriesContainer.innerHTML = "";
  categories.forEach((cat) => {
    const card = document.createElement("div");
    card.className = "category-card";

    card.innerHTML = `
      <div class="category-info">
        <span class="category-icon">${cat.icon || "⚽"}</span>
        <span class="category-name">${cat.name}</span>
      </div>
      <div class="category-input-wrapper">
        <input 
          type="text" 
          class="category-input" 
          data-id="${cat.id}" 
          data-name="${cat.name}" 
          placeholder="Começa com a letra '${letter}'..."
          autocomplete="off"
        />
      </div>
    `;

    // Permite dar Enter e ir para o próximo campo
    const input = card.querySelector("input");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const inputs = Array.from(document.querySelectorAll(".category-input"));
        const currentIndex = inputs.indexOf(input);
        if (currentIndex < inputs.length - 1) {
          inputs[currentIndex + 1].focus();
        } else {
          endRound();
        }
      }
    });

    categoriesContainer.appendChild(card);
  });
}

function startTimer() {
  clearInterval(state.timerId);
  updateTimerUI();

  state.timerId = setInterval(() => {
    state.timeLeft--;
    updateTimerUI();

    if (state.timeLeft <= 0) {
      clearInterval(state.timerId);
      endRound();
    }
  }, 1000);
}

function updateTimerUI() {
  timerValEl.textContent = state.timeLeft;
  if (state.timeLeft <= 10) {
    timerCircle.classList.add("danger");
  } else {
    timerCircle.classList.remove("danger");
  }
}

async function endRound() {
  if (state.isEnding) return;
  state.isEnding = true;
  clearInterval(state.timerId);

  // Coleta respostas preenchidas
  const inputs = document.querySelectorAll(".category-input");
  const answers = Array.from(inputs).map((input) => ({
    id: input.dataset.id,
    name: input.dataset.name,
    answer: input.value.trim()
  }));

  // Exibe Modal em estado de carregamento
  resultsModal.classList.remove("hidden");
  roundSummaryTextEl.textContent = "O VAR está analisando as respostas no DynamoDB local...";
  resultsList.innerHTML = `
    <div style="text-align: center; padding: 30px; font-size: 1.1rem; color: #10b981;">
      ⏱️ Consultando dados e regras de futebol...
    </div>
  `;
  roundPointsEarnedEl.textContent = "...";

  try {
    const res = await fetch(`${API_BASE}/api/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        letter: state.currentLetter,
        answers: answers
      })
    });

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    resultsList.innerHTML = `<div style="color: #ef4444; padding: 20px;">Erro ao validar respostas: ${err.message}</div>`;
  }
}

function renderResults(data) {
  roundSummaryTextEl.textContent = `Avaliação completa da Rodada com a letra '${data.letter}'!`;
  roundPointsEarnedEl.textContent = `+${data.total_points} PTS`;

  // Atualiza pontuação global
  state.totalScore += data.total_points;
  totalScoreEl.textContent = state.totalScore;

  resultsList.innerHTML = "";
  data.results.forEach((item) => {
    const el = document.createElement("div");
    el.className = `result-item ${item.valid ? "valid" : ""}`;

    el.innerHTML = `
      <div class="result-top">
        <span class="result-cat">${item.name}</span>
        <span class="result-points">${item.valid ? "+10 PTS" : "0 PTS"}</span>
      </div>
      <div class="result-ans">${item.answer ? `"${item.answer}"` : "<em style='color: #6b7280'>(Em branco)</em>"}</div>
      <div class="result-reason">${item.reason}</div>
    `;

    resultsList.appendChild(el);
  });
}

function startNextRound() {
  state.round++;
  roundNumEl.textContent = state.round;
  resultsModal.classList.add("hidden");
  startRound();
}
