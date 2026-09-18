import json
import os
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

FEED_URL = "https://rsshub.app/bilibili/user/dynamic/3546611678448071"
STATE_FILE = Path("bilibili-monitor/state.json")
SPT = os.environ.get("WXPUSHER_SPT", "").strip()
APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN", "").strip()
UID = os.environ.get("WXPUSHER_UID", "").strip()

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 bilibili-monitor"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def text_of(el, name):
    x = el.find(name)
    if x is not None and x.text:
        return x.text.strip()
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
        for child in el:
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
        url = "https://wxpusher.zjiecode.com/api/send/message/" + urllib.parse.quote(SPT, safe="") + "/" + urllib.parse.quote(content, safe="")
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            return json.loads(r.read())
    if APP_TOKEN and UID:
        payload = json.dumps({
            "appToken": APP_TOKEN,
            "content": content,
            "contentType": 1,
            "uids": [UID]
        }).encode()
        req = urllib.request.Request(
            "https://wxpusher.zjiecode.com/api/send/message",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    raise RuntimeError("未配置 WXPUSHER_SPT，或 WXPUSHER_APP_TOKEN + WXPUSHER_UID")

def main():
    items = parse_feed(fetch(FEED_URL))
    if not items:
        raise RuntimeError("RSSHub 没有返回可解析的动态")
    state = {"seen": []}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    seen = set(state.get("seen", []))
    new_items = [x for x in items if x["id"] not in seen]

    # First run establishes a baseline and avoids把历史动态一次性推送。
    if not seen:
        state["seen"] = [x["id"] for x in items[:30]]
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"首次运行：建立基线，当前 {len(items)} 条，不推送历史消息")
        return

    for item in reversed(new_items):
        content = f"🔔 B站 UP主有新动态\n\n{item['title']}\n\n{item['link']}"
        print("推送:", item["title"])
        print(send_wxpusher(content))

    merged = [x["id"] for x in items] + list(seen)
    state["seen"] = list(dict.fromkeys(merged))[:50]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
