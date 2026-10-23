"""Validate QQ image references and shrink one frame before local inference."""

import base64
import io
import warnings
from urllib.parse import urlparse

import aiohttp
from PIL import Image, ImageOps

LIMIT = 12 * 1024 * 1024


def allowed_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme in {"http", "https"}
        and not parsed.username
        and not parsed.password
        and parsed.port in {None, 80, 443}
        and (
            host == "qpic.cn"
            or host.endswith(".qpic.cn")
            or host == "multimedia.nt.qq.com"
            or host == "multimedia.nt.qq.com.cn"
        )
    )


def normalize(payload):
    if len(payload) > LIMIT:
        raise ValueError("图片太大，发一张小于12MB的图吧")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(payload)) as original:
            if original.width * original.height > 16000000:
                raise ValueError("图片分辨率过大，缩小后再发吧")
            original.seek(0)
            picture = ImageOps.exif_transpose(original).convert("RGB")
            picture.thumbnail((448, 448))
            output = io.BytesIO()
            picture.save(output, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode(
        "ascii"
    )


async def prepare(reference):
    if reference.startswith("base64://"):
        encoded = reference[9:]
        if len(encoded) > LIMIT * 4 // 3 + 8:
            raise ValueError("图片太大，缩小后再发吧")
        payload = base64.b64decode(encoded, validate=True)
    else:
        url = reference
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            for _ in range(4):
                if not allowed_url(url):
                    raise ValueError("这张图片地址不可用，请直接重新发图")
                async with session.get(url, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        from urllib.parse import urljoin

                        url = urljoin(url, response.headers.get("Location", ""))
                        continue
                    response.raise_for_status()
                    if response.content_length and response.content_length > LIMIT:
                        raise ValueError("图片太大，缩小后再发吧")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > LIMIT:
                            raise ValueError("图片太大，缩小后再发吧")
                        chunks.append(chunk)
                    payload = b"".join(chunks)
                    break
            else:
                raise ValueError("图片跳转过多，请重新发图")
    return normalize(payload)
