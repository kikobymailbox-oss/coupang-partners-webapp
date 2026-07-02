# 쿠팡 파트너스 링크 생성기 (팀 내부용)

Streamlit + Supabase 웹앱과, 썸네일용 크롬 확장으로 구성된 **하이브리드** 팀 도구.

| 기능 | 어디서 | 이유 |
|---|---|---|
| **1. 파트너스 링크 변환** | 웹앱(서버) | HMAC 서명엔 Secret Key가 필요해 서버에만 보관. 웹앱은 이 기능만 한다. |
| **2. 슬롯·API키 관리 (매니저 전용)** | 웹앱(서버) | 여러 키를 슬롯으로 관리, 팀원에겐 이름만 노출 |
| **썸네일** | 크롬 확장(브라우저, 사람이 직접 클릭) — 웹앱엔 없음 | 링크를 만들려면 쿠팡 상품 페이지를 이미 열어봤을 것이므로, 그 페이지에서 확장 아이콘을 직접 클릭하면 됨. 프로그램이 대신 탭을 열어주는 자동화는 쿠팡 봇 차단에 걸려 폐기(실측 확인) |

> **왜 이 구조인가:** 쿠팡은 서버에서의 페이지 접근을 강력히 차단(403)한다. 일반 요청·Jina·Apify 모두 실측에서 막혔다. 웹앱이 프로그램으로 몰래 여는 탭도 결국 같은 차단에 걸리는 것으로 확인됐다(간헐적 재현 후 근본원인 확정). 오직 **사람이 직접 열고 클릭하는 방식만** 안정적이라, 썸네일은 확장의 팝업(직접 클릭)으로 처리하고 웹앱에서는 아예 뺐다. 자세한 근거는 `DECISIONS.md` 참고.

키(Access/Secret)는 **서버에만 저장**되고 HMAC 서명·API 호출도 서버에서 처리하므로, 팀원 브라우저로는 키가 전달되지 않는다.

**로그인 없음.** 대신 URL 뒤에 `?admin=<매니저 비밀코드>` 를 붙인 사람만 API키 관리 화면을 본다.
세션이 아니라 URL 자체에 상태가 있어 새로고침해도 매니저 권한이 풀리지 않는다.

---

## 1. 로컬에서 바로 실행 (Supabase 없이 체험)

```bash
cd coupang-partners-webapp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

- `.env.example` 을 `.env` 로 복사하고 `MANAGER_TOKEN` 에 아무 문자열이나 채우세요
- 브라우저에서 `http://localhost:8501/?admin=방금넣은값` 으로 접속하면 매니저 화면(API키 관리) 이 보임
- API키 관리 탭에서 실제 쿠팡 Access/Secret 키로 슬롯을 추가하면 링크 변환이 실제로 동작
- 이 모드는 데이터를 `local_data.json` 파일에 저장(내 PC에서만)

> 실제 키는 채팅이나 코드에 넣지 말고 이 화면에서 직접 입력하세요.

---

## 2. Supabase 연결 (팀 공유용)

1. [supabase.com](https://supabase.com) 에서 프로젝트 생성
2. SQL Editor 에 `schema.sql` 내용을 붙여넣고 실행 (`cp_slots` 테이블 생성)
3. Project Settings → API 에서 **Project URL** 과 **Secret key**(⚠️ 서버 전용, 공개 금지) 확인
4. 로컬은 `.env.example` → `.env` 복사 후 값 입력(`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `MANAGER_TOKEN`) / 배포는 아래 3번

---

## 3. 클라우드 배포 (Streamlit Community Cloud, 무료)

1. 이 폴더를 GitHub 저장소에 올림 (`.env`, `secrets.toml`, `local_data.json` 은 `.gitignore` 로 제외)
2. [share.streamlit.io](https://share.streamlit.io) → New app → 저장소/`app.py` 선택
3. Settings → **Secrets** 에 입력 (`.streamlit/secrets.toml.example` 형식):
   ```toml
   MANAGER_TOKEN = "무작위-문자열"
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_SERVICE_KEY = "eyJ...service_role..."
   EXTENSION_INSTALL_URL = "https://..."   # 썸네일 확장 설치 링크(선택)
   ```
4. 배포된 URL은 팀원 전체에게 그대로 전달, **매니저에게만** `주소?admin=MANAGER_TOKEN` 형태로 전달

---

## 4. 썸네일 — 크롬 확장(사람이 직접 클릭, 웹앱에는 없음)

쿠팡이 서버 접근을 차단하므로, 이미지 추출은 **크롬 확장이 브라우저에서** 수행한다.
**핵심 제약**: 프로그램이 자동으로 여는 탭은 쿠팡 봇 차단에 걸리고, 사람이 직접 연 탭에서
확장을 클릭하는 것만 항상 안정적으로 동작함이 실측으로 확인됐다(2026-07-02, `DECISIONS.md`).
게다가 파트너스 링크를 만들려면 사용자가 어차피 쿠팡 상품 페이지를 이미 열어봤으므로,
웹앱이 "상품 페이지 열기" 버튼을 다시 제공하는 것도 불필요해 아예 뺐다. 사용법:

1. (평소처럼) 쿠팡 상품 페이지에서 링크를 복사해 웹앱에 붙여넣고 파트너스 링크를 만든다.
2. 썸네일이 필요하면, **그 원본 쿠팡 탭으로 돌아가** 툴바의 확장 아이콘 클릭 → 썸네일 가져오기 → 다운로드.

- 팀원은 **확장을 최초 1회만 설치**하면 된다 (`extension/README.md`, 웹앱 사이드바 → 🧩 확장 설치 안내)
- 웹앱은 확장에게 "설치돼 있는지"만 확인(PING)해서 설치 안내를 자동으로 숨기거나 보여준다
- 확장 ID는 `manifest.json`의 `key`로 고정되어 있어(`algnnfjoiiepjinfalghfnmmpjedehdg`) 재설치해도 항상 같은 ID

---

## 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit UI (URL 쿼리파라미터로 매니저 판별·링크변환 전용·API키관리·확장 설치 안내 모달) |
| `coupang_api.py` | 딥링크 API HMAC 서명·호출 (서버 전용) |
| `storage.py` | 저장소 (Supabase / 로컬 JSON 자동 선택) |
| `schema.sql` | Supabase 테이블 정의 |
| `extension/` | 썸네일 추출용 크롬 확장. 실제 추출은 `popup.js`(직접 클릭)가 전담, `background.js`는 설치 확인(PING)만 |
