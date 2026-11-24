import re
from plenty import site


def test_site_builds_and_links_resolve():
    site.main()
    pages = sorted(p.name for p in site.SITE.glob("*.html"))
    assert pages == ["capabilities.html", "gaps.html", "index.html", "method.html", "needs.html",
                     "sectors.html", "work.html"]
    for name in pages:
        text = (site.SITE / name).read_text()
        assert ">nan<" not in text and "nan%" not in text, name
        for href in re.findall(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"', text):
            if href.startswith(("http://", "https://")):
                continue
            assert (site.SITE / href).exists(), f"{name}: broken link {href}"
        # every in-page anchor used across pages exists on its target
        for target, anchor in re.findall(r'href="([a-z]+\.html)#([^"]+)"', text):
            assert f'id="{anchor}"' in (site.SITE / target).read_text(), f"{name}: {target}#{anchor}"
