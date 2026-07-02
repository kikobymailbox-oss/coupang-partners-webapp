// 백그라운드 서비스워커: 웹앱(Streamlit) 페이지가 chrome.runtime.sendMessage(EXTENSION_ID, ...)로
// 보낸 요청을 받아, 쿠팡 페이지를 백그라운드(active:false) 탭에서 열어 이미지를 추출하고
// 다운로드를 대행한다. externally_connectable(manifest.json)에 등록된 우리 웹앱 주소에서만 호출 가능하다.
//
// 한때 "0개 후보" 재현 시 active:false가 원인이라 보고 active:true(화면 노출)로 바꿨으나,
// 이전엔 active:false로도 정상 동작했다는 사용자 확인에 따라 active:false로 되돌렸다. 이후에도
// 같은 증상(제목 빈값 + 이미지 1개 = 쿠팡 봇체크 인터스티셜)이 간헐적으로 재현되어, 근본 차단은
// 없앨 수 없다고 보고 대신 자동 재시도를 넣었다(2026-07-02, DECISIONS.md).

const EXTRACT_TIMEOUT_MS = 20000;
const HYDRATION_WAIT_MS = 2500; // 1차 시도 대기
const RETRY_HYDRATION_WAIT_MS = 4000; // 재시도 대기(봇체크가 풀릴 시간을 더 준다)
const MAX_ATTEMPTS = 2;

// 후보가 없고 페이지에 이미지가 거의 없으면(제목도 비어있으면 더 확실) 쿠팡 봇체크
// 인터스티셜 페이지를 받은 것으로 간주한다 — 실제 상품 페이지라면 이미지가 훨씬 많다.
function looksLikeInterstitial(candidates, debug) {
  if (candidates.length > 0) return false;
  if (!debug) return false;
  return debug.totalImgs <= 2;
}

function waitForTabComplete(tabId) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("페이지 로딩 시간 초과"));
    }, EXTRACT_TIMEOUT_MS);

    function listener(updatedTabId, info) {
      if (updatedTabId === tabId && info.status === "complete") {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function attemptExtract(url, hydrationWaitMs) {
  // active:false 유지 — 사용자 확인 결과 이전엔 비활성 탭으로도 정상 동작했으므로,
  // "비활성 탭 자체가 봇차단 원인"이라는 가설은 근거가 부족해 되돌렸다(2026-07-02).
  const tab = await chrome.tabs.create({ url, active: false });
  try {
    await waitForTabComplete(tab.id);
    await new Promise((r) => setTimeout(r, hydrationWaitMs));
    let resp;
    try {
      resp = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT" });
    } catch (e) {
      // content script 자동 주입 전에 탭이 준비된 경우 대비 재주입
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      resp = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT" });
    }
    return { candidates: (resp && resp.candidates) || [], debug: (resp && resp.debug) || null };
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

async function extractFromUrl(url, originatorTabId) {
  if (!/^https:\/\/[^/]*coupang\.com\//.test(url || "")) {
    throw new Error("쿠팡 상품 링크(coupang.com)만 지원합니다.");
  }
  try {
    let result = await attemptExtract(url, HYDRATION_WAIT_MS);
    let attempt = 1;
    // 봇체크 인터스티셜로 의심되면, 대기시간을 늘려 새 탭으로 한 번 더 시도한다.
    while (attempt < MAX_ATTEMPTS && looksLikeInterstitial(result.candidates, result.debug)) {
      attempt++;
      result = await attemptExtract(url, RETRY_HYDRATION_WAIT_MS);
    }
    return result;
  } finally {
    // 잠깐 열렸던 쿠팡 탭(들)을 닫은 뒤, 원래 웹앱 탭으로 포커스를 되돌려준다.
    if (originatorTabId) {
      chrome.tabs.update(originatorTabId, { active: true }).catch(() => {});
    }
  }
}

chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;

  if (msg.type === "PING") {
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "EXTRACT_URL") {
    const originatorTabId = sender && sender.tab && sender.tab.id;
    extractFromUrl(msg.url, originatorTabId)
      .then(({ candidates, debug }) => sendResponse({ ok: true, candidates, debug }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true; // 비동기 응답 예약
  }

  if (msg.type === "DOWNLOAD_IMAGE") {
    chrome.downloads.download(
      { url: msg.url, filename: msg.filename || "coupang_thumbnail.jpg" },
      (id) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ ok: true, downloadId: id });
        }
      }
    );
    return true;
  }

  return false;
});
