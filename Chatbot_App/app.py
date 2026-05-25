from flask import Flask, request, render_template
from flask_cors import CORS
import json
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, AutoModelForCausalLM

app = Flask(__name__)
CORS(app)

'''
model_name = "facebook/blenderbot-400M-distill"
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)
'''

model_name = "HuggingFaceTB/SmolLM2-360M-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.unk_token
model = AutoModelForCausalLM.from_pretrained(
  model_name,
  device_map="cpu",
  torch_dtype=torch.float32
)

conversation_history = []

@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/chatbot', methods=['POST'])
def handle_prompt():
    data = request.get_data(as_text=True)
    data = json.loads(data)
    print(data) # DEBUG
    input_text = data['prompt']
	
	# Create conversation history string
    history = "\n".join(conversation_history)

	# Tokenize the input text and history
    inputs = tokenizer._encode_plus(history, input_text, return_tensors="pt")

    # Generate the response from the model
    outputs = model.generate(**inputs)

	# Decode the response
    response = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

	# Add interaction to conversation history
    conversation_history.append(input_text)
    conversation_history.append(response)

    return response

if __name__ == '__main__':
    app.run()
