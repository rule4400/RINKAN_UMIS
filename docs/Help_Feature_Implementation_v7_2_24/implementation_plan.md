# UMIS Pro v7.2.24 設定モーダル・ヒント機能実装計画

## 概要
設定画面の各項目にヘルプテキスト（ヒント）を表示する「情報ボタン（iアイコン）」を追加し、ユーザーが各設定の意味を直感的に理解できるようにします。

## 変更内容

### 1. HELP_TEXTS 辞書の更新
- 既存の `HELP_TEXTS` を、ユーザーから提供された最新の説明文に更新します。
- `rename_date`, `rename_venue`, `rename_scene`, `rename_pg`, `rename_id`, `date_format`, `show_file_log`, `scene_numbering`, `use_sequential`, `emergency_fmt`, `create_sub_folder`, `sub_folder_name` の各キーを含めます。

### 2. 設定モーダル (open_settings_modal) の改修
- **リネーム規則セクション**:
    - `ft.ExpansionTile` 内の各項目のラベル横に `create_info_btn(f"rename_{key}", self.page)` を配置します。
    - 日付書式のドロップダウン横にも `create_info_btn("date_format", self.page)` を追加します。
- **表示・動作設定セクション**:
    - `create_switch_tile_ctrl` 呼び出し時に、適切な `help_key` と `self.page` を渡すように変更します。
    - 「選別フォルダ名」の項目も `ft.Row` 内に情報ボタンを追加します。
- **カテゴリ設定セクション**:
    - カテゴリ名（Movie, Photoなど）の横に情報ボタンを追加します。

### 3. レイアウトと整列の徹底
- `ft.Row` 内での `vertical_alignment="center"` を徹底し、テキストとアイコンがずれないように調整します。
- ヘルパー関数（`create_switch_tile_ctrl`, `create_input_tile`）は既にヒント表示に対応しているため、これらを最大限活用します。

## 検証計画
- アプリケーションが起動することを確認。
- 設定モーダルを開き、各項目の横に「i」アイコンが表示されていることを確認。
- 各「i」アイコンをクリックし、正しいヘルプテキストがダイアログで表示されることを確認。
- 各スイッチやドロップダウンが従来どおり機能し、設定が保存されることを確認。
