"""데이터 저장소 추상화.

- Supabase가 설정되면(SUPABASE_URL + SUPABASE_SERVICE_KEY) 원격 사용.
- 없으면 로컬 JSON(local_data.json)으로 동작 → 로컬에서 바로 실행/시연 가능.

핵심: 슬롯의 access_key/secret_key는 서버 측에서만 읽으며, 팀원 UI로
슬롯 이름/메모만 노출한다(list_slots에는 키가 없음).
"""
import json
import os
import threading

import requests

_LOCAL_PATH = os.path.join(os.path.dirname(__file__), "local_data.json")
_lock = threading.Lock()


def _config():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    # Streamlit secrets 지원 (배포 환경)
    try:
        import streamlit as st

        url = url or st.secrets.get("SUPABASE_URL")
        key = key or st.secrets.get("SUPABASE_SERVICE_KEY")
    except Exception:
        pass
    # URL 정규화: 붙여넣을 때 끝에 /rest/v1 나 슬래시가 딸려와도 떼어낸다.
    if url:
        url = url.strip().rstrip("/")
        if url.endswith("/rest/v1"):
            url = url[: -len("/rest/v1")]
    return url, key


def use_supabase() -> bool:
    url, key = _config()
    return bool(url and key)


# ---------------------------------------------------------------- 로컬 JSON

def _local_load():
    if not os.path.exists(_LOCAL_PATH):
        data = {"slots": [], "_seq": 0}
        _local_save(data)
        return data
    with open(_LOCAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _local_save(data):
    with open(_LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- Supabase

def _sb_headers():
    _, key = _config()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _sb(path, method="GET", params=None, json_body=None):
    url, _ = _config()
    headers = _sb_headers()
    if method in ("POST", "PATCH", "DELETE"):
        headers["Prefer"] = "return=representation"
    resp = requests.request(
        method,
        f"{url}/rest/v1/{path}",
        headers=headers,
        params=params,
        json=json_body,
        timeout=15,
    )
    resp.raise_for_status()
    if resp.text:
        return resp.json()
    return None


# ---------------------------------------------------------------- 슬롯

def list_slots():
    """팀원/매니저 공통. 키 값은 절대 포함하지 않는다."""
    if use_supabase():
        return _sb("cp_slots", params={"select": "id,name,memo", "order": "name"}) or []
    data = _local_load()
    return [{"id": s["id"], "name": s["name"], "memo": s.get("memo", "")} for s in data["slots"]]


def list_slots_admin():
    """매니저 화면용: 슬롯 식별을 위해 access_key 끝 3자리만 포함한다.
    전체 키는 반환하지 않는다(끝 3자리는 식별 불가 정보)."""
    if use_supabase():
        rows = _sb("cp_slots", params={"select": "id,name,memo,access_key", "order": "name"}) or []
    else:
        rows = [
            {"id": s["id"], "name": s["name"], "memo": s.get("memo", ""), "access_key": s.get("access_key", "")}
            for s in _local_load()["slots"]
        ]
    out = []
    for r in rows:
        ak = r.get("access_key") or ""
        out.append({
            "id": r["id"], "name": r["name"], "memo": r.get("memo", ""),
            "access_tail": ak[-3:] if ak else "",
        })
    return out


def get_slot_secrets(slot_id):
    """서버 측에서만 호출. access/secret 키를 반환한다."""
    if use_supabase():
        rows = _sb("cp_slots", params={"id": f"eq.{slot_id}", "select": "access_key,secret_key"})
        return rows[0] if rows else None
    data = _local_load()
    for s in data["slots"]:
        if str(s["id"]) == str(slot_id):
            return {"access_key": s["access_key"], "secret_key": s["secret_key"]}
    return None


def add_slot(name, access_key, secret_key, memo=""):
    if use_supabase():
        _sb("cp_slots", "POST", json_body={
            "name": name, "access_key": access_key,
            "secret_key": secret_key, "memo": memo,
        })
    else:
        with _lock:
            data = _local_load()
            data["_seq"] = data.get("_seq", 0) + 1
            data["slots"].append({
                "id": data["_seq"], "name": name,
                "access_key": access_key, "secret_key": secret_key, "memo": memo,
            })
            _local_save(data)


def update_slot(slot_id, name, memo="", access_key=None, secret_key=None):
    """슬롯 정보를 수정한다. access_key/secret_key 는 None 이면 기존 값을 유지한다
    (매니저가 이름/메모만 바꾸고 싶을 때 키를 재입력하지 않아도 되게 하기 위함)."""
    if use_supabase():
        body = {"name": name, "memo": memo}
        if access_key:
            body["access_key"] = access_key
        if secret_key:
            body["secret_key"] = secret_key
        _sb("cp_slots", "PATCH", params={"id": f"eq.{slot_id}"}, json_body=body)
    else:
        with _lock:
            data = _local_load()
            for s in data["slots"]:
                if str(s["id"]) == str(slot_id):
                    s["name"] = name
                    s["memo"] = memo
                    if access_key:
                        s["access_key"] = access_key
                    if secret_key:
                        s["secret_key"] = secret_key
            _local_save(data)


def delete_slot(slot_id):
    if use_supabase():
        _sb("cp_slots", "DELETE", params={"id": f"eq.{slot_id}"})
    else:
        with _lock:
            data = _local_load()
            data["slots"] = [s for s in data["slots"] if str(s["id"]) != str(slot_id)]
            _local_save(data)
