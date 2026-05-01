# UMIS Pro v7.2.22 シーンボタンUI改善計画

## 概要
シーン選択パネル内のボタンにおいて、ファイル件数バッジがレイアウト崩れの原因となっている問題を解決します。バッジをボタン内の右上に絶対配置（Stack + Positioned）することで、パネル幅に関わらず常に見やすく、プロフェッショナルな外観を実現します。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.22.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.22.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.22"` に更新。
- **refresh_scene_buttons**: ボタンの構築ロジックを刷新。
    - **構造の変更**: `ft.Column` のみから、`ft.Stack` をベースにした構造に変更。
    - **絶対配置の導入**: `ft.Container`（バッジ）に `right=0, top=0` を設定し、ボタンの右上に固定。
    - **メインコンテンツの集約**: 日付番号とシーン名を `ft.Column` にまとめ、Stack内の中央（`alignment=ft.alignment.center`）に配置。
    - **テキストの最適化**: シーン名に `max_lines=1` および `overflow=ft.TextOverflow.ELLIPSIS` を追加し、ボタンからはみ出さないように調整。

## 検証計画
- アプリケーションが起動することを確認。
- シーンにファイルを割り当てた際、件数バッジがボタンの右上に表示されることを確認。
- スプリットバーでパネル幅を極端に狭めた際、バッジがボタン下部に埋まることなく、常に右上に維持されていることを確認。
- シーン名が長い場合に、末尾が省略（...）され、レイアウトが維持されていることを確認。
