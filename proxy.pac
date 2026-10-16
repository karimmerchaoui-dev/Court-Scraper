function FindProxyForURL(url, host) {
    // Send local traffic directly
    if (isPlainHostName(host) || shExpMatch(host, "localhost") || shExpMatch(host, "127.*")) {
        return "DIRECT";
    }

    // Send only specific sites through the proxy
    if (shExpMatch(host, "*.njcourts.gov") || shExpMatch(host, "ip.oxylabs.io")) {
        return "PROXY 127.0.0.1:8899";
    }

    // Everything else goes direct
    return "DIRECT";
}