# タスクリスト (v7.3.5)

- [x] `rinkan_umis_pro_v7.3.5.py` ファイルの生成と `VERSION` の更新
- [x] 【根本解決：カスタムモーダルへの移行】
  - [x] Fletネイティブの `AlertDialog` を廃止し、`Stack` 管理下の `settings_overlay` (Container) によるカスタムモーダルを実装
  - [x] これにより、モーダル表示中も `tutorial_overlay` が最前面でクリックを確実に受け取れる設計へ変更
- [x] 【レイヤー構造の再定義】
  - [x] `build_ui` において、`Main < Settings Overlay < Tutorial Overlay` の順序で `Stack` を構成
- [x] 【ハイライトデザインの洗練】
  - [x] 白色の細い枠線（WHITE70）と透過感のある背景を維持し、視認性を確保
- [x] 【座標精度の修正】
  - [x] 履歴表示ボタンのハイライト位置を正確に修正
- [x] 【UI・機能の継承】
  - [x] 設定画面最上部の「ガイド再開」ボタン、右クリック範囲選択、シーンバッジ等の基幹機能を完全維持
- [x] 動作検証（IndentationError/SyntaxErrorの解消、GUI起動確認）
