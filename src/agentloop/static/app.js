// 에이전트 루프 화면 — 서버가 SSE로 보내는 이벤트(events.py)를 받아 카드로 그린다.
// 빌드 단계 없는 바닐라 JS. 위에서 아래로 읽으면 된다.

const $ = (sel) => document.querySelector(sel);

// ── 화면 문구 표 (영어 / 한국어) ─────────────────────────────
// 화면에 보이는 문구는 전부 여기 있다. 두 언어의 키가 같아야 한다(tests/test_i18n.py 가 검사한다).
// {이름} 은 값이 들어갈 자리, `백틱` 으로 감싼 부분은 <code> 로 보인다.
// 번역하지 않는 것: 이벤트·JSON 키, MCP 도구 이름·스키마, 예시 질문(한국어 데모 데이터), 모델에게 보내는 시스템 프롬프트.
const MESSAGES = {
  en: {
    "title": "Agent loop + MCP",
    "badge_checking": "Checking mode…",
    "run_mode": "Run mode",
    "option_mock": "Mock (scripted LLM)",
    "option_real": "Real (Ollama)",
    "step_toggle": "Step by step",
    "next_step": "Next step",
    "language": "Language",
    "servers_title": "Connected MCP servers",
    "reload": "Reload",
    "reload_title": "Press after editing the code in servers/",
    "servers_note": "This list is each server's `tools/list` response. The model reads these names, descriptions and input schemas to pick a tool.",
    "connecting": "Connecting to servers…",
    "question_placeholder": "Type a question or press an example below",
    "run": "Run",
    "stop": "Stop",
    "timeline_empty": "Run a question and \"thinking → tool call → observation\" cards pile up here in order.",
    "loop_title": "The loop",
    "loop_aria": "A loop through plan, act and observe, with the final answer as the exit",
    "node_plan": "Plan (think)",
    "node_act": "Act (call)",
    "node_observe": "Observe (result)",
    "node_answer": "Final answer",
    "loop_note": "It repeats plan → act → observe until an answer comes out. The current step is highlighted.",
    "history_title": "Conversation history sent to the model",
    "history_note": "At every step the model re-reads this whole history. An agent = a loop that grows the history and calls the model again.",
    "history_empty": "The messages array appears when you run.",
    "footer": "The MCP messages on the cards are the SDK result objects dumped as wire-shaped JSON. The request side is a display reconstruction without `_meta`.",
    "stop.answer": "answered",
    "stop.max_steps": "max steps reached",
    "stop.error": "error",
    "stop.cancelled": "cancelled",
    "my_tools_hint": "This tool is a single function in servers/my_tools_server.py. Edit it to plug in your own tool.",
    "sec": "{s}s",
    "min_sec": "{m}m {s}s",
    "example": "Example {n}: {q}",
    "badge_mock": "Mock mode · scripted LLM + real MCP servers",
    "badge_real": "Real mode · Ollama {model}",
    "server_head": "{name}  ·  tools: {n}",
    "no_args": "no arguments",
    "details_schema": "Show input/output schema (JSON)",
    "details_list": "Show tools/list response",
    "details_request": "Show MCP request (tools/call)",
    "details_response": "Show MCP response (content · structuredContent · isError)",
    "err_not_started": "Could not start the run. Another run is in progress or the server is down.",
    "err_lost": "The connection to the server was lost.",
    "err_title": "Connection error",
    "stopped_title": "Stopped",
    "stopped_body": "The run was stopped. The agent on the server side is cancelled too.",
    "pending": "({n} steps waiting)",
    "prep_title": "Ready",
    "prep_body": "Connected {servers} MCP server(s), received {tools} tool(s) (tools/list)",
    "step_head": "Step {n}",
    "step_sent": "{n} message(s) sent to the model",
    "think_title": "Step {n} · Thinking",
    "waiting": "Waiting for the model… {n}s",
    "no_thinking": "(no thinking)",
    "chars": "{n} chars",
    "call_title": "Step {n} · Tool call",
    "server_chip": "server {name}",
    "none": "none",
    "dup": "duplicate call",
    "observe_title": "Step {n} · Observation",
    "observe_hint": "An error is an observation too. This text goes back to the model as-is and becomes material for the next step's thinking.",
    "answer_title": "Final answer",
    "answer_end": "(final answer — no tool request → the loop ends)",
    "error_title": "Error",
    "summary": "steps {steps} · tool calls {calls} · errors {errors} · total {total} · {reason}",
    "question_line": "Question: {q}  ·  Model: {m}",
    "translation": "Translation: {text}"
  },
  ko: {
    "title": "에이전트 루프 + MCP",
    "badge_checking": "모드 확인 중…",
    "run_mode": "실행 모드",
    "option_mock": "모의 (대본 LLM)",
    "option_real": "실제 (Ollama)",
    "step_toggle": "한 단계씩 보기",
    "next_step": "다음 단계",
    "language": "언어",
    "servers_title": "연결된 MCP 서버",
    "reload": "다시 불러오기",
    "reload_title": "servers/ 코드를 고친 뒤 눌러 보세요",
    "servers_note": "이 목록은 각 서버의 `tools/list` 응답입니다. 모델은 이 이름·설명·입력 스키마를 읽고 도구를 고릅니다.",
    "connecting": "서버에 연결하는 중…",
    "question_placeholder": "질문을 입력하거나 아래 예시를 누르세요",
    "run": "실행",
    "stop": "중지",
    "timeline_empty": "질문을 실행하면 \"생각 → 도구 호출 → 관찰\" 카드가 여기에 차례로 쌓입니다.",
    "loop_title": "루프 그림",
    "loop_aria": "계획, 행동, 관찰을 도는 루프와 출구인 최종 답",
    "node_plan": "계획(생각)",
    "node_act": "행동(호출)",
    "node_observe": "관찰(결과)",
    "node_answer": "최종 답",
    "loop_note": "답이 나올 때까지 계획 → 행동 → 관찰을 반복합니다. 지금 단계가 강조됩니다.",
    "history_title": "모델에게 보낸 대화 기록",
    "history_note": "회차마다 모델은 이 기록 전체를 다시 읽습니다. 에이전트 = 기록을 늘려 가며 모델을 다시 부르는 반복문.",
    "history_empty": "실행하면 messages 배열이 보입니다.",
    "footer": "카드의 MCP 메시지는 SDK 결과 객체를 와이어 모양 JSON으로 덤프한 것입니다. 요청 쪽은 `_meta`를 뺀 표시용 재구성입니다.",
    "stop.answer": "답을 냄",
    "stop.max_steps": "최대 회차 도달",
    "stop.error": "오류",
    "stop.cancelled": "취소됨",
    "my_tools_hint": "이 도구는 servers/my_tools_server.py 의 함수 하나입니다. 고쳐서 내 도구를 붙여 보세요.",
    "sec": "{s}초",
    "min_sec": "{m}분 {s}초",
    "example": "예시 {n}: {q}",
    "badge_mock": "모의 모드 · 대본 LLM + 진짜 MCP 서버",
    "badge_real": "실제 모드 · Ollama {model}",
    "server_head": "{name}  ·  도구 {n}개",
    "no_args": "인자 없음",
    "details_schema": "입력·출력 스키마(JSON) 보기",
    "details_list": "tools/list 응답 보기",
    "details_request": "MCP 요청 보기 (tools/call)",
    "details_response": "MCP 응답 보기 (content · structuredContent · isError)",
    "err_not_started": "실행을 시작하지 못했습니다. 다른 실행이 진행 중이거나 서버가 꺼져 있습니다.",
    "err_lost": "서버와 연결이 끊겼습니다.",
    "err_title": "연결 오류",
    "stopped_title": "중지",
    "stopped_body": "실행을 중지했습니다. 서버 쪽 에이전트도 취소됩니다.",
    "pending": "({n}단계 대기)",
    "prep_title": "준비",
    "prep_body": "MCP 서버 {servers}개 연결, 도구 {tools}개 받음 (tools/list)",
    "step_head": "회차 {n}",
    "step_sent": "모델에게 메시지 {n}개 전송",
    "think_title": "회차 {n} · 생각",
    "waiting": "모델 응답 기다리는 중… {n}초",
    "no_thinking": "(생각 없음)",
    "chars": "{n}자",
    "call_title": "회차 {n} · 도구 호출",
    "server_chip": "서버 {name}",
    "none": "없음",
    "dup": "중복 호출",
    "observe_title": "회차 {n} · 관찰",
    "observe_hint": "오류도 관찰입니다. 이 문구가 그대로 모델에게 돌아가 다음 회차 생각의 재료가 됩니다.",
    "answer_title": "최종 답",
    "answer_end": "(최종 답 — 도구 요청 없음 → 루프 종료)",
    "error_title": "오류",
    "summary": "회차 {steps} · 도구 호출 {calls} · 오류 {errors} · 총 {total} · {reason}",
    "question_line": "질문: {q}  ·  모델: {m}",
    "translation": "번역: {text}"
  },
};

// ── 화면 언어: 저장된 선택 > (처음만) 브라우저 언어 ───────────
const LANG_KEY = "agentloop.lang";
function detectLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved === "en" || saved === "ko") return saved;
  } catch (e) { /* 저장소를 못 쓰면(프라이빗 모드 등) 매번 브라우저 언어로 정한다 */ }
  const nav = (navigator.languages && navigator.languages[0]) || navigator.language || "en";
  return nav.toLowerCase().startsWith("ko") ? "ko" : "en";
}
function saveLang(value) {
  try { localStorage.setItem(LANG_KEY, value); } catch (e) { /* 저장 실패는 무시 */ }
}
let lang = detectLang();
saveLang(lang); // 처음 연 순간 정한 값을 저장해 둔다 (이후엔 사용자가 고른 값이 우선)

// 문구 가져오기: tr("pending", { n: 3 })
function tr(key, params) {
  const text = MESSAGES[lang][key] ?? MESSAGES.en[key] ?? key;
  return params ? text.replace(/\{(\w+)\}/g, (m, name) => (name in params ? params[name] : m)) : text;
}
// `백틱` 으로 감싼 부분만 <code> 로 만든다 (HTML 로 해석하지 않으므로 안전)
function setRich(node, text) {
  node.replaceChildren(...text.split("`").map((part, i) => (i % 2 ? el("code", null, part) : document.createTextNode(part))));
}
// index.html 의 data-i18n* 속성이 달린 요소를 현재 언어로 채운다
function applyStaticText() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((n) => setRich(n, tr(n.dataset.i18n)));
  document.querySelectorAll("[data-i18n-title]").forEach((n) => { n.title = tr(n.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => { n.placeholder = tr(n.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-aria]").forEach((n) => { n.setAttribute("aria-label", tr(n.dataset.i18nAria)); });
}

// 서버가 보내는 이벤트 종류 (src/agentloop/events.py 와 같은 목록)
const EVENT_TYPES = [
  "run_start", "tools_listed", "step_start", "thinking_delta", "thinking_done",
  "tool_call", "tool_result", "answer", "error", "run_end",
];
// "한 단계씩 보기"에서 버튼 한 번에 드러낼 큰 단계 (thinking_delta 같은 조각은 함께 흘려보낸다)
const MAJOR_TYPES = new Set(["tools_listed", "thinking_done", "tool_call", "tool_result", "answer", "error", "run_end"]);

let config = null;        // /api/config 응답
let source = null;        // 지금 열린 EventSource
let stepMode = false;     // 한 단계씩 보기
let pending = [];         // 한 단계씩 보기에서 아직 안 그린 이벤트
let current = {};         // 지금 그리고 있는 카드들 (생각 카드 등)
let waitTimer = null;     // "모델 응답 기다리는 중… n초" 타이머
let lastServers = null;   // 마지막으로 그린 MCP 서버 목록 (언어를 바꾸면 다시 그린다)

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
  if (s < 60) return tr("sec", { s: s.toFixed(1) });
  return tr("min_sec", { m: Math.floor(s / 60), s: Math.round(s % 60) });
}
// 서버에 보내는 /api 주소에 화면 언어를 붙인다 (서버가 만드는 오류·안내 문구가 같은 언어로 온다)
function api(path, extra = "") {
  return `${path}?lang=${lang}${extra}`;
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
  const first = config === null; // 언어를 바꿔 다시 불러올 때는 사용자가 고른 실행 모드를 건드리지 않는다
  config = await (await fetch(api("/api/config"))).json();
  if (first) $("#mode-select").value = config.mode;
  $("#notice").textContent = config.notice;
  updateBadge();
  const box = $("#examples");
  box.replaceChildren();
  config.examples.forEach((q, i) => {
    const b = el("button", "example", tr("example", { n: i + 1, q }));
    b.type = "button";
    b.dataset.question = q;
    b.addEventListener("click", () => { $("#question").value = q; startRun(); });
    box.append(b);
  });
}

function updateBadge() {
  const mode = $("#mode-select").value;
  const badge = $("#mode-badge");
  if (!config) return; // 설정을 받기 전에는 HTML 의 "확인 중" 문구를 그대로 둔다
  badge.className = `badge ${mode}`;
  badge.textContent = mode === "mock" ? tr("badge_mock") : tr("badge_real", { model: config.model });
}

async function loadTools() {
  const list = $("#server-list");
  list.replaceChildren(el("p", "muted", tr("connecting")));
  const res = await fetch(api("/api/tools"));
  const data = await res.json();
  if (!res.ok) {
    list.replaceChildren(el("p", "chip err", data.error));
    return;
  }
  lastServers = data.servers;
  renderServers(list, data.servers);
}

function renderServers(list, servers) {
  list.replaceChildren();
  for (const server of servers) {
    const box = el("div", "server");
    box.dataset.server = server.name;
    box.append(el("div", "server-name", tr("server_head", { name: server.name, n: server.tools.length })));
    if (server.name === "my_tools") box.append(el("p", "server-hint", tr("my_tools_hint")));
    for (const tool of server.tools) {
      const t = el("div", "tool");
      t.append(el("div", "tool-name mono", tool.name), el("p", "tool-desc", tool.description));
      // 입력 스키마의 properties → "item: string — 설명" 목록
      const props = (tool.input_schema && tool.input_schema.properties) || {};
      const ul = el("ul", "tool-params");
      const names = Object.keys(props);
      if (names.length === 0) ul.append(el("li", null, tr("no_args")));
      for (const name of names) {
        const p = props[name];
        ul.append(el("li", null, `${name}: ${p.type || "?"}${p.description ? " — " + p.description : ""}`));
      }
      t.append(ul, details(tr("details_schema"), json({ inputSchema: tool.input_schema, outputSchema: tool.output_schema })));
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
  const url = api("/api/run", `&q=${encodeURIComponent(question)}&mode=${mode}`);
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
      ? tr("err_not_started")
      : tr("err_lost");
    const c = card("error-banner", tr("err_title"));
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
  const c = card("stopped", tr("stopped_title"));
  c.append(el("div", "card-body", tr("stopped_body")));
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
  $("#pending-count").textContent = stepMode && pending.length ? tr("pending", { n: steps }) : "";
  $("#next-step").disabled = !(stepMode && pending.length);
}
function stopLabel(reason) {
  const key = `stop.${reason}`;
  return key in MESSAGES.en ? tr(key) : reason; // 모르는 값은 그대로 보여 준다
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
    $("#timeline").append(el("p", "muted", tr("question_line", { q: ev.question, m: ev.model })));
  },

  tools_listed(ev) {
    const toolCount = ev.servers.reduce((n, s) => n + s.tools.length, 0);
    const c = card("prep", tr("prep_title"), tr("sec", { s: ev.seconds.toFixed(1) }));
    c.append(el("div", "card-body", tr("prep_body", { servers: ev.servers.length, tools: toolCount })));
    c.append(details(tr("details_list"), json(ev.wire)));
    lastServers = ev.servers;
    renderServers($("#server-list"), ev.servers);
  },

  step_start(ev) {
    const head = el("div", "step-head");
    head.append(el("span", null, tr("step_head", { n: ev.step })), el("span", null, tr("step_sent", { n: ev.messages_count })));
    $("#timeline").append(head);
    renderHistory(ev.messages_preview);
    highlight("node-plan");

    // 생각 카드를 미리 만들고, 첫 글자가 올 때까지 기다린 시간을 보여 준다(실제 모드는 모델 적재로 오래 걸릴 수 있다)
    const c = card("thinking", tr("think_title", { n: ev.step }));
    const body = el("div", "card-body waiting", tr("waiting", { n: 0 }));
    c.append(body);
    current = { thinkingCard: c, thinkingBody: body, thinkingText: "", step: ev.step };
    const startedAt = Date.now();
    stopWaitTimer();
    waitTimer = setInterval(() => {
      body.textContent = tr("waiting", { n: Math.round((Date.now() - startedAt) / 1000) });
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
    current.thinkingBody.textContent = ev.text || tr("no_thinking");
    current.thinkingCard.querySelector(".card-time").textContent = `${tr("chars", { n: ev.chars })} · ${fmtSec(ev.seconds)}`;
  },

  tool_call(ev) {
    highlight("node-act");
    const c = card("call", tr("call_title", { n: ev.step }), tr("sec", { s: ev.t.toFixed(1) }));
    c.dataset.callId = ev.call_id;
    const title = c.querySelector(".card-title");
    title.append(el("span", "chip", tr("server_chip", { name: ev.server ?? tr("none") })));
    if (ev.duplicate) title.append(el("span", "chip dup", tr("dup")));
    c.append(el("div", "card-body mono", `${ev.name} ${oneLine(ev.arguments)}`));
    if (ev.server === "my_tools") c.append(el("p", "hint", tr("my_tools_hint")));
    c.append(details(tr("details_request"), json(ev.wire_request)));
  },

  tool_result(ev) {
    highlight("node-observe", ev.is_error);
    const c = card(ev.is_error ? "observe error" : "observe", tr("observe_title", { n: ev.step }), fmtSec(ev.seconds));
    c.dataset.callId = ev.call_id;
    if (ev.is_error) c.querySelector(".card-title").append(el("span", "chip err", "isError: true"));
    c.append(el("div", "card-body mono", ev.observation));
    if (ev.is_error) c.append(el("p", "hint", tr("observe_hint")));
    c.append(details(tr("details_response"), json(ev.wire_response)));
  },

  answer(ev) {
    highlight("node-answer");
    const c = card("answer", tr("answer_title"), tr("sec", { s: ev.t.toFixed(1) }));
    c.append(el("div", "card-body", ev.text));
    appendHistory({ role: "assistant", text: ev.text }, tr("answer_end"));
  },

  error(ev) {
    const c = card("error-banner", tr("error_title"));
    c.append(el("div", "card-body", ev.message));
    if (ev.hint) c.append(el("p", "hint", ev.hint));
  },

  run_end(ev) {
    stopWaitTimer();
    if (ev.stop_reason !== "answer") highlight(null);
    const s = $("#summary");
    s.textContent = tr("summary", { steps: ev.steps, calls: ev.tool_calls, errors: ev.errors, total: fmtSec(ev.seconds), reason: stopLabel(ev.stop_reason) });
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
  // 시스템 프롬프트는 영어 그대로 모델에 가므로, 한국어 화면에서만 번역 줄을 덧붙인다
  if (m.role === "system" && config && lang === "ko") li.append(el("div", "msg-ko", tr("translation", { text: config.system_prompt_ko })));
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

// 언어 선택: 고르면 저장하고 화면 문구를 바로 다시 채운다(이미 그려진 타임라인 카드는 그대로 둔다)
const langSelect = $("#lang-select");
langSelect.value = lang;
langSelect.addEventListener("change", async () => {
  lang = langSelect.value;
  saveLang(lang);
  applyStaticText();
  updatePending();
  if (config) await loadConfig(); // 안내 문구·예시 버튼·배지를 새 언어로
  if (lastServers) renderServers($("#server-list"), lastServers);
});

applyStaticText();
loadConfig().then(loadTools);
