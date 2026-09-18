# B站 UP 主动态监控

监控 Bilibili UID `3546611678448071` 的动态，每 30 分钟检查一次；发现新动态后通过 WxPusher 推送到微信。

## 配置

推荐使用 WxPusher 极简推送 SPT：

1. 获取自己的 `SPT_...`。
2. 在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中新建 Repository secret：
   - Name: `WXPUSHER_SPT`
   - Value: 你的 SPT
3. 手动运行一次 GitHub Actions，确认收到通知。

也兼容标准 WxPusher：
- `WXPUSHER_APP_TOKEN`
- `WXPUSHER_UID`

## 工作方式

B站 → RSSHub → GitHub Actions → WxPusher → 微信

GitHub Actions 不需要自己的服务器。
