# UMIS Pro v7.2.19 範囲選択の究極安定化とデバッグ機構の実装計画

## 概要
macOS環境におけるFletのキーボードイベント検知の不安定さを打破するため、以下の2つのアプローチで範囲選択機能を強化します。

1. **右クリック（副ボタン）による範囲選択**: Shiftキーを使用せずに、起点（左クリック）から終点（右クリック）までの範囲を一括選択できるようにします。
2. **キー入力デバッグ機構**: OSから送られてくる生のキーボードイベントを画面上に可視化し、状況をリアルタイムで把握できるようにします。また、「S」キーによる代替範囲選択モードも導入します。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.19.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.19.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.19"` に更新。
- **__init__**: `lbl_shift_status` を `lbl_key_debug` に変更。
- **build_ui**: 
    - `thumb_toolbar` 内のラベル配置を変更。
    - `on_keyboard` 関数を生データ出力および「S」キー検知ロジックに書き換え。
- **on_file_click**: 範囲選択完了時のデバッグラベルのリセット処理を追加。
- **on_file_right_click**: 右クリック時の範囲選択ロジックを新規追加。
- **_refresh_grid_view / _refresh_list_view**: `ft.GestureDetector` に `on_secondary_tap` を追加し、右クリックイベントを有効化。

## 検証計画
- アプリケーションが起動することを確認。
- サムネイルを左クリックして起点を選択し、別のサムネイルを右クリック（二本指タップ）して範囲選択ができるか確認。
- キーボードを押した際、ツールバーに生データ（Key, Shift, Ctrlの状態）が表示されるか確認。
- 「S」キーを押して [RANGE MODE ON] と表示され、次のクリックで範囲選択が動作するか確認。
