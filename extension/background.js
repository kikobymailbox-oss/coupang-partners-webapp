// 백그라운드 서비스워커: 웹앱(Streamlit) 페이지가 chrome.runtime.sendMessage(EXTENSION_ID, ...)로
// 보낸 요청을 받아, 쿠팡 페이지를 백그라운드(active:false) 탭에서 열어 이미지를 추출하고
// 다운로드를 대행한다. externally_connectable(manifest.json)에 등록된 우리 웹앱 주소에서만 호출 가능하다.
//
// 한때 "0개 후보" 재현 시 active:false가 원인이라 보고 active:true(화면 노출)로 바꿨으나,
// 이전엔 active:false로도 정상 동작했다는 사용자 확인에 따라 active:false로 되돌렸고
// 실제로 다시 정상 동작함을 확인했다(2026-07-02, DECISIONS.md). 그 0개 증상의 정확한 원인은
// 반복 테스트로 인한 일시적 현상이었을 가능성이 있다 — 재발하면 debug 필드(title/totalImgs/cdnHits)로
// 재진단할 것.

const EXTRACT_TIMEOUT_MS = 20000;
const HYDRATION_WAIT_MS = 2500; // SPA 렌더링 대기

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

async function extractFromUrl(url, originatorTabId) {
  if (!/^https:\/\/[^/]*coupang\.com\//.test(url || "")) {
    throw new Error("쿠팡 상품 링크(coupang.com)만 지원합니다.");
  }
  // active:false 유지 — 사용자 확인 결과 이전엔 비활성 탭으로도 정상 동작했으므로,
  // "비활성 탭 자체가 봇차단 원인"이라는 가설은 근거가 부족해 되돌린다(2026-07-02).
  const tab = await chrome.tabs.create({ url, active: false });
  try {
    await waitForTabComplete(tab.id);
    await new Promise((r) => setTimeout(r, HYDRATION_WAIT_MS));
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
    // 잠깐 열렸던 쿠팡 탭을 닫은 뒤, 원래 웹앱 탭으로 포커스를 되돌려준다.
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
