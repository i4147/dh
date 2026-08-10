import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse


def get_sha256(path: str | Path, chunk_size: int = 524288) -> str:
    from hashlib import sha256

    path = Path(path)
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()



def is_valid_url(url: str) -> bool:
    """
    Validate a URL string.
    
    Returns True if the URL is valid, False otherwise.
    Considers URLs with template placeholders (${...}), backticks,
    incomplete hosts, and invalid IPv6 addresses as invalid.
    """
    if not isinstance(url, str) or not url.strip():
        return False
    
    url = url.strip()
    
    # Reject URLs containing template placeholders like ${key}
    if '${' in url or '}' in url:
        return False
    
    # Reject URLs containing backticks
    if '`' in url:
        return False
    
    # Must have a scheme
    if '://' not in url:
        return False
    
    # Parse the URL
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    
    # Scheme must be http or https (or other valid schemes)
    if parsed.scheme not in ('http', 'https', 'ftp', 'ftps'):
        return False
    
    # Host must be present
    if not parsed.hostname:
        return False
    
    # Validate hostname
    hostname = parsed.hostname
    
    # Check for invalid characters in hostname
    if re.search(r'[^a-zA-Z0-9.\-\[\]:]', hostname):
        return False
    
    # Handle IPv6 addresses
    if ':' in hostname and not hostname.startswith('['):
        # Bare IPv6 without brackets is invalid in URLs
        return False
    
    if hostname.startswith('['):
        # Extract IPv6 address
        ipv6_match = re.match(r'\[([^\]]+)\]', hostname)
        if not ipv6_match:
            return False
        ipv6_addr = ipv6_match.group(1)
        try:
            ipaddress.IPv6Address(ipv6_addr)
        except ValueError:
            return False
    
    # Validate regular hostnames
    if not hostname.startswith('['):
        # Must be a valid hostname or IP
        if not is_valid_hostname(hostname):
            return False
    
    # Validate port if present
    if parsed.port is not None:
        if not (0 < parsed.port < 65536):
            return False
    
    return True

def is_valid_hostname(hostname: str) -> bool:
    """
    Validate a hostname (not IPv6).
    """
    # Localhost is valid
    if hostname == 'localhost':
        return True
    
    # Try IPv4
    try:
        ipaddress.IPv4Address(hostname)
        return True
    except ValueError:
        pass
    
    # Hostname rules: labels of alphanumeric and hyphens, 
    # not starting or ending with hyphen, max 63 chars per label
    if len(hostname) > 253:
        return False
    
    labels = hostname.split('.')
    for label in labels:
        if not label or len(label) > 63:
            return False
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?$', label):
            return False
    
    return True

