const messagesContainer = document.getElementById('messages-container');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const tabBar = document.getElementById('tab-bar');
const newChatBtn = document.getElementById('new-chat-btn');

let conversations = [];
let activeConversationIndex = 0;

const createConversation = (title = 'Chat 1', sessionId = null) => ({
  title,
  sessionId,
  messages: []
});

const makeSessionId = () => `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

const renderTabs = () => {
  tabBar.innerHTML = '';
  conversations.forEach((conversation, index) => {
    const tabWrapper = document.createElement('div');
    tabWrapper.className = 'tab-wrapper';

    const tabButton = document.createElement('button');
    tabButton.className = `tab${index === activeConversationIndex ? ' active' : ''}`;
    tabButton.textContent = conversation.title;
    tabButton.type = 'button';
    tabButton.title = 'Click to switch chat. Double-click to rename.';
    tabButton.addEventListener('click', () => switchConversation(index));
    tabButton.addEventListener('dblclick', () => renameConversation(index));

    const deleteToggleButton = document.createElement('button');
    deleteToggleButton.className = 'tab-delete-toggle';
    deleteToggleButton.type = 'button';
    deleteToggleButton.title = 'Delete chat';
    deleteToggleButton.innerHTML = '✕';
    deleteToggleButton.addEventListener('click', (event) => {
      event.stopPropagation();
      toggleDeleteConfirm(index);
    });

    const deleteConfirmButton = document.createElement('button');
    deleteConfirmButton.className = 'tab-delete-confirm';
    deleteConfirmButton.type = 'button';
    deleteConfirmButton.title = 'Confirm delete';
    deleteConfirmButton.innerHTML = '🗑';
    deleteConfirmButton.style.display = 'none';
    deleteConfirmButton.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteConversation(index);
    });

    tabWrapper.appendChild(tabButton);
    tabWrapper.appendChild(deleteToggleButton);
    tabWrapper.appendChild(deleteConfirmButton);
    tabBar.appendChild(tabWrapper);
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

const toggleDeleteConfirm = (index) => {
  const tabWrapper = tabBar.children[index];
  if (!tabWrapper) return;

  const deleteToggleButton = tabWrapper.querySelector('.tab-delete-toggle');
  const deleteConfirmButton = tabWrapper.querySelector('.tab-delete-confirm');

  if (!deleteToggleButton || !deleteConfirmButton) return;

  const showConfirm = deleteConfirmButton.style.display === 'none';
  deleteConfirmButton.style.display = showConfirm ? 'inline-flex' : 'none';
  deleteToggleButton.style.opacity = showConfirm ? '0.6' : '1';
};

const deleteConversation = async (index) => {
  const conversation = conversations[index];
  if (!conversation) return;

  try {
    if (conversation.sessionId) {
      await fetch(`/delete-session/${encodeURIComponent(conversation.sessionId)}`, {
        method: 'DELETE'
      });
    }

    conversations.splice(index, 1);
    if (conversations.length === 0) {
      conversations.push(createConversation('Chat 1', makeSessionId()));
    }
    activeConversationIndex = Math.min(index, conversations.length - 1);
    renderTabs();
    renderMessages();
  } catch (error) {
    console.error('Failed to delete conversation:', error);
  }
};

const renderCitations = (citations) => {
  if (!citations || citations.length === 0) return null;

  const citationsElement = document.createElement('p');
  citationsElement.className = 'message-citations';
  citationsElement.innerText = 'Sources: ' + citations
    .map((citation) => {
      const confidence = typeof citation.confidence === 'number' ? `, ${citation.confidence}%` : '';
      return `${citation.title} (${citation.source}${confidence})`;
    })
    .join(' · ');
  return citationsElement;
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
    const citationsElement = renderCitations(message.citations);
    if (citationsElement) messageElement.appendChild(citationsElement);
    messagesContainer.appendChild(messageElement);
    const clearDiv = document.createElement('div');
    clearDiv.style.clear = 'both';
    messagesContainer.appendChild(clearDiv);
  });

  messagesContainer.scrollTop = messagesContainer.scrollHeight;
};

const addMessage = (message, role, citations = null) => {
  conversations[activeConversationIndex].messages.push({ content: message, role, citations });
  const messageElement = document.createElement('div');
  const textElement = document.createElement('p');
  messageElement.className = `message ${role}`;
  textElement.innerText = message;
  messageElement.appendChild(textElement);
  const citationsElement = renderCitations(citations);
  if (citationsElement) messageElement.appendChild(citationsElement);
  messagesContainer.appendChild(messageElement);
  const clearDiv = document.createElement('div');
  clearDiv.style.clear = 'both';
  messagesContainer.appendChild(clearDiv);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
};

const addNewConversation = () => {
  const title = `Chat ${conversations.length + 1}`;
  const sessionId = makeSessionId();
  conversations.push(createConversation(title, sessionId));
  activeConversationIndex = conversations.length - 1;
  renderTabs();
  renderMessages();
  messageInput.focus();
};

const sendMessage = async (message) => {
  const conversation = conversations[activeConversationIndex];
  const sessionId = conversation.sessionId || makeSessionId();
  if (!conversation.sessionId) {
    conversation.sessionId = sessionId;
  }

  addMessage(message, 'user');

  const loadingRow = document.createElement('div');
  loadingRow.className = 'loading-row';
  const loadingElement = document.createElement('div');
  loadingElement.className = 'loading-animation';
  loadingRow.appendChild(loadingElement);
  messagesContainer.appendChild(loadingRow);
  loadingRow.scrollIntoView({ block: 'end' });

  const requestBody = {
    text: message,
    session_id: sessionId
  };

  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    const data = await response.json();
    loadingRow.remove();

    if (!response.ok) {
      addMessage(`Error: ${data.error || 'Unknown error'}`, 'error');
      return;
    }

    addMessage(data.response, 'aibot', data.citations);
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

const restoreConversations = async () => {
  try {
    const response = await fetch('/sessions');
    const sessions = await response.json();

    if (!Array.isArray(sessions)) {
      throw new Error('Invalid sessions response');
    }

    if (sessions.length === 0) {
      conversations = [createConversation('Chat 1', makeSessionId())];
    } else {
      conversations = sessions.map((sessionId, index) => ({
        title: `Chat ${index + 1}`,
        sessionId,
        messages: []
      }));

      for (const conversation of conversations) {
        const historyResponse = await fetch(`/history/${conversation.sessionId}`);
        const historyData = await historyResponse.json();
        conversation.messages = (historyData.messages || []).map((msg) => ({
          role: msg.role === 'assistant' ? 'aibot' : msg.role,
          content: msg.content,
          citations: msg.citations
        }));
      }
    }

    activeConversationIndex = 0;
    renderTabs();
    renderMessages();
  } catch (error) {
    conversations = [createConversation('Chat 1', makeSessionId())];
    activeConversationIndex = 0;
    renderTabs();
    renderMessages();
  }
};

restoreConversations();
