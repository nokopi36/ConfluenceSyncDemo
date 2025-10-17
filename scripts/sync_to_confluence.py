#!/usr/bin/env python3
"""
Confluence同期スクリプト

docs配下のマークダウンファイルをConfluenceに同期します。
frontmatterでページIDやスペースキーを指定できます。
"""

import os
import json
import requests
import re
from pathlib import Path
from typing import Dict, Tuple, Optional
import sys

# 環境変数から設定を取得
BASE_URL = os.environ.get('CONFLUENCE_BASE_URL', '').rstrip('/')
USERNAME = os.environ.get('CONFLUENCE_USER_NAME', '')
API_TOKEN = os.environ.get('CONFLUENCE_API_TOKEN', '')
PARENT_ID = os.environ.get('CONFLUENCE_PARENT_ID', '')
SPACE_KEY = os.environ.get('CONFLUENCE_SPACE_KEY', 'DOCS')

# 認証設定
auth = (USERNAME, API_TOKEN)
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


def validate_config():
    """必須の環境変数をチェック"""
    required_vars = {
        'CONFLUENCE_BASE_URL': BASE_URL,
        'CONFLUENCE_USER_NAME': USERNAME,
        'CONFLUENCE_API_TOKEN': API_TOKEN,
    }

    missing = [k for k, v in required_vars.items() if not v]

    if missing:
        print(f"❌ Error: Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """
    マークダウンのfrontmatterをパース

    Args:
        content: マークダウンの内容

    Returns:
        (frontmatter辞書, 本文)
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)

    if match:
        frontmatter_text = match.group(1)
        body = match.group(2)

        frontmatter = {}
        for line in frontmatter_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                # コメントを除去
                value = value.split('#')[0].strip()
                frontmatter[key.strip()] = value.strip('"\'')

        return frontmatter, body
    return {}, content


def markdown_to_confluence_storage(md_content: str, md_file_path: Optional[Path] = None, page_id: Optional[str] = None, images_to_upload: Optional[list] = None) -> str:
    """
    MarkdownをConfluenceのStorage形式に変換

    基本的な変換のみ実装。必要に応じてカスタマイズ可能。

    Args:
        md_content: Markdown形式のコンテンツ
        md_file_path: マークダウンファイルのパス（画像の相対パス解決用）
        page_id: ページID（画像アップロード用）
        images_to_upload: アップロードする画像のリスト（出力用）

    Returns:
        Confluence Storage形式のコンテンツ
    """
    content = md_content

    # 画像変換（![alt](url) 形式）
    def image_replace(match):
        alt_text = match.group(1)
        image_path = match.group(2)

        # 外部URLの場合
        if image_path.startswith(('http://', 'https://')):
            return f'<ac:image><ri:url ri:value="{image_path}" /></ac:image>'

        # ローカル画像の場合
        if md_file_path and images_to_upload is not None:
            # 相対パスを解決
            if not Path(image_path).is_absolute():
                image_full_path = (md_file_path.parent / image_path).resolve()
            else:
                image_full_path = Path(image_path)

            if image_full_path.exists():
                images_to_upload.append(image_full_path)
                filename = image_full_path.name
                # 添付ファイルとして参照
                return f'<ac:image><ri:attachment ri:filename="{filename}" /></ac:image>'
            else:
                print(f"   ⚠️  Image not found: {image_path}")
                return f'<p><em>Image not found: {image_path}</em></p>'

        # ページIDがない場合は警告
        return f'<p><em>Image: {image_path}</em></p>'

    content = re.sub(r'!\[(.*?)\]\((.*?)\)', image_replace, content)

    # 見出し変換
    content = re.sub(r'^######\s+(.*?)$', r'<h6>\1</h6>', content, flags=re.MULTILINE)
    content = re.sub(r'^#####\s+(.*?)$', r'<h5>\1</h5>', content, flags=re.MULTILINE)
    content = re.sub(r'^####\s+(.*?)$', r'<h4>\1</h4>', content, flags=re.MULTILINE)
    content = re.sub(r'^###\s+(.*?)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
    content = re.sub(r'^##\s+(.*?)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
    content = re.sub(r'^#\s+(.*?)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)

    # 太字変換
    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
    content = re.sub(r'__(.*?)__', r'<strong>\1</strong>', content)

    # イタリック変換
    content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
    content = re.sub(r'_(.*?)_', r'<em>\1</em>', content)

    # コードブロック変換
    code_block_pattern = r'```(\w*)\n(.*?)```'
    def code_block_replace(match):
        lang = match.group(1) or 'none'
        code = match.group(2)
        return f'<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">{lang}</ac:parameter><ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>'

    content = re.sub(code_block_pattern, code_block_replace, content, flags=re.DOTALL)

    # インラインコード変換
    content = re.sub(r'`(.*?)`', r'<code>\1</code>', content)

    # テーブル変換（簡易版）
    lines = content.split('\n')
    converted_lines = []
    in_table = False
    table_rows = []

    for line in lines:
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(line)
        else:
            if in_table:
                # テーブルを変換
                converted_lines.append(convert_table(table_rows))
                in_table = False
                table_rows = []
            converted_lines.append(line)

    if in_table:
        converted_lines.append(convert_table(table_rows))

    content = '\n'.join(converted_lines)

    # 水平線変換
    content = re.sub(r'^---+$', r'<hr />', content, flags=re.MULTILINE)

    # 段落変換
    paragraphs = content.split('\n\n')
    formatted_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para and not para.startswith('<'):
            para = f'<p>{para}</p>'
        formatted_paragraphs.append(para)

    content = '\n'.join(formatted_paragraphs)

    return content


def upload_attachment(page_id: str, file_path: Path) -> Optional[str]:
    """
    ページに添付ファイルをアップロード

    Args:
        page_id: ページID
        file_path: アップロードするファイルのパス

    Returns:
        添付ファイル名、失敗した場合はNone
    """
    url = f"{BASE_URL}/rest/api/content/{page_id}/child/attachment"

    try:
        # 既存の添付ファイルを確認
        response = requests.get(url, auth=auth, headers={'Accept': 'application/json'})

        filename = file_path.name
        existing_attachment = None

        if response.status_code == 200:
            attachments = response.json().get('results', [])
            for attachment in attachments:
                if attachment['title'] == filename:
                    existing_attachment = attachment
                    break

        # ファイルをアップロード
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'application/octet-stream')}
            upload_headers = {'X-Atlassian-Token': 'no-check'}

            if existing_attachment:
                # 既存の添付ファイルを更新
                attachment_url = f"{BASE_URL}/rest/api/content/{page_id}/child/attachment/{existing_attachment['id']}/data"
                response = requests.post(attachment_url, auth=auth, headers=upload_headers, files=files)
            else:
                # 新規アップロード
                response = requests.post(url, auth=auth, headers=upload_headers, files=files)

            if response.status_code in [200, 201]:
                print(f"   ✅ Uploaded attachment: {filename}")
                return filename
            else:
                print(f"   ⚠️  Failed to upload {filename}: {response.status_code}")
                return None
    except Exception as e:
        print(f"   ❌ Error uploading {file_path}: {str(e)}")
        return None


def convert_table(table_lines: list) -> str:
    """
    Markdownテーブルをconfluenceテーブルに変換

    Args:
        table_lines: テーブル行のリスト

    Returns:
        Confluenceテーブル形式
    """
    if len(table_lines) < 2:
        return '\n'.join(table_lines)

    # ヘッダー行
    header = [cell.strip() for cell in table_lines[0].split('|')[1:-1]]

    # データ行（区切り行をスキップ）
    data_rows = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        data_rows.append(cells)

    # Confluenceテーブル形式に変換
    table_html = '<table><tbody>'

    # ヘッダー
    table_html += '<tr>'
    for cell in header:
        table_html += f'<th>{cell}</th>'
    table_html += '</tr>'

    # データ行
    for row in data_rows:
        table_html += '<tr>'
        for cell in row:
            table_html += f'<td>{cell}</td>'
        table_html += '</tr>'

    table_html += '</tbody></table>'

    return table_html


def get_page_by_id(page_id: str) -> Optional[dict]:
    """
    ページIDでページを取得

    Args:
        page_id: ConfluenceページID

    Returns:
        ページ情報の辞書、見つからない場合はNone
    """
    url = f"{BASE_URL}/rest/api/content/{page_id}"

    try:
        response = requests.get(url, auth=auth, headers=headers)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            print(f"⚠️  Warning: Failed to get page {page_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error getting page {page_id}: {str(e)}")
        return None


def search_page_by_title(space_key: str, title: str) -> Optional[dict]:
    """
    タイトルとスペースキーでページを検索

    Args:
        space_key: Confluenceスペースキー
        title: ページタイトル

    Returns:
        ページ情報の辞書、見つからない場合はNone
    """
    url = f"{BASE_URL}/rest/api/content"
    params = {
        'spaceKey': space_key,
        'title': title,
        'type': 'page',
        'status': 'current',
        'expand': 'version'
    }

    try:
        response = requests.get(url, auth=auth, headers=headers, params=params)

        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                # タイトルが完全一致するページを返す
                for page in results:
                    if page['title'] == title:
                        return page
            return None
        else:
            print(f"⚠️  Warning: Failed to search page '{title}': {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error searching page '{title}': {str(e)}")
        return None


def create_page(space_key: str, title: str, content: str, parent_id: Optional[str] = None) -> Optional[dict]:
    """
    新規ページを作成

    Args:
        space_key: Confluenceスペースキー
        title: ページタイトル
        content: ページコンテンツ（Storage形式）
        parent_id: 親ページID（オプション）

    Returns:
        作成されたページ情報、失敗した場合はNone
    """
    url = f"{BASE_URL}/rest/api/content"

    data = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        }
    }

    if parent_id:
        data["ancestors"] = [{"id": parent_id}]

    try:
        response = requests.post(url, auth=auth, headers=headers, json=data)

        if response.status_code == 200:
            page_data = response.json()
            page_url = f"{BASE_URL}{page_data['_links']['webui']}"
            print(f"✅ Created page: {title}")
            print(f"   URL: {page_url}")
            print(f"   Page ID: {page_data['id']}")
            return page_data
        else:
            print(f"❌ Failed to create page: {title}")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error creating page {title}: {str(e)}")
        return None


def update_page(page_id: str, title: str, content: str, version: int) -> Optional[dict]:
    """
    既存ページを更新

    Args:
        page_id: ページID
        title: ページタイトル
        content: ページコンテンツ（Storage形式）
        version: 現在のバージョン番号

    Returns:
        更新されたページ情報、失敗した場合はNone
    """
    url = f"{BASE_URL}/rest/api/content/{page_id}"

    data = {
        "version": {"number": version + 1},
        "title": title,
        "type": "page",
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        }
    }

    try:
        response = requests.put(url, auth=auth, headers=headers, json=data)

        if response.status_code == 200:
            page_data = response.json()
            page_url = f"{BASE_URL}{page_data['_links']['webui']}"
            print(f"✅ Updated page: {title} (version {version} → {version + 1})")
            print(f"   URL: {page_url}")
            return page_data
        else:
            print(f"❌ Failed to update page: {title}")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error updating page {title}: {str(e)}")
        return None


def process_markdown_file(md_file: Path) -> bool:
    """
    単一のマークダウンファイルを処理

    Args:
        md_file: マークダウンファイルのパス

    Returns:
        成功した場合True、失敗した場合False
    """
    print(f"\n📄 Processing: {md_file}")

    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {str(e)}")
        return False

    # frontmatterをパース
    frontmatter, body = parse_frontmatter(content)

    # タイトルの決定
    title = frontmatter.get('confluence_title', md_file.stem)

    # 画像収集用のリスト
    images_to_upload = []

    # Confluenceのストレージ形式に変換
    confluence_content = markdown_to_confluence_storage(body, md_file, None, images_to_upload)

    # ページIDが指定されている場合は更新、なければ新規作成
    if 'confluence_page_id' in frontmatter:
        page_id = frontmatter['confluence_page_id']
        existing_page = get_page_by_id(page_id)

        if existing_page:
            # 画像を含む場合は再変換（ページIDを使用）
            if images_to_upload:
                images_to_upload = []
                confluence_content = markdown_to_confluence_storage(body, md_file, page_id, images_to_upload)

            result = update_page(
                page_id,
                title,
                confluence_content,
                existing_page['version']['number']
            )

            # 画像をアップロード
            if result and images_to_upload:
                print(f"   📎 Uploading {len(images_to_upload)} image(s)...")
                for image_path in images_to_upload:
                    upload_attachment(page_id, image_path)

            return result is not None
        else:
            print(f"⚠️  Page ID {page_id} not found, skipping...")
            return False
    else:
        # ページIDが指定されていない場合、タイトルで検索
        space_key = frontmatter.get('confluence_space_key', SPACE_KEY)
        parent_id = frontmatter.get('confluence_parent_id', PARENT_ID)

        # タイトルで既存ページを検索
        existing_page = search_page_by_title(space_key, title)

        if existing_page:
            # 既存ページが見つかった場合は更新
            page_id = existing_page['id']
            print(f"   🔍 Found existing page with title '{title}' (ID: {page_id})")

            # 画像を含む場合は再変換（ページIDを使用）
            if images_to_upload:
                images_to_upload = []
                confluence_content = markdown_to_confluence_storage(body, md_file, page_id, images_to_upload)

            result = update_page(
                page_id,
                title,
                confluence_content,
                existing_page['version']['number']
            )

            # 画像をアップロード
            if result and images_to_upload:
                print(f"   📎 Uploading {len(images_to_upload)} image(s)...")
                for image_path in images_to_upload:
                    upload_attachment(page_id, image_path)

            return result is not None
        else:
            # 既存ページが見つからない場合は新規作成
            result = create_page(space_key, title, confluence_content, parent_id)

            if result:
                page_id = result['id']

                # 画像がある場合はアップロードして再変換
                if images_to_upload:
                    print(f"   📎 Uploading {len(images_to_upload)} image(s)...")
                    for image_path in images_to_upload:
                        upload_attachment(page_id, image_path)

                    # 画像参照を含むコンテンツで再変換して更新
                    images_to_upload = []
                    confluence_content = markdown_to_confluence_storage(body, md_file, page_id, images_to_upload)
                    update_page(page_id, title, confluence_content, result['version']['number'])

                # 作成されたページIDをfrontmatterに追加する提案（オプション）
                print(f"💡 Tip: You can add 'confluence_page_id: {result['id']}' to frontmatter (optional)")

            return result is not None


def process_markdown_files(docs_dir: str) -> Tuple[int, int]:
    """
    docsディレクトリ内のマークダウンファイルを処理

    Args:
        docs_dir: ドキュメントディレクトリのパス

    Returns:
        (成功数, 失敗数)
    """
    docs_path = Path(docs_dir)

    if not docs_path.exists():
        print(f"❌ Error: Directory '{docs_dir}' does not exist")
        return 0, 0

    md_files = list(docs_path.rglob('*.md'))

    if not md_files:
        print(f"⚠️  No markdown files found in '{docs_dir}'")
        return 0, 0

    print(f"Found {len(md_files)} markdown file(s)")

    success_count = 0
    failure_count = 0

    for md_file in md_files:
        if process_markdown_file(md_file):
            success_count += 1
        else:
            failure_count += 1

    return success_count, failure_count


def main():
    """メイン処理"""
    print("=" * 60)
    print("Confluence Sync Script")
    print("=" * 60)

    # 設定の検証
    validate_config()

    print(f"\nConfiguration:")
    print(f"  Base URL: {BASE_URL}")
    print(f"  Username: {USERNAME}")
    print(f"  Default Space: {SPACE_KEY}")
    if PARENT_ID:
        print(f"  Default Parent ID: {PARENT_ID}")

    # マークダウンファイルを処理
    success_count, failure_count = process_markdown_files('docs')

    # サマリー
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed:  {failure_count}")
    print(f"📊 Total:   {success_count + failure_count}")

    # 失敗があった場合は終了コード1で終了
    if failure_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()