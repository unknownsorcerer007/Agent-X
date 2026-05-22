"""
Agent-OS Security Scanner
Bug bounty tools: XSS scanner, SQL injection detector, sensitive data finder.
"""
import asyncio
import re
import logging
import urllib.parse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("agent-os.scanner")


@dataclass
class Vulnerability:
    """A found vulnerability."""
    type: str
    url: str
    parameter: str
    payload: str
    confidence: float  # 0-1
    evidence: str
    severity: str  # low, medium, high, critical


class XSSScanner:
    """Cross-Site Scripting (XSS) vulnerability scanner."""

    # XSS test payloads (safe, won't cause damage)
    PAYLOADS = [
        '<script>alert("XSS")</script>',
        '<img src=x onerror=alert("XSS")>',
        '"><script>alert("XSS")</script>',
        "'-alert('XSS')-'",
        '<svg onload=alert("XSS")>',
        'javascript:alert("XSS")',
        '<body onload=alert("XSS")>',
        '<iframe src="javascript:alert(1)">',
        '<details open ontoggle=alert("XSS")>',
        '<marquee onstart=alert("XSS")>',
        '"><img src=x onerror=alert(document.domain)>',
        "{{constructor.constructor('alert(1)')()}}",
    ]

    # Patterns that indicate XSS reflection
    REFLECTION_PATTERNS = [
        r'<script>alert\("XSS"\)</script>',
        r'onerror=alert\("XSS"\)',
        r'onload=alert\("XSS"\)',
        r'alert\(1\)',
        r'alert\(document\.domain\)',
    ]

    def __init__(self, browser):
        self.browser = browser
        self.vulnerabilities: List[Vulnerability] = []

    async def scan(self, url: str) -> Dict[str, Any]:
        """Scan a URL for XSS vulnerabilities."""
        logger.info(f"Starting XSS scan on {url}")
        self.vulnerabilities = []

        # Navigate to target
        result = await self.browser.navigate(url)
        if result.get("status") != "success":
            return {"status": "error", "error": f"Failed to navigate: {result.get('error')}"}

        # Get DOM snapshot to find input fields
        dom = await self.browser.get_dom_snapshot()  # noqa: F841
        content = await self.browser.get_content()  # noqa: F841

        # Find all forms and input fields
        _forms_resp = await self.browser.evaluate_js("""() => {
            const forms = [];
            document.querySelectorAll('form').forEach((form, i) => {
                const inputs = [];
                form.querySelectorAll('input, textarea').forEach(inp => {
                    inputs.push({
                        name: inp.name || inp.id || '',
                        type: inp.type || 'text',
                        id: inp.id || '',
                        placeholder: inp.placeholder || ''
                    });
                });
                forms.push({
                    action: form.action || window.location.href,
                    method: form.method || 'GET',
                    inputs: inputs
                });
            });
            return forms;
        }""")
        forms = _forms_resp.get("result") if isinstance(_forms_resp, dict) and _forms_resp.get("status") == "success" else _forms_resp

        # Test URL parameters
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        for param_name in params:
            vuln = await self._test_param_reflection(url, param_name)
            if vuln:
                self.vulnerabilities.append(vuln)

        # Test form inputs
        for form in (forms or []):
            for inp in form.get("inputs", []):
                if inp.get("name"):
                    vuln = await self._test_input_xss(url, form, inp)
                    if vuln:
                        self.vulnerabilities.append(vuln)

        return self._format_results()

    async def _test_param_reflection(self, url: str, param: str) -> Optional[Vulnerability]:
        """Test if a URL parameter reflects XSS payloads."""
        for payload in self.PAYLOADS[:5]:  # Test first 5 payloads
            test_url = self._inject_payload_url(url, param, payload)
            await self.browser.navigate(test_url)
            content = await self.browser.get_content()
            html = content.get("html", "")

            for pattern in self.REFLECTION_PATTERNS:
                if re.search(pattern, html, re.IGNORECASE):
                    return Vulnerability(
                        type="XSS",
                        url=url,
                        parameter=param,
                        payload=payload,
                        confidence=0.85,
                        evidence=f"Payload reflected in response: {pattern}",
                        severity="high"
                    )
        return None

    async def _test_input_xss(self, url: str, form: dict, input_field: dict) -> Optional[Vulnerability]:
        """Test a form input for XSS."""
        selector = f'input[name="{input_field["name"]}"]'
        for payload in self.PAYLOADS[:3]:
            await self.browser.navigate(url)
            await self.browser.fill_form({selector: payload})

            # Try to submit form
            submit_result = await self.browser.click('button[type="submit"]')
            if submit_result.get("status") != "success":
                await self.browser.click('input[type="submit"]')

            content = await self.browser.get_content()
            html = content.get("html", "")

            for pattern in self.REFLECTION_PATTERNS:
                if re.search(pattern, html, re.IGNORECASE):
                    return Vulnerability(
                        type="XSS",
                        url=url,
                        parameter=input_field.get("name", "unknown"),
                        payload=payload,
                        confidence=0.9,
                        evidence=f"Form input payload reflected: {pattern}",
                        severity="high"
                    )
        return None

    def _inject_payload_url(self, url: str, param: str, payload: str) -> str:
        """Inject XSS payload into URL parameter."""
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        params[param] = [payload]
        new_query = urllib.parse.urlencode(params, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))

    def _format_results(self) -> Dict:
        """Format scan results."""
        return {
            "status": "success",
            "scanner": "xss",
            "vulnerabilities_found": len(self.vulnerabilities),
            "vulnerabilities": [
                {
                    "type": v.type,
                    "url": v.url,
                    "parameter": v.parameter,
                    "payload": v.payload,
                    "confidence": v.confidence,
                    "evidence": v.evidence,
                    "severity": v.severity,
                }
                for v in self.vulnerabilities
            ]
        }


class SQLiScanner:
    """SQL Injection vulnerability scanner."""

    # SQL injection test payloads
    PAYLOADS = [
        "'",
        "''",
        "' OR '1'='1",
        "' OR '1'='1' --",
        "' OR '1'='1' /*",
        "1' ORDER BY 1--",
        "1' ORDER BY 10--",
        "' UNION SELECT NULL--",
        "1; DROP TABLE test--",
        "' AND SLEEP(5)--",
    ]

    # SQL error patterns in responses
    ERROR_PATTERNS = [
        r"SQL syntax.*MySQL",
        r"Warning.*mysql_",
        r"MySQLSyntaxErrorException",
        r"valid MySQL result",
        r"check the manual that corresponds to your MySQL server version",
        r"PostgreSQL.*ERROR",
        r"Warning.*pg_",
        r"valid PostgreSQL result",
        r"Npgsql\.",
        r"Driver.*SQL[\-\_\ ]*Server",
        r"OLE DB.*SQL Server",
        r"SQLServer JDBC Driver",
        r"SqlClient",
        r"SQL Server.*Driver",
        r"Warning.*mssql_",
        r"Unclosed quotation mark after the character string",
        r"SQLITE_ERROR",
        r"SQLite/JDBCDriver",
        r"SQLite\.Exception",
        r"System\.Data\.SQLite\.SQLiteException",
        r"Warning.*sqlite_",
        r"Warning.*SQLite3::",
        r"SQLite3::query",
        r"ORA-\d{5}",
        r"Oracle error",
        r"Oracle.*Driver",
        r"Warning.*oci_",
        r"quoted string not properly terminated",
    ]

    def __init__(self, browser):
        self.browser = browser
        self.vulnerabilities: List[Vulnerability] = []

    async def scan(self, url: str) -> Dict[str, Any]:
        """Scan a URL for SQL injection vulnerabilities."""
        logger.info(f"Starting SQLi scan on {url}")
        self.vulnerabilities = []

        # Test URL parameters
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        for param_name in params:
            vuln = await self._test_sqli_param(url, param_name)
            if vuln:
                self.vulnerabilities.append(vuln)

        # Test forms
        await self.browser.navigate(url)
        _forms_resp = await self.browser.evaluate_js("""() => {
            const forms = [];
            document.querySelectorAll('form').forEach((form, i) => {
                const inputs = [];
                form.querySelectorAll('input, textarea').forEach(inp => {
                    if (inp.type === 'hidden' || inp.type === 'submit') return;
                    inputs.push({
                        name: inp.name || inp.id || '',
                        type: inp.type || 'text',
                        id: inp.id || '',
                        selector: inp.id ? '#' + inp.id : (inp.name ? 'input[name="' + inp.name + '"]' : '')
                    });
                });
                if (inputs.length > 0) {
                    forms.push({
                        action: form.action || window.location.href,
                        method: form.method || 'GET',
                        inputs: inputs,
                        submit_selector: 'button[type="submit"], input[type="submit"]'
                    });
                }
            });
            return forms;
        }""")
        forms = _forms_resp.get("result") if isinstance(_forms_resp, dict) and _forms_resp.get("status") == "success" else _forms_resp

        for form in (forms or []):
            for inp in form.get("inputs", []):
                selector = inp.get("selector")
                if not selector:
                    continue
                vuln = await self._test_sqli_input(url, form, inp)
                if vuln:
                    self.vulnerabilities.append(vuln)

        return self._format_results()

    async def _test_sqli_input(self, url: str, form: dict, input_field: dict) -> Optional[Vulnerability]:
        """Test a form input for SQL injection."""
        selector = input_field.get("selector")
        if not selector:
            return None

        for payload in self.PAYLOADS:
            try:
                await self.browser.navigate(url)
                await self.browser.fill_form({selector: payload})

                # Try to submit
                submit_sel = form.get("submit_selector", 'button[type="submit"]')
                await self.browser.click(submit_sel)

                await asyncio.sleep(1)
                content = await self.browser.get_content()
                html = content.get("html", "")

                for pattern in self.ERROR_PATTERNS:
                    if re.search(pattern, html, re.IGNORECASE):
                        return Vulnerability(
                            type="SQLi",
                            url=url,
                            parameter=input_field.get("name", "unknown"),
                            payload=payload,
                            confidence=0.85,
                            evidence=f"SQL error in form response: {pattern[:60]}",
                            severity="critical"
                        )
            except Exception:
                continue

        return None

    async def _test_sqli_param(self, url: str, param: str) -> Optional[Vulnerability]:
        """Test a URL parameter for SQL injection."""
        for payload in self.PAYLOADS:
            test_url = self._inject_sqli_url(url, param, payload)
            result = await self.browser.navigate(test_url)
            content = await self.browser.get_content()
            html = content.get("html", "")

            # Check for SQL error patterns
            for pattern in self.ERROR_PATTERNS:
                if re.search(pattern, html, re.IGNORECASE):
                    return Vulnerability(
                        type="SQLi",
                        url=url,
                        parameter=param,
                        payload=payload,
                        confidence=0.8,
                        evidence=f"SQL error detected: {pattern[:60]}",
                        severity="critical"
                    )

            # Check for time-based blind SQLi (if SLEEP payload was used)
            if "SLEEP" in payload and result.get("status") == "success":
                # Time-based blind SQLi: if SLEEP(5) caused a delay > 4s,
                # the server likely executed the SQL SLEEP command.
                # We check the elapsed time from the navigation result.
                elapsed = result.get("duration_ms", 0)
                if elapsed > 4000:
                    return Vulnerability(
                        type="SQLi",
                        url=url,
                        parameter=param,
                        payload=payload,
                        confidence=0.7,
                        evidence=f"Time-based blind SQLi: SLEEP caused {elapsed:.0f}ms delay",
                        severity="high"
                    )

        return None

    def _inject_sqli_url(self, url: str, param: str, payload: str) -> str:
        """Inject SQLi payload into URL parameter."""
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        params[param] = [payload]
        new_query = urllib.parse.urlencode(params, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query))

    def _format_results(self) -> Dict:
        return {
            "status": "success",
            "scanner": "sqli",
            "vulnerabilities_found": len(self.vulnerabilities),
            "vulnerabilities": [
                {
                    "type": v.type,
                    "url": v.url,
                    "parameter": v.parameter,
                    "payload": v.payload,
                    "confidence": v.confidence,
                    "evidence": v.evidence,
                    "severity": v.severity,
                }
                for v in self.vulnerabilities
            ]
        }


class SensitiveDataScanner:
    """Scans for exposed sensitive data (API keys, tokens, etc.)."""

    PATTERNS = {
        "AWS Key": r"AKIA[0-9A-Z]{16}",
        "GitHub Token": r"ghp_[a-zA-Z0-9]{36}",
        "Generic API Key": r"['\"]?(api[_-]?key|apikey)['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9]{20,}['\"]?",
        "Private Key": r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----",
        "JWT Token": r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*",
        "Password in URL": r"://[^:]+:[^@]+@",
        "Email Address": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "IP Address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        "Internal IP": r"\b(10|172\.(1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b",
    }

    async def scan_page(self, browser) -> Dict:
        """Scan current page for sensitive data."""
        content = await browser.get_content()
        html = content.get("html", "")
        text = content.get("text", "")

        findings = []
        for data_type, pattern in self.PATTERNS.items():
            matches = re.findall(pattern, html + text)
            if matches:
                findings.append({
                    "type": data_type,
                    "count": len(matches),
                    # Don't expose actual values, just first few chars
                    "samples": [m[:10] + "..." if len(str(m)) > 10 else m for m in matches[:3]]
                })

        return {
            "status": "success",
            "findings": findings,
            "total_issues": len(findings)
        }
