# UMIS Pro v7.2.20 Shiftキー単体での範囲選択修正計画

## 概要
v7.2.19 で導入したデバッグロジックにおいて、Shiftキー単独の押下状態が `self.shift_pressed` 変数に正しく同期されない場合がある問題を修正します。また、通常の左クリック操作における範囲選択ロジックを最適化し、右クリックの代替機能と合わせて、あらゆる環境で確実な一括選択を実現します。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.20.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.20.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.20"` に更新。
- **build_ui**: `on_keyboard` イベントハンドラを修正。
    - メソッドの冒頭で `self.shift_pressed = e.shift` を確実に実行し、キーボードの状態を同期。
    - デバッグ表示のテキスト（[SHIFT ON] / [SHIFT OFF]）を状態に合わせて更新。
- **on_file_click**: 左クリック時の範囲選択ロジックを修正。
    - `self.shift_pressed` が True の場合に、起点から現在地までの範囲選択を確実に実行。
    - 実行後にフラグとデバッグ表示をリセットし、連続した誤動作を防止。

## 検証計画
- アプリケーションが起動することを確認。
- Shiftキー単体を押した際、ツールバーのデバッグラベルに [SHIFT ON] と表示されることを確認。
- Shiftキーを押しながらサムネイルを左クリックして、範囲選択が正常に動作することを確認。
- 範囲選択完了後、デバッグラベルが "Shift Mode Reset" に戻ることを確認。
- 右クリック（副ボタン）による範囲選択も引き続き動作することを確認。
