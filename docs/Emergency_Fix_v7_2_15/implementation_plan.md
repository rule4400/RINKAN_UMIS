# UMIS Pro v7.2.15 緊急バグ修正およびUI・Shift選択の極限最適化実装計画

## 概要
起動を妨げている SyntaxError の修正、およびユーザー体験の要である Shift キーによる範囲選択の視覚化と安定化を行います。また、UIのレスポンシブ動作とリスト表示のレイアウトを最終調整します。

1. **SyntaxErrorの修正**: 履歴画面の引数重複を解消し、確実に起動するようにします。
2. **Shift状態の可視化**: ツールバーに Shift キーの ON/OFF 状態を表示するラベルを追加し、ユーザーが確実にキー入力を認識できるようにします。
3. **範囲選択の安定化**: 範囲選択実行後に Shift 状態をリセットし、入力スタックを防ぎます。
4. **UIの最終調整**: シーングリッドのレスポンシブ動作と、リスト表示の列幅固定化を確実に実施します。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.15.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.15.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.15"` に更新。
- **SyntaxError修正**:
    - `_build_history_entry_widget` 内の `ft.Column(spacing=8, spacing=5)` を `spacing=5` に修正。
- **Shift状態可視化**:
    - `__init__` に `self.lbl_shift_status` を定義。
    - `build_ui` で `thumb_toolbar` に `self.lbl_shift_status` を配置。
    - `on_keyboard_event` でラベルのテキストと色を更新。
- **範囲選択後のリセット**:
    - `on_file_click` 内の範囲選択処理終了後、`self.shift_pressed = False` に戻し、ラベルを更新。
- **レイアウト修正**:
    - `grid_scenes` の `max_extent` 削除を確認。
    - `_refresh_list_view` の列幅を (カテゴリ: 65, サイズ: 80, シーン名: 110) に設定。

## 検証計画
- アプリケーションが正常に起動することを確認。
- キーボードの Shift キーを押した際、ツールバーのラベルが "Shift: ON" になることを確認。
- 範囲選択実行後、ラベルが "Shift: OFF" に戻ることを確認。
- パネルリサイズ時にシーングリッドの列数が切り替わることを確認。
