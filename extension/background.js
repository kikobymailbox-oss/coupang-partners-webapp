// 백그라운드 서비스워커: 웹앱(Streamlit) 페이지가 chrome.runtime.sendMessage(EXTENSION_ID, ...)로
// 보낸 PING에 응답해 "확장이 설치되어 있는지"만 알려준다. 이 응답으로 웹앱은 설치 안내를
// 자동으로 숨기거나 보여준다. externally_connectable(manifest.json)에 등록된 우리 웹앱
// 주소에서만 호출 가능하다.
//
// 예전에는 이 파일이 chrome.tabs.create()로 쿠팡 페이지를 프로그램이 직접 열어 이미지를
// 추출하는 자동화도 담당했으나, 실측 결과 "프로그램이 여는 탭"만 쿠팡 봇 차단에 걸리고
// "사람이 직접 열고 확장 아이콘을 클릭"하는 방식(popup.js)은 항상 정상 동작함이 확인되어
// 그 자동화 코드는 전부 제거했다(2026-07-02, DECISIONS.md). 썸네일 추출·다운로드는 이제
// popup.js가 활성 탭에서 전담한다.

chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== "PING") return false;
  sendResponse({ ok: true });
  return false;
});
