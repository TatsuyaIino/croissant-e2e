# e2e/src/selectors/diagnose_selectors.py

START_BTN_TEXT = "診断を始める"
QUESTION_LABEL_TEXT = "QUESTION"

# Q番号表示（例: 1,2,3）: テキストで拾う（厳密にしたければ領域セレクタに）
MULTI_LABEL_TEXT = "（複数回答可）"

NEXT_BTN_TEXT = "次へ"
RESULT_CONFIRM_TEXT = "回答お疲れ様でした。"
RESULT_BTN_TEXT = "診断結果を確認する"
BACK_TO_ANS_TEXT = "回答選択に戻る"

# 設問画像の alt
QUESTION_IMAGE_ALT = "question image"
QUESTION_IMAGE_SELECTOR = "img[alt='question image']"

# 回答：checkbox label内の p を拾う
ANSWER_LABEL_P_SELECTOR = "span.chakra-checkbox__label p"

# （あれば）「もう一度あそぶ」ボタンはガチャと同じセレクタを使う想定
