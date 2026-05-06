"""Browser fetch backend scaffold for webpage_extraction."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from tokenbank.backends.adapter import BackendExecutionContext, build_result_envelope
from tokenbank.backends.errors import normalize_backend_error
from tokenbank.backends.local_tool import _extract_url
from tokenbank.backends.usage import make_usage_record
from tokenbank.core.canonical import canonical_url
from tokenbank.models.result_envelope import WorkUnitResultEnvelope


class BrowserFetchAdapter:
    backend_class = "browser_fetch"

    def execute(self, context: BackendExecutionContext) -> WorkUnitResultEnvelope:
        started_at = datetime.now(UTC)
        usage = [
            make_usage_record(
                work_unit_id=context.work_unit_id,
                attempt_id=context.attempt_id,
                backend_id=context.backend_id,
                cost_source="zero_internal_phase0",
                cost_confidence="medium",
            )
        ]
        url = _extract_url(context.input_payload, context.effective_constraints)
        error = self._policy_error(context, url)
        if error is not None:
            return build_result_envelope(
                context=context,
                output={"ok": False, "reason": error.error_code},
                usage_records=usage,
                started_at=started_at,
                status="failed",
                errors=[error],
                redacted_logs=["browser_fetch denied by egress policy"],
            )

        normalized = canonical_url(url or "")
        extraction = _extract_webpage_payload(context.input_payload, normalized)
        return build_result_envelope(
            context=context,
            output={
                "ok": True,
                "tool": "webpage_extraction",
                "url": normalized,
                "extracted": extraction.extracted,
                "prompt_injection_detected": extraction.prompt_injection_detected,
                "fetched": False,
                "untrusted_content": True,
                "browser_fetch_scaffold": True,
            },
            usage_records=usage,
            started_at=started_at,
            redacted_logs=["browser_fetch scaffold produced untrusted content tag"],
        )

    def _policy_error(
        self,
        context: BackendExecutionContext,
        url: str | None,
    ):
        if not url:
            return normalize_backend_error(
                error_code="browser_fetch.bad_input",
                error_message="browser_fetch requires an explicit URL",
                retryable=False,
                fallbackable=False,
            )
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return normalize_backend_error(
                error_code="browser_fetch.bad_input",
                error_message="browser_fetch requires http or https URL",
                retryable=False,
                fallbackable=False,
            )
        if _is_private_or_local_host(parsed.hostname or ""):
            return normalize_backend_error(
                error_code="browser_fetch.private_ip_denied",
                error_message="browser_fetch denied private or local host",
                retryable=False,
                fallbackable=True,
                details={"host": parsed.hostname},
            )
        redirect_url = context.input_payload.get("redirect_url")
        if isinstance(redirect_url, str) and redirect_url != url:
            return normalize_backend_error(
                error_code="browser_fetch.redirect_denied",
                error_message="browser_fetch denied redirect in P0 scaffold",
                retryable=False,
                fallbackable=True,
                details={"redirect_host": urlsplit(redirect_url).hostname},
            )
        return None


def _is_private_or_local_host(host: str) -> bool:
    normalized = host.lower()
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    )


class _StaticHtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)


class _ExtractionResult:
    def __init__(
        self,
        *,
        extracted: dict[str, str | bool],
        prompt_injection_detected: bool,
    ) -> None:
        self.extracted = extracted
        self.prompt_injection_detected = prompt_injection_detected


def _extract_webpage_payload(
    payload: dict,
    normalized_url: str,
) -> _ExtractionResult:
    html = payload.get("html")
    text = payload.get("text")
    title = payload.get("title")
    source = html if isinstance(html, str) else text if isinstance(text, str) else ""
    extracted: dict[str, str | bool] = {
        "url": normalized_url,
        "source": "explicit_static_input",
        "untrusted_content": True,
    }

    if isinstance(html, str) and html:
        parser = _StaticHtmlExtractor()
        parser.feed(html)
        parsed_title = " ".join(parser.title_parts).strip()
        parsed_text = " ".join(parser.text_parts).strip()
        if parsed_title:
            extracted["title"] = parsed_title
        if parsed_text:
            extracted["text_preview"] = parsed_text[:500]
        source = html
    elif isinstance(text, str) and text:
        extracted["text_preview"] = " ".join(text.split())[:500]
    if isinstance(title, str) and title:
        extracted["title"] = " ".join(title.split())[:200]

    prompt_injection_detected = _contains_prompt_injection(source)
    return _ExtractionResult(
        extracted=extracted,
        prompt_injection_detected=prompt_injection_detected,
    )


def _contains_prompt_injection(value: str) -> bool:
    lowered = value.lower()
    markers = (
        "ignore previous instructions",
        "ignore all previous instructions",
        "system prompt",
        "developer message",
        "reveal your instructions",
    )
    return any(marker in lowered for marker in markers)
