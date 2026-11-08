// 에이전트 루프 화면 — 서버가 SSE로 보내는 이벤트(events.py)를 받아 카드로 그린다.
// 빌드 단계 없는 바닐라 JS. 위에서 아래로 읽으면 된다.

const $ = (sel) => document.querySelector(sel);

// 서버가 보내는 이벤트 종류 (src/agentloop/events.py 와 같은 목록)
const EVENT_TYPES = [
  "run_start", "tools_listed", "step_start", "thinking_delta", "thinking_done",
  "tool_call", "tool_result", "answer", "error", "run_end",
];
// "한 단계씩 보기"에서 버튼 한 번에 드러낼 큰 단계 (thinking_delta 같은 조각은 함께 흘려보낸다)
const MAJOR_TYPES = new Set(["tools_listed", "thinking_done", "tool_call", "tool_result", "answer", "error", "run_end"]);
const STOP_LABELS = { answer: "답을 냄", max_steps: "최대 회차 도달", error: "오류", cancelled: "취소됨" };
const MY_TOOLS_HINT = "이 도구는 servers/my_tools_server.py 의 함수 하나입니다. 고쳐서 내 도구를 붙여 보세요.";

let config = null;        // /api/config 응답
let source = null;        // 지금 열린 EventSource
let stepMode = false;     // 한 단계씩 보기
let pending = [];         // 한 단계씩 보기에서 아직 안 그린 이벤트
let current = {};         // 지금 그리고 있는 카드들 (생각 카드 등)
let waitTimer = null;     // "모델 응답 기다리는 중… n초" 타이머

// ── 작은 도우미 ─────────────────────────────────────────────
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text; // textContent: HTML로 해석하지 않아 안전
  return node;
}
function json(value) { return JSON.stringify(value, null, 2); }
function oneLine(value) { return JSON.stringify(value); }
function fmtSec(s) {
  if (s < 60) return `${s.toFixed(1)}초`;
  return `${Math.floor(s / 60)}분 ${Math.round(s % 60)}초`;
}
function details(summaryText, body) {
  const d = el("details");
  d.append(el("summary", null, summaryText), el("pre", null, body));
  return d;
}
function card(kind, title, time) {
  const c = el("div", `card ${kind}`);
  const head = el("div", "card-head");
  head.append(el("span", "card-title", title), el("span", "card-time", time ?? ""));
  c.append(head);
  $("#timeline").append(c);
  c.scrollIntoView({ block: "nearest" });
  return c;
}
function stopWaitTimer() {
  if (waitTimer) clearInterval(waitTimer);
  waitTimer = null;
}
function highlight(nodeId, isError = false) {
  document.querySelectorAll("#loop .node").forEach((n) => n.classList.remove("active", "error"));
  if (!nodeId) return;
  const node = document.getElementById(nodeId);
  node.classList.add("active");
  if (isError) node.classList.add("error");
}

// ── 처음 화면: 설정과 MCP 서버 목록 ───────────────────────────
async function loadConfig() {
  config = await (await fetch("/api/config")).json();
  $("#mode-select").value = config.mode;
  $("#notice").textContent = config.notice;
  updateBadge();
  const box = $("#examples");
  config.examples.forEach((q, i) => {
    const b = el("button", "example", `예시 ${i + 1}: ${q}`);
    b.type = "button";
    b.dataset.question = q;
    b.addEventListener("click", () => { $("#question").value = q; startRun(); });
    box.append(b);
  });
}

function updateBadge() {
  const mode = $("#mode-select").value;
  const badge = $("#mode-badge");
  badge.className = `badge ${mode}`;
  badge.textContent = mode === "mock" ? "모의 모드 · 대본 LLM + 진짜 MCP 서버" : `실제 모드 · Ollama ${config.model}`;
}

async function loadTools() {
  const list = $("#server-list");
  list.replaceChildren(el("p", "muted", "서버에 연결하는 중…"));
  const res = await fetch("/api/tools");
  const data = await res.json();
  if (!res.ok) {
    list.replaceChildren(el("p", "chip err", data.error));
    return;
  }
  renderServers(list, data.servers);
}

function renderServers(list, servers) {
  list.replaceChildren();
  for (const server of servers) {
    const box = el("div", "server");
    box.dataset.server = server.name;
    box.append(el("div", "server-name", `${server.name}  ·  도구 ${server.tools.length}개`));
    if (server.name === "my_tools") box.append(el("p", "server-hint", MY_TOOLS_HINT));
    for (const tool of server.tools) {
      const t = el("div", "tool");
      t.append(el("div", "tool-name mono", tool.name), el("p", "tool-desc", tool.description));
      // 입력 스키마의 properties → "item: string — 설명" 목록
      const props = (tool.input_schema && tool.input_schema.properties) || {};
      const ul = el("ul", "tool-params");
      const names = Object.keys(props);
      if (names.length === 0) ul.append(el("li", null, "인자 없음"));
      for (const name of names) {
        const p = props[name];
        ul.append(el("li", null, `${name}: ${p.type || "?"}${p.description ? " — " + p.description : ""}`));
      }
      t.append(ul, details("입력·출력 스키마(JSON) 보기", json({ inputSchema: tool.input_schema, outputSchema: tool.output_schema })));
      box.append(t);
    }
    list.append(box);
  }
}

// ── 실행: EventSource로 SSE 받기 ─────────────────────────────
function startRun() {
  const question = $("#question").value.trim();
  if (!question || source) return;

  // 화면 초기화
  $("#timeline").replaceChildren();
  $("#summary").className = "summary";
  $("#summary").textContent = "";
  $("#history").replaceChildren();
  pending = [];
  current = {};
  updatePending();
  highlight(null);
  document.body.dataset.runState = "running";
  document.body.dataset.streamState = "open"; // 서버 스트림 상태 (한 단계씩 보기에서는 화면보다 먼저 끝난다)
  $("#run").disabled = true;
  $("#stop").disabled = false;

  const mode = $("#mode-select").value;
  const url = `/api/run?q=${encodeURIComponent(question)}&mode=${mode}`;
  let received = 0;
  let ended = false;
  source = new EventSource(url);

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (e) => {
      received += 1;
      const event = JSON.parse(e.data);
      if (type === "run_end") { ended = true; document.body.dataset.streamState = "ended"; closeSource(); } // 끝나면 바로 닫는다(안 닫으면 브라우저가 재접속해 다시 실행한다)
      if (stepMode) { pending.push(event); updatePending(); } else { render(event); }
    });
  }
  source.onerror = () => {
    if (ended) return;
    closeSource();
    const msg = received === 0
      ? "실행을 시작하지 못했습니다. 다른 실행이 진행 중이거나 서버가 꺼져 있습니다."
      : "서버와 연결이 끊겼습니다.";
    const c = card("error-banner", "연결 오류");
    c.append(el("div", "card-body", msg));
    finishUi("error");
  };
}

function closeSource() {
  if (source) source.close();
  source = null;
}

function stopRun() {
  // 연결을 끊으면 서버가 알아채고 에이전트를 취소, MCP 서버 프로세스를 정리한다
  closeSource();
  pending = [];
  updatePending();
  const c = card("stopped", "중지");
  c.append(el("div", "card-body", "실행을 중지했습니다. 서버 쪽 에이전트도 취소됩니다."));
  finishUi("stopped");
}

function finishUi(state) {
  stopWaitTimer();
  document.body.dataset.runState = state;
  $("#run").disabled = false;
  $("#stop").disabled = true;
}

// ── 한 단계씩 보기 ───────────────────────────────────────────
function updatePending() {
  const steps = pending.filter((e) => MAJOR_TYPES.has(e.type)).length; // 생각 조각은 빼고 "단계"만 센다
  $("#pending-count").textContent = stepMode && pending.length ? `(${steps}단계 대기)` : "";
  $("#next-step").disabled = !(stepMode && pending.length);
}
function nextStep() {
  // 큰 단계 하나가 그려질 때까지 이벤트를 꺼내 그린다
  while (pending.length) {
    const event = pending.shift();
    render(event);
    if (MAJOR_TYPES.has(event.type)) break;
  }
  updatePending();
}

// ── 이벤트 → 화면 ───────────────────────────────────────────
function render(ev) {
  const handler = RENDERERS[ev.type];
  if (handler) handler(ev);
}

const RENDERERS = {
  run_start(ev) {
    $("#timeline").append(el("p", "muted", `질문: ${ev.question}  ·  모델: ${ev.model}`));
  },

  tools_listed(ev) {
    const toolCount = ev.servers.reduce((n, s) => n + s.tools.length, 0);
    const c = card("prep", "준비", `${ev.seconds.toFixed(1)}초`);
    c.append(el("div", "card-body", `MCP 서버 ${ev.servers.length}개 연결, 도구 ${toolCount}개 받음 (tools/list)`));
    c.append(details("tools/list 응답 보기", json(ev.wire)));
    renderServers($("#server-list"), ev.servers);
  },

  step_start(ev) {
    const head = el("div", "step-head");
    head.append(el("span", null, `회차 ${ev.step}`), el("span", null, `모델에게 메시지 ${ev.messages_count}개 전송`));
    $("#timeline").append(head);
    renderHistory(ev.messages_preview);
    highlight("node-plan");

    // 생각 카드를 미리 만들고, 첫 글자가 올 때까지 기다린 시간을 보여 준다(실제 모드는 모델 적재로 오래 걸릴 수 있다)
    const c = card("thinking", `회차 ${ev.step} · 생각`);
    const body = el("div", "card-body waiting", "모델 응답 기다리는 중… 0초");
    c.append(body);
    current = { thinkingCard: c, thinkingBody: body, thinkingText: "", step: ev.step };
    const startedAt = Date.now();
    stopWaitTimer();
    waitTimer = setInterval(() => {
      body.textContent = `모델 응답 기다리는 중… ${Math.round((Date.now() - startedAt) / 1000)}초`;
    }, 1000);
  },

  thinking_delta(ev) {
    stopWaitTimer();
    current.thinkingText += ev.text;
    current.thinkingBody.classList.remove("waiting");
    current.thinkingBody.textContent = current.thinkingText;
  },

  thinking_done(ev) {
    stopWaitTimer();
    current.thinkingBody.classList.remove("waiting");
    current.thinkingBody.textContent = ev.text || "(생각 없음)";
    current.thinkingCard.querySelector(".card-time").textContent = `${ev.chars}자 · ${fmtSec(ev.seconds)}`;
  },

  tool_call(ev) {
    highlight("node-act");
    const c = card("call", `회차 ${ev.step} · 도구 호출`, `${ev.t.toFixed(1)}초`);
    c.dataset.callId = ev.call_id;
    const title = c.querySelector(".card-title");
    title.append(el("span", "chip", `서버 ${ev.server ?? "없음"}`));
    if (ev.duplicate) title.append(el("span", "chip dup", "중복 호출"));
    c.append(el("div", "card-body mono", `${ev.name} ${oneLine(ev.arguments)}`));
    if (ev.server === "my_tools") c.append(el("p", "hint", MY_TOOLS_HINT));
    c.append(details("MCP 요청 보기 (tools/call)", json(ev.wire_request)));
  },

  tool_result(ev) {
    highlight("node-observe", ev.is_error);
    const c = card(ev.is_error ? "observe error" : "observe", `회차 ${ev.step} · 관찰`, fmtSec(ev.seconds));
    c.dataset.callId = ev.call_id;
    if (ev.is_error) c.querySelector(".card-title").append(el("span", "chip err", "isError: true"));
    c.append(el("div", "card-body mono", ev.observation));
    if (ev.is_error) c.append(el("p", "hint", "오류도 관찰입니다. 이 문구가 그대로 모델에게 돌아가 다음 회차 생각의 재료가 됩니다."));
    c.append(details("MCP 응답 보기 (content · structuredContent · isError)", json(ev.wire_response)));
  },

  answer(ev) {
    highlight("node-answer");
    const c = card("answer", "최종 답", `${ev.t.toFixed(1)}초`);
    c.append(el("div", "card-body", ev.text));
    appendHistory({ role: "assistant", text: ev.text }, "(최종 답 — 도구 요청 없음 → 루프 종료)");
  },

  error(ev) {
    const c = card("error-banner", "오류");
    c.append(el("div", "card-body", ev.message));
    if (ev.hint) c.append(el("p", "hint", ev.hint));
  },

  run_end(ev) {
    stopWaitTimer();
    if (ev.stop_reason !== "answer") highlight(null);
    const s = $("#summary");
    s.textContent = `회차 ${ev.steps} · 도구 호출 ${ev.tool_calls} · 오류 ${ev.errors} · 총 ${fmtSec(ev.seconds)} · ${STOP_LABELS[ev.stop_reason] ?? ev.stop_reason}`;
    s.className = `summary done ${ev.stop_reason}`;
    finishUi("done");
  },
};

// ── 대화 기록 패널 ───────────────────────────────────────────
function renderHistory(messages) {
  const list = $("#history");
  const before = list.children.length;
  list.replaceChildren();
  messages.forEach((m, i) => appendHistory(m, null, i >= before && before > 0));
}
function appendHistory(m, extra, isNew = true) {
  const li = el("li", isNew ? "new" : "");
  const role = el("span", `role role-${m.role}`, m.role + (m.tool_name ? ` (${m.tool_name})` : ""));
  li.append(role, el("div", "msg-text", m.text));
  if (m.role === "system" && config) li.append(el("div", "msg-ko", `번역: ${config.system_prompt_ko}`));
  if (extra) li.append(el("div", "msg-ko", extra));
  $("#history").append(li);
}

// ── 버튼 연결 ───────────────────────────────────────────────
$("#ask").addEventListener("submit", (e) => { e.preventDefault(); startRun(); });
$("#stop").addEventListener("click", stopRun);
$("#reload-tools").addEventListener("click", loadTools);
$("#mode-select").addEventListener("change", updateBadge);
$("#next-step").addEventListener("click", nextStep);
$("#step-toggle").addEventListener("change", (e) => {
  stepMode = e.target.checked;
  if (!stepMode) { while (pending.length) render(pending.shift()); } // 끄면 밀린 이벤트를 한꺼번에 그린다
  updatePending();
});
window.addEventListener("beforeunload", closeSource);

loadConfig().then(loadTools);
