"""
wooatree 보호수 데이터 수집 스크립트
행정안전부(산림청) 전국보호수표준데이터를 localdata.go.kr에서 CSV로 내려받아
data/tree_data.json으로 정규화한다.

원본 데이터 특징:
- CP949(EUC-KR) 인코딩
- 좌표가 이미 WGS84위도/WGS84경도 컬럼으로 제공됨 → 별도 좌표변환 불필요
  (wooavet/wooagym의 Bessel TM 변환과 달리 이 데이터셋은 변환이 필요 없음)
- 보호수해지일자가 채워진 건은 지정 해제된 보호수 → 제외

실행: python scripts/fetch_tree_data.py
"""
import csv
import io
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
import requests

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
RAW_PATH = DATA_DIR / "protected_tree_raw.csv"
OUT_PATH = DATA_DIR / "tree_data.json"

DOWNLOAD_URL = "https://file.localdata.go.kr/file/download/protected_tree_info/info"
DETAIL_URL = "https://www.data.go.kr/data/15013194/standard.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": DETAIL_URL,
}

SIDO_FULL_TO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "인천광역시": "인천",
    "대구광역시": "대구", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "제주도": "제주",
}


def guess_sido_sggu(sido_full: str, sggu: str):
    """시도명/시군구명 컬럼을 직접 사용(주소 문자열 파싱보다 신뢰도 높음).
    "전남광주통합특별시" — 광주+전남 통합 행정구역명. 시군구명이 "구"로 끝나면
    (광주 자치구: 동/서/남/북/광산구) 광주, 그 외(전남 시/군)는 전남으로 재분류."""
    sido_full = (sido_full or "").strip()
    sggu = (sggu or "").strip()
    if sido_full == "전남광주통합특별시":
        short = "광주" if sggu.endswith("구") else "전남"
        return short, sggu
    short = SIDO_FULL_TO_SHORT.get(sido_full, "")
    return short, sggu


DONG_SUFFIXES = ("동", "리", "가", "읍", "면")


def guess_dong(addr: str, sido: str, sggu: str):
    """지번주소에서 시도/시군구 다음 토큰(동/리/읍/면 등)을 이름 힌트로 추출."""
    text = addr or ""
    tokens = text.split()
    # 시도명·시군구명 토큰을 건너뛰고 그 다음 토큰을 찾는다
    idx = 0
    for i, t in enumerate(tokens):
        if sggu and sggu in t:
            idx = i + 1
            break
    if idx < len(tokens):
        cand = tokens[idx]
        # "산123-4" 같은 지번 토큰이 아니라 동/리 이름인지 확인
        stripped = cand.lstrip("산")
        if any(cand.endswith(suf) for suf in DONG_SUFFIXES):
            return cand
    return ""


def download():
    resp = requests.get(DOWNLOAD_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    if len(resp.content) < 100_000:
        raise SystemExit(
            f"다운로드 실패로 추정 — 응답 크기가 너무 작음 ({len(resp.content)} bytes). "
            f"localdata.go.kr 다운로드 URL이 바뀌었을 수 있음 — 브라우저로 "
            f"{DETAIL_URL} 방문 후 다운로드 버튼의 실제 요청을 다시 확인할 것."
        )
    DATA_DIR.mkdir(exist_ok=True)
    RAW_PATH.write_bytes(resp.content)
    print(f"다운로드 완료: {RAW_PATH} ({len(resp.content):,} bytes)")


def parse():
    with open(RAW_PATH, encoding="cp949", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


def main():
    if not RAW_PATH.exists():
        print("원본 CSV 없음 — 다운로드 시도")
        download()

    rows = parse()
    print(f"총 {len(rows):,}건 파싱 완료 (해지분 포함)")
    print(f"컬럼: {list(rows[0].keys()) if rows else '(없음)'}")

    active_rows = [r for r in rows if not (r.get("보호수해지일자") or "").strip()]
    print(f"지정 유지 중 {len(active_rows):,}건 (해지 {len(rows) - len(active_rows):,}건 제외)")

    records = []
    skipped_region = 0
    skipped_basic = 0
    for r in active_rows:
        species = (r.get("나무종류") or "").strip()
        addr = (r.get("소재지도로명주소") or r.get("소재지지번주소") or "").strip()
        if not species or not addr:
            skipped_basic += 1
            continue

        sido, sggu = guess_sido_sggu(r.get("시도명"), r.get("시군구명"))
        if not sido or not sggu:
            skipped_region += 1
            continue

        dong = guess_dong((r.get("소재지지번주소") or "").strip() or addr, sido, sggu)

        records.append({
            "species": species,
            "dong": dong,
            "addr": addr,
            "lat": (r.get("WGS84위도") or "").strip(),
            "lng": (r.get("WGS84경도") or "").strip(),
            "sido_nm": sido,
            "sggu_nm": sggu,
            "typeName": (r.get("보호수유형명") or "").strip(),
            "family": (r.get("과명") or "").strip(),
            "sciName": (r.get("학명") or "").strip(),
            "count": (r.get("그루수") or "").strip(),
            "age": (r.get("나무나이") or "").strip(),
            "height": (r.get("나무높이") or "").strip(),
            "girth": (r.get("가슴높이둘레") or "").strip(),
            "designationNo": (r.get("지정번호") or "").strip(),
            "designatedDate": (r.get("보호수지정일자") or "").strip(),
        })

    print(f"주소/수종 없음 {skipped_basic:,}건 / 지역 매칭 실패 {skipped_region:,}건")
    print(f"최종 저장 {len(records):,}건")

    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("items", [])
        if existing and len(records) < len(existing) * 0.5:
            raise SystemExit(
                f"수집 건수({len(records)}건)가 기존 데이터({len(existing)}건)의 절반 미만입니다. "
                "다운로드 오류로 판단하여 저장을 중단합니다."
            )

    DATA_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"items": records}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장 완료: {OUT_PATH}")


if __name__ == "__main__":
    main()
