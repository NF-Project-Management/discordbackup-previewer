import json
import zipfile
import tempfile
import base64
from datetime import datetime
from pathlib import Path

import streamlit as st


# ============= SETTINGS =============
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB limit for Streamlit Cloud


# ============= BASIC HELPERS =============
def parse_ts(ts: str | None):
    """Parse ISO timestamp string from Discord export."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def html_escape(text: str) -> str:
    """Escape text so it is safe in HTML, keep line breaks."""
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
        .replace("\n", "<br>")
    )


# ============= LOADING EXPORTS =============
def extract_zip(uploaded_zip):
    """Extract uploaded ZIP into a temp directory. Return Path to that directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="discord_zip_"))
    with zipfile.ZipFile(uploaded_zip, "r") as z:
        z.extractall(temp_dir)
    return temp_dir


def load_zip_export(zip_dir: Path):
    """
    Expect:
      zip_dir/
        messages.json
        metadata.json (optional)
        attachments/ (folder of files named by `saved_as`)
    """
    messages_path = zip_dir / "messages.json"
    metadata_path = zip_dir / "metadata.json"
    attachments_path = zip_dir / "attachments"

    if not messages_path.exists():
        return None, None, None

    with messages_path.open("r", encoding="utf-8") as f:
        messages = json.load(f)

    metadata = None
    if metadata_path.exists():
        try:
            with metadata_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = None

    attachments_dir = attachments_path if attachments_path.exists() else None

    # Support {"messages": [...]} and plain list
    if isinstance(messages, dict) and "messages" in messages:
        messages = messages["messages"]

    return messages, metadata, attachments_dir


def load_json(uploaded_json):
    """Load messages from a standalone messages.json file."""
    data = json.load(uploaded_json)
    if isinstance(data, dict) and "messages" in data:
        return data["messages"]
    return data


# ============= RENDERING ATTACHMENTS =============
def render_attachment(att, attachments_dir: Path | None) -> str:
    """
    Return HTML snippet for a single attachment.

    - If ZIP + attachments_dir is available and file is found:
        * Images => inline <img>
        * Videos => <video controls>
    - Otherwise:
        * Show a simple link using the CDN URL (if any)
    """
    filename = att.get("filename", "attachment")
    saved_as = att.get("saved_as") or filename
    url = att.get("url", "")
    content_type = att.get("content_type") or ""
    if not isinstance(content_type, str):
        content_type = str(content_type)
    content_type = content_type.lower()

    # Try to locate the local file inside /attachments
    local_file = None
    if attachments_dir is not None:
        candidate = attachments_dir / saved_as
        if candidate.exists():
            local_file = candidate

    # Determine media type
    media_type = ""
    if "/" in content_type:
        media_type = content_type.split("/", 1)[0]

    # Choose src: prefer local base64 (for images/videos), fallback to URL
    src = None
    if local_file is not None and media_type in ("image", "video"):
        try:
            data = local_file.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            src = f"data:{content_type};base64,{b64}"
        except Exception:
            src = None

    if src is None and url:
        src = url

    # Image preview
    if media_type == "image" and src:
        return (
            '<div class="attachment">'
            '<span class="attachment-label">Image:</span>'
            f'<a href="{html_escape(url or src)}" target="_blank">'
            f'<img src="{html_escape(src)}" class="attachment-image" alt="{html_escape(filename)}">'
            '</a>'
            '</div>'
        )

    # Video preview
    if media_type == "video" and src:
        return (
            '<div class="attachment">'
            '<span class="attachment-label">Video:</span>'
            f'<video controls class="attachment-video" src="{html_escape(src)}"></video>'
            '</div>'
        )

    # Other files → just a link (or plain filename)
    if url:
        return (
            '<div class="attachment">'
            '<span class="attachment-label">Attachment:</span>'
            f'<a href="{html_escape(url)}" target="_blank" class="attachment-link">'
            f'{html_escape(filename)}</a>'
            '</div>'
        )

    return (
        '<div class="attachment">'
        '<span class="attachment-label">Attachment:</span>'
        f'<span class="attachment-filename">{html_escape(filename)}</span>'
        '</div>'
    )


# ============= RENDERING MESSAGES =============
def render_message(msg, attachments_dir: Path | None) -> str:
    """Return HTML snippet for a single Discord message row."""
    author = msg.get("author", "Unknown")
    content = msg.get("content", "")
    created_at = msg.get("created_at", "")

    dt = parse_ts(created_at)
    # 12-hour format with AM/PM
    timestamp = dt.strftime("%Y-%m-%d %I:%M %p") if dt else ""

    avatar_letter = (author[:1] or "?").upper()

    body = html_escape(content)
    attachments_html = "".join(
        render_attachment(att, attachments_dir)
        for att in (msg.get("attachments") or [])
    )

    return (
        '<div class="message">'
        f'<div class="avatar">{html_escape(avatar_letter)}</div>'
        '<div class="message-content">'
        '<div class="message-header">'
        f'<span class="author-name">{html_escape(author)}</span>'
        f'<span class="timestamp">{html_escape(timestamp)}</span>'
        '</div>'
        f'<div class="message-body">{body}</div>'
        f'{attachments_html}'
        '</div>'
        '</div>'
    )


# ============= CSS =============
def inject_css():
    st.markdown(
        """
        <style>
        body {
            background-color: #2f3136;
        }

        .discord-window {
            max-height: 600px;         /* Scrollable preview window */
            overflow-y: auto;
            border: 1px solid #202225;
            border-radius: 10px;
            background-color: #2f3136;
            padding: 0.5rem 0;
        }

        .discord-container {
            background-color: #2f3136;
            padding: 0.25rem 0.75rem 0.75rem 0.75rem;
        }

        .message {
            display: flex;
            padding: 0.35rem 0;
            color: #dcddde;
            font-family: system-ui, -apple-system, BlinkMacSystemFont,
                         "Segoe UI", sans-serif;
        }

        .avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background-color: #5865f2;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 0.75rem;
            font-weight: bold;
            flex-shrink: 0;
        }

        .message-content {
            flex: 1;
            min-width: 0;
        }

        .message-header {
            display: flex;
            align-items: baseline;
            gap: 0.35rem;
        }

        .author-name {
            font-weight: 600;
            color: #ffffff;
        }

        .timestamp {
            color: #72767d;
            font-size: 0.8rem;
        }

        .message-body {
            margin-top: 0.1rem;
            font-size: 0.95rem;
            word-wrap: break-word;
            white-space: normal;
        }

        .attachment {
            margin-top: 0.35rem;
            font-size: 0.8rem;
        }

        .attachment-label {
            color: #72767d;
            margin-bottom: 0.1rem;
            display: block;
        }

        .attachment-image,
        .attachment-video {
            max-width: 260px;
            max-height: 260px;
            border-radius: 6px;
            display: block;
            border: 1px solid #202225;
        }

        .attachment-link {
            color: #00aff4;
            text-decoration: none;
        }

        .attachment-link:hover {
            text-decoration: underline;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============= MAIN APP =============
def main():
    st.set_page_config(page_title="Discord Export Viewer", layout="wide")
    inject_css()

    st.title("Discord Export Viewer")

    st.write(
        "Upload either a **messages.json** file or a **Discord export ZIP** "
        "(with `messages.json`, `metadata.json`, and `attachments/`)."
    )

    # Side-by-side uploaders
    col_json, col_zip = st.columns(2)

    with col_json:
        json_file = st.file_uploader("📄 Upload messages.json", type=["json"])

    with col_zip:
        zip_file = st.file_uploader("🗂 Upload export ZIP", type=["zip"])

    messages = None
    metadata = None
    attachments_dir = None

    # ZIP has priority if present and within limit
    if zip_file is not None:
        if zip_file.size > MAX_UPLOAD_SIZE:
            st.error(
                f"ZIP file is too large ({zip_file.size/1024/1024:.1f} MB). "
                "Streamlit Cloud upload limit is 200 MB. "
                "Please upload the smaller messages.json instead."
            )
        else:
            st.success("ZIP uploaded → reading full export (with attachments)…")
            extracted_dir = extract_zip(zip_file)
            messages, metadata, attachments_dir = load_zip_export(extracted_dir)

    elif json_file is not None:
        st.success("JSON uploaded → reading messages only (no local attachments)…")
        messages = load_json(json_file)

    else:
        st.info("Please upload either `messages.json` or an export ZIP to begin.")
        return

    if not messages:
        st.error("No messages found in the provided file.")
        return

    # Sort by timestamp
    def sort_key(msg):
        dt = parse_ts(msg.get("created_at", ""))
        return dt or datetime.min

    messages = sorted(messages, key=sort_key)

    st.subheader(f"Loaded {len(messages)} messages")

    # Build the full HTML once → fewer chances for stray tags to show
    messages_html = "".join(render_message(m, attachments_dir) for m in messages)

    container_html = (
        '<div class="discord-window"><div class="discord-container">'
        f"{messages_html}"
        "</div></div>"
    )

    st.markdown(container_html, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
