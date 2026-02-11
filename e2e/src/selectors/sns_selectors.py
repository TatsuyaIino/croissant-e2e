# src/selectors/sns_selectors.py

# SNSモーダル（Chakra dialog）
SNS_MODAL_SELECTOR = "[data-scope='dialog'][data-part='content'][role='dialog']"
SNS_MODAL_TEXT = "ご利用いただくには以下のリンクへのアクセスが必要です。"

# モーダル内のSNSリンク（3つ想定）
SNS_ACCOUNT_LINKS_SELECTOR = "a[target='_blank'][href]"

# チェックアイコン（MUI）
SNS_CHECK_ICON_SELECTOR = "svg[data-testid='CheckCircleIcon']"

# グレー/緑の判定（class差分）
SNS_CHECK_GRAY_SELECTOR = "svg[data-testid='CheckCircleIcon'][class*='css-l0elaw']"
SNS_CHECK_GREEN_SELECTOR = "svg[data-testid='CheckCircleIcon'][class*='css-qy6vmb']"

# CTA（ガチャを回す）… MUI Buttonが a[role=button] になってる
SNS_CTA_SELECTOR = "a[role='button']:has-text('ガチャを回す')"

# CTAが無効のときに入りがちなclass（念のため）
SNS_CTA_DISABLED_CLASS = "Mui-disabled"
