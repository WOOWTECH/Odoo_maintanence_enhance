# Odoo 維護入口增強模組

一個擴充 Odoo 18 維護模組的模組，提供員工自助入口以提交和追蹤維護請求。

## 功能特色

- **員工自助入口**：透過網頁入口提交維護請求
- **設備管理**：追蹤所有設備及其維護歷史
- **請求追蹤**：即時更新維護請求狀態
- **維護排程**：規劃和安排維護活動
- **多語言支援**：繁體中文 (zh_TW) 和英文

## 系統需求

- Odoo 18.0
- Python 3.10+

## 相依模組

- `base`
- `mail`
- `portal`
- `maintenance`

## 安裝方式

1. 將此儲存庫複製到您的 Odoo 附加模組目錄：
   ```bash
   git clone https://github.com/WOOWTECH/Odoo_maintanence_enhance.git
   ```

2. 更新 Odoo 設定檔中的附加模組路徑

3. 重新啟動 Odoo 伺服器

4. 前往應用程式選單並安裝「維護入口」

## 模組結構

```
maintenance_portal/
├── controllers/
│   └── portal.py              # 入口控制器
├── i18n/
│   ├── maintenance_portal.pot # 翻譯模板
│   └── zh_TW.po               # 繁體中文翻譯
├── models/
│   ├── maintenance_equipment.py
│   └── maintenance_request.py
├── security/
│   ├── ir.model.access.csv
│   └── maintenance_portal_security.xml
├── static/
│   └── src/
│       ├── css/
│       │   └── portal.css     # 入口樣式
│       └── img/
│           ├── equipment.svg
│           └── maintenance.svg
├── views/
│   ├── maintenance_equipment_views.xml
│   ├── maintenance_request_views.xml
│   └── portal_templates.xml
├── __init__.py
└── __manifest__.py
```

## 使用方式

### 後台管理（維護團隊）

1. 進入 **維護** 選單
2. 管理設備和維護請求
3. 指派技術人員並安排維修
4. 追蹤維護歷史

### 入口網站（員工）

1. 透過 `/my/maintenance` 存取入口
2. 查看分配給您的設備
3. 提交新的維護請求
4. 追蹤請求狀態和歷史

## 截圖說明

### 入口儀表板
員工可透過直覺化介面查看其設備並提交維護請求。

### 請求表單
簡單的表單用於描述問題並請求維護支援。

## 授權條款

LGPL-3

## 作者

WOOWTECH

## 支援

如有問題或功能需求，請使用 [GitHub Issues](https://github.com/WOOWTECH/Odoo_maintanence_enhance/issues) 頁面。
