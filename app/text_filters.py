import re

from markupsafe import Markup, escape


_ALLOWED_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|[a-zA-Z][a-zA-Z0-9_-]{0,30})$")
_ALLOWED_SIZE_RE = re.compile(r"^(small|normal|large|x-large|xx-large|[8-9]px|[1-2][0-9]px|3[0-2]px|0\.[8-9]em|1(?:\.[0-9])?em|2(?:\.0)?em)$", re.IGNORECASE)
_URL_RE = re.compile(r"(https?://[^\s<]+)", re.IGNORECASE)


def _split_trailing_url_punctuation(raw_url):
    trailing = ""
    while raw_url and raw_url[-1] in ".,;:!?)]}":
        trailing = raw_url[-1] + trailing
        raw_url = raw_url[:-1]
    return raw_url, trailing


def linkify_text(value):
    """Render plain text safely and turn detected http(s) URLs into links.

    Used for workflow step descriptions in the incident page: the surrounding
    workflow card remains clickable, while links embedded in the text can be
    opened independently. Newlines are preserved as HTML line breaks.
    """
    text_value = "" if value is None else str(value)
    parts = []
    last = 0
    for match in _URL_RE.finditer(text_value):
        parts.append(escape(text_value[last:match.start()]))
        raw_url, trailing = _split_trailing_url_punctuation(match.group(1))
        safe_url = escape(raw_url)
        parts.append(
            Markup(
                '<a class="inline-url" href="{0}" target="_blank" '
                'rel="noopener noreferrer">{0}</a>'
            ).format(safe_url)
        )
        if trailing:
            parts.append(escape(trailing))
        last = match.end()
    parts.append(escape(text_value[last:]))
    return Markup("").join(parts).replace("\n", Markup("<br>"))


def _apply_inline_markdown(text):
    """Apply a deliberately small, safe subset of Markdown to escaped text."""
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f"<code>{m.group(1)}</code>",
        text,
    )
    text = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
        lambda m: (
            f'<a class="inline-url" href="{m.group(2)}" target="_blank" '
            f'rel="noopener noreferrer">{m.group(1)}</a>'
        ),
        text,
    )
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", text)

    def color_repl(match):
        color = match.group(1).strip()
        body = match.group(2)
        if not _ALLOWED_COLOR_RE.match(color):
            return body
        return f'<span class="workflow-markdown-color" style="color: {color};">{body}</span>'

    def size_repl(match):
        size = match.group(1).strip().lower()
        body = match.group(2)
        if not _ALLOWED_SIZE_RE.match(size):
            return body
        return f'<span class="workflow-markdown-size" style="font-size: {size};">{body}</span>'

    text = re.sub(r"\{color:([^}]+)\}(.+?)\{/color\}", color_repl, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\{size:([^}]+)\}(.+?)\{/size\}", size_repl, text, flags=re.IGNORECASE | re.DOTALL)
    return text



def _auto_link_escaped_html(text):
    """Link raw http(s) URLs in already escaped/generated inline HTML."""
    def repl(match):
        raw_url, trailing = _split_trailing_url_punctuation(match.group(1))
        return (
            f'<a class="inline-url" href="{raw_url}" target="_blank" '
            f'rel="noopener noreferrer">{raw_url}</a>{trailing}'
        )
    return re.sub(r'(?<!href=")\b(https?://[^\s<]+)', repl, text, flags=re.IGNORECASE)


def _render_workflow_inline(raw_text):
    return _auto_link_escaped_html(_apply_inline_markdown(str(escape(raw_text))))

def workflow_markdown(value):
    """Render workflow step descriptions with safe Markdown and controlled colors.

    Supported syntax is intentionally limited to headings, unordered/ordered
    lists, bold, italic, inline code, Markdown links, auto-linked http(s) URLs,
    color spans using {color:red}text{/color} or {color:#c00}text{/color}
    and size spans using {size:large}text{/size} or {size:14px}text{/size}.
    Raw HTML is escaped.
    """
    raw = "" if value is None else str(value)
    lines = raw.splitlines()
    html = []
    list_mode = None

    def close_list():
        nonlocal list_mode
        if list_mode:
            html.append(f"</{list_mode}>")
            list_mode = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            close_list()
            continue

        escaped = _render_workflow_inline(stripped)

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if heading:
            close_list()
            level = min(len(heading.group(1)) + 2, 6)
            body = _render_workflow_inline(heading.group(2).strip())
            html.append(f"<h{level}>{body}</h{level}>")
        elif unordered:
            if list_mode != "ul":
                close_list(); html.append("<ul>"); list_mode = "ul"
            body = _render_workflow_inline(unordered.group(1).strip())
            html.append(f"<li>{body}</li>")
        elif ordered:
            if list_mode != "ol":
                close_list(); html.append("<ol>"); list_mode = "ol"
            body = _render_workflow_inline(ordered.group(1).strip())
            html.append(f"<li>{body}</li>")
        else:
            close_list()
            html.append(f"<p>{escaped}</p>")
    close_list()
    return Markup("\n".join(html))  # nosec B704


def register_text_filters(app):
    """Register custom text-related Jinja filters."""
    app.jinja_env.filters["linkify_text"] = linkify_text
    app.jinja_env.filters["workflow_markdown"] = workflow_markdown
