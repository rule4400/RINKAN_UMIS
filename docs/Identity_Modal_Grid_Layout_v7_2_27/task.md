# タスクリスト (v7.2.27)

- [x] `rinkan_umis_pro_v7.2.27.py` の準備
- [x] `VERSION` を `7.2.27` に更新
- [x] Tooltipエラーの修正 (`create_info_btn`)
- [x] `format_card` 内の `NameError` の修正（関数定義順序の修正）
- [x] `show_identity_modal` のタイル型グリッドレイアウト化
    - [x] リストエリアを `ft.Row(wrap=True)` に変更
    - [x] タイルのデザイン適用（固定幅・高さ、角丸、枠線など）
    - [x] 選択時の強調（太い白色枠線、背景色変化）
    - [x] 追加ボタンのヘッダーへの移動（`ft.Icons.ADD_CIRCLE_OUTLINE`）
- [x] 動作検証（アプリ起動、モーダル動作、エラー有無の確認）
