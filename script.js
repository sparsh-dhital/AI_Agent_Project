const form = document.getElementById('chatForm');
const input = document.getElementById('messageInput');
const feed = document.getElementById('conversation');
const sidebar = document.getElementById('sidebar');

let credentials = JSON.parse(localStorage.getItem('orbit_user_creds')) || {
    name: '',
    usertype: '',
    registration_number: ''
};

let needsCredentials = !credentials.registration_number;
let currentChatId = null;

// Always start on a fresh chat when first loading the page
startNewChat();

function startNewChat() {
    currentChatId = 'chat_' + Math.random().toString(36).substr(2, 9);
    feed.innerHTML = '';
    showWelcomeScreen();
}

// --- Sidebar Logic ---
document.getElementById('menuBtn').addEventListener('click', () => {
    sidebar.classList.add('open');
    loadSidebarHistory();
});
document.getElementById('closeSidebar').addEventListener('click', () => {
    sidebar.classList.remove('open');
});
document.getElementById('newChatBtn').addEventListener('click', () => {
    sidebar.classList.remove('open');
    startNewChat();
});

async function loadSidebarHistory() {
    const list = document.getElementById('historyList');
    list.innerHTML = '<p style="color:#666; padding:10px; font-size:12px;">Loading conversations...</p>';
    try {
        const res = await fetch('http://127.0.0.1:5000/api/chats');
        const chats = await res.json();
        list.innerHTML = '';
        if (chats.length === 0) {
            list.innerHTML = '<p style="color:#666; padding:10px; font-size:12px;">No past conversations yet.</p>';
            return;
        }
        chats.forEach(chat => {
            const div = document.createElement('div');
            div.className = `history-item ${chat.chat_id === currentChatId ? 'active' : ''}`;
            div.textContent = chat.title || 'Conversation';
            div.onclick = () => loadSpecificChat(chat.chat_id);
            list.appendChild(div);
        });
    } catch (e) { 
        list.innerHTML = '<p style="color:#666; padding:10px; font-size:12px;">Failed to load history.</p>'; 
    }
}

async function loadSpecificChat(chatId) {
    currentChatId = chatId;
    sidebar.classList.remove('open');
    feed.innerHTML = '';
    
    try {
        const res = await fetch(`http://127.0.0.1:5000/api/chats/${chatId}`);
        const history = await res.json();
        if (history.length === 0) {
            return showWelcomeScreen();
        }
        
        // Re-render conversation from MongoDB
        history.forEach(msg => {
            appendUserMessage(msg.user_message);
            appendAIMessage(msg.bot_response, { recommendation: msg.plan });
        });
    } catch (e) { 
        showWelcomeScreen(); 
    }
}

// --- UI Rendering ---
function showWelcomeScreen() {
    if (needsCredentials) {
        feed.innerHTML = `
            <div class="message ai-message animate-in">
                <div class="avatar ai-avatar">✦</div>
                <div class="content">
                    <p class="greeting-text">Hello, welcome to CampusMove AI.</p>
                    <p>Please enter your credentials as your first input in this format:</p>
                    <p><strong>Name | Student/Employee | RegistrationNumber/EmpID</strong></p>
                    <div class="quick-actions">
                        <button class="action-chip" data-query="Alex Morgan | Student | 22CS104">Use Sample Credentials</button>
                    </div>
                </div>
            </div>
        `;
    } else {
        feed.innerHTML = `
            <div class="message ai-message animate-in">
                <div class="avatar ai-avatar">✦</div>
                <div class="content">
                    <p class="greeting-text">Hello ${credentials.name}.</p>
                    <p>Where are you heading today on campus?</p>
                    <div class="quick-actions">
                        <button class="action-chip" data-query="I need a bus from Hostel to College by 09:00">🚌 Hostel to College (by 9 AM)</button>
                        <button class="action-chip" data-query="What is the fastest route to College?">⚡ Fastest Route</button>
                        <button class="action-chip" data-query="Are there any delays right now?">⚠️ Check Delays</button>
                    </div>
                </div>
            </div>
        `;
    }
}

// Auto-expand textarea
input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
    }
});

feed.addEventListener('click', (e) => {
    if (e.target.classList.contains('action-chip')) {
        const query = e.target.getAttribute('data-query');
        e.target.parentElement.remove();
        submitMessage(query);
    }
});

function appendUserMessage(text) {
    const safeText = String(text).replace(/</g, '&lt;').replace(/>/g, '&gt;');
    feed.insertAdjacentHTML('beforeend', `
        <div class="message user-message animate-in">
            <div class="content"><p>${safeText}</p></div>
        </div>
    `);
    scrollToBottom();
}

function appendAIMessage(text, plan = null) {
    const safeText = String(text).replace(/</g, '&lt;').replace(/>/g, '&gt;');
    let cardHTML = '';
    if (plan && plan.recommendation) {
        const rec = plan.recommendation;
        cardHTML = `
            <div class="route-card animate-in">
                <div class="route-header">
                    <span class="route-name">🚌 ${rec.name}</span>
                    <span class="route-badge">${rec.crowding || 'Medium'} Crowd</span>
                </div>
                <div class="route-details">
                    <div class="route-stat"><span class="stat-label">Departing (${rec.from})</span><span class="stat-value">${rec.departure}</span></div>
                    <div class="route-stat right"><span class="stat-label">Arriving (${rec.to})</span><span class="stat-value">${rec.actual_arrival || rec.arrival}</span></div>
                </div>
            </div>`;
    }
    feed.insertAdjacentHTML('beforeend', `
        <div class="message ai-message animate-in">
            <div class="avatar ai-avatar">✦</div>
            <div class="content"><p>${safeText}</p>${cardHTML}</div>
        </div>
    `);
    scrollToBottom();
}

function parseCredentialInput(text) {
    const parts = String(text).split('|').map(p => p.trim());
    if (parts.length < 3) return null;
    const utRaw = parts[1].toLowerCase();
    const usertype = utRaw === 'student' ? 'Student' : utRaw === 'employee' ? 'Employee' : '';
    if (!parts[0] || !usertype || !parts[2]) return null;
    return { name: parts[0], usertype, registration_number: parts[2] };
}

function showTyping() {
    const id = 'typing-' + Date.now();
    feed.insertAdjacentHTML('beforeend', `
        <div class="message ai-message animate-in" id="${id}">
            <div class="avatar ai-avatar">✦</div>
            <div class="content"><div class="typing-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>
        </div>
    `);
    scrollToBottom();
    return id;
}

function scrollToBottom() {
    const vp = document.querySelector('.chat-viewport');
    vp.scrollTo({ top: vp.scrollHeight, behavior: 'smooth' });
}

// --- Send Logic ---
async function submitMessage(text) {
    if (!text) return;
    input.value = ''; 
    input.style.height = 'auto';

    if (needsCredentials) {
        const parsed = parseCredentialInput(text);
        if (parsed) {
            credentials = parsed;
            localStorage.setItem('orbit_user_creds', JSON.stringify(credentials));
        }
    }

    appendUserMessage(text);
    const typingId = showTyping();

    try {
        const response = await fetch('http://127.0.0.1:5000/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                chat_id: currentChatId,
                credentials
            })
        });

        const data = await response.json();
        document.getElementById(typingId)?.remove();

        appendAIMessage(data.answer, data.plan);
        needsCredentials = Boolean(data.needs_credentials);
    } catch (error) {
        document.getElementById(typingId)?.remove();
        appendAIMessage(`Connection issue: ${error.message || 'Unable to reach backend'}`);
    }
}

form.addEventListener('submit', (e) => {
    e.preventDefault();
    submitMessage(input.value.trim());
});