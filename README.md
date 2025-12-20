# MultiMails

一個簡單易用的批次寄信工具，透過 CSV 檔案批次寄送客製化郵件。支援自訂 SMTP 伺服器、Markdown 郵件內容與 PDF 附件。

## 功能特色

- ✉️ **批次寄送郵件**：透過 CSV 檔案批次寄送郵件給多位收件者
- 🎨 **Markdown 支援**：郵件內容支援 Markdown 語法，讓郵件排版更美觀
- 📝 **客製化內容**：使用變數模板，為每位收件者客製化郵件內容
- 📎 **附件支援**：可為每封郵件附上不同的 PDF 檔案
- 🔧 **彈性 SMTP 設定**：支援自訂 SMTP 伺服器，可使用 Gmail、Outlook 等各種郵件服務
- 🚀 **多執行緒處理**：使用多執行緒技術，加快批次寄送速度

## 環境需求

- Python 3.8+
- Flask
- Flask-Mail

## 安裝步驟

1. **Clone 專案**
```bash
git clone https://github.com/SeanGau/multimails.git
cd multimails
```

2. **安裝相依套件**
```bash
uv sync
```

3. **設定配置檔**
```bash
cp config.example.py config.py
```

編輯 `config.py`，設定你的 SECRET_KEY：
```python
SECRET_KEY = 'your_secret_key'
```

4. **啟動應用程式**
```bash
uv run flask run
```

應用程式會在 `http://localhost:5000` 啟動。

## 使用說明

### 1. 填寫表單

訪問 `http://localhost:5000`，填寫以下資訊：

- **寄件者**：寄件者的電子郵件地址
- **SMTP Server**：您的郵件伺服器地址（例：`smtp.gmail.com`、`smtp.office365.com`）
- **SMTP Port**：SMTP 埠號（通常 TLS 使用 587，SSL 使用 465）
- **使用 TLS/SSL**：是否啟用 TLS 加密連線
- **Email / Username**：SMTP 登入帳號
- **Password**：SMTP 登入密碼或應用程式專用密碼
- **Template**：郵件內容模板（支援 Markdown 語法）
- **CSV 檔案**：包含收件者資訊的 CSV 檔案
- **附件**：（選填）要附加的 PDF 檔案

### 2. 準備 CSV 檔案

CSV 檔案需包含以下必要欄位：

- `email`：收件者的電子郵件地址
- `subject`：郵件主旨
- 其他 template 中有用到的變數

**選填欄位：**
- `attachment`：要附加的 PDF 檔案名稱（不含 `.pdf` 副檔名）
- 其他自訂欄位：可在郵件模板中使用

**CSV 範例：**
```csv
email,subject,name,attachment
user1@example.com,歡迎加入我們,小明,certificate
user2@example.com,歡迎加入我們,小華,certificate2
user3@example.com,歡迎加入我們,小美,
```

### 3. 撰寫郵件模板

郵件模板支援 Markdown 語法和變數替換。變數需使用 `$` 符號開頭。

**範例：**
```markdown
Dear $name,

感謝您的註冊！我們很高興您加入我們的社群。

## 接下來的步驟

1. 完成您的個人資料
2. 探索我們的服務
3. 開始使用

祝您使用愉快！

最誠摯的問候，  
團隊敬上
```

### 4. 上傳附件（選填）

- 目前僅支援 PDF 格式的附件
- 可上傳多個 PDF 檔案
- 在 CSV 檔案中，使用 `attachment` 欄位指定要附加的檔案名稱（不需加 `.pdf`）
- 如果某一列的 `attachment` 欄位為空，該封郵件將不會附加檔案

### 5. 提交並寄送

點擊「Submit」按鈕後，系統會：
1. 讀取 CSV 檔案中的收件者資訊
2. 為每位收件者客製化郵件內容
3. 使用多執行緒並行寄送郵件
4. 顯示寄送結果（成功/失敗）

## 注意事項

⚠️ **寄送限制**
- 各郵件服務商可能有每日寄送數量限制
- Gmail 免費帳號每日限制約 500 封
- 建議分批寄送大量郵件，避免觸發垃圾郵件偵測

⚠️ **檔案限制**
- CSV 檔案必須是 UTF-8 編碼
- 附件目前僅支援 PDF 格式
- 上傳的檔案會在寄送完成後自動刪除

## 授權

本專案採用 [GNU General Public License v3.0](LICENSE) 授權。