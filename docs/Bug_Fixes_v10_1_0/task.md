# タスクリスト (v10.1.0)

- [x] `rinkan_umis_pro_v10.1.0.py` の新規作成（v10.0.1のコピー）
- [x] アイコンスライダーのUI反映修正
    - [x] `on_thumb_size_change` の `update()` 追加
    - [x] `on_font_size_change` の `update()` 追加
- [x] グリッドタイルの選択状態表示修正
    - [x] `_create_grid_item` にチェックアイコンを追加
    - [x] `_update_item_visual` の更新ロジック強化
- [x] インスペクタ（プレビュー）表示修正
    - [x] `on_file_click` で `update_col_preview` を常に呼び出す
- [x] サムネイル・再生時間バッジの不具合修正
    - [x] `_refresh_grid_view` / `_refresh_list_view` でのキュー投入漏れを修正
    - [x] `_thumb_worker` でのバッジ反映タイミングの改善
- [x] 動作確認
    - [x] スライダー操作
    - [x] タイルクリックとインスペクタ表示
    - [x] サムネイル/バッジの逐次生成表示
- [x] `walkthrough.md` の作成
