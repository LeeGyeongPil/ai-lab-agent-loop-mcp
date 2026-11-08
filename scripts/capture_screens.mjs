// README 장면 캡처 스크립트(개발용). 모의 모드로 결정적인 화면을 찍는다.
//
//   1) 터미널 A:  AGENT_MODE=mock uv run agent-loop --no-browser
//   2) 터미널 B:  npx -y -p playwright@1.60.0 node scripts/capture_screens.mjs
//      (처음이면 브라우저 설치: npx -y playwright@1.60.0 install chromium)
//
// 환경 변수: BASE_URL(기본 http://127.0.0.1:8765), OUT_DIR(기본 docs/images)
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8765";
const OUT_DIR = process.env.OUT_DIR || "docs/images";
const EXAMPLES = [
  "가장 재고가 많은 과일의 가격은 얼마야?",
  "수박 재고 있어?",
  "'에이전트 루프'는 몇 글자야?",
];

// `npx -p playwright` 는 PATH에만 패키지를 올려 두므로, 거기서 playwright 모듈을 찾아 불러온다.
async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    for (const dir of (process.env.PATH || "").split(path.delimiter)) {
      const entry = path.join(dir, "..", "playwright", "index.mjs");
      if (dir.endsWith(path.join("node_modules", ".bin")) && fs.existsSync(entry)) {
        return await import(pathToFileURL(entry).href);
      }
    }
    throw new Error("playwright 모듈을 찾지 못했습니다. `npx -y -p playwright@1.60.0 node scripts/capture_screens.mjs` 로 실행하세요.");
  }
}

async function openPage(browser, { video = false } = {}) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: "light",
    ...(video ? { recordVideo: { dir: OUT_DIR, size: { width: 1440, height: 900 } } } : {}),
  });
  const page = await context.newPage();
  await page.goto(BASE_URL);
  await page.waitForSelector("#server-list .tool >> nth=3"); // 도구 4개가 보일 때까지
  await page.selectOption("#mode-select", "mock"); // 촬영은 항상 모의 모드
  return { context, page };
}

async function runExample(page, index) {
  await page.click(`#examples button >> nth=${index}`);
  await page.waitForSelector('body[data-run-state="done"]', { timeout: 60_000 }); // 완료 표시
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch();
  const shot = (page, name, opts = {}) => page.screenshot({ path: path.join(OUT_DIR, name), ...opts });

  try {
    // 장면 1: 첫 화면 — 연결된 MCP 서버 2개와 도구 4개
    let { context, page } = await openPage(browser);
    await shot(page, "01-first-screen.png");

    // 장면 2: 예시 ① 완료 화면(루프 그림·대화 기록 포함)
    await runExample(page, 0);
    await shot(page, "02-chain-done.png", { fullPage: true });

    // 장면 3: 도구 호출·관찰 카드를 펼쳐 MCP 메시지 보기
    const call = page.locator(".card.call").last();
    const obs = page.locator(".card.observe").last();
    await call.locator("details").evaluate((d) => (d.open = true));
    await obs.locator("details").evaluate((d) => (d.open = true));
    await page.locator(".center").screenshot({ path: path.join(OUT_DIR, "03-mcp-messages.png") });
    await context.close();

    // 장면 4: 예시 ② — 빨간 오류 관찰 카드와 다음 회차 생각
    ({ context, page } = await openPage(browser));
    await runExample(page, 1);
    await shot(page, "04-error-observed.png", { fullPage: true });
    await context.close();

    // 장면 5: 예시 ③ — 내 도구(count_chars) 호출
    ({ context, page } = await openPage(browser));
    await runExample(page, 2);
    await shot(page, "05-my-tool.png", { fullPage: true });
    await context.close();

    // 장면 6: 한 단계씩 보기 — "다음 단계"를 4번 누른 상태
    ({ context, page } = await openPage(browser));
    await page.check("#step-toggle");
    await page.click("#examples button >> nth=0");
    await page.waitForSelector('body[data-stream-state="ended"]'); // 이벤트가 모두 도착(버퍼에 쌓임)할 때까지
    for (let i = 0; i < 5; i++) await page.click("#next-step"); // 준비 → 생각 → 호출 → 관찰 → 다음 생각
    await shot(page, "06-step-mode.png");
    await context.close();

    // 장면 7(동영상): 예시 ① 전체 흐름. webm → GIF 변환은 ffmpeg 등으로 따로 한다.
    ({ context, page } = await openPage(browser, { video: true }));
    await page.waitForTimeout(500);
    await runExample(page, 0);
    await page.waitForTimeout(1500);
    const video = page.video();
    await context.close();
    if (video) fs.renameSync(await video.path(), path.join(OUT_DIR, "07-chain-run.webm"));
  } finally {
    await browser.close();
  }
  console.log(`saved to ${OUT_DIR}: ${EXAMPLES.length} examples captured`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
