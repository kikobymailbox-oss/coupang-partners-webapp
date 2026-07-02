// 쿠팡 상품 페이지에서 썸네일 후보 이미지를 수집한다.
// 팝업(popup.js)의 요청(EXTRACT)에 후보 목록을 응답한다.
// 서버를 거치지 않고, 사용자의 실제 브라우저 컨텍스트에서 DOM/상태값을 읽는다.
//
// 원칙: 절대 "0개"를 만들지 않는다. 정크(로고·아이콘·배너)로 의심되면 점수를
// 깎아 뒤로 보낼 뿐 제외하지 않는다 — 하드 필터로 제외하면, 쿠팡 자체가
// "로켓배송/로켓프레시" 등 브랜딩을 상품 이미지 경로에도 흔히 섞어 쓰기 때문에
// 진짜 상품 사진까지 함께 사라지는 위험이 더 크다(대표이미지까지 걸러진 사례로 확인됨).

function normalize(u) {
  if (!u) return "";
  if (u.startsWith("//")) return "https:" + u;
  return u.replace(/\\\//g, "/");
}

// 쿠팡의 "썸네일 리사이징" 경로 패턴. 실제 상품 사진은 대체로 이 경로(크기 폴더)를 거친다.
// 로고·아이콘·배너 같은 사이트 UI 이미지는 이 경로를 안 거치는 경우가 많아 가산점 근거로만 쓴다.
const THUMB_PATH_RE = /\/remote\/\d+x\d+[a-z]*\//;

// 파일명에 이런 단어가 있으면 UI 자산일 가능성이 있어 감점만 한다(제외하지 않음).
// "rocket"/"biz_" 처럼 쿠팡 자체 브랜딩과 겹쳐 진짜 상품 이미지에도 나타날 수 있는 단어는 넣지 않는다.
const ICON_HINT_RE = /(logo|icon|badge|sprite|btn_|app_download|banner)/i;

const MAX_CANDIDATES = 20;
const MIN_DIM = 120; // px, 이보다 작으면 아이콘일 가능성 — 감점만(제외 아님)

// 쿠팡 썸네일 URL의 사이즈 구간(/remote/230x230ex/)을 큰 값으로 바꿔 고해상도로.
function toHiRes(u) {
  return u.replace(/\/remote\/\d+x\d+[a-z]*\//, "/remote/492x492ex/");
}

function collect() {
  const scored = new Map(); // url -> score (중복 제거 + 점수, 병합 시 더 높은 점수 유지)
  let totalImgs = 0;
  let cdnHits = 0;

  const add = (raw, baseScore) => {
    let u = normalize(raw);
    if (!/^https?:/.test(u)) return;
    if (!u.includes("coupangcdn")) return; // 쿠팡 CDN 이미지만(이것만 하드 조건)
    cdnHits++;

    let score = baseScore;
    if (THUMB_PATH_RE.test(u)) score += 20; // 상품 리사이징 경로 가산점
    if (ICON_HINT_RE.test(u)) score -= 40; // UI 자산 의심 감점(제외는 아님)

    u = toHiRes(u);
    scored.set(u, Math.max(scored.get(u) || -Infinity, score));
  };

  // 1) 대표 이미지 메타태그 (쿠팡이 직접 지정 — 가장 신뢰도 높음)
  const og = document.querySelector('meta[property="og:image"]');
  if (og) add(og.content, 100);
  const tw = document.querySelector('meta[name="twitter:image"]');
  if (tw) add(tw.content, 90);

  // 2) 구조화 데이터(ld+json)의 image (역시 쿠팡이 직접 지정)
  document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
    try {
      const j = JSON.parse(s.textContent);
      const imgs = [].concat(j.image || []);
      imgs.forEach((x) => add(typeof x === "string" ? x : x && x.url, 80));
    } catch (e) {}
  });

  // 3) DOM 이미지 (src / data-src / srcset)
  totalImgs = document.querySelectorAll("img").length;
  document.querySelectorAll("img").forEach((img) => {
    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    const small = w && h && (w < MIN_DIM || h < MIN_DIM);
    const base = small ? 20 : 50; // 작아 보여도 제외하지 않고 감점만
    add(img.currentSrc || img.src || img.getAttribute("data-src") || "", base);
    const ss = img.getAttribute("srcset");
    if (ss) ss.split(",").forEach((p) => add(p.trim().split(" ")[0], small ? 22 : 55));
  });

  // 4) 페이지 HTML/상태값(__NEXT_DATA__ 등) 안에 박힌 CDN 이미지 URL
  const html = document.documentElement.innerHTML;
  const re = /https?:\\?\/\\?\/[^"'\\ )]+coupangcdn[^"'\\ )]+\.(?:jpg|jpeg|png|webp)/gi;
  (html.match(re) || []).forEach((u) => add(u, 40));

  const candidates = Array.from(scored.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_CANDIDATES)
    .map(([url, score]) => ({ url, score }));

  // 진단 정보: 후보가 0개일 때 "왜 0개인지"를 화면에 보여주기 위함
  // (예: 봇체크 인터스티셜 페이지라 실제 상품 페이지 내용 자체가 없는 경우를 구분하기 위해)
  const debug = {
    title: document.title || "",
    url: location.href,
    totalImgs: totalImgs,
    cdnHits: cdnHits,
    htmlLen: document.documentElement.innerHTML.length,
  };

  return { candidates: candidates, debug: debug };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "EXTRACT") {
    sendResponse(collect());
  }
  return true;
});
