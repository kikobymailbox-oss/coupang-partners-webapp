// 팝업: 활성 쿠팡 탭에서 썸네일 후보를 받아 표시하고, 선택 시 다운로드한다.

const btn = document.getElementById("btn");
const grid = document.getElementById("grid");
const msg = document.getElementById("msg");

function setMsg(text) {
  msg.textContent = text || "";
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function download(url, index) {
  // chrome.downloads 는 CORS 제약 없이 크로스 오리진 다운로드가 가능하다.
  chrome.downloads.download(
    { url, filename: `coupang_thumbnail_${index + 1}.jpg` },
    () => {
      if (chrome.runtime.lastError) setMsg("다운로드 실패: " + chrome.runtime.lastError.message);
      else setMsg("다운로드를 시작했습니다.");
    }
  );
}

function render(candidates) {
  grid.innerHTML = "";
  candidates.forEach((c, i) => {
    const card = document.createElement("div");
    card.className = "card";

    const img = document.createElement("img");
    img.src = c.url;
    img.referrerPolicy = "no-referrer";
    img.onerror = () => { img.style.opacity = "0.3"; };

    const b = document.createElement("button");
    b.textContent = "⬇ 다운로드";
    b.onclick = () => download(c.url, i);

    card.appendChild(img);
    card.appendChild(b);
    grid.appendChild(card);
  });
}

async function extract() {
  setMsg("");
  grid.innerHTML = "";
  btn.disabled = true;
  btn.textContent = "가져오는 중...";
  try {
    const tab = await activeTab();
    if (!tab || !/https:\/\/[^/]*coupang\.com/.test(tab.url || "")) {
      setMsg("쿠팡 상품 페이지에서 실행해주세요.");
      return;
    }
    let resp;
    try {
      resp = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT" });
    } catch (e) {
      // 확장 설치 전에 열린 탭이면 content script 가 없다 → 주입 후 재시도
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      resp = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT" });
    }
    const candidates = (resp && resp.candidates) || [];
    if (!candidates.length) {
      setMsg("이미지를 찾지 못했습니다. 페이지를 새로고침한 뒤 다시 시도하세요.");
      return;
    }
    render(candidates);
  } catch (e) {
    setMsg("오류: " + (e && e.message ? e.message : e));
  } finally {
    btn.disabled = false;
    btn.textContent = "썸네일 가져오기";
  }
}

btn.addEventListener("click", extract);
