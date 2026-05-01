# UMIS Pro v7.2.11 複数選択（範囲選択）機能の安定化実装計画

## 概要
FletのShiftキー監視が不安定な問題を解決するため、UI上に明示的な「範囲選択モード」を導入します。

1. **範囲選択トグルの追加**: サムネイルツールバーに範囲選択モードのON/OFFボタンを追加します。
2. **クリックロジックの改善**: Shiftキーの状態だけでなく、UIのモード設定も参照するようにし、確実に範囲選択ができるようにします。
3. **自動解除機能**: 範囲選択実行後にモードを自動でOFFにすることで、誤操作を防ぎます。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.11.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.11.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.11"` に更新。
- **初期化 (`__init__`)**:
    - `self.is_range_select_mode = False` を追加。
    - `self.btn_range_select` を定義（アイコン: `LIBRARY_ADD_CHECK`）。
- **UI構築 (`build_ui`)**:
    - `thumb_toolbar` に `self.btn_range_select` を追加。
- **新メソッド実装**:
    - `toggle_range_select_mode(self, e)`: モードを切り替え、アイコンの色を更新します。
- **既存メソッド修正**:
    - `on_file_click(self, e, idx)`: `is_range_select_mode` を考慮した範囲選択ロジックに更新し、実行後の自動解除処理を追加。

## 検証計画
- ツールバーに新しく追加された「範囲選択モード」ボタンが正しく表示されることを確認。
- ボタンをONにしてから2つのファイルをクリックした際、その間のファイルがまとめて選択されることを確認。
- 範囲選択後にモードが自動的にOFFに戻ることを確認。
- 従来のShiftキーによる選択も（可能な限り）動作し続けることを確認。
