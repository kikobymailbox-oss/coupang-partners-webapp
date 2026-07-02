-- 쿠팡 파트너스 웹앱 Supabase 스키마
-- 다른 프로젝트와 충돌하지 않도록 cp_ 접두사 사용.
-- RLS를 켜고 정책을 두지 않으므로 service_role/secret 키(서버 전용)로만 접근 가능.
--
-- 참고: 라이센스(로그인) 시스템은 2026-07-02부로 제거되었다(DECISIONS.md 참고).
-- 매니저 구분은 URL 쿼리파라미터 ?admin=<MANAGER_TOKEN> 로 대체되어 별도 테이블이 필요 없다.
-- 예전에 cp_licenses 테이블을 이미 만들어 사용 중이었다면, 앱은 더 이상 이 테이블을 읽지 않으니
-- 그대로 두어도 무해하다(원하면 직접 DROP TABLE cp_licenses; 로 정리해도 됨 — 이 스크립트는 건드리지 않는다).

create table if not exists cp_slots (
  id         bigint generated always as identity primary key,
  name       text not null,
  access_key text not null,
  secret_key text not null,
  memo       text,
  created_at timestamptz default now()
);

alter table cp_slots enable row level security;
