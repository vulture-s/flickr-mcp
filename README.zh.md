# Flickr MCP

> [English](README.md) ｜ 繁體中文

讓 Claude 直接操作你的 Flickr——瀏覽 photostream、抓可嵌入的直連圖片網址、上傳、管理相簿。用 [Model Context Protocol](https://modelcontextprotocol.io) 包 Flickr 官方 API（OAuth 1.0a 簽章，讀+寫）。

狀態：🟢 **10 工具全 live-verified**（6 讀 + 4 寫，真實約 1500 張帳號實測）。首次上傳實測抓到 `upload_photo` 兩個真 bug——OAuth multipart 簽章失敗（401）＋中文標題簽章 ascii crash——皆已修（手簽 HMAC-SHA1、UTF-8 safe）。

## 能做什麼（工具清單）

**讀**
- `whoami` — 驗證授權是否成功（回傳登入的 user id / 帳號）
- `list_albums` — 列你的相簿
- `list_album_photos` — 列相簿內照片（每張附 1024px 直連網址）
- `search_photos` — 搜尋（預設只搜你自己的照片）
- `get_photo_info` — 單張完整 metadata（標題/描述/標籤/拍攝時間/公開狀態/頁面網址）
- `get_photo_sizes` — 單張所有尺寸的直連來源網址（**嵌入用最可靠的來源**）

**寫**
- `upload_photo` — 上傳本機圖檔（**預設 private**，不會不小心公開）
- `create_album` — 建相簿（Flickr 規定要指定一張現有照片當封面）
- `add_photo_to_album` — 把照片加進相簿
- `set_photo_meta` — 改標題/描述

## 安裝

```bash
git clone https://github.com/vulture-s/flickr-mcp.git
cd flickr-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 拿憑證（四個字串）

1. 到 <https://www.flickr.com/services/apps/create/> 申請一個 app（選 non-commercial 即可），拿 **Key** 和 **Secret**。
2. 授權換 token：
   ```bash
   export FLICKR_API_KEY=你的key
   export FLICKR_API_SECRET=你的secret
   python authorize.py
   ```
   照提示開網址 → 按同意 → 把 Flickr 顯示的 9 位驗證碼貼回終端機。腳本會印出四個 `FLICKR_*` 變數。

> 要求 `write` 權限（涵蓋讀 + 上傳 + 管相簿）。腳本不會自動寫檔，token 你自己貼進設定。

### 掛進 Claude Code

`claude mcp add`，或在 MCP 設定 JSON 加：

```json
{
  "mcpServers": {
    "flickr": {
      "command": "python",
      "args": ["-m", "flickr_mcp.server"],
      "cwd": "/絕對路徑/to/flickr-mcp",
      "env": {
        "FLICKR_API_KEY": "...",
        "FLICKR_API_SECRET": "...",
        "FLICKR_OAUTH_TOKEN": "...",
        "FLICKR_OAUTH_TOKEN_SECRET": "..."
      }
    }
  }
}
```

裝好後先叫我跑 `whoami` 確認通了。

## 嵌入作品集的典型流程

1. `list_albums` → 找到作品集那本的 album_id
2. `list_album_photos` 或 `get_photo_sizes` → 拿每張的直連網址
3. 把網址用你自己的 HTML/CSS 排進網站（圖放 Flickr、外觀你控制）

## 注意

- **上傳預設 private**：`upload_photo` 的 `is_public` 預設 False，要公開得明確指定。
- **憑證不進 git**：`.env` 已被 `.gitignore` 擋；只有 `.env.example` 進版控。建議用 MCP 設定的 `env` 區塊傳這四個變數。
- **`write` 權限不含刪除**：Flickr 的 `write` 涵蓋上傳與相簿管理，但**不含刪照片**——測試上傳的照片只能上 Flickr 網頁手動刪。上傳前先想清楚。
- OAuth token 是長效的，除非你在 Flickr 後台撤銷，否則不用重跑 `authorize.py`。

## 授權

MIT — 見 [LICENSE](LICENSE)。
