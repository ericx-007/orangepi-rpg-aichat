"""Owner-private controls and bounded retrieval from public search pages."""

import asyncio
import ipaddress
import json
import re
import socket
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from bs4 import BeautifulSoup

from .policy import OWNER

COMMANDS = {"开启联网": "on", "关闭联网": "off", "联网状态": "status"}
BEIJING = timezone(timedelta(hours=8))


def query_from(text):
    """Parse only an explicit search prefix, returning None for ordinary chat.

    Args:
        text: The current message text without mention segments.

    Returns:
        Search text, an empty string for a bare prefix, or None for normal chat.
    """
    match = re.fullmatch(
        r"(?:搜一下|搜索|查一下|联网搜索)[\s:：]*(.*)", text.strip(), re.S
    )
    return match.group(1).strip() if match else None


def public_url(url):
    """Validate a public HTTP target before DNS and each redirect.

    Args:
        url: Search result or redirect target.

    Returns:
        Whether the URL has a supported scheme, public host and ordinary port.
    """
    try:
        value = urlsplit(url)
        host = (value.hostname or "").lower()
        if len(url) > 350 or value.scheme not in {"http", "https"} or not host:
            return False
        if value.username or value.password or value.port not in {None, 80, 443}:
            return False
        if (
            host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
            or "." not in host
        ):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


class PublicResolver(aiohttp.resolver.ThreadedResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        """Reject private DNS answers rather than fetching local services.

        Args:
            host: DNS hostname to resolve.
            port: Destination port.
            family: Address family requested by aiohttp.

        Returns:
            Resolver records containing only global IP addresses.

        Raises:
            OSError: A hostname resolves to a non-public address.
        """
        records = await super().resolve(host, port, family)
        if not records or any(
            not ipaddress.ip_address(item["host"]).is_global for item in records
        ):
            raise OSError("Non-public DNS target")
        return records


class WebSearch:
    def __init__(self, state_path, clock=time.time):
        self.path = Path(state_path)
        self.clock = clock
        self.lock = asyncio.Lock()
        self.state = {
            "enabled": True,
            "date": "",
            "count": 0,
            "control_seen": [],
            "control_times": [],
        }
        if self.path.exists():
            self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
        self.save()

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    def control(self, text, *, sender, group, private, message_id):
        """Apply exact controls only in the authenticated owner's private chat.

        Args:
            text: Exact command text.
            sender: QQ sender ID taken from the actual event.
            group: Group ID, empty for private messages.
            private: Whether the platform classified this as a private message.
            message_id: Actual incoming message ID for replay protection.

        Returns:
            A confirmation, or None for duplicate/rate-limited controls.
        """
        if str(sender) != OWNER or group or not private:
            return "联网开关只接受主号私聊指令"
        action = COMMANDS.get(text)
        if action is None:
            return None
        identity = str(message_id)
        if identity and identity in self.state["control_seen"]:
            return None
        now = self.clock()
        recent = [t for t in self.state["control_times"] if now - t < 60]
        if len(recent) >= 6:
            return None
        recent.append(now)
        self.state["control_times"] = recent
        if identity:
            self.state["control_seen"] = (self.state["control_seen"] + [identity])[
                -256:
            ]
        if action != "status":
            self.state["enabled"] = action == "on"
        self.save()
        if action == "on":
            return "联网已开启，发“搜一下 内容”就能查；群里记得@我"
        if action == "off":
            return "联网已关闭，普通聊天照常"
        date = datetime.fromtimestamp(now, BEIJING).date().isoformat()
        count = self.state["count"] if self.state["date"] == date else 0
        return f"联网：{'开启' if self.state['enabled'] else '关闭'}；今天已搜索{count}/30次。发“搜一下 内容”触发"

    async def read_url(self, session, url, limit=500000):
        """Fetch a bounded public document with validated manual redirects.

        Args:
            session: HTTP session using PublicResolver and no local proxy.
            url: Public destination URL.
            limit: Maximum decompressed response bytes.

        Returns:
            Response bytes, content type and final URL.

        Raises:
            ValueError: The URL, response type, status or size is unsupported.
        """
        from urllib.parse import urljoin

        for _ in range(4):
            if not public_url(url):
                raise ValueError("Non-public URL")
            async with session.get(url, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                if response.status != 200:
                    raise ValueError("Page unavailable")
                kind = response.headers.get("Content-Type", "").lower()
                if not any(t in kind for t in ["html", "xml", "text/plain"]):
                    raise ValueError("Unsupported document")
                parts = []
                size = 0
                async for chunk in response.content.iter_chunked(32768):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Page too large")
                    parts.append(chunk)
                return b"".join(parts), kind, url
        raise ValueError("Too many redirects")

    async def retrieve(self, query):
        """Search, read source bodies and return a small evidence packet.

        Args:
            query: Only the explicitly requested search query, without history.

        Returns:
            A status and at most two body excerpts, or a user-facing failure.
        """
        if not self.state["enabled"]:
            return {
                "status": "disabled",
                "message": "联网没开，让主号私聊我发“开启联网”",
            }
        if not query or len(query) > 200:
            return {
                "status": "invalid_query",
                "message": "发“搜一下 内容”就行，内容控制在200字以内",
            }
        if self.lock.locked():
            return {"status": "busy", "message": "还有一条搜索在路上，稍等一下"}
        async with self.lock:
            date = datetime.fromtimestamp(self.clock(), BEIJING).date().isoformat()
            if self.state["date"] != date:
                self.state.update(date=date, count=0)
            if self.state["count"] >= 30:
                return {
                    "status": "daily_limit",
                    "message": "今天的30次搜索用完了，明天再查",
                }
            self.state["count"] += 1
            self.save()
            started = time.monotonic()
            try:
                async with asyncio.timeout(24):
                    connector = aiohttp.TCPConnector(resolver=PublicResolver(), limit=4)
                    async with aiohttp.ClientSession(
                        connector=connector,
                        trust_env=False,
                        timeout=aiohttp.ClientTimeout(total=8),
                        headers={
                            "User-Agent": "Mozilla/5.0 (compatible; LittleWhale/1.0)"
                        },
                    ) as session:
                        from urllib.parse import urlencode

                        raw, _, _ = await self.read_url(
                            session,
                            "https://www.bing.com/search?"
                            + urlencode({"q": query, "format": "rss"}),
                        )
                        root = ET.fromstring(raw)
                        candidates = []
                        for item in root.findall(".//item"):
                            url = item.findtext("link") or ""
                            if public_url(url) and url not in [
                                c["url"] for c in candidates
                            ]:
                                candidates.append(
                                    {
                                        "url": url,
                                        "title": (item.findtext("title") or "")[:100],
                                    }
                                )
                        if not candidates:
                            return {
                                "status": "no_results",
                                "message": "这次没搜到可用结果，换个关键词试试",
                            }
                        # Parallel page reads keep latency bounded; only full
                        # body excerpts are passed on, never snippets as bodies.
                        pages = await asyncio.gather(
                            *(self.read_url(session, c["url"]) for c in candidates[:6]),
                            return_exceptions=True,
                        )
                        sources = []
                        tokens = re.findall(r"[a-z0-9.]{2,}", query.lower())
                        chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", query))
                        tokens += [
                            chinese[i : i + 2] for i in range(max(0, len(chinese) - 1))
                        ]
                        for candidate, page in zip(candidates, pages):
                            if isinstance(page, BaseException):
                                continue
                            body, _, final_url = page
                            soup = BeautifulSoup(body, "html.parser")
                            for node in soup(
                                [
                                    "script",
                                    "style",
                                    "nav",
                                    "footer",
                                    "header",
                                    "aside",
                                    "form",
                                    "noscript",
                                ]
                            ):
                                node.decompose()
                            main = (
                                soup.find("article")
                                or soup.find("main")
                                or soup.body
                                or soup
                            )
                            blocks = [
                                n.get_text(" ", strip=True)
                                for n in main.find_all(
                                    ["p", "h1", "h2", "h3", "li", "tr", "dd"]
                                )
                            ]
                            blocks = [
                                re.sub(r"\s+", " ", t) for t in blocks if len(t) > 25
                            ]
                            if not blocks:
                                blocks = [main.get_text(" ", strip=True)]
                            scores = []
                            for index, block in enumerate(blocks):
                                score = 0
                                for token in tokens:
                                    if any(c.isdigit() for c in token):
                                        if re.search(
                                            r"(?<![\d.])"
                                            + re.escape(token)
                                            + r"(?!\d)",
                                            block.lower(),
                                        ):
                                            score += 8
                                    elif token in block.lower():
                                        score += 1
                                scores.append((index, block, score))
                            ranked = [
                                (i, t)
                                for i, t, _ in sorted(
                                    scores, key=lambda item: (-item[2], item[0])
                                )[:3]
                            ]
                            excerpt = " ".join(t for _, t in sorted(ranked))[:650]
                            if len(excerpt) < 60:
                                continue
                            sources.append(
                                {
                                    "title": candidate["title"],
                                    "url": final_url,
                                    "body": excerpt,
                                }
                            )
                            if len(sources) == 2:
                                break
                        if not sources:
                            return {
                                "status": "no_readable_pages",
                                "message": "搜到链接了，但正文没读下来，这次先不瞎猜",
                            }
                        if not self.state["enabled"]:
                            return {
                                "status": "disabled",
                                "message": "联网已关闭，这次搜索不继续回答",
                            }
                        return {
                            "status": "ok",
                            "provider": "Bing public search",
                            "checked_at": datetime.fromtimestamp(
                                self.clock(), BEIJING
                            ).isoformat(),
                            "seconds": round(time.monotonic() - started, 3),
                            "sources": sources,
                        }
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                OSError,
                ValueError,
                ET.ParseError,
            ):
                return {
                    "status": "unavailable",
                    "message": "这次联网搜索没成功，可能超时或被限制了，先不拿记忆冒充搜索结果",
                }
