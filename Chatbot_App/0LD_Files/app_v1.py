from flask import Flask, request, render_template
from flask_cors import CORS
import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

app = Flask(__name__)
CORS(app)

model_name = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
tokenizer = None
model = None
device = "cpu"
conversation_history = []


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model():
    global tokenizer, model, device
    if tokenizer is not None and model is not None:
        return

    device = get_device()
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.unk_token

    torch_dtype = torch.float16 if device != "cpu" else torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map=device,
        torch_dtype=torch_dtype,
    )
    model.eval()

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
    load_model()
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
            eos_token_id=tokenizer.eos_token_id,
        )

    # Decode the response
    #response = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)

    # Add interaction to conversation history
    conversation_history.append(input_text)
    conversation_history.append(response)

    return response

if __name__ == '__main__':
    app.run()
