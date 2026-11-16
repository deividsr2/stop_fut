/**
 * StopFut - Cliente Frontend & Multiplayer (StopotS Pattern)
 * Suporta salas públicas/privadas, matchmaking rápido, sincronização em tempo real,
 * cronômetro sincronizado, evento STOP, decisão do VAR e ranking global.
 */

// Se configurado para AWS Lambda Function URL, usa a URL remota, senão relativo
const API_BASE = window.LAMBDA_API_URL || "";

// --- Gerador de Nomes & Avatares ---
const FOOTBALL_NICKNAMES = [
  "Craque", "Camisa10", "Goleador", "Paredao", "Artilheiro",
  "Xerife", "Boleiro", "Falcão", "Fenômeno", "Maestro",
  "Canhotinha", "Capitão", "Golaço", "Muralha", "Coringa"
];

const AVATAR_OPTIONS = [
  "👱‍♂️", "👨‍🦱", "🧢", "🧔", "👔", "🟨",
  "⚽", "🦁", "🧤", "🎯", "👑", "🎩"
];

// Estado Local do Jogador
let currentUser = {
  id: localStorage.getItem("stopfut_uid") || `u_${Math.random().toString(36).substring(2, 9)}`,
  name: localStorage.getItem("stopfut_name") || `${FOOTBALL_NICKNAMES[Math.floor(Math.random() * FOOTBALL_NICKNAMES.length)]}_${Math.floor(Math.random() * 900 + 100)}`,
  avatar: localStorage.getItem("stopfut_avatar") || "👱‍♂️",
  email: localStorage.getItem("stopfut_email") || ""
};

localStorage.setItem("stopfut_uid", currentUser.id);
localStorage.setItem("stopfut_name", currentUser.name);
localStorage.setItem("stopfut_avatar", currentUser.avatar);

// Estado da Sala
let currentRoomId = null;
let roomPollInterval = null;
let currentRoomState = null;
let roundSubmitted = false;
let localTimerInterval = null;

// ========================================================
// INICIALIZAÇÃO
// ========================================================
document.addEventListener("DOMContentLoaded", () => {
  initProfileUI();
  initTutorialCarousel();
  initModals();
  initActions();
  checkUrlForRoomInvite();
});

function initProfileUI() {
  const avatarDisplay = document.getElementById("user-avatar-display");
  const nickInput = document.getElementById("nickname-input");

  avatarDisplay.textContent = currentUser.avatar;
  nickInput.value = currentUser.name;

  nickInput.addEventListener("change", (e) => {
    const val = e.target.value.trim();
    if (val) {
      currentUser.name = val;
      localStorage.setItem("stopfut_name", val);
    }
  });

  document.getElementById("btn-random-name").addEventListener("click", () => {
    const base = FOOTBALL_NICKNAMES[Math.floor(Math.random() * FOOTBALL_NICKNAMES.length)];
    const num = Math.floor(Math.random() * 900 + 100);
    const newName = `${base}_${num}`;
    currentUser.name = newName;
    nickInput.value = newName;
    localStorage.setItem("stopfut_name", newName);
  });

  // Modal Seletor de Avatar
  const avatarPicker = document.getElementById("avatar-grid-picker");
  avatarPicker.innerHTML = "";
  AVATAR_OPTIONS.forEach(av => {
    const btn = document.createElement("button");
    btn.className = "avatar-choice-btn";
    btn.textContent = av;
    btn.onclick = () => {
      currentUser.avatar = av;
      avatarDisplay.textContent = av;
      localStorage.setItem("stopfut_avatar", av);
      closeModal("modal-avatars");
    };
    avatarPicker.appendChild(btn);
  });

  document.getElementById("btn-edit-avatar").addEventListener("click", () => {
    openModal("modal-avatars");
  });

  // Google Sign-In Callback (se o script Google for carregado)
  window.handleGoogleCredentialResponse = async (response) => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential: response.credential })
      });
      const data = await res.json();
      if (data.profile) {
        currentUser.id = data.profile.id;
        currentUser.name = data.profile.name;
        currentUser.email = data.profile.email;
        localStorage.setItem("stopfut_uid", currentUser.id);
        localStorage.setItem("stopfut_name", currentUser.name);
        localStorage.setItem("stopfut_email", currentUser.email);
        nickInput.value = currentUser.name;
        document.getElementById("logged-email-text").textContent = `Conectado como: ${currentUser.email}`;
        document.getElementById("logged-user-bar").classList.remove("hidden");
        document.getElementById("google-login-btn").classList.add("hidden");
      }
    } catch (e) {
      console.warn("Erro no login Google:", e);
    }
  };

  document.getElementById("btn-logout-google").addEventListener("click", () => {
    localStorage.removeItem("stopfut_email");
    currentUser.email = "";
    document.getElementById("logged-user-bar").classList.add("hidden");
    document.getElementById("google-login-btn").classList.remove("hidden");
  });
}

// ========================================================
// CARROSSEL TUTORIAL (STOPOTS PATTERN)
// ========================================================
function initTutorialCarousel() {
  const steps = [
    { icon: "⏱️", title: "1. TIC-TAC", desc: "Preencha categorias de futebol com a letra sorteada antes do tempo acabar!" },
    { icon: "🏟️", title: "2. ESCOLHA A SALA", desc: "Crie uma sala privada para a galera ou clique em Jogar para entrar em uma sala pública!" },
    { icon: "🚨", title: "3. GRITE STOP!", desc: "Seja o primeiro a terminar para parar a contagem regressiva de todos na sala!" },
    { icon: "🖥️", title: "4. O VAR DECIDE", desc: "A arbitragem inteligente analisa posições, clubes e valida os golaços da rodada!" }
  ];

  let currentStep = 0;
  const iconEl = document.getElementById("tutorial-icon");
  const titleEl = document.getElementById("tutorial-title");
  const descEl = document.getElementById("tutorial-desc");
  const dots = document.querySelectorAll(".carousel-dots .dot");

  function renderStep(idx) {
    currentStep = idx;
    iconEl.textContent = steps[idx].icon;
    titleEl.textContent = steps[idx].title;
    descEl.textContent = steps[idx].desc;
    dots.forEach((d, i) => d.classList.toggle("active", i === idx));
  }

  dots.forEach(d => {
    d.addEventListener("click", () => renderStep(parseInt(d.dataset.step)));
  });

  setInterval(() => {
    renderStep((currentStep + 1) % steps.length);
  }, 4500);
}

// ========================================================
// AÇÕES DO LOBBY (JOGAR, CRIAR SALA, SALAS)
// ========================================================
function initActions() {
  // Partida Rápida (JOGAR)
  document.getElementById("btn-quick-play").addEventListener("click", async () => {
    try {
      const res = await fetch(`${API_BASE}/api/rooms/quick_match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: currentUser.id,
          nickname: currentUser.name,
          avatar: currentUser.avatar
        })
      });
      const data = await res.json();
      if (data.room_id) {
        enterRoom(data.room_id);
      }
    } catch (e) {
      alert("Erro ao buscar partida rápida: " + e.message);
    }
  });

  // Abrir Modal Criar Sala
  document.getElementById("btn-open-create-room").addEventListener("click", () => {
    openModal("modal-create-room");
  });

  // Toggle do campo de senha
  document.getElementById("create-room-private").addEventListener("change", (e) => {
    document.getElementById("password-field-group").classList.toggle("hidden", !e.target.checked);
  });

  // Submeter Criar Sala
  document.getElementById("btn-submit-create-room").addEventListener("click", async () => {
    const name = document.getElementById("create-room-name").value.trim() || `Sala de ${currentUser.name}`;
    const roundTime = parseInt(document.getElementById("create-room-time").value);
    const roundsTotal = parseInt(document.getElementById("create-room-rounds").value);
    const isPrivate = document.getElementById("create-room-private").checked;
    const password = document.getElementById("create-room-password").value.trim();

    try {
      const res = await fetch(`${API_BASE}/api/rooms/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          is_private: isPrivate,
          password,
          rounds_total: roundsTotal,
          round_time: roundTime,
          user_id: currentUser.id,
          nickname: currentUser.name,
          avatar: currentUser.avatar
        })
      });
      const room = await res.json();
      closeModal("modal-create-room");
      enterRoom(room.id);
    } catch (e) {
      alert("Erro ao criar sala: " + e.message);
    }
  });

  // Abrir Modal Lista de Salas
  document.getElementById("btn-open-rooms-list").addEventListener("click", () => {
    loadRoomsList();
    openModal("modal-rooms-list");
  });

  document.getElementById("btn-refresh-rooms").addEventListener("click", loadRoomsList);

  // Abrir Ranking Global
  document.getElementById("btn-open-ranking").addEventListener("click", () => {
    loadGlobalRanking();
    openModal("modal-ranking");
  });

  // Sair da Sala
  document.getElementById("btn-leave-room").addEventListener("click", () => {
    leaveRoom();
  });

  // Host Inicia Jogo
  document.getElementById("btn-start-game").addEventListener("click", async () => {
    try {
      await fetch(`${API_BASE}/api/rooms/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_id: currentRoomId, user_id: currentUser.id })
      });
    } catch (e) {
      alert("Erro ao iniciar jogo: " + e.message);
    }
  });

  // Botão STOP da Partida
  document.getElementById("btn-stop-game").addEventListener("click", async () => {
    try {
      await fetch(`${API_BASE}/api/rooms/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_id: currentRoomId, user_id: currentUser.id })
      });
    } catch (e) {
      console.warn("Erro ao acionar STOP:", e);
    }
  });

  // Próxima Rodada (Host)
  document.getElementById("btn-next-round-action").addEventListener("click", async () => {
    try {
      closeModal("modal-results");
      await fetch(`${API_BASE}/api/rooms/next_round`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_id: currentRoomId, user_id: currentUser.id })
      });
    } catch (e) {
      alert("Erro ao avançar rodada: " + e.message);
    }
  });

  // Copiar Link da Sala
  document.getElementById("btn-copy-link").addEventListener("click", () => {
    const input = document.getElementById("share-link-input");
    input.select();
    navigator.clipboard.writeText(input.value);
    alert("Link copiado! Envie para seus amigos entrarem na sala.");
  });
}

// ========================================================
// GESTÃO DE SALAS & MULTIPLAYER EM TEMPO REAL
// ========================================================
async function loadRoomsList() {
  const container = document.getElementById("rooms-items-container");
  container.innerHTML = "<p class='text-muted'>Carregando salas...</p>";

  try {
    const res = await fetch(`${API_BASE}/api/rooms`);
    const data = await res.json();
    const rooms = data.rooms || [];

    if (rooms.length === 0) {
      container.innerHTML = "<p class='text-muted text-center'>Nenhuma sala pública no momento. Crie uma e convide a galera!</p>";
      return;
    }

    container.innerHTML = "";
    rooms.forEach(r => {
      const card = document.createElement("div");
      card.className = "room-list-card";
      card.innerHTML = `
        <div>
          <div class="room-list-name">${r.name}</div>
          <div class="room-list-meta">Host: ${r.host_name} • ${r.players_count}/${r.max_players} Jogadores • ${r.round_time}s</div>
        </div>
        <button class="btn-join-room" onclick="promptJoinRoom('${r.id}', ${r.is_private})">ENTRAR</button>
      `;
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = "<p class='text-muted'>Erro ao carregar salas.</p>";
  }
}

window.promptJoinRoom = (roomId, isPrivate) => {
  let pwd = "";
  if (isPrivate) {
    pwd = prompt("Esta sala é privada. Digite a senha de acesso:") || "";
    if (!pwd) return;
  }
  closeModal("modal-rooms-list");
  enterRoom(roomId, pwd);
};

async function enterRoom(roomId, password = "") {
  try {
    const res = await fetch(`${API_BASE}/api/rooms/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room_id: roomId,
        user_id: currentUser.id,
        nickname: currentUser.name,
        avatar: currentUser.avatar,
        password: password
      })
    });
    const data = await res.json();
    if (data.error) {
      alert(data.error);
      return;
    }

    currentRoomId = roomId;
    roundSubmitted = false;

    // Atualiza URL com o ID da sala para compartilhamento fácil
    const newUrl = `${window.location.origin}${window.location.pathname}?room=${roomId}`;
    window.history.pushState({ path: newUrl }, "", newUrl);
    document.getElementById("share-link-input").value = newUrl;

    // Transiciona para o Lobby da Sala
    document.getElementById("screen-home").classList.add("hidden");
    document.getElementById("screen-game").classList.add("hidden");
    document.getElementById("screen-room-lobby").classList.remove("hidden");

    // Inicia Polling Sincronizado da Sala a cada 1.5s
    if (roomPollInterval) clearInterval(roomPollInterval);
    roomPollInterval = setInterval(pollRoomState, 1500);
    pollRoomState();
  } catch (e) {
    alert("Erro ao entrar na sala: " + e.message);
  }
}

function leaveRoom() {
  if (roomPollInterval) clearInterval(roomPollInterval);
  currentRoomId = null;
  currentRoomState = null;
  roundSubmitted = false;

  window.history.pushState({}, "", window.location.pathname);
  document.getElementById("screen-room-lobby").classList.add("hidden");
  document.getElementById("screen-game").classList.add("hidden");
  closeModal("modal-results");
  document.getElementById("screen-home").classList.remove("hidden");
}

async function pollRoomState() {
  if (!currentRoomId) return;

  try {
    const res = await fetch(`${API_BASE}/api/rooms/state?room_id=${currentRoomId}&user_id=${currentUser.id}`);
    const state = await res.json();
    if (state.error) {
      leaveRoom();
      return;
    }

    currentRoomState = state;
    renderRoomState(state);
  } catch (e) {
    console.warn("Erro no polling da sala:", e);
  }
}

function renderRoomState(state) {
  // 1. Atualiza Informações do Cabeçalho da Sala
  document.getElementById("lobby-room-name").textContent = state.name;
  document.getElementById("lobby-room-info").textContent = `${state.rounds_total} Rodadas • ${state.round_time}s • ${state.players_count} Jogadores`;

  // 2. Renderiza Lista de Jogadores no Lobby
  const listEl = document.getElementById("lobby-players-list");
  listEl.innerHTML = "";
  state.players.forEach(p => {
    const badge = document.createElement("div");
    badge.className = `player-card-badge ${p.is_host ? "is-host" : ""}`;
    badge.innerHTML = `
      ${p.is_host ? '<span class="host-crown" title="Host da Sala">👑</span>' : ""}
      <span class="player-badge-avatar">${p.avatar}</span>
      <div>
        <div class="player-badge-name">${p.name} ${p.id === currentUser.id ? "(Você)" : ""}</div>
        <div class="player-badge-score">${p.score} pts</div>
      </div>
    `;
    listEl.appendChild(badge);
  });

  // 3. Controles do Host
  const hostCtrl = document.getElementById("host-controls");
  const guestMsg = document.getElementById("guest-waiting-msg");
  if (state.is_host) {
    hostCtrl.classList.remove("hidden");
    guestMsg.classList.add("hidden");
  } else {
    hostCtrl.classList.add("hidden");
    guestMsg.classList.remove("hidden");
  }

  // 4. Se o jogo está em andamento (PLAYING)
  if (state.status === "PLAYING") {
    document.getElementById("screen-room-lobby").classList.add("hidden");
    document.getElementById("screen-game").classList.remove("hidden");
    closeModal("modal-results");

    document.getElementById("match-round-indicator").textContent = `${state.current_round} / ${state.rounds_total}`;
    document.getElementById("current-letter").textContent = state.letter;
    document.getElementById("timer-val").textContent = state.time_left;
    document.getElementById("stop-alert-banner").classList.add("hidden");

    // Renderiza campos de categorias apenas se mudou a rodada
    renderMatchCategories(state.categories, state.letter);
  }

  // 5. Se alguém parou a rodada (RESULTS)
  if (state.status === "RESULTS") {
    if (state.stopped_by) {
      document.getElementById("stop-alert-banner").classList.remove("hidden");
      document.getElementById("stopped-player-name").textContent = state.stopped_by;
    }

    // Se ainda não submetemos as respostas locais, submete agora!
    if (!roundSubmitted) {
      roundSubmitted = true;
      submitLocalAnswers();
    }

    // Atualiza placar da sala no modal
    renderRoomScoreboard(state.players);

    // Controles do host para avançar
    const nextBtn = document.getElementById("btn-next-round-action");
    const waitSpan = document.getElementById("guest-next-round-wait");
    if (state.is_host) {
      nextBtn.classList.remove("hidden");
      waitSpan.classList.add("hidden");
    } else {
      nextBtn.classList.add("hidden");
      waitSpan.classList.remove("hidden");
    }
  }

  // 6. Jogo Finalizado (FINISHED)
  if (state.status === "FINISHED") {
    openPodiumScreen(state.players);
  }
}

let renderedCategoryIds = "";
function renderMatchCategories(categories, letter) {
  const currentIds = categories.map(c => c.id).join(",");
  if (renderedCategoryIds === currentIds) return;
  renderedCategoryIds = currentIds;
  roundSubmitted = false;

  const container = document.getElementById("categories-container");
  container.innerHTML = "";

  categories.forEach((cat, idx) => {
    const row = document.createElement("div");
    row.className = "cat-row-card";
    row.innerHTML = `
      <div class="cat-icon-badge">${cat.icon || "⚽"}</div>
      <div class="cat-name-box">
        <div class="cat-title">${cat.name}</div>
      </div>
      <div class="cat-input-box">
        <input type="text" id="cat-input-${idx}" data-id="${cat.id}" data-name="${cat.name}" placeholder="Comece com '${letter}'..." autocomplete="off">
      </div>
    `;
    container.appendChild(row);
  });

  // Foco no primeiro campo
  setTimeout(() => {
    const firstInput = document.getElementById("cat-input-0");
    if (firstInput) firstInput.focus();
  }, 100);
}

// Submissão das Respostas do Jogador para Validação do VAR
async function submitLocalAnswers() {
  const inputs = document.querySelectorAll("#categories-container input");
  const answers = [];
  inputs.forEach(inp => {
    inp.disabled = true;
    answers.push({
      id: inp.dataset.id,
      name: inp.dataset.name,
      answer: inp.value.trim()
    });
  });

  try {
    const res = await fetch(`${API_BASE}/api/rooms/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room_id: currentRoomId,
        user_id: currentUser.id,
        answers: answers
      })
    });
    const data = await res.json();
    renderVarResultsModal(data);
  } catch (e) {
    console.warn("Erro ao enviar respostas:", e);
  }
}

function renderVarResultsModal(data) {
  document.getElementById("var-round-title").textContent = `Rodada com a Letra '${currentRoomState?.letter || ""}'`;
  document.getElementById("round-earned-points").textContent = `+${data.total_points || 0} PTS`;

  const resultsList = document.getElementById("var-results-list");
  resultsList.innerHTML = "";

  (data.results || []).forEach(r => {
    const card = document.createElement("div");
    card.className = `var-card-row ${r.valid ? "valid" : "invalid"}`;
    card.innerHTML = `
      <div>
        <div class="var-info-cat">${r.name}</div>
        <div class="var-user-answer">"${r.answer || "(Em branco)"}"</div>
        <div class="var-reason">${r.reason}</div>
      </div>
      <div class="var-pts-tag">${r.valid ? `+${r.points} PTS` : "0 PTS"}</div>
    `;
    resultsList.appendChild(card);
  });

  openModal("modal-results");
}

function renderRoomScoreboard(players) {
  const board = document.getElementById("room-scoreboard-list");
  board.innerHTML = "";
  players.forEach((p, idx) => {
    const row = document.createElement("div");
    row.className = "score-player-item";
    row.innerHTML = `
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-weight: 800; color: #ffcc00; width: 20px;">#${idx + 1}</span>
        <span>${p.avatar}</span>
        <strong>${p.name} ${p.id === currentUser.id ? "(Você)" : ""}</strong>
      </div>
      <strong style="color: #ffea79;">${p.score} pts</strong>
    `;
    board.appendChild(row);
  });
}

function openPodiumScreen(players) {
  closeModal("modal-results");
  const p1 = players[0] || { name: "Ninguém", avatar: "⚽", score: 0 };
  const p2 = players[1] || null;
  const p3 = players[2] || null;

  alert(`🏆 FIM DE PARTIDA! PÓDIO DOS CRAQUES:\n🥇 1º Lugar: ${p1.name} (${p1.score} pts)\n${p2 ? `🥈 2º Lugar: ${p2.name} (${p2.score} pts)\n` : ""}${p3 ? `🥉 3º Lugar: ${p3.name} (${p3.score} pts)` : ""}`);
  leaveRoom();
}

// ========================================================
// RANKING GERAL (LÍDERES GLOBAIS)
// ========================================================
async function loadGlobalRanking() {
  const container = document.getElementById("ranking-global-container");
  container.innerHTML = "<p class='text-muted'>Carregando ranking global...</p>";

  try {
    const res = await fetch(`${API_BASE}/api/ranking`);
    const data = await res.json();
    const list = data.ranking || [];

    container.innerHTML = "";
    list.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "rank-row";
      row.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="rank-pos">#${idx + 1}</span>
          <span style="font-size: 1.4rem;">${item.avatar || "⚽"}</span>
          <strong>${item.name}</strong>
        </div>
        <strong style="color: #ffea79;">${item.score} pts</strong>
      `;
      container.appendChild(row);
    });
  } catch (e) {
    container.innerHTML = "<p class='text-muted'>Erro ao carregar ranking.</p>";
  }
}

// ========================================================
// MODAIS HELPERS
// ========================================================
function openModal(id) {
  document.getElementById(id).classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

function initModals() {
  document.querySelectorAll(".btn-close-modal").forEach(btn => {
    btn.addEventListener("click", () => {
      closeModal(btn.dataset.close);
    });
  });
}

function checkUrlForRoomInvite() {
  const params = new URLSearchParams(window.location.search);
  const roomId = params.get("room");
  if (roomId) {
    setTimeout(() => {
      if (confirm(`Deseja entrar na sala '${roomId}'?`)) {
        enterRoom(roomId);
      }
    }, 500);
  }
}
