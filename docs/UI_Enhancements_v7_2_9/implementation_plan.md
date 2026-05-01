# UMIS Pro v7.2.9 UI改修実装計画

## 概要
ユーザーの要望に基づき、UIの利便性を向上させるための2点の改修を行います。

1. **可変スプリッターの実装**: ソースファイルパネルとシーンパネルの境界に、マウスドラッグで幅を変更できるスプリッターを追加します。
2. **リスト表示のテキスト見切れ修正**: ソースファイルのリスト表示において、カテゴリ、サイズ、シーン名の列幅をフォントサイズに合わせた動的な値に変更し、テキストが途切れないようにします。

## ユーザーレビューが必要な事項
> [!IMPORTANT]
> スプリッターの実装により、メインコンテンツのレイアウトが動的に変更されます。最小幅と最大幅の制限（例: 200px 〜 600px）を設けますが、極端なサイズ変更によりUIが崩れる可能性があります。

## 変更内容

### UMIS App 本体

#### [MODIFY] [rinkan_umis_pro_v7.2.9.py](file:///Users/kiroku_keizo/開発/UMIS%20(Universal%20Media%20Ingest%20System)/安定版/rinkan_umis_pro_v7.2.9.py) [NEW]

- **VERSION更新**: `VERSION = "7.2.9"` に更新。
- **初期化 (`__init__`)**:
    - `self.scene_panel_width = 320` を追加。
- **UI構築 (`build_ui`)**:
    - `scene_panel` の `width` を `self.scene_panel_width` に固定（`expand=True` は削除）。
    - `ft.VerticalDivider` を `ft.GestureDetector` を含むスプリッターコンポーネントに置換。
    - `on_pan_update` イベントハンドラ `on_splitter_drag` を実装。
- **リスト表示更新 (`_refresh_list_view`)**:
    - 列幅の固定値（50, 65, 85）を `font_sz` に基づく計算値に変更。
    - 例: `width=font_sz * 4`, `width=font_sz * 6`, `width=font_sz * 8` など。

## 検証計画

### 自動テスト（ブラウザ/UI検証）
- Fletアプリケーションを実行し、以下の操作を確認します。
    - スプリッターをドラッグしてシーンパネルの幅が変わること。
    - リスト表示に切り替えた際、各列のテキストが適切に表示され、見切れていないこと。

### 手動確認
- ウィンドウサイズを変更した際のレイアウト追従性を確認。
