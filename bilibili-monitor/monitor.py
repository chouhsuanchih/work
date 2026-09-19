import json
import os
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

CONFIG_FILE = Path("bilibili-monitor/config.json")
STATE_FILE = Path("bilibili-monitor/state.json")
FEED_TEMPLATES = [
    "https://rsshub.liumingye.cn/bilibili/user/dynamic/{uid}",
    "https://rsshub.chyi.org/bilibili/user/dynamic/{uid}",
    "https://rsshub.runnable.run/bilibili/user/dynamic/{uid}",
]
SPT = os.environ.get("WXPUSHER_SPT", "").strip()
APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN", "").strip()
WX_UID = os.environ.get("WXPUSHER_UID", "").strip()

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; bilibili-monitor/1.0)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def fetch_feed(user):
    errors = []
    for template in FEED_TEMPLATES:
        url = template.format(uid=user["uid"])
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
    raise RuntimeError(f"UP主 {user['name']} ({user['uid']}) 的所有 RSSHub 备用源均失败：\n" + "\n".join(errors))

def text_of(el, name):
    for child in el.iter():
        if child.tag.split("}")[-1] == name and child.text:
            return child.text.strip()
    return ""

def parse_feed(data):
    root = ET.fromstring(data)
    items = []
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
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
        payload = json.dumps({
            "content": content,
            "summary": "B站 UP主新动态",
            "contentType": 1,
            "spt": SPT,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://wxpusher.zjiecode.com/api/send/message/simple-push",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            if not result.get("success", False):
                raise RuntimeError(f"WxPusher 返回失败: {result}")
            return result
    if APP_TOKEN and WX_UID:
        payload = json.dumps({"appToken": APP_TOKEN, "content": content, "contentType": 1, "uids": [WX_UID]}).encode()
        req = urllib.request.Request("https://wxpusher.zjiecode.com/api/send/message", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    raise RuntimeError("未配置 WXPUSHER_SPT，或 WXPUSHER_APP_TOKEN + WXPUSHER_UID")

def main():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    users = config["users"]
    state = {"seen": {}}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    if isinstance(state.get("seen"), list):
        first_uid = users[0]["uid"]
        state = {"seen": {first_uid: state["seen"]}}

    seen_by_uid = state.setdefault("seen", {})
    had_error = False

    for user in users:
        uid = user["uid"]
        try:
            items = fetch_feed(user)
        except Exception as e:
            had_error = True
            print(f"⚠️ 跳过 UP主 {user['name']} ({uid})，不影响其他 UP 主：{e}")
            continue

        seen = set(seen_by_uid.get(uid, []))
        new_items = [x for x in items if x["id"] not in seen]

        if uid not in seen_by_uid:
            seen_by_uid[uid] = [x["id"] for x in items[:30]]
            print(f"首次监控 {user['name']} ({uid})：建立基线，当前 {len(items)} 条，不推送历史消息")
            continue

        successfully_handled = set()
        for item in reversed(new_items):
            content = f"🔔 B站 UP主有新动态\n\nUP主：{user['name']}\n标题：{item['title']}\n\n{item['link']}"
            print("推送:", user["name"], item["title"])
            try:
                result = send_wxpusher(content)
                print(result)
                successfully_handled.add(item["id"])
            except Exception as e:
                had_error = True
                print(f"⚠️ 推送失败：{user['name']} -> {type(e).__name__}: {e}")

        merged = [x["id"] for x in items if x["id"] in seen or x["id"] in successfully_handled] + list(seen)
        seen_by_uid[uid] = list(dict.fromkeys(merged))[:50]

    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Do not fail the whole workflow just because one UP or one push failed.
    if had_error:
        print("本次检查存在部分错误，但已完成其他可用 UP 主的检查。")

if __name__ == "__main__":
    main()
