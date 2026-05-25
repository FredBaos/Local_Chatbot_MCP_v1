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

#model_name = "HuggingFaceTB/SmolLM2-360M-Instruct"
model_name = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.unk_token

device = "mps" if torch.backends.mps.is_available() else "cpu"
model = AutoModelForCausalLM.from_pretrained(
  model_name,
  #device_map="cpu",
  device_map=device,
  #torch_dtype=torch.float32
  torch_dtype=torch.float16
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
    #inputs = tokenizer._encode_plus(history, input_text, return_tensors="pt")
    inputs = tokenizer(history, input_text, return_tensors="pt").to(device)

    # Generate the response from the model
    #outputs = model.generate(**inputs)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,       
            do_sample=True,            
            temperature=0.7,           
            top_p=0.9,   
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,              
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )

	# Decode the response
    #response = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)

# 4. Decode only the response
    

	# Add interaction to conversation history
    conversation_history.append(input_text)
    conversation_history.append(response)

    return response

if __name__ == '__main__':
    app.run()
