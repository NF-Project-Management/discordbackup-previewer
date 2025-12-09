import json
import zipfile
import tempfile
import base64
from datetime import datetime
from pathlib import Path
import streamlit as st


# ============= SETTINGS =============
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB limit for Streamlit Cloud


# ============= HELPERS =============
def extract_zip(uploaded_zip):
    """Extract ZIP to a temporary directory and return its path."""
    temp_dir = Path(tempfile.mkdtemp(prefix="discord_zip_"))
    with zipfile.ZipFile(uploaded_zip, "r") as z:
        z.extractall(temp_dir)
    return temp_dir


def load_zip_export(zip_dir: Path):
    """Load messages, metadata, and attachments directory from extracted ZIP."""
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

    attachments = attachments_path if attachments_path.exists() else None

    # If JSON is dict with "messages" key
    if isinstance(messages, dict) and "messages" in messages:
        messages = messages["messages"]

    return messages, metadata, attachments


def load_json(uploaded_json):
    """Load messages.json directly."""
    data = json.load(uploaded_json)
    if isinstance(data, dict) and "messages" in data:
        return data["messages"]
    return data


def parse_ts(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def html_escape(text: str) -> str:
    """Very simple HTML escape + line breaks."""
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def render_attachment(att, attachments_dir: Path | None):
    """Render a single attachment HTML block."""
    filename = att.get("filename", "attachment")
    saved_as = att.get("saved_as", filename)
    url = att.get("url", "")
    content_type = att.get("content_type", "")

    local_file = None
    if attachments_dir is not None:
        candidate = attachments_dir / saved_as
        if candidate.exists():
            local_file = candidate

    # Images
    if content_type.startswith("image/"):
        img_src = None

        # Try local base64 first (when ZIP + attachments are available)
        if local_file:
            try:
                data = local_file.read_bytes()
                b64 = base64.b64encode(data).decode("utf-8")
                img_src = f"data:{content_type};base64,{b64}"
            except Exception:
                img_src = None

        # Fallback to URL
        if not img_src and url:
            img_src = url

        if img_src:
            return f"""
                <div class="attachment">
                    <div class="attachment-label">Image:</div>
                    <img src="{img_src}" class="attachment-image"/>
                    <div class="attachment-filename">{html_escape(filename)}</div>
                </div>
            """

        # If no src at all:
        return f"""
            <div class="attachment">
                <span class="attachment-label">Image:</span>
                <span class="attachment-filename">{html_escape(filename)}</span>
            </div>
        """

    # Non-image attachments
    if url:
        return f"""
            <div class="attachment">
                <span class="attachment-label">Attachment:</span>
                <a href="{url}" target="_blank" class="attachment-link">{html_escape(filename)}</a>
            </div>
        """
    else:
        return f"""
            <div class="attachment">
                <span class="attachment-label">Attachment:</span>
                <span>{html_escape(filename)}</span>
            </div>
        """


def render_message(msg, attachments_dir):
    author = msg.get("author", "Unknown")
    content = msg.get("content", "")
    created_at = msg.get("created_at", "")

    dt = parse_ts(created_at)
    timestamp = dt.strftime("%Y-%m-%d %H:%M") if dt else ""

    content_html = html_escape(content)

    attachments_html = ""
    for att in msg.get("attachments", []):
        attachments_html += render_attachment(att, attachments_dir)

    avatar_letter = html_escape(author[:1].upper() if author else "?")
    author_html = html_escape(author)

    return f"""
        <div class="message">
            <div class="avatar">{avatar_letter}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="author-name">{author_html}</span>
                    <span class="timestamp">{html_escape(timestamp)}</span>
                </div>
                <div class="message-body">{content_html}</div>
                {attachments_html}
            </div>
        </div>
    """


# ============= CSS =============
def inject_css():
    st.markdown(
        """
        <style>
            body {
                background-color: #2f3136;
            }

            .discord-window {
                max-height: 600px;            /* fixed-height preview window */
                overflow-y: auto;             /* vertical scrollbar */
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

            .attachment-image {
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

    st.write("Upload either a **messages.json** file or a **Discord export ZIP** (with `messages.json`, `metadata.json`, and `attachments/`).")

    # ---------- SIDE BY SIDE UPLOADERS ----------
    col_json, col_zip = st.columns(2)

    with col_json:
        json_file = st.file_uploader("📄 Upload messages.json", type=["json"])

    with col_zip:
        zip_file = st.file_uploader("🗂 Upload export ZIP", type=["zip"])

    # ---------- PRIORITY LOGIC ----------
    messages = None
    metadata = None
    attachments_dir = None

    if zip_file is not None:
        if zip_file.size > MAX_UPLOAD_SIZE:
            st.error(
                f"ZIP file is too large ({zip_file.size/1024/1024:.1f} MB). "
                "Streamlit Cloud upload limit is 200 MB. "
                "Please upload the smaller messages.json instead."
            )
        else:
            st.success("ZIP uploaded → reading full export…")
            extracted_dir = extract_zip(zip_file)
            messages, metadata, attachments_dir = load_zip_export(extracted_dir)

    elif json_file is not None:
        st.success("JSON uploaded → reading messages only…")
        messages = load_json(json_file)

    else:
        st.info("Please upload either `messages.json` or an export ZIP to begin.")
        return

    # ---------- VALIDATE & SORT ----------
    if not messages:
        st.error("No messages found in the provided file.")
        return

    # Sort by timestamp if present
    def sort_key(msg):
        dt = parse_ts(msg.get("created_at", ""))
        return dt or datetime.min

    messages = sorted(messages, key=sort_key)

    st.subheader(f"Loaded {len(messages)} messages")

    # ---------- SCROLLABLE CHAT WINDOW ----------
    st.markdown('<div class="discord-window"><div class="discord-container">', unsafe_allow_html=True)

    for msg in messages:
        st.markdown(render_message(msg, attachments_dir), unsafe_allow_html=True)

    st.markdown("</div></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
