# e2e/src/selectors/line_selectors.py

LINE_MODAL_TEXT = "本コンテンツのご利用にはLINE連携が必要です。"

# あなたのDOMそのまま
LINE_MODAL_SELECTOR = "[data-scope='dialog'][data-part='content'][role='dialog']"

# 「LINEでログイン」押下ターゲット（imgではなく “親” をクリックできるように複数用意）
# あなたのDOM: img alt="LINEでログイン" を起点に「親の親」を狙うのが効くことが多い
LINE_LOGIN_IMG_SELECTOR = "img[alt='LINEでログイン']"
LINE_LOGIN_TEXT_SELECTOR = "div:has-text('LINEでログイン')"

# LINEログイン画面のログインボタン（2パターン）
LINE_LOGIN_BUTTON_SELECTOR = (
    "div.login-button button[type='submit'], "
    "button:has-text('ログイン')"
)

DRAW_COUNT_MARK_TEXT_1 = "1"
