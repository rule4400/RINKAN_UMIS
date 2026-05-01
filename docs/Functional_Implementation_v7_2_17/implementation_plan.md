# UMIS Pro v7.2.17 欠落機能の完全実装およびバグ修正実装計画

## 概要
前バージョンで発生した `lbl_assigned_count` の定義漏れによるクラッシュを修正し、指示されていた新機能（未割当選択、ドライブ整合性チェック、Shiftキー可視化など）を確実にコードに反映させます。

1. **クラッシュの修正**: `__init__` 内で削除されてしまった `lbl_assigned_count` を復元し、必要な変数（`last_ingested_drive` 等）を全て定義します。
2. **UI要素の確実な配置**: ツールバーに「未割当を選択」ボタンと「Shiftステータス」ラベルを配置します。
3. **Shiftキー操作の安定化**: リアルタイムな状態表示と、範囲選択実行後の自動リセットを実装し、操作の不確実性を排除します。
4. **安全機能の強化**: 最後に取り込んだドライブとの一致チェックによる誤フォーマット防止と、ドライブ変更時のシーン選択リセットを実装します。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.17.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.17.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.17"` に更新。
- **初期化 (`__init__`)**:
    - `self.lbl_assigned_count`, `self.lbl_shift_status`, `self.last_ingested_drive` を確実に定義。
- **UI構築 (`build_ui`)**:
    - `thumb_toolbar` に全ての要素（全選択、未割当を選択、各ラベル）を記述。
- **キーボードイベント (`on_keyboard_event`)**:
    - ラベルのテキストと色をリアルタイムに更新するロジックを実装。
- **ファイルクリック (`on_file_click`)**:
    - 範囲選択終了後に `shift_pressed = False` とラベルの更新を実行。
- **新メソッド (`select_unassigned`)**:
    - シーン未設定ファイルのみを選択状態にするロジックを実装。
- **整合性チェック (`check_format_button_state`)**:
    - `last_ingested_drive` との比較ロジックを正確に記述。
- **シーンリセット**:
    - `_start_scan` 冒頭にシーン選択状態のリセットを追加。

## 検証計画
- アプリケーションがエラーなく起動することを確認。
- Shiftキーを押した際に「Shift: ON」と表示され、範囲選択後に「Shift: OFF」に戻ることを確認。
- 「未割当を選択」ボタンで適切なファイルが選択されることを確認。
- 別のドライブを挿した際に「カード初期化」ボタンが無効化されることを確認。
