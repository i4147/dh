import re
import subprocess
from io import BytesIO

try:
    import pycurl
except ImportError:
    pycurl = None


class CurlHeader:
    def __init__(self) -> None:
        self._buf = BytesIO()

    def write(self, buff: (bytes | str)) -> int:
        if isinstance(buff, str):
            buff = buff.encode("utf-8")
        self._buf.write(buff)
        return len(buff)

    def setvalue_from_file(self, in_filename: str) -> None:
        self._buf = BytesIO()
        with open(in_filename, encoding="utf-8") as f:
            for line in f:
                self.write(line.strip() + "\r\n")

    def getvalue(self) -> str:
        return self._buf.getvalue().decode("utf-8", errors="replace")

    def __str__(self) -> str:
        return self.getvalue()


class GetURL:
    def __init__(self) -> None:
        self.header_buffer = CurlHeader()
        self.insecure = False
        self.http_proxy: str | None = None

    def get_content_length(self, hdr: (str | CurlHeader)) -> int | None:
        text = hdr.getvalue() if isinstance(hdr, CurlHeader) else hdr
        m = re.search("^Content-Length:\\s*(\\d+)", text, re.IGNORECASE | re.MULTILINE)
        return int(m.group(1)) if m else None

    def set_insecure(self, bool_value: bool = True) -> None:
        self.insecure = bool_value

    def set_proxy(self, http_proxy: str) -> None:
        self.http_proxy = http_proxy

    def get_status_code(self, status_line: str) -> int | None:
        if not status_line:
            return None
        m = re.match("HTTP/\\d\\.\\d\\s+(\\d{3})", status_line)
        return int(m.group(1)) if m else None

    def get(self, *args, **kwargs) -> bytes:
        raise NotImplementedError

    def post(self, *args, **kwargs) -> bytes:
        raise NotImplementedError


class GetURLpyCurl(GetURL):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def is_available() -> bool:
        return pycurl is not None

    def get(self, url: str, headers: (dict[str, str] | None) = None, **kwargs) -> bytes:
        return self._fetch(url, method="GET", headers=headers, data=None, **kwargs)

    def post(
        self,
        url: str,
        data: (bytes | str | None) = None,
        headers: (dict[str, str] | None) = None,
        **kwargs,
    ) -> bytes:
        return self._fetch(url, method="POST", headers=headers, data=data, **kwargs)

    def _fetch(
        self,
        url: str,
        method: str = "GET",
        headers: (dict[str, str] | None) = None,
        data: (bytes | str | None) = None,
        **kwargs,
    ) -> bytes:
        if self.is_available():
            return self._fetch_pycurl(url, method, headers, data, **kwargs)
        return self._fetch_subprocess(url, method, headers, data)

    def _fetch_pycurl(
        self,
        url: str,
        method: str,
        headers: (dict[str, str] | None),
        data: (bytes | str | None),
        **kwargs,
    ) -> bytes:
        body_buffer = BytesIO()
        self.header_buffer = CurlHeader()
        c = pycurl.Curl()
        try:
            c.setopt(pycurl.URL, url)
            c.setopt(pycurl.WRITEDATA, body_buffer)
            c.setopt(pycurl.HEADERFUNCTION, self.header_buffer.write)
            if method == "POST":
                c.setopt(pycurl.POST, 1)
                if data is not None:
                    c.setopt(pycurl.POSTFIELDS, data)
            else:
                c.setopt(pycurl.HTTPGET, 1)
            if self.insecure:
                c.setopt(pycurl.SSL_VERIFYPEER, 0)
                c.setopt(pycurl.SSL_VERIFYHOST, 0)
            if self.http_proxy:
                c.setopt(pycurl.PROXY, self.http_proxy)
            if headers:
                curl_headers = [f"{k}: {v}" for k, v in headers.items()]
                c.setopt(pycurl.HTTPHEADER, curl_headers)
            for opt_name, opt_val in kwargs.items():
                opt_const = getattr(pycurl, opt_name, None)
                if opt_const is not None:
                    c.setopt(opt_const, opt_val)
            c.perform()
        finally:
            c.close()
        return body_buffer.getvalue()

    def _fetch_subprocess(
        self,
        url: str,
        method: str,
        headers: (dict[str, str] | None),
        data: (bytes | str | None),
    ) -> bytes:
        cmd = ["curl", "-sS", "-L", "--fail", "-i"]
        if self.insecure:
            cmd.append("--insecure")
        if self.http_proxy:
            cmd.extend(["--proxy", self.http_proxy])
        if method == "POST":
            cmd.extend(["-X", "POST"])
            if data is not None:
                cmd.extend(
                    ["--data", data if isinstance(data, str) else data.decode("utf-8")]
                )
        if headers:
            for k, v in headers.items():
                cmd.extend(["-H", f"{k}: {v}"])
        cmd.append(url)
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        if proc.returncode != 0:
            msg = f"curl failed with code {proc.returncode}: {proc.stderr.decode('utf-8', errors='replace')}"
            raise RuntimeError(msg)
        raw = proc.stdout
        header_end = raw.find(b"\r\n\r\n")
        if header_end == -1:
            header_end = raw.find(b"\n\n")
        if header_end == -1:
            msg = "Could not separate headers from body"
            raise ValueError(msg)
        header_part = raw[:header_end]
        body = raw[
            header_end
            + len(b"\r\n\r\n" if b"\r\n\r\n" in raw[: header_end + 4] else b"\n\n") :
        ]
        self.header_buffer = CurlHeader()
        for line in header_part.splitlines():
            self.header_buffer.write(line + b"\r\n")
        return body


def cdownload(url: str, **kwargs) -> bytes:
    downloader = GetURLpyCurl()
    return downloader.get(url, **kwargs)
