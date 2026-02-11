# src/selectors/embed_form_selectors.py

# HubSpot埋め込みフォーム（hs-form）全体
HS_FORM_SELECTOR = "form.hs-form"

# 必須エラー（各項目）
HS_FIELD_ERROR_SELECTOR = "ul.hs-error-msgs label.hs-error-msg"

# エラーロールアップ（全体）
HS_ERROR_ROLLUP_SELECTOR = "div.hs_error_rollup label.hs-main-font-element"
HS_ERROR_ROLLUP_TEXT = "全ての必須項目に入力してください。"

# 送信ボタン
HS_SUBMIT_SELECTOR = "input[type='submit'][value='送信'], input.hs-button.primary"

# 必須フィールド（あなたが提示したname属性に合わせる）
HS_FIRSTNAME = "input[name='firstname']"
HS_LASTNAME  = "input[name='lastname']"
HS_EMAIL     = "input[name='email']"
HS_PHONE     = "input[name='phone']"
HS_COMPANY   = "input[name='company']"

# 任意：ファイル添付
HS_FILE = "input[type='file'][name='file_attach']"

# 必須エラーテキスト（各項目）
HS_REQUIRED_ERROR_TEXT = "この必須項目を入力してください。"

EMBED_FORM_IFRAME_SELECTOR = "iframe.hs-form-iframe"
EMBED_FORM_SUBMIT_SELECTOR = "input[type='submit'][value='送信']"

