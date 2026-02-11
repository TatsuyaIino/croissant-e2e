START_GACHA_BTN_TEXT = "ガチャを回す"
DRAW_START_TEXT = "スタート"
SINGLE_DRAW_START_TEXT = "抽選スタート"

# カード画像（カードめくり）
CARD_IMAGE_SELECTOR = "img.chakra-image[alt^='結果']"

# ドット（抽選回数分）
DOT_BUTTON_SELECTOR = "div.css-k008qs button"

# 上部サムネ（2回以上）
TOP_THUMB_SELECTOR = "img.chakra-image.css-9qpbgg[alt^='結果']"

# 詳細ブロック（結果画像 + 今すぐつかう を含む塊）
# 1回のとき
DETAIL_BLOCK_SELECTOR_SINGLE = "div.css-1z13ymv"

DETAIL_SECTION_SELECTOR_MULTI = "div.css-10u597l:has-text('結果詳細')"

# 2回以上：結果詳細セクション直下の「1件ブロック」を取る
DETAIL_USE_BUTTON_SELECTOR = "button:has-text('今すぐつかう'), [role='button']:has-text('今すぐつかう')"
USED_BUTTON_SELECTOR = "button:has-text('使用済み'), [role='button']:has-text('使用済み')"



# 結果詳細内の「結果名」
# 結果名（1回抽選で使われる）
DETAIL_NAME_SELECTOR_SINGLE = "div.css-1cmdo0c"
# 2回以上：結果詳細セクション直下の「1件ブロック」を取る
DETAIL_BLOCK_SELECTOR_MULTI = (
    "div.chakra-stack"
    ":has(> div.css-1xhi066)"
    ":has(> button:has-text('今すぐつかう'), > button:has-text('使用済み'))"
)

# 結果名（2回以上で使われるが、ボタンラベルとも被るので flow 側で除外する）
DETAIL_NAME_SELECTOR_MULTI = "div.css-1r7lvp9"
DETAIL_RESULT_IMG_SELECTOR = "img.chakra-image[alt^='結果']"
DETAIL_DESC_TEXT_SELECTOR = "div.MuiBox-root span[style*='white-space: pre-wrap']"
DETAIL_DESC_IMAGE_SELECTOR = "div.MuiBox-root img.richEditorTheme__image"
DETAIL_USE_BUTTON_SELECTOR = "button:has-text('今すぐつかう')"



# 使用モーダル
RESULT_MODAL_SELECTOR = "[data-scope='dialog'][data-part='content'][role='dialog']"
RESULT_MODAL_MESSAGE_TEXT = "一度ご利用いただくと元に戻すことはできません。対象にお間違いがないかご確認ください。"
RESULT_MODAL_USE_BUTTON_SELECTOR = "button:has-text('つかう')"
RESULT_MODAL_BACK_BUTTON_SELECTOR = "button:has-text('戻る')"


# リンク一覧
LINK_ITEM_SELECTOR = "div.css-1uom0pk"
LINK_DESC_TEXT_SELECTOR = "span[style*='white-space: pre-wrap']"
LINK_DESC_IMAGE_SELECTOR = "img.richEditorTheme__image"
LINK_BUTTON_SELECTOR = "a[target='_blank'][href]"
LINK_BUTTON_TEXT_SELECTOR = "div.css-1r7lvp9"

# カード画面 UI（divでもOK）
CARD_TAP_NEXT_TEXT = "タップで次へ"
CARD_SKIP_TEXT = "スキップ"
CARD_TAP_NEXT_SELECTOR = "text=タップで次へ, div:has-text('タップで次へ'), button:has-text('タップで次へ')"
CARD_SKIP_SELECTOR = "text=スキップ, div:has-text('スキップ'), button:has-text('スキップ')"

# もう一度あそぶ
PLAY_AGAIN_BUTTON_SELECTOR = "button:has-text('もう一度あそぶ')"

# Toast
TOAST_TITLE_SELECTOR = "[data-scope='toast'][data-part='title']"
TOAST_USED_MESSAGE = "本日はご利用済みです"
TOAST_USED_MESSAGE_ONLY_ONCE = "ご利用済みです"

# 抽選回数画面の目印
DRAW_COUNT_BUTTON_TEXT_1 = "1"

PAID_CONFIRM_TITLE_TEXT = "購入内容の確認"
PAID_MEMBER_LOGIN_TITLE_TEXT = "会員登録済みの方はこちら"



