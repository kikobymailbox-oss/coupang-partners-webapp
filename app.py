"""쿠팡 파트너스 팀 내부용 링크 생성기 (Streamlit).

기능:
  1) 쿠팡 링크 -> 파트너스 링크 변환 + 복사, 같은 화면에서 썸네일까지 자동 추출
  2) (매니저 전용) 슬롯/API키 관리 — 팀원에게는 키가 노출되지 않음

접근 구분: 로그인 없음. URL 쿼리파라미터 ?admin=<MANAGER_TOKEN> 이 서버 설정값과 일치할 때만
매니저 화면(API키 관리)이 추가로 보인다. 세션이 아니라 URL에 상태가 있어 새로고침해도 유지된다.
"""
import html
import io
import json
import os
import zipfile
from pathlib import Path

from dotenv import dotenv_values

# 키 로딩 규칙(harness/CLAUDE.md 공통 API 키):
#   프로젝트 .env 우선 → 없으면 공통 harness/.env fallback → 셸 env 는 신뢰하지 않음.
# 빈 값(placeholder)은 무시해 공통값을 덮지 않게 하고, 채워진 값만 os.environ 에 강제 적용한다.
_PROJECT_ENV = Path(__file__).resolve().parent / ".env"
_HARNESS_ENV = Path(__file__).resolve().parents[2] / ".env"  # projects/<app>/ → harness/


def _load_env():
    merged = {}
    if _HARNESS_ENV.exists():  # 공통(fallback)
        merged.update({k: v for k, v in dotenv_values(_HARNESS_ENV).items() if v})
    if _PROJECT_ENV.exists():  # 프로젝트(우선) — 채워진 값만
        merged.update({k: v for k, v in dotenv_values(_PROJECT_ENV).items() if v})
    for k, v in merged.items():
        os.environ[k] = v  # 셸의 낡은 키까지 덮어씀(override)


_load_env()

import streamlit as st
import streamlit.components.v1 as components

import coupang_api
import storage

st.set_page_config(page_title="쿠팡 파트너스 링크 생성기", page_icon="🔗", layout="centered")


def _render_copy_box(text):
    """코드블록처럼 보이는 상자를 클릭하면 바로 클립보드에 복사되는 위젯.

    크롬 확장과 통신하지 않으므로 components.v1.html(srcdoc)을 그대로 써도 무방하다
    (srcdoc의 about:srcdoc 제약은 externally_connectable 매칭에서만 문제가 된다).
    """
    safe_text = json.dumps(text)
    escaped_text = html.escape(text)
    components.html(
        f"""
        <div id="box" style="font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
             font-size:13px; padding:10px 12px; border:1px solid #ddd; border-radius:6px;
             background:#f6f6f6; cursor:pointer; word-break:break-all; user-select:all;">
          {escaped_text}
        </div>
        <div id="msg" style="font-size:12px; color:#2e7d32; margin-top:4px; height:14px;"></div>
        <script>
        (function () {{
          const box = document.getElementById("box");
          const msg = document.getElementById("msg");
          const value = {safe_text};
          box.addEventListener("click", function (e) {{
            e.preventDefault();
            e.stopPropagation();
            navigator.clipboard.writeText(value).then(function () {{
              msg.textContent = "복사되었습니다!";
              setTimeout(function () {{ msg.textContent = ""; }}, 1500);
            }}).catch(function () {{
              msg.textContent = "복사 실패 — 직접 선택해 복사해주세요.";
            }});
          }});
        }})();
        </script>
        """,
        height=70,
    )


# ------------------------------------------------------------------ 기능1+2: 링크 변환 + 썸네일 (한 화면)
def convert_view():
    st.subheader("파트너스 링크 생성 + 썸네일")
    slots = storage.list_slots()
    if not slots:
        st.warning("등록된 슬롯이 없습니다. 매니저에게 슬롯 등록을 요청하세요.")
        return

    # 확장이 설치·정상작동 중이면 가이드를 아예 안 보여준다.
    # 처음 방문(또는 확장 미설치/미응답)이면 눈에 띄게(펼친 채) 보여준다.
    ext_id, ext_url = _extension_config()
    ext_installed = _check_extension_installed(ext_id)
    if not ext_installed:
        _render_install_guide(ext_url, expanded=True)

    # 같은 이름 슬롯이 있어도 섞이지 않도록 id를 라벨에 포함해 고유화
    slot_label = {f"{s['name']} (#{s['id']})": s["id"] for s in slots}
    chosen = st.selectbox("슬롯(계정) 선택", list(slot_label.keys()))
    url = st.text_input(
        "쿠팡 링크",
        placeholder="https://www.coupang.com/vp/products/...",
        key="cp_link_input",
    )

    if st.button("생성하기", type="primary"):
        url = url.strip()
        if not url:
            st.warning("링크를 입력하세요.")
        else:
            secrets = storage.get_slot_secrets(slot_label[chosen])
            if not secrets:
                st.error("슬롯 키를 찾을 수 없습니다.")
            else:
                with st.spinner("파트너스 링크 변환 중..."):
                    ok, result = coupang_api.create_deeplinks(
                        [url], secrets["access_key"], secrets["secret_key"]
                    )
                if not ok:
                    # 실패 시 이전 성공 결과가 남아 오인되지 않도록 비운다
                    st.session_state.pop("convert_result", None)
                    st.error(result)
                else:
                    st.session_state.convert_result = result
                # 링크 변환 성공/실패와 무관하게 썸네일은 항상 시도한다(둘은 독립 기능).
                st.session_state.thumbnail_url = url

    for item in st.session_state.get("convert_result", []):
        short = item.get("shortenUrl") or item.get("landingUrl") or ""
        st.markdown("**변환된 파트너스 링크** (클릭하면 복사됩니다)")
        _render_copy_box(short)

    thumb_url = st.session_state.get("thumbnail_url")
    if thumb_url:
        st.divider()
        _render_thumbnail_widget(thumb_url, ext_id)


# 확장(extension/)의 manifest.json "key" 로부터 고정된 확장 ID. extension/README.md 참고.
_DEFAULT_EXTENSION_ID = "algnnfjoiiepjinfalghfnmmpjedehdg"

# 확장 설치·정상작동 여부를 감지하는 화면에 안 보이는 위젯.
# declare_component(path=...)로 실제 URL에 서빙해야 chrome.runtime 이 주입된다(위 이유와 동일).
# Streamlit.setComponentValue 프로토콜로 True/False 를 파이썬에 돌려준다.
_EXT_CHECK_DIR = Path(__file__).resolve().parent / "component_ext_check"
_EXT_CHECK_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body>
<script>
(function () {
  const EXT_ID = "__EXTENSION_ID__";

  function send(type, extra) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, extra || {}), "*");
  }

  function reportInstalled(installed) {
    send("streamlit:setComponentValue", { value: installed, dataType: "json" });
  }

  function checkExtension() {
    if (!window.chrome || !chrome.runtime || !chrome.runtime.sendMessage) {
      reportInstalled(false);
      return;
    }
    let done = false;
    const timer = setTimeout(function () {
      if (!done) { done = true; reportInstalled(false); }
    }, 1500);
    try {
      chrome.runtime.sendMessage(EXT_ID, { type: "PING" }, function (resp) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        reportInstalled(!chrome.runtime.lastError && !!resp && resp.ok === true);
      });
    } catch (e) {
      if (!done) { done = true; clearTimeout(timer); reportInstalled(false); }
    }
  }

  window.addEventListener("load", function () {
    send("streamlit:componentReady", { apiVersion: 1 });
    send("streamlit:setFrameHeight", { height: 1 });
    checkExtension();
  });
})();
</script>
</body></html>
"""


def _check_extension_installed(ext_id: str) -> bool:
    """확장이 설치되어 PING에 응답하는지 확인한다. 실패/미설치/판단 전이면 False."""
    try:
        _EXT_CHECK_DIR.mkdir(exist_ok=True)
        html_ = _EXT_CHECK_HTML.replace("__EXTENSION_ID__", ext_id)
        (_EXT_CHECK_DIR / "index.html").write_text(html_, encoding="utf-8")
        checker = components.declare_component("coupang_ext_check", path=str(_EXT_CHECK_DIR))
        return bool(checker(key="cp_ext_check", default=False))
    except Exception:
        return False

# 이 위젯은 반드시 st.components.v1.declare_component(path=...)로 "실제 URL"에 서빙해야 한다.
# st.components.v1.html()은 iframe을 srcdoc(문서 URL이 항상 about:srcdoc)으로 렌더링하는데,
# 크롬의 externally_connectable 매칭은 프레임의 실제 URL 기준이라 about:srcdoc은
# 어떤 허용 목록을 넣어도 절대 매칭되지 않아 chrome.runtime 자체가 주입되지 않는다.
# declare_component(path=...)는 Streamlit 자체 서버가 실제 http(s) 경로로 서빙해 이 문제가 없다.
_WIDGET_DIR = Path(__file__).resolve().parent / "component_thumbnail"

# 웹앱 페이지 안에서 크롬 확장과 직접 통신하는 위젯.
# chrome.runtime.sendMessage(EXTENSION_ID, ...) 로 확장에 "URL 추출"/"다운로드"를 요청하며,
# 서버(Streamlit 파이썬)는 이 과정에 관여하지 않는다 — 이미지가 서버를 거치지 않는다.
_THUMBNAIL_WIDGET_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body>
<div id="cp-ext-app" style="font-family:-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif;">
  <div style="display:flex;gap:8px;">
    <input id="cp-url" type="text" placeholder="https://www.coupang.com/vp/products/..."
           style="flex:1;padding:8px;font-size:14px;border:1px solid #ccc;border-radius:6px;" />
    <button id="cp-go" style="padding:8px 16px;font-size:14px;cursor:pointer;border:0;
            border-radius:6px;background:#346aff;color:#fff;">가져오기</button>
  </div>
  <div id="cp-msg" style="margin-top:10px;font-size:13px;color:#555;"></div>
  <div id="cp-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px;"></div>
</div>
<script>
(function () {
  const EXT_ID = "__EXTENSION_ID__";
  const PRODUCT_URL = __PRODUCT_URL_JSON__; // 파이썬에서 json.dumps로 넣은 문자열(따옴표 포함) 또는 null
  const urlInput = document.getElementById("cp-url");
  const btn = document.getElementById("cp-go");
  const msg = document.getElementById("cp-msg");
  const grid = document.getElementById("cp-grid");

  if (PRODUCT_URL) { urlInput.value = PRODUCT_URL; }

  function setMsg(text, tone) {
    msg.textContent = text || "";
    msg.style.color = tone === "error" ? "#c0392b" : tone === "ok" ? "#2e7d32" : "#555";
  }

  function hasExtensionApi() {
    return !!(window.chrome && chrome.runtime && chrome.runtime.sendMessage);
  }

  function download(url, idx) {
    chrome.runtime.sendMessage(
      EXT_ID,
      { type: "DOWNLOAD_IMAGE", url: url, filename: "coupang_thumbnail_" + (idx + 1) + ".jpg" },
      function (resp) {
        if (chrome.runtime.lastError || !resp || !resp.ok) {
          setMsg("다운로드 실패", "error");
        } else {
          setMsg("다운로드를 시작했습니다.", "ok");
        }
      }
    );
  }

  function render(candidates) {
    grid.innerHTML = "";
    candidates.forEach(function (c, i) {
      const card = document.createElement("div");
      card.style.cssText = "border:1px solid #eee;border-radius:8px;overflow:hidden;text-align:center;";
      const img = document.createElement("img");
      img.src = c.url;
      img.referrerPolicy = "no-referrer";
      img.style.cssText = "width:100%;height:110px;object-fit:cover;display:block;background:#f4f4f4;";
      img.onerror = function () { img.style.opacity = "0.25"; };
      const b = document.createElement("button");
      b.textContent = "⬇ 다운로드";
      b.style.cssText = "width:100%;border:0;padding:6px 0;cursor:pointer;background:#f2f4f8;";
      b.onclick = function () { download(c.url, i); };
      card.appendChild(img);
      card.appendChild(b);
      grid.appendChild(card);
    });
  }

  function runExtract() {
    const url = urlInput.value.trim();
    grid.innerHTML = "";
    if (!url) { setMsg("쿠팡 상품 링크를 입력하세요.", "error"); return; }
    if (!hasExtensionApi()) {
      setMsg("크롬 브라우저에서, 확장 프로그램을 설치한 뒤 이용해주세요.", "error");
      return;
    }
    setMsg("이미지를 가져오는 중입니다... (드물게 최대 15초 정도 걸릴 수 있어요)");
    chrome.runtime.sendMessage(EXT_ID, { type: "EXTRACT_URL", url: url }, function (resp) {
      if (chrome.runtime.lastError) {
        setMsg("확장 프로그램을 찾을 수 없습니다. 설치되어 있는지 확인해주세요.", "error");
        return;
      }
      if (!resp || !resp.ok) {
        setMsg((resp && resp.error) || "이미지를 가져오지 못했습니다.", "error");
        return;
      }
      if (!resp.candidates || !resp.candidates.length) {
        var d = resp.debug;
        var detail = d
          ? " (페이지제목: '" + (d.title || "") + "', 전체이미지 " + d.totalImgs + "개, 쿠팡CDN이미지 " + d.cdnHits + "개)"
          : "";
        setMsg("이미지를 찾지 못했습니다." + detail, "error");
        console.log("[쿠팡 썸네일] 진단 정보:", d);
        return;
      }
      setMsg("후보 " + resp.candidates.length + "개를 찾았습니다. 원하는 이미지의 다운로드를 누르세요.", "ok");
      render(resp.candidates);
    });
  }

  btn.addEventListener("click", runExtract);
  // 위쪽 파트너스 링크 입력값이 그대로 넘어온 경우, 클릭 없이 자동으로 한 번 실행한다.
  if (PRODUCT_URL) {
    window.addEventListener("load", runExtract);
  }
})();

// Streamlit 커스텀 컴포넌트 프로토콜(최소): 부모 프레임에 준비완료·높이를 알려준다.
(function () {
  function send(type, extra) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, extra || {}), "*");
  }
  function reportHeight() {
    send("streamlit:setFrameHeight", { height: document.documentElement.scrollHeight });
  }
  window.addEventListener("load", function () {
    send("streamlit:componentReady", { apiVersion: 1 });
    reportHeight();
  });
  new MutationObserver(reportHeight).observe(document.body, { childList: true, subtree: true });
})();
</script>
</body></html>
"""


# 확장 소스 폴더와, 배포용 zip에 담을 파일 목록(문서/스크린샷은 제외해 용량을 줄인다)
_EXTENSION_DIR = Path(__file__).resolve().parent / "extension"
_EXTENSION_ZIP_FILES = ["manifest.json", "background.js", "content.js", "popup.html", "popup.js"]
_EXTENSION_ZIP_NAME = "coupang-thumbnail-extension"


def _build_extension_zip() -> bytes:
    """확장 폴더를 매 요청 시 새로 압축해 반환한다(파일이 최신 상태로 항상 동기화됨).

    압축 해제 시 파일이 흩어지지 않도록 zip 내부에 폴더(_EXTENSION_ZIP_NAME)를 두어
    사용자가 그 폴더를 그대로 "압축해제된 확장 프로그램 로드"에서 선택하면 되게 한다.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in _EXTENSION_ZIP_FILES:
            fpath = _EXTENSION_DIR / fname
            if fpath.exists():
                zf.write(fpath, arcname=f"{_EXTENSION_ZIP_NAME}/{fname}")
    return buf.getvalue()


def _extension_config():
    """Secrets/env 에서 확장 ID·웹스토어 설치 링크를 읽는다(공통 로직)."""
    ext_id = None
    ext_url = None
    try:
        ext_id = st.secrets.get("CHROME_EXTENSION_ID")
        ext_url = st.secrets.get("EXTENSION_INSTALL_URL")
    except Exception:
        pass
    ext_id = ext_id or os.environ.get("CHROME_EXTENSION_ID") or _DEFAULT_EXTENSION_ID
    ext_url = ext_url or os.environ.get("EXTENSION_INSTALL_URL")
    return ext_id, ext_url


def _render_install_guide(ext_url, expanded):
    """카드 4장(다운로드 → 이동 → 로드 → 완료)으로 구성된 설치 안내."""
    with st.expander("(첫 실행시) 크롬 확장 프로그램 설치 안내", expanded=expanded):
        with st.container(border=True):
            st.markdown("**① 파일을 다운로드 받는다**")
            st.download_button(
                "⬇️ 확장 프로그램 다운로드 (zip)",
                data=_build_extension_zip(),
                file_name=f"{_EXTENSION_ZIP_NAME}.zip",
                mime="application/zip",
                type="primary",
                key="ext_download_btn",
            )
            st.caption("다운로드한 zip 파일은 압축을 풀어주세요(더블클릭하면 보통 자동으로 풀립니다).")
            if ext_url:
                st.caption("또는 크롬 웹스토어에서 바로 설치할 수도 있습니다:")
                st.link_button("🧩 웹스토어에서 설치하기", ext_url)

        with st.container(border=True):
            st.markdown("**② 주소창에 아래 주소로 이동한다**")
            st.caption("클릭하면 주소가 복사됩니다 → 브라우저 주소창에 붙여넣기(⌘V 또는 Ctrl+V)")
            _render_copy_box("chrome://extensions/")

        with st.container(border=True):
            st.markdown("**③ 압축해제된 확장 프로그램 로드 → 압축 해제한 폴더를 선택한다**")
            st.image(str(_EXTENSION_DIR / "docs" / "step3_load_button.png"), width=320)

        with st.container(border=True):
            st.markdown("**④ 다음과 같이 보이면 완료**")
            st.image(str(_EXTENSION_DIR / "docs" / "step4_installed.png"), width=320)

        st.caption("설치 후에는 위에서 링크 넣고 [생성하기]만 누르면 썸네일도 자동으로 뜹니다.")


# ------------------------------------------------------------------ 썸네일 위젯 (웹앱 화면 안, 확장과 직접 통신)
def _render_thumbnail_widget(product_url, ext_id):
    st.markdown("**썸네일**")
    st.caption(
        "설치된 크롬 확장이 위 링크로 자동으로 이미지를 가져옵니다. "
        "(브라우저에서 직접 처리 — 서버는 이미지를 보지 않습니다)"
    )

    # 실제 URL로 서빙되는 정적 파일을 매번 최신 EXTENSION_ID/링크로 갱신해 두고,
    # declare_component(path=...)로 그 폴더를 서빙한다(components.v1.html의 srcdoc 문제 회피).
    try:
        _WIDGET_DIR.mkdir(exist_ok=True)
        widget_html = _THUMBNAIL_WIDGET_HTML.replace("__EXTENSION_ID__", ext_id).replace(
            "__PRODUCT_URL_JSON__", json.dumps(product_url)
        )
        (_WIDGET_DIR / "index.html").write_text(widget_html, encoding="utf-8")
        thumbnail_widget = components.declare_component(
            "coupang_thumbnail_widget", path=str(_WIDGET_DIR)
        )
        # 링크가 바뀌면 key도 바뀌어 위젯이 새로 마운트되고, 새 링크로 자동 실행된다.
        thumbnail_widget(key=f"cp_thumbnail_widget_{abs(hash(product_url)) % 100000}")
    except Exception as e:
        st.error(f"썸네일 위젯을 불러오지 못했습니다: {e}")


# ------------------------------------------------------------------ API 키 관리 (매니저)
def api_key_view():
    st.subheader("API 키 관리 (매니저 전용)")
    st.caption("여기서 등록한 키는 서버에만 저장되며 팀원에게는 슬롯 이름만 보입니다.")

    st.markdown("#### 등록된 슬롯(API 키)")
    slots = storage.list_slots_admin()
    if not slots:
        st.info("아직 등록된 API 키가 없습니다.")
    for s in slots:
        c1, c2, c3 = st.columns([5, 1, 1])
        tail = s.get("access_tail")
        ident = f"Access …{tail}" if tail else "키 없음"
        memo = f" · {s['memo']}" if s.get("memo") else ""
        c1.write(f"**{s['name']}**  ·  `{ident}`{memo}")
        edit_key = f"editing_slot_{s['id']}"
        if c2.button("수정", key=f"edit_btn_{s['id']}"):
            st.session_state[edit_key] = not st.session_state.get(edit_key, False)
        if c3.button("삭제", key=f"del_slot_{s['id']}"):
            storage.delete_slot(s["id"])
            st.rerun()

        if st.session_state.get(edit_key):
            with st.form(f"edit_form_{s['id']}"):
                st.caption("Access/Secret Key는 바꿀 때만 입력하세요. 비워두면 기존 키가 유지됩니다.")
                new_name = st.text_input("슬롯 이름", value=s["name"], key=f"edit_name_{s['id']}")
                new_memo = st.text_input("메모", value=s.get("memo") or "", key=f"edit_memo_{s['id']}")
                new_access = st.text_input("새 Access Key (선택)", type="password", key=f"edit_access_{s['id']}")
                new_secret = st.text_input("새 Secret Key (선택)", type="password", key=f"edit_secret_{s['id']}")
                col_save, col_cancel = st.columns(2)
                save = col_save.form_submit_button("저장", type="primary")
                cancel = col_cancel.form_submit_button("취소")
                if save:
                    if new_name:
                        storage.update_slot(
                            s["id"], new_name, new_memo,
                            access_key=new_access or None, secret_key=new_secret or None,
                        )
                        st.session_state[edit_key] = False
                        st.success("수정되었습니다.")
                        st.rerun()
                    else:
                        st.warning("슬롯 이름은 비울 수 없습니다.")
                if cancel:
                    st.session_state[edit_key] = False
                    st.rerun()

    st.markdown("#### 새 API 키 추가")
    with st.form("add_slot", clear_on_submit=True):
        name = st.text_input("슬롯 이름 (예: 메인계정)")
        access = st.text_input("Access Key", type="password")
        secret = st.text_input("Secret Key", type="password")
        memo = st.text_input("메모 (선택)")
        if st.form_submit_button("API 키 추가"):
            if name and access and secret:
                storage.add_slot(name, access, secret, memo)
                st.success("API 키가 추가되었습니다.")
                st.rerun()
            else:
                st.warning("이름/Access/Secret 은 필수입니다.")


def _is_manager() -> bool:
    """URL 쿼리파라미터 ?admin=<토큰> 이 서버의 MANAGER_TOKEN과 일치하는지 확인.

    세션이 아니라 URL에 상태가 있으므로 새로고침해도 매니저 권한이 유지된다.
    """
    manager_token = None
    try:
        manager_token = st.secrets.get("MANAGER_TOKEN")
    except Exception:
        pass
    manager_token = manager_token or os.environ.get("MANAGER_TOKEN")
    if not manager_token:
        return False
    return st.query_params.get("admin") == manager_token


# ------------------------------------------------------------------ 메인
def main():
    is_manager = _is_manager()

    with st.sidebar:
        st.write("🛠️ **매니저 모드**" if is_manager else "👤 **팀원 모드**")
        if not storage.use_supabase():
            st.caption("⚠️ 로컬 모드")

    tab_titles = ["파트너스 링크"]
    if is_manager:
        tab_titles.append("API키 관리")
    tabs = st.tabs(tab_titles)

    with tabs[0]:
        convert_view()
    if is_manager:
        with tabs[1]:
            api_key_view()


if __name__ == "__main__":
    main()
