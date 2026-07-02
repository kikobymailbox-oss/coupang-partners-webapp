# CLAUDE.md — coupang-partners-webapp

> 전역·워크스페이스 원칙은 `~/.claude/CLAUDE.md`, `harness/CLAUDE.md`를 따른다. 이 파일은 이 프로젝트 로컬 규칙만 담는다.

## 목적
쿠팡 파트너스 팀 내부용 도구. 하이브리드 구조. **로그인 없음** — URL 쿼리파라미터로 매니저/팀원 구분.
1. 파트너스 링크 변환 — 링크 입력 → [생성하기] → 변환(서버) + 클릭복사
2. 썸네일 — 웹앱은 "상품 페이지 열기" 버튼만 제공, **실제 추출·다운로드는 사용자가 그 페이지에서 확장 아이콘을 직접 클릭**(자동화 아님 — 이유는 아래 불변식 참고)
3. API키 관리 — `?admin=<MANAGER_TOKEN>` 일 때만 보임, 팀원은 키 미노출 (웹앱/서버)

## 구조
- `app.py` Streamlit UI (`_is_manager()`로 URL 쿼리파라미터 판별·`convert_view`(링크변환)·`_render_thumbnail_instructions`(상품페이지 열기 안내)·`_install_guide_dialog`(모달, 사이드바에서 호출)·`api_key_view`)
- `coupang_api.py` 딥링크 HMAC 서명·호출 (서버 전용)
- `storage.py` 저장소 추상화 (Supabase REST / 로컬 JSON 자동 선택) — 슬롯만 다룸, 라이센스 없음
- `schema.sql` Supabase `cp_slots` 테이블 (라이센스 테이블은 2026-07-02 제거)
- `extension/` 썸네일 추출용 크롬 확장. **`popup.js`(확장 아이콘 클릭)가 추출·다운로드 전담**. `background.js`는 웹앱의 설치 확인(PING) 요청에만 응답 — 자동 탭 오픈 로직은 2026-07-02 전면 제거됨(아래 불변식)
- 배경·판단 근거는 `DECISIONS.md`

## 핵심 불변식 (깨지 말 것)
- **Access/Secret 키는 서버(Supabase/서버 프로세스)에만.** `storage.list_slots()`는 절대 키를 포함하지 않는다(팀원 UI용). `storage.list_slots_admin()`도 access_key 끝 3자리(`access_tail`)만 노출하고 전체 키는 안 준다. 키는 `get_slot_secrets()`로 서버에서만 읽어 서명에 쓴다.
- 매니저 전용 화면(`api_key_view`)은 `_is_manager()`가 True일 때만 렌더 — 이건 `st.query_params.get("admin")`이 서버의 `MANAGER_TOKEN`(env/secrets)과 일치할 때만이다. `MANAGER_TOKEN`이 미설정이면 항상 False(매니저 화면 전체 비노출)로 안전하게 fail-closed.
- 로그인/라이센스 시스템을 다시 추가하지 말 것 — 새로고침 시 `st.session_state`가 초기화돼 로그인이 풀리는 문제 때문에 의도적으로 제거함(2026-07-02, `DECISIONS.md`). 상태가 필요하면 세션이 아니라 URL(쿼리파라미터)에 둘 것.
- 진입점(app.py)의 `_load_env()`는 **프로젝트 `.env` 우선 → 공통 `harness/.env` fallback → 셸 env 무시** 순서로 로드한다(harness/CLAUDE.md 공통 API 키 규칙). 빈 값은 무시(공통값을 덮지 않음), 채워진 값만 `os.environ`에 강제 적용(셸의 낡은 키 shadow 방지).
- **썸네일 자동화(프로그램이 `chrome.tabs.create()`로 쿠팡 탭을 여는 방식)를 다시 추가하지 말 것.** 실측으로 확정: 쿠팡 봇 차단은 "프로그램이 여는 탭"만 감지하고 "사람이 직접 열고 클릭"하는 탭은 차단하지 않는다(2026-07-02, `DECISIONS.md`). 여러 차례(재시도, active/inactive 전환, 대기시간 조정) 시도했지만 전부 이 구조적 문제를 못 고쳤다. 썸네일은 반드시 `extension/popup.js`(사용자가 쿠팡 페이지에서 직접 확장 클릭)로만 처리할 것 — 웹앱은 "상품 페이지 열기" 링크만 제공.
- `extension/background.js`는 PING(설치 확인) 핸들러만 가진다 — 여기에 탭 자동화 로직을 다시 추가하지 말 것.
- 확장 설치 확인 위젯(`_check_extension_installed`)은 반드시 `st.components.v1.declare_component(path=...)`로 서빙할 것 — `components.v1.html()`(srcdoc iframe)은 프레임 URL이 항상 `about:srcdoc`이라 `externally_connectable` 매칭이 절대 안 되고 `chrome.runtime`이 주입되지 않는다(2026-07-02 근본원인, `DECISIONS.md` 참고). (`_render_copy_box`처럼 확장과 통신하지 않는 위젯은 `components.v1.html()` 그대로 써도 무방 — about:srcdoc 제약은 확장 메시징에만 해당.)
- `extension/manifest.json`의 `key`(고정 확장 ID `algnnfjoiiepjinfalghfnmmpjedehdg`)와 `externally_connectable.matches`는 임의로 지우지 말 것 — 지우면 웹앱의 설치 확인(PING)이 끊긴다. 배포 도메인이 바뀌면 `matches`에 추가.

## 검증 방법
- 의존성: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- 부팅: `.venv/bin/streamlit run app.py --server.headless true --server.port 8535` → `curl -s localhost:8535/_stcore/health` 가 200
- 로직(로컬 모드, 키 없이): 아래가 모두 통과해야 한다
  - `coupang_api._authorization(...)` 이 `CEA algorithm=HmacSHA256 ... access-key= ... signature=` 형식 반환
  - `storage.list_slots()` 결과 문자열에 access_key/secret_key 값이 **없음**
  - `storage.get_slot_secrets(id)` 는 서버에서 키를 반환
- 실제 링크 변환은 **실제 쿠팡 키**가 있어야 확인 가능(슬롯 등록 후 변환). 키는 채팅에 붙여넣지 말 것.

## 실행 금지
- 실제 키 없이 딥링크 API 성공까지 단정하지 말 것(401/인증은 실제 키로만 확인).
