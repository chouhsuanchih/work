import json
import os
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

UID_BILIBILI = "3546611678448071"
FEED_URLS = [
    f"https://rsshub.liumingye.cn/bilibili/user/dynamic/{UID_BILIBILI}",
    f"https://rsshub.chyi.org/bilibili/user/dynamic/{UID_BILIBILI}",
    f"https://rsshub.runnable.run/bilibili/user/dynamic/{UID_BILIBILI}",
]
STATE_FILE = Path("bilibili-monitor/state.json")
SPT = os.environ.get("WXPUSHER_SPT", "").strip()
APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN", "").strip()
WX_UID = os.environ.get("WXPUSHER_UID", "").strip()

def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; bilibili-monitor/1.0)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def fetch_feed():
    errors = []
    for url in FEED_URLS:
        try:
            data = fetch(url)
            items = parse_feed(data)
            if items:
                print(f"RSS 源可用: {url}，获取 {len(items)} 条动态")
                return items
            errors.append(f"{url}: 返回内容无法解析或没有条目")
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
            print(f"RSS 源失败: {url} -> {e}")
    raise RuntimeError("所有 RSSHub 备用源均失败：\n" + "\n".join(errors))

def text_of(el, name):
    for child in el.iter():
        if child.tag.split("}")[-1] == name and child.text:
            return child.text.strip()
    return ""

def parse_feed(data):
    root = ET.fromstring(data)
    items = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = text_of(el, "title")
        link = ""
        for child in el.iter():
            if child.tag.split("}")[-1] == "link":
                link = (child.attrib.get("href") or child.text or "").strip()
                if link:
                    break
        guid = text_of(el, "guid") or text_of(el, "id") or link or title
        pub = text_of(el, "pubDate") or text_of(el, "published") or text_of(el, "updated")
        if guid:
            items.append({"id": guid, "title": title or "B站动态更新", "link": link, "date": pub})
    return items

def send_wxpusher(content):
    if SPT:
        url = (
            "https://wxpusher.zjiecode.com/api/send/message/"
            + urllib.parse.quote(SPT, safe="")
            + "/"
            + urllib.parse.quote(content, safe="")
        )
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            return json.loads(r.read())
    if APP_TOKEN and WX_UID:
        payload = json.dumps({
            "appToken": APP_TOKEN,
            "content": content,
            "contentType": 1,
            "uids": [WX_UID],
        }).encode()
        req = urllib.request.Request(
            "https://wxpusher.zjiecode.com/api/send/message",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    raise RuntimeError("未配置 WXPUSHER_SPT，或 WXPUSHER_APP_TOKEN + WXPUSHER_UID")

def main():
    items = fetch_feed()
    state = {"seen": []}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    seen = set(state.get("seen", []))
    new_items = [x for x in items if x["id"] not in seen]

    # First run establishes a baseline and does not push historical updates.
    if not seen:
        state["seen"] = [x["id"] for x in items[:30]]
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"首次运行：建立基线，当前 {len(items)} 条，不推送历史消息")
        return

    for item in reversed(new_items):
        content = f"🔔 B站 UP主有新动态\n\n{item['title']}\n\n{item['link']}"
        print("推送:", item["title"])
        print(send_wxpusher(content))

    merged = [x["id"] for x in items] + list(seen)
    state["seen"] = list(dict.fromkeys(merged))[:50]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
