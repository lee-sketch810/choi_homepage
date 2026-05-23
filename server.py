#!/usr/bin/env python3
"""
최경선 작가 홈페이지 관리 서버
사용법: python server.py
브라우저에서 http://localhost:8080 으로 접속
관리자 페이지: http://localhost:8080/admin.html
"""
import json, os, re, base64
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

ADMIN_PASSWORD = "1123"
PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
IMAGES_DIR = os.path.join(BASE_DIR, "images")

os.makedirs(IMAGES_DIR, exist_ok=True)

# ── 섹션 추출/교체 유틸 ──────────────────────────────────────────

def read_html():
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return f.read()

def write_html(html):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html)

def extract_hero_quote(html):
    m = re.search(r'<p class="hero-quote">(.*?)</p>', html, re.DOTALL)
    return m.group(1).strip() if m else ""

def extract_about_statements(html):
    return re.findall(r'<p class="about-statement">(.*?)</p>', html, re.DOTALL)

def extract_statement_quote(html):
    m = re.search(r'<blockquote>(.*?)</blockquote>', html, re.DOTALL)
    return m.group(1).strip() if m else ""

def extract_exhibitions(html):
    groups = re.findall(
        r'<div class="exh-year-group">(.*?)</div>\s*\n\s*</div>',
        html, re.DOTALL
    )
    result = []
    for g in groups:
        year_m = re.search(r'<div class="exh-year">(.*?)</div>', g, re.DOTALL)
        year = year_m.group(1).strip() if year_m else ""
        items = re.findall(
            r'<div class="exh-name">(.*?)</div>\s*<div class="exh-venue">(.*?)</div>',
            g, re.DOTALL
        )
        result.append({
            "year": re.sub(r'<[^>]+>', '', year).strip(),
            "items": [
                {"name": re.sub(r'<[^>]+>', ' ', n).strip(),
                 "venue": re.sub(r'<[^>]+>', '', v).strip()}
                for n, v in items
            ]
        })
    return result

def get_content():
    html = read_html()
    return {
        "hero_quote": extract_hero_quote(html),
        "about_statements": extract_about_statements(html),
        "statement_quote": extract_statement_quote(html),
        "exhibitions": extract_exhibitions(html),
    }

def update_hero_quote(html, new_quote):
    return re.sub(
        r'(<p class="hero-quote">)(.*?)(</p>)',
        lambda m: m.group(1) + new_quote + m.group(3),
        html, flags=re.DOTALL
    )

def update_statement_quote(html, new_quote):
    return re.sub(
        r'(<blockquote>)(.*?)(</blockquote>)',
        lambda m: m.group(1) + new_quote + m.group(3),
        html, flags=re.DOTALL
    )

def update_about_statements(html, paragraphs):
    # 기존 about-statement 블록 전체를 교체
    existing = re.findall(r'<p class="about-statement">.*?</p>', html, re.DOTALL)
    if not existing:
        return html
    new_blocks = "".join(
        f'\n    <p class="about-statement">{p}</p>' for p in paragraphs if p.strip()
    )
    # 첫 번째는 교체, 나머지는 삭제
    result = html
    for i, block in enumerate(existing):
        if i == 0:
            result = result.replace(block, new_blocks, 1)
        else:
            result = result.replace(block, "", 1)
    return result

def rebuild_exhibitions_html(exh_list):
    blocks = []
    for exh in exh_list:
        year = exh.get("year", "")
        items_html = ""
        for item in exh.get("items", []):
            name = item.get("name", "")
            venue = item.get("venue", "")
            date = item.get("date", "")
            date_span = f'<br><span style="font-size:.82rem;color:var(--light);">{date}</span>' if date else ""
            items_html += f"""      <div class="exh-item">
        <div class="exh-name">
          <strong>{name}</strong>{date_span}
        </div>
        <div class="exh-venue">{venue}</div>
      </div>\n"""
        blocks.append(
            f'    <div class="exh-year-group">\n'
            f'      <div class="exh-year">{year}</div>\n'
            f'{items_html}'
            f'    </div>\n'
        )
    return "\n".join(blocks)

def update_exhibitions(html, exh_list):
    new_exh_html = rebuild_exhibitions_html(exh_list)
    return re.sub(
        r'(<!-- 2025 -->.*?)(</div>\s*\n</section>)',
        lambda m: new_exh_html + "\n\n  </div>\n</section>",
        html, flags=re.DOTALL
    )

# ── HTTP 핸들러 ─────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # 로그 조용히

    def check_password(self):
        pwd = self.headers.get("X-Admin-Password", "")
        return pwd == ADMIN_PASSWORD

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Password")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/content":
            if not self.check_password():
                return self.send_json(403, {"error": "비밀번호 오류"})
            return self.send_json(200, get_content())
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/verify":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length else {}
            if data.get("password") == ADMIN_PASSWORD:
                return self.send_json(200, {"ok": True})
            return self.send_json(403, {"ok": False})

        if not self.check_password():
            return self.send_json(403, {"error": "비밀번호 오류"})

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if parsed.path == "/api/save":
            try:
                data = json.loads(body)
                html = read_html()
                if "hero_quote" in data:
                    html = update_hero_quote(html, data["hero_quote"])
                if "about_statements" in data:
                    html = update_about_statements(html, data["about_statements"])
                if "statement_quote" in data:
                    html = update_statement_quote(html, data["statement_quote"])
                if "exhibitions" in data:
                    html = update_exhibitions(html, data["exhibitions"])
                write_html(html)
                return self.send_json(200, {"ok": True, "message": "저장 완료"})
            except Exception as e:
                return self.send_json(500, {"error": str(e)})

        if parsed.path == "/api/upload-image":
            try:
                data = json.loads(body)
                filename = os.path.basename(data["filename"])
                img_data = data["data"]
                if img_data.startswith("data:"):
                    img_data = img_data.split(",", 1)[1]
                raw = base64.b64decode(img_data)
                filepath = os.path.join(IMAGES_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(raw)
                return self.send_json(200, {"ok": True, "path": f"images/{filename}"})
            except Exception as e:
                return self.send_json(500, {"error": str(e)})

        self.send_json(404, {"error": "Not found"})


if __name__ == "__main__":
    print(f"✦ 최경선 작가 홈페이지 서버 시작")
    print(f"  홈페이지: http://localhost:{PORT}")
    print(f"  관리자:   http://localhost:{PORT}/admin.html")
    print(f"  종료:     Ctrl+C\n")
    HTTPServer(("", PORT), Handler).serve_forever()
