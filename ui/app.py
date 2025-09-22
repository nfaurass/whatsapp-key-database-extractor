import os
import sqlite3
import urllib.parse
# pip install flask
from flask import Flask, jsonify, request, render_template_string, send_file

# Make sure to change this to the path of your WhatsApp msgstore.db file
DB_PATH = r"D:\Projects\whatsapp-key-database-extractor\data\com.whatsapp\db\msgstore.db"
# Set MEDIA_ROOT to your WhatsApp media folder if you want media previews, otherwise leave as None
MEDIA_ROOT = None
# Default batch size for message loading
BATCH_SIZE = 400

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WhatsApp Database Viewer</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  /* Custom scrollbar for webkit browsers to match WhatsApp */
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(0,0,0,0.2);
    border-radius: 3px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(0,0,0,0.3);
  }

  /* Message bubble tails */
  .msg-tail-right::after {
    content: '';
    position: absolute;
    top: 0;
    right: -8px;
    width: 0;
    height: 0;
    border: 8px solid transparent;
    border-left-color: #dcf8c6;
    border-right: 0;
    border-top: 0;
  }
  .msg-tail-left::after {
    content: '';
    position: absolute;
    top: 0;
    left: -8px;
    width: 0;
    height: 0;
    border: 8px solid transparent;
    border-right-color: white;
    border-left: 0;
    border-top: 0;
  }
</style>
</head>
<body class="bg-gray-100 h-screen overflow-hidden">
<div class="flex h-screen">
  <div class="w-80 bg-white border-r border-gray-200 flex flex-col">
    <!-- Header -->
    <div class="bg-gray-50 px-4 py-3 border-b border-gray-200">
      <h1 class="text-lg font-semibold text-gray-800">Chats</h1>
    </div>
    <div class="flex-1 overflow-y-auto custom-scrollbar" id="sidebar">
      {% for chat in chats %}
        <div class="px-4 py-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors" 
             onclick="selectChat({{ chat['chat_id'] }}, '{{ chat['chat_name']|e }}')">
          <div class="flex items-center space-x-3">
            <div class="w-12 h-12 bg-gray-300 rounded-full flex items-center justify-center">
              <span class="text-gray-600 font-medium text-sm">
                {{ chat['chat_name'][:2].upper() if chat['chat_name'] else '?' }}
              </span>
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium text-gray-900 truncate">{{ chat['chat_name'] }}</div>
              <div class="text-sm text-gray-500 truncate">{{ chat['preview'] }}</div>
            </div>
          </div>
        </div>
      {% endfor %}
    </div>
  </div>
  <div class="flex-1 flex flex-col bg-gray-50">
    <!-- Chat Header -->
    <div class="bg-white px-6 py-4 border-b border-gray-200 shadow-sm">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <div class="w-10 h-10 bg-gray-300 rounded-full flex items-center justify-center">
            <span class="text-gray-600 font-medium text-sm" id="chat-avatar">?</span>
          </div>
          <div>
            <div class="font-medium text-gray-900" id="chat-header">Select a chat</div>
            <div class="text-sm text-gray-500">Click on a chat to start viewing messages</div>
          </div>
        </div>
        <div class="flex items-center space-x-3">
          <label class="text-sm text-gray-600">Order</label>
          <select id="order-select" class="border rounded px-2 py-1 text-sm" onchange="onOrderOrBatchChanged()">
            <option value="desc" selected>Newest first (new → old)</option>
            <option value="asc">Oldest first (old → new)</option>
          </select>
          <label class="text-sm text-gray-600">Batch</label>
          <input id="batch-input" type="number" min="1" max="5000" step="1" class="w-20 border rounded px-2 py-1 text-sm"
                 value="{{ batch }}" onchange="onOrderOrBatchChanged()">
        </div>
      </div>
    </div>
    <div class="flex-1 overflow-y-auto custom-scrollbar px-6 py-4" 
         style="background-image: url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICAgIDxkZWZzPgogICAgICAgIDxwYXR0ZXJuIGlkPSJjaGF0LWJnIiB4PSIwIiB5PSIwIiB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHBhdHRlcm5Vbml0cz0idXNlclNwYWNlT25Vc2UiPgogICAgICAgICAgICA8cmVjdCB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIGZpbGw9IiNmN2Y3ZjciLz4KICAgICAgICAgICAgPGNpcmNsZSBjeD0iMTAiIGN5PSIxMCIgcj0iMC41IiBmaWxsPSIjZTVlNWU1Ii8+CiAgICAgICAgPC9wYXR0ZXJuPgogICAgPC9kZWZzPgogICAgPHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0idXJsKCNjaGF0LWJnKSIvPgo8L3N2Zz4K');" 
         id="messages">
      <div class="text-center text-gray-500 py-8">
        <div class="text-lg">👋</div>
        <div class="mt-2">Select a chat to view messages</div>
      </div>
    </div>
  </div>
</div>

<script>
let currentChatId = null;
let oldestTimestamp = null;
let newestTimestamp = null;
let loading = false;
let exhausted = false;

function getOrder() {
  return document.getElementById('order-select').value;
}

function getBatchSize() {
  const v = parseInt(document.getElementById('batch-input').value, 10);
  if (!Number.isFinite(v) || v < 1) return {{ batch }};
  return v;
}

function onOrderOrBatchChanged() {
  if (currentChatId !== null) {
    oldestTimestamp = null;
    newestTimestamp = null;
    exhausted = false;
    loadMessages(true);
  }
}

function getDateKey(ms) {
  const d = new Date(ms);
  return d.toDateString();
}

function formatDateDisplay(ms) {
  const d = new Date(ms);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

function makeDateSeparator(dateKey, displayText) {
  const sep = document.createElement('div');
  sep.className = 'flex justify-center my-4';
  sep.innerHTML = `
    <div class="bg-white bg-opacity-90 px-3 py-1 rounded-full text-xs font-medium text-gray-600 shadow-sm">
      ${displayText || dateKey}
    </div>
  `;
  sep.dataset.date = dateKey;
  return sep;
}

function escapeHtml(s) {
  if (!s && s !== 0) return '';
  return s.toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMessageNode(msg) {
  const container = document.createElement('div');
  const isMe = msg.from_me;
  const dateKey = getDateKey(msg.timestamp_ms);
  container.dataset.date = dateKey;

  container.className = `flex ${isMe ? 'justify-end' : 'justify-start'} mb-2`;

  let bubbleClasses = `relative max-w-sm px-3 py-2 rounded-lg shadow-sm ${
    isMe 
      ? 'bg-green-100 text-gray-800 msg-tail-right' 
      : 'bg-white text-gray-800 msg-tail-left'
  }`;

  let inner = '';

  if (msg.quoted_text) {
    inner += `
      <div class="border-l-4 border-gray-300 pl-2 mb-2 text-sm text-gray-600 bg-gray-50 p-2 rounded">
        ${escapeHtml(msg.quoted_text)}
      </div>
    `;
  }

  if (msg.sender && !msg.from_me) {
    inner += `<div class="font-semibold text-sm mb-1 text-blue-600">${escapeHtml(msg.sender)}</div>`;
  }

  if (msg.text && msg.text.trim().length > 0) {
    inner += `<div class="break-words">${escapeHtml(msg.text)}</div>`;
  } else if (msg.media_name || msg.media_url) {
    if (msg.media_url) {
      inner += `
        <div class="mb-2">
          <img src="${msg.media_url}" 
               class="max-w-xs max-h-48 rounded-lg" 
               onerror="this.style.display='none'">
        </div>
        <div class="text-sm text-gray-500 italic">${escapeHtml(msg.media_name || '[media]')}</div>
      `;
    } else {
      inner += `<div class="text-sm text-gray-500 italic flex items-center">
        <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd" />
        </svg>
        ${escapeHtml(msg.media_name || 'file')}
      </div>`;
    }
  } else if (msg.message_type) {
    inner += `<div class="text-sm text-gray-500 italic">[${escapeHtml(msg.message_type)}]</div>`;
  } else {
    inner += `<div class="text-sm text-gray-500 italic">[no text]</div>`;
  }

  const time = new Date(msg.timestamp_ms);
  const timeStr = time.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
  inner += `<div class="text-xs text-gray-500 mt-1 text-right">${timeStr}</div>`;

  container.innerHTML = `<div class="${bubbleClasses}">${inner}</div>`;
  container.dataset.messageId = msg.id;
  return container;
}

function dedupeSeparators(messagesEl) {
  const nodes = Array.from(messagesEl.childNodes);
  for (let i = 0; i < nodes.length - 1; i++) {
    const a = nodes[i];
    const b = nodes[i + 1];
    if (a.dataset?.date && b.dataset?.date && 
        a.querySelector('.bg-white.bg-opacity-90') && b.querySelector('.bg-white.bg-opacity-90')) {
      if (a.dataset.date === b.dataset.date) {
        a.remove();
        nodes.splice(i, 1);
        i--;
      }
    }
  }

  const messageNodes = Array.from(messagesEl.childNodes);
  let currentDate = null;

  for (let i = 0; i < messageNodes.length; i++) {
    const node = messageNodes[i];
    if (node.dataset?.date && !node.querySelector('.bg-white.bg-opacity-90')) {
      const messageDate = node.dataset.date;
      if (messageDate !== currentDate) {
        const existingSeparator = i > 0 && messageNodes[i-1].querySelector('.bg-white.bg-opacity-90');
        if (!existingSeparator) {
          const separator = makeDateSeparator(messageDate, formatDateDisplay(new Date(messageDate).getTime()));
          messagesEl.insertBefore(separator, node);
        }
        currentDate = messageDate;
      }
    } else if (node.dataset?.date && node.querySelector('.bg-white.bg-opacity-90')) {
      currentDate = node.dataset.date;
    }
  }
}

async function insertBatch(chronological, initial=false, orderMode='desc') {
  const messagesEl = document.getElementById('messages');
  if (chronological.length === 0) return;

  if (initial) {
    messagesEl.innerHTML = '';
    let lastDate = null;
    for (const m of chronological) {
      const dateKey = getDateKey(m.timestamp_ms);
      if (dateKey !== lastDate) {
        messagesEl.appendChild(makeDateSeparator(dateKey, formatDateDisplay(m.timestamp_ms)));
        lastDate = dateKey;
      }
      messagesEl.appendChild(renderMessageNode(m));
    }
    return;
  }

  if (orderMode === 'desc') {
    const messagesFragment = document.createDocumentFragment();
    let lastInsertedDate = null;
    for (const m of chronological) {
      const dateKey = getDateKey(m.timestamp_ms);
      if (dateKey !== lastInsertedDate) {
        messagesFragment.appendChild(makeDateSeparator(dateKey, formatDateDisplay(m.timestamp_ms)));
        lastInsertedDate = dateKey;
      }
      messagesFragment.appendChild(renderMessageNode(m));
    }
    const firstChild = messagesEl.firstChild;
    const prevScrollHeight = messagesEl.scrollHeight;
    messagesEl.insertBefore(messagesFragment, firstChild);
    dedupeSeparators(messagesEl);
    const newScrollHeight = messagesEl.scrollHeight;
    messagesEl.scrollTop = newScrollHeight - prevScrollHeight;
  } else {
    const messagesFragment = document.createDocumentFragment();
    let lastInsertedDate = null;
    for (const m of chronological) {
      const dateKey = getDateKey(m.timestamp_ms);
      if (dateKey !== lastInsertedDate) {
        messagesFragment.appendChild(makeDateSeparator(dateKey, formatDateDisplay(m.timestamp_ms)));
        lastInsertedDate = dateKey;
      }
      messagesFragment.appendChild(renderMessageNode(m));
    }
    messagesEl.appendChild(messagesFragment);
    dedupeSeparators(messagesEl);
  }
}

async function selectChat(chatId, chatName) {
  currentChatId = chatId;
  oldestTimestamp = null;
  newestTimestamp = null;
  exhausted = false;

  document.getElementById('chat-header').textContent = chatName;
  document.getElementById('chat-avatar').textContent = chatName.substring(0, 2).toUpperCase();

  const messagesEl = document.getElementById('messages');
  messagesEl.innerHTML = `
    <div class="flex justify-center items-center h-full">
      <div class="text-center">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500 mx-auto"></div>
        <div class="mt-2 text-gray-500">Loading messages...</div>
      </div>
    </div>
  `;

  await loadMessages(true);

  const order = getOrder();
  if (order === 'desc') {
    setTimeout(() => { messagesEl.scrollTop = messagesEl.scrollHeight; }, 50);
  } else {
    setTimeout(() => { messagesEl.scrollTop = 0; }, 50);
  }
}

async function loadMessages(initial=false) {
  if (loading || currentChatId === null || exhausted) return;
  loading = true;

  const params = new URLSearchParams();
  params.set('chat_id', currentChatId);
  params.set('limit', getBatchSize());
  const order = getOrder();
  params.set('order', order);

  if (order === 'desc') {
    if (oldestTimestamp) params.set('before_ms', oldestTimestamp);
  } else {
    if (newestTimestamp) params.set('after_ms', newestTimestamp);
  }

  const res = await fetch('/messages?' + params.toString());
  if (!res.ok) { loading = false; return; }
  const json = await res.json();
  const msgs = json.messages;
  const messagesEl = document.getElementById('messages');

  const loader = messagesEl.querySelector('.animate-spin')?.closest('.flex');
  if (loader) loader.remove();

  if (msgs.length === 0) {
    exhausted = true;
    if (initial) {
      messagesEl.innerHTML = `
        <div class="flex justify-center items-center h-full">
          <div class="text-center text-gray-500">
            <div class="text-4xl mb-4">💬</div>
            <div>No messages in this chat</div>
          </div>
        </div>
      `;
    }
    loading = false;
    return;
  }

  const chronological = msgs.slice().sort((a,b) => a.timestamp_ms - b.timestamp_ms);

  await insertBatch(chronological, initial, order);

  if (order === 'desc') {
    oldestTimestamp = chronological[0].timestamp_ms;
    newestTimestamp = chronological[chronological.length - 1].timestamp_ms;
    if (json.count < getBatchSize()) exhausted = true;
  } else {
    newestTimestamp = chronological[chronological.length - 1].timestamp_ms;
    oldestTimestamp = chronological[0].timestamp_ms;
    if (json.count < getBatchSize()) exhausted = true;
  }

  loading = false;
}

document.addEventListener('DOMContentLoaded', () => {
  const messagesEl = document.getElementById('messages');

  messagesEl.addEventListener('scroll', () => {
    if (loading || exhausted || currentChatId === null) return;

    const order = getOrder();

    if (order === 'desc') {
      if (messagesEl.scrollTop === 0 && !loading && !exhausted) {
        loadMessages(false);
      }
    } else {
      const threshold = 20;
      if (messagesEl.scrollTop + messagesEl.clientHeight >= messagesEl.scrollHeight - threshold) {
        loadMessages(false);
      }
    }
  });
});
</script>
</body>
</html>
"""


def open_db():
    if not os.path.isfile(DB_PATH):
        raise FileNotFoundError(f"DB file not found at {DB_PATH!r}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_media_url(path):
    if not path:
        return None
    return '/media?path=' + urllib.parse.quote_plus(path)


@app.route('/')
def index():
    try:
        conn = open_db()
    except Exception as e:
        return f"<pre>Unable to open DB: {e}</pre>", 500

    cur = conn.cursor()
    cur.execute("""
    SELECT c._id AS chat_id,
           COALESCE(c.subject, j.user, j.raw_string, 'Unknown') AS chat_name,
           (SELECT text_data FROM message m WHERE m.chat_row_id = c._id ORDER BY m.timestamp DESC LIMIT 1) AS preview
    FROM chat c
    LEFT JOIN jid j ON c.jid_row_id = j._id
    ORDER BY c.sort_timestamp DESC, c._id DESC
    """)
    chats = []
    for row in cur.fetchall():
        preview = row['preview']
        if preview:
            preview = (preview[:80] + '...') if len(preview) > 80 else preview
        chats.append({
            'chat_id': row['chat_id'],
            'chat_name': row['chat_name'],
            'preview': preview or ''
        })
    conn.close()
    return render_template_string(HTML_TEMPLATE, chats=chats, batch=BATCH_SIZE)


@app.route('/messages')
def messages():
    chat_id = request.args.get('chat_id', type=int)
    before_ms = request.args.get('before_ms', type=int)  # ms
    after_ms = request.args.get('after_ms', type=int)  # ms (for asc)
    limit = request.args.get('limit', type=int) or BATCH_SIZE
    order = request.args.get('order', 'desc')  # 'asc' or 'desc'

    if chat_id is None:
        return jsonify({'error': 'chat_id required'}), 400

    try:
        conn = open_db()
    except Exception as e:
        return jsonify({'error': f'unable to open db: {e}'}), 500

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base_query = """
    SELECT m._id as id,
           m.from_me as from_me,
           m.text_data as text,
           m.timestamp as timestamp_ms,
           j.user as sender_user,
           j.raw_string as sender_raw,
           cj.user as chat_user,
           cj.raw_string as chat_raw,
           mq.text_data as quoted_text,
           mm.file_path as media_path,
           mm.direct_path as media_direct_path,
           mm.media_name as media_name,
           m.message_type as message_type
    FROM message m
    LEFT JOIN jid j ON m.sender_jid_row_id = j._id
    LEFT JOIN chat c ON m.chat_row_id = c._id
    LEFT JOIN jid cj ON c.jid_row_id = cj._id
    LEFT JOIN message_quoted mq ON m._id = mq.message_row_id
    LEFT JOIN message_media mm ON m._id = mm.message_row_id
    WHERE m.chat_row_id = ?
    """

    params = [chat_id]

    if order == 'asc':
        if after_ms:
            base_query += " AND m.timestamp > ?"
            params.append(after_ms)
        base_query += " ORDER BY m.timestamp ASC LIMIT ?"
        params.append(limit)
    else:
        if before_ms:
            base_query += " AND m.timestamp < ?"
            params.append(before_ms)
        base_query += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)

    cur.execute(base_query, params)
    rows = cur.fetchall()
    conn.close()

    messages = []
    for r in rows:
        if r['from_me']:
            sender_label = 'Me'
        else:
            sender_label = None
            if r['sender_user']:
                sender_label = r['sender_user']
            elif r['sender_raw']:
                sender_label = r['sender_raw']
            elif r['chat_user']:
                sender_label = r['chat_user']
            elif r['chat_raw']:
                sender_label = r['chat_raw']
            else:
                sender_label = 'Unknown'

        media_path = r['media_path'] or r['media_direct_path'] or None

        media_url = build_media_url(media_path) if (media_path and MEDIA_ROOT) else None

        messages.append({
            'id': r['id'],
            'from_me': bool(r['from_me']),
            'text': r['text'] or '',
            'timestamp_ms': int(r['timestamp_ms']) if r['timestamp_ms'] is not None else 0,
            'sender': sender_label,
            'quoted_text': r['quoted_text'] or '',
            'media_name': (r['media_name'] or (os.path.basename(media_path) if media_path else '')),
            'media_url': media_url,
            'message_type': r['message_type'] or ''
        })

    return jsonify({'messages': messages, 'count': len(messages)})


@app.route('/media')
def media():
    if MEDIA_ROOT is None:
        return jsonify({'error': 'media serving disabled (MEDIA_ROOT is None)'}), 404

    raw_path = request.args.get('path', '')
    if not raw_path:
        return jsonify({'error': 'path required'}), 400

    candidate = raw_path
    candidate = candidate.replace('\\', os.sep).replace('/', os.sep)

    if os.path.isabs(candidate):
        file_path = os.path.abspath(candidate)
    else:
        file_path = os.path.abspath(os.path.join(MEDIA_ROOT, candidate))

    media_root_abs = os.path.abspath(MEDIA_ROOT)
    if not file_path.startswith(media_root_abs):
        return jsonify({'error': 'file not allowed'}), 403

    if not os.path.exists(file_path):
        return jsonify({'error': 'file not found', 'path': file_path}), 404

    try:
        return send_file(file_path)
    except Exception as e:
        return jsonify({'error': f'could not send file: {e}'}), 500


if __name__ == '__main__':
    if not os.path.isfile(DB_PATH):
        print(f"ERROR: DB file not found at {DB_PATH!r}. Edit DB_PATH at top of script.")
    if MEDIA_ROOT and not os.path.isdir(MEDIA_ROOT):
        print(
            f"WARNING: MEDIA_ROOT directory not found at {MEDIA_ROOT!r}. Media preview disabled until path is correct.")
    app.run()
