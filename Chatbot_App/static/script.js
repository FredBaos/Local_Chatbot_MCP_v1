let savedpasttext = []; // Variable to store the message
let savedpastresponse = []; // Variable to store the message

// Section: get the Id of the talking container
const messagesContainer = document.getElementById('messages-container');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
//

//Section: function to creat the dialogue window
const addMessage = (message, role) => {
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
//


//Section: Calling the model
const sendMessage = async (message) => {
  addMessage(message, 'user');
  // Loading animation
  const loadingRow = document.createElement('div');
  loadingRow.className = 'loading-row';
  const loadingElement = document.createElement('div');
  loadingElement.className = 'loading-animation';
  loadingRow.appendChild(loadingElement);
  messagesContainer.appendChild(loadingRow);
  loadingRow.scrollIntoView({ block: 'end' });

  async function makePostRequest(msg) {
    const url = '/analyze';
    const requestBody = {
      text: msg
    };
  
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });
  
      const data = await response.text();
      // Handle the response data here
      console.log(data);
      return data;
    } catch (error) {
      // Handle any errors that occurred during the request
      console.error('Error:', error);
      return error
    }
  }
  
  var res = await makePostRequest(message);
  
  data = {"response": res};
  
  // Deleting the loading animation
  loadingRow.remove();

  if (data.error) {
    const errorMessage = JSON.stringify(data);
    addMessage(errorMessage, 'error');
  } else {
    const responseMessage = data['response'];
    addMessage(responseMessage, 'aibot');
  }
};

//Section: Button to submit to the model and get the response
messageForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (message !== '') {
    messageInput.value = '';
    await sendMessage(message);
  }
});

// Send the message when pressing Enter in the textarea.
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
