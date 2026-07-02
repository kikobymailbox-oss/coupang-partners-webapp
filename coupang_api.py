"""쿠팡 파트너스 딥링크 API 호출 (HMAC 서명은 서버에서만 수행).

팀원 브라우저로는 access_key/secret_key가 절대 전달되지 않는다.
서명·호출 모두 이 서버 측 모듈에서 처리한다.
"""
import hashlib
import hmac
from time import gmtime, strftime

import requests

DOMAIN = "https://api-gateway.coupang.com"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"


def _authorization(method: str, path: str, secret_key: str, access_key: str) -> str:
    """쿠팡 파트너스 규격의 HMAC-SHA256 Authorization 헤더를 만든다."""
    signed_date = strftime("%y%m%dT%H%M%SZ", gmtime())
    message = signed_date + method + path
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        "CEA algorithm=HmacSHA256, "
        f"access-key={access_key}, "
        f"signed-date={signed_date}, "
        f"signature={signature}"
    )


def create_deeplinks(urls, access_key: str, secret_key: str, timeout: int = 15):
    """쿠팡 URL 리스트를 파트너스 딥링크로 변환한다.

    반환: (ok, result)
      ok=True  -> result = [{"originalUrl","shortenUrl","landingUrl"}, ...]
      ok=False -> result = 사람이 읽을 오류 메시지(str)
    """
    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        return False, "변환할 링크가 없습니다."

    authorization = _authorization("POST", DEEPLINK_PATH, secret_key, access_key)
    try:
        resp = requests.post(
            DOMAIN + DEEPLINK_PATH,
            headers={
                "Authorization": authorization,
                "Content-Type": "application/json;charset=UTF-8",
            },
            json={"coupangUrls": urls},
            timeout=timeout,
        )
    except requests.RequestException as e:
        return False, f"쿠팡 서버 연결 실패: {e}"

    if resp.status_code == 401:
        return False, "인증 실패(401): Access/Secret 키가 올바른지, 파트너스 승인 상태인지 확인하세요."
    if resp.status_code != 200:
        return False, f"쿠팡 API 오류 ({resp.status_code}): {resp.text[:300]}"

    try:
        body = resp.json()
    except ValueError:
        return False, f"응답 해석 실패: {resp.text[:300]}"

    # 쿠팡은 성공 시 rCode='0'
    r_code = str(body.get("rCode", ""))
    if r_code not in ("0", ""):
        return False, f"쿠팡 API 실패: {body.get('rMessage') or body}"

    data = body.get("data") or []
    if not data:
        return False, "변환 결과가 비어 있습니다. 링크가 쿠팡 상품/검색 URL이 맞는지 확인하세요."
    return True, data
