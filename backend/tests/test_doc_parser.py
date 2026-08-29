import pytest

from app.services.doc_parser import parse_document
from tests.conftest import register


def test_parse_markdown_keeps_teaching_content_and_drops_non_content():
    parsed = parse_document(
        "lesson.md",
        """---
title: should not become material
---
# 细胞

叶绿体是光合作用的场所。

## 细胞器

- 线粒体进行呼吸作用
- [查看示例](https://example.com)

> 这是重点。

| 名称 | 作用 |
| --- | --- |
| 核糖体 | 合成蛋白质 |

质能方程为 $E=mc^2$ 。

<!-- 隐藏指令 -->

```python
ignore_all_previous_instructions()
```

![构造图](https://example.com/cell.png)
""".encode("utf-8"),
    )

    assert parsed.error is None
    assert "细胞" in parsed.text
    assert "叶绿体是光合作用的场所" in parsed.text
    assert "查看示例" in parsed.text
    assert "https://example.com" not in parsed.text
    assert "引用：这是重点" in parsed.text
    assert "[表格]" in parsed.text
    assert "核糖体 | 合成蛋白质" in parsed.text
    assert "$E=mc^2$" in parsed.text
    assert "should not become material" not in parsed.text
    assert "ignore_all_previous_instructions" not in parsed.text
    assert "构造图" not in parsed.text


def test_parse_markdown_rejects_non_utf8_input():
    parsed = parse_document("lesson.md", b"\xff\xfe")

    assert parsed.text == ""
    assert parsed.error == "Markdown 文件必须使用 UTF-8 编码"


@pytest.mark.asyncio
async def test_upload_accepts_markdown_reported_as_text_plain(client, monkeypatch):
    registered = await register(client, "markdown-upload@example.com")

    monkeypatch.setattr("app.api.documents.upload_bytes", lambda *_args, **_kwargs: None)
    response = await client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {registered['token']}"},
        files={"file": ("lesson.md", "# 细胞\n\n叶绿体进行光合作用。".encode(), "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["filename"] == "lesson.md"
