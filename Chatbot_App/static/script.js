const messagesContainer = document.getElementById('messages-container');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const tabBar = document.getElementById('tab-bar');
const newChatBtn = document.getElementById('new-chat-btn');

let conversations = [];
let activeConversationIndex = 0;

const createConversation = (title = 'Chat 1') => ({
  title,
  messages: []
});

const renderTabs = () => {
  tabBar.innerHTML = '';
  conversations.forEach((conversation, index) => {
    const tabButton = document.createElement('button');
    tabButton.className = `tab${index === activeConversationIndex ? ' active' : ''}`;
    tabButton.textContent = conversation.title;
    tabButton.type = 'button';
    tabButton.title = 'Click to switch chat. Double-click to rename.';
    tabButton.addEventListener('click', () => switchConversation(index));
    tabButton.addEventListener('dblclick', () => renameConversation(index));
    tabBar.appendChild(tabButton);
  });
};

const renameConversation = (index) => {
  const current = conversations[index].title;
  const newTitle = prompt('Rename chat', current);
  if (newTitle === null) return;
  const trimmedTitle = newTitle.trim();
  if (trimmedTitle.length === 0) return;
  conversations[index].title = trimmedTitle;
  renderTabs();
};

const switchConversation = (index) => {
  if (index === activeConversationIndex) return;
  activeConversationIndex = index;
  renderTabs();
  renderMessages();
};

const renderMessages = () => {
  messagesContainer.innerHTML = '';
  const conversation = conversations[activeConversationIndex];

  conversation.messages.forEach((message) => {
    const messageElement = document.createElement('div');
    const textElement = document.createElement('p');
    messageElement.className = `message ${message.role}`;
    textElement.innerText = message.content;
    messageElement.appendChild(textElement);
    messagesContainer.appendChild(messageElement);
    const clearDiv = document.createElement('div');
    clearDiv.style.clear = 'both';
    messagesContainer.appendChild(clearDiv);
  });

  messagesContainer.scrollTop = messagesContainer.scrollHeight;
};

const addMessage = (message, role) => {
  conversations[activeConversationIndex].messages.push({ content: message, role });
  const messageElement = document.createElement('div');
  const textElement = document.createElement('p');
  messageElement.className = `message ${role}`;
  textElement.innerText = message;
  messageElement.appendChild(textElement);
  messagesContainer.appendChild(messageElement);
  const clearDiv = document.createElement('div');
  clearDiv.style.clear = 'both';
  messagesContainer.appendChild(clearDiv);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
};

const addNewConversation = () => {
  const title = `Chat ${conversations.length + 1}`;
  conversations.push(createConversation(title));
  activeConversationIndex = conversations.length - 1;
  renderTabs();
  renderMessages();
  messageInput.focus();
};

const sendMessage = async (message) => {
  addMessage(message, 'user');

  const loadingRow = document.createElement('div');
  loadingRow.className = 'loading-row';
  const loadingElement = document.createElement('div');
  loadingElement.className = 'loading-animation';
  loadingRow.appendChild(loadingElement);
  messagesContainer.appendChild(loadingRow);
  loadingRow.scrollIntoView({ block: 'end' });

  const requestBody = { text: message };

  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    const data = await response.text();
    loadingRow.remove();

    if (!response.ok) {
      addMessage(`Error: ${data}`, 'error');
      return;
    }

    addMessage(data, 'aibot');
  } catch (error) {
    loadingRow.remove();
    addMessage(`Request failed: ${error.message}`, 'error');
  }
};

messageForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (message !== '') {
    messageInput.value = '';
    await sendMessage(message);
  }
});

messageInput.addEventListener('keydown', async (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    const message = messageInput.value.trim();
    if (message !== '') {
      messageInput.value = '';
      await sendMessage(message);
    }
  }
});

newChatBtn.addEventListener('click', addNewConversation);

const initialize = () => {
  conversations = [createConversation('Chat 1')];
  activeConversationIndex = 0;
  renderTabs();
  renderMessages();
};

initialize();
