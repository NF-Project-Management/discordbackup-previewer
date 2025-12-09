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

    messages = json.load(open(messages_path, "r", encoding="utf-8"))
    metadata = (
        json.load(open(metadata_path, "r", encoding="utf-8"))
        if metadata_path.exists()
        else None
    )
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


def parse_ts(ts):
    try:
        return datetime.fromisoformat(ts)
    except:
        return None


def render_attachment(att, attachments_dir: Path | None):
    """Render attachment HTML block."""
    filename = att.get("filename", "attachment")
    saved_as = att.get("saved_as", filename)
    url = att.get("url", "")
    content_type = att.get("content_type", "")

    # If ZIP attachments exist, try local file first
    if attachments_dir:
        local_file = attachments_dir / saved_as
    else:
        local_file = None

    # Images
    if content_type.startswith("image/"):
        img_src = None

        # Try local base64
        if local_file and local_file.exists():
            try:
                data = local_file.read_bytes()
                b64 = base64.b64encode(data).decode("utf-8")
                img_src = f"data:{content_type};base64,{b64}"
            except:
                img_src = None

        # Fallback to URL
        if not img_src:
            img_src = url

        if img_src:
            return f"""
                <div class="attachment">
                    <div class="attachment-label">Image:</div>
                    <img src="{img_src}" class="attachment-image"/>
                    <div class="attachment-filename">{filename}</div>
                </div>
            """

    # Non-image fallback
    if url:
        return f"""
            <div class="attachment">
                <span class="attachment-label">Attachment:</span>
                <a href="{url}" target="_blank" class="attachment-link">{filename}</a>
            </div>
        """
    else:
        return f"""
            <div class="attachment">
                <span class="attachment-label">Attachment:</span>
                <span>{filename}</span>
            </div>
        """


def render_message(msg, attachments_dir):
    author = msg.get("author", "Unknown")
    content = msg.get("content", "")
    created_at = msg.get("created_at", "")

    dt = parse_ts(created_at)
    timestamp = dt.strftime("%Y-%m-%d %H:%M") if dt else ""

    content_html = (
        content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )

    attachments_html = ""
    for att in msg.get("attachments", []):
        attachments_html += render_attachment(att, attachments_dir)

    return f"""
        <div class="message">
            <div class="avatar">{author[:1].upper()}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="author-name">{author}</span>
                    <span class="timestamp">{timestamp}</span>
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
            body { background-color: #2f3136; }
            .discord-container { padding: 1rem; background-color: #2f3136; }
            .message { display: flex; padding: 0.5rem; color: #dcddde; }
            .avatar {
                width: 40px; height: 40px;
                border-radius: 50%; background-color: #5865f2;
                display: flex; align-items: center; justify-content: center;
                margin-right: 0.75rem; font-weight: bold;
            }
            .attachment-image {
                max-width: 260px; max-height: 260px;
                margin-top: 5px; border-radius: 5px;
            }
            .attachment-label { color: #72767d; font-size: 0.8rem; }
            .timestamp { margin-left: 10px; color: #72767d; font-size: 0.8rem; }
            .author-name { font-weight: bold; color: white; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============= MAIN APP =============
def main():
    st.title("Discord Export Viewer")
    inject_css()

    st.write("Upload a **messages.json** or a **Discord export ZIP**")

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

    if zip_file:
        if zip_file.size > MAX_UPLOAD_SIZE:
            st.error(
                f"ZIP file is too large ({zip_file.size/1024/1024:.1f} MB). Limit is 200 MB on Streamlit Cloud.\n"
                "Please upload messages.json instead."
            )
        else:
            st.success("ZIP uploaded → reading full export…")
            extracted = extract_zip(zip_file)
            messages, metadata, attachments_dir = load_zip_export(extracted)

    elif json_file:
        st.success("JSON uploaded → reading messages only…")
        messages = load_json(json_file)

    else:
        st.info("Please upload a file to view messages.")
        return

    # ---------- RENDER ----------
    if not messages:
        st.error("No messages found in file.")
        return

    st.subheader(f"Loaded {len(messages)} messages")

    st.markdown('<div class="discord-container">', unsafe_allow_html=True)

    for msg in messages:
        st.markdown(render_message(msg, attachments_dir), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
