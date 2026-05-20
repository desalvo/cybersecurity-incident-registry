import re

from markupsafe import Markup, escape


def linkify_text(value):
    """Render plain text safely and turn detected http(s) URLs into links.

    Used for workflow step descriptions in the incident page: the surrounding
    workflow card remains clickable, while links embedded in the text can be
    opened independently. Newlines are preserved as HTML line breaks.
    """
    text_value = "" if value is None else str(value)
    url_re = re.compile(r"(https?://[^\s<]+)", re.IGNORECASE)
    parts = []
    last = 0
    for match in url_re.finditer(text_value):
        parts.append(escape(text_value[last:match.start()]))
        raw_url = match.group(1)
        trailing = ""
        while raw_url and raw_url[-1] in ".,;:!?)]}":
            trailing = raw_url[-1] + trailing
            raw_url = raw_url[:-1]
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


def register_text_filters(app):
    """Register custom text-related Jinja filters."""
    app.jinja_env.filters["linkify_text"] = linkify_text
