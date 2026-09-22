import pytest

from app.services.platform import detect

CASES = [
    ("https://www.douyin.com/video/734123", "short", "douyin", False),
    ("https://v.douyin.com/iAbCdE/", "short", "douyin", False),
    ("https://www.douyin.com/user/MS4wLjABAAAA?from=x", "short", "douyin", True),
    ("https://v.kuaishou.com/xyz", "short", "kuaishou", False),
    ("https://www.kuaishou.com/short-video/3x", "short", "kuaishou", False),
    ("https://www.xiaohongshu.com/explore/64ab", "short", "xiaohongshu", False),
    ("https://xhslink.com/a1b2", "short", "xiaohongshu", False),
    ("https://www.bilibili.com/video/BV1xx411c7mD", "vip", "bilibili", False),
    ("https://b23.tv/abc", "vip", "bilibili", False),
    ("https://v.qq.com/x/cover/mzc00253a", "vip", "tencent", False),
    ("https://www.youku.com/v_show/id_XNj.html", "vip", "youku", False),
    ("https://www.iqiyi.com/v_19rro.html", "vip", "iqiyi", False),
    ("https://www.mgtv.com/b/123/456.html", "vip", "mgtv", False),
    ("https://example.com/video/1", "unknown", None, False),
    # SSRF 加固：平台域名出现在 query / fragment / 非 http scheme 中一律不识别
    ("http://169.254.169.254/latest/?x=https://v.qq.com/", "unknown", None, False),
    ("http://internal-host:8000/admin#https://youku.com", "unknown", None, False),
    ("ftp://v.qq.com/x", "unknown", None, False),
    ("not a url at all", "unknown", None, False),
    ("https://evil-douyin.com/video/1", "unknown", None, False),
    # 子域仍正常识别
    ("https://www.douyin.com/video/1", "short", "douyin", False),
]


@pytest.mark.parametrize("url,kind,platform,homepage", CASES)
def test_detect(url, kind, platform, homepage):
    d = detect(url)
    assert (d.kind, d.platform, d.is_homepage) == (kind, platform, homepage)
