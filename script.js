const form = document.querySelector('#chatForm');
const input = document.querySelector('#messageInput');
const conversation = document.querySelector('#conversation');
const suggestions = document.querySelector('#suggestions');
const newChatButton = document.querySelector('#newChatButton');
const themeButton = document.querySelector('#themeButton');
const moreButton = document.querySelector('#moreButton');
const moreMenu = document.querySelector('#moreMenu');
const clearChatButton = document.querySelector('#clearChatButton');
const copyReplyButton = document.querySelector('#copyReplyButton');
const attachButton = document.querySelector('#attachButton');
const fileInput = document.querySelector('#fileInput');

const responses = [
  {
    match: ['plan', 'week', 'schedule'],
    answer: 'Let’s make it feel lighter. Start by choosing one important outcome for the week, then add two smaller wins and leave a little white space around them. What is the one thing you want to feel proud of on Friday?'
  },
  {
    match: ['creative', 'prompt', 'idea'],
    answer: 'Try this: describe an ordinary object as if it has been quietly watching your life for a year. Give it one secret, one fear, and one generous act. Keep it to 200 words.'
  },
  {
    match: ['decision', 'choose', 'think', 'should'],
    answer: 'A useful first pass is to separate the decision from the emotion around it. Write down what each option makes possible, what it costs, and which regret you would rather carry. I can help you work through the list.'
  }
];

function getResponse(message) {
  const lowerMessage = message.toLowerCase();
  const foundResponse = responses.find(({ match }) => match.some((word) => lowerMessage.includes(word)));
  return foundResponse?.answer || 'That sounds worth exploring. Tell me a little more about what you are trying to make sense of, and we can take it one step at a time.';
}

function addMessage(text, type) {
  const row = document.createElement('div');
  row.className = `message-row ${type}-row`;
  const now = type === 'user' ? 'Just now' : 'A moment ago';
  row.innerHTML = type === 'assistant'
    ? `<div class="assistant-avatar" aria-hidden="true">✦</div><div class="message-content"><div class="message-meta"><strong>Orbit</strong><span>${now}</span></div><div class="message-bubble">${text}</div></div>`
    : `<div class="message-content"><div class="message-meta"><strong>You</strong><span>${now}</span></div><div class="message-bubble">${text}</div></div>`;
  conversation.appendChild(row);
  row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showTyping() {
  const typing = document.createElement('div');
  typing.className = 'message-row assistant-row';
  typing.id = 'typingIndicator';
  typing.innerHTML = '<div class="assistant-avatar" aria-hidden="true">✦</div><div class="message-content"><div class="message-meta"><strong>Orbit</strong><span>Thinking...</span></div><div class="typing">Orbit is gathering a thought<span>...</span></div></div>';
  conversation.appendChild(typing);
  typing.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.querySelector('.chat-panel').appendChild(toast);
  window.setTimeout(() => toast.remove(), 2200);
}

function sendMessage(message) {
  const cleanMessage = message.trim();
  if (!cleanMessage) return;
  addMessage(cleanMessage.replace(/</g, '&lt;').replace(/>/g, '&gt;'), 'user');
  input.value = '';
  input.style.height = 'auto';
  suggestions?.remove();
  showTyping();
  window.setTimeout(() => {
    document.querySelector('#typingIndicator')?.remove();
    addMessage(getResponse(cleanMessage), 'assistant');
  }, 650);
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
});

document.querySelectorAll('.suggestion').forEach((button) => {
  button.addEventListener('click', () => sendMessage(button.dataset.prompt));
});

newChatButton.addEventListener('click', () => {
  conversation.innerHTML = `<div class="welcome-row message-row assistant-row"><div class="assistant-avatar" aria-hidden="true">✦</div><div class="message-content"><div class="message-meta"><strong>Orbit</strong><span>Just now</span></div><div class="message-bubble welcome-bubble">Fresh page, clear mind. What would you like to work through?</div></div></div>`;
  input.focus();
});

themeButton.addEventListener('click', () => {
  document.documentElement.classList.toggle('dark');
  document.body.classList.toggle('dark');
  const isDark = document.documentElement.classList.contains('dark');
  themeButton.textContent = isDark ? '☼' : '◐';
  document.querySelectorAll('.suggestion').forEach((button) => {
    if (isDark) {
      button.style.setProperty('background', '#202d44', 'important');
    } else {
      button.style.removeProperty('background-color');
    }
  });
  input.style.backgroundColor = isDark ? 'transparent' : '';
});

moreButton.addEventListener('click', (event) => {
  event.stopPropagation();
  const isOpen = moreMenu.classList.toggle('open');
  moreButton.setAttribute('aria-expanded', String(isOpen));
});

document.addEventListener('click', () => {
  moreMenu.classList.remove('open');
  moreButton.setAttribute('aria-expanded', 'false');
});

clearChatButton.addEventListener('click', () => {
  newChatButton.click();
  showToast('Chat cleared');
});

copyReplyButton.addEventListener('click', async () => {
  const lastReply = conversation.querySelector('.assistant-row:last-of-type .message-bubble');
  if (!lastReply) return;
  await navigator.clipboard?.writeText(lastReply.textContent);
  showToast('Reply copied');
});

attachButton.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  const fileName = fileInput.files[0]?.name;
  if (fileName) showToast(`${fileName} ready to attach`);
});
