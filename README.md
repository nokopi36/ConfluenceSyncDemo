# ConfluenceSyncDemo

docs配下のマークダウンファイルを自動的にConfluenceに同期するプロジェクトです。

## 機能

- GitHub Actionsを使用した自動同期
- Confluence REST APIを直接使用（カスタマイズ可能）
- Markdownのfrontmatterでページ設定を管理
- 既存ページの更新と新規ページ作成に対応

## セットアップ

### 1. GitHub Secretsの設定

以下のSecretsをリポジトリに設定してください：

| Secret名 | 説明 | 例 |
|---------|------|-----|
| `CONFLUENCE_BASE_URL` | ConfluenceのベースURL | `https://your-domain.atlassian.net/wiki` |
| `CONFLUENCE_USER_NAME_SECRET` | Confluenceのユーザー名（メールアドレス） | `your-email@example.com` |
| `CONFLUENCE_API_TOKEN_SECRET` | Confluence APIトークン | [取得方法](#api-tokenの取得方法) |
| `CONFLUENCE_PARENT_ID` | 親ページのID（オプション） | `123456789` |
| `CONFLUENCE_SPACE_KEY` | スペースキー（オプション、デフォルト: DOCS） | `DOCS` |

### 2. API Tokenの取得方法

1. Atlassian アカウント設定にアクセス: https://id.atlassian.com/manage-profile/security/api-tokens
2. 「APIトークンを作成」をクリック
3. トークン名を入力（例: GitHub Actions）
4. 生成されたトークンをコピーして、GitHub Secretsに保存

### 3. マークダウンファイルの設定

`docs/` ディレクトリにマークダウンファイルを配置します。

#### frontmatterの例

```markdown
---
confluence_page_id: 1617395903      # 既存ページを更新する場合（オプション）
confluence_space_key: DOCS          # スペースキー（オプション）
confluence_title: "ページタイトル"    # ページタイトル（オプション、未指定時はファイル名）
---

# ここから本文

マークダウンの内容がConfluenceに同期されます。
```

## 使い方

### 自動同期

以下のタイミングで自動的に同期されます：

- `main` ブランチへのpush時に `docs/**/*.md` ファイルが変更された場合

**注意**: `docs/` ディレクトリ配下のマークダウンファイル（`.md`）のみが監視対象です。他のファイル（`README.md`、`scripts/`、ワークフローファイルなど）の変更では自動実行されません。

### 手動実行

GitHub Actionsの画面から「Confluence Publisher」ワークフローを選択し、「Run workflow」ボタンで手動実行できます。

### ローカルでのテスト

```bash
# 依存関係のインストール
pip install -r requirements.txt

# 環境変数を設定
export CONFLUENCE_BASE_URL="https://your-domain.atlassian.net/wiki"
export CONFLUENCE_USER_NAME="your-email@example.com"
export CONFLUENCE_API_TOKEN="your-api-token"
export CONFLUENCE_PARENT_ID="123456789"  # オプション
export CONFLUENCE_SPACE_KEY="DOCS"       # オプション

# スクリプトの実行
python scripts/sync_to_confluence.py
```

## カスタマイズ

### Markdown変換のカスタマイズ

`scripts/sync_to_confluence.py` の `markdown_to_confluence_storage()` 関数を編集することで、Markdownの変換方法をカスタマイズできます。

現在サポートしている要素：
- 見出し（h1-h6）
- 太字・イタリック
- コードブロック・インラインコード
- テーブル
- 水平線

### ワークフローのカスタマイズ

`.github/workflows/confluence.yml` を編集して、トリガー条件や実行環境をカスタマイズできます。

## トラブルシューティング

### ページが更新されない

1. GitHub Secretsが正しく設定されているか確認
2. `confluence_page_id` が正しいか確認
3. APIトークンに適切な権限があるか確認

### Markdown変換がうまくいかない

複雑なMarkdown構文の場合、`scripts/sync_to_confluence.py` の変換ロジックをカスタマイズしてください。

### frontmatterが正しく認識されない

frontmatterを使用する場合は、以下の点に注意してください：

- frontmatterは**ファイルの先頭**に配置する必要があります
- `---` で囲まれた部分がfrontmatterとして認識されます
- 本文中で水平線（`---`）を使う場合は、必ずfrontmatterを先頭に配置するか、frontmatterを使わない場合は本文の最初の行を `---` 以外で始めてください

**推奨される構造:**
```markdown
---
confluence_page_id: 123456789
---

# タイトル

本文

---

別のセクション  ← この水平線は問題なく処理されます
```

### GitHub Actionsのログを確認

1. リポジトリの「Actions」タブを開く
2. 「Confluence Publisher」ワークフローを選択
3. 実行ログで詳細なエラーメッセージを確認

## ライセンス

MIT