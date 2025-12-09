import json
import zipfile
import tempfile
import base64
from datetime import datetime
from pathlib import Path

import streamlit as st


# ---------- Helpers ----------

def extract_zip_to_temp(uploaded_zip) -> Path:
    """
    Extract uploaded ZIP to a temporary directory.
    Returns the Path to the extracted directory.
    """
    tmp_dir = tempfile.mkdtemp(prefix="discord_export_")
    tmp_path = Path(tmp_dir)

    with zipfile.ZipFile(uploaded_zip) as zf:
        zf.extractall(tmp_path)

    return tmp_path


def load_from_directory(base_dir: Path):
    """
    Expect structure:
      - base_dir/messages.json
      - base_dir/metadata.json (optional)
      - base_dir/attachments/ (optional)
    """
    messages_path = base_dir / "messages.json"
    if not messages_path.exists():
        return [], None, None

    with messages_path.open("r", encoding="utf-8") as f:
        messages = json.load(f)

    metadata = None
    metadata_path = base_dir / "metadata.json"
    if metadata_path.exists():
        try:
            with metadata_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = None

    attachments_dir = base_dir / "attachments"
    if not attachments_dir.exists() or not attachments_dir.is_dir():
        attachments_dir = None

    return messages, metadata, attachments_dir


def parse_timestamp(ts):
    if not ts:
        return None
    try:
        # Handles strings like "2024-09-17T06:52:11.254000+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def format_timestamp(ts: str) -> str:
    dt = parse_timestamp(ts)
    if not dt:
        return ts or ""
    # Display as: 2024-09-17 14:52
    return dt.strftime("%Y-%m-%d %H:%M")


def escape_html(text: str) -> str:
    """Basic HTML escape to avoid breaking the layout."""
    import html

    if text is None:
        return ""
    text = html.escape(text)
    # Preserve line breaks
    text = text.replace("\n", "<br>")
    return text


def highlight_mentions(text_html: str) -> str:
    """
    Replace &lt;@...&gt; with .mention spans.
    We keep the raw ID because we don't have a mapping to names.
    """
    import re

    def repl(match):
        inner = match.group(1)  # includes optional ! or &
        # Just show @ID for now
        return f'<span class="mention">@{inner}</span>'

    return re.sub(r"&lt;@([!&]?\d+)&gt;", repl, text_html)


def render_attachments(attachments, attachments_dir: Path | None) -> str:
    """
    Render attachment HTML. For images, prefer local files from attachments_dir
    using base64; fallback to URL if local file missing.
    """
    if not attachments:
        return ""

    html_parts = []

    for att in attachments:
        filename = att.get("filename", "attachment")
        saved_as = att.get("saved_as") or filename
        url = att.get("url", "")
        content_type = att.get("content_type", "")

        local_file = None
        if attachments_dir is not None:
            candidate = attachments_dir / saved_as
            if candidate.exists():
                local_file = candidate

        # Images
        if content_type.startswith("image/"):
            src = ""
            if local_file is not None:
                try:
                    with local_file.open("rb") as f:
                        data = f.read()
                    b64 = base64.b64encode(data).decode("ascii")
                    mime = content_type or "image/png"
                    src = f"data:{mime};base64,{b64}"
                except Exception:
                    src = ""
            # Fallback to remote URL if base64 failed and URL is present
            if not src and url:
                src = url

            if src:
                html_parts.append(
                    f"""
                    <div class="attachment">
                        <div class="attachment-label">Image:</div>
                        <a href="{url or src}" target="_blank">
                            <img src="{src}" alt="{filename}" class="attachment-image" />
                        </a>
                        <div class="attachment-filename">{filename}</div>
                    </div>
                    """
                )
            else:
                # If all else fails, just show filename
                html_parts.append(
                    f"""
                    <div class="attachment">
                        <span class="attachment-label">Image:</span>
                        <span class="attachment-filename">{filename}</span>
                    </div>
                    """
                )

        # Non-image attachments
        else:
            # If we have a URL, link to it, otherwise just show the filename
            if url:
                link_html = (
                    f'<a href="{url}" target="_blank" class="attachment-link">{filename}</a>'
                )
            else:
                link_html = f'<span class="attachment-filename">{filename}</span>'

            html_parts.append(
                f"""
                <div class="attachment">
                    <span class="attachment-label">Attachment:</span>
                    {link_html}
                </div>
                """
            )

    return "".join(html_parts)


def inject_css():
    st.markdown(
        """
        <style>
        body {
            background-color: #2f3136;
        }

        .discord-container {
            background-color: #2f3136;
            padding: 1rem 0.5rem 4rem 0.5rem;
        }

        .day-separator {
            text-align: center;
            margin: 1.5rem 0 1rem 0;
            position: relative;
            color: #b9bbbe;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .day-separator::before,
        .day-separator::after {
            content: "";
            position: absolute;
            top: 50%;
            width: 30%;
            border-bottom: 1px solid #40444b;
        }
        .day-separator::before {
            left: 0;
        }
        .day-separator::after {
            right: 0;
        }

        .message {
            display: flex;
            padding: 0.25rem 0.75rem;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: #dcddde;
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
            font-weight: 700;
            text-transform: uppercase;
            font-size: 1rem;
            flex-shrink: 0;
        }

        .message-content {
            flex: 1;
            min-width: 0;
        }

        .message-header {
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
        }

        .author-name {
            font-weight: 600;
            margin-right: 0.45rem;
            color: #ffffff;
        }

        .timestamp {
            font-size: 0.75rem;
            color: #72767d;
        }

        .message-body {
            margin-top: 0.15rem;
            font-size: 0.95rem;
            word-wrap: break-word;
            white-space: normal;
        }

        .message-body code {
            background-color: #202225;
            padding: 0.1rem 0.25rem;
            border-radius: 3px;
            font-size: 0.9em;
        }

        .attachment {
            margin-top: 0.35rem;
            font-size: 0.8rem;
        }

        .attachment-label {
            color: #72767d;
            margin-bottom: 0.1rem;
        }

        .attachment-image {
            max-width: 260px;
            max-height: 260px;
            border-radius: 6px;
            display: block;
            margin-bottom: 0.1rem;
            border: 1px solid #202225;
        }

        .attachment-link,
        .attachment-filename a {
            color: #00aff4;
            text-decoration: none;
        }

        .attachment-link:hover,
        .attachment-filename a:hover {
            text-decoration: underline;
        }

        .attachment-filename {
            color: #b9bbbe;
        }

        .mention {
            background-color: #3b4a6b;
            color: #dee0fc;
            padding: 0 0.15rem;
            border-radius: 3px;
            font-weight: 500;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------- Streamlit App ----------

def main():
    st.set_page_config(page_title="Discord ZIP Viewer", layout="wide")
    inject_css()

    st.title("Discord ZIP Viewer")
    st.caption("Upload a Discord export ZIP (messages.json, metadata.json, attachments/) and view it in a chat-style layout.")

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_zip = st.file_uploader("Upload export ZIP", type=["zip"])
    with col2:
        st.markdown(
            """
            **Expected ZIP structure:**
            - `messages.json`  
            - `metadata.json` *(optional)*  
            - `attachments/` *(folder where files are named using `saved_as` from `messages.json`)*  
            """
        )

    # Determine base directory for loading
    if uploaded_zip is not None:
        base_dir = extract_zip_to_temp(uploaded_zip)
    else:
        # Fallback: try local current directory (for dev/debug)
        base_dir = Path(".")

    messages, metadata, attachments_dir = load_from_directory(base_dir)

    if not messages:
        if uploaded_zip is None:
            st.info(
                "Upload a ZIP file, or place `messages.json` (and optionally `metadata.json`, `attachments/`) "
                "in the same folder as this script."
            )
        else:
            st.error("Could not find `messages.json` in the uploaded ZIP.")
        return

    # Handle case where JSON is a dict with "messages" key
    if isinstance(messages, dict):
        if "messages" in messages:
            messages = messages["messages"]
        else:
            st.error("JSON format not recognized. Expected a list of messages or a 'messages' key.")
            return

    # Sort messages by created_at
    def sort_key(msg):
        dt = parse_timestamp(msg.get("created_at", ""))
        return dt or datetime.min

    messages = sorted(messages, key=sort_key)

    # Show some metadata if available
    if metadata:
        st.subheader("Metadata")
        # Try common keys, fall back to generic pretty-print
        guild_name = metadata.get("guild_name") or metadata.get("server_name")
        channel_name = metadata.get("channel_name")
        if guild_name or channel_name:
            if guild_name:
                st.write(f"**Server:** {guild_name}")
            if channel_name:
                st.write(f"**Channel:** {channel_name}")
        else:
            st.json(metadata)

    st.subheader(f"Messages ({len(messages)})")

    # Render messages
    st.markdown('<div class="discord-container">', unsafe_allow_html=True)

    last_date_str = None

    for msg in messages:
        author = msg.get("author", "Unknown")
        content = msg.get("content", "")
        created_at = msg.get("created_at", "")
        attachments = msg.get("attachments", [])

        dt = parse_timestamp(created_at)
        cur_date_str = dt.strftime("%Y-%m-%d") if dt else None

        # Day separator when date changes
        if cur_date_str and cur_date_str != last_date_str:
            st.markdown(
                f'<div class="day-separator">{cur_date_str}</div>',
                unsafe_allow_html=True,
            )
            last_date_str = cur_date_str

        avatar_letter = author[0].upper() if author else "?"

        safe_body = escape_html(content)
        safe_body = highlight_mentions(safe_body)

        attachments_html = render_attachments(attachments, attachments_dir)

        message_html = f"""
        <div class="message">
            <div class="avatar">{avatar_letter}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="author-name">{author}</span>
                    <span class="timestamp">{format_timestamp(created_at)}</span>
                </div>
                <div class="message-body">
                    {safe_body}
                </div>
                {attachments_html}
            </div>
        </div>
        """

        st.markdown(message_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
